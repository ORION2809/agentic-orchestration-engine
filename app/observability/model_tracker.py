"""Model quality tracker — adaptive routing based on per-model success rates."""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger()


@dataclass
class ModelRecord:
    """Track success/failure metrics for a specific model."""
    successes: int = 0
    failures: int = 0
    total_tokens: int = 0
    total_latency: float = 0.0
    last_used: float = 0.0

    @property
    def total_calls(self) -> int:
        return self.successes + self.failures

    @property
    def success_rate(self) -> float:
        if self.total_calls == 0:
            return 1.0  # optimistic default
        return self.successes / self.total_calls

    @property
    def avg_latency(self) -> float:
        if self.total_calls == 0:
            return 0.0
        return self.total_latency / self.total_calls

    @property
    def avg_tokens(self) -> float:
        if self.total_calls == 0:
            return 0.0
        return self.total_tokens / self.total_calls


class ModelQualityTracker:
    """Tracks per-model quality metrics for adaptive routing decisions.

    Maintains success rates, latency, and token usage per model+phase.
    Used by AdaptiveModelSelector to make escalation decisions.
    """

    def __init__(self, window_seconds: float = 3600.0) -> None:
        """Initialize tracker.

        Args:
            window_seconds: Time window for relevance weighting (default 1h).
        """
        self._window = window_seconds
        # Keyed by (model, phase)
        self._records: dict[tuple[str, str], ModelRecord] = defaultdict(ModelRecord)
        # Keyed by model only (aggregate)
        self._aggregate: dict[str, ModelRecord] = defaultdict(ModelRecord)

    def record_success(
        self,
        model: str,
        phase: str,
        tokens: int = 0,
        latency: float = 0.0,
    ) -> None:
        """Record a successful LLM call."""
        now = time.time()
        key = (model, phase)
        self._records[key].successes += 1
        self._records[key].total_tokens += tokens
        self._records[key].total_latency += latency
        self._records[key].last_used = now

        self._aggregate[model].successes += 1
        self._aggregate[model].total_tokens += tokens
        self._aggregate[model].total_latency += latency
        self._aggregate[model].last_used = now

    def record_failure(
        self,
        model: str,
        phase: str,
        tokens: int = 0,
        latency: float = 0.0,
    ) -> None:
        """Record a failed LLM call."""
        now = time.time()
        key = (model, phase)
        self._records[key].failures += 1
        self._records[key].total_tokens += tokens
        self._records[key].total_latency += latency
        self._records[key].last_used = now

        self._aggregate[model].failures += 1
        self._aggregate[model].total_tokens += tokens
        self._aggregate[model].total_latency += latency
        self._aggregate[model].last_used = now

    def get_success_rate(self, model: str, phase: str | None = None) -> float:
        """Get success rate for a model, optionally in a specific phase."""
        if phase:
            return self._records[(model, phase)].success_rate
        return self._aggregate[model].success_rate

    def get_record(self, model: str, phase: str) -> ModelRecord:
        """Get the full record for a model+phase combination."""
        return self._records[(model, phase)]

    def should_escalate(
        self,
        model: str,
        phase: str,
        min_calls: int = 3,
        threshold: float = 0.5,
    ) -> bool:
        """Determine if a model should be escalated based on failure rate.

        Args:
            model: Model identifier
            phase: Pipeline phase
            min_calls: Minimum calls before escalation can trigger
            threshold: Success rate below which escalation is recommended

        Returns:
            True if the model's success rate in this phase warrants escalation.
        """
        record = self._records[(model, phase)]
        if record.total_calls < min_calls:
            return False
        return record.success_rate < threshold

    def get_best_model(
        self,
        candidates: list[str],
        phase: str,
        min_calls: int = 2,
    ) -> str | None:
        """Pick the best model from candidates based on quality data.

        Args:
            candidates: List of model identifiers to choose from
            phase: Pipeline phase for contextual selection
            min_calls: Minimum calls for a model to be considered

        Returns:
            Best model identifier, or None if no data.
        """
        best_model = None
        best_rate = -1.0

        for model in candidates:
            record = self._records[(model, phase)]
            if record.total_calls < min_calls:
                continue
            if record.success_rate > best_rate:
                best_rate = record.success_rate
                best_model = model

        return best_model

    def get_summary(self) -> dict:
        """Return a summary of all tracked models."""
        summary = {}
        for model, record in self._aggregate.items():
            summary[model] = {
                "total_calls": record.total_calls,
                "success_rate": round(record.success_rate, 3),
                "avg_latency": round(record.avg_latency, 3),
                "avg_tokens": round(record.avg_tokens, 1),
            }
        return summary
