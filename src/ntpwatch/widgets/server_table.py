"""Dashboard server table widget."""

from __future__ import annotations

from textual.widgets import DataTable
from rich.text import Text

from ntpwatch.ntp.types import ServerStatus, ServerState
from ntpwatch.config import ThresholdConfig
from ntpwatch.widgets.reach_bar import render_reach
from ntpwatch.widgets.sparkline import render_sparkline


class ServerTable(DataTable):
    """DataTable showing all monitored servers."""

    def __init__(self, thresholds: ThresholdConfig | None = None, **kwargs) -> None:
        super().__init__(cursor_type="row", **kwargs)
        self._thresholds = thresholds or ThresholdConfig()
        self._initialized = False

    def on_mount(self) -> None:
        self.add_column("Status", key="status", width=8)
        self.add_column("Server", key="server", width=24)
        self.add_column("St", key="stratum", width=4)
        self.add_column("RefID", key="refid", width=16)
        self.add_column("Offset (ms)", key="offset", width=12)
        self.add_column("Delay (ms)", key="delay", width=12)
        self.add_column("Jitter (ms)", key="jitter", width=12)
        self.add_column("Reach", key="reach", width=16)
        self.add_column("Trend", key="sparkline", width=22)
        self._initialized = True

    def update_servers(self, servers: list[ServerStatus]) -> None:
        """Update or add rows for all servers."""
        if not self._initialized:
            return

        for server in servers:
            key = server.address
            row_data = self._build_row(server)

            if key in self._row_key_to_index:
                # Update existing row
                for col_key, value in zip(
                    ["status", "server", "stratum", "refid",
                     "offset", "delay", "jitter", "reach", "sparkline"],
                    row_data,
                ):
                    self.update_cell(key, col_key, value)
            else:
                self.add_row(*row_data, key=key)

    @property
    def _row_key_to_index(self) -> dict:
        """Map row key values to indices."""
        return {row_key.value: idx for idx, row_key in enumerate(self.rows)}

    def _build_row(self, server: ServerStatus) -> tuple:
        t = self._thresholds

        # Status column
        if server.state == ServerState.SYNCED:
            status = Text("\u25cf SYNC", style="bold green")
        elif server.state == ServerState.DEGRADED:
            status = Text("\u25c6 DEGR", style="bold yellow")
        elif server.state == ServerState.UNREACHABLE:
            status = Text("\u2715 DOWN", style="bold red")
        else:
            status = Text("? ???", style="dim")

        # Server name
        name = Text(server.display_name)

        if server.latest is None:
            return (
                status, name,
                Text("-", style="dim"), Text("-", style="dim"),
                Text("-", style="dim"), Text("-", style="dim"),
                Text("-", style="dim"), Text("-", style="dim"),
                Text("-", style="dim"),
            )

        r = server.latest

        # Stratum
        stratum = Text(str(r.stratum))

        # RefID
        ref_id = Text(r.ref_id)

        # Offset with color coding
        offset_ms = r.offset_s * 1000
        abs_offset = abs(offset_ms)
        if abs_offset < t.offset_warning_ms:
            offset_style = "green"
        elif abs_offset < t.offset_critical_ms:
            offset_style = "yellow"
        else:
            offset_style = "red"
        offset = Text(f"{offset_ms:+.3f}", style=offset_style)

        # Delay
        delay_ms = r.delay_s * 1000
        delay = Text(f"{delay_ms:.3f}")

        # Jitter with color coding
        jitter_ms = server.jitter_s * 1000
        if jitter_ms < t.jitter_warning_ms:
            jitter_style = "green"
        elif jitter_ms < t.jitter_critical_ms:
            jitter_style = "yellow"
        else:
            jitter_style = "red"
        jitter = Text(f"{jitter_ms:.3f}", style=jitter_style)

        # Reach — use last known reach from peers if available, else 0xFF
        reach_val = 0xFF  # Assume fully reachable if responding
        if server.consecutive_failures > 0:
            # Simulate a reach register based on failure count
            reach_val = (0xFF << server.consecutive_failures) & 0xFF
        reach = render_reach(reach_val)

        # Sparkline
        sparkline = render_sparkline(
            [o * 1000 for o in server.offset_history], width=20
        )

        return (status, name, stratum, ref_id, offset, delay, jitter, reach, sparkline)
