"""Part 3 · Tail at scale: what happens when one page needs answers from many servers?

A front-end request calls ``k`` backends in parallel and has to wait for all of them.
Each backend call is fast (2 ms) 99% of the time and slow (50 ms) 1% of the time. One
backend is "slow at p99". The front end is slow whenever *any* of its ``k`` calls is,
which happens with probability ``1 - 0.99 ** k``: about 18% at k = 20, 39% at k = 50.

Then the fix from Dean and Barroso's "The Tail at Scale": hedged requests. If a call has
not answered after 10 ms (well past its usual 2 ms), send the same call again and take
whichever answer comes first. It costs a few percent more backend calls and removes most
of the tail.

    uv run challenges/challenge-1-latency-under-load/part-3-tail-at-scale/tail_at_scale.py
    (about a minute and a half; add --quick for about 30 seconds)
"""

from __future__ import annotations

import argparse
import random
import threading
import time
from collections.abc import Callable, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import wait as wait_for
from dataclasses import dataclass
from pathlib import Path

from jiffy_load import Sample, open_loop, poisson
from jiffy_metrics import Histogram, live, ms, pct, table
from jiffy_service import Client, Reply, spawn

WORKERS = 64  # plenty: this part is about variance, not queueing
FAST, SLOW, SLOW_SHARE = 0.002, 0.050, 0.01
THRESHOLD = 0.020  # what counts as slow, for one backend call or one front-end request
HEDGE_AFTER = 0.010
FRONT_RATE = 25.0  # front-end requests per second
FANOUTS = (1, 5, 10, 20, 50)


@dataclass(frozen=True)
class Front:
    """One front-end request's result."""

    calls: int  # backend calls actually sent, hedges included
    slow_calls: int  # primary calls whose service took longer than THRESHOLD


def wait_until(futures: Sequence[Future[Reply]], deadline: float) -> None:
    """Wait for every future or until ``deadline``, whichever is first.

    Not ``concurrent.futures.wait(timeout=...)``: on Windows a lock's timeout is rounded
    up to the system clock tick, and a 10 ms timeout measured 21 ms. ``time.sleep`` uses
    a high-resolution timer, so short sleeps in a loop are accurate to well under 1 ms.
    """
    while time.perf_counter() < deadline and not all(f.done() for f in futures):
        time.sleep(0.0005)


def backend_work(rng: random.Random) -> float:
    return SLOW if rng.random() < SLOW_SHARE else FAST


def fan_out(client: Client, k: int, seed: int, hedge_after: float | None) -> Front:
    started = time.perf_counter()
    rng = random.Random(seed)  # one per front request, so runs are repeatable
    firsts: list[Future[Reply]] = [Future() for _ in range(k)]
    lock = threading.Lock()

    def settle(slot: Future[Reply]) -> Callable[[Future[Reply]], None]:
        def done(f: Future[Reply]) -> None:
            with lock:
                if slot.done():
                    return  # the other copy already answered
                error = f.exception()
                if error is not None:
                    slot.set_exception(error)
                else:
                    slot.set_result(f.result())

        return done

    primaries = []
    for slot in firsts:
        call = client.work(backend_work(rng))
        call.add_done_callback(settle(slot))
        primaries.append(call)
    calls = k
    if hedge_after is not None:
        wait_until(firsts, started + hedge_after)
        for slot in firsts:
            if not slot.done():
                client.work(backend_work(rng)).add_done_callback(settle(slot))
                calls += 1
    wait_for(firsts)
    slow = sum(1 for p in primaries if p.done() and p.result().service > THRESHOLD)
    return Front(calls, slow)


@dataclass(frozen=True)
class Result:
    k: int
    hedged: bool
    samples: list[Sample[Front]]

    @property
    def latency(self) -> Histogram:
        return Histogram.of([s.latency for s in self.samples if s.ok])

    @property
    def calls(self) -> int:
        return sum(s.value.calls for s in self.samples if s.value is not None)

    @property
    def slow_calls(self) -> int:
        return sum(s.value.slow_calls for s in self.samples if s.value is not None)


def measure(
    client: Client, pool: ThreadPoolExecutor, k: int, n: int, seed: int, hedged: bool
) -> Result:
    schedule = poisson(FRONT_RATE, n / FRONT_RATE, random.Random(seed))
    hedge = HEDGE_AFTER if hedged else None
    samples = open_loop(
        schedule,
        lambda i: pool.submit(fan_out, client, k, seed * 100_000 + i, hedge),
        on_sample=live.record,
    )
    return Result(k, hedged, samples)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tail-at-scale", description=__doc__.split("\n")[0])
    parser.add_argument("--quick", action="store_true", help="fewer front-end requests")
    parser.add_argument("--requests", type=int, help="front-end requests per fan-out")
    parser.add_argument("--seed", type=int, default=3)
    parser.add_argument("--out", type=Path, default=Path(__file__).with_name("results.md"))
    args = parser.parse_args(argv)
    n = args.requests or (120 if args.quick else 300)

    out: list[str] = ["# Part 3 · Tail at scale: results", ""]

    def say(text: str = "") -> None:
        print(text, flush=True)
        out.append(text)

    live.slow_above(THRESHOLD)
    plain: list[Result] = []
    hedged: list[Result] = []
    with (
        spawn(WORKERS) as address,
        Client(address) as client,
        ThreadPoolExecutor(max_workers=32) as pool,
    ):
        for k in FANOUTS:
            live.step(f"  fan-out {k}: {n} front-end requests ...")
            plain.append(measure(client, pool, k, n, args.seed + k, hedged=False))
        for k in (20, 50):
            live.step(f"  fan-out {k}, hedged after {ms(HEDGE_AFTER)} ...")
            hedged.append(measure(client, pool, k, n, args.seed + k, hedged=True))

    # p: how often a single backend call was really slow, measured over every plain run.
    p = sum(r.slow_calls for r in plain) / sum(r.calls for r in plain)
    say(f"## A. Fan-out: each backend call is slow {pct(p)} of the time (measured)")
    say()
    rows = []
    for r in plain:
        lat = r.latency
        rows.append(
            [
                r.k,
                pct(1 - (1 - p) ** r.k),
                pct(lat.fraction_above(THRESHOLD)),
                ms(lat.percentile(50)),
                ms(lat.percentile(90)),
                ms(lat.percentile(99)),
            ]
        )
    say(
        table(
            ["fan-out k", "slow: theory 1-(1-p)^k", "slow: measured", "p50", "p90", "p99"],
            rows,
        )
    )
    say()
    say(f"## B. Hedging: resend any call still unanswered after {ms(HEDGE_AFTER)}")
    say()
    rows = []
    for h in hedged:
        before = next(r for r in plain if r.k == h.k)
        rows.append(
            [
                h.k,
                pct(before.latency.fraction_above(THRESHOLD)),
                pct(h.latency.fraction_above(THRESHOLD)),
                ms(before.latency.percentile(99)),
                ms(h.latency.percentile(99)),
                pct(h.calls / (h.k * len(h.samples)) - 1),
            ]
        )
    say(
        table(
            ["fan-out k", "slow before", "slow hedged", "p99 before", "p99 hedged", "extra calls"],
            rows,
        )
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"\nreport written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
