"""What queueing theory predicts for ``c`` identical workers sharing one queue (M/M/c).

The assumptions are Poisson arrivals, exponential service times and first-come
first-served. Real systems rarely match them exactly. The point is the shape: as
utilization approaches 100%, waiting time grows like ``1 / (1 - utilization)``. Going
from 50% to 90% busy does not make requests 1.8x slower; it makes them wait ~10x longer.

Notation, kept close to the textbooks:

- ``arrival_rate`` (lambda): requests per second.
- ``service_time`` (S, which is 1/mu): mean seconds of work per request.
- ``offered`` (a = lambda * S): how many workers' worth of work is arriving.
- ``utilization`` (rho = a / c): share of the time each worker is busy.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


def erlang_b(servers: int, offered: float) -> float:
    """Probability that all ``servers`` are busy in a system with no queue (Erlang B).
    The recurrence avoids the factorials that overflow in the closed form."""
    b = 1.0
    for k in range(1, servers + 1):
        b = offered * b / (k + offered * b)
    return b


def erlang_c(servers: int, offered: float) -> float:
    """Probability that an arriving request has to wait (Erlang C). 1.0 when unstable."""
    if servers < 1:
        raise ValueError("at least one server")
    rho = offered / servers
    if rho >= 1:
        return 1.0
    b = erlang_b(servers, offered)
    return b / (1 - rho * (1 - b))


@dataclass(frozen=True)
class MMc:
    arrival_rate: float
    service_time: float
    servers: int = 1

    @property
    def offered(self) -> float:
        return self.arrival_rate * self.service_time

    @property
    def utilization(self) -> float:
        return self.offered / self.servers

    @property
    def stable(self) -> bool:
        return self.utilization < 1

    @property
    def prob_wait(self) -> float:
        return erlang_c(self.servers, self.offered)

    @property
    def _drain_rate(self) -> float:
        """How fast the queue empties once every worker is busy: (c - a) / S per second."""
        return (self.servers - self.offered) / self.service_time

    @property
    def mean_wait(self) -> float:
        """Mean time in the queue before a worker picks the request up."""
        if not self.stable:
            return math.inf
        return self.prob_wait / self._drain_rate

    @property
    def mean_latency(self) -> float:
        """Mean wait plus mean service: what the caller sees on average."""
        return self.mean_wait + self.service_time

    @property
    def mean_queue_length(self) -> float:
        """Little's law: L = lambda * W, applied to the queue alone."""
        return self.arrival_rate * self.mean_wait

    def wait_percentile(self, p: float) -> float:
        """The ``p``-th percentile of waiting time. In M/M/c the wait is 0 with probability
        ``1 - prob_wait`` and exponential otherwise, so this has a closed form."""
        if not self.stable:
            return math.inf
        tail = 1 - p / 100
        if tail <= 0:
            return math.inf
        if self.prob_wait <= tail:
            return 0.0
        return math.log(self.prob_wait / tail) / self._drain_rate


def latency_multiplier(utilization: float, servers: int = 1) -> float:
    """Mean latency as a multiple of the bare service time, at a given utilization."""
    return MMc(utilization * servers, 1.0, servers).mean_latency
