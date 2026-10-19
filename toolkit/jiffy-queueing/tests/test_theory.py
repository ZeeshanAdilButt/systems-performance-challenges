import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from jiffy_queueing import MMc, erlang_c, latency_multiplier


def test_erlang_c_known_values() -> None:
    assert erlang_c(1, 0.5) == pytest.approx(0.5)  # M/M/1: P(wait) is the utilization
    assert erlang_c(2, 1.0) == pytest.approx(1 / 3)
    assert erlang_c(10, 8.0) == pytest.approx(0.4092, abs=1e-4)  # standard table value
    assert erlang_c(3, 3.0) == 1.0


def test_mm1_textbook_formulas() -> None:
    q = MMc(arrival_rate=80, service_time=0.01, servers=1)  # 80% busy
    assert q.utilization == pytest.approx(0.8)
    assert q.mean_latency == pytest.approx(0.01 / (1 - 0.8))
    assert q.mean_queue_length == pytest.approx(0.8**2 / (1 - 0.8))


def test_the_knee() -> None:
    assert latency_multiplier(0.5) == pytest.approx(2)
    assert latency_multiplier(0.9) == pytest.approx(10)
    assert latency_multiplier(0.99) == pytest.approx(100)
    # More workers sharing one queue push the knee to the right.
    assert latency_multiplier(0.9, servers=4) < latency_multiplier(0.9, servers=1)


def test_unstable() -> None:
    q = MMc(arrival_rate=200, service_time=0.01, servers=2)
    assert not q.stable
    assert math.isinf(q.mean_wait)
    assert math.isinf(q.wait_percentile(99))


@given(
    st.integers(min_value=1, max_value=50),
    st.floats(min_value=0.01, max_value=0.99),
)
def test_wait_percentile_inverts_the_tail(servers: int, utilization: float) -> None:
    q = MMc(arrival_rate=utilization * servers / 0.01, service_time=0.01, servers=servers)
    t = q.wait_percentile(99)
    assert 0 <= erlang_c(servers, q.offered) <= 1
    if t > 0:
        drain = (servers - q.offered) / 0.01
        assert q.prob_wait * math.exp(-drain * t) == pytest.approx(0.01)
