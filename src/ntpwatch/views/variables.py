"""System variables screen."""

from __future__ import annotations

from textual.screen import Screen
from textual.containers import Vertical, Horizontal
from textual.widgets import Header, Static
from rich.text import Text
from rich.table import Table

from ntpwatch.ntp.types import SystemVariables


# Variable groupings
_GROUPS = {
    "System": ["version", "processor", "system"],
    "Clock": ["offset", "frequency", "sys_jitter", "clk_jitter", "clk_wander", "stability", "tc"],
    "Timing": ["stratum", "precision", "rootdelay", "rootdisp", "refid", "reftime"],
    "Leap": ["leap", "tai", "leapsec"],
}


class VariablesScreen(Screen):
    """Screen showing system variables for the selected server."""

    BINDINGS = []

    def __init__(self) -> None:
        super().__init__()
        self._server_name = ""
        self._vars: SystemVariables | None = None

    def compose(self):
        yield Header()
        yield Static("", id="vars-header")
        yield Vertical(id="vars-content")

    def update_variables(
        self,
        server_name: str,
        sys_vars: SystemVariables | None,
        mode6_supported: bool,
    ) -> None:
        self._server_name = server_name
        self._vars = sys_vars

        try:
            header = self.query_one("#vars-header", Static)
            header.update(Text(f" System Variables: {server_name}", style="bold"))
        except Exception:
            pass

        try:
            content = self.query_one("#vars-content", Vertical)
            content.remove_children()

            if not mode6_supported or sys_vars is None or not sys_vars.raw:
                content.mount(
                    Static(
                        Text(
                            " System variables unavailable — server does not "
                            "support NTP control queries (Mode 6).",
                            style="dim italic",
                        )
                    )
                )
                return

            # Build grouped key-value display
            shown_keys: set[str] = set()
            for group_name, keys in _GROUPS.items():
                group_vars = {}
                for key in keys:
                    if key in sys_vars.raw:
                        group_vars[key] = sys_vars.raw[key]
                        shown_keys.add(key)

                if group_vars:
                    table = Table(title=group_name, show_header=False, expand=True)
                    table.add_column("Variable", style="cyan", width=16)
                    table.add_column("Value")
                    for k, v in group_vars.items():
                        value_text = self._style_value(k, v)
                        table.add_row(k, value_text)
                    content.mount(Static(table))

            # Show remaining variables not in any group
            remaining = {
                k: v for k, v in sys_vars.raw.items() if k not in shown_keys
            }
            if remaining:
                table = Table(title="Other", show_header=False, expand=True)
                table.add_column("Variable", style="cyan", width=16)
                table.add_column("Value")
                for k, v in sorted(remaining.items()):
                    table.add_row(k, v)
                content.mount(Static(table))

        except Exception:
            pass

    def _style_value(self, key: str, value: str) -> Text:
        """Apply color coding to certain values."""
        if key in ("offset", "sys_jitter", "clk_jitter"):
            try:
                val = abs(float(value))
                if val < 1.0:
                    return Text(value, style="green")
                elif val < 10.0:
                    return Text(value, style="cyan")
                elif val < 50.0:
                    return Text(value, style="yellow")
                else:
                    return Text(value, style="red")
            except ValueError:
                pass
        return Text(value)
