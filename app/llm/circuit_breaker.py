"""Per-provider sliding-window circuit breaker with time decay."""

from __future__ import annotations

import structlog
from collections import deque
from datetime import datetime, timedelta
from typing import Literal

logger = structlog.get_logger()


class SlidingWindowCircuitBreaker:
    """
    Per-provider circuit breaker with time-decayed sliding window.

    States:
        CLOSED  ──(failure_rate ≥ threshold)──► OPEN
        OPEN    ──(recovery_timeout elapsed)──► HALF-OPEN
        HALF-OPEN ──(probe succeeds)──► CLOSED
        HALF-OPEN ──(probe fails)──► OPEN
    """

    def __init__(
        self,
        provider: str,
        window_size: timedelta = timedelta(minutes=5),
        failure_rate_threshold: float = 0.5,
        min_calls_in_window: int = 5,
        recovery_timeout: timedelta = timedelta(seconds=60),
    ):
        self.provider = provider
        self.window_size = window_size
        self.failure_rate_threshold = failure_rate_threshold
        self.min_calls_in_window = min_calls_in_window
        self.recovery_timeout = recovery_timeout

        self.calls: deque[tuple[datetime, bool]] = deque()  # (timestamp, success)
        self.state: Literal["closed", "open", "half-open"] = "closed"
        self.opened_at: datetime | None = None

    def record(self, success: bool) -> None:
        """Record the outcome of an LLM call."""
        now = datetime.utcnow()
        self.calls.append((now, success))
        self._evict_old(now)

        if self.state == "half-open":
            if success:
                self.state = "closed"
                self.opened_at = None
                logger.info("circuit_breaker_closed", provider=self.provider)
            else:
                self.state = "open"
                self.opened_at = now
                logger.warning("circuit_breaker_reopened", provider=self.provider)
            return

        if len(self.calls) >= self.min_calls_in_window:
            failure_count = sum(1 for _, s in self.calls if not s)
            failure_rate = failure_count / len(self.calls)
            if failure_rate >= self.failure_rate_threshold:
                self.state = "open"
                self.opened_at = now
                logger.warning(
                    "circuit_breaker_opened",
                    provider=self.provider,
                    failure_rate=round(failure_rate, 2),
                )

    def can_execute(self) -> bool:
        """Check whether the circuit allows a call."""
        if self.state == "closed":
            return True
        if self.state == "open":
            if self.opened_at and datetime.utcnow() - self.opened_at >= self.recovery_timeout:
                self.state = "half-open"
                logger.info("circuit_breaker_half_open", provider=self.provider)
                return True
            return False
        # half-open: allow one probe
        return True

    def _evict_old(self, now: datetime) -> None:
        cutoff = now - self.window_size
        while self.calls and self.calls[0][0] < cutoff:
            self.calls.popleft()
