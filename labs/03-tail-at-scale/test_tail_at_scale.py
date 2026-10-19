import random
import time
from concurrent.futures import Future

import pytest

from jiffy_service import Client, Reply, Server
from tail_at_scale import SLOW, SLOW_SHARE, backend_work, fan_out, wait_until


def test_backend_is_slow_one_percent_of_the_time() -> None:
    rng = random.Random(0)
    draws = [backend_work(rng) for _ in range(100_000)]
    assert draws.count(SLOW) / len(draws) == pytest.approx(SLOW_SHARE, rel=0.1)


def test_wait_until_honours_a_short_deadline() -> None:
    never: Future[Reply] = Future()
    started = time.perf_counter()
    wait_until([never], started + 0.010)
    assert time.perf_counter() - started < 0.015


def test_fan_out_waits_for_every_call() -> None:
    with Server(workers=16) as server, Client(server.address) as client:
        front = fan_out(client, 8, seed=1, hedge_after=None)
    assert front.calls == 8


def test_hedging_sends_a_second_copy_of_a_slow_call() -> None:
    # Find a seed whose first draw is slow, then fan out to just that call.
    seed = next(s for s in range(10_000) if backend_work(random.Random(s)) == SLOW)
    with Server(workers=4) as server, Client(server.address) as client:
        started = time.perf_counter()
        front = fan_out(client, 1, seed=seed, hedge_after=0.005)
        elapsed = time.perf_counter() - started
    assert front.calls == 2
    assert elapsed < SLOW
