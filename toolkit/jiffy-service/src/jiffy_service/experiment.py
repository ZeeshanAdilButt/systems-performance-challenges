"""One measured run against a jiffy-service: the client's view and the server's, together.

Every part needs the same three steps: reset the server's counters, drive it with
some load, then ask the server what it saw. ``Run`` keeps both perspectives side by side,
because the interesting lessons live in the gap between them:

- the **workload** view: latency per request, measured by the client;
- the **resource** view: utilization and saturation, measured by the server.

When a dashboard is watching (see ``jiffy_metrics.live``), every request is also sent to
it the moment it finishes.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from jiffy_load import Sample, closed_loop, open_loop, poisson, throughput
from jiffy_metrics import Histogram, live
from jiffy_service.client import Client, Reply


@dataclass(frozen=True)
class Run:
    samples: list[Sample[Reply]]
    use: list[dict[str, float]]  # the server's USE summary, one per window width asked for

    @property
    def replies(self) -> list[Reply]:
        return [s.value for s in self.samples if s.value is not None]

    @property
    def errors(self) -> int:
        return sum(1 for s in self.samples if not s.ok)

    @property
    def throughput(self) -> float:
        return throughput(self.samples)

    @property
    def mean_service(self) -> float:
        replies = self.replies
        return sum(r.service for r in replies) / len(replies) if replies else 0.0

    def latency(self) -> Histogram:
        """Client view, from when each request was due."""
        return Histogram.of([s.latency for s in self.samples if s.ok])

    def server_time(self) -> Histogram:
        """Server view: wait plus service, as the server measured them."""
        return Histogram.of([r.server_time for r in self.replies])


def drive_open(
    client: Client,
    schedule: Sequence[float],
    work: Sequence[float],
    widths: Sequence[float] = (1.0,),
) -> Run:
    """Request ``i`` asks for ``work[i]`` seconds and is due at ``schedule[i]``."""
    client.reset()
    samples = open_loop(schedule, lambda i: client.work(work[i]), on_sample=live.record)
    return Run(samples, client.use(widths))


def drive_closed(
    client: Client,
    users: int,
    duration: float,
    work: Callable[[int], float],
    *,
    think: float = 0.0,
    widths: Sequence[float] = (1.0,),
) -> Run:
    client.reset()
    samples = closed_loop(
        users, duration, lambda i: client.work(work(i)), think=think, on_sample=live.record
    )
    return Run(samples, client.use(widths))


def calibrate(client: Client, mean_work: float, workers: int, seconds: float = 1.5) -> float:
    """Measure, don't guess: what mean service time does asking for ``mean_work`` really
    give on this machine? ``time.sleep`` overshoots, and by how much depends on the OS.

    Averaging the service times themselves would be noisy (exponential work varies a
    lot), so this measures the overshoot of each request over what it asked for, which
    barely varies, and adds it to ``mean_work``. Runs at 20% load so nothing queues."""
    rng = random.Random(0)
    rate = 0.2 * workers / mean_work
    schedule = poisson(rate, seconds, rng)
    work = [rng.expovariate(1 / mean_work) for _ in schedule]
    run = drive_open(client, schedule, work)
    over = [s.value.service - work[s.index] for s in run.samples if s.value is not None]
    return mean_work + sum(over) / len(over)
