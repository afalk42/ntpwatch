# ntpwatch

Modern terminal UI for monitoring NTP time servers.

ntpwatch queries one or more NTP servers and displays a live dashboard with offset, jitter, stratum, reachability, and peer associations — all from the terminal. It works against any NTP server on the network using standard NTP protocol queries, with no agent or local installation required on the target.

## Installation

Requires Python 3.10+ and [uv](https://docs.astral.sh/uv/).

```bash
# Clone and install
git clone https://github.com/your-username/ntpwatch.git
cd ntpwatch
uv sync
```

## Quick Start

```bash
# Monitor servers with live TUI dashboard
uv run ntpwatch time.cloudflare.com time.google.com

# Single query, print table, exit
uv run ntpwatch --once 192.168.1.1 pool.ntp.org

# JSON output for scripting
uv run ntpwatch --json time.google.com
```

## Features

- **Multi-server dashboard** — monitor multiple NTP servers simultaneously with auto-refresh
- **Color-coded status** — green/yellow/red indicators for offset, jitter, and server health
- **Peer associations** — drill into any server's upstream peers with tally codes (`*` sys.peer, `+` candidate, `-` outlier, `x` falseticker)
- **Reachability visualization** — 8-bit reach register shown as a visual bar (`377 ████████`)
- **Offset sparklines** — inline trend charts of the last 20 offset samples
- **System variables** — full dump of NTP server variables, grouped by category
- **Pure Python NTP** — no dependency on `ntpq`, `ntplib`, or any NTP binaries
- **Dual query modes** — Mode 3 (basic time, works everywhere) + Mode 6 (control queries for ntpd peer/variable data), with automatic fallback
- **`--once` and `--json`** — single-query modes for scripting and automation
- **Config file** — optional TOML config for persistent server lists and thresholds

## Usage

```
ntpwatch [OPTIONS] [SERVERS...]

Arguments:
  SERVERS              NTP server addresses to monitor

Options:
  -i, --interval N     Poll interval in seconds (default: 10)
  -c, --config PATH    Path to config file
  --once               Single query, print table, exit
  --json               Single query, JSON output, exit
  --list               List configured servers
  --version            Show version
```

### TUI Key Bindings

| Key | Action |
|-----|--------|
| `d` | Dashboard view (all servers) |
| `p` | Peer associations view |
| `v` | System variables view |
| `r` | Force immediate refresh |
| `Tab` / `Shift+Tab` | Cycle between servers |
| `1`–`9` | Jump to server by number |
| `?` | Help overlay |
| `q` | Quit |

## Configuration

Optional config file at `~/.config/ntpwatch/config.toml`:

```toml
[general]
poll_interval = 10
theme = "dark"

[[servers]]
address = "192.168.1.1"
alias = "GPS-NTP"
description = "Stratum 1 GPS server"

[[servers]]
address = "time.cloudflare.com"
alias = "Cloudflare"

[thresholds]
offset_warning_ms = 10.0
offset_critical_ms = 100.0
jitter_warning_ms = 5.0
jitter_critical_ms = 50.0
unreachable_after = 3
```

## How It Works

ntpwatch uses two NTP query methods:

1. **Mode 3 (Client query)** — standard NTP time request. Works against any NTP server. Returns stratum, offset, delay, reference ID, and leap indicator.

2. **Mode 6 (Control query)** — `ntpq`-compatible control messages for detailed peer associations and system variables. Works against ntpd and NTPsec. Automatically falls back to Mode 3 if unsupported.

Offset is calculated using the standard NTP symmetric delay formula:
- `offset = ((T2 - T1) + (T3 - T4)) / 2`
- `delay = (T4 - T1) - (T3 - T2)`

## Development

```bash
# Run tests
uv run pytest

# Run tests with verbose output
uv run pytest -v

# Run a specific test file
uv run pytest tests/test_packet.py -v
```

## License

MIT
