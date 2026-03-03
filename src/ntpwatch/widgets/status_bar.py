"""Footer status bar widget."""

from __future__ import annotations

import time
from textual.widgets import Static
from rich.text import Text

from ntpwatch.ntp.types import ServerStatus, ServerState


class StatusBar(Static):
    """Persistent footer showing server health summary."""

    def __init__(self) -> None:
        super().__init__(" Waiting for data...")
        self._servers: list[ServerStatus] = []
        self._next_poll: float = 0
        self._poll_interval: int = 10

    def update_status(
        self,
        servers: list[ServerStatus],
        poll_interval: int,
        next_poll: float,
    ) -> None:
        self._servers = servers
        self._poll_interval = poll_interval
        self._next_poll = next_poll
        self._refresh_content()

    def _refresh_content(self) -> None:
        total = len(self._servers)
        healthy = sum(
            1 for s in self._servers if s.state == ServerState.SYNCED
        )
        degraded = sum(
            1 for s in self._servers if s.state == ServerState.DEGRADED
        )
        unreachable = sum(
            1 for s in self._servers if s.state == ServerState.UNREACHABLE
        )

        text = Text()
        text.append(f" {total} servers", style="bold")
        text.append(" | ")
        text.append(f"{healthy} healthy", style="green")
        text.append(" | ")
        if degraded:
            text.append(f"{degraded} degraded", style="yellow")
        else:
            text.append("0 degraded", style="dim")
        text.append(" | ")
        if unreachable:
            text.append(f"{unreachable} unreachable", style="red")
        else:
            text.append("0 unreachable", style="dim")

        # Last poll time
        last_times = [
            s.last_query_time for s in self._servers if s.last_query_time > 0
        ]
        if last_times:
            last = max(last_times)
            last_str = time.strftime("%H:%M:%S", time.localtime(last))
            text.append(f" | Last: {last_str}")

        # Next poll countdown
        remaining = max(0, int(self._next_poll - time.time()))
        text.append(f" | Next: {remaining}s")

        self.update(text)
