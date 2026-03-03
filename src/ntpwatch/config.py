"""Configuration loading from TOML files and CLI arguments."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ServerConfig:
    address: str
    alias: str = ""
    description: str = ""


@dataclass
class ThresholdConfig:
    offset_warning_ms: float = 10.0
    offset_critical_ms: float = 100.0
    jitter_warning_ms: float = 5.0
    jitter_critical_ms: float = 50.0
    unreachable_after: int = 3


@dataclass
class AppConfig:
    servers: list[ServerConfig] = field(default_factory=list)
    poll_interval: int = 10
    thresholds: ThresholdConfig = field(default_factory=ThresholdConfig)
    theme: str = "dark"


_DEFAULT_CONFIG_PATH = Path.home() / ".config" / "ntpwatch" / "config.toml"


def load_config(path: Path | None = None) -> AppConfig:
    """Load configuration from a TOML file.

    Falls back to default config if file doesn't exist.
    """
    config_path = path or _DEFAULT_CONFIG_PATH

    if not config_path.exists():
        return AppConfig()

    # Use tomllib (3.11+) or tomli as fallback
    if sys.version_info >= (3, 11):
        import tomllib
    else:
        try:
            import tomli as tomllib
        except ImportError:
            return AppConfig()

    with open(config_path, "rb") as f:
        data = tomllib.load(f)

    return _parse_config(data)


def _parse_config(data: dict) -> AppConfig:
    """Parse a TOML dict into AppConfig."""
    config = AppConfig()

    general = data.get("general", {})
    if "poll_interval" in general:
        config.poll_interval = int(general["poll_interval"])
    if "theme" in general:
        config.theme = general["theme"]

    servers_data = data.get("servers", [])
    for srv in servers_data:
        if isinstance(srv, dict) and "address" in srv:
            config.servers.append(
                ServerConfig(
                    address=srv["address"],
                    alias=srv.get("alias", ""),
                    description=srv.get("description", ""),
                )
            )

    thresholds = data.get("thresholds", {})
    if thresholds:
        t = config.thresholds
        if "offset_warning_ms" in thresholds:
            t.offset_warning_ms = float(thresholds["offset_warning_ms"])
        if "offset_critical_ms" in thresholds:
            t.offset_critical_ms = float(thresholds["offset_critical_ms"])
        if "jitter_warning_ms" in thresholds:
            t.jitter_warning_ms = float(thresholds["jitter_warning_ms"])
        if "jitter_critical_ms" in thresholds:
            t.jitter_critical_ms = float(thresholds["jitter_critical_ms"])
        if "unreachable_after" in thresholds:
            t.unreachable_after = int(thresholds["unreachable_after"])

    return config


def merge_cli_args(config: AppConfig, args) -> AppConfig:
    """Merge CLI arguments over config file values."""
    if hasattr(args, "interval") and args.interval is not None:
        config.poll_interval = args.interval

    if hasattr(args, "servers") and args.servers:
        cli_servers = [ServerConfig(address=s) for s in args.servers]
        config.servers = cli_servers

    return config
