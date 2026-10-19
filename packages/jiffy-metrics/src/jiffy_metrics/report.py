"""Plain-text output: aligned tables, millisecond formatting and bar charts.

Every table can be printed to a terminal or pasted into Markdown unchanged.
"""

from __future__ import annotations

from collections.abc import Sequence


def ms(seconds: float) -> str:
    """Seconds as milliseconds, with as many digits as are worth reading."""
    value = seconds * 1000
    if value >= 100:
        return f"{value:.0f} ms"
    if value >= 10:
        return f"{value:.1f} ms"
    return f"{value:.2f} ms"


def pct(fraction: float) -> str:
    value = fraction * 100
    if value and value < 1:
        return f"{value:.2f}%"
    return f"{value:.1f}%"


def table(headers: Sequence[str], rows: Sequence[Sequence[object]]) -> str:
    """A Markdown table whose columns also line up in a terminal."""
    cells = [[str(h) for h in headers], *[[str(c) for c in row] for row in rows]]
    widths = [max(len(r[i]) for r in cells) for i in range(len(headers))]

    def line(row: list[str]) -> str:
        return "| " + " | ".join(c.ljust(w) for c, w in zip(row, widths, strict=True)) + " |"

    rule = "|" + "|".join("-" * (w + 2) for w in widths) + "|"
    return "\n".join([line(cells[0]), rule, *(line(r) for r in cells[1:])])


def bars(
    labels: Sequence[str],
    values: Sequence[float],
    *,
    width: int = 50,
    fmt: str = "{:.1f}",
) -> str:
    """Horizontal bars, scaled to the largest value."""
    top = max(values, default=0.0) or 1.0
    pad = max((len(label) for label in labels), default=0)
    lines = []
    for label, value in zip(labels, values, strict=True):
        n = round(value / top * width)
        lines.append(f"{label.rjust(pad)} | {'#' * n} {fmt.format(value)}")
    return "\n".join(lines)
