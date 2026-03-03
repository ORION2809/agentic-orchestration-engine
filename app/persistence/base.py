"""Abstract persistence interfaces for checkpoint and artifact storage."""

from __future__ import annotations

from abc import ABC, abstractmethod


class CheckpointStore(ABC):
    """Abstract persistence for run state. Backend is injectable."""

    @abstractmethod
    def save(self, run_id: str, snapshot: dict) -> None:
        """Persist a checkpoint snapshot."""
        ...

    @abstractmethod
    def load(self, run_id: str) -> dict | None:
        """Load a checkpoint snapshot, or None if not found."""
        ...

    @abstractmethod
    def exists(self, run_id: str) -> bool:
        """Check if a checkpoint exists for the given run."""
        ...


class ArtifactStore(ABC):
    """Abstract persistence for game file artifacts."""

    @abstractmethod
    def save_game(
        self, run_id: str, files: dict[str, str], build_number: int = 1
    ) -> str:
        """Save game files. Returns the path/URI of the saved artifacts."""
        ...

    @abstractmethod
    def load_game(self, run_id: str) -> dict[str, str] | None:
        """Load the latest game files for a run."""
        ...
