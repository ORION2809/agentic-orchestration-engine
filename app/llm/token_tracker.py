"""Per-phase and total token accounting."""

from __future__ import annotations

import structlog

logger = structlog.get_logger()


class TokenTracker:
    """Tracks token usage per-phase and total across the run."""

    # Approximate pricing per 1K tokens (input+output blended estimate)
    MODEL_PRICING: dict[str, float] = {
        "gpt-4o": 0.005,
        "gpt-4o-mini": 0.00015,
        "claude-sonnet-4-20250514": 0.003,
        "claude-sonnet": 0.003,
    }

    def __init__(self) -> None:
        self.total_tokens: int = 0
        self.per_phase: dict[str, int] = {}
        self.per_model: dict[str, int] = {}
        self.calls: list[dict] = []

    def record(self, phase: str, model: str, usage: dict | None) -> None:
        """Record token usage from an LLM response.

        Args:
            phase: The agent phase (clarifier, planner, builder, critic).
            model: The model identifier used.
            usage: The usage dict from the LLM response (total_tokens, etc.).
        """
        if usage is None:
            return

        tokens = 0
        if hasattr(usage, "total_tokens"):
            tokens = usage.total_tokens
        elif isinstance(usage, dict):
            tokens = usage.get("total_tokens", 0)

        self.total_tokens += tokens
        self.per_phase[phase] = self.per_phase.get(phase, 0) + tokens
        self.per_model[model] = self.per_model.get(model, 0) + tokens
        self.calls.append({
            "phase": phase,
            "model": model,
            "tokens": tokens,
        })

        logger.debug(
            "tokens_recorded",
            phase=phase,
            model=model,
            tokens=tokens,
            total=self.total_tokens,
        )

    def cost_estimate_usd(self, default_model: str = "gpt-4o") -> float:
        """Estimate total cost based on per-model token usage."""
        total_cost = 0.0
        for model, tokens in self.per_model.items():
            rate = self.MODEL_PRICING.get(model, self.MODEL_PRICING.get(default_model, 0.005))
            total_cost += (tokens / 1000) * rate
        return round(total_cost, 4)

    def get_summary(self) -> dict:
        """Return a summary dict for the run manifest."""
        return {
            "total_tokens": self.total_tokens,
            "per_phase": dict(self.per_phase),
            "per_model": dict(self.per_model),
            "estimated_cost_usd": self.cost_estimate_usd(),
            "num_calls": len(self.calls),
        }
