"""Tests for the prompt versioning system."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.prompts.versioning import PromptVersion, get_manifest, verify_manifest


@pytest.fixture
def prompt_dir(tmp_path: Path) -> Path:
    """Create a temporary prompts directory with sample files."""
    d = tmp_path / "prompts"
    d.mkdir()
    (d / "builder_system.md").write_text("You are a builder.", encoding="utf-8")
    (d / "planner_system.md").write_text("You are a planner.", encoding="utf-8")
    (d / "critic_system.md").write_text("You are a critic.", encoding="utf-8")
    return d


def test_prompt_version_from_file(prompt_dir: Path) -> None:
    """PromptVersion.from_file creates a valid version with SHA-256."""
    pv = PromptVersion.from_file(prompt_dir / "builder_system.md")
    assert pv.name == "builder_system"
    assert len(pv.sha256) == 64  # SHA-256 hex length
    assert pv.content == "You are a builder."


def test_get_manifest(prompt_dir: Path) -> None:
    """get_manifest loads all .md files and returns versioned entries."""
    manifest = get_manifest(prompt_dir)
    assert len(manifest) == 3
    assert "builder_system" in manifest
    assert "planner_system" in manifest
    assert "critic_system" in manifest


def test_manifest_empty_dir(tmp_path: Path) -> None:
    """Empty directory returns empty manifest."""
    empty = tmp_path / "empty_prompts"
    empty.mkdir()
    manifest = get_manifest(empty)
    assert len(manifest) == 0


def test_manifest_nonexistent_dir(tmp_path: Path) -> None:
    """Nonexistent directory returns empty manifest."""
    manifest = get_manifest(tmp_path / "nope")
    assert len(manifest) == 0


def test_verify_manifest_unchanged(prompt_dir: Path) -> None:
    """verify_manifest reports no changes when files haven't changed."""
    manifest = get_manifest(prompt_dir)
    changed = verify_manifest(manifest, prompt_dir)
    assert changed == []


def test_verify_manifest_detects_change(prompt_dir: Path) -> None:
    """verify_manifest detects when a prompt file has been modified."""
    manifest = get_manifest(prompt_dir)
    # Modify a file
    (prompt_dir / "builder_system.md").write_text("Updated builder prompt.", encoding="utf-8")
    changed = verify_manifest(manifest, prompt_dir)
    assert "builder_system" in changed


def test_verify_manifest_detects_deletion(prompt_dir: Path) -> None:
    """verify_manifest detects when a prompt file has been deleted."""
    manifest = get_manifest(prompt_dir)
    (prompt_dir / "critic_system.md").unlink()
    changed = verify_manifest(manifest, prompt_dir)
    assert "critic_system" in changed


def test_deterministic_hashing(prompt_dir: Path) -> None:
    """Same content always produces the same hash."""
    v1 = PromptVersion.from_file(prompt_dir / "builder_system.md")
    v2 = PromptVersion.from_file(prompt_dir / "builder_system.md")
    assert v1.sha256 == v2.sha256
