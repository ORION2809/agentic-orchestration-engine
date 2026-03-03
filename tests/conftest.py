"""Shared test fixtures: mock sample data and config."""

from __future__ import annotations

import pytest

from app.config import Config
from app.models.schemas import (
    Assumption,
    ClarificationResult,
    CriticFinding,
    CritiqueResult,
    Entity,
    GamePlan,
    GameRequirements,
    GeneratedGame,
    Mechanic,
    ValidationCheck,
    ValidationReport,
)
from app.models.state import RunContext


@pytest.fixture
def config() -> Config:
    cfg = Config()
    cfg.llm_model = "gpt-4o-mini"
    cfg.llm_fallback = ""
    cfg.batch_mode = True
    cfg.output_dir = "test_outputs"
    cfg.max_retries = 1
    cfg.max_clarification_rounds = 2
    cfg.chaos_mode = False
    return cfg


@pytest.fixture
def sample_clarification() -> ClarificationResult:
    return ClarificationResult(
        questions_asked=["What is the win condition?"],
        user_answers={"What is the win condition?": "reach 100 points"},
        resolved_requirements=GameRequirements(
            genre="arcade",
            core_objective="dodge asteroids",
            controls="keyboard",
            win_condition="reach 100 points",
            lose_condition="collision",
            visual_style="retro",
        ),
        assumptions=[
            Assumption(
                dimension="sound",
                assumed_value="none",
                reason="Default silent mode",
            )
        ],
        confidence_score=0.85,
        rounds_used=1,
    )


@pytest.fixture
def sample_plan() -> GamePlan:
    return GamePlan(
        game_title="Space Dodger",
        game_concept="Dodge falling asteroids",
        framework="vanilla",
        core_mechanics=[
            Mechanic(name="movement", description="Move left and right"),
            Mechanic(name="dodge", description="Avoid asteroids"),
        ],
        entities=[Entity(name="player", type="player", description="Main character")],
        acceptance_checks=["Player responds to arrow keys"],
    )


@pytest.fixture
def sample_game() -> GeneratedGame:
    return GeneratedGame(
        index_html="""<!DOCTYPE html>
<html><head><link rel=\"stylesheet\" href=\"style.css\"></head>
<body><canvas id=\"gameCanvas\" width=\"480\" height=\"640\"></canvas>
<script src=\"game.js\"></script></body></html>""",
        style_css="""body { margin: 0; background: #000; } canvas { border: 1px solid #fff; }""",
        game_js="""const canvas = document.getElementById('gameCanvas');
const ctx = canvas.getContext('2d');
const gameState = { player: { x: 100, y: 100 }, score: 0, gameOver: false };
window.gameState = gameState;
document.addEventListener('keydown', (e) => {
  if (e.key === 'ArrowLeft') gameState.player.x -= 5;
  if (e.key === 'ArrowRight') gameState.player.x += 5;
});
function update() { gameState.score += 1; }
function draw() { ctx.clearRect(0, 0, canvas.width, canvas.height); }
function loop() { update(); draw(); requestAnimationFrame(loop); }
loop();""",
    )


@pytest.fixture
def sample_game_files(sample_game: GeneratedGame) -> dict[str, str]:
    return sample_game.files


@pytest.fixture
def sample_critique() -> CritiqueResult:
    return CritiqueResult(
        findings=[
            CriticFinding(
                severity="warning",
                category="quality",
                description="No restart shortcut",
                affected_file="game.js",
                suggested_fix="Add R to restart",
            )
        ],
        has_critical=False,
        overall_assessment="Looks mostly fine",
        plan_compliance_score=0.85,
        deterministic_checks_run=3,
        llm_checks_run=True,
    )


@pytest.fixture
def sample_validation_report() -> ValidationReport:
    return ValidationReport(
        passed=True,
        checks=[
            ValidationCheck(name="file_existence", passed=True, severity="info"),
            ValidationCheck(name="html_structure", passed=True, severity="info"),
            ValidationCheck(name="js_syntax", passed=True, severity="info"),
        ],
    )


@pytest.fixture
def sample_run_context(
    sample_clarification: ClarificationResult,
    sample_plan: GamePlan,
    sample_game_files: dict[str, str],
) -> RunContext:
    ctx = RunContext(run_id="test-001")
    ctx.original_idea = "a space dodging game"
    ctx.clarification = sample_clarification
    ctx.plan = sample_plan
    ctx.game_files = sample_game_files
    return ctx
