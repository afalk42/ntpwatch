"""Peer associations screen."""

from __future__ import annotations

from textual.screen import Screen
from textual.containers import Vertical
from textual.widgets import Header, Static, DataTable
from rich.text import Text

from ntpwatch.ntp.types import PeerInfo
from ntpwatch.widgets.reach_bar import render_reach

# Tally code → style mapping
_TALLY_STYLES = {
    "*": "bold green",
    "+": "cyan",
    "-": "yellow",
    "x": "red",
    ".": "dim",
    " ": "dim",
    "#": "blue",
    "o": "bold green",
}


class PeerScreen(Screen):
    """Screen showing peer associations for the selected server."""

    BINDINGS = []

    def __init__(self) -> None:
        super().__init__()
        self._server_name = ""
        self._peers: list[PeerInfo] | None = None
        self._no_mode6 = False

    def compose(self):
        yield Header()
        yield Static("", id="peer-header")
        yield Vertical(
            DataTable(cursor_type="row", id="peer-table"),
            id="peer-content",
        )

    def on_mount(self) -> None:
        table = self.query_one("#peer-table", DataTable)
        table.add_column("T", key="tally", width=3)
        table.add_column("Remote", key="remote", width=24)
        table.add_column("RefID", key="refid", width=16)
        table.add_column("St", key="stratum", width=4)
        table.add_column("Type", key="type", width=5)
        table.add_column("When", key="when", width=6)
        table.add_column("Poll", key="poll", width=6)
        table.add_column("Reach", key="reach", width=16)
        table.add_column("Delay", key="delay", width=10)
        table.add_column("Offset", key="offset", width=10)
        table.add_column("Jitter", key="jitter", width=10)

    def update_peers(
        self,
        server_name: str,
        peers: list[PeerInfo] | None,
        mode6_supported: bool,
    ) -> None:
        self._server_name = server_name
        self._peers = peers
        self._no_mode6 = not mode6_supported

        try:
            header = self.query_one("#peer-header", Static)
            header.update(Text(f" Peers: {server_name}", style="bold"))
        except Exception:
            pass

        try:
            table = self.query_one("#peer-table", DataTable)
            table.clear()

            if self._no_mode6 or peers is None:
                return

            for peer in peers:
                tally_style = _TALLY_STYLES.get(peer.tally_code, "dim")
                tally = Text(peer.tally_code, style=tally_style)
                remote = Text(peer.remote, style=tally_style)
                reach = render_reach(peer.reach)

                table.add_row(
                    tally,
                    remote,
                    peer.ref_id,
                    str(peer.stratum),
                    peer.peer_type,
                    str(peer.when),
                    str(peer.poll),
                    reach,
                    f"{peer.delay_ms:.3f}",
                    f"{peer.offset_ms:.3f}",
                    f"{peer.jitter_ms:.3f}",
                )
        except Exception:
            pass
