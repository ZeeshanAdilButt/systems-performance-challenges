"""The live feed against a real socket standing in for the dashboard."""

import json
import os
import socket
from dataclasses import dataclass

import pytest

from jiffy_metrics import live


@dataclass
class Done:
    latency: float
    ok: bool = True


def messages(conn: socket.socket, count: int) -> list[dict[str, object]]:
    conn.settimeout(5)
    with conn.makefile("rb") as stream:
        return [json.loads(stream.readline()) for _ in range(count)]


def test_off_unless_someone_is_watching(capsys: pytest.CaptureFixture[str]) -> None:
    if os.environ.get(live.ENV):
        pytest.skip(f"{live.ENV} is set in this shell")
    assert live.feed() is None
    live.record(Done(0.01))  # no feed: nothing happens
    live.step("  measuring ...")
    assert capsys.readouterr().out == "  measuring ...\n"


def test_steps_go_out_at_once_and_latencies_in_batches() -> None:
    with socket.create_server(("127.0.0.1", 0)) as server:
        feed = live.connect(f"127.0.0.1:{server.getsockname()[1]}")
        conn, _ = server.accept()
        with conn:
            feed.send({"kind": "step", "text": "go"})
            for latency in (0.010, 0.020, 0.030):
                feed.record(Done(latency))
            feed.record(Done(1.0, ok=False))
            feed.flush()
            step, batch = messages(conn, 2)
        feed.close()
    assert step == {"kind": "step", "text": "go"}
    assert batch == {"kind": "samples", "latency": [0.010, 0.020, 0.030], "errors": 1}


def test_the_lab_carries_on_when_the_dashboard_goes_away() -> None:
    with socket.create_server(("127.0.0.1", 0)) as server:
        feed = live.connect(f"127.0.0.1:{server.getsockname()[1]}")
        conn, _ = server.accept()
        conn.close()
    for _ in range(50):  # the first sends may still land in the socket buffer
        feed.send({"kind": "step", "text": "x" * 10_000})
    assert feed.closed
    feed.close()
