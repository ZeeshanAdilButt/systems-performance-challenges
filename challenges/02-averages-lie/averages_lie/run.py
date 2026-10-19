"""Challenge 02: the numbers that look fine while users suffer.

Part A, microbursts. Two workloads with the same average rate, 50% of a 4-worker
service. One is smooth Poisson; the other packs the same requests into 50 ms bursts
every 200 ms. A one-second utilization graph cannot tell them apart. Ten-millisecond
windows, and the users, can.

Part B, coordinated omission. A service that freezes for 300 ms every 1.5 s (think of a
garbage collector). The same service is measured three ways:

- by the server itself (queue wait plus service, the usual "request duration" metric);
- by a closed-loop load tool (a few users, each waits for its answer before sending again);
- by an open-loop load tool (requests go out on schedule, latency counted from when each
  was due).

    uv run averages-lie            about 40 seconds
    uv run averages-lie --quick    about 20 seconds
"""

from __future__ import annotations

import argparse
import random
from collections.abc import Sequence
from pathlib import Path

from jiffy_load import bursty, poisson
from jiffy_metrics import Histogram, ms, pct, table
from jiffy_service import Client, Run, Stall, calibrate, drive_closed, drive_open, spawn

WORKERS = 4
MEAN_WORK = 0.010
BUSY = 0.5  # part A: average utilization, identical for both workloads
BURST_PERIOD = 0.2
BURST_ON = 0.25  # the first quarter of every period carries all the traffic
STALL = Stall(every=1.5, length=0.3)
STALL_RATE = 100.0  # part B: requests per second, about 26% busy between stalls
SLOW = 0.050  # what counts as a slow request in part B
CLOSED_USERS = 2


def microbursts(client: Client, service: float, duration: float, seed: int) -> list[list[object]]:
    rate = BUSY * WORKERS / service
    rows: list[list[object]] = []
    for name, schedule in (
        ("smooth (Poisson)", poisson(rate, duration, random.Random(seed))),
        (
            "bursty (50 ms on, 150 ms off)",
            bursty(
                rate,
                duration,
                random.Random(seed),
                period=BURST_PERIOD,
                on_fraction=BURST_ON,
            ),
        ),
    ):
        rng = random.Random(seed + 1)
        work = [rng.expovariate(1 / MEAN_WORK) for _ in schedule]
        run = drive_open(client, schedule, work, widths=(1.0, 0.01))
        second, tick = run.use
        lat = run.latency()
        rows.append(
            [
                name,
                pct(second["utilization"]),
                pct(second["peak_utilization"]),
                pct(tick["peak_utilization"]),
                pct(tick["saturated_windows"]),
                int(tick["max_queue"]),
                ms(lat.percentile(50)),
                ms(lat.percentile(99)),
            ]
        )
    return rows


def ladder(name: str, h: Histogram) -> list[object]:
    return [
        name,
        h.count,
        ms(h.mean),
        ms(h.percentile(50)),
        ms(h.percentile(90)),
        ms(h.percentile(99)),
        ms(h.percentile(99.9)),
        ms(h.max),
        pct(h.fraction_above(SLOW)),
    ]


def omission(service: float, duration: float, seed: int) -> tuple[list[list[object]], Run, Run]:
    with spawn(WORKERS, STALL) as address, Client(address) as client:
        rng = random.Random(seed)
        schedule = poisson(STALL_RATE, duration, rng)
        work = [rng.expovariate(1 / MEAN_WORK) for _ in schedule]
        opened = drive_open(client, schedule, work)
        # Each closed-loop user sends, waits, then thinks long enough that the pair of
        # users together aim for the same rate as the open-loop run.
        think = max(0.0, CLOSED_USERS / STALL_RATE - service)
        draws = random.Random(seed + 2)
        closed = drive_closed(
            client,
            CLOSED_USERS,
            duration,
            lambda _: draws.expovariate(1 / MEAN_WORK),
            think=think,
        )
    rows = [
        ladder("server's own metric (wait + service)", opened.server_time()),
        ladder(f"closed-loop tool ({CLOSED_USERS} users)", closed.latency()),
        ladder("open-loop tool (from when each was due)", opened.latency()),
    ]
    return rows, opened, closed


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="averages-lie", description=__doc__.split("\n")[0])
    parser.add_argument("--quick", action="store_true", help="shorter runs")
    parser.add_argument("--seed", type=int, default=2)
    parser.add_argument("--out", type=Path, default=Path("reports/02-averages-lie.md"))
    args = parser.parse_args(argv)
    burst_seconds = 4.0 if args.quick else 8.0
    stall_seconds = 4.5 if args.quick else 9.0

    out: list[str] = ["# Challenge 02: averages lie", ""]

    def say(text: str = "") -> None:
        print(text, flush=True)
        out.append(text)

    with spawn(WORKERS) as address, Client(address) as client:
        service = calibrate(client, MEAN_WORK, WORKERS)
        print(f"  calibrated: {ms(service)} per request; running part A ...", flush=True)
        rows = microbursts(client, service, burst_seconds, args.seed)

    say(f"## A. Same average load, {BUSY:.0%} of {WORKERS} workers, two shapes")
    say()
    say(
        table(
            [
                "workload",
                "busy (1 s avg)",
                "peak (1 s)",
                "peak (10 ms)",
                "10 ms windows queueing",
                "max queue",
                "p50",
                "p99",
            ],
            rows,
        )
    )
    say()

    print("  running part B (stalls) ...", flush=True)
    ladder_rows, opened, closed = omission(service, stall_seconds, args.seed)
    say(
        f"## B. One service, a {ms(STALL.length)} pause every {STALL.every:g} s,"
        f" ~{STALL_RATE:.0f} req/s, measured three ways"
    )
    say()
    say(
        table(
            ["measured by", "requests", "mean", "p50", "p90", "p99", "p99.9", "max", "> 50 ms"],
            ladder_rows,
        )
    )
    say()
    stalled = STALL.length / STALL.every
    say(
        f"The service is frozen {stalled:.0%} of the time. The open-loop tool saw"
        f" {pct(opened.latency().fraction_above(SLOW))} of requests take over {ms(SLOW)};"
        f" the closed-loop tool saw {pct(closed.latency().fraction_above(SLOW))}, and the"
        f" server's own metric {pct(opened.server_time().fraction_above(SLOW))}."
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"\nreport written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
