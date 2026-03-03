"""Tests for schema contracts."""

from __future__ import annotations

from app.models.schemas import (
    Assumption,
    ClarificationResult,
    ComplexityAssessment,
    CriticFinding,
    CritiqueResult,
    GeneratedGame,
    RunResult,
    SecurityFinding,
    ValidationCheck,
    ValidationReport,
)


def test_assumption_fields() -> None:
    a = Assumption(dimension="difficulty", assumed_value="medium", reason="default")
    assert a.assumed_value == "medium"


def test_clarification_confidence_alias(sample_clarification: ClarificationResult) -> None:
    assert sample_clarification.confidence == sample_clarification.confidence_score
    assert sample_clarification.confidence_score > 0


def test_generated_game_file_map(sample_game: GeneratedGame) -> None:
    files = sample_game.files
    assert set(files.keys()) == {"index.html", "style.css", "game.js"}


def test_critique_pass_property(sample_critique: CritiqueResult) -> None:
    assert sample_critique.pass_result is True

    failing = CritiqueResult(
        findings=[
            CriticFinding(
                severity="blocker",
                category="logic",
                description="No game loop",
                affected_file="game.js",
            )
        ]
    )
    assert failing.pass_result is False


def test_validation_report() -> None:
    report = ValidationReport(
        passed=False,
        checks=[
            ValidationCheck(
                name="js_syntax",
                passed=False,
                details="SyntaxError",
                severity="blocker",
            )
        ],
    )
    assert report.passed is False


def test_run_result_fields() -> None:
    r = RunResult(run_id="abc123", success=False, status="failed", error="bad build")
    assert r.status == "failed"
    assert r.error == "bad build"


def test_security_finding_fields() -> None:
    f = SecurityFinding(
        file="game.js",
        line=10,
        pattern=r"fetch\\(",
        severity="blocker",
        description="Network request",
        snippet="fetch('/api')",
    )
    assert f.line == 10


def test_complexity_assessment() -> None:
    ca = ComplexityAssessment(score=5, tier="moderate", factors=["3 entities"])
    assert ca.tier == "moderate"
