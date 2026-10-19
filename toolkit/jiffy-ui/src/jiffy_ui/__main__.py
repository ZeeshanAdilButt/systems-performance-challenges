"""``uv run jiffy-ui``: start the dashboard and open it in the browser."""

from __future__ import annotations

import argparse
import webbrowser
from collections.abc import Sequence
from pathlib import Path

from jiffy_ui.app import Dashboard
from jiffy_ui.labs import find_root


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jiffy-ui", description=__doc__)
    parser.add_argument("--port", type=int, default=8765, help="0 picks any free port")
    parser.add_argument("--root", type=Path, help="the repository (default: found from here)")
    parser.add_argument("--no-browser", action="store_true", help="don't open a browser tab")
    args = parser.parse_args(argv)
    root = find_root((args.root or Path.cwd()).resolve())
    try:
        dashboard = Dashboard(root, args.port)
    except OSError:  # that port is taken, perhaps by another dashboard: take any
        dashboard = Dashboard(root, 0)
    print(f"lab dashboard on {dashboard.url}  (Ctrl+C to stop)", flush=True)
    if not args.no_browser:
        webbrowser.open(dashboard.url)
    try:
        dashboard.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        dashboard.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
