"""``python -m jiffy_service --workers 4``: serve until killed. The first line printed is
``listening <host> <port>``."""

from __future__ import annotations

import argparse
import time
from collections.abc import Sequence

from jiffy_service.server import Server, Stall


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jiffy-service")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--stall-every", type=float, help="seconds between pauses")
    parser.add_argument("--stall-for", type=float, default=0.2, help="length of each pause")
    args = parser.parse_args(argv)
    stall = Stall(args.stall_every, args.stall_for) if args.stall_every else None
    server = Server(args.workers, args.host, args.port, stall).start()
    host, port = server.address
    print(f"listening {host} {port}", flush=True)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        server.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
