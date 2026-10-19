"""Run the server in its own OS process, so it never competes with the load generator
for the Python interpreter lock, and the measurements cross a real process boundary."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager

from jiffy_service.server import Stall


@contextmanager
def spawn(workers: int = 4, stall: Stall | None = None) -> Iterator[tuple[str, int]]:
    """Start ``python -m jiffy_service`` and yield the address it listens on."""
    cmd = [sys.executable, "-m", "jiffy_service", "--workers", str(workers)]
    if stall is not None:
        cmd += ["--stall-every", str(stall.every), "--stall-for", str(stall.length)]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True)
    try:
        assert proc.stdout is not None
        line = proc.stdout.readline().split()
        if len(line) != 3 or line[0] != "listening":
            raise RuntimeError(f"server did not start: {line!r}")
        yield line[1], int(line[2])
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
