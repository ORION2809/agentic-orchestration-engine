"""Application configuration via environment variables with sensible defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    """Central configuration — all settings from env vars with defaults."""

    # --- LLM ---
    llm_model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "gpt-4o"))
    llm_fallback: str = field(default_factory=lambda: os.getenv("LLM_FALLBACK", ""))
    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    anthropic_api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))

    # --- Per-phase model overrides ---
    phase_model_overrides: dict[str, str] = field(default_factory=lambda: {
        "clarifier": os.getenv("CLARIFIER_MODEL", "gpt-4o-mini"),
        "planner": os.getenv("PLANNER_MODEL", "gpt-4o-mini"),
        "builder": os.getenv("BUILDER_MODEL", "gpt-4o"),
        "critic": os.getenv("CRITIC_MODEL", "gpt-4o-mini"),
    })

    phase_escalation_models: dict[str, str] = field(default_factory=lambda: {
        "clarifier": "gpt-4o",
        "planner": "gpt-4o",
        "builder": "claude-sonnet-4-20250514",
        "critic": "gpt-4o",
    })

    # --- Temperature per phase ---
    phase_temperatures: dict[str, float] = field(default_factory=lambda: {
        "clarifier": 0.3,
        "planner": 0.2,
        "builder": 0.4,
        "critic": 0.1,
    })

    # --- Runtime mode ---
    batch_mode: bool = field(
        default_factory=lambda: os.getenv("BATCH_MODE", "false").lower() == "true"
    )

    # --- Output ---
    output_dir: Path = field(
        default_factory=lambda: Path(os.getenv("OUTPUT_DIR", "outputs"))
    )

    # --- Retry & limits ---
    max_retries: int = 2
    max_clarification_rounds: int = 3
    confidence_threshold: float = 0.75
    max_simplification_rounds: int = 1

    # --- Budget ---
    max_total_tokens: int = field(
        default_factory=lambda: int(os.getenv("MAX_TOTAL_TOKENS", "50000"))
    )

    # --- Concurrency ---
    max_concurrent_runs: int = field(
        default_factory=lambda: int(os.getenv("MAX_CONCURRENT_RUNS", "5"))
    )
    max_runs_per_user: int = field(
        default_factory=lambda: int(os.getenv("MAX_RUNS_PER_USER", "2"))
    )

    # --- Persistence ---
    persistence_backend: str = field(
        default_factory=lambda: os.getenv("PERSISTENCE_BACKEND", "file")
    )
    db_dsn: str = field(default_factory=lambda: os.getenv("DATABASE_DSN", ""))
    s3_bucket: str = field(default_factory=lambda: os.getenv("S3_BUCKET", ""))

    # --- Prompts ---
    prompt_dir: Path = field(
        default_factory=lambda: Path(os.getenv("PROMPT_DIR", "app/prompts"))
    )

    # --- Chaos testing ---
    chaos_mode: bool = field(
        default_factory=lambda: os.getenv("RUN_CHAOS_MODE", "false").lower() == "true"
    )
    chaos_failure_rate: float = field(
        default_factory=lambda: float(os.getenv("CHAOS_FAILURE_RATE", "0.10"))
    )

    # --- Backpressure ---
    backpressure_max_tokens_per_window: int = 500_000
    backpressure_max_cost_per_window_usd: float = 5.00
    backpressure_window_minutes: int = 5

    @property
    def fallback_models(self) -> list[str]:
        """Parse comma-separated fallback model list."""
        return [m.strip() for m in self.llm_fallback.split(",") if m.strip()]

    @property
    def chaos_rate(self) -> float:
        """Compatibility alias for chaos injector."""
        return self.chaos_failure_rate

    @property
    def backpressure_window(self) -> int:
        """Compatibility alias for backpressure constructor (seconds)."""
        return self.backpressure_window_minutes * 60

    @property
    def backpressure_max_tokens(self) -> int:
        """Compatibility alias for backpressure constructor."""
        return self.backpressure_max_tokens_per_window

    @property
    def backpressure_max_cost(self) -> float:
        """Compatibility alias for backpressure constructor."""
        return self.backpressure_max_cost_per_window_usd

    def ensure_output_dir(self) -> None:
        """Create output directory if it doesn't exist."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
