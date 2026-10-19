"""The web server: one page, a list of labs, Run and Stop, and a stream of events.

Standard library only. The live charts use server-sent events: the page opens
``/api/events`` once and the server keeps writing ``event: point`` lines into that one
response as the lab runs. Plain HTTP, one direction, nothing to install.

    GET  /             the page
    GET  /api/labs     the labs, as JSON
    POST /api/run      {"lab": "01-the-knee", "quick": true}
    POST /api/stop
    GET  /api/events   the event stream: run, step, slow, point, use, log, done

It only answers on 127.0.0.1, and only to requests addressed to this machine by name,
so a web page you happen to visit can't start labs on it.
"""

from __future__ import annotations

import json
import queue
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from jiffy_ui.board import Hub
from jiffy_ui.labs import Lab, find_labs
from jiffy_ui.runner import BusyError, Runner

KEEPALIVE = 10.0  # seconds between comment lines on a quiet event stream


class Dashboard(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, root: Path, port: int = 0) -> None:
        super().__init__(("127.0.0.1", port), Handler)
        self.root = root
        self.labs: dict[str, Lab] = {lab.id: lab for lab in find_labs(root)}
        self.hub = Hub()
        self.runner = Runner(root, self.hub)
        self.page = resources.files("jiffy_ui").joinpath("page.html").read_bytes()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server_address[1]}/"

    def server_close(self) -> None:
        self.runner.close()
        super().server_close()


class Handler(BaseHTTPRequestHandler):
    server: Dashboard

    def log_message(self, format: str, *args: Any) -> None:
        pass  # the terminal is for the dashboard's address, not one line per request

    def do_GET(self) -> None:
        if not self._local():
            return
        path = urlsplit(self.path).path
        if path == "/":
            self._send(200, self.server.page, "text/html; charset=utf-8")
        elif path == "/api/labs":
            labs = [
                {**asdict(lab), "script": lab.script.relative_to(self.server.root).as_posix()}
                for lab in self.server.labs.values()
            ]
            self._json(200, {"labs": labs, "running": self.server.runner.running})
        elif path == "/api/events":
            self._events()
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        if not self._local():
            return
        # Only JSON: a browser won't send that cross-site without asking first.
        if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
            self._json(415, {"error": "send JSON"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            self._json(400, {"error": "bad JSON"})
            return
        path = urlsplit(self.path).path
        if path == "/api/run":
            lab = self.server.labs.get(str(body.get("lab")))
            if lab is None:
                self._json(404, {"error": f"no lab {body.get('lab')!r}"})
                return
            try:
                self.server.runner.start(lab, bool(body.get("quick", True)))
            except BusyError as exc:
                self._json(409, {"error": str(exc)})
                return
            self._json(200, {"ok": True})
        elif path == "/api/stop":
            self.server.runner.stop()
            self._json(200, {"ok": True})
        else:
            self._json(404, {"error": "not found"})

    def _local(self) -> bool:
        host = self.headers.get("Host", "").rsplit(":", 1)[0]
        if host in ("127.0.0.1", "localhost"):
            return True
        self._json(403, {"error": "local only"})
        return False

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, data: object) -> None:
        self._send(status, json.dumps(data).encode(), "application/json")

    def _events(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        tab = self.server.hub.subscribe()
        try:
            while True:
                try:
                    name, data = tab.get(timeout=KEEPALIVE)
                    chunk = f"event: {name}\ndata: {json.dumps(data)}\n\n"
                except queue.Empty:
                    chunk = ": still here\n\n"  # a comment: keeps the connection open
                self.wfile.write(chunk.encode())
                self.wfile.flush()
        except OSError:
            pass  # the tab was closed
        finally:
            self.server.hub.unsubscribe(tab)
