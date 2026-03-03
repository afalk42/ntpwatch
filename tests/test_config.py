"""Tests for config loading."""

import pytest
from pathlib import Path
from ntpwatch.config import (
    AppConfig,
    ServerConfig,
    ThresholdConfig,
    _parse_config,
    load_config,
    merge_cli_args,
)


class TestParseConfig:
    def test_empty_config(self):
        config = _parse_config({})
        assert config.servers == []
        assert config.poll_interval == 10
        assert config.theme == "dark"

    def test_general_settings(self):
        data = {
            "general": {
                "poll_interval": 5,
                "theme": "light",
            }
        }
        config = _parse_config(data)
        assert config.poll_interval == 5
        assert config.theme == "light"

    def test_servers(self):
        data = {
            "servers": [
                {"address": "192.168.1.1", "alias": "NTP1", "description": "Primary"},
                {"address": "time.google.com"},
            ]
        }
        config = _parse_config(data)
        assert len(config.servers) == 2
        assert config.servers[0].address == "192.168.1.1"
        assert config.servers[0].alias == "NTP1"
        assert config.servers[0].description == "Primary"
        assert config.servers[1].address == "time.google.com"
        assert config.servers[1].alias == ""

    def test_thresholds(self):
        data = {
            "thresholds": {
                "offset_warning_ms": 20.0,
                "offset_critical_ms": 200.0,
                "jitter_warning_ms": 10.0,
                "jitter_critical_ms": 100.0,
                "unreachable_after": 5,
            }
        }
        config = _parse_config(data)
        assert config.thresholds.offset_warning_ms == 20.0
        assert config.thresholds.offset_critical_ms == 200.0
        assert config.thresholds.unreachable_after == 5

    def test_default_thresholds(self):
        config = _parse_config({})
        assert config.thresholds.offset_warning_ms == 10.0
        assert config.thresholds.offset_critical_ms == 100.0
        assert config.thresholds.jitter_warning_ms == 5.0
        assert config.thresholds.jitter_critical_ms == 50.0
        assert config.thresholds.unreachable_after == 3

    def test_invalid_server_skipped(self):
        data = {"servers": [{"no_address": True}, {"address": "ok.com"}]}
        config = _parse_config(data)
        assert len(config.servers) == 1
        assert config.servers[0].address == "ok.com"

    def test_full_config(self):
        data = {
            "general": {"poll_interval": 15, "theme": "auto"},
            "servers": [
                {"address": "192.168.1.1", "alias": "GPS"},
                {"address": "pool.ntp.org"},
            ],
            "thresholds": {
                "offset_warning_ms": 5.0,
                "unreachable_after": 2,
            },
        }
        config = _parse_config(data)
        assert config.poll_interval == 15
        assert len(config.servers) == 2
        assert config.thresholds.offset_warning_ms == 5.0
        assert config.thresholds.unreachable_after == 2
        # Defaults preserved for unset thresholds
        assert config.thresholds.offset_critical_ms == 100.0


class TestLoadConfig:
    def test_missing_file_returns_default(self, tmp_path):
        config = load_config(tmp_path / "nonexistent.toml")
        assert config.servers == []
        assert config.poll_interval == 10

    def test_load_real_toml(self, tmp_path):
        toml_file = tmp_path / "config.toml"
        toml_file.write_text(
            '[general]\n'
            'poll_interval = 30\n\n'
            '[[servers]]\n'
            'address = "time.google.com"\n'
            'alias = "Google"\n'
        )
        config = load_config(toml_file)
        assert config.poll_interval == 30
        assert len(config.servers) == 1
        assert config.servers[0].alias == "Google"


class TestMergeCLIArgs:
    def test_override_interval(self):
        config = AppConfig()

        class Args:
            interval = 5
            servers = []

        result = merge_cli_args(config, Args())
        assert result.poll_interval == 5

    def test_cli_servers_replace_config(self):
        config = AppConfig(servers=[ServerConfig(address="old.com")])

        class Args:
            interval = None
            servers = ["new1.com", "new2.com"]

        result = merge_cli_args(config, Args())
        assert len(result.servers) == 2
        assert result.servers[0].address == "new1.com"

    def test_no_override_when_none(self):
        config = AppConfig(poll_interval=20)

        class Args:
            interval = None
            servers = []

        result = merge_cli_args(config, Args())
        assert result.poll_interval == 20


class TestTypes:
    def test_types_dataclass(self):
        """Test type data structures."""
        from ntpwatch.ntp.types import ServerStatus, ServerState, NTPResult

        status = ServerStatus(address="test.com", alias="Test")
        assert status.display_name == "Test"
        assert status.state == ServerState.UNKNOWN

        status2 = ServerStatus(address="test.com")
        assert status2.display_name == "test.com"

    def test_record_result(self):
        from ntpwatch.ntp.types import ServerStatus, ServerState, NTPResult

        status = ServerStatus(address="test.com")
        result = NTPResult(
            offset_s=0.001, delay_s=0.002, stratum=1, leap=0,
            ref_id="GPS", root_delay_s=0.0, root_dispersion_s=0.0,
            ref_timestamp=0.0, poll=6, precision=-20, version=4,
        )
        status.record_result(result)
        assert status.state == ServerState.SYNCED
        assert status.consecutive_failures == 0
        assert len(status.offset_history) == 1

    def test_record_failure_transitions_to_unreachable(self):
        from ntpwatch.ntp.types import ServerStatus, ServerState

        status = ServerStatus(address="test.com")
        for _ in range(3):
            status.record_failure()
        assert status.state == ServerState.UNREACHABLE
