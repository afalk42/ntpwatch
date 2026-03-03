"""NTPWatch Textual Application."""

from __future__ import annotations

import asyncio
import time

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.containers import Vertical
from textual.widgets import Static
from rich.text import Text

from ntpwatch.config import AppConfig, ThresholdConfig
from ntpwatch.ntp.types import ServerStatus, ServerState, ServerData
from ntpwatch.views.dashboard import DashboardScreen
from ntpwatch.views.peers import PeerScreen
from ntpwatch.views.variables import VariablesScreen


class HelpScreen(ModalScreen):
    """Modal help overlay showing key bindings."""

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("question_mark", "dismiss", "Close"),
    ]

    def compose(self) -> ComposeResult:
        help_text = (
            "[bold]ntpwatch — Key Bindings[/bold]\n\n"
            "  [cyan]d[/]  Dashboard (all servers)\n"
            "  [cyan]p[/]  Peer associations\n"
            "  [cyan]v[/]  System variables\n"
            "  [cyan]r[/]  Force refresh now\n"
            "  [cyan]Tab[/]  Next server\n"
            "  [cyan]Shift+Tab[/]  Previous server\n"
            "  [cyan]1-9[/]  Jump to server #\n"
            "  [cyan]?[/]  This help screen\n"
            "  [cyan]q[/]  Quit\n"
        )
        yield Vertical(
            Static(help_text, id="help-text"),
            id="help-content",
        )


class NTPWatchApp(App):
    """NTP server monitoring TUI application."""

    TITLE = "ntpwatch"
    CSS_PATH = "app.tcss"

    BINDINGS = [
        Binding("d", "switch_view('dashboard')", "Dashboard", priority=True),
        Binding("p", "switch_view('peers')", "Peers", priority=True),
        Binding("v", "switch_view('variables')", "Variables", priority=True),
        Binding("r", "force_refresh", "Refresh", priority=True),
        Binding("q", "quit", "Quit", priority=True),
        Binding("question_mark", "show_help", "Help", priority=True),
        Binding("tab", "next_server", "Next Server", priority=True, show=False),
        Binding("shift+tab", "prev_server", "Prev Server", priority=True, show=False),
        Binding("1", "jump_server(1)", priority=True, show=False),
        Binding("2", "jump_server(2)", priority=True, show=False),
        Binding("3", "jump_server(3)", priority=True, show=False),
        Binding("4", "jump_server(4)", priority=True, show=False),
        Binding("5", "jump_server(5)", priority=True, show=False),
        Binding("6", "jump_server(6)", priority=True, show=False),
        Binding("7", "jump_server(7)", priority=True, show=False),
        Binding("8", "jump_server(8)", priority=True, show=False),
        Binding("9", "jump_server(9)", priority=True, show=False),
    ]

    def __init__(self, config: AppConfig | None = None) -> None:
        super().__init__()
        self._config = config or AppConfig()
        self._servers: list[ServerStatus] = []
        self._selected_index: int = 0
        self._current_view: str = "dashboard"
        self._next_poll: float = 0
        self._peers_cache: dict[str, list] = {}
        self._sysvars_cache: dict[str, dict] = {}
        self._poll_timer = None

        # Initialize server status objects
        for srv in self._config.servers:
            self._servers.append(
                ServerStatus(address=srv.address, alias=srv.alias)
            )

    def on_mount(self) -> None:
        self._dashboard = DashboardScreen(thresholds=self._config.thresholds)
        self._peer_screen = PeerScreen()
        self._var_screen = VariablesScreen()

        self.install_screen(self._dashboard, name="dashboard")
        self.install_screen(self._peer_screen, name="peers")
        self.install_screen(self._var_screen, name="variables")

        self.push_screen("dashboard")

        # Start polling
        self._schedule_poll()

    def _schedule_poll(self) -> None:
        self._next_poll = time.time() + self._config.poll_interval
        self._poll_timer = self.set_timer(0.1, self._poll_all)
        # Update status bar every second
        self.set_interval(1.0, self._tick_status_bar)

    def _tick_status_bar(self) -> None:
        if self._current_view == "dashboard":
            self._dashboard.update_status_bar(
                self._servers, self._config.poll_interval, self._next_poll
            )

    async def _poll_all(self) -> None:
        """Poll all servers."""
        from ntpwatch.ntp.client import query_ntp
        from ntpwatch.ntp.control import (
            get_peers,
            get_system_vars,
            Mode6NotSupportedError,
        )
        from ntpwatch.ntp.packet import NTPError

        async def poll_one(server: ServerStatus) -> None:
            # Mode 3 query
            try:
                result = await query_ntp(server.address, timeout=5.0)
                server.record_result(result)
            except NTPError:
                server.record_failure()
                return

            # Mode 6 queries (skip if previously failed)
            if server.mode6_supported is not False:
                try:
                    peers = await get_peers(server.address, timeout=3.0)
                    self._peers_cache[server.address] = peers
                    server.mode6_supported = True
                except (Mode6NotSupportedError, NTPError, asyncio.TimeoutError):
                    if server.mode6_supported is None:
                        server.mode6_supported = False

                try:
                    sys_vars = await get_system_vars(server.address, timeout=3.0)
                    self._sysvars_cache[server.address] = sys_vars
                except (Mode6NotSupportedError, NTPError, asyncio.TimeoutError):
                    pass

        # Query all servers concurrently
        tasks = [poll_one(s) for s in self._servers]
        await asyncio.gather(*tasks, return_exceptions=True)

        # Update UI
        self._update_views()

        # Schedule next poll
        self._next_poll = time.time() + self._config.poll_interval
        self.set_timer(self._config.poll_interval, self._poll_all)

    def _update_views(self) -> None:
        """Update all view screens with latest data."""
        self._dashboard.update_servers(self._servers)
        self._dashboard.update_status_bar(
            self._servers, self._config.poll_interval, self._next_poll
        )

        # Update peer/variables views if a server is selected
        if self._servers:
            selected = self._servers[self._selected_index]
            peers = self._peers_cache.get(selected.address)
            sys_vars = self._sysvars_cache.get(selected.address)
            mode6 = selected.mode6_supported is not False

            self._peer_screen.update_peers(
                selected.display_name, peers, mode6
            )
            self._var_screen.update_variables(
                selected.display_name, sys_vars, mode6
            )

    def action_switch_view(self, view: str) -> None:
        if view == self._current_view:
            return
        self._current_view = view
        self.switch_screen(view)

    def action_force_refresh(self) -> None:
        self.run_worker(self._poll_all(), exclusive=True)

    def action_show_help(self) -> None:
        self.push_screen(HelpScreen())

    def action_next_server(self) -> None:
        if self._servers:
            self._selected_index = (self._selected_index + 1) % len(self._servers)
            self._update_views()

    def action_prev_server(self) -> None:
        if self._servers:
            self._selected_index = (self._selected_index - 1) % len(self._servers)
            self._update_views()

    def action_jump_server(self, number: int) -> None:
        idx = number - 1
        if 0 <= idx < len(self._servers):
            self._selected_index = idx
            self._update_views()
