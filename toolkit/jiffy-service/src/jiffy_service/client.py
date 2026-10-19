"""A client that multiplexes every request over one connection.

``work`` returns a ``Future`` at once; a reader thread resolves it when the reply with
the matching id arrives. Hundreds of requests can be in flight on the one socket, which
is what an open-loop load test needs, and the connection is set up once, not per call.
"""

from __future__ import annotations

import contextlib
import itertools
import socket
import threading
from collections.abc import Callable, Iterator, Sequence
from concurrent.futures import Future
from dataclasses import dataclass
from typing import Any

from jiffy_service.protocol import Message, decode, encode


@dataclass(frozen=True)
class Reply:
    """What the server says about one request: how long it queued and how long it took."""

    wait: float
    service: float

    @property
    def server_time(self) -> float:
        return self.wait + self.service


class Client:
    def __init__(self, address: tuple[str, int], timeout: float = 10.0) -> None:
        self._sock = socket.create_connection(address, timeout=timeout)
        self._sock.settimeout(None)
        self._sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self._lock = threading.Lock()
        self._ids = itertools.count(1)
        self._pending: dict[int, tuple[Future[Any], Callable[[Message], Any]]] = {}
        self._closed = False
        self._reader = threading.Thread(target=self._read, daemon=True)
        self._reader.start()

    def _send(self, message: Message, convert: Callable[[Message], Any]) -> Future[Any]:
        future: Future[Any] = Future()
        with self._lock:
            if self._closed:
                raise ConnectionError("client is closed")
            message["id"] = next(self._ids)
            self._pending[message["id"]] = (future, convert)
            self._sock.sendall(encode(message))
        return future

    def work(self, seconds: float) -> Future[Reply]:
        """Ask the server for ``seconds`` of work."""
        return self._send(
            {"op": "work", "work": seconds},
            lambda m: Reply(float(m["wait"]), float(m["service"])),
        )

    def use(
        self, widths: Sequence[float] = (1.0,), timeout: float = 10.0
    ) -> list[dict[str, float]]:
        """The server's own USE summary of the run so far, one entry per window width."""
        future = self._send({"op": "use", "widths": list(widths)}, lambda m: m["use"])
        result: list[dict[str, float]] = future.result(timeout=timeout)
        return result

    def reset(self, timeout: float = 10.0) -> None:
        """Start a fresh run on the server: its USE history is cleared."""
        self._send({"op": "reset"}, lambda m: None).result(timeout=timeout)

    def _lines(self) -> Iterator[bytes]:
        """The replies, one line at a time. Plain ``recv``, not ``makefile``: the file
        object holds a reference that turns ``close()`` into a no-op until it is closed
        too, and on Windows only a real close (not ``shutdown``) wakes a blocked
        ``recv``, so ``close()`` would hang until the server hung up."""
        buffer = b""
        while chunk := self._sock.recv(65536):
            buffer += chunk
            *lines, buffer = buffer.split(b"\n")
            yield from lines

    def _read(self) -> None:
        try:
            for line in self._lines():
                message = decode(line)
                with self._lock:
                    entry = self._pending.pop(message["id"], None)
                if entry is None:
                    continue
                future, convert = entry
                if "error" in message:
                    future.set_exception(RuntimeError(message["error"]))
                else:
                    future.set_result(convert(message))
        except (OSError, ValueError):
            pass
        with self._lock:
            self._closed = True
            pending = list(self._pending.values())
            self._pending.clear()
        for future, _ in pending:
            future.set_exception(ConnectionError("connection closed"))

    def close(self) -> None:
        with contextlib.suppress(OSError):
            self._sock.shutdown(socket.SHUT_RDWR)
        self._sock.close()
        self._reader.join(timeout=5)

    def __enter__(self) -> Client:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
