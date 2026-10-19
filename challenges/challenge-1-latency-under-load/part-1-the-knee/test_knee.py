import random

import pytest

from jiffy_service import Client, Server
from knee import duration_for, measure, theory_table


def test_busier_points_run_longer() -> None:
    assert duration_for(0.5, 4) == 4
    assert duration_for(0.9, 4) == 8
    assert duration_for(0.95, 4) == 12


def test_theory_table_shows_the_knee() -> None:
    text = theory_table()
    assert "| 90%  | 10.0x" in text
    assert "| 99%  | 100.0x" in text


@pytest.mark.slow
def test_one_point_lines_theory_simulation_and_reality_up() -> None:
    with Server(workers=4) as server, Client(server.address) as client:
        point = measure(client, 0.5, 0.0105, 2.0, random.Random(1))
    assert point.real.count > 300
    # Same arrivals, same service times: reality is the simulation plus a little overhead.
    assert point.simulated.mean <= point.real.mean < point.simulated.mean + 0.005
    assert 0.35 < point.utilization < 0.65
