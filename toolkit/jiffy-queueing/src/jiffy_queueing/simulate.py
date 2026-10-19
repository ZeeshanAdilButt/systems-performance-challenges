"""Replay a workload through ``c`` first-come first-served workers, instantly and exactly.

Give it arrival times and service times (made up, or measured on a real system) and it
tells you when each request would have started and finished, with no scheduler noise,
no network and no sleep overshoot. Comparing that with what a real run measured, on the
very same arrivals and service times, isolates the system's own overhead.
"""

from __future__ import annotations

import heapq
import random
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Job:
    arrival: float
    start: float
    end: float

    @property
    def wait(self) -> float:
        return self.start - self.arrival

    @property
    def service(self) -> float:
        return self.end - self.start

    @property
    def latency(self) -> float:
        return self.end - self.arrival


def fcfs(arrivals: Sequence[float], services: Sequence[float], servers: int) -> list[Job]:
    """Jobs in arrival order. Each takes the worker that frees up first; with one shared
    queue and first-come first-served that is exactly what happens."""
    if len(arrivals) != len(services):
        raise ValueError("one service time per arrival")
    if servers < 1:
        raise ValueError("at least one server")
    order = sorted(range(len(arrivals)), key=lambda i: arrivals[i])
    free_at = [0.0] * servers  # a min-heap of when each worker is next free
    jobs: list[Job | None] = [None] * len(arrivals)
    for i in order:
        start = max(arrivals[i], heapq.heappop(free_at))
        end = start + services[i]
        heapq.heappush(free_at, end)
        jobs[i] = Job(arrivals[i], start, end)
    return [j for j in jobs if j is not None]


def exponential(mean: float, n: int, rng: random.Random) -> list[float]:
    return [rng.expovariate(1 / mean) for _ in range(n)]
