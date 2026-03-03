"""NTP packet encoding/decoding per RFC 5905."""

from __future__ import annotations

import struct
import time
from dataclasses import dataclass

# Seconds between NTP epoch (1900-01-01) and Unix epoch (1970-01-01)
NTP_DELTA = 2208988800

# NTP protocol constants
NTP_VERSION = 4
MODE_CLIENT = 3
MODE_SERVER = 4
MODE_CONTROL = 6

# Leap indicator values
LEAP_NONE = 0
LEAP_61 = 1
LEAP_59 = 2
LEAP_ALARM = 3

# Packet size
NTP_PACKET_SIZE = 48


class NTPError(Exception):
    """Base exception for NTP errors."""


class KissOfDeathError(NTPError):
    """Server sent a Kiss-of-Death packet (stratum 0)."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(f"Kiss-of-Death: {code}")


class NTPTimeoutError(NTPError):
    """NTP query timed out."""


class MalformedPacketError(NTPError):
    """Received packet is malformed."""


@dataclass
class NTPPacket:
    """Represents a 48-byte NTP packet."""

    li: int = 0  # Leap indicator (2 bits)
    vn: int = NTP_VERSION  # Version number (3 bits)
    mode: int = MODE_CLIENT  # Mode (3 bits)
    stratum: int = 0
    poll: int = 0
    precision: int = 0
    root_delay: float = 0.0  # seconds (NTP short format)
    root_dispersion: float = 0.0  # seconds (NTP short format)
    ref_id: int = 0  # 4 bytes
    ref_ts: float = 0.0  # NTP timestamp (seconds since 1900)
    orig_ts: float = 0.0
    recv_ts: float = 0.0
    tx_ts: float = 0.0

    def to_bytes(self) -> bytes:
        """Encode packet to 48 bytes."""
        first_byte = (self.li << 6) | (self.vn << 3) | self.mode
        # precision is signed int8
        precision = self.precision & 0xFF

        root_delay_fixed = _seconds_to_ntp_short(self.root_delay)
        root_disp_fixed = _seconds_to_ntp_short(self.root_dispersion)

        ref_ts_int, ref_ts_frac = _float_to_ntp_ts(self.ref_ts)
        orig_ts_int, orig_ts_frac = _float_to_ntp_ts(self.orig_ts)
        recv_ts_int, recv_ts_frac = _float_to_ntp_ts(self.recv_ts)
        tx_ts_int, tx_ts_frac = _float_to_ntp_ts(self.tx_ts)

        return struct.pack(
            "!BBBb I I I II II II II",
            first_byte,
            self.stratum,
            self.poll,
            self.precision if self.precision < 128 else self.precision - 256,
            root_delay_fixed,
            root_disp_fixed,
            self.ref_id,
            ref_ts_int,
            ref_ts_frac,
            orig_ts_int,
            orig_ts_frac,
            recv_ts_int,
            recv_ts_frac,
            tx_ts_int,
            tx_ts_frac,
        )

    @classmethod
    def from_bytes(cls, data: bytes) -> NTPPacket:
        """Decode a 48-byte NTP packet."""
        if len(data) < NTP_PACKET_SIZE:
            raise MalformedPacketError(
                f"Packet too short: {len(data)} bytes (need {NTP_PACKET_SIZE})"
            )

        unpacked = struct.unpack(
            "!BBBb I I I II II II II",
            data[:NTP_PACKET_SIZE],
        )

        first_byte = unpacked[0]
        li = (first_byte >> 6) & 0x3
        vn = (first_byte >> 3) & 0x7
        mode = first_byte & 0x7

        return cls(
            li=li,
            vn=vn,
            mode=mode,
            stratum=unpacked[1],
            poll=unpacked[2],
            precision=unpacked[3],
            root_delay=_ntp_short_to_seconds(unpacked[4]),
            root_dispersion=_ntp_short_to_seconds(unpacked[5]),
            ref_id=unpacked[6],
            ref_ts=_ntp_ts_to_float(unpacked[7], unpacked[8]),
            orig_ts=_ntp_ts_to_float(unpacked[9], unpacked[10]),
            recv_ts=_ntp_ts_to_float(unpacked[11], unpacked[12]),
            tx_ts=_ntp_ts_to_float(unpacked[13], unpacked[14]),
        )


def build_request() -> tuple[bytes, float]:
    """Build a Mode 3 client request packet.

    Returns (packet_bytes, unix_transmit_time).
    """
    tx_time = time.time()
    pkt = NTPPacket(
        li=LEAP_NONE,
        vn=NTP_VERSION,
        mode=MODE_CLIENT,
        tx_ts=unix_to_ntp(tx_time),
    )
    return pkt.to_bytes(), tx_time


def parse_response(data: bytes) -> NTPPacket:
    """Parse a Mode 4 server response packet."""
    pkt = NTPPacket.from_bytes(data)
    if pkt.mode != MODE_SERVER:
        raise MalformedPacketError(f"Expected mode {MODE_SERVER}, got {pkt.mode}")
    if pkt.stratum == 0:
        code = ref_id_to_str(pkt.ref_id, 0)
        raise KissOfDeathError(code)
    return pkt


def ref_id_to_str(ref_id: int, stratum: int) -> str:
    """Convert a 4-byte reference ID to a human-readable string.

    Stratum 0-1: ASCII kiss code / reference clock ID (e.g. .GPS., .PPS.)
    Stratum 2+: IPv4 address of upstream server
    """
    if stratum <= 1:
        chars = ref_id.to_bytes(4, "big")
        return chars.decode("ascii", errors="replace").rstrip("\x00").strip()
    else:
        b = ref_id.to_bytes(4, "big")
        return f"{b[0]}.{b[1]}.{b[2]}.{b[3]}"


# --- Timestamp conversion helpers ---


def unix_to_ntp(unix_ts: float) -> float:
    """Convert Unix timestamp to NTP timestamp (seconds since 1900)."""
    return unix_ts + NTP_DELTA


def ntp_to_unix(ntp_ts: float) -> float:
    """Convert NTP timestamp to Unix timestamp."""
    return ntp_ts - NTP_DELTA


def _float_to_ntp_ts(t: float) -> tuple[int, int]:
    """Convert NTP float timestamp to (integer_part, fractional_part)."""
    if t == 0.0:
        return 0, 0
    integer = int(t)
    fraction = int((t - integer) * 2**32)
    return integer & 0xFFFFFFFF, fraction & 0xFFFFFFFF


def _ntp_ts_to_float(integer: int, fraction: int) -> float:
    """Convert (integer_part, fractional_part) to NTP float timestamp."""
    return float(integer) + float(fraction) / 2**32


def _seconds_to_ntp_short(secs: float) -> int:
    """Convert seconds to NTP short format (16.16 fixed-point), stored as uint32."""
    if secs < 0:
        secs = 0.0
    integer = int(secs)
    fraction = int((secs - integer) * 2**16)
    return ((integer & 0xFFFF) << 16) | (fraction & 0xFFFF)


def _ntp_short_to_seconds(val: int) -> float:
    """Convert NTP short format (16.16 fixed-point) to seconds."""
    integer = (val >> 16) & 0xFFFF
    fraction = val & 0xFFFF
    return float(integer) + float(fraction) / 2**16
