"""IO artifacts — write run outputs (JSON, Markdown, game files) to disk."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog

from app.models.schemas import (
    ClarificationResult,
    CritiqueResult,
    GamePlan,
    RunResult,
    ValidationReport,
)
from app.models.state import RunContext

logger = structlog.get_logger()


def _ensure_model(data: Any, model_cls: type) -> Any:
    """Coerce a dict into a Pydantic model if needed; return None on failure."""
    if data is None:
        return None
    if isinstance(data, model_cls):
        return data
    if isinstance(data, dict):
        try:
            return model_cls(**data)
        except Exception:
            return None
    return data


def write_run_result(result: RunResult, output_dir: Path) -> Path:
    """Write the final RunResult as JSON.

    Args:
        result: The completed run result.
        output_dir: Base output directory.

    Returns:
        Path to the written JSON file.
    """
    run_dir = output_dir / str(result.run_id)
    run_dir.mkdir(parents=True, exist_ok=True)

    result_path = run_dir / "run_result.json"
    result_path.write_text(
        result.model_dump_json(indent=2),
        encoding="utf-8",
    )
    logger.info("run_result_written", path=str(result_path))
    return result_path


def write_context_snapshot(ctx: RunContext, output_dir: Path) -> Path:
    """Write a RunContext snapshot for debugging/audit.

    Args:
        ctx: Current run context.
        output_dir: Base output directory.

    Returns:
        Path to the written JSON file.
    """
    run_dir = output_dir / str(ctx.run_id)
    run_dir.mkdir(parents=True, exist_ok=True)

    snapshot_path = run_dir / "context_snapshot.json"
    snapshot_path.write_text(
        json.dumps(ctx.to_dict(), indent=2, default=str),
        encoding="utf-8",
    )
    logger.debug("context_snapshot_written", path=str(snapshot_path))
    return snapshot_path


def write_game_files(
    game_files: dict[str, str],
    output_dir: Path,
    run_id: str,
    build_number: int,
) -> Path:
    """Write generated game files to the output directory.

    Args:
        game_files: filename → content mapping.
        output_dir: Base output directory.
        run_id: Unique run identifier.
        build_number: Current build iteration.

    Returns:
        Path to the game directory.
    """
    game_dir = output_dir / str(run_id) / f"build_{build_number}" / "game"
    game_dir.mkdir(parents=True, exist_ok=True)

    for filename, content in game_files.items():
        file_path = game_dir / filename
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")

    logger.info(
        "game_files_written",
        game_dir=str(game_dir),
        files=list(game_files.keys()),
        build=build_number,
    )
    return game_dir


def write_markdown_report(
    ctx: RunContext,
    output_dir: Path,
    metrics: dict[str, Any] | None = None,
) -> Path:
    """Write a human-readable Markdown summary of the run.

    Args:
        ctx: Completed run context.
        output_dir: Base output directory.
        metrics: Optional metrics summary dict.

    Returns:
        Path to the Markdown file.
    """
    run_dir = output_dir / str(ctx.run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    report_path = run_dir / "report.md"

    lines = [
        f"# Game Build Report",
        f"",
        f"**Run ID:** `{ctx.run_id}`",
        f"**Idea:** {ctx.original_idea}",
        f"**Complexity:** {ctx.complexity_tier or 'unknown'}",
        f"**Build Number:** {ctx.build_number}",
        f"**Generated:** {datetime.now(timezone.utc).isoformat()}",
        f"",
    ]

    # Clarification summary
    clarification = _ensure_model(ctx.clarification, ClarificationResult)
    if clarification:
        lines.append("## Clarification")
        lines.append(f"- Confidence: {clarification.confidence_score}")
        if clarification.assumptions:
            lines.append("- Assumptions:")
            for a in clarification.assumptions:
                lines.append(f"  - [{a.dimension}] {a.assumed_value} ({a.reason})")
        lines.append("")

    # Plan summary
    plan = _ensure_model(ctx.plan, GamePlan)
    if plan:
        lines.append("## Plan")
        lines.append(f"- Framework: {plan.framework}")
        lines.append(f"- Entities: {len(plan.entities)}")
        lines.append(f"- Mechanics: {len(plan.core_mechanics)}")
        if plan.acceptance_checks:
            lines.append("- Acceptance Checks:")
            for check in plan.acceptance_checks:
                lines.append(f"  - {check}")
        lines.append("")

    # Critique summary
    critique = _ensure_model(ctx.critique, CritiqueResult)
    if critique:
        lines.append("## Critique")
        lines.append(f"- Compliance: {critique.plan_compliance_score}")
        lines.append(f"- Pass: {not critique.has_critical}")
        lines.append(f"- Findings: {len(critique.findings)}")
        for f in critique.findings[:10]:
            lines.append(f"  - [{f.severity}] {f.description}")
        lines.append("")

    # Validation summary
    validation = _ensure_model(ctx.validation_report, ValidationReport)
    if validation:
        lines.append("## Validation")
        lines.append(f"- Passed: {validation.passed}")
        lines.append(f"- Checks: {len(validation.checks)}")
        blockers = [c for c in validation.checks if c.severity == "blocker" and not c.passed]
        if blockers:
            lines.append("- Blockers:")
            for b in blockers:
                lines.append(f"  - {b.name}: {b.details}")
        lines.append("")

    # Metrics
    if metrics:
        lines.append("## Metrics")
        lines.append(f"```json\n{json.dumps(metrics, indent=2)}\n```")
        lines.append("")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("report_written", path=str(report_path))
    return report_path
