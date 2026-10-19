"""The dashboard's parts on their own, then the whole thing against a tiny fake part."""

import json
import textwrap
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from jiffy_ui import Board, Dashboard, Hub, find_parts, find_root

REPO = Path(__file__).resolve().parents[3]

FAKE_PART = """
    import argparse
    import time
    from dataclasses import dataclass
    from pathlib import Path

    from jiffy_metrics import live


    @dataclass
    class Done:
        latency: float
        ok: bool = True


    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path)
    parser.add_argument("--quick", action="store_true")
    args = parser.parse_args()
    live.slow_above(0.02)
    live.step("  warming up ...")
    for i in range(20):
        live.record(Done(0.05 if i % 10 == 0 else 0.01))
    live.send({"kind": "use", "busy": 0.5, "queue": 1.0, "max_queue": 3})
    time.sleep(0.8)
    args.out.write_text("# Fake part: results\\n\\n| a | b |\\n|---|---|\\n| 1 | 2 |\\n")
"""


class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


CHALLENGE = "challenge-1-latency-under-load"


def test_finds_the_real_parts_with_their_titles_and_questions() -> None:
    parts = {part.id: part for part in find_parts(REPO)}
    knee = parts[f"{CHALLENGE}/part-1-the-knee"]
    assert knee.title == "Part 1 · The knee"
    assert knee.question.startswith("how busy can a server get")
    assert knee.script.name == "knee.py"
    assert {f"{CHALLENGE}/part-2-averages-lie", f"{CHALLENGE}/part-3-tail-at-scale"} <= parts.keys()


def test_finds_the_repository_from_inside_it() -> None:
    assert find_root(REPO / "toolkit" / "jiffy-ui") == REPO


def test_a_point_boils_down_half_a_second_of_latencies() -> None:
    clock = FakeClock()
    board = Board(clock)
    assert board.take({"kind": "slow", "above": 0.02}) == ("slow", {"above": 0.02})
    clock.now += 1.5
    assert board.take({"kind": "step", "text": "go"}) == ("step", {"t": 1.5, "text": "go"})
    board.take({"kind": "samples", "latency": [0.01] * 9 + [0.05], "errors": 1})
    point = board.point()
    assert point["count"] == 10
    assert point["errors"] == 1
    assert point["p50"] == pytest.approx(0.01, rel=0.02)
    assert point["p99"] == pytest.approx(0.05, rel=0.02)
    assert point["slow"] == pytest.approx(0.1)
    empty = board.point()  # nothing new: a gap, not a zero
    assert empty["count"] == 0
    assert empty["p99"] is None


def test_server_reports_go_straight_through() -> None:
    clock = FakeClock()
    board = Board(clock)
    clock.now += 0.25
    event = board.take({"kind": "use", "busy": 0.75, "queue": 2.5, "max_queue": 4})
    assert event == ("use", {"t": 0.25, "busy": 0.75, "queue": 2.5, "max_queue": 4})


def test_a_tab_that_connects_late_catches_up_on_this_run_only() -> None:
    hub = Hub()
    hub.publish("run", {"part": "old"}, fresh=True)
    hub.publish("run", {"part": "new"}, fresh=True)
    hub.publish("step", {"text": "go"})
    tab = hub.subscribe()
    caught_up = [tab.get_nowait() for _ in range(2)]
    assert caught_up == [("run", {"part": "new"}), ("step", {"text": "go"})]
    hub.publish("point", {"t": 1})
    assert tab.get_nowait() == ("point", {"t": 1})
    hub.unsubscribe(tab)


FAKE_ID = "challenge-9-fake/part-1-fake"


@pytest.fixture
def dashboard(tmp_path: Path) -> Iterator[Dashboard]:
    folder = tmp_path / "challenges" / FAKE_ID
    folder.mkdir(parents=True)
    (folder / "fake.py").write_text(textwrap.dedent(FAKE_PART), encoding="utf-8")
    readme = "# Part 1 · Fake\n\n**Question:** does it work?\n"
    (folder / "README.md").write_text(readme, encoding="utf-8")
    board = Dashboard(tmp_path, 0)
    threading.Thread(target=board.serve_forever, daemon=True).start()
    yield board
    board.shutdown()
    board.server_close()


def call(url: str, body: object = None, content_type: str = "application/json") -> Any:
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(url, data, {"Content-Type": content_type})
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)


def test_only_json_posts_start_a_part(dashboard: Dashboard) -> None:
    with pytest.raises(urllib.error.HTTPError) as refused:
        call(dashboard.url + "api/run", {"part": FAKE_ID}, "text/plain")
    assert refused.value.code == 415
    with pytest.raises(urllib.error.HTTPError) as missing:
        call(dashboard.url + "api/run", {"part": "nope"})
    assert missing.value.code == 404


@pytest.mark.slow
def test_runs_a_part_and_streams_it_to_the_page(dashboard: Dashboard) -> None:
    parts = call(dashboard.url + "api/parts")["parts"]
    assert [(part["id"], part["title"]) for part in parts] == [(FAKE_ID, "Part 1 · Fake")]
    assert call(dashboard.url + "api/run", {"part": FAKE_ID, "quick": True}) == {"ok": True}
    events: dict[str, list[dict[str, Any]]] = {}
    with urllib.request.urlopen(dashboard.url + "api/events", timeout=15) as stream:
        name = ""
        for raw in stream:
            line = raw.decode().rstrip("\n")
            if line.startswith("event: "):
                name = line[len("event: ") :]
            elif line.startswith("data: "):
                events.setdefault(name, []).append(json.loads(line[len("data: ") :]))
                if name == "done":
                    break
    command = f"uv run challenges/{FAKE_ID}/fake.py --out .cache/ui/fake.md --quick"
    assert events["run"][0]["command"] == command
    assert events["slow"] == [{"above": 0.02}]
    assert [s["text"] for s in events["step"]] == ["warming up ..."]
    assert events["use"][0]["busy"] == 0.5
    counted = [p for p in events["point"] if p["count"]]
    assert sum(p["count"] for p in counted) == 20
    assert any(p["slow"] for p in counted)
    assert {"line": "  warming up ..."} in events["log"]
    done = events["done"][0]
    assert (done["code"], done["stopped"]) == (0, False)
    assert done["report"].startswith("# Fake part: results")
