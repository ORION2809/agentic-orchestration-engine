"""Tests for checkpoint save/load and orchestrator resume."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.config import Config
from app.models.state import AgentState, RunContext, TRANSITIONS
from app.persistence.file_store import FileCheckpointStore


@pytest.fixture
def checkpoint_dir(tmp_path: Path) -> Path:
    return tmp_path / "checkpoints"


@pytest.fixture
def store(checkpoint_dir: Path) -> FileCheckpointStore:
    return FileCheckpointStore(checkpoint_dir)


def test_checkpoint_save_and_load(store: FileCheckpointStore) -> None:
    """Checkpoint round-trip: save → load restores same data."""
    snapshot = {
        "run_id": "test-001",
        "state": AgentState.BUILDING.value,
        "retry_count": 1,
        "build_number": 2,
        "context": RunContext(run_id="test-001", original_idea="a dodge game").to_dict(),
        "timestamp": "2024-01-01T00:00:00Z",
        "token_summary": {"total_tokens": 5000},
    }
    store.save("test-001", snapshot)
    loaded = store.load("test-001")

    assert loaded is not None
    assert loaded["run_id"] == "test-001"
    assert loaded["state"] == "building"
    assert loaded["retry_count"] == 1
    assert loaded["build_number"] == 2
    assert loaded["context"]["original_idea"] == "a dodge game"


def test_checkpoint_not_found(store: FileCheckpointStore) -> None:
    """Loading a missing checkpoint returns None."""
    assert store.load("nonexistent") is None


def test_checkpoint_exists(store: FileCheckpointStore) -> None:
    """exists() returns True only when a checkpoint has been saved."""
    assert not store.exists("test-002")
    store.save("test-002", {"run_id": "test-002", "state": "init"})
    assert store.exists("test-002")


def test_context_roundtrip_preserves_all_fields(
    sample_clarification, sample_plan, sample_critique, sample_validation_report
) -> None:
    """RunContext → to_dict → from_dict preserves all fields."""
    ctx = RunContext(run_id="roundtrip-001")
    ctx.original_idea = "make a platformer"
    ctx.clarification = sample_clarification
    ctx.plan = sample_plan
    ctx.critique = sample_critique
    ctx.validation_report = sample_validation_report
    ctx.game_files = {"index.html": "<html></html>", "style.css": "body{}", "game.js": "loop()"}
    ctx.repair_instructions = ["fix collision"]
    ctx.validation_errors = ["no game loop"]
    ctx.complexity_tier = "complex"
    ctx.build_number = 3

    data = ctx.to_dict()
    restored = RunContext.from_dict(data)

    assert restored.run_id == "roundtrip-001"
    assert restored.original_idea == "make a platformer"
    assert restored.complexity_tier == "complex"
    assert restored.build_number == 3
    assert restored.game_files is not None
    assert "index.html" in restored.game_files
    assert restored.repair_instructions == ["fix collision"]
    assert restored.validation_errors == ["no game loop"]


def test_resume_restores_correct_state(store: FileCheckpointStore) -> None:
    """Orchestrator.resume properly restores state from checkpoint."""
    from app.orchestrator import Orchestrator, create_stores

    config = Config()
    config.batch_mode = True
    config.output_dir = Path(store.output_dir)

    # Save a checkpoint at BUILDING state
    ctx = RunContext(run_id="resume-001", original_idea="a dodge game")
    ctx.build_number = 1
    snapshot = {
        "run_id": "resume-001",
        "state": AgentState.BUILDING.value,
        "retry_count": 0,
        "build_number": 1,
        "context": ctx.to_dict(),
        "timestamp": "2024-01-01T00:00:00Z",
    }
    store.save("resume-001", snapshot)

    # Resume
    from app.persistence.file_store import FileArtifactStore

    artifact_store = FileArtifactStore(store.output_dir)
    orchestrator = Orchestrator.resume("resume-001", config, store, artifact_store)

    assert orchestrator.state == AgentState.BUILDING
    assert orchestrator.context.run_id == "resume-001"
    assert orchestrator.context.original_idea == "a dodge game"
    assert orchestrator.build_number == 1


def test_resume_nonexistent_raises(store: FileCheckpointStore) -> None:
    """Resuming a non-existent run raises ValueError."""
    from app.orchestrator import Orchestrator
    from app.persistence.file_store import FileArtifactStore

    config = Config()
    artifact_store = FileArtifactStore(store.output_dir)

    with pytest.raises(ValueError, match="No checkpoint found"):
        Orchestrator.resume("does-not-exist", config, store, artifact_store)
