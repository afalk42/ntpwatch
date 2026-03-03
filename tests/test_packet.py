"""Tests for NTP packet encode/decode."""

import struct
import pytest
from ntpwatch.ntp.packet import (
    NTP_DELTA,
    NTP_PACKET_SIZE,
    NTPPacket,
    KissOfDeathError,
    MalformedPacketError,
    build_request,
    parse_response,
    ref_id_to_str,
    unix_to_ntp,
    ntp_to_unix,
    _float_to_ntp_ts,
    _ntp_ts_to_float,
    _seconds_to_ntp_short,
    _ntp_short_to_seconds,
    MODE_CLIENT,
    MODE_SERVER,
    NTP_VERSION,
    LEAP_NONE,
)


class TestTimestampConversion:
    def test_unix_ntp_roundtrip(self):
        unix_ts = 1700000000.123456
        assert abs(ntp_to_unix(unix_to_ntp(unix_ts)) - unix_ts) < 1e-6

    def test_ntp_delta(self):
        assert NTP_DELTA == 2208988800

    def test_ntp_ts_roundtrip(self):
        original = 3900000000.5
        integer, fraction = _float_to_ntp_ts(original)
        result = _ntp_ts_to_float(integer, fraction)
        assert abs(result - original) < 1e-6

    def test_ntp_ts_zero(self):
        integer, fraction = _float_to_ntp_ts(0.0)
        assert integer == 0
        assert fraction == 0

    def test_ntp_short_roundtrip(self):
        original = 0.123
        encoded = _seconds_to_ntp_short(original)
        decoded = _ntp_short_to_seconds(encoded)
        assert abs(decoded - original) < 0.001

    def test_ntp_short_zero(self):
        assert _seconds_to_ntp_short(0.0) == 0
        assert _ntp_short_to_seconds(0) == 0.0

    def test_ntp_short_negative_clamps(self):
        assert _seconds_to_ntp_short(-1.0) == 0


class TestNTPPacket:
    def test_encode_decode_roundtrip(self):
        pkt = NTPPacket(
            li=0, vn=4, mode=MODE_CLIENT,
            stratum=2, poll=6, precision=-20,
            root_delay=0.015625, root_dispersion=0.03125,
            ref_id=0xC0A80101,
            ref_ts=3900000000.5,
            orig_ts=3900000001.25,
            recv_ts=3900000001.5,
            tx_ts=3900000001.75,
        )
        data = pkt.to_bytes()
        assert len(data) == NTP_PACKET_SIZE

        decoded = NTPPacket.from_bytes(data)
        assert decoded.li == pkt.li
        assert decoded.vn == pkt.vn
        assert decoded.mode == pkt.mode
        assert decoded.stratum == pkt.stratum
        assert decoded.poll == pkt.poll
        assert abs(decoded.root_delay - pkt.root_delay) < 0.001
        assert abs(decoded.root_dispersion - pkt.root_dispersion) < 0.001
        assert decoded.ref_id == pkt.ref_id
        assert abs(decoded.ref_ts - pkt.ref_ts) < 1e-6
        assert abs(decoded.tx_ts - pkt.tx_ts) < 1e-6

    def test_packet_size(self):
        pkt = NTPPacket()
        assert len(pkt.to_bytes()) == 48

    def test_first_byte_encoding(self):
        pkt = NTPPacket(li=2, vn=4, mode=3)
        data = pkt.to_bytes()
        first = data[0]
        assert (first >> 6) & 0x3 == 2  # LI
        assert (first >> 3) & 0x7 == 4  # VN
        assert first & 0x7 == 3  # Mode

    def test_decode_too_short(self):
        with pytest.raises(MalformedPacketError):
            NTPPacket.from_bytes(b"\x00" * 10)

    def test_decode_extra_bytes_ok(self):
        pkt = NTPPacket()
        data = pkt.to_bytes() + b"\xff" * 20
        decoded = NTPPacket.from_bytes(data)
        assert decoded.li == pkt.li


class TestBuildRequest:
    def test_returns_48_bytes(self):
        data, tx_time = build_request()
        assert len(data) == 48
        assert tx_time > 0

    def test_mode_is_client(self):
        data, _ = build_request()
        first = data[0]
        assert first & 0x7 == MODE_CLIENT

    def test_version_is_4(self):
        data, _ = build_request()
        first = data[0]
        assert (first >> 3) & 0x7 == NTP_VERSION

    def test_transmit_timestamp_set(self):
        data, tx_time = build_request()
        pkt = NTPPacket.from_bytes(data)
        # tx_ts should be near tx_time converted to NTP
        expected_ntp = unix_to_ntp(tx_time)
        assert abs(pkt.tx_ts - expected_ntp) < 1.0


class TestParseResponse:
    def _make_server_response(self, stratum=2, ref_id=0xC0A80101):
        pkt = NTPPacket(
            li=LEAP_NONE, vn=NTP_VERSION, mode=MODE_SERVER,
            stratum=stratum, poll=6, precision=-20,
            root_delay=0.01, root_dispersion=0.02,
            ref_id=ref_id,
            ref_ts=3900000000.0,
            orig_ts=3900000001.0,
            recv_ts=3900000001.001,
            tx_ts=3900000001.002,
        )
        return pkt.to_bytes()

    def test_parse_valid_response(self):
        data = self._make_server_response()
        pkt = parse_response(data)
        assert pkt.mode == MODE_SERVER
        assert pkt.stratum == 2

    def test_parse_wrong_mode_raises(self):
        pkt = NTPPacket(mode=MODE_CLIENT)
        with pytest.raises(MalformedPacketError):
            parse_response(pkt.to_bytes())

    def test_kiss_of_death(self):
        # Stratum 0 with RATE kiss code
        rate_id = int.from_bytes(b"RATE", "big")
        data = self._make_server_response(stratum=0, ref_id=rate_id)
        with pytest.raises(KissOfDeathError) as exc:
            parse_response(data)
        assert exc.value.code == "RATE"


class TestRefIdToStr:
    def test_stratum_1_gps(self):
        ref_id = int.from_bytes(b"GPS\x00", "big")
        assert ref_id_to_str(ref_id, 1) == "GPS"

    def test_stratum_1_pps(self):
        ref_id = int.from_bytes(b"PPS\x00", "big")
        assert ref_id_to_str(ref_id, 1) == "PPS"

    def test_stratum_0_kiss_code(self):
        ref_id = int.from_bytes(b"DENY", "big")
        assert ref_id_to_str(ref_id, 0) == "DENY"

    def test_stratum_2_ipv4(self):
        ref_id = (192 << 24) | (168 << 16) | (1 << 8) | 1
        assert ref_id_to_str(ref_id, 2) == "192.168.1.1"

    def test_stratum_3_ipv4(self):
        ref_id = (10 << 24) | (0 << 16) | (0 << 8) | 1
        assert ref_id_to_str(ref_id, 3) == "10.0.0.1"
