import random

import pytest

from jiffy_load import bursty, poisson, uniform


def test_poisson_hits_the_rate_and_stays_in_range() -> None:
    times = poisson(1000, 10, random.Random(1))
    assert len(times) == pytest.approx(10_000, rel=0.03)
    assert times == sorted(times)
    assert times[0] >= 0
    assert times[-1] < 10


def test_uniform_is_evenly_spaced() -> None:
    assert uniform(4, 1) == [0.0, 0.25, 0.5, 0.75]


def test_bursty_keeps_the_average_but_only_sends_during_bursts() -> None:
    times = bursty(1000, 10, random.Random(1), period=0.2, on_fraction=0.25)
    assert len(times) == pytest.approx(10_000, rel=0.03)
    assert times == sorted(times)
    assert all((t % 0.2) < 0.05 + 1e-9 for t in times)


def test_nothing_to_send() -> None:
    assert poisson(0, 10, random.Random(1)) == []
    assert uniform(10, 0) == []
    with pytest.raises(ValueError, match="on_fraction"):
        bursty(10, 1, random.Random(1), on_fraction=0)
