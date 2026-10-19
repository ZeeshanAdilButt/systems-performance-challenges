"""A service with a fixed number of workers and one shared queue in front of them.

It is deliberately the simplest thing that behaves like a real backend under load: a
reader thread per connection puts requests on a queue, ``workers`` threads take them off
and "work" (sleep for as long as the request asks, which stands in for a database call
or any other I/O), then reply on the same connection.

It measures itself the way a typical service does, and reports those numbers back:

- ``wait``: from when the reader thread took the request off the socket to when a
  worker picked it up.
- ``service``: from pickup to done.

Anything that happens *before* the reader thread sees the request (a full socket
buffer, a paused process) is invisible to those two numbers. Lab 02 is about that
blind spot.

``Stall`` simulates a stop-the-world pause, such as a garbage collector or a VM being
descheduled: every ``every`` seconds, all threads (readers included) freeze for
``length`` seconds.

With a dashboard watching (see ``jiffy_metrics.live``), the server also reports how busy
its workers were and how long the queue was, ten times a second.
"""

from __future__ import annotations

import contextlib
import queue
import socket
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from jiffy_metrics import UseRecorder, live
from jiffy_service.protocol import Message, decode, encode

clock = time.perf_counter


@dataclass(frozen=True)
class Stall:
    every: float
    length: float


@dataclass
class _Job:
    id: int
    work: float
    received: float
    conn: _Connection


class _Connection:
    def __init__(self, sock: socket.socket) -> None:
        self.sock = sock
        self._lock = threading.Lock()

    def send(self, message: Message) -> None:
        data = encode(message)
        # If the client went away there is nobody to tell.
        with self._lock, contextlib.suppress(OSError):
            self.sock.sendall(data)


class Server:
    def __init__(
        self,
        workers: int = 4,
        host: str = "127.0.0.1",
        port: int = 0,
        stall: Stall | None = None,
    ) -> None:
        self.workers = workers
        self.stall = stall
        self.use = UseRecorder(capacity=workers)
        self._queue: queue.Queue[_Job | None] = queue.Queue()
        self._running = threading.Event()  # cleared while the world is stopped
        self._running.set()
        self._stop = threading.Event()
        self._sock = socket.create_server((host, port))
        self.address: tuple[str, int] = self._sock.getsockname()[:2]
        self._threads: list[threading.Thread] = []
        self._conns: list[socket.socket] = []

    def _spawn(self, target: Callable[..., None], *args: object) -> None:
        t = threading.Thread(target=target, args=args, daemon=True)
        t.start()
        self._threads.append(t)

    def start(self) -> Server:
        self._spawn(self._accept)
        for _ in range(self.workers):
            self._spawn(self._work)
        if self.stall is not None:
            self._spawn(self._stall, self.stall)
        if live.enabled():
            self._spawn(self._report_live)
        return self

    def stop(self) -> None:
        self._stop.set()
        self._running.set()
        self._sock.close()
        for conn in self._conns:
            with contextlib.suppress(OSError):
                conn.shutdown(socket.SHUT_RDWR)
            conn.close()
        for _ in range(self.workers):
            self._queue.put(None)

    def __enter__(self) -> Server:
        return self.start()

    def __exit__(self, *exc: object) -> None:
        self.stop()

    def _accept(self) -> None:
        while not self._stop.is_set():
            try:
                sock, _ = self._sock.accept()
            except OSError:
                return
            # Without TCP_NODELAY, small replies wait for the previous one to be
            # acknowledged (Nagle's algorithm meeting delayed ACKs): +40 ms or worse.
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self._conns.append(sock)
            self._spawn(self._read, _Connection(sock))

    def _read(self, conn: _Connection) -> None:
        stream = conn.sock.makefile("rb")
        try:
            for line in stream:
                self._running.wait()  # a stalled process reads nothing
                received = clock()
                message = decode(line)
                op = message.get("op", "work")
                if op == "work":
                    self.use.enqueued()
                    self._queue.put(_Job(message["id"], float(message["work"]), received, conn))
                elif op == "use":
                    widths = message.get("widths", [1.0])
                    summaries = [self.use.summary(float(w)).as_dict() for w in widths]
                    conn.send({"id": message["id"], "use": summaries})
                elif op == "reset":
                    self.use.reset()
                    conn.send({"id": message["id"]})
                else:
                    conn.send({"id": message.get("id"), "error": f"unknown op {op!r}"})
        except (OSError, ValueError):
            return

    def _work(self) -> None:
        while True:
            job = self._queue.get()
            if job is None:
                return
            started = clock()
            self.use.started()
            self._running.wait()
            time.sleep(job.work)
            self._running.wait()  # a pause that lands mid-request holds the reply too
            done = clock()
            self.use.finished()
            job.conn.send({"id": job.id, "wait": started - job.received, "service": done - started})

    def _sleep(self, seconds: float) -> bool:
        """Sleep, waking early if the server stops; True if it did. Not ``Event.wait``:
        on Windows its timeout is rounded up to the clock tick (15.6 ms or more), while
        ``time.sleep`` is accurate to a fraction of a millisecond."""
        deadline = clock() + seconds
        while (left := deadline - clock()) > 0:
            if self._stop.is_set():
                return True
            time.sleep(min(left, 0.05))
        return self._stop.is_set()

    def _report_live(self) -> None:
        """Busy % and queue length over the last ``live.EVERY`` seconds, on repeat. A
        stalled process can't report, so a pause shows up as a gap on the dashboard."""
        while not self._sleep(live.EVERY):
            if not self._running.is_set():
                self._running.wait()
                continue  # the window just ended inside the pause: skip it
            window = self.use.recent(live.EVERY)
            live.send(
                {
                    "kind": "use",
                    "busy": window.utilization,
                    "queue": window.mean_queue,
                    "max_queue": window.max_queue,
                }
            )

    def _stall(self, stall: Stall) -> None:
        while not self._sleep(stall.every):
            self._running.clear()
            self._sleep(stall.length)
            self._running.set()
