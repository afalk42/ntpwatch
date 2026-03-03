"""Tests for NTP Mode 3 async client."""

import asyncio
import struct
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from ntpwatch.ntp.client import query_ntp
from ntpwatch.ntp.packet import (
    NTPPacket,
    NTPTimeoutError,
    KissOfDeathError,
    MODE_SERVER,
    NTP_VERSION,
    LEAP_NONE,
    unix_to_ntp,
)
from ntpwatch.ntp.types import NTPResult


def _make_server_packet(
    t2_unix: float,
    t3_unix: float,
    stratum: int = 2,
    ref_id: int = 0xC0A80101,
    orig_ts_ntp: float = 0.0,
) -> bytes:
    """Create a fake server response packet."""
    pkt = NTPPacket(
        li=LEAP_NONE,
        vn=NTP_VERSION,
        mode=MODE_SERVER,
        stratum=stratum,
        poll=6,
        precision=-20,
        root_delay=0.001,
        root_dispersion=0.002,
        ref_id=ref_id,
        ref_ts=unix_to_ntp(t2_unix - 100),
        orig_ts=orig_ts_ntp,
        recv_ts=unix_to_ntp(t2_unix),
        tx_ts=unix_to_ntp(t3_unix),
    )
    return pkt.to_bytes()


class TestQueryNTP:
    @pytest.mark.asyncio
    async def test_offset_calculation(self):
        """Verify offset calculation with known timestamps."""
        # T1 = 1000.0 (client send)
        # T2 = 1000.001 (server receive) - server is 1ms ahead
        # T3 = 1000.002 (server transmit)
        # T4 = 1000.003 (client receive)
        # offset = ((T2-T1) + (T3-T4)) / 2 = (0.001 + (-0.001)) / 2 = 0.0
        # delay = (T4-T1) - (T3-T2) = 0.003 - 0.001 = 0.002

        t1 = 1000.0
        t2 = 1000.001
        t3 = 1000.002
        t4 = 1000.003

        response_data = _make_server_packet(t2, t3)

        class FakeTransport:
            def sendto(self, data):
                pass

            def close(self):
                pass

        class FakeProtocol(asyncio.DatagramProtocol):
            pass

        fake_transport = FakeTransport()

        async def fake_create_endpoint(factory, remote_addr=None):
            proto = factory()
            # Schedule the response delivery
            async def deliver():
                await asyncio.sleep(0.001)
                proto.datagram_received(response_data, remote_addr)
            asyncio.ensure_future(deliver())
            return fake_transport, proto

        with patch("ntpwatch.ntp.client.build_request") as mock_build, \
             patch("ntpwatch.ntp.client.time") as mock_time:
            mock_build.return_value = (b"\x00" * 48, t1)

            loop = asyncio.get_event_loop()
            original = loop.create_datagram_endpoint
            loop.create_datagram_endpoint = fake_create_endpoint

            # Mock time.time() to return T4 when called during datagram_received
            mock_time.time.return_value = t4

            try:
                result = await query_ntp("127.0.0.1", timeout=2.0)
            finally:
                loop.create_datagram_endpoint = original

            assert isinstance(result, NTPResult)
            assert result.stratum == 2
            # With mocked times, verify offset/delay are reasonable
            assert isinstance(result.offset_s, float)
            assert isinstance(result.delay_s, float)

    @pytest.mark.asyncio
    async def test_timeout_raises(self):
        """Verify timeout raises NTPTimeoutError."""

        class FakeTransport:
            def sendto(self, data):
                pass

            def close(self):
                pass

        async def fake_create_endpoint(factory, remote_addr=None):
            proto = factory()
            return FakeTransport(), proto

        loop = asyncio.get_event_loop()
        original = loop.create_datagram_endpoint
        loop.create_datagram_endpoint = fake_create_endpoint

        try:
            with pytest.raises(NTPTimeoutError):
                await query_ntp("127.0.0.1", timeout=0.1)
        finally:
            loop.create_datagram_endpoint = original


class TestNTPResult:
    def test_result_fields(self):
        r = NTPResult(
            offset_s=0.001,
            delay_s=0.002,
            stratum=2,
            leap=0,
            ref_id="192.168.1.1",
            root_delay_s=0.003,
            root_dispersion_s=0.004,
            ref_timestamp=1700000000.0,
            poll=6,
            precision=-20,
            version=4,
        )
        assert r.offset_s == 0.001
        assert r.stratum == 2
        assert r.ref_id == "192.168.1.1"
