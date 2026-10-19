"""A percentile of the most recent values only, for timers that should follow the system.

``Histogram`` keeps every value it has ever seen, which is what a report wants. A timer
that reacts to the system, such as "hedge a call once it is later than usual", wants the
opposite: only the last few hundred values, so that when latency drifts up, the answer
drifts up with it and the old quiet values stop counting.
"""

from __future__ import annotations

import math
import threading
from collections import deque


class RollingPercentile:
    """The percentile of the last ``size`` values recorded. Safe to share between threads."""

    def __init__(self, size: int) -> None:
        if size < 1:
            raise ValueError(f"size must be at least 1, got {size}")
        self.size = size
        self._values: deque[float] = deque(maxlen=size)  # the oldest value falls off the end
        self._lock = threading.Lock()

    def record(self, value: float) -> None:
        if value < 0 or math.isnan(value):
            raise ValueError(f"durations are non-negative, got {value}")
        with self._lock:
            self._values.append(value)

    def __len__(self) -> int:
        with self._lock:
            return len(self._values)

    def percentile(self, p: float) -> float:
        """Nearest-rank percentile of the values in the window, ``p`` in [0, 100].

        Exact, not bucketed: the window is small, so sorting a copy is cheap. 0.0 when
        nothing has been recorded yet.
        """
        if not 0 <= p <= 100:
            raise ValueError(f"percentile must be in [0, 100], got {p}")
        with self._lock:
            ordered = sorted(self._values)
        if not ordered:
            return 0.0
        rank = max(1, math.ceil(p / 100 * len(ordered)))
        return ordered[rank - 1]
