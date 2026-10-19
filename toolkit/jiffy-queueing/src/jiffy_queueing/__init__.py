"""Queueing formulas (M/M/c, Erlang C, Little's law) and an exact FCFS simulator."""

from jiffy_queueing.simulate import Job, exponential, fcfs
from jiffy_queueing.theory import MMc, erlang_b, erlang_c, latency_multiplier

__all__ = ["Job", "MMc", "erlang_b", "erlang_c", "exponential", "fcfs", "latency_multiplier"]
