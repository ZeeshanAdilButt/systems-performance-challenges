import pytest

from averages_lie import ladder, microbursts
from jiffy_metrics import Histogram
from jiffy_service import Client, Server


def test_ladder_reads_left_to_right() -> None:
    row = ladder("x", Histogram.of([0.01] * 99 + [0.3]))
    assert row[0] == "x"
    assert row[1] == 100
    assert row[-1] == "1.0%"  # one request in a hundred over 50 ms


@pytest.mark.slow
def test_bursts_hurt_the_tail_at_the_same_average() -> None:
    with Server(workers=4) as server, Client(server.address) as client:
        smooth, burst = microbursts(client, 0.0105, 3.0, seed=2)
    # Same busy-ness over a second (within noise)...
    assert abs(float(str(smooth[1])[:-1]) - float(str(burst[1])[:-1])) < 10
    # ...very different queues: bursts pile up far more requests at once.
    assert int(str(burst[5])) > 2 * int(str(smooth[5]))
