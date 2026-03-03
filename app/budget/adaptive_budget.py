"""Adaptive token budget management — scales with plan complexity."""

from __future__ import annotations

import structlog

from app.models.schemas import ComplexityAssessment

logger = structlog.get_logger()


class AdaptiveTokenBudget:
    """Budget scales with plan complexity instead of being fixed.

    Tiers:
        simple   → 30k total, 10k builder, 5k repairs
        moderate → 50k total, 15k builder, 10k repairs
        complex  → 70k total, 25k builder, 15k repairs
    """

    TIER_BUDGETS: dict[str, dict[str, int]] = {
        "simple": {"total": 30_000, "builder": 10_000, "repairs": 5_000},
        "moderate": {"total": 50_000, "builder": 15_000, "repairs": 10_000},
        "complex": {"total": 70_000, "builder": 25_000, "repairs": 15_000},
    }

    def __init__(self, complexity_tier: str = "moderate"):
        tier = self.TIER_BUDGETS.get(complexity_tier, self.TIER_BUDGETS["moderate"])
        self.max_total: int = tier["total"]
        self.builder_budget: int = tier["builder"]
        self.repair_budget: int = tier["repairs"]
        self.used: int = 0
        self.per_phase: dict[str, int] = {}
        self.tier: str = complexity_tier

    def can_afford(self, estimated_tokens: int | str) -> bool:
        """Check whether budget can cover an estimated token spend.

        Supports legacy phase-string input ("builder", "repairs", "total")
        for compatibility with older orchestrator code.
        """
        if isinstance(estimated_tokens, str):
            phase = estimated_tokens.lower()
            if phase == "builder":
                estimated_tokens = self.builder_budget
            elif phase in {"repair", "repairs"}:
                estimated_tokens = self.repair_budget
            else:
                estimated_tokens = max(self.builder_budget, self.repair_budget)
        return (self.used + estimated_tokens) <= self.max_total

    def record(self, phase: str, tokens: int) -> None:
        self.used += tokens
        self.per_phase[phase] = self.per_phase.get(phase, 0) + tokens

        if self.used >= self.max_total * 0.8:
            logger.warning(
                "budget_warning",
                used=self.used,
                max_total=self.max_total,
                tier=self.tier,
                pct=round(self.used / self.max_total * 100, 1),
            )

    def remaining(self) -> int:
        return max(0, self.max_total - self.used)

    def cost_estimate_usd(self, model: str = "gpt-4o") -> float:
        pricing = {"gpt-4o": 0.005, "gpt-4o-mini": 0.00015, "claude-sonnet": 0.003}
        rate = pricing.get(model, 0.005)
        return round((self.used / 1000) * rate, 4)

    @classmethod
    def from_complexity(
        cls,
        assessment: ComplexityAssessment | str,
    ) -> AdaptiveTokenBudget:
        if isinstance(assessment, str):
            return cls(complexity_tier=assessment)
        return cls(complexity_tier=assessment.tier)

    def get_summary(self) -> dict:
        return {
            "tier": self.tier,
            "max_total": self.max_total,
            "used": self.used,
            "remaining": self.remaining(),
            "per_phase": dict(self.per_phase),
        }
