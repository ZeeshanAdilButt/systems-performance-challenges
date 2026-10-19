"""A cap on extra calls: hedges (or retries) may add at most ``ratio`` more calls.

Every normal call earns ``ratio`` of a token. Every extra call spends one whole token,
and is refused when there isn't one. With ``ratio = 0.05`` it takes 20 normal calls to
earn one extra call, so extra calls can never be more than 5% of normal calls, however
badly the timer that asks for them misbehaves. ``max_saved`` stops a long quiet spell from
banking a big burst of extra calls for later.

Finagle's ``RetryBudget`` works the same way.
"""

from __future__ import annotations

import threading

# 20 x 0.05 is 0.9999999999999999 in floating point; that is still one token.
_ROUNDING = 1e-9


class HedgeBudget:
    """Extra calls allowed: ``ratio`` per normal call, at most ``max_saved`` banked."""

    def __init__(self, ratio: float, max_saved: float = 10.0) -> None:
        if not 0 <= ratio <= 1:
            raise ValueError(f"ratio must be in [0, 1], got {ratio}")
        if max_saved < 1:
            raise ValueError(f"max_saved must be at least 1, got {max_saved}")
        self.ratio = ratio
        self.max_saved = max_saved
        self.tokens = 0.0  # starts empty: nothing is allowed before any normal call
        self.spent = 0
        self.denied = 0
        self._lock = threading.Lock()

    def earn(self, calls: int = 1) -> None:
        """``calls`` normal calls were sent."""
        with self._lock:
            self.tokens = min(self.max_saved, self.tokens + calls * self.ratio)

    def spend(self) -> bool:
        """May one extra call go out? Takes a token if so."""
        with self._lock:
            if self.tokens >= 1 - _ROUNDING:
                self.tokens = max(0.0, self.tokens - 1)
                self.spent += 1
                return True
            self.denied += 1
            return False
