"""One JSON object per line, in both directions, over one long-lived TCP connection.

Every request carries an ``id`` the client picks, and the reply echoes it. That lets one
connection carry hundreds of requests at once and get the answers back in any order, so
the client never pays for a new connection (a TCP handshake, a new port) per request.

Requests::

    {"id": 7, "op": "work", "work": 0.010}      do 10 ms of work
    {"id": 8, "op": "use", "widths": [1, 0.01]}  USE summary of the run so far
    {"id": 9, "op": "reset"}                    start a fresh run

Replies::

    {"id": 7, "wait": 0.0031, "service": 0.0104}
    {"id": 8, "use": [{...}, {...}]}
    {"id": 9}
"""

from __future__ import annotations

import json
from typing import Any

Message = dict[str, Any]


def encode(message: Message) -> bytes:
    return json.dumps(message, separators=(",", ":")).encode() + b"\n"


def decode(line: bytes) -> Message:
    message = json.loads(line)
    if not isinstance(message, dict):
        raise ValueError(f"expected a JSON object, got {line!r}")
    return message
