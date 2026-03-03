"""Tests for NTP Mode 6 control queries."""

import struct
import pytest

from ntpwatch.ntp.control import (
    _parse_control_header,
    _parse_varlist,
    _split_vars,
    _extract_tally_code,
    _extract_peer_type,
    _build_control_packet,
    _TALLY_CODES,
    OP_READSTAT,
    OP_READVAR,
)
from ntpwatch.ntp.packet import NTPError


class TestParseControlHeader:
    def _make_header(
        self, mode=6, response=True, error=False, more=False,
        opcode=1, seq=1, status=0, assoc_id=0, offset=0, count=0,
    ) -> bytes:
        first = (4 << 3) | mode  # VN=4, mode
        rem = (opcode & 0x1F)
        if response:
            rem |= 0x80
        if error:
            rem |= 0x40
        if more:
            rem |= 0x20
        return struct.pack("!BBHHHHH", first, rem, seq, status, assoc_id, offset, count)

    def test_parse_valid_response(self):
        data = self._make_header(status=0x1234, assoc_id=5, count=20)
        hdr = _parse_control_header(data)
        assert hdr["response"] is True
        assert hdr["error"] is False
        assert hdr["more"] is False
        assert hdr["opcode"] == 1
        assert hdr["status"] == 0x1234
        assert hdr["assoc_id"] == 5
        assert hdr["count"] == 20

    def test_parse_error_response(self):
        data = self._make_header(error=True, status=0x0100)
        with pytest.raises(NTPError, match="Mode 6 error"):
            _parse_control_header(data)

    def test_parse_more_flag(self):
        data = self._make_header(more=True)
        hdr = _parse_control_header(data)
        assert hdr["more"] is True

    def test_too_short(self):
        with pytest.raises(NTPError, match="too short"):
            _parse_control_header(b"\x00" * 6)

    def test_wrong_mode(self):
        data = self._make_header(mode=3)
        with pytest.raises(NTPError, match="Not a Mode 6"):
            _parse_control_header(data)


class TestParseVarlist:
    def test_simple_vars(self):
        data = b'stratum=2, offset=0.123, refid=192.168.1.1'
        result = _parse_varlist(data)
        assert result["stratum"] == "2"
        assert result["offset"] == "0.123"
        assert result["refid"] == "192.168.1.1"

    def test_quoted_value(self):
        data = b'version="ntpd 4.2.8p15@1.3728-o"'
        result = _parse_varlist(data)
        assert result["version"] == "ntpd 4.2.8p15@1.3728-o"

    def test_empty_data(self):
        assert _parse_varlist(b"") == {}
        assert _parse_varlist(b"\x00\x00") == {}

    def test_no_value_key(self):
        data = b'leap_none'
        result = _parse_varlist(data)
        assert result["leap_none"] == ""

    def test_with_null_padding(self):
        data = b'stratum=1, refid=GPS\x00\x00\x00'
        result = _parse_varlist(data)
        assert result["stratum"] == "1"
        assert result["refid"] == "GPS"

    def test_quoted_with_comma(self):
        data = b'version="ntpd 4.2.8, release", stratum=2'
        result = _parse_varlist(data)
        assert result["version"] == "ntpd 4.2.8, release"
        assert result["stratum"] == "2"


class TestSplitVars:
    def test_simple(self):
        parts = _split_vars("a=1, b=2, c=3")
        assert len(parts) == 3

    def test_quoted_comma(self):
        parts = _split_vars('a="1,2", b=3')
        assert len(parts) == 2
        assert '"1,2"' in parts[0]


class TestTallyCodes:
    def test_all_codes(self):
        expected = {0: " ", 1: "x", 2: ".", 3: "-", 4: "+", 5: "#", 6: "*", 7: "o"}
        for code, char in expected.items():
            assert _extract_tally_code(code << 8) == char

    def test_sys_peer(self):
        # Selection code 6 = sys.peer = '*'
        status = 0x0600
        assert _extract_tally_code(status) == "*"

    def test_falseticker(self):
        status = 0x0100
        assert _extract_tally_code(status) == "x"

    def test_pps_peer(self):
        # Selection code 7 = PPS peer = 'o'
        status = 0x0700
        assert _extract_tally_code(status) == "o"


class TestPeerType:
    def test_unicast(self):
        assert _extract_peer_type("3") == "u"

    def test_broadcast(self):
        assert _extract_peer_type("5") == "b"

    def test_symmetric(self):
        assert _extract_peer_type("1") == "s"

    def test_unknown(self):
        assert _extract_peer_type("99") == "u"


class TestBuildControlPacket:
    def test_readstat_packet(self):
        data, seq = _build_control_packet(OP_READSTAT)
        assert len(data) >= 12
        first = data[0]
        assert first & 0x7 == 6  # Mode 6
        assert (first >> 3) & 0x7 == 4  # VN 4
        rem = data[1]
        assert rem & 0x1F == OP_READSTAT

    def test_readvar_with_data(self):
        var_data = b"stratum, offset"
        pkt, seq = _build_control_packet(OP_READVAR, assoc_id=5, data=var_data)
        assert len(pkt) >= 12 + len(var_data)
        # Check assoc_id is in bytes 6-7
        assoc = struct.unpack("!H", pkt[6:8])[0]
        assert assoc == 5

    def test_padding_to_4_bytes(self):
        data, seq = _build_control_packet(OP_READVAR, data=b"ab")
        # 12 header + 4 (padded from 2)
        assert len(data) == 16

    def test_sequence_increments(self):
        _, seq1 = _build_control_packet(OP_READSTAT)
        _, seq2 = _build_control_packet(OP_READSTAT)
        assert seq2 == seq1 + 1
