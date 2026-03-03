"""Tests for validators: schema, static code, and security scans."""

from __future__ import annotations

from pathlib import Path

from app.models.schemas import GeneratedGame, SecurityFinding
from app.validators.code_validator import (
    check_css_validity,
    check_file_existence,
    check_html_structure,
    check_structural_heuristics,
    load_game_from_dir,
    run_code_validation,
    run_code_validation_from_dir,
)
from app.validators.schema_validator import (
    validate_clarification,
    validate_critique,
    validate_game_files,
    validate_plan,
)
from app.validators.security_scanner import (
    format_security_report,
    has_blockers,
    scan_generated_code,
)


def test_schema_validation_passes(
    sample_clarification,
    sample_plan,
    sample_game,
    sample_critique,
) -> None:
    assert validate_clarification(sample_clarification).passed
    assert validate_plan(sample_plan).passed
    assert validate_game_files(sample_game).passed
    assert validate_critique(sample_critique).passed


def test_code_validation_passes(sample_game: GeneratedGame) -> None:
    checks = run_code_validation(sample_game)
    assert any(c.name == "file_existence" and c.passed for c in checks)
    assert any(c.name == "js_syntax" for c in checks)


def test_individual_code_checks(sample_game: GeneratedGame) -> None:
    assert check_file_existence(sample_game).passed
    assert check_html_structure(sample_game).passed
    assert check_css_validity(sample_game).passed
    assert check_structural_heuristics(sample_game).passed


def test_directory_validation(tmp_path: Path, sample_game_files: dict[str, str]) -> None:
    for name, content in sample_game_files.items():
        (tmp_path / name).write_text(content, encoding="utf-8")

    loaded = load_game_from_dir(tmp_path)
    assert isinstance(loaded, GeneratedGame)

    checks = run_code_validation_from_dir(tmp_path)
    assert len(checks) >= 3


def test_security_scanner_clean(sample_game_files: dict[str, str]) -> None:
    findings = scan_generated_code(sample_game_files)
    assert not has_blockers(findings)


def test_security_scanner_blockers() -> None:
    findings = scan_generated_code({"game.js": "fetch('/api'); eval('x')"})
    assert has_blockers(findings)


def test_security_report_formatting() -> None:
    clean = format_security_report([])
    assert "PASS" in clean

    findings = [
        SecurityFinding(
            file="game.js",
            line=1,
            pattern="fetch",
            severity="blocker",
            description="fetch() call",
            snippet="fetch('/api')",
        )
    ]
    report = format_security_report(findings)
    assert "BLOCKERS" in report
