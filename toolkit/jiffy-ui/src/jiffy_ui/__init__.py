"""A local dashboard: pick a lab, press Run, watch its latency, busy % and queue live."""

from jiffy_ui.app import Dashboard
from jiffy_ui.board import Board, Hub
from jiffy_ui.labs import Lab, find_labs, find_root
from jiffy_ui.runner import BusyError, Runner

__all__ = ["Board", "BusyError", "Dashboard", "Hub", "Lab", "Runner", "find_labs", "find_root"]
