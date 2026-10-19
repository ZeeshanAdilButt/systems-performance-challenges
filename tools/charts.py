"""Draw every part's charts from its results.md, as SVG files the READMEs show.

    uv run tools/charts.py

Each part writes its tables to results.md when it runs. This reads those tables back and
draws them, so a chart can never disagree with the numbers next to it. Run it again after
re-running a part.
"""

from __future__ import annotations

import re
from pathlib import Path

from jiffy_metrics.svg import BLUE, GRAY, GREEN, ORANGE, bar_chart, line_chart

ROOT = Path(__file__).resolve().parent.parent
CHALLENGE = ROOT / "challenges" / "challenge-1-latency-under-load"

Table = list[dict[str, str]]


def tables(md: str) -> list[Table]:
    """Every Markdown table in ``md``, in order, as rows keyed by column header."""
    found: list[Table] = []
    lines = md.splitlines()
    i = 0
    while i < len(lines):
        if lines[i].startswith("|") and i + 1 < len(lines) and lines[i + 1].startswith("|-"):
            headers = [c.strip() for c in lines[i].strip("|").split("|")]
            # A header like "mean: theory | sim | real" names a group: later columns
            # without a colon belong to it ("mean: real"), so no two keys collide.
            group = ""
            for k, h in enumerate(headers):
                if ":" in h:
                    group = h.split(":")[0]
                elif group and h in ("sim", "real"):
                    headers[k] = f"{group}: {h}"
            rows = []
            i += 2
            while i < len(lines) and lines[i].startswith("|"):
                cells = [c.strip() for c in lines[i].strip("|").split("|")]
                rows.append(dict(zip(headers, cells, strict=False)))
                i += 1
            found.append(rows)
        else:
            i += 1
    return found


def num(cell: str) -> float:
    """'12.3 ms' -> 12.3, '0.5%' -> 0.5, '-' -> 0."""
    match = re.search(r"-?\d+(\.\d+)?", cell)
    return float(match.group()) if match else 0.0


def write(folder: Path, name: str, svg: str) -> None:
    (folder / name).write_text(svg, encoding="utf-8", newline="\n")
    print(f"wrote {(folder / name).relative_to(ROOT).as_posix()}")


def knee() -> None:
    folder = CHALLENGE / "part-1-the-knee"
    sweep = tables((folder / "results.md").read_text(encoding="utf-8"))[1]
    busy = [num(r["busy (server)"]) for r in sweep]
    write(
        folder,
        "chart.svg",
        line_chart(
            "Waiting time as the server gets busier",
            busy,
            [
                ("p99", BLUE, [num(r["p99: real"]) for r in sweep]),
                ("average", ORANGE, [num(r["mean: real"]) for r in sweep]),
            ],
            x_label="how busy the server was",
            y_label="latency (ms)",
            x_suffix="%",
            y_suffix=" ms",
            x_max=100,
            dashed=[False, True],
        ),
    )


def averages() -> None:
    folder = CHALLENGE / "part-2-averages-lie"
    a, b = tables((folder / "results.md").read_text(encoding="utf-8"))[:2]
    write(
        folder,
        "chart-bursts.svg",
        bar_chart(
            "Same average busy %, different waits",
            ["smooth traffic", "bursty traffic"],
            [
                ("p50", GRAY, [num(r["p50"]) for r in a]),
                ("p99", BLUE, [num(r["p99"]) for r in a]),
            ],
            y_label="latency (ms)",
            y_suffix=" ms",
        ),
    )
    write(
        folder,
        "chart-tools.svg",
        bar_chart(
            "Server frozen 20% of the time: slow requests each tool saw",
            ["server's own timer", "wait-for-answer tool", "send-on-schedule tool"],
            [("slow (> 50 ms)", BLUE, [num(r["> 50 ms"]) for r in b])],
            y_label="share of requests",
            y_suffix="%",
        ),
    )


def tail() -> None:
    folder = CHALLENGE / "part-3-tail-at-scale"
    a, b = tables((folder / "results.md").read_text(encoding="utf-8"))[:2]
    write(
        folder,
        "chart-fanout.svg",
        bar_chart(
            "More servers per page, more slow pages",
            [f"{r['fan-out k']} server{'s' if r['fan-out k'] != '1' else ''}" for r in a],
            [
                ("math: 1-(1-p)^k", GRAY, [num(r["slow: theory 1-(1-p)^k"]) for r in a]),
                ("measured", BLUE, [num(r["slow: measured"]) for r in a]),
            ],
            y_label="slow pages",
            y_suffix="%",
        ),
    )
    write(
        folder,
        "chart-hedging.svg",
        bar_chart(
            "Asking again when a call is late (after 10 ms)",
            [f"{r['fan-out k']} servers per page" for r in b],
            [
                ("slow before", GRAY, [num(r["slow before"]) for r in b]),
                ("slow with hedging", GREEN, [num(r["slow hedged"]) for r in b]),
                ("extra calls", ORANGE, [num(r["extra calls"]) for r in b]),
            ],
            y_label="share",
            y_suffix="%",
        ),
    )


def adaptive() -> None:
    folder = CHALLENGE / "part-4-adaptive-hedging"
    a = tables((folder / "results.md").read_text(encoding="utf-8"))[0]
    write(
        folder,
        "chart.svg",
        bar_chart(
            "Four ways to hedge while normal calls get slower",
            [r["policy"].replace("adaptive p95 + 5% budget", "adaptive + budget") for r in a],
            [
                ("slow pages", BLUE, [num(r["slow pages"]) for r in a]),
                ("extra calls", ORANGE, [num(r["extra calls"]) for r in a]),
            ],
            y_label="share",
            y_suffix="%",
        ),
    )


def main() -> int:
    knee()
    averages()
    tail()
    adaptive()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
