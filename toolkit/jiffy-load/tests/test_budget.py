import pytest
from hypothesis import given
from hypothesis import strategies as st

from jiffy_load import HedgeBudget

# A run is a list of steps: a positive number is that many normal calls, 0 is one request
# for an extra call.
steps = st.lists(st.integers(min_value=0, max_value=60), max_size=500)


@given(steps, st.sampled_from([0.01, 0.05, 0.1, 0.5]))
def test_extra_calls_never_exceed_the_ratio(run: list[int], ratio: float) -> None:
    budget = HedgeBudget(ratio)
    normal = 0
    for step in run:
        if step:
            budget.earn(step)
            normal += step
        else:
            budget.spend()
    assert budget.spent <= ratio * normal + 1e-6


def test_twenty_calls_earn_one_hedge_at_five_percent() -> None:
    budget = HedgeBudget(0.05)
    budget.earn(19)
    assert not budget.spend()
    budget.earn(1)
    assert budget.spend()
    assert not budget.spend()
    assert (budget.spent, budget.denied) == (1, 2)


def test_a_quiet_spell_banks_at_most_max_saved() -> None:
    budget = HedgeBudget(0.05, max_saved=3)
    budget.earn(10_000)  # would be 500 tokens without the cap
    assert [budget.spend() for _ in range(4)] == [True, True, True, False]


def test_rejects_bad_settings() -> None:
    with pytest.raises(ValueError, match="ratio"):
        HedgeBudget(1.5)
    with pytest.raises(ValueError, match="max_saved"):
        HedgeBudget(0.05, max_saved=0.5)
