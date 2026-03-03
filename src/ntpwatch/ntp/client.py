"""Async NTP Mode 3 client — basic time queries."""

from __future__ import annotations

import asyncio
import time

from .packet import (
    NTPPacket,
    NTPError,
    NTPTimeoutError,
    KissOfDeathError,
    MalformedPacketError,
    build_request,
    parse_response,
    ntp_to_unix,
    ref_id_to_str,
    MODE_SERVER,
)
from .types import NTPResult


async def query_ntp(
    host: str,
    port: int = 123,
    timeout: float = 5.0,
) -> NTPResult:
    """Send a Mode 3 NTP query and return the result.

    Uses asyncio UDP for non-blocking I/O.
    """
    request_data, t1_unix = build_request()

    loop = asyncio.get_running_loop()
    response_future: asyncio.Future[tuple[bytes, float]] = loop.create_future()

    class NTPProtocol(asyncio.DatagramProtocol):
        def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
            t4 = time.time()
            if not response_future.done():
                response_future.set_result((data, t4))

        def error_received(self, exc: Exception) -> None:
            if not response_future.done():
                response_future.set_exception(
                    NTPError(f"UDP error: {exc}")
                )

        def connection_lost(self, exc: Exception | None) -> None:
            if exc and not response_future.done():
                response_future.set_exception(
                    NTPError(f"Connection lost: {exc}")
                )

    transport, protocol = await loop.create_datagram_endpoint(
        NTPProtocol,
        remote_addr=(host, port),
    )

    try:
        transport.sendto(request_data)

        try:
            data, t4_unix = await asyncio.wait_for(response_future, timeout=timeout)
        except asyncio.TimeoutError:
            raise NTPTimeoutError(f"No response from {host}:{port} within {timeout}s")

        pkt = parse_response(data)

        # Convert NTP timestamps to Unix
        t2_unix = ntp_to_unix(pkt.recv_ts)
        t3_unix = ntp_to_unix(pkt.tx_ts)

        # Offset and delay calculation per RFC 5905
        offset = ((t2_unix - t1_unix) + (t3_unix - t4_unix)) / 2
        delay = (t4_unix - t1_unix) - (t3_unix - t2_unix)

        return NTPResult(
            offset_s=offset,
            delay_s=delay,
            stratum=pkt.stratum,
            leap=pkt.li,
            ref_id=ref_id_to_str(pkt.ref_id, pkt.stratum),
            root_delay_s=pkt.root_delay,
            root_dispersion_s=pkt.root_dispersion,
            ref_timestamp=ntp_to_unix(pkt.ref_ts),
            poll=pkt.poll,
            precision=pkt.precision,
            version=pkt.vn,
        )
    finally:
        transport.close()
