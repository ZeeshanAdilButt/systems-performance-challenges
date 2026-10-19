"""A local dashboard: pick a part, press Run, watch its latency, busy % and queue live."""

from jiffy_ui.app import Dashboard
from jiffy_ui.board import Board, Hub
from jiffy_ui.parts import Part, find_parts, find_root
from jiffy_ui.runner import BusyError, Runner

__all__ = ["Board", "BusyError", "Dashboard", "Hub", "Part", "Runner", "find_parts", "find_root"]
