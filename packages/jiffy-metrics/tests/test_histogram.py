import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from jiffy_metrics import Histogram

durations = st.lists(
    st.floats(min_value=1e-5, max_value=100, allow_nan=False), min_size=1, max_size=300
)


def exact(values: list[float], p: float) -> float:
    ordered = sorted(values)
    return ordered[max(1, math.ceil(p / 100 * len(ordered))) - 1]


@given(durations, st.floats(min_value=0, max_value=100))
def test_percentile_is_within_precision_of_the_exact_answer(values: list[float], p: float) -> None:
    h = Histogram.of(values, precision=0.01)
    truth = exact(values, p)
    # One bucket of error, plus one more for a value that lands exactly on an edge.
    assert truth / 1.0201 <= h.percentile(p) <= truth * 1.0201


@given(durations, durations)
def test_merge_is_the_same_as_recording_everything(a: list[float], b: list[float]) -> None:
    merged = Histogram.of(a)
    merged.merge(Histogram.of(b))
    both = Histogram.of(a + b)
    assert merged.count == both.count
    assert merged.max == both.max
    assert merged.mean == pytest.approx(both.mean)
    for p in (0, 50, 90, 99, 99.9, 100):
        assert merged.percentile(p) == both.percentile(p)


def test_summary_of_a_known_distribution() -> None:
    h = Histogram.of([i / 1000 for i in range(1, 1001)])  # 1 ms .. 1000 ms
    s = h.summary()
    assert s.count == 1000
    assert s.mean == pytest.approx(0.5005)
    assert s.p50 == pytest.approx(0.5, rel=0.011)
    assert s.p99 == pytest.approx(0.99, rel=0.011)
    assert s.max == 1.0


def test_fraction_above() -> None:
    h = Histogram.of([0.001] * 90 + [0.1] * 10)
    assert h.fraction_above(0.05) == pytest.approx(0.10)
    assert h.fraction_above(0.5) == 0


def test_empty_and_invalid() -> None:
    h = Histogram()
    assert h.percentile(99) == 0.0
    assert h.mean == 0.0
    with pytest.raises(ValueError, match="non-negative"):
        h.record(-1)
    with pytest.raises(ValueError, match="same precision"):
        h.merge(Histogram(precision=0.05))
