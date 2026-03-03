"""Tests for clarifier confidence and dimension metadata."""

from __future__ import annotations

from app.agents.clarifier import DIMENSIONS, compute_confidence


def _resolved(keys: set[str]) -> dict[str, str]:
    return {k: "filled" for k in keys}


def test_all_dimensions_covered() -> None:
    keys = {d["key"] for d in DIMENSIONS}
    conf = compute_confidence(_resolved(keys))
    assert conf >= 0.95


def test_no_dimensions_gives_zero() -> None:
    conf = compute_confidence({})
    assert conf == 0.0


def test_required_only_high_confidence() -> None:
    required = {d["key"] for d in DIMENSIONS if d["required"]}
    conf = compute_confidence(_resolved(required))
    assert conf >= 0.75


def test_optional_only_lower_confidence() -> None:
    optional = {d["key"] for d in DIMENSIONS if not d["required"]}
    conf = compute_confidence(_resolved(optional))
    assert conf < 0.75


def test_confidence_monotonic() -> None:
    small = compute_confidence(_resolved({"genre"}))
    medium = compute_confidence(_resolved({"genre", "core_objective", "controls"}))
    large = compute_confidence(
        _resolved({"genre", "core_objective", "controls", "win_condition", "lose_condition"})
    )
    assert small < medium < large


def test_dimensions_integrity() -> None:
    keys = [d["key"] for d in DIMENSIONS]
    assert len(DIMENSIONS) == 10
    assert len(keys) == len(set(keys))
    assert {"genre", "core_objective", "controls", "win_condition", "lose_condition"}.issubset(keys)
