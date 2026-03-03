"""Reachability visualization widget — 8-bit reach register as visual bar."""

from __future__ import annotations

from rich.text import Text


def render_reach(reach: int) -> Text:
    """Render an 8-bit reach register as a visual bar.

    Each bit represents one poll: filled block = success, dim block = failure.
    Bit 0 is most recent, bit 7 is oldest.
    Returns a Rich Text with per-character styling.
    """
    text = Text()
    octal = oct(reach)[2:].rjust(3, "0")
    text.append(f"{octal} ")

    # Show 8 bits, MSB (oldest) first
    for i in range(7, -1, -1):
        if reach & (1 << i):
            text.append("\u2588", style="green")  # Full block
        else:
            text.append("\u2591", style="dim")  # Light shade
    return text
