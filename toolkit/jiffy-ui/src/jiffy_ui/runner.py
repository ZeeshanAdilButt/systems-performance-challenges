"""Run one lab at a time, exactly as you would from a terminal, and listen to its feed.

The lab is started as its own process (``python labs/.../knee.py --quick --out ...``)
with ``JIFFY_LIVE`` pointing at a socket here. Nothing about the lab changes: it measures
the same way and prints the same tables. Three streams come back:

- its live feed (see ``jiffy_metrics.live``), folded into chart points by ``Board``;
- its printed output, line by line, for the log;
- its report, read from ``.cache/ui/<lab>.md`` when it finishes.
"""

from __future__ import annotations

import contextlib
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

from jiffy_metrics import live
from jiffy_ui.board import TICK, Board, Hub
from jiffy_ui.labs import Lab


class BusyError(RuntimeError):
    """A lab is already running."""


class Runner:
    def __init__(self, root: Path, hub: Hub) -> None:
        self.root = root
        self.hub = hub
        self._listener = socket.create_server(("127.0.0.1", 0))
        self.feed_address: tuple[str, int] = self._listener.getsockname()[:2]
        self._lock = threading.Lock()
        self._proc: subprocess.Popen[str] | None = None
        self._board: Board | None = None
        self._stopped = False
        threading.Thread(target=self._accept, daemon=True).start()

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def report_path(self, lab: Lab) -> Path:
        return self.root / ".cache" / "ui" / f"{lab.script.stem}.md"

    def start(self, lab: Lab, quick: bool) -> None:
        with self._lock:
            if self.running:
                raise BusyError("a lab is already running")
            out = self.report_path(lab)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.unlink(missing_ok=True)  # an old report must not pass for this run's
            script = lab.script.relative_to(self.root).as_posix()
            args = [script, "--out", out.relative_to(self.root).as_posix()]
            args += ["--quick"] if quick else []
            host, port = self.feed_address
            env = {
                **os.environ,
                live.ENV: f"{host}:{port}",
                "PYTHONUNBUFFERED": "1",
                "PYTHONIOENCODING": "utf-8",
            }
            board = Board()
            self.hub.publish(
                "run",
                {
                    "lab": lab.id,
                    "title": lab.title,
                    "quick": quick,
                    "command": "uv run " + " ".join(args),
                    "slow": board.slow,
                },
                fresh=True,
            )
            self._board = board
            self._stopped = False
            proc = subprocess.Popen(
                [sys.executable, *args],
                cwd=self.root,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                # On Linux and macOS, its own process group, so Stop can end the lab and
                # the server it started together.
                start_new_session=sys.platform != "win32",
            )
            self._proc = proc
        threading.Thread(target=self._watch, args=(proc, board, out), daemon=True).start()

    def stop(self) -> None:
        with self._lock:
            proc = self._proc
            if proc is None or proc.poll() is not None:
                return
            self._stopped = True
        _kill_tree(proc)

    def _watch(self, proc: subprocess.Popen[str], board: Board, out: Path) -> None:
        """One point every TICK while the lab runs; then the last point and the report."""
        printer = threading.Thread(target=self._print, args=(proc,), daemon=True)
        printer.start()
        while proc.poll() is None:
            time.sleep(TICK)
            self.hub.publish("point", board.point())
        time.sleep(0.2)  # the feed's last batch can land just after the process exits
        self.hub.publish("point", board.point())
        printer.join(timeout=5)
        report = out.read_text(encoding="utf-8") if out.exists() else ""
        self.hub.publish(
            "done",
            {
                "code": proc.returncode,
                "stopped": self._stopped,
                "seconds": round(board.elapsed(), 1),
                "report": report,
            },
        )

    def _print(self, proc: subprocess.Popen[str]) -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            self.hub.publish("log", {"line": line.rstrip("\n")})

    def _accept(self) -> None:
        while True:
            try:
                conn, _ = self._listener.accept()
            except OSError:
                return
            threading.Thread(target=self._listen, args=(conn,), daemon=True).start()

    def _listen(self, conn: socket.socket) -> None:
        """One connection: the lab's or its server's. One JSON object per line."""
        with conn, conn.makefile("rb") as stream:
            try:
                for line in stream:
                    board = self._board
                    if board is None:
                        continue
                    event = board.take(json.loads(line))
                    if event is not None:
                        self.hub.publish(*event)
            except (OSError, ValueError, KeyError):
                return

    def close(self) -> None:
        self.stop()
        self._listener.close()


def _kill_tree(proc: subprocess.Popen[str]) -> None:
    """End the lab and every process it started (its server)."""
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True, check=False
        )
    else:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGTERM)
