"""Concurrency controller — per-user and global limits."""

from __future__ import annotations

import structlog

from app.config import Config

logger = structlog.get_logger()


class ConcurrencyController:
    """Enforces per-user and global concurrency limits.

    In-memory implementation for CLI/Docker single-process mode.
    For distributed production, swap with RedisConcurrencyController.
    """

    def __init__(self, config: Config):
        self.max_concurrent_runs: int = config.max_concurrent_runs
        self.max_runs_per_user: int = config.max_runs_per_user
        self.active_runs: dict[str, list[str]] = {}  # user_id -> [run_ids]

    def can_start_run(self, user_id: str) -> tuple[bool, str]:
        """Check if a new run is allowed for the given user."""
        total_active = sum(len(runs) for runs in self.active_runs.values())
        if total_active >= self.max_concurrent_runs:
            return False, "Global concurrency limit reached"
        if len(self.active_runs.get(user_id, [])) >= self.max_runs_per_user:
            return False, "Per-user concurrency limit reached"
        return True, "ok"

    def register_run(self, user_id: str, run_id: str) -> None:
        """Register a new active run."""
        if user_id not in self.active_runs:
            self.active_runs[user_id] = []
        self.active_runs[user_id].append(run_id)
        logger.debug(
            "run_registered",
            user_id=user_id,
            run_id=run_id,
            active=len(self.active_runs[user_id]),
        )

    def release_run(self, user_id: str, run_id: str) -> None:
        """Release a run on completion or failure."""
        if user_id in self.active_runs:
            self.active_runs[user_id] = [
                r for r in self.active_runs[user_id] if r != run_id
            ]
            if not self.active_runs[user_id]:
                del self.active_runs[user_id]
        logger.debug("run_released", user_id=user_id, run_id=run_id)
