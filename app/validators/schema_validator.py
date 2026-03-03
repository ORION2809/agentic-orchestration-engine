"""Schema validator — Pydantic contract enforcement for phase I/O."""

from __future__ import annotations

import structlog
from pydantic import ValidationError as PydanticValidationError

from app.models.schemas import (
    ClarificationResult,
    CritiqueResult,
    GamePlan,
    GeneratedGame,
    ValidationCheck,
)

logger = structlog.get_logger()


def _coerce_payload(data: object) -> dict:
    if hasattr(data, "model_dump"):
        return data.model_dump()  # type: ignore[return-value]
    if isinstance(data, dict):
        return data
    return {}


def validate_clarification(data: object) -> ValidationCheck:
    """Validate clarification output against ClarificationResult schema."""
    try:
        ClarificationResult(**_coerce_payload(data))
        return ValidationCheck(name="schema_clarification", passed=True, severity="info")
    except PydanticValidationError as e:
        return ValidationCheck(
            name="schema_clarification",
            passed=False,
            details=str(e),
            severity="blocker",
        )


def validate_plan(data: object) -> ValidationCheck:
    """Validate plan against GamePlan schema."""
    try:
        plan = GamePlan(**_coerce_payload(data))
        # Additional: check required fields are non-empty
        issues = []
        if not plan.game_title:
            issues.append("game_title is empty")
        if not plan.entities:
            issues.append("no entities defined")
        if not plan.core_mechanics:
            issues.append("no mechanics defined")

        if issues:
            return ValidationCheck(
                name="schema_plan",
                passed=False,
                details=f"Plan validation issues: {', '.join(issues)}",
                severity="blocker",
            )
        return ValidationCheck(name="schema_plan", passed=True, severity="info")
    except PydanticValidationError as e:
        return ValidationCheck(
            name="schema_plan",
            passed=False,
            details=str(e),
            severity="blocker",
        )


def validate_game_files(data: object) -> ValidationCheck:
    """Validate generated game files against GeneratedGame schema."""
    try:
        payload = _coerce_payload(data)
        if "index.html" in payload or "game.js" in payload or "style.css" in payload:
            GeneratedGame.from_file_map(payload)
        else:
            GeneratedGame(**payload)
        return ValidationCheck(name="schema_game_files", passed=True, severity="info")
    except PydanticValidationError as e:
        return ValidationCheck(
            name="schema_game_files",
            passed=False,
            details=str(e),
            severity="blocker",
        )


def validate_critique(data: object) -> ValidationCheck:
    """Validate critique result against CritiqueResult schema."""
    try:
        CritiqueResult(**_coerce_payload(data))
        return ValidationCheck(name="schema_critique", passed=True, severity="info")
    except PydanticValidationError as e:
        return ValidationCheck(
            name="schema_critique",
            passed=False,
            details=str(e),
            severity="warning",
        )
