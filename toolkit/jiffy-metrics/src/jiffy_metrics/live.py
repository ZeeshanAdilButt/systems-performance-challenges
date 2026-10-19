"""A live feed of a running part, for the dashboard in ``toolkit/jiffy-ui`` to draw.

Off by default: every function here does nothing (``step`` still prints) unless the
environment variable ``JIFFY_LIVE`` holds an address such as ``127.0.0.1:52011``. The
dashboard sets it when it starts a part. Child processes inherit it, so the part and the
server it spawns both report in, each over its own connection.

One JSON object per line, the same framing jiffy-service uses:

    {"kind": "step", "text": "measuring at 70% for 4s ..."}      the part moved on
    {"kind": "slow", "above": 0.05}                              what counts as slow
    {"kind": "samples", "latency": [0.011, ...], "errors": 0}     requests just finished
    {"kind": "use", "busy": 0.71, "queue": 1.4, "max_queue": 6}   the server, last 100 ms

Latencies go out in batches every ``EVERY`` seconds from a background thread, not one
message per request. The load generator's threads only append to a list, so watching a
run barely changes it.
"""

from __future__ import annotations

import atexit
import json
import os
import socket
import sys
import threading
import time
from typing import Any, Protocol

ENV = "JIFFY_LIVE"
EVERY = 0.1  # seconds between batches, and between the server's busy % reports


class Timed(Protocol):
    """Anything with a latency and an ok flag, such as ``jiffy_load.Sample``."""

    @property
    def latency(self) -> float: ...

    @property
    def ok(self) -> bool: ...


class Feed:
    """One connection to the dashboard. Thread-safe. If the dashboard goes away, the feed
    goes quiet and the part carries on."""

    def __init__(self, address: tuple[str, int]) -> None:
        self._sock = socket.create_connection(address, timeout=5)
        self._sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self._send_lock = threading.Lock()
        self._batch_lock = threading.Lock()
        self._latency: list[float] = []
        self._errors = 0
        self._flusher: threading.Thread | None = None
        self.closed = False

    def send(self, message: dict[str, Any]) -> None:
        data = (json.dumps(message, separators=(",", ":")) + "\n").encode()
        with self._send_lock:
            if self.closed:
                return
            try:
                self._sock.sendall(data)
            except OSError:
                self.closed = True

    def record(self, sample: Timed) -> None:
        with self._batch_lock:
            if sample.ok:
                self._latency.append(sample.latency)
            else:
                self._errors += 1
            if self._flusher is None:
                self._flusher = threading.Thread(target=self._flush_forever, daemon=True)
                self._flusher.start()

    def flush(self) -> None:
        with self._batch_lock:
            latency, errors = self._latency, self._errors
            self._latency, self._errors = [], 0
        if latency or errors:
            self.send({"kind": "samples", "latency": latency, "errors": errors})

    def _flush_forever(self) -> None:
        while not self.closed:
            time.sleep(EVERY)  # not Event.wait: on Windows its timeout rounds up to ~16 ms
            self.flush()

    def close(self) -> None:
        self.flush()
        with self._send_lock:
            self.closed = True
            self._sock.close()


_feed: Feed | None = None
_checked = False
_lock = threading.Lock()


def connect(value: str) -> Feed:
    """``"127.0.0.1:52011"`` -> a feed to that address."""
    host, _, port = value.rpartition(":")
    return Feed((host, int(port)))


def feed() -> Feed | None:
    """The process's feed, connected on first use; None when nobody is watching."""
    global _feed, _checked
    if _checked:
        return _feed
    with _lock:
        if not _checked:
            value = os.environ.get(ENV)
            if value:
                try:
                    _feed = connect(value)
                    atexit.register(_feed.close)
                except (OSError, ValueError) as exc:
                    print(f"live feed off, cannot reach {value}: {exc}", file=sys.stderr)
            _checked = True
    return _feed


def enabled() -> bool:
    return feed() is not None


def send(message: dict[str, Any]) -> None:
    if (f := feed()) is not None:
        f.send(message)


def record(sample: Timed) -> None:
    """One finished request. Pass this as ``on_sample`` to the jiffy_load runners."""
    if (f := feed()) is not None:
        f.record(sample)


def step(text: str) -> None:
    """Print a progress line, and mark it on the dashboard's charts."""
    print(text, flush=True)
    send({"kind": "step", "text": text.strip()})


def slow_above(seconds: float) -> None:
    """Tell the dashboard what this part calls a slow request."""
    send({"kind": "slow", "above": seconds})
