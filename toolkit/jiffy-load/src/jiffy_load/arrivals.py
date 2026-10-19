"""When requests should be sent: schedules as offsets in seconds from the start of a run.

A schedule is decided before the run starts and does not depend on how fast the system
answers. That is what makes a load test open-loop, and what lets latency be measured
from when a request *should* have gone out (see ``runner``).
"""

from __future__ import annotations

import random


def poisson(rate: float, duration: float, rng: random.Random) -> list[float]:
    """Independent arrivals at ``rate`` per second: exponential gaps, the textbook model
    for many users acting independently."""
    if rate <= 0 or duration <= 0:
        return []
    out = []
    t = rng.expovariate(rate)
    while t < duration:
        out.append(t)
        t += rng.expovariate(rate)
    return out


def uniform(rate: float, duration: float) -> list[float]:
    """Exactly one request every ``1 / rate`` seconds: no burstiness at all."""
    if rate <= 0 or duration <= 0:
        return []
    gap = 1 / rate
    return [i * gap for i in range(int(duration * rate))]


def bursty(
    rate: float,
    duration: float,
    rng: random.Random,
    *,
    period: float = 0.2,
    on_fraction: float = 0.25,
) -> list[float]:
    """The same average ``rate`` as ``poisson``, squeezed into bursts.

    Each ``period`` starts with ``on_fraction * period`` seconds of Poisson arrivals at
    ``rate / on_fraction``, then silence. Averaged over a second it is indistinguishable
    from a smooth stream; over ten milliseconds it is not.
    """
    if not 0 < on_fraction <= 1:
        raise ValueError("on_fraction must be in (0, 1]")
    on = period * on_fraction
    out = []
    for t in poisson(rate / on_fraction, duration * on_fraction, rng):
        burst = int(t // on)
        at = burst * period + (t - burst * on)
        if at < duration:
            out.append(at)
    return out
