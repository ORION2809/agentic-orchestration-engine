"""File-based persistence — default for CLI/Docker single-run mode.

Supports immutable build versioning: each rebuild gets its own directory.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import structlog

from app.persistence.base import ArtifactStore, CheckpointStore

logger = structlog.get_logger()


class FileCheckpointStore(CheckpointStore):
    """Writes checkpoint.json to local disk. Default for single-container."""

    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)

    def save(self, run_id: str, snapshot: dict) -> None:
        path = self.output_dir / run_id / "checkpoint.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(snapshot, indent=2, default=str))
        logger.debug("checkpoint_saved", run_id=run_id, path=str(path))

    def load(self, run_id: str) -> dict | None:
        path = self.output_dir / run_id / "checkpoint.json"
        if path.exists():
            return json.loads(path.read_text())
        return None

    def exists(self, run_id: str) -> bool:
        return (self.output_dir / run_id / "checkpoint.json").exists()


class FileArtifactStore(ArtifactStore):
    """File-based artifact store with immutable build versioning.

    Each build attempt gets its own directory: outputs/<run_id>/build_<N>/
    A 'game' directory (or junction on Windows) points to the latest build.
    """

    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)

    def save_game(
        self, run_id: str, files: dict[str, str], build_number: int = 1
    ) -> str:
        build_dir = self.output_dir / run_id / f"build_{build_number}"
        build_dir.mkdir(parents=True, exist_ok=True)

        for filename, content in files.items():
            (build_dir / filename).write_text(content, encoding="utf-8")

        # Update 'game' directory to point to latest build
        latest = self.output_dir / run_id / "game"
        if latest.exists():
            # Remove old directory/junction
            if latest.is_symlink() or latest.is_dir():
                import shutil
                shutil.rmtree(latest, ignore_errors=True)

        # Copy latest build into game/ for cross-platform compatibility
        import shutil
        shutil.copytree(build_dir, latest)

        logger.info(
            "artifacts_saved",
            run_id=run_id,
            build_number=build_number,
            path=str(build_dir),
        )
        return str(build_dir)

    def load_game(self, run_id: str) -> dict[str, str] | None:
        game_dir = self.output_dir / run_id / "game"
        if not game_dir.exists():
            return None

        files = {}
        for filepath in game_dir.iterdir():
            if filepath.is_file():
                files[filepath.name] = filepath.read_text(encoding="utf-8")
        return files if files else None
