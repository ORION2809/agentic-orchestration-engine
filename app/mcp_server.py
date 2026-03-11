"""MCP Server — exposes the Agentic Game-Builder as a Model Context Protocol service.

This transforms the CLI-based game builder into a protocol-compliant MCP server
that any MCP client (Claude Desktop, VS Code Copilot, Cursor, etc.) can connect to.

Tools:
    build_game      — Generate a playable browser game from a natural language idea
    validate_game   — Run validation checks against existing game files
    resume_build    — Resume a previously interrupted build from checkpoint
    remix_game      — Modify an existing build with new instructions
    list_builds     — List all completed/failed build runs
    get_build_files — Retrieve the generated game files for a specific build

Resources:
    builds://{run_id}/result      — JSON run result for a specific build
    builds://{run_id}/report      — Markdown report for a specific build
    builds://{run_id}/game/{file} — Individual game file (index.html, style.css, game.js)

Prompts:
    game_idea_refiner  — Help users refine vague game ideas into detailed specs
    build_config_guide — Guide users through build configuration options
    analyze_game_code  — Review generated code for a specific build
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import structlog

# Ensure project root is on sys.path for imports
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from mcp.server.fastmcp import Context, FastMCP

from app.config import Config
from app.concurrency.controller import ConcurrencyController
from app.models.state import AgentState
from app.orchestrator import Orchestrator, create_stores

# ── Configure structlog for MCP (JSON output, no rich console) ──────────────
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(20),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

# ── Phase metadata for progress reporting ───────────────────────────────────
# Maps each pipeline state to a (step_number, description) for progress bars.
_PHASE_META: dict[str, tuple[int, str]] = {
    "init": (0, "Initializing"),
    "clarifying": (1, "Clarifying game idea"),
    "planning": (2, "Planning architecture & mechanics"),
    "building": (3, "Generating game code"),
    "critiquing": (4, "Reviewing code for bugs"),
    "validating": (5, "Running validation checks"),
    "done": (6, "Build complete"),
    "failed": (6, "Build failed"),
}
_TOTAL_PHASES = 6

# ── FastMCP Server Instance ─────────────────────────────────────────────────
mcp = FastMCP(
    "game-builder",
    instructions=(
        "Agentic Game-Builder AI — an MCP server that generates playable HTML5 "
        "browser games from natural language descriptions. Use the build_game tool "
        "to create games, validate_game to check existing games, remix_game to modify "
        "existing builds, and list_builds to see previous runs. Game files can be "
        "retrieved via the get_build_files tool or as resources."
    ),
)


def _get_config(**overrides: str) -> Config:
    """Create a Config with optional overrides."""
    config = Config()
    config.batch_mode = True  # MCP always runs non-interactive
    if overrides.get("output_dir"):
        config.output_dir = Path(overrides["output_dir"])
    if overrides.get("model"):
        config.llm_model = overrides["model"]
    return config


def _find_output_base() -> Path:
    """Resolve the base output directory."""
    return Path(os.getenv("OUTPUT_DIR", "outputs"))


def _list_run_ids(base: Path | None = None) -> list[dict]:
    """Scan output directories for completed runs."""
    base = base or _find_output_base()
    runs = []
    if not base.exists():
        return runs

    for d in sorted(base.iterdir(), reverse=True):
        if d.is_dir() and (d / "run_result.json").exists():
            try:
                result = json.loads((d / "run_result.json").read_text(encoding="utf-8"))
                runs.append({
                    "run_id": d.name,
                    "success": result.get("success", False),
                    "status": result.get("status", "unknown"),
                    "tokens": result.get("total_tokens", 0),
                    "cost_usd": result.get("cost_usd", 0.0),
                    "duration_s": result.get("duration_seconds", 0),
                    "output_path": result.get("output_path", ""),
                })
            except Exception:
                runs.append({"run_id": d.name, "status": "corrupt"})
    return runs


def _make_progress_callback(ctx: Context, loop: asyncio.AbstractEventLoop):
    """Create a sync callback that sends async MCP progress notifications.

    The orchestrator runs in a worker thread, so we use loop.call_soon_threadsafe
    to schedule coroutines back onto the event loop.
    """

    def _on_phase_transition(state: AgentState, build_number: int, retry_count: int):
        step, description = _PHASE_META.get(state.value, (0, state.value))
        if retry_count > 0:
            description = f"{description} (retry {retry_count})"

        # Schedule async notifications on the event loop from the worker thread
        asyncio.run_coroutine_threadsafe(
            ctx.report_progress(step, _TOTAL_PHASES, description), loop
        )
        asyncio.run_coroutine_threadsafe(
            ctx.info(f"[{step}/{_TOTAL_PHASES}] {description}"), loop
        )

    return _on_phase_transition


def _format_result(result) -> str:
    """Serialize a RunResult to JSON for MCP responses."""
    return json.dumps({
        "run_id": result.run_id,
        "success": result.success,
        "status": result.status,
        "output_path": result.output_path,
        "total_tokens": result.total_tokens,
        "cost_usd": round(result.cost_usd, 4),
        "duration_seconds": result.duration_seconds,
        "build_number": result.build_number,
        "error": result.error,
        "game_files": list((result.game_files or {}).keys()),
        "hint": (
            "Use get_build_files to retrieve the actual game source code, "
            "or open the output_path/index.html in a browser to play."
        ),
    }, indent=2)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TOOLS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@mcp.tool()
async def build_game(
    idea: str,
    ctx: Context,
    model: str = "gpt-4o",
    output_dir: str = "outputs",
) -> str:
    """Generate a playable HTML5 browser game from a natural language description.

    This runs the full multi-agent pipeline:
    CLARIFY → PLAN → BUILD → CRITIQUE → VALIDATE → DONE

    The pipeline uses LLM agents for each phase with deterministic state machine
    orchestration, AST-based code critique, Playwright behavioral validation,
    and automatic repair cycles. Progress notifications are sent for each phase.

    Args:
        idea: Natural language game description (e.g., "a space shooter with powerups",
              "multiplayer pong", "flappy bird clone with pixel art").
        model: LLM model to use. Default "gpt-4o". Options: gpt-4o, gpt-4o-mini,
               claude-sonnet-4-20250514.
        output_dir: Directory to write game files to. Default "outputs".

    Returns:
        JSON string with run_id, success status, output path, token usage, and cost.
        On success, the game files (index.html, style.css, game.js) are in the output path.
    """
    logger.info("mcp_build_game", idea=idea[:100], model=model)
    await ctx.info(f"Starting build: \"{idea[:80]}\" (model={model})")
    await ctx.report_progress(0, _TOTAL_PHASES, "Initializing pipeline")

    config = _get_config(output_dir=output_dir, model=model)
    controller = ConcurrencyController(config)
    user_id = "mcp_client"

    can_start, reason = controller.can_start_run(user_id)
    if not can_start:
        return json.dumps({"success": False, "error": f"Concurrency limit: {reason}"})

    loop = asyncio.get_running_loop()
    run_id = None
    try:
        controller.register_run(user_id, "pending")
        stores = create_stores(config)
        progress_cb = _make_progress_callback(ctx, loop)
        orchestrator = Orchestrator(config, stores[0], stores[1], progress_callback=progress_cb)
        run_id = orchestrator.context.run_id
        controller.release_run(user_id, "pending")
        controller.register_run(user_id, run_id)

        # Run orchestrator in a thread to avoid blocking the MCP event loop
        result = await loop.run_in_executor(None, orchestrator.run, idea)

        await ctx.report_progress(_TOTAL_PHASES, _TOTAL_PHASES, "Complete")
        await ctx.info(f"Build finished: success={result.success}, tokens={result.total_tokens}")
        return _format_result(result)

    except Exception as exc:
        logger.exception("mcp_build_error", error=str(exc))
        return json.dumps({"success": False, "error": str(exc)})
    finally:
        if run_id:
            controller.release_run(user_id, run_id)


@mcp.tool()
async def validate_game(game_dir: str, ctx: Context) -> str:
    """Run validation checks against existing game files in a directory.

    Performs: file existence, HTML structure, CSS validity, JS syntax (node --check),
    structural heuristics (game loop, input handlers, scoring), and security scanning
    (blocks fetch, eval, WebSocket, cookie access, etc.).

    Args:
        game_dir: Path to directory containing index.html, style.css, and game.js.

    Returns:
        JSON with validation results: overall pass/fail, individual check details,
        and security findings.
    """
    from app.validators.code_validator import run_code_validation_from_dir
    from app.validators.security_scanner import has_blockers, scan_generated_code

    game_path = Path(game_dir)
    if not game_path.exists():
        return json.dumps({"passed": False, "error": f"Directory not found: {game_dir}"})

    await ctx.info(f"Validating game files in {game_dir}")

    files = [f.name for f in game_path.iterdir() if f.is_file()]
    checks = run_code_validation_from_dir(game_path, files)

    file_contents: dict[str, str] = {}
    for f in game_path.iterdir():
        if f.is_file() and f.suffix in (".html", ".css", ".js"):
            file_contents[f.name] = f.read_text(encoding="utf-8")

    security_findings = scan_generated_code(file_contents)
    blocker_failures = [c for c in checks if not c.passed and c.severity == "blocker"]

    await ctx.info(
        f"Validation done: {len(checks)} checks, {len(blocker_failures)} blockers"
    )

    return json.dumps({
        "passed": len(blocker_failures) == 0,
        "total_checks": len(checks),
        "blockers": len(blocker_failures),
        "checks": [
            {
                "name": c.name,
                "passed": c.passed,
                "severity": c.severity,
                "details": c.details,
            }
            for c in checks
        ],
        "security": {
            "has_blockers": has_blockers(security_findings),
            "findings": [
                {
                    "severity": f.severity,
                    "description": f.description,
                    "file": f.file,
                    "line": f.line,
                }
                for f in security_findings
            ],
        },
    }, indent=2)


@mcp.tool()
async def resume_build(run_id: str, ctx: Context, output_dir: str = "outputs") -> str:
    """Resume a previously interrupted or failed build from its checkpoint.

    The orchestrator saves checkpoints on every state transition. If a build
    was interrupted (crash, timeout, API error), it can be resumed from the
    last successful state. Progress notifications are sent for each phase.

    Args:
        run_id: The run ID to resume (from a previous build_game result).
        output_dir: Output directory containing the checkpoint.

    Returns:
        JSON with the resumed run result.
    """
    config = _get_config(output_dir=output_dir)
    await ctx.info(f"Resuming build {run_id}")

    loop = asyncio.get_running_loop()
    try:
        stores = create_stores(config)
        progress_cb = _make_progress_callback(ctx, loop)
        orchestrator = Orchestrator.resume(run_id, config, stores[0], stores[1])
        orchestrator._progress_callback = progress_cb

        result = await loop.run_in_executor(
            None, orchestrator.run, orchestrator.context.original_idea
        )

        await ctx.info(f"Resume finished: success={result.success}")
        return json.dumps({
            "run_id": result.run_id,
            "success": result.success,
            "status": result.status,
            "output_path": result.output_path,
            "total_tokens": result.total_tokens,
            "cost_usd": round(result.cost_usd, 4),
            "duration_seconds": result.duration_seconds,
            "error": result.error,
        }, indent=2)

    except ValueError as exc:
        return json.dumps({"success": False, "error": str(exc)})
    except Exception as exc:
        logger.exception("mcp_resume_error", error=str(exc))
        return json.dumps({"success": False, "error": str(exc)})


@mcp.tool()
async def remix_game(
    run_id: str,
    instructions: str,
    ctx: Context,
    model: str = "gpt-4o",
    output_dir: str = "outputs",
) -> str:
    """Modify an existing game build with new instructions.

    Takes a previously built game and re-runs the pipeline with the original idea
    combined with your modification instructions. The LLM sees the existing code
    and your changes, producing an updated version.

    Examples:
        - "Add a score multiplier power-up that appears every 30 seconds"
        - "Change the visual style to neon cyberpunk with particle effects"
        - "Add a start screen with instructions and a high score display"
        - "Make the player a spaceship sprite instead of a rectangle"
        - "Add sound effects using the Web Audio API"

    Args:
        run_id: The run ID of the build to remix (from list_builds or a previous build_game).
        instructions: What to change. Be specific about additions, removals, or modifications.
        model: LLM model to use. Default "gpt-4o".
        output_dir: Base output directory. Default "outputs".

    Returns:
        JSON with the new run_id, success status, and output path.
        The remixed game is a new build — the original is preserved.
    """
    logger.info("mcp_remix_game", run_id=run_id, instructions=instructions[:100])
    await ctx.info(f"Remixing build {run_id}: \"{instructions[:80]}\"")

    # 1. Load existing game files
    base = Path(output_dir) / run_id / "latest"
    if not base.exists():
        return json.dumps({"success": False, "error": f"No build found at {base}"})

    existing_files: dict[str, str] = {}
    for name in ["index.html", "style.css", "game.js"]:
        path = base / name
        if path.exists():
            existing_files[name] = path.read_text(encoding="utf-8")

    if not existing_files.get("game.js"):
        return json.dumps({"success": False, "error": "Original build has no game.js"})

    # 2. Load original idea from run_result.json
    result_path = Path(output_dir) / run_id / "run_result.json"
    original_idea = "a browser game"
    if result_path.exists():
        try:
            run_data = json.loads(result_path.read_text(encoding="utf-8"))
            # Try to get from context snapshot
            ctx_path = Path(output_dir) / run_id / "context.json"
            if ctx_path.exists():
                ctx_data = json.loads(ctx_path.read_text(encoding="utf-8"))
                original_idea = ctx_data.get("original_idea", original_idea)
        except Exception:
            pass

    # 3. Build a remix prompt that includes existing code + instructions
    remix_idea = (
        f"REMIX REQUEST — Modify an existing game.\n\n"
        f"ORIGINAL IDEA: {original_idea}\n\n"
        f"EXISTING CODE (game.js - {len(existing_files.get('game.js', ''))} chars):\n"
        f"```javascript\n{existing_files.get('game.js', '')}\n```\n\n"
        f"EXISTING HTML (index.html):\n"
        f"```html\n{existing_files.get('index.html', '')}\n```\n\n"
        f"EXISTING CSS (style.css):\n"
        f"```css\n{existing_files.get('style.css', '')}\n```\n\n"
        f"MODIFICATION INSTRUCTIONS: {instructions}\n\n"
        f"Generate the COMPLETE updated game incorporating the requested changes. "
        f"Keep everything that worked well in the original and apply the modifications."
    )

    await ctx.report_progress(0, _TOTAL_PHASES, "Preparing remix")

    # 4. Run the full pipeline with the remix prompt
    config = _get_config(output_dir=output_dir, model=model)
    controller = ConcurrencyController(config)
    user_id = "mcp_client"

    can_start, reason = controller.can_start_run(user_id)
    if not can_start:
        return json.dumps({"success": False, "error": f"Concurrency limit: {reason}"})

    loop = asyncio.get_running_loop()
    new_run_id = None
    try:
        controller.register_run(user_id, "pending")
        stores = create_stores(config)
        progress_cb = _make_progress_callback(ctx, loop)
        orchestrator = Orchestrator(config, stores[0], stores[1], progress_callback=progress_cb)
        new_run_id = orchestrator.context.run_id
        controller.release_run(user_id, "pending")
        controller.register_run(user_id, new_run_id)

        result = await loop.run_in_executor(None, orchestrator.run, remix_idea)

        await ctx.report_progress(_TOTAL_PHASES, _TOTAL_PHASES, "Remix complete")
        await ctx.info(f"Remix finished: success={result.success}, new_run_id={result.run_id}")

        return json.dumps({
            "run_id": result.run_id,
            "original_run_id": run_id,
            "success": result.success,
            "status": result.status,
            "output_path": result.output_path,
            "total_tokens": result.total_tokens,
            "cost_usd": round(result.cost_usd, 4),
            "duration_seconds": result.duration_seconds,
            "build_number": result.build_number,
            "error": result.error,
            "game_files": list((result.game_files or {}).keys()),
            "hint": (
                f"Original build {run_id} is preserved. "
                "Use get_build_files to retrieve the remixed game source code."
            ),
        }, indent=2)

    except Exception as exc:
        logger.exception("mcp_remix_error", error=str(exc))
        return json.dumps({"success": False, "error": str(exc)})
    finally:
        if new_run_id:
            controller.release_run(user_id, new_run_id)


@mcp.tool()
async def list_builds(output_dir: str = "outputs") -> str:
    """List all previous game build runs with their status and metrics.

    Scans the output directory for completed runs and returns summary info
    for each: run_id, success/fail, tokens used, cost, duration.

    Args:
        output_dir: Base output directory to scan. Default "outputs".

    Returns:
        JSON array of build summaries, most recent first.
    """
    base = Path(output_dir)
    runs = _list_run_ids(base)

    if not runs:
        return json.dumps({"builds": [], "message": "No builds found in " + str(base)})

    return json.dumps({"builds": runs, "total": len(runs)}, indent=2)


@mcp.tool()
async def get_build_files(run_id: str, output_dir: str = "outputs") -> str:
    """Retrieve the generated game source files for a specific build.

    Returns the full source code of index.html, style.css, and game.js
    from the latest build iteration.

    Args:
        run_id: The run ID to retrieve files for.
        output_dir: Base output directory. Default "outputs".

    Returns:
        JSON with the game file contents (index_html, style_css, game_js).
    """
    base = Path(output_dir) / run_id / "latest"
    if not base.exists():
        return json.dumps({"error": f"No build found at {base}"})

    files = {}
    for name in ["index.html", "style.css", "game.js"]:
        path = base / name
        if path.exists():
            files[name] = path.read_text(encoding="utf-8")
        else:
            files[name] = None

    return json.dumps({
        "run_id": run_id,
        "path": str(base),
        "files": files,
    }, indent=2)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RESOURCES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@mcp.resource("builds://latest")
def get_latest_build() -> str:
    """Get the most recent build result."""
    base = _find_output_base()
    runs = _list_run_ids(base)
    if not runs:
        return json.dumps({"message": "No builds found"})
    return json.dumps(runs[0], indent=2)


@mcp.resource("builds://{run_id}/result")
def get_build_result(run_id: str) -> str:
    """Get the full JSON run result for a specific build."""
    path = _find_output_base() / run_id / "run_result.json"
    if not path.exists():
        return json.dumps({"error": f"No result found for run_id={run_id}"})
    return path.read_text(encoding="utf-8")


@mcp.resource("builds://{run_id}/report")
def get_build_report(run_id: str) -> str:
    """Get the markdown report for a specific build."""
    path = _find_output_base() / run_id / "report.md"
    if not path.exists():
        return f"No report found for run_id={run_id}"
    return path.read_text(encoding="utf-8")


@mcp.resource("builds://{run_id}/manifest")
def get_build_manifest(run_id: str) -> str:
    """Get the prompt version manifest for a specific build (traceability)."""
    path = _find_output_base() / run_id / "run_manifest.json"
    if not path.exists():
        return json.dumps({"error": f"No manifest found for run_id={run_id}"})
    return path.read_text(encoding="utf-8")


@mcp.resource("builds://{run_id}/game/index.html")
def get_game_html(run_id: str) -> str:
    """Get the generated index.html for a specific build."""
    path = _find_output_base() / run_id / "latest" / "index.html"
    if not path.exists():
        return f"<!-- No index.html found for run_id={run_id} -->"
    return path.read_text(encoding="utf-8")


@mcp.resource("builds://{run_id}/game/style.css")
def get_game_css(run_id: str) -> str:
    """Get the generated style.css for a specific build."""
    path = _find_output_base() / run_id / "latest" / "style.css"
    if not path.exists():
        return f"/* No style.css found for run_id={run_id} */"
    return path.read_text(encoding="utf-8")


@mcp.resource("builds://{run_id}/game/game.js")
def get_game_js(run_id: str) -> str:
    """Get the generated game.js for a specific build."""
    path = _find_output_base() / run_id / "latest" / "game.js"
    if not path.exists():
        return f"// No game.js found for run_id={run_id}"
    return path.read_text(encoding="utf-8")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PROMPTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@mcp.prompt()
def game_idea_refiner(vague_idea: str) -> str:
    """Help refine a vague game idea into a detailed specification.

    Takes a rough game concept and returns a structured prompt that helps
    the user think through: genre, mechanics, controls, win/lose conditions,
    visual style, and difficulty.

    Args:
        vague_idea: The user's initial rough game concept.
    """
    return f"""I want to build a browser game based on this idea: "{vague_idea}"

Help me refine this into a detailed game specification by answering:

1. **Genre**: What genre fits best? (action, puzzle, platformer, shooter, arcade, strategy)
2. **Core Mechanic**: What is the one primary action the player does repeatedly?
3. **Controls**: What inputs? (keyboard arrows, WASD, mouse, touch)
4. **Win Condition**: How does the player "win" or succeed?
5. **Lose Condition**: How does the game end?
6. **Visual Style**: What look? (pixel art, minimalist shapes, neon, retro)
7. **Difficulty**: How does it ramp up over time?
8. **Unique Twist**: What makes this different from a basic version?

Once refined, I can use the build_game tool to generate the actual playable game.
Format the final idea as a single descriptive sentence that captures all the key details."""


@mcp.prompt()
def build_config_guide() -> str:
    """Guide for configuring game build parameters.

    Returns a structured prompt explaining available configuration options
    for the build_game tool.
    """
    return """# Game Builder Configuration Guide

## Build Options

| Parameter    | Default  | Options                                          |
|-------------|----------|--------------------------------------------------|
| `model`     | gpt-4o   | gpt-4o, gpt-4o-mini, claude-sonnet-4-20250514  |
| `output_dir`| outputs  | Any valid directory path                         |

## Model Selection Strategy

- **gpt-4o** (default): Best quality. Uses gpt-4o for planning/building, gpt-4o-mini for clarification/critique.
  Typical cost: $0.03-0.06 per game.
- **gpt-4o-mini**: Cheaper but lower quality code. Good for simple games.
  Typical cost: $0.005-0.01 per game.
- **claude-sonnet-4-20250514**: Used as escalation model when gpt-4o fails. Excellent at code generation.

## What Happens During a Build

The pipeline runs through 6 phases:
1. **CLARIFY** — Analyzes the idea, fills in missing details with smart defaults
2. **PLAN** — Creates a GamePlan: entities, mechanics, controls, acceptance criteria
3. **BUILD** — Generates index.html + style.css + game.js via structured LLM output
4. **CRITIQUE** — AST analysis + LLM review finds bugs and missing features
5. **REPAIR** — If critique finds issues, rebuilds with targeted fixes (up to 2 retries)
6. **VALIDATE** — Playwright headless browser: checks rendering, input response, FPS, security

If the pipeline fails after all retries, a deterministic fallback game is provided.

## Tips for Good Results

- Be specific: "a side-scrolling space shooter where you dodge asteroids and collect power-ups"
- Mention controls: "arrow keys to move, space to shoot"
- Mention visual style: "pixel art" or "neon minimalist"
- Keep scope small: single-screen games work best (avoid "open world" or "multiplayer")

Ready to build? Use: `build_game(idea="your detailed game idea")`"""


@mcp.prompt()
def analyze_game_code(run_id: str) -> str:
    """Prompt to analyze the generated game code for a specific build.

    Args:
        run_id: The build run ID whose code should be analyzed.
    """
    return f"""Please retrieve and analyze the game code from build {run_id}.

Use these tools in order:
1. `get_build_files(run_id="{run_id}")` — Get the source code
2. Review the code for:
   - **Architecture**: Is it well-structured? Clean separation of concerns?
   - **Game Loop**: Is requestAnimationFrame used correctly?
   - **Input Handling**: Are controls responsive? Key-held vs key-press?
   - **Collision Detection**: Is AABB or circle collision implemented correctly?
   - **Progressive Difficulty**: Does the game get harder over time?
   - **Edge Cases**: Bounds checking, restart logic, game-over state
   - **Visual Quality**: Drawing code, colors, text rendering
3. Suggest specific improvements that could make the game more polished.

If the build failed, check the run result for error details and suggest fixes."""


@mcp.prompt()
def remix_workflow(run_id: str) -> str:
    """Interactive workflow prompt for remixing an existing game build.

    Guides the user through reviewing the current game, choosing modifications,
    and executing the remix.

    Args:
        run_id: The build run ID to remix.
    """
    return f"""Let's remix game build **{run_id}**.

## Step 1: Review the current game
First, retrieve the source code:
- `get_build_files(run_id="{run_id}")`

Review what the game does: mechanics, visuals, controls, scoring.

## Step 2: Choose modifications
Here are common remix ideas (pick one or combine several):

**Gameplay:**
- Add power-ups (shield, speed boost, score multiplier)
- Add progressive difficulty levels
- Add a boss enemy or special challenge
- Add combo/chain mechanics

**Visuals:**
- Switch to neon/cyberpunk style with glow effects
- Add particle effects (explosions, trails, sparks)
- Add screen shake on impact
- Use gradients and shadows instead of flat colors

**Audio:**
- Add Web Audio API sound effects (shoot, hit, collect, game-over)
- Add a simple background beat

**UX:**
- Add a start screen with instructions
- Add a pause/resume feature
- Add a high-score display (localStorage)
- Add a restart button on game-over

## Step 3: Execute the remix
Once you've decided, use:
```
remix_game(run_id="{run_id}", instructions="your detailed changes here")
```

Be specific! For example:
"Add a neon visual style with CSS glow effects, screen shake on collision,
a score multiplier power-up that spawns every 20 seconds, and a high score
display using localStorage."

## Step 4: Compare
After the remix completes, use `get_build_files` on the new run_id to compare
the before/after code and verify your changes were applied."""


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ENTRYPOINT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def main():
    """Run the MCP server (stdio transport)."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
