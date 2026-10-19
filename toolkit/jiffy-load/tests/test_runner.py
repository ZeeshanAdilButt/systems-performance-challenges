"""The runners against a fake target: a single worker that takes a fixed time per request,
with a freeze in the middle. Open-loop and closed-loop must disagree about it."""

import threading
import time
from concurrent.futures import Future

import pytest

from jiffy_load import Sample, closed_loop, open_loop, throughput, uniform


class OneWorker:
    """Serves requests one at a time, ``service`` seconds each, frozen between
    ``freeze_from`` and ``freeze_to`` seconds after it was created."""

    def __init__(self, service: float, freeze_from: float = -1, freeze_to: float = -1) -> None:
        self.service = service
        self.start = time.perf_counter()
        self.freeze = (freeze_from, freeze_to)
        self.lock = threading.Lock()

    def call(self, i: int) -> Future[int]:
        future: Future[int] = Future()

        def serve() -> None:
            with self.lock:
                elapsed = time.perf_counter() - self.start
                if self.freeze[0] <= elapsed < self.freeze[1]:
                    time.sleep(self.freeze[1] - elapsed)
                time.sleep(self.service)
            future.set_result(i)

        threading.Thread(target=serve, daemon=True).start()
        return future


def test_open_loop_sends_on_schedule_and_measures_from_it() -> None:
    target = OneWorker(service=0.002)
    samples = open_loop(uniform(100, 0.5), target.call)
    assert len(samples) == 50
    assert all(s.ok and s.value == s.index for s in samples)
    late = max(s.sent - s.intended for s in samples)
    assert late < 0.010
    assert all(s.latency >= s.response_time - 1e-9 for s in samples)
    assert throughput(samples) == pytest.approx(100, rel=0.2)


def test_a_synchronous_failure_is_still_a_sample() -> None:
    def broken(i: int) -> Future[int]:
        raise ConnectionError("refused")

    samples = open_loop([0.0, 0.01], broken)
    assert [s.ok for s in samples] == [False, False]
    assert isinstance(samples[0].error, ConnectionError)


@pytest.mark.slow
def test_closed_loop_hides_a_freeze_that_open_loop_counts() -> None:
    # Frozen for 0.4 s out of 1.2 s. Requests due during the freeze all wait for it.
    open_target = OneWorker(service=0.002, freeze_from=0.4, freeze_to=0.8)
    opened = open_loop(uniform(100, 1.2), open_target.call, lead=0.0)
    closed_target = OneWorker(service=0.002, freeze_from=0.4, freeze_to=0.8)
    closed = closed_loop(1, 1.2, closed_target.call, think=0.008)

    def slow_share(samples: list[Sample[int]]) -> float:
        return sum(1 for s in samples if s.latency > 0.05) / len(samples)

    # About a third of the open-loop requests were due during the freeze. The one
    # closed-loop user records the freeze about once. A busy machine adds a few slow
    # samples to both, so compare the two rather than pinning the closed-loop number.
    assert slow_share(opened) > 0.2
    assert slow_share(closed) < slow_share(opened) / 3
