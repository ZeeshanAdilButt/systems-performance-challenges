"""Part 1 · The knee: how busy can a server get before people notice it's slow?

Sweep load on a 4-worker service from 10% to 95% busy, and at every step put three
answers next to each other:

- **theory**: the M/M/c formula, from the arrival rate and the measured service time;
- **simulation**: the exact same arrivals and the exact same service times, replayed
  through a perfect queue with no network, no scheduler and no Python;
- **real**: what the client measured over TCP against a separate server process.

    uv run challenges/challenge-1-latency-under-load/part-1-the-knee/knee.py
    (about a minute; add --quick for about fifteen seconds)
"""

from __future__ import annotations

import argparse
import random
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from jiffy_load import poisson
from jiffy_metrics import Histogram, bars, live, ms, pct, table
from jiffy_queueing import MMc, fcfs, latency_multiplier
from jiffy_service import Client, Run, calibrate, drive_open, spawn

WORKERS = 4
MEAN_WORK = 0.010  # what each request asks for, on average: 10 ms of exponential work
FULL = (0.1, 0.3, 0.5, 0.7, 0.8, 0.85, 0.9, 0.95)
QUICK = (0.3, 0.7, 0.9)


def duration_for(target: float, base: float) -> float:
    """Near saturation the queue swings wildly from one second to the next, so a short run
    is mostly luck. Busier points get longer runs."""
    if target < 0.75:
        return base
    return base * (2 if target < 0.93 else 3)


@dataclass(frozen=True)
class Point:
    target: float  # the utilization we aimed for
    rate: float  # arrivals per second actually scheduled
    run: Run
    theory: MMc
    simulated: Histogram
    real: Histogram

    @property
    def utilization(self) -> float:
        """What the server says it was: the resource view."""
        return self.run.use[0]["utilization"]

    @property
    def max_queue(self) -> int:
        return int(self.run.use[0]["max_queue"])


def measure(
    client: Client, target: float, service: float, duration: float, rng: random.Random
) -> Point:
    rate = target * WORKERS / service
    schedule = poisson(rate, duration, rng)
    work = [rng.expovariate(1 / MEAN_WORK) for _ in schedule]
    run = drive_open(client, schedule, work)
    # Replay the identical workload through a perfect queue: same arrival offsets, and
    # each request's service time as the server actually measured it.
    by_index = {s.index: s.value.service for s in run.samples if s.value is not None}
    arrivals = [schedule[i] for i in sorted(by_index)]
    services = [by_index[i] for i in sorted(by_index)]
    simulated = Histogram.of([j.latency for j in fcfs(arrivals, services, WORKERS)])
    theory = MMc(len(schedule) / duration, run.mean_service, WORKERS)
    return Point(target, len(schedule) / duration, run, theory, simulated, run.latency())


def sweep_table(points: Sequence[Point]) -> str:
    rows = []
    for p in points:
        rows.append(
            [
                f"{p.target:.0%}",
                pct(p.utilization),
                f"{p.run.throughput:.0f}",
                p.max_queue,
                ms(p.theory.mean_latency) if p.theory.stable else "unstable",
                ms(p.simulated.mean),
                ms(p.real.mean),
                ms(p.simulated.percentile(99)),
                ms(p.real.percentile(99)),
            ]
        )
    return table(
        [
            "aimed",
            "busy (server)",
            "req/s",
            "max queue",
            "mean: theory",
            "sim",
            "real",
            "p99: sim",
            "real",
        ],
        rows,
    )


def theory_table() -> str:
    """The curve with no noise at all: latency as a multiple of the service time."""
    rows = []
    for u in (0.5, 0.7, 0.8, 0.9, 0.95, 0.99):
        one = MMc(u, 1.0, 1)
        four = MMc(u * 4, 1.0, 4)
        rows.append(
            [
                f"{u:.0%}",
                f"{latency_multiplier(u, 1):.1f}x",
                f"{one.wait_percentile(99) + 1:.1f}x",
                f"{latency_multiplier(u, 4):.1f}x",
                f"{four.wait_percentile(99) + 1:.1f}x",
            ]
        )
    return table(
        ["busy", "1 worker: mean", "~p99", "4 workers: mean", "~p99"],
        rows,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="knee", description=__doc__.split("\n")[0])
    parser.add_argument("--quick", action="store_true", help="three points, shorter runs")
    parser.add_argument("--duration", type=float, help="base seconds per point")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--out", type=Path, default=Path(__file__).with_name("results.md"))
    args = parser.parse_args(argv)
    targets = QUICK if args.quick else FULL
    base = args.duration or (2.5 if args.quick else 4.0)
    rng = random.Random(args.seed)

    out: list[str] = ["# Part 1 · The knee: results", ""]

    def say(text: str = "") -> None:
        print(text, flush=True)
        out.append(text)

    say("## Theory first: latency as a multiple of service time (M/M/c)")
    say()
    say(theory_table())
    say()
    say("(~p99 is the 99th-percentile wait plus one mean service time.)")
    say()

    with spawn(WORKERS) as address, Client(address) as client:
        live.step(f"  calibrating: how long does {ms(MEAN_WORK)} of work really take? ...")
        service = calibrate(client, MEAN_WORK, WORKERS)
        say("## Calibration: measure, don't guess")
        say()
        say(
            f"Asked for {ms(MEAN_WORK)} of work per request on average; the server took"
            f" {ms(service)}. Arrival rates below are planned from the measured number."
        )
        say()
        points = []
        for target in targets:
            duration = duration_for(target, base)
            live.step(f"  measuring at {target:.0%} for {duration:.0f}s ...")
            points.append(measure(client, target, service, duration, rng))

    say(f"## The sweep: {WORKERS} workers, open-loop Poisson load, {base:.0f}s or more per point")
    say()
    say(sweep_table(points))
    say()
    say("p99 latency, real, by how busy the server was:")
    say()
    say("```")
    say(
        bars(
            [f"{p.utilization:.0%} busy" for p in points],
            [p.real.percentile(99) * 1000 for p in points],
            fmt="{:.1f} ms",
        )
    )
    say("```")
    low, high = points[0], points[-1]
    say()
    say(
        f"From {low.utilization:.0%} to {high.utilization:.0%} busy, the server did"
        f" {high.run.throughput / low.run.throughput:.1f}x the work, and p99 latency went"
        f" from {ms(low.real.percentile(99))} to {ms(high.real.percentile(99))}"
        f" ({high.real.percentile(99) / low.real.percentile(99):.1f}x)."
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"\nreport written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
