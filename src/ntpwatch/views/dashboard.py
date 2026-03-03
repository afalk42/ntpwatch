"""Dashboard screen — multi-server overview."""

from __future__ import annotations

from textual.screen import Screen
from textual.containers import Vertical
from textual.widgets import Header

from ntpwatch.widgets.server_table import ServerTable
from ntpwatch.widgets.status_bar import StatusBar
from ntpwatch.config import ThresholdConfig
from ntpwatch.ntp.types import ServerStatus


class DashboardScreen(Screen):
    """Main dashboard showing all monitored NTP servers."""

    BINDINGS = []

    def __init__(self, thresholds: ThresholdConfig | None = None) -> None:
        super().__init__()
        self._thresholds = thresholds or ThresholdConfig()

    def compose(self):
        yield Header()
        yield Vertical(
            ServerTable(thresholds=self._thresholds, id="server-table"),
            id="dashboard-content",
        )
        yield StatusBar()

    def update_servers(self, servers: list[ServerStatus]) -> None:
        try:
            table = self.query_one("#server-table", ServerTable)
            table.update_servers(servers)
        except Exception:
            pass

    def update_status_bar(
        self, servers: list[ServerStatus], poll_interval: int, next_poll: float
    ) -> None:
        try:
            bar = self.query_one(StatusBar)
            bar.update_status(servers, poll_interval, next_poll)
        except Exception:
            pass
