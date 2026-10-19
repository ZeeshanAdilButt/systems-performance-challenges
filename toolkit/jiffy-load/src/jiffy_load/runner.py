"""Drive a target with load and record one ``Sample`` per request.

Two ways to generate load, and they disagree about what the system's latency is:

- ``open_loop`` sends each request at its scheduled time whether or not earlier ones have
  come back, the way real independent users behave. Latency is measured from the
  *scheduled* time, so if the sender itself falls behind, that delay counts too.
- ``closed_loop`` runs a fixed number of users that each send, wait for the answer, then
  send again. When the system stalls, the users stall with it and stop sending, so the
  stall is recorded once per user instead of once per request that would have arrived.
  This is *coordinated omission*: the load tool and the system coordinate to hide the
  slow period.

The target is any ``call(i) -> Future``: the i-th request of the run. Pass ``on_sample``
to see each request the moment it finishes, for example to draw it live.
"""

from __future__ import annotations

import itertools
import threading
import time
from collections.abc import Callable, Sequence
from concurrent.futures import Future
from concurrent.futures import wait as wait_all
from dataclasses import dataclass

clock = time.perf_counter


@dataclass(frozen=True)
class Sample[T]:
    """One request. Times are ``perf_counter`` seconds."""

    index: int
    intended: float  # when the request should have been sent
    sent: float  # when it was actually sent
    done: float  # when the answer (or the failure) came back
    value: T | None
    error: BaseException | None = None

    @property
    def ok(self) -> bool:
        return self.error is None

    @property
    def latency(self) -> float:
        """What the user experienced: from when they wanted to send to the answer."""
        return self.done - self.intended

    @property
    def response_time(self) -> float:
        """From the moment the request actually left. Misses any delay before sending."""
        return self.done - self.sent


def sleep_until(deadline: float) -> None:
    """Sleep coarsely, then yield in a tight loop for the last stretch. ``time.sleep`` can
    overshoot by a millisecond or more, which would bunch up arrivals."""
    while True:
        remaining = deadline - clock()
        if remaining <= 0:
            return
        if remaining > 0.002:
            time.sleep(remaining - 0.0015)
        else:
            time.sleep(0)


def open_loop[T](
    schedule: Sequence[float],
    call: Callable[[int], Future[T]],
    *,
    timeout: float = 30.0,
    lead: float = 0.05,
    on_sample: Callable[[Sample[T]], object] | None = None,
) -> list[Sample[T]]:
    """Send request ``i`` at ``start + schedule[i]`` and wait for every answer."""
    samples: list[Sample[T] | None] = [None] * len(schedule)
    futures: list[Future[T]] = []
    start = clock() + lead

    def keep(sample: Sample[T]) -> None:
        samples[sample.index] = sample
        if on_sample is not None:
            on_sample(sample)

    def recorder(i: int, intended: float, sent: float) -> Callable[[Future[T]], None]:
        def done(f: Future[T]) -> None:
            finished = clock()
            error = f.exception()
            value = None if error is not None else f.result()
            keep(Sample(i, intended, sent, finished, value, error))

        return done

    for i, offset in enumerate(schedule):
        intended = start + offset
        sleep_until(intended)
        sent = clock()
        try:
            future = call(i)
        except Exception as exc:  # the target refused synchronously: still a sample
            keep(Sample(i, intended, sent, clock(), None, exc))
            continue
        future.add_done_callback(recorder(i, intended, sent))
        futures.append(future)
    wait_all(futures, timeout=timeout)
    now = clock()
    for i, s in enumerate(samples):
        if s is None:
            due = start + schedule[i]
            keep(Sample(i, due, due, now, None, TimeoutError()))
    return [s for s in samples if s is not None]


def closed_loop[T](
    users: int,
    duration: float,
    call: Callable[[int], Future[T]],
    *,
    think: float = 0.0,
    timeout: float = 30.0,
    on_sample: Callable[[Sample[T]], object] | None = None,
) -> list[Sample[T]]:
    """``users`` threads, each: send, wait for the answer, think, repeat."""
    samples: list[Sample[T]] = []
    lock = threading.Lock()
    counter = itertools.count()
    deadline = clock() + duration

    def user() -> None:
        while clock() < deadline:
            with lock:
                i = next(counter)
            sent = clock()
            value: T | None = None
            error: BaseException | None = None
            try:
                value = call(i).result(timeout=timeout)
            except Exception as exc:
                error = exc
            sample = Sample(i, sent, sent, clock(), value, error)
            with lock:
                samples.append(sample)
            if on_sample is not None:
                on_sample(sample)
            if think:
                time.sleep(think)

    threads = [threading.Thread(target=user, daemon=True) for _ in range(users)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return sorted(samples, key=lambda s: s.index)


def throughput(samples: Sequence[Sample[object]]) -> float:
    """Completed requests per second, over the span from first send to last answer."""
    done = [s for s in samples if s.ok]
    if len(done) < 2:
        return 0.0
    span = max(s.done for s in done) - min(s.sent for s in done)
    return len(done) / span if span > 0 else 0.0
