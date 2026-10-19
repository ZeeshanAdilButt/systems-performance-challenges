import random
import time

import pytest

from adaptive_hedging import (
    BUSY,
    FIXED_DELAY,
    QUIET,
    STUCK,
    STUCK_SHARE,
    WARMUP,
    Hedger,
    K,
    Policy,
    backend_work,
    fan_out,
    normal_time,
)
from jiffy_service import Client, Server


def test_normal_calls_drift_from_quiet_to_busy() -> None:
    assert normal_time(0.0) == normal_time(0.25) == QUIET
    assert normal_time(0.5) == pytest.approx((QUIET + BUSY) / 2)
    assert normal_time(0.75) == normal_time(1.0) == BUSY


def test_one_call_in_a_hundred_is_stuck_and_the_rest_spread_around_typical() -> None:
    rng = random.Random(0)
    draws = [backend_work(rng, 0.010) for _ in range(100_000)]
    assert draws.count(STUCK) / len(draws) == pytest.approx(STUCK_SHARE, rel=0.1)
    normal = [d for d in draws if d != STUCK]
    assert min(normal) >= 0.005
    assert max(normal) <= 0.015


def test_each_policy_picks_its_timer() -> None:
    assert Hedger(Policy("none")).delay() is None
    assert Hedger(Policy("fixed", fixed=0.007)).delay() == 0.007
    adaptive = Hedger(Policy("adaptive", adaptive=True))
    assert adaptive.delay() == FIXED_DELAY  # nothing seen yet
    for _ in range(WARMUP):
        adaptive.recent.record(0.030)
    assert adaptive.delay() == 0.030  # latency drifted up: so does the timer


def test_the_budget_refuses_hedges_it_has_not_earned() -> None:
    hedger = Hedger(Policy("budget", adaptive=True, budget=0.05))
    hedger.sent(19)
    assert not hedger.allow()
    hedger.sent(1)
    assert hedger.allow()


def stuck_seed() -> int:
    """A page seed whose first call is stuck."""
    return next(s for s in range(10_000) if backend_work(random.Random(s), 0.001) == STUCK)


def test_hedging_rescues_a_stuck_call() -> None:
    with Server(workers=2 * K) as server, Client(server.address) as client:
        started = time.perf_counter()
        front = fan_out(client, stuck_seed(), 0.001, Hedger(Policy("fixed", fixed=0.020)))
        elapsed = time.perf_counter() - started
    assert front.hedges >= 1
    assert front.won >= 1
    assert elapsed < STUCK


def test_an_empty_budget_sends_no_hedges() -> None:
    hedger = Hedger(Policy("no budget", fixed=0.020, budget=0.0))
    with Server(workers=2 * K) as server, Client(server.address) as client:
        front = fan_out(client, stuck_seed(), 0.001, hedger)
    assert (front.calls, front.hedges) == (K, 0)
    assert front.denied >= 1
