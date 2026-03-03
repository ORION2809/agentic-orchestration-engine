"""CLI entrypoint for the Agentic Game-Builder AI."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import structlog
import typer

from app.config import Config
from app.concurrency.controller import ConcurrencyController
from app.orchestrator import Orchestrator, create_stores

# Configure structlog
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(20),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

app = typer.Typer(
    name="game-builder",
    help="Generate playable HTML5 games from natural language ideas.",
    add_completion=False,
)


@app.command()
def build(
    idea: str = typer.Option(
        ...,
        "--idea",
        "-i",
        help="Game idea in natural language (e.g., 'a space shooter with powerups')",
    ),
    batch: bool = typer.Option(
        False,
        "--batch/--interactive",
        help="Batch mode (no user prompts) or interactive clarification",
    ),
    output: str = typer.Option(
        "outputs",
        "--output",
        "-o",
        help="Output directory for generated game files",
    ),
    model: Optional[str] = typer.Option(
        None,
        "--model",
        "-m",
        help="Override LLM model (e.g., gpt-4o, claude-sonnet-4-20250514)",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable verbose/debug logging",
    ),
) -> None:
    """Generate a playable browser game from a natural language idea."""
    if verbose:
        structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(10))

    config = Config()
    # --batch flag OR BATCH_MODE env var (critical for Docker where env=true but CLI default=False)
    config.batch_mode = batch or config.batch_mode
    config.output_dir = Path(output)

    if model:
        config.llm_model = model

    logger.info(
        "build_started",
        idea=idea[:100],
        model=config.llm_model,
        batch=batch,
        output=output,
    )

    controller = ConcurrencyController(config)
    user_id = "cli_user"
    can_start, reason = controller.can_start_run(user_id)
    if not can_start:
        typer.echo(f"Cannot start run: {reason}", err=True)
        raise typer.Exit(code=1)

    run_id = None
    try:
        controller.register_run(user_id, "pending")
        stores = create_stores(config)
        orchestrator = Orchestrator(config, stores[0], stores[1])
        run_id = orchestrator.context.run_id
        controller.release_run(user_id, "pending")
        controller.register_run(user_id, run_id)

        result = orchestrator.run(idea)

        if result.success:
            if result.status == "degraded_fallback":
                typer.echo("\nGame built using degraded fallback mode.")
            typer.echo(f"Game built: {result.output_path}")
            typer.echo("Open index.html in a browser to play.")
            raise typer.Exit(code=0)

        typer.echo(f"\nBuild failed: {result.error}", err=True)
        if result.output_path:
            typer.echo(f"Fallback game saved to: {result.output_path}")
        raise typer.Exit(code=1)

    except typer.Exit:
        raise
    except Exception as exc:
        logger.exception("fatal_error", error=str(exc))
        typer.echo(f"\nFatal error: {exc}", err=True)
        raise typer.Exit(code=2)
    finally:
        if run_id:
            controller.release_run(user_id, run_id)


@app.command()
def resume(
    run_id: str = typer.Argument(..., help="Run ID to resume from checkpoint"),
    output: str = typer.Option(
        "outputs",
        "--output",
        "-o",
        help="Output directory (must contain the checkpoint)",
    ),
) -> None:
    """Resume a previously interrupted run from its last checkpoint."""
    config = Config()
    config.output_dir = Path(output)

    logger.info("resuming_run", run_id=run_id)

    try:
        stores = create_stores(config)
        orchestrator = Orchestrator.resume(run_id, config, stores[0], stores[1])
        result = orchestrator.run(orchestrator.context.original_idea)

        if result.success:
            if result.status == "degraded_fallback":
                typer.echo("\nResumed with degraded fallback output.")
            typer.echo(f"Resumed and completed: {result.output_path}")
            raise typer.Exit(code=0)

        typer.echo(f"\nResumed but failed: {result.error}", err=True)
        raise typer.Exit(code=1)

    except ValueError as exc:
        typer.echo(f"Cannot resume: {exc}", err=True)
        raise typer.Exit(code=1)
    except typer.Exit:
        raise
    except Exception as exc:
        logger.exception("resume_error", error=str(exc))
        typer.echo(f"\nError: {exc}", err=True)
        raise typer.Exit(code=2)


@app.command()
def validate(
    game_dir: str = typer.Argument(
        ...,
        help="Path to a directory containing index.html, style.css, and game.js",
    ),
) -> None:
    """Run validation checks against an existing game directory."""
    from app.io.console import print_validation_results
    from app.models.schemas import ValidationReport
    from app.validators.code_validator import run_code_validation_from_dir
    from app.validators.security_scanner import format_security_report, scan_generated_code

    game_path = Path(game_dir)
    if not game_path.exists():
        typer.echo(f"Directory not found: {game_dir}", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Validating {game_dir}...")

    files = [f.name for f in game_path.iterdir() if f.is_file()]
    checks = run_code_validation_from_dir(game_path, files)

    file_contents: dict[str, str] = {}
    for f in game_path.iterdir():
        if f.is_file() and f.suffix in (".html", ".css", ".js"):
            file_contents[f.name] = f.read_text(encoding="utf-8")

    findings = scan_generated_code(file_contents)
    typer.echo(format_security_report(findings))

    blocker_failures = [c for c in checks if not c.passed and c.severity == "blocker"]
    report = ValidationReport(passed=len(blocker_failures) == 0, checks=checks)
    print_validation_results(report)

    raise typer.Exit(code=0 if report.passed else 1)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
