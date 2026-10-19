"""Lab 04: a hedge timer that follows latency, and a cap on how much it may hedge.

Lab 03 resent every backend call still unanswered after a fixed 10 ms. On a quiet laptop
that was cheap. On a busy one, normal calls took longer than 10 ms, so the timer fired on
calls that weren't stuck at all: 40% more calls for very little gain.

This lab makes that happen on purpose. Normal backend calls start at about 2 ms and drift
up to about 14 ms during the run, the way a service slows down when its machine gets
busy. Then it sends the same pages four ways:

- no hedging;
- hedge after a fixed 10 ms (lab 03's timer);
- adaptive: hedge after the 95th percentile of the last 1000 calls;
- adaptive with a budget: hedges may add at most 5% more calls.

    uv run labs/04-adaptive-hedging/adaptive_hedging.py           about two minutes
    uv run labs/04-adaptive-hedging/adaptive_hedging.py --quick   about a minute
"""

from __future__ import annotations

import argparse
import random
import statistics
import threading
import time
from collections.abc import Callable, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import wait as wait_for
from dataclasses import dataclass
from pathlib import Path

from jiffy_load import HedgeBudget, Sample, open_loop, poisson
from jiffy_metrics import Histogram, RollingPercentile, live, ms, pct, table
from jiffy_service import Client, Reply, spawn

WORKERS = 128  # enough that no call ever waits in line, hedges included
K = 50  # backend calls per page
FRONT_RATE = 10.0  # pages per second
QUIET, BUSY = 0.002, 0.014  # a normal call's typical time at the start, and at the end
STUCK, STUCK_SHARE = 0.200, 0.01  # 1 call in 100 gets stuck for 200 ms
THRESHOLD = 0.100  # a page that takes longer than this counts as slow
FIXED_DELAY = 0.010  # lab 03's timer
PERCENTILE, WINDOW = 95, 1000  # adaptive timer: p95 of the last 1000 calls
WARMUP = 100  # calls to see before trusting the window; until then, FIXED_DELAY
BUDGET, MAX_SAVED = 0.05, 10.0  # hedges may add 5% more calls, with 10 saved up at most
PHASES = (("quiet", 0.0, 0.25), ("climbing", 0.25, 0.75), ("busy", 0.75, 1.0))


def normal_time(progress: float) -> float:
    """A normal call's typical time, ``progress`` of the way through the run (0 to 1).

    Quiet for the first quarter, climbing steadily through the middle half, busy for the
    last quarter.
    """
    climb = min(1.0, max(0.0, (progress - 0.25) / 0.5))
    return QUIET + (BUSY - QUIET) * climb


def backend_work(rng: random.Random, typical: float) -> float:
    if rng.random() < STUCK_SHARE:
        return STUCK
    return typical * (0.5 + rng.random())  # anywhere from half to one and a half times


@dataclass(frozen=True)
class Policy:
    name: str
    fixed: float | None = None  # hedge after this long, every time
    adaptive: bool = False  # hedge after the recent p95 instead
    budget: float | None = None  # extra calls allowed, as a share of normal calls


POLICIES = (
    Policy("no hedging"),
    Policy("fixed 10 ms", fixed=FIXED_DELAY),
    Policy("adaptive p95", adaptive=True),
    Policy("adaptive p95 + 5% budget", adaptive=True, budget=BUDGET),
)


class Hedger:
    """One run's hedging state: the latency of recent calls, and the budget."""

    def __init__(self, policy: Policy) -> None:
        self.policy = policy
        self.recent = RollingPercentile(WINDOW)
        self.budget = None if policy.budget is None else HedgeBudget(policy.budget, MAX_SAVED)

    def delay(self) -> float | None:
        """How long to wait before hedging a call. None: never hedge."""
        if not self.policy.adaptive:
            return self.policy.fixed
        if len(self.recent) < WARMUP:
            return FIXED_DELAY
        return self.recent.percentile(PERCENTILE)

    def sent(self, calls: int) -> None:
        if self.budget is not None:
            self.budget.earn(calls)

    def allow(self) -> bool:
        return self.budget is None or self.budget.spend()


@dataclass(frozen=True)
class Front:
    """One page's result."""

    calls: int  # backend calls sent, hedges included
    hedges: int
    won: int  # hedges that answered before the call they copied
    denied: int  # hedges the budget refused
    delay: float | None  # the hedge timer this page used


def fan_out(client: Client, seed: int, typical: float, hedger: Hedger) -> Front:
    rng = random.Random(seed)  # one per page: every policy sees the same normal calls
    firsts: list[Future[Reply]] = [Future() for _ in range(K)]
    lock = threading.Lock()
    won = 0

    def settle(slot: Future[Reply], hedge: bool) -> Callable[[Future[Reply]], None]:
        def done(f: Future[Reply]) -> None:
            nonlocal won
            with lock:
                if slot.done():
                    return  # the other copy already answered
                if hedge:
                    won += 1
                error = f.exception()
                if error is not None:
                    slot.set_exception(error)
                else:
                    slot.set_result(f.result())

        return done

    def timed(sent: float) -> Callable[[Future[Reply]], None]:
        def done(f: Future[Reply]) -> None:
            if f.exception() is None:
                hedger.recent.record(time.perf_counter() - sent)

        return done

    sent: list[float] = []
    for slot in firsts:
        sent.append(time.perf_counter())
        call = client.work(backend_work(rng, typical))
        call.add_done_callback(timed(sent[-1]))
        call.add_done_callback(settle(slot, hedge=False))
    hedger.sent(K)
    delay = hedger.delay()
    hedges = denied = 0
    # Each call has its own timer, started when it was sent. Every half millisecond, look
    # at the calls still out: hedge each one that has been out longer than ``delay``, if
    # the budget allows. Short sleeps, not a lock timeout, which Windows rounds up to
    # about 21 ms (lab 03).
    waiting = list(range(K)) if delay is not None else []
    while delay is not None and waiting:
        now = time.perf_counter()
        late = [i for i in waiting if not firsts[i].done() and now >= sent[i] + delay]
        for i in late:
            if hedger.allow():
                copy = client.work(backend_work(rng, typical))
                copy.add_done_callback(settle(firsts[i], hedge=True))
                hedges += 1
            else:
                denied += 1
        waiting = [i for i in waiting if not firsts[i].done() and i not in late]
        if waiting:
            time.sleep(0.0005)
    wait_for(firsts)
    with lock:
        return Front(K + hedges, hedges, won, denied, delay)


@dataclass(frozen=True)
class Result:
    policy: Policy
    samples: list[Sample[Front]]

    def fronts(self, start: float = 0.0, end: float = 1.0) -> list[Front]:
        """The pages sent between ``start`` and ``end`` of the way through the run."""
        n = len(self.samples)
        return [s.value for s in self.samples if s.value is not None and start <= s.index / n < end]

    @property
    def latency(self) -> Histogram:
        return Histogram.of([s.latency for s in self.samples if s.ok])

    def extra(self, start: float = 0.0, end: float = 1.0) -> float:
        """Hedges sent, as a share of normal calls."""
        fronts = self.fronts(start, end)
        return sum(f.hedges for f in fronts) / (K * len(fronts)) if fronts else 0.0


def measure(client: Client, pool: ThreadPoolExecutor, policy: Policy, n: int, seed: int) -> Result:
    # The same seed for every policy: the same pages, at the same times, with the same calls.
    schedule = poisson(FRONT_RATE, n / FRONT_RATE, random.Random(seed))
    hedger = Hedger(policy)

    def page(i: int) -> Future[Front]:
        return pool.submit(
            fan_out, client, seed * 100_000 + i, normal_time(i / len(schedule)), hedger
        )

    return Result(policy, open_loop(schedule, page, on_sample=live.record))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="adaptive-hedging", description=__doc__.split("\n")[0])
    parser.add_argument("--quick", action="store_true", help="fewer pages")
    parser.add_argument("--requests", type=int, help="pages per policy")
    parser.add_argument("--seed", type=int, default=4)
    parser.add_argument("--out", type=Path, default=Path(__file__).with_name("results.md"))
    args = parser.parse_args(argv)
    n = args.requests or (120 if args.quick else 300)

    out: list[str] = ["# Lab 04 · Adaptive hedging: results", ""]

    def say(text: str = "") -> None:
        print(text, flush=True)
        out.append(text)

    live.slow_above(THRESHOLD)
    results: list[Result] = []
    with (
        spawn(WORKERS) as address,
        Client(address) as client,
        ThreadPoolExecutor(max_workers=32) as pool,
    ):
        for policy in POLICIES:
            live.step(f"  {policy.name}: {n} pages, {K} calls each ...")
            results.append(measure(client, pool, policy, n, args.seed))

    say(
        f"## A. Four ways to hedge, same {K}-call pages, normal calls drifting from "
        f"{ms(QUIET)} to {ms(BUSY)}"
    )
    say()
    rows = []
    for r in results:
        lat = r.latency
        hedges = sum(f.hedges for f in r.fronts())
        rows.append(
            [
                r.policy.name,
                pct(lat.fraction_above(THRESHOLD)),
                ms(lat.percentile(50)),
                ms(lat.percentile(99)),
                pct(r.extra()),
                pct(sum(f.won for f in r.fronts()) / hedges) if hedges else "-",
                sum(f.denied for f in r.fronts()),
            ]
        )
    say(
        table(
            ["policy", "slow pages", "p50", "p99", "extra calls", "hedges that won", "refused"],
            rows,
        )
    )
    say()
    say("## B. Phase by phase: the timer each policy used, and the extra calls it sent")
    say()
    fixed, adaptive, budgeted = results[1], results[2], results[3]
    rows = []
    for name, start, end in PHASES:
        delays = [f.delay for f in adaptive.fronts(start, end) if f.delay is not None]
        rows.append(
            [
                name,
                " to ".join(dict.fromkeys([ms(normal_time(start)), ms(normal_time(end))])),
                ms(FIXED_DELAY),
                ms(statistics.median(delays)) if delays else "-",
                pct(fixed.extra(start, end)),
                pct(adaptive.extra(start, end)),
                pct(budgeted.extra(start, end)),
            ]
        )
    say(
        table(
            [
                "phase",
                "normal call",
                "fixed timer",
                "adaptive timer",
                "extra: fixed",
                "extra: adaptive",
                "extra: + budget",
            ],
            rows,
        )
    )
    say()
    say(f"## C. Where the budget said no ({budgeted.policy.name})")
    say()
    rows = []
    for label, low, high in (("none", 0, 0), ("1 to 9", 1, 9), (f"10 to {K}", 10, K)):
        pages = [
            s
            for s in budgeted.samples
            if s.value is not None and low <= s.value.hedges + s.value.denied <= high
        ]
        fronts = [s.value for s in pages if s.value is not None]
        rows.append(
            [
                label,
                len(pages),
                sum(f.hedges + f.denied for f in fronts),
                sum(f.denied for f in fronts),
                sum(1 for s in pages if s.latency > THRESHOLD),
            ]
        )
    say(table(["hedges a page asked for", "pages", "asked", "refused", "slow pages"], rows))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"\nreport written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
