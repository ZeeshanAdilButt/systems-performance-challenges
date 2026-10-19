import pytest

from jiffy_metrics import UseRecorder


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def at(clock: FakeClock, t: float) -> None:
    clock.now = t


def test_utilization_is_busy_time_over_capacity() -> None:
    clock = FakeClock()
    use = UseRecorder(capacity=2, clock=clock)
    at(clock, 0.0)
    use.enqueued()
    use.started()
    at(clock, 0.5)
    use.finished()  # one of two workers busy for half a second
    summary = use.summary(1.0, end=1.0)
    assert summary.utilization == pytest.approx(0.25)
    assert summary.saturated_windows == 0


def test_a_burst_invisible_at_one_second_is_obvious_at_ten_milliseconds() -> None:
    clock = FakeClock()
    use = UseRecorder(capacity=1, clock=clock)
    # 20 ms of overload: the worker is busy and three more requests wait.
    at(clock, 0.400)
    for _ in range(4):
        use.enqueued()
    use.started()
    at(clock, 0.420)
    use.finished()
    for _ in range(3):
        use.started()
        use.finished()
    second = use.summary(1.0, end=1.0)
    tick = use.summary(0.01, end=1.0)
    assert second.utilization == pytest.approx(0.02)
    assert second.peak_utilization == pytest.approx(0.02)
    assert tick.peak_utilization == pytest.approx(1.0)
    assert tick.max_queue == 3
    assert tick.saturated_windows == pytest.approx(2 / 100)


def test_a_momentary_queue_with_idle_workers_is_not_saturation() -> None:
    clock = FakeClock()
    use = UseRecorder(capacity=4, clock=clock)
    at(clock, 0.1)
    use.enqueued()
    at(clock, 0.1001)  # an idle worker takes it 100 us later
    use.started()
    at(clock, 0.2)
    use.finished()
    assert use.summary(0.01, end=1.0).saturated_windows == 0


def test_windows_split_a_segment_across_boundaries() -> None:
    clock = FakeClock()
    use = UseRecorder(capacity=1, clock=clock)
    at(clock, 0.05)
    use.enqueued()
    use.started()
    at(clock, 0.25)
    use.finished()
    ws = use.windows(0.1, end=0.3)
    assert [round(w.utilization, 6) for w in ws] == [0.5, 1.0, 0.5]


def test_reset_keeps_work_in_flight() -> None:
    clock = FakeClock()
    use = UseRecorder(capacity=1, clock=clock)
    use.enqueued()
    use.started()
    at(clock, 5.0)
    use.reset()
    at(clock, 6.0)
    assert use.summary(1.0).utilization == pytest.approx(1.0)
    assert use.summary(1.0).windows == 1
