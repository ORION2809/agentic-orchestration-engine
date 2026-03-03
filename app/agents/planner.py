"""Phase 2: Planner Agent — transforms clarified requirements into a machine-readable game plan."""

from __future__ import annotations

from typing import Any

import structlog

from app.agents.base import BaseAgent
from app.models.schemas import (
    ClarificationResult,
    ComplexityAssessment,
    GamePlan,
    GameRequirements,
)
from app.models.state import RunContext

logger = structlog.get_logger()


def decide_framework(requirements: GameRequirements) -> tuple[str, str]:
    """Rule-based framework decision — vanilla unless complexity requires Phaser."""
    needs_physics = any(
        kw in (requirements.core_objective + " " + requirements.genre).lower()
        for kw in ["bounce", "gravity", "collision_complex", "physics"]
    )
    needs_sprites = requirements.visual_style and "sprite" in requirements.visual_style.lower()

    if needs_physics or needs_sprites:
        return "phaser", "Complex mechanics require Phaser's built-in physics/scene/sprite systems"
    return "vanilla", "Simple mechanics achievable with Canvas API; fewer dependencies = more reliable generation"


def score_complexity(plan: GamePlan) -> ComplexityAssessment:
    """Score plan complexity using structural shape + predicted token cost."""
    score = 0
    factors: list[str] = []

    # Entity count
    if len(plan.entities) > 5:
        score += 2
        factors.append(f"{len(plan.entities)} entities (high)")
    elif len(plan.entities) > 3:
        score += 1

    # Physics requirement
    if plan.framework == "phaser" or any(
        "physics" in m.description.lower() for m in plan.core_mechanics
    ):
        score += 2
        factors.append("Physics engine required")

    # Multiple levels
    if any(
        kw in plan.difficulty_curve.lower()
        for kw in ["level", "stage"]
    ):
        score += 2
        factors.append("Multi-level game")

    # Complex state model
    if len(plan.state_model.states) > 4:
        score += 1
        factors.append(f"{len(plan.state_model.states)} game states")

    # Mechanic count
    if len(plan.core_mechanics) > 4:
        score += 1
        factors.append(f"{len(plan.core_mechanics)} mechanics")

    # Entity interaction complexity (combinatorial explosion)
    interaction_pairs = len(plan.entities) * (len(plan.entities) - 1) / 2
    if interaction_pairs > 10:
        score += 2
        factors.append(f"{interaction_pairs:.0f} entity interaction pairs (combinatorial risk)")
    elif interaction_pairs > 5:
        score += 1

    # Framework generation size
    if plan.framework == "phaser":
        score += 1
        factors.append("Phaser framework (larger code generation)")

    # Predicted builder token cost
    estimated_tokens = estimate_builder_tokens(plan)
    if estimated_tokens > 20_000:
        score += 2
        factors.append(f"Estimated builder tokens: {estimated_tokens:,} (high)")
    elif estimated_tokens > 12_000:
        score += 1

    tier = "simple" if score <= 3 else "moderate" if score <= 6 else "complex"

    return ComplexityAssessment(
        score=score,
        tier=tier,
        factors=factors,
        estimated_builder_tokens=estimated_tokens,
    )


def estimate_builder_tokens(plan: GamePlan) -> int:
    """Predict how many tokens the builder will need based on plan shape."""
    base = 5_000
    per_entity = 1_500
    per_mechanic = 1_200
    per_state = 800
    framework_multiplier = 1.4 if plan.framework == "phaser" else 1.0

    estimate = (
        base
        + len(plan.entities) * per_entity
        + len(plan.core_mechanics) * per_mechanic
        + len(plan.state_model.states) * per_state
    )
    return int(estimate * framework_multiplier)


class PlannerAgent(BaseAgent):
    """Generates a structured GamePlan from clarified requirements."""

    PHASE_NAME = "planner"

    def run(self, context: RunContext) -> GamePlan:
        logger.info("planner_start")
        clarification = context.clarification
        if clarification is None:
            clarification_dict: dict[str, Any] = {}
            requirements: dict[str, Any] = {}
        elif isinstance(clarification, ClarificationResult):
            clarification_dict = clarification.model_dump()
            requirements = clarification.resolved_requirements.model_dump()
        elif isinstance(clarification, dict):
            clarification_dict = clarification
            requirements = clarification.get("resolved_requirements", {})
        else:
            clarification_dict = {}
            requirements = {}

        # Determine framework
        req = (
            GameRequirements(**requirements)
            if isinstance(requirements, dict)
            else requirements
        )
        framework, rationale = decide_framework(req)

        # Build the planning prompt
        system_prompt = self.load_prompt("planner_system.md")
        user_prompt = self._build_user_prompt(clarification_dict, framework, rationale)

        # Call LLM for structured plan
        plan = self.call_structured(
            messages=[
                {
                    "role": "system",
                    "content": system_prompt or self._default_system_prompt(),
                },
                {"role": "user", "content": user_prompt},
            ],
            response_model=GamePlan,
        )

        # Override framework with rule-based decision
        plan.framework = framework
        plan.framework_rationale = rationale

        logger.info(
            "planner_done",
            title=plan.game_title,
            framework=plan.framework,
            entities=len(plan.entities),
            mechanics=len(plan.core_mechanics),
        )
        return plan

    def simplify(self, plan: GamePlan, context: RunContext | None = None) -> GamePlan:
        """Ask the planner to simplify a complex plan."""
        logger.info("planner_simplify", original_entities=len(plan.entities))

        prompt = f"""The following game plan is too complex for reliable code generation.
Simplify it to:
- Max 4 entities
- Max 3 core mechanics
- Single level (no multi-level)
- Preserve the core fun and game concept

Original plan:
{plan.model_dump_json(indent=2)}

Return the simplified plan with the same structure."""

        try:
            simplified = self.call_structured(
                messages=[
                    {
                        "role": "system",
                        "content": "You are a game design expert. Simplify the game plan while preserving the core fun.",
                    },
                    {"role": "user", "content": prompt},
                ],
                response_model=GamePlan,
            )
            logger.info(
                "planner_simplified",
                new_entities=len(simplified.entities),
                new_mechanics=len(simplified.core_mechanics),
            )
            return simplified
        except Exception as e:
            logger.warning("simplification_failed", error=str(e))
            return plan

    def _build_user_prompt(
        self,
        clarification: dict[str, Any],
        framework: str,
        rationale: str,
    ) -> str:
        requirements = clarification.get("resolved_requirements", {})
        assumptions = clarification.get("assumptions", [])

        user_template = self.load_prompt("planner_user.md")
        if user_template:
            return user_template.replace(
                "{{requirements}}", str(requirements)
            ).replace(
                "{{assumptions}}", str(assumptions)
            ).replace(
                "{{framework}}", framework
            ).replace(
                "{{framework_rationale}}", rationale
            )

        return f"""Create a complete game plan based on these requirements:

Requirements: {requirements}
Assumptions made: {assumptions}
Framework decision: {framework} — {rationale}

Fill ALL fields in the game plan completely. Be specific and detailed.
Ensure every entity, mechanic, and game state is fully described.
The game must be implementable in a single game.js file using {framework} JS."""

    def _default_system_prompt(self) -> str:
        return """You are an expert game designer and architect. Your job is to create a complete,
detailed game plan (blueprint) that a code generator can follow exactly.

Rules:
- Fill every field in the plan schema completely
- Be specific about entity properties, sizes, speeds, colors
- Define clear state transitions (menu → playing → paused → game_over)
- Specify exact control mappings
- Keep the game achievable in a single game.js file
- Use standard Canvas API patterns for vanilla JS
- Include acceptance checks that can be verified programmatically"""
