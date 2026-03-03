"""All Pydantic models used as typed contracts between pipeline phases."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class Assumption(BaseModel):
    """An explicit assumption made when clarification data is missing."""

    dimension: str
    assumed_value: str
    reason: str


class GameRequirements(BaseModel):
    """Structured requirements extracted from user intent + defaults."""

    genre: str = ""
    core_objective: str = ""
    controls: str = "keyboard arrows + space"
    win_condition: str = ""
    lose_condition: str = ""
    difficulty: str = "medium, progressive"
    visual_style: str = "minimalist CSS shapes"
    framework_preference: str = "vanilla"
    sound: str = "none"
    num_players: str = "single player"


class ClarificationResult(BaseModel):
    """Output contract for the clarifier phase."""

    questions_asked: list[str] = Field(default_factory=list)
    user_answers: dict[str, str] = Field(default_factory=dict)
    resolved_requirements: GameRequirements = Field(default_factory=GameRequirements)
    assumptions: list[Assumption] = Field(default_factory=list)
    confidence_score: float = Field(ge=0.0, le=1.0, default=0.0)
    rounds_used: int = 0

    @property
    def confidence(self) -> float:
        """Backwards-compatible accessor used by reporting and console output."""
        return self.confidence_score


class Mechanic(BaseModel):
    """A single game mechanic."""

    name: str
    description: str


class ControlScheme(BaseModel):
    """Input mapping for the generated game."""

    key_mappings: dict[str, str] = Field(
        default_factory=lambda: {
            "ArrowLeft": "move_left",
            "ArrowRight": "move_right",
            "ArrowUp": "move_up",
            "ArrowDown": "move_down",
            "Space": "action",
        }
    )
    mouse_used: bool = False
    description: str = ""


class GameLoopSpec(BaseModel):
    """Description of the core game loop."""

    init_description: str = ""
    update_description: str = ""
    render_description: str = ""
    target_fps: int = 60


class Entity(BaseModel):
    """A game entity (player, enemy, collectible, obstacle, UI element)."""

    name: str
    type: str = "generic"
    description: str = ""
    properties: dict[str, Any] = Field(default_factory=dict)


class GameStateModel(BaseModel):
    """State model for the generated game."""

    states: list[str] = Field(
        default_factory=lambda: ["menu", "playing", "paused", "game_over"]
    )
    initial_state: str = "menu"
    transitions: list[str] = Field(default_factory=list)


class ScoringSpec(BaseModel):
    """Scoring system specification."""

    method: str = "increment on event"
    display: str = "top-left HUD text"
    events: list[str] = Field(default_factory=list)


class GamePlan(BaseModel):
    """Planner output contract."""

    game_title: str = ""
    game_concept: str = ""
    framework: Literal["vanilla", "phaser"] = "vanilla"
    framework_rationale: str = ""
    core_mechanics: list[Mechanic] = Field(default_factory=list)
    controls: ControlScheme = Field(default_factory=ControlScheme)
    game_loop: GameLoopSpec = Field(default_factory=GameLoopSpec)
    entities: list[Entity] = Field(default_factory=list)
    entity_relationships: list[str] = Field(default_factory=list)
    state_model: GameStateModel = Field(default_factory=GameStateModel)
    scoring: ScoringSpec = Field(default_factory=ScoringSpec)
    win_condition: str = ""
    lose_condition: str = ""
    difficulty_curve: str = ""
    canvas_width: int = 800
    canvas_height: int = 600
    visual_style: str = "geometric shapes"
    color_palette: list[str] = Field(default_factory=list)
    asset_strategy: Literal[
        "css_shapes", "canvas_draw", "emoji", "external_sprites"
    ] = "canvas_draw"
    html_spec: str = ""
    css_spec: str = ""
    js_architecture: str = ""
    acceptance_checks: list[str] = Field(default_factory=list)


class GeneratedGame(BaseModel):
    """Builder output contract (the three final files)."""

    index_html: str = Field(min_length=50)
    style_css: str = Field(min_length=20)
    game_js: str = Field(min_length=200)

    @property
    def files(self) -> dict[str, str]:
        """Filename-to-content map used by validators, scanners, and writers."""
        return {
            "index.html": self.index_html,
            "style.css": self.style_css,
            "game.js": self.game_js,
        }

    @classmethod
    def from_file_map(cls, files: dict[str, str]) -> GeneratedGame:
        """Build model from filename map."""
        return cls(
            index_html=files.get("index.html", ""),
            style_css=files.get("style.css", ""),
            game_js=files.get("game.js", ""),
        )


class CriticFinding(BaseModel):
    """A single issue found by deterministic/LLM critique."""

    severity: Literal[
        "blocker",
        "major",
        "critical",
        "warning",
        "minor",
        "suggestion",
    ] = "warning"
    category: str = "quality"
    description: str
    affected_file: str = "game.js"
    suggested_fix: str = ""
    source: Literal["deterministic", "llm"] = "deterministic"

    @property
    def file(self) -> str:
        """Backwards-compatible file accessor."""
        return self.affected_file

    @property
    def line(self) -> int | None:
        """Unified interface with security findings."""
        return None


class CritiqueResult(BaseModel):
    """Combined hybrid critic output."""

    findings: list[CriticFinding] = Field(default_factory=list)
    has_critical: bool = False
    overall_assessment: str = ""
    plan_compliance_score: float = Field(ge=0.0, le=1.0, default=1.0)
    deterministic_checks_run: int = 0
    llm_checks_run: bool = False

    @property
    def compliance_score(self) -> float:
        """Backwards-compatible alias used by legacy report formatting."""
        return self.plan_compliance_score

    @property
    def pass_result(self) -> bool:
        """Passes when no blocking/critical findings exist."""
        return not any(
            f.severity in ("blocker", "major", "critical")
            for f in self.findings
        )


class ValidationCheck(BaseModel):
    """A single validation check result."""

    name: str
    passed: bool
    details: str = ""
    severity: Literal["blocker", "warning", "info"] = "info"


class ValidationReport(BaseModel):
    """Aggregated validation report."""

    checks: list[ValidationCheck] = Field(default_factory=list)
    passed: bool = True
    screenshot_path: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now())


class ComplexityAssessment(BaseModel):
    """Result of plan complexity scoring."""

    score: int = 0
    tier: Literal["simple", "moderate", "complex"] = "moderate"
    factors: list[str] = Field(default_factory=list)
    estimated_builder_tokens: int = 10_000


class SecurityFinding(BaseModel):
    """A security issue found by static analysis."""

    file: str
    line: int | None = None
    pattern: str
    severity: Literal["blocker", "warning", "info"] = "blocker"
    description: str = ""
    snippet: str = ""
    occurrences: int = 1
    action: Literal["auto_remove", "block_output", "log_only"] = "block_output"


class RunResult(BaseModel):
    """Final result of an orchestrator run."""

    run_id: str
    success: bool = True
    status: Literal["done", "failed", "degraded_fallback", "rejected"] = "done"
    error: str | None = None
    reason: str = ""
    output_path: str = ""
    output_dir: str = ""
    game_files: dict[str, str] | None = None
    total_tokens: int = 0
    cost_usd: float = 0.0
    estimated_cost_usd: float = 0.0
    duration_seconds: float = 0.0
    elapsed_seconds: float = 0.0
    build_number: int = 0
    phases: dict[str, Any] = Field(default_factory=dict)
