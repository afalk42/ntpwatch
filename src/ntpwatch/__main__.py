"""CLI entry point for ntpwatch."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from ntpwatch import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ntpwatch",
        description="Modern terminal UI for monitoring NTP time servers",
    )
    parser.add_argument(
        "servers",
        nargs="*",
        help="NTP server addresses to monitor",
    )
    parser.add_argument(
        "-i", "--interval",
        type=int,
        default=None,
        help="Poll interval in seconds (default: 10)",
    )
    parser.add_argument(
        "-c", "--config",
        type=Path,
        default=None,
        help="Path to config file",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Single query, print table, exit",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Single query, JSON output, exit",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        dest="list_servers",
        help="List configured servers",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"ntpwatch {__version__}",
    )
    return parser


async def query_all_servers(server_addresses: list[str]) -> list[dict]:
    """Query all servers and return results as dicts."""
    from ntpwatch.ntp.client import query_ntp
    from ntpwatch.ntp.control import (
        get_peers,
        get_system_vars,
        Mode6NotSupportedError,
    )
    from ntpwatch.ntp.packet import NTPError

    results = []

    async def query_one(address: str) -> dict:
        entry: dict = {"server": address}
        # Mode 3 query
        try:
            result = await query_ntp(address, timeout=5.0)
            entry["status"] = "ok"
            entry["stratum"] = result.stratum
            entry["offset_ms"] = round(result.offset_s * 1000, 3)
            entry["delay_ms"] = round(result.delay_s * 1000, 3)
            entry["ref_id"] = result.ref_id
            entry["leap"] = result.leap
            entry["root_delay_ms"] = round(result.root_delay_s * 1000, 3)
            entry["root_dispersion_ms"] = round(result.root_dispersion_s * 1000, 3)
            entry["version"] = result.version
        except NTPError as e:
            entry["status"] = "error"
            entry["error"] = str(e)
            return entry

        # Try Mode 6
        try:
            peers = await get_peers(address, timeout=3.0)
            entry["peers"] = [
                {
                    "tally": p.tally_code,
                    "remote": p.remote,
                    "ref_id": p.ref_id,
                    "stratum": p.stratum,
                    "reach": p.reach,
                    "delay_ms": p.delay_ms,
                    "offset_ms": p.offset_ms,
                    "jitter_ms": p.jitter_ms,
                }
                for p in peers
            ]
        except (NTPError, Mode6NotSupportedError, asyncio.TimeoutError):
            entry["peers"] = None

        try:
            sys_vars = await get_system_vars(address, timeout=3.0)
            entry["system_vars"] = sys_vars.raw if sys_vars.raw else None
        except (NTPError, Mode6NotSupportedError, asyncio.TimeoutError):
            entry["system_vars"] = None

        return entry

    tasks = [query_one(addr) for addr in server_addresses]
    results = await asyncio.gather(*tasks)
    return list(results)


def print_table(results: list[dict]) -> None:
    """Print results as a Rich table."""
    from rich.console import Console
    from rich.table import Table
    from rich.text import Text

    console = Console()
    table = Table(title="NTP Server Status", show_lines=False)
    table.add_column("Status", width=6)
    table.add_column("Server")
    table.add_column("St", justify="right")
    table.add_column("RefID")
    table.add_column("Offset (ms)", justify="right")
    table.add_column("Delay (ms)", justify="right")
    table.add_column("Root Delay", justify="right")
    table.add_column("Root Disp", justify="right")

    for r in results:
        if r.get("status") == "error":
            status = Text("DOWN", style="bold red")
            table.add_row(
                status, r["server"],
                "-", "-", "-", "-", "-", "-",
            )
        else:
            offset = r.get("offset_ms", 0)
            abs_offset = abs(offset)
            if abs_offset < 1:
                style = "green"
            elif abs_offset < 10:
                style = "cyan"
            elif abs_offset < 50:
                style = "yellow"
            else:
                style = "red"

            status = Text("SYNC", style="bold green")
            if r.get("stratum", 16) >= 16 or r.get("leap") == 3:
                status = Text("DEGR", style="bold yellow")

            table.add_row(
                status,
                r["server"],
                str(r.get("stratum", "-")),
                r.get("ref_id", "-"),
                Text(f"{offset:+.3f}", style=style),
                f"{r.get('delay_ms', 0):.3f}",
                f"{r.get('root_delay_ms', 0):.3f}",
                f"{r.get('root_dispersion_ms', 0):.3f}",
            )

    console.print(table)


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    # Load config
    from ntpwatch.config import load_config, merge_cli_args

    config = load_config(args.config)
    config = merge_cli_args(config, args)

    if args.list_servers:
        if not config.servers:
            print("No servers configured.")
        else:
            for i, s in enumerate(config.servers, 1):
                alias = f" ({s.alias})" if s.alias else ""
                desc = f" — {s.description}" if s.description else ""
                print(f"  {i}. {s.address}{alias}{desc}")
        return

    # Determine server list
    server_addresses = [s.address for s in config.servers]
    if not server_addresses:
        parser.error(
            "No servers specified. Provide servers as arguments or in config file."
        )

    if args.once or args.json_output:
        results = asyncio.run(query_all_servers(server_addresses))
        if args.json_output:
            print(json.dumps(results, indent=2))
        else:
            print_table(results)
        return

    # Launch TUI
    from ntpwatch.app import NTPWatchApp

    app = NTPWatchApp(config=config)
    app.run()


if __name__ == "__main__":
    main()
