import math
import threading

import pytest
from hypothesis import given
from hypothesis import strategies as st

from jiffy_metrics import RollingPercentile

durations = st.lists(
    st.floats(min_value=0, max_value=100, allow_nan=False), min_size=1, max_size=300
)


def exact(values: list[float], p: float) -> float:
    ordered = sorted(values)
    return ordered[max(1, math.ceil(p / 100 * len(ordered))) - 1]


@given(durations, st.integers(min_value=1, max_value=50), st.floats(min_value=0, max_value=100))
def test_percentile_is_exact_over_the_last_size_values(
    values: list[float], size: int, p: float
) -> None:
    window = RollingPercentile(size)
    for v in values:
        window.record(v)
    assert len(window) == min(size, len(values))
    assert window.percentile(p) == exact(values[-size:], p)


def test_old_values_stop_counting_when_latency_drifts() -> None:
    window = RollingPercentile(100)
    for _ in range(1000):
        window.record(0.002)
    assert window.percentile(95) == 0.002
    for _ in range(100):
        window.record(0.014)
    assert window.percentile(5) == 0.014  # the quiet values are all gone


def test_empty_window_is_zero() -> None:
    assert RollingPercentile(10).percentile(95) == 0.0


def test_rejects_bad_input() -> None:
    with pytest.raises(ValueError, match="size"):
        RollingPercentile(0)
    window = RollingPercentile(10)
    with pytest.raises(ValueError, match="non-negative"):
        window.record(-1.0)
    with pytest.raises(ValueError, match="percentile"):
        window.percentile(101)


def test_many_threads_can_record_at_once() -> None:
    window = RollingPercentile(10_000)

    def writer() -> None:
        for i in range(1000):
            window.record(i / 1000)

    threads = [threading.Thread(target=writer) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(window) == 8000
    assert window.percentile(100) == 0.999
