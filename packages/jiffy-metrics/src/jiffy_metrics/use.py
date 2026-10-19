"""Utilization, saturation and errors of one resource, from exact transitions.

Most tools sample: every second they read "how many workers are busy" and average. A
burst that fills the queue for 30 ms and drains before the next sample never shows up.
This recorder is told about every transition instead (a request queued, a worker picked
it up, a worker finished), so it knows the exact state at every instant. Ask it for
windows of any width afterwards: one second, ten milliseconds, both from the same run.

The three numbers are Brendan Gregg's USE method:

- **Utilization**: share of the time the resource was busy, as busy-worker-seconds over
  capacity-seconds.
- **Saturation**: work that had to wait because every worker was busy. A request that sits
  in the queue for a few microseconds while an idle worker wakes up does not count.
- **Errors**: requests that failed.
"""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class Window:
    """One slice of time. ``utilization`` is 0..1; queue numbers are in requests."""

    start: float
    length: float
    utilization: float
    mean_queue: float
    max_queue: int
    saturated_time: float  # seconds in the window with every worker busy and work waiting


@dataclass(frozen=True)
class UseSummary:
    """A run seen through windows of one width."""

    width: float
    windows: int
    utilization: float  # over the whole run
    peak_utilization: float  # busiest single window
    saturated_windows: float  # share of windows in which work waited for a busy worker
    max_queue: int
    errors: int

    def as_dict(self) -> dict[str, float]:
        return {
            "width": self.width,
            "windows": self.windows,
            "utilization": self.utilization,
            "peak_utilization": self.peak_utilization,
            "saturated_windows": self.saturated_windows,
            "max_queue": self.max_queue,
            "errors": self.errors,
        }


class UseRecorder:
    """Thread-safe. Call ``enqueued`` when work arrives, ``started`` when a worker takes it
    and ``finished`` when it is done."""

    def __init__(self, capacity: int, clock: Callable[[], float] = time.perf_counter) -> None:
        if capacity < 1:
            raise ValueError("capacity is the number of workers, at least 1")
        self.capacity = capacity
        self._clock = clock
        self._lock = threading.Lock()
        self._busy = 0
        self._queued = 0
        self.errors = 0
        self._start = clock()
        self._events: list[tuple[float, int, int]] = [(self._start, 0, 0)]

    def _note(self) -> None:
        self._events.append((self._clock(), self._busy, self._queued))

    def enqueued(self) -> None:
        with self._lock:
            self._queued += 1
            self._note()

    def started(self) -> None:
        with self._lock:
            self._queued -= 1
            self._busy += 1
            self._note()

    def finished(self, ok: bool = True) -> None:
        with self._lock:
            self._busy -= 1
            if not ok:
                self.errors += 1
            self._note()

    def reset(self) -> None:
        """Forget history but keep the current state: work in flight stays in flight."""
        with self._lock:
            self._start = self._clock()
            self._events = [(self._start, self._busy, self._queued)]
            self.errors = 0

    def windows(self, width: float, end: float | None = None) -> list[Window]:
        if width <= 0:
            raise ValueError("window width must be positive")
        with self._lock:
            events = list(self._events)
            start = self._start
            now = self._clock()
        end = now if end is None else end
        span = end - start
        n = max(1, math.ceil(span / width - 1e-9))
        busy_area = [0.0] * n
        queue_area = [0.0] * n
        saturated = [0.0] * n
        max_queue = [0] * n
        # The state is constant between two events: walk each of those segments and
        # spread it over the windows it crosses.
        for k, (t, busy, queued) in enumerate(events):
            seg_start = max(t, start)
            seg_end = min(events[k + 1][0] if k + 1 < len(events) else end, end)
            w = min(n - 1, int((seg_start - start) // width))
            while seg_start < seg_end and w < n:
                piece_end = min(seg_end, start + (w + 1) * width)
                dt = piece_end - seg_start
                if dt > 0:
                    busy_area[w] += busy * dt
                    queue_area[w] += queued * dt
                    if queued and busy >= self.capacity:
                        saturated[w] += dt
                    max_queue[w] = max(max_queue[w], queued)
                seg_start = piece_end
                w += 1
        out = []
        for w in range(n):
            w_start = start + w * width
            length = max(min(width, end - w_start), 1e-12)
            out.append(
                Window(
                    start=w_start - start,
                    length=length,
                    utilization=busy_area[w] / (self.capacity * length),
                    mean_queue=queue_area[w] / length,
                    max_queue=max_queue[w],
                    saturated_time=saturated[w],
                )
            )
        return out

    def summary(self, width: float, end: float | None = None) -> UseSummary:
        ws = self.windows(width, end)
        span = sum(w.length for w in ws)
        busy = sum(w.utilization * w.length for w in ws)
        return UseSummary(
            width=width,
            windows=len(ws),
            utilization=busy / span if span else 0.0,
            peak_utilization=max(w.utilization for w in ws),
            saturated_windows=sum(1 for w in ws if w.saturated_time > 0) / len(ws),
            max_queue=max(w.max_queue for w in ws),
            errors=self.errors,
        )
