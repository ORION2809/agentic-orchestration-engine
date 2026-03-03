"""Adaptive model selector with quality-driven escalation."""

from __future__ import annotations

import structlog

logger = structlog.get_logger()


class AdaptiveModelSelector:
    """
    Auto-escalate to premium model on two triggers:
    1. Phase execution failures (exceptions, parse errors)
    2. Downstream validation failures (quality signal from later phases)

    When total failure signals reach max_cheap_failures, the selector
    switches from the default (cheap) model to the escalation (premium) model.
    """

    def __init__(
        self,
        overrides: dict[str, str],
        escalation: dict[str, str],
        max_cheap_failures: int = 2,
    ):
        self.overrides = dict(overrides)
        self.escalation = dict(escalation)
        self.max_cheap_failures = max_cheap_failures
        self.phase_failures: dict[str, int] = {}
        self.validation_failures: dict[str, int] = {}

    def get_model(self, phase: str) -> str:
        """Return the model for the given phase, possibly escalated."""
        exec_failures = self.phase_failures.get(phase, 0)
        val_failures = self.validation_failures.get(phase, 0)
        total_signal = exec_failures + val_failures

        if total_signal >= self.max_cheap_failures and phase in self.escalation:
            model = self.escalation[phase]
            logger.info(
                "model_escalated",
                phase=phase,
                model=model,
                exec_failures=exec_failures,
                validation_failures=val_failures,
            )
            return model
        return self.overrides.get(phase, "gpt-4o")

    def record_failure(self, phase: str) -> None:
        """Record an execution failure (exception, parse error)."""
        self.phase_failures[phase] = self.phase_failures.get(phase, 0) + 1

    def record_validation_failure(self, phase: str) -> None:
        """Record a quality failure (phase succeeded but downstream validation failed)."""
        self.validation_failures[phase] = self.validation_failures.get(phase, 0) + 1

    def record_success(self, phase: str) -> None:
        """Reset failure counts on full success."""
        self.phase_failures[phase] = 0
        self.validation_failures[phase] = 0
