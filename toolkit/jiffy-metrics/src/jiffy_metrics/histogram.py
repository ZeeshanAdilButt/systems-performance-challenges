"""A latency histogram with bounded memory and a fixed relative error.

Values land in log-spaced buckets: bucket ``i`` holds everything in
``(floor * (1 + precision) ** (i - 1), floor * (1 + precision) ** i]``. Reporting a
bucket's upper edge is therefore never more than ``precision`` above the true value,
however many values were recorded. It is the idea behind HdrHistogram, small enough to
read in one sitting.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Summary:
    """The numbers worth printing for one latency distribution, in seconds."""

    count: int
    mean: float
    p50: float
    p90: float
    p99: float
    p999: float
    max: float


class Histogram:
    """Durations in seconds. Percentiles are within ``precision`` (relative) of the truth."""

    def __init__(self, precision: float = 0.01, floor: float = 1e-6) -> None:
        if not 0 < precision < 1:
            raise ValueError(f"precision must be in (0, 1), got {precision}")
        if floor <= 0:
            raise ValueError(f"floor must be positive, got {floor}")
        self.precision = precision
        self.floor = floor
        self._log_step = math.log1p(precision)
        self._buckets: dict[int, int] = {}
        self.count = 0
        self.total = 0.0
        self.min = math.inf
        self.max = 0.0

    @classmethod
    def of(cls, values: list[float] | tuple[float, ...], precision: float = 0.01) -> Histogram:
        h = cls(precision)
        for v in values:
            h.record(v)
        return h

    def _index(self, value: float) -> int:
        if value <= self.floor:
            return 0
        return math.ceil(math.log(value / self.floor) / self._log_step)

    def _upper(self, index: int) -> float:
        return self.floor * math.exp(index * self._log_step)

    def record(self, value: float) -> None:
        if value < 0 or math.isnan(value):
            raise ValueError(f"durations are non-negative, got {value}")
        i = self._index(value)
        self._buckets[i] = self._buckets.get(i, 0) + 1
        self.count += 1
        self.total += value
        self.min = min(self.min, value)
        self.max = max(self.max, value)

    def merge(self, other: Histogram) -> None:
        if (other.precision, other.floor) != (self.precision, self.floor):
            raise ValueError("can only merge histograms with the same precision and floor")
        for i, n in other._buckets.items():
            self._buckets[i] = self._buckets.get(i, 0) + n
        self.count += other.count
        self.total += other.total
        self.min = min(self.min, other.min)
        self.max = max(self.max, other.max)

    @property
    def mean(self) -> float:
        return self.total / self.count if self.count else 0.0

    def percentile(self, p: float) -> float:
        """Nearest-rank percentile, ``p`` in [0, 100]."""
        if not 0 <= p <= 100:
            raise ValueError(f"percentile must be in [0, 100], got {p}")
        if not self.count:
            return 0.0
        rank = max(1, math.ceil(p / 100 * self.count))
        seen = 0
        for i in sorted(self._buckets):
            seen += self._buckets[i]
            if seen >= rank:
                # The bucket edge can sit above the largest value recorded, or below the
                # smallest; the true answer cannot.
                return min(max(self._upper(i), self.min), self.max)
        return self.max

    def fraction_above(self, threshold: float) -> float:
        """Share of recorded values above ``threshold``, to bucket resolution."""
        if not self.count:
            return 0.0
        edge = self._index(threshold)
        return sum(n for i, n in self._buckets.items() if i > edge) / self.count

    def summary(self) -> Summary:
        return Summary(
            count=self.count,
            mean=self.mean,
            p50=self.percentile(50),
            p90=self.percentile(90),
            p99=self.percentile(99),
            p999=self.percentile(99.9),
            max=self.max,
        )
