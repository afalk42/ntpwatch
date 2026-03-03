"""NTP Mode 6 control queries — peer associations and system variables."""

from __future__ import annotations

import asyncio
import struct
import time

from .packet import NTP_VERSION, NTPError, NTPTimeoutError
from .types import PeerInfo, SystemVariables


class Mode6NotSupportedError(NTPError):
    """Server does not support Mode 6 control queries."""


# Mode 6 opcodes
OP_READSTAT = 1
OP_READVAR = 2

# Tally code mapping: selection code (bits 11-8 of peer status) → character
_TALLY_CODES = {
    0: " ",  # reject
    1: "x",  # falseticker
    2: ".",  # excess
    3: "-",  # outlier
    4: "+",  # candidate
    5: "#",  # backup
    6: "*",  # sys.peer
    7: "o",  # PPS peer
}

# Sequence counter for Mode 6 requests
_sequence = 0


def _next_sequence() -> int:
    global _sequence
    _sequence = (_sequence + 1) & 0xFFFF
    return _sequence


def _build_control_packet(
    opcode: int,
    assoc_id: int = 0,
    data: bytes = b"",
) -> bytes:
    """Build a Mode 6 control packet.

    Header (12 bytes):
      Byte 0: LI(2) | VN(3) | Mode(3) = 0 | 4 | 6 = 0x26
      Byte 1: R(1) | E(1) | M(1) | Opcode(5)
      Bytes 2-3: Sequence number
      Bytes 4-5: Status (0 for requests)
      Bytes 6-7: Association ID
      Bytes 8-9: Offset (0 for requests)
      Bytes 10-11: Count (length of data)
    """
    first_byte = (NTP_VERSION << 3) | 6  # VN=4, Mode=6
    rem_byte = opcode & 0x1F  # R=0, E=0, M=0
    seq = _next_sequence()
    count = len(data)

    header = struct.pack(
        "!BBHHHHH",
        first_byte,
        rem_byte,
        seq,
        0,  # status
        assoc_id,
        0,  # offset
        count,
    )

    # Pad data to 4-byte boundary
    padded = data
    if len(data) % 4:
        padded = data + b"\x00" * (4 - len(data) % 4)

    return header + padded, seq


def _parse_control_header(data: bytes) -> dict:
    """Parse a Mode 6 control response header."""
    if len(data) < 12:
        raise NTPError("Control response too short")

    first, rem, seq, status, assoc_id, offset, count = struct.unpack(
        "!BBHHHHH", data[:12]
    )

    mode = first & 0x7
    if mode != 6:
        raise NTPError(f"Not a Mode 6 response (mode={mode})")

    response = bool(rem & 0x80)
    error = bool(rem & 0x40)
    more = bool(rem & 0x20)
    opcode = rem & 0x1F

    if error:
        error_code = (status >> 8) & 0xFF
        raise NTPError(f"Mode 6 error response (error_code={error_code})")

    return {
        "response": response,
        "error": error,
        "more": more,
        "opcode": opcode,
        "sequence": seq,
        "status": status,
        "assoc_id": assoc_id,
        "offset": offset,
        "count": count,
    }


async def _send_control(
    host: str,
    opcode: int,
    assoc_id: int = 0,
    data: bytes = b"",
    port: int = 123,
    timeout: float = 5.0,
) -> tuple[int, bytes]:
    """Send a Mode 6 control request and reassemble fragmented response.

    Returns (status_word, payload_bytes).
    """
    request, seq = _build_control_packet(opcode, assoc_id, data)

    loop = asyncio.get_running_loop()
    fragments: dict[int, bytes] = {}
    done_event = asyncio.Event()
    status_word = 0
    has_more = True

    class ControlProtocol(asyncio.DatagramProtocol):
        def datagram_received(self, resp_data: bytes, addr: tuple[str, int]) -> None:
            nonlocal has_more, status_word
            try:
                hdr = _parse_control_header(resp_data)
            except NTPError:
                return

            if not hdr["response"]:
                return

            status_word = hdr["status"]
            payload = resp_data[12 : 12 + hdr["count"]]
            fragments[hdr["offset"]] = payload

            if not hdr["more"]:
                has_more = False
                done_event.set()

        def error_received(self, exc: Exception) -> None:
            done_event.set()

    transport, protocol = await loop.create_datagram_endpoint(
        ControlProtocol,
        remote_addr=(host, port),
    )

    try:
        transport.sendto(request)

        try:
            await asyncio.wait_for(done_event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            if not fragments:
                raise Mode6NotSupportedError(
                    f"No Mode 6 response from {host}:{port}"
                )

        # Reassemble fragments
        assembled = b""
        for offset in sorted(fragments.keys()):
            assembled += fragments[offset]

        return status_word, assembled
    finally:
        transport.close()


def _parse_varlist(data: bytes) -> dict[str, str]:
    """Parse a comma-separated key=value variable list from Mode 6 readvar."""
    text = data.decode("ascii", errors="replace").rstrip("\x00").strip()
    if not text:
        return {}

    result = {}
    # Variables are comma-separated, values may be quoted
    for item in _split_vars(text):
        item = item.strip()
        if not item:
            continue
        if "=" in item:
            key, _, value = item.partition("=")
            key = key.strip()
            value = value.strip().strip('"')
            result[key] = value
        else:
            result[item.strip()] = ""
    return result


def _split_vars(text: str) -> list[str]:
    """Split variable list handling quoted values with commas."""
    parts = []
    current = []
    in_quotes = False

    for char in text:
        if char == '"':
            in_quotes = not in_quotes
            current.append(char)
        elif char == "," and not in_quotes:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)

    if current:
        parts.append("".join(current))

    return parts


async def readstat(
    host: str,
    port: int = 123,
    timeout: float = 5.0,
) -> list[tuple[int, int]]:
    """Read association status list (opcode 1).

    Returns list of (assoc_id, status_word) tuples.
    """
    _, payload = await _send_control(host, OP_READSTAT, port=port, timeout=timeout)

    peers = []
    # Each peer is 4 bytes: 2 bytes assoc_id + 2 bytes status
    for i in range(0, len(payload) - 3, 4):
        assoc_id, status = struct.unpack("!HH", payload[i : i + 4])
        if assoc_id != 0:
            peers.append((assoc_id, status))

    return peers


async def readvar(
    host: str,
    assoc_id: int = 0,
    varnames: list[str] | None = None,
    port: int = 123,
    timeout: float = 5.0,
) -> dict[str, str]:
    """Read variables (opcode 2).

    assoc_id=0 → system variables
    assoc_id=N → peer N's variables
    """
    data = b""
    if varnames:
        data = ", ".join(varnames).encode("ascii")

    _, payload = await _send_control(
        host, OP_READVAR, assoc_id=assoc_id, data=data, port=port, timeout=timeout
    )

    return _parse_varlist(payload)


def _extract_tally_code(status_word: int) -> str:
    """Extract tally code character from peer status word.

    Bits 13-11 (or 10-8 depending on numbering) contain the selection code.
    """
    selection = (status_word >> 8) & 0x7
    return _TALLY_CODES.get(selection, " ")


def _extract_peer_type(hmode: str) -> str:
    """Map hmode variable to peer type character."""
    mode_map = {
        "1": "s",  # symmetric active
        "2": "s",  # symmetric passive
        "3": "u",  # client (unicast)
        "4": "u",  # server
        "5": "b",  # broadcast
        "6": "b",  # broadcast client
    }
    return mode_map.get(hmode, "u")


async def get_peers(
    host: str,
    port: int = 123,
    timeout: float = 5.0,
) -> list[PeerInfo]:
    """Get peer associations with details.

    Performs readstat to get association IDs, then readvar for each peer.
    """
    assoc_list = await readstat(host, port=port, timeout=timeout)

    peers = []
    for assoc_id, status in assoc_list:
        try:
            variables = await readvar(
                host, assoc_id=assoc_id, port=port, timeout=timeout
            )
        except (NTPError, asyncio.TimeoutError):
            continue

        tally = _extract_tally_code(status)
        remote = variables.get("srcadr", variables.get("remote", "?"))
        ref_id = variables.get("refid", "")
        stratum = _safe_int(variables.get("stratum", "0"))
        hmode = variables.get("hmode", "3")
        peer_type = _extract_peer_type(hmode)
        when = _safe_int(variables.get("unreach", "0"))

        # Try to compute "when" from reftime or rec
        rec_str = variables.get("rec", "")
        if rec_str:
            try:
                rec_hex = rec_str.replace("0x", "").split(".")[0]
                rec_ntp = int(rec_hex, 16)
                when = max(0, int(time.time() + 2208988800 - rec_ntp))
            except (ValueError, TypeError):
                pass

        poll_val = _safe_int(variables.get("hpoll", variables.get("ppoll", "0")))
        reach = _safe_int(variables.get("reach", "0"))
        delay = _safe_float(variables.get("delay", "0"))
        offset = _safe_float(variables.get("offset", "0"))
        jitter = _safe_float(variables.get("jitter", variables.get("disp", "0")))

        peers.append(
            PeerInfo(
                tally_code=tally,
                remote=remote,
                ref_id=ref_id,
                stratum=stratum,
                peer_type=peer_type,
                when=when,
                poll=poll_val,
                reach=reach,
                delay_ms=delay,
                offset_ms=offset,
                jitter_ms=jitter,
                assoc_id=assoc_id,
            )
        )

    return peers


async def get_system_vars(
    host: str,
    port: int = 123,
    timeout: float = 5.0,
) -> SystemVariables:
    """Get system variables (assoc_id=0)."""
    variables = await readvar(host, assoc_id=0, port=port, timeout=timeout)
    return SystemVariables(raw=variables)


def _safe_int(val: str, default: int = 0) -> int:
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def _safe_float(val: str, default: float = 0.0) -> float:
    try:
        return float(val)
    except (ValueError, TypeError):
        return default
