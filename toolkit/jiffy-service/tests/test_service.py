import time
from collections.abc import Iterator

import pytest

from jiffy_service import Client, Server, Stall, spawn


@pytest.fixture
def server() -> Iterator[Server]:
    with Server(workers=2) as s:
        yield s


def test_replies_report_wait_and_service(server: Server) -> None:
    with Client(server.address) as client:
        reply = client.work(0.005).result(timeout=5)
    assert 0.005 <= reply.service < 0.05
    assert 0 <= reply.wait < 0.05


def test_many_requests_share_one_connection_and_queue_for_two_workers(server: Server) -> None:
    with Client(server.address) as client:
        started = time.perf_counter()
        futures = [client.work(0.02) for _ in range(6)]
        replies = [f.result(timeout=5) for f in futures]
        elapsed = time.perf_counter() - started
    # Six 20 ms jobs on two workers: three rounds, so at least 60 ms, and the later ones
    # say they waited.
    assert elapsed >= 0.06
    assert sorted(r.wait for r in replies)[-1] >= 0.035


def test_use_and_reset(server: Server) -> None:
    with Client(server.address) as client:
        client.reset()
        for f in [client.work(0.02) for _ in range(4)]:
            f.result(timeout=5)
        second, tick = client.use([1.0, 0.01])
        assert 0 < second["utilization"] <= 1
        assert tick["peak_utilization"] == pytest.approx(1.0, abs=0.05)
        assert tick["max_queue"] >= 1
        assert tick["saturated_windows"] > 0


def test_a_stall_freezes_everything() -> None:
    with (
        Server(workers=2, stall=Stall(every=0.1, length=0.2)) as server,
        Client(server.address) as client,
    ):
        time.sleep(0.12)  # inside the first stall
        started = time.perf_counter()
        reply = client.work(0.001).result(timeout=5)
        waited = time.perf_counter() - started
    assert waited > 0.1
    # The reader was frozen too, so the server never saw most of that wait.
    assert reply.server_time < waited / 2


def test_unknown_op_is_an_error(server: Server) -> None:
    with Client(server.address) as client:
        future = client._send({"op": "nope"}, lambda m: m)
        with pytest.raises(RuntimeError, match="unknown op"):
            future.result(timeout=5)


def test_close_is_quick(server: Server) -> None:
    client = Client(server.address)
    client.work(0.001).result(timeout=5)
    started = time.perf_counter()
    client.close()
    # The reader thread is blocked in recv; close() must wake it, not wait out the
    # five-second join timeout (which it used to on Windows).
    assert time.perf_counter() - started < 0.1
    with pytest.raises(ConnectionError):
        client.work(0.001)


@pytest.mark.slow
def test_spawned_process() -> None:
    with spawn(workers=1) as address, Client(address) as client:
        assert client.work(0.001).result(timeout=5).service >= 0.001
