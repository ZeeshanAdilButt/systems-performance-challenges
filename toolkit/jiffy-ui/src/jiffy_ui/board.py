"""Turn the part's live feed into chart points, and hand every event to every open tab.

The feed (``jiffy_metrics.live``) carries two kinds of numbers:

- latencies, in batches from the part every 100 ms. Ten requests are too few for a p99, so
  ``Board`` piles them up and every ``TICK`` seconds boils the pile down to one point:
  p50 and p99 with the toolkit's ``Histogram``, and the share of slow requests;
- busy % and queue length, from the server every 100 ms. Those go straight to the page,
  one point each, so a 300 ms freeze shows up as a hole in the line.
"""

from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable
from typing import Any

from jiffy_metrics import Histogram

TICK = 0.5  # seconds per chart point
DEFAULT_SLOW = 0.050  # what counts as slow until the part says otherwise

Event = tuple[str, dict[str, Any]]


class Board:
    """What the feed said since the last point. Thread-safe."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self.started = clock()
        self.slow = DEFAULT_SLOW
        self._latency: list[float] = []
        self._errors = 0

    def elapsed(self) -> float:
        return self._clock() - self.started

    def take(self, message: dict[str, Any]) -> Event | None:
        """One feed message. Returns an event to show right away (a step, a new slow
        threshold, a server report), or None if it only counts towards the next point."""
        kind = message.get("kind")
        with self._lock:
            if kind == "samples":
                self._latency.extend(float(x) for x in message.get("latency", []))
                self._errors += int(message.get("errors", 0))
            elif kind == "use":
                return "use", {
                    "t": round(self.elapsed(), 2),
                    "busy": float(message["busy"]),
                    "queue": float(message["queue"]),
                    "max_queue": int(message["max_queue"]),
                }
            elif kind == "slow":
                self.slow = float(message["above"])
                return "slow", {"above": self.slow}
            elif kind == "step":
                return "step", {"t": round(self.elapsed(), 2), "text": str(message["text"])}
        return None

    def point(self) -> dict[str, Any]:
        """The latencies since the last point, boiled down. With none, the numbers are
        None, which the page draws as a gap."""
        with self._lock:
            latency, errors = self._latency, self._errors
            self._latency, self._errors = [], 0
        h = Histogram.of(latency) if latency else None
        return {
            "t": round(self.elapsed(), 2),
            "count": len(latency),
            "errors": errors,
            "p50": h.percentile(50) if h else None,
            "p99": h.percentile(99) if h else None,
            "slow": h.fraction_above(self.slow) if h else None,
        }


class Hub:
    """Every event of the current run, kept so that a tab opened (or reloaded) mid-run
    catches up, and pushed to each open tab as it happens."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._history: list[Event] = []
        self._tabs: list[queue.Queue[Event]] = []

    def publish(self, name: str, data: dict[str, Any], *, fresh: bool = False) -> None:
        """``fresh`` starts a new run: tabs that connect later won't see the old one."""
        with self._lock:
            if fresh:
                self._history.clear()
            self._history.append((name, data))
            for tab in self._tabs:
                tab.put((name, data))

    def subscribe(self) -> queue.Queue[Event]:
        tab: queue.Queue[Event] = queue.Queue()
        with self._lock:
            for event in self._history:
                tab.put(event)
            self._tabs.append(tab)
        return tab

    def unsubscribe(self, tab: queue.Queue[Event]) -> None:
        with self._lock:
            if tab in self._tabs:
                self._tabs.remove(tab)
