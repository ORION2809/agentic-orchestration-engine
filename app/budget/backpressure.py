"""Global token backpressure — sliding-window system-wide cost safety."""

from __future__ import annotations

import structlog
from collections import deque
from datetime import datetime, timedelta

logger = structlog.get_logger()


class GlobalTokenBackpressure:
    """Tracks system-wide token consumption over a sliding window.

    Rejects new runs when burn rate exceeds threshold, preventing
    aggregate cost spikes across all concurrent runs.
    """

    def __init__(
        self,
        window: timedelta = timedelta(minutes=5),
        max_tokens_per_window: int = 500_000,
        max_cost_per_window_usd: float = 5.00,
        *,
        window_seconds: int | None = None,
        max_tokens: int | None = None,
        max_cost: float | None = None,
    ):
        if window_seconds is not None:
            window = timedelta(seconds=window_seconds)
        if max_tokens is not None:
            max_tokens_per_window = max_tokens
        if max_cost is not None:
            max_cost_per_window_usd = max_cost

        self.window = window
        self.max_tokens = max_tokens_per_window
        self.max_cost = max_cost_per_window_usd
        self.records: deque[tuple[datetime, int, float]] = deque()

    def record_usage(self, tokens: int, cost_usd: float) -> None:
        now = datetime.utcnow()
        self.records.append((now, tokens, cost_usd))
        self._evict_old(now)

    def can_accept_new_run(
        self, estimated_tokens: int = 20_000
    ) -> tuple[bool, str]:
        now = datetime.utcnow()
        self._evict_old(now)

        total_tokens = sum(t for _, t, _ in self.records) + estimated_tokens
        total_cost = sum(c for _, _, c in self.records)

        if total_tokens > self.max_tokens:
            msg = (
                f"Token burn rate too high: {total_tokens:,} tokens "
                f"in last {self.window}"
            )
            logger.warning("backpressure_reject_tokens", total_tokens=total_tokens)
            return False, msg

        if total_cost > self.max_cost:
            msg = (
                f"Cost burn rate too high: ${total_cost:.2f} "
                f"in last {self.window}"
            )
            logger.warning("backpressure_reject_cost", total_cost=total_cost)
            return False, msg

        return True, "ok"

    def _evict_old(self, now: datetime) -> None:
        cutoff = now - self.window
        while self.records and self.records[0][0] < cutoff:
            self.records.popleft()
