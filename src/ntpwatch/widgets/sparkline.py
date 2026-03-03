"""Offset sparkline rendering using Unicode block characters."""

from __future__ import annotations

from rich.text import Text

_SPARK_CHARS = "\u2581\u2582\u2583\u2584\u2585\u2586\u2587\u2588"


def render_sparkline(values: list[float], width: int = 20) -> Text:
    """Render a sparkline from a list of float values.

    Uses Unicode block characters (▁▂▃▄▅▆▇█).
    """
    if not values:
        return Text("" * width, style="dim")

    # Take last `width` values
    data = values[-width:]

    min_val = min(data)
    max_val = max(data)
    val_range = max_val - min_val

    text = Text()
    for v in data:
        if val_range == 0:
            idx = 3  # middle
        else:
            idx = int((v - min_val) / val_range * 7)
            idx = max(0, min(7, idx))
        text.append(_SPARK_CHARS[idx], style="cyan")

    # Pad if fewer values than width
    if len(data) < width:
        text = Text("" * (width - len(data)), style="dim") + text

    return text
