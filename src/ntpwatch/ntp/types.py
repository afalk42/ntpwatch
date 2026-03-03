"""Data types for NTP responses and server state."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum


class ServerState(Enum):
    SYNCED = "synced"
    DEGRADED = "degraded"
    UNREACHABLE = "unreachable"
    UNKNOWN = "unknown"


@dataclass
class NTPResult:
    """Result of a single Mode 3 NTP query."""

    offset_s: float
    delay_s: float
    stratum: int
    leap: int
    ref_id: str
    root_delay_s: float
    root_dispersion_s: float
    ref_timestamp: float
    poll: int
    precision: int
    version: int


@dataclass
class ServerStatus:
    """Aggregated state for a monitored server."""

    address: str
    alias: str = ""
    state: ServerState = ServerState.UNKNOWN
    latest: NTPResult | None = None
    offset_history: list[float] = field(default_factory=list)
    jitter_s: float = 0.0
    consecutive_failures: int = 0
    last_query_time: float = 0.0
    mode6_supported: bool | None = None  # None = untested

    @property
    def display_name(self) -> str:
        return self.alias or self.address

    def record_result(self, result: NTPResult) -> None:
        """Record a successful query result."""
        self.latest = result
        self.offset_history.append(result.offset_s)
        if len(self.offset_history) > 60:
            self.offset_history = self.offset_history[-60:]
        self.consecutive_failures = 0
        self.last_query_time = time.time()
        self._update_jitter()
        self._update_state()

    def record_failure(self) -> None:
        """Record a query failure."""
        self.consecutive_failures += 1
        self.last_query_time = time.time()
        self._update_state()

    def _update_jitter(self) -> None:
        if len(self.offset_history) < 2:
            self.jitter_s = 0.0
            return
        recent = self.offset_history[-8:]
        mean = sum(recent) / len(recent)
        self.jitter_s = (sum((x - mean) ** 2 for x in recent) / len(recent)) ** 0.5

    def _update_state(self) -> None:
        if self.consecutive_failures >= 3:
            self.state = ServerState.UNREACHABLE
        elif self.latest is None:
            self.state = ServerState.UNKNOWN
        elif self.latest.stratum >= 16 or self.latest.leap == 3:
            self.state = ServerState.DEGRADED
        elif abs(self.latest.offset_s) > 0.1:
            self.state = ServerState.DEGRADED
        else:
            self.state = ServerState.SYNCED


@dataclass
class PeerInfo:
    """A single peer from Mode 6 readvar."""

    tally_code: str  # ' ', 'x', '.', '-', '+', '#', '*', 'o'
    remote: str
    ref_id: str
    stratum: int
    peer_type: str  # u, b, m, l
    when: int  # seconds since last response
    poll: int
    reach: int  # 8-bit reachability register
    delay_ms: float
    offset_ms: float
    jitter_ms: float
    assoc_id: int = 0


@dataclass
class SystemVariables:
    """System variables from Mode 6 readvar (assoc_id=0)."""

    raw: dict[str, str] = field(default_factory=dict)

    def get(self, key: str, default: str = "") -> str:
        return self.raw.get(key, default)

    def get_float(self, key: str, default: float = 0.0) -> float:
        try:
            return float(self.raw.get(key, ""))
        except (ValueError, TypeError):
            return default

    def get_int(self, key: str, default: int = 0) -> int:
        try:
            return int(self.raw.get(key, ""))
        except (ValueError, TypeError):
            return default


@dataclass
class ServerData:
    """Combined result of all queries for one server."""

    address: str
    result: NTPResult | None = None
    peers: list[PeerInfo] | None = None
    system_vars: SystemVariables | None = None
    error: str | None = None
