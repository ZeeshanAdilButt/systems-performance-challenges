import random
from itertools import accumulate

import pytest
from hypothesis import given
from hypothesis import strategies as st

from jiffy_queueing import MMc, exponential, fcfs


def test_simulation_agrees_with_theory_over_a_long_run() -> None:
    rng = random.Random(7)
    for servers, utilization in ((1, 0.7), (4, 0.9)):
        mean_service = 0.01
        rate = utilization * servers / mean_service
        n = 200_000
        gaps = exponential(1 / rate, n, rng)
        arrivals = list(accumulate(gaps))
        jobs = fcfs(arrivals, exponential(mean_service, n, rng), servers)
        mean_latency = sum(j.latency for j in jobs) / n
        theory = MMc(rate, mean_service, servers).mean_latency
        assert mean_latency == pytest.approx(theory, rel=0.05)


def test_one_worker_by_hand() -> None:
    jobs = fcfs([0.0, 0.1, 0.2], [0.3, 0.1, 0.1], servers=1)
    assert [(j.start, j.end) for j in jobs] == [(0.0, 0.3), (0.3, 0.4), (0.4, 0.5)]
    assert [round(j.wait, 9) for j in jobs] == [0.0, 0.2, 0.2]


jobs_strategy = st.lists(st.tuples(st.floats(0, 10), st.floats(0.001, 2)), min_size=1, max_size=60)


@given(jobs_strategy, st.integers(min_value=1, max_value=5))
def test_fcfs_invariants(pairs: list[tuple[float, float]], servers: int) -> None:
    arrivals = [a for a, _ in pairs]
    services = [s for _, s in pairs]
    jobs = fcfs(arrivals, services, servers)
    for job, arrival, service in zip(jobs, arrivals, services, strict=True):
        assert job.arrival == arrival
        assert job.start >= arrival
        assert job.service == pytest.approx(service)
    # Never more than `servers` jobs in service at once.
    edges = sorted([(j.start, 1) for j in jobs] + [(j.end, -1) for j in jobs])
    running = 0
    for _, step in edges:
        running += step
        assert running <= servers
    # First come, first served: jobs start in arrival order.
    by_arrival = sorted(jobs, key=lambda j: j.arrival)
    starts = [j.start for j in by_arrival]
    assert starts == sorted(starts)
