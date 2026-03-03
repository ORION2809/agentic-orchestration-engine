"""Console output helpers using Rich."""

from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.text import Text

from app.models.schemas import CritiqueResult, ValidationReport
from app.models.state import AgentState

console = Console()


def print_banner() -> None:
    banner = Text("Agentic Game-Builder AI", style="bold cyan")
    console.print(Panel(banner, border_style="cyan"))


def print_phase(state: AgentState, message: str = "") -> None:
    icons = {
        AgentState.INIT: "[INIT]",
        AgentState.CLARIFYING: "[CLARIFY]",
        AgentState.PLANNING: "[PLAN]",
        AgentState.BUILDING: "[BUILD]",
        AgentState.CRITIQUING: "[CRITIC]",
        AgentState.VALIDATING: "[VALIDATE]",
        AgentState.DONE: "[DONE]",
        AgentState.FAILED: "[FAILED]",
    }
    icon = icons.get(state, "[>]")
    console.print(f"\n{icon} [bold]{state.value.upper()}[/bold] {message}")


def print_clarification_summary(confidence: float, assumptions: int, questions_asked: int) -> None:
    table = Table(title="Clarification Summary", show_header=False)
    table.add_column("Key", style="cyan")
    table.add_column("Value")
    table.add_row("Confidence", f"{confidence:.0%}")
    table.add_row("Assumptions Made", str(assumptions))
    table.add_row("Questions Asked", str(questions_asked))
    console.print(table)


def print_plan_summary(framework: str, entities: int, mechanics: int, complexity: str) -> None:
    table = Table(title="Plan Summary", show_header=False)
    table.add_column("Key", style="cyan")
    table.add_column("Value")
    table.add_row("Framework", framework)
    table.add_row("Entities", str(entities))
    table.add_row("Mechanics", str(mechanics))
    table.add_row("Complexity", complexity)
    console.print(table)


def print_critique_results(critique: CritiqueResult) -> None:
    console.print(f"\n[bold]Critique Score:[/bold] {critique.compliance_score:.0%}")
    console.print(
        f"[bold]Result:[/bold] {'[green]PASS[/green]' if critique.pass_result else '[red]FAIL[/red]'}"
    )

    if not critique.findings:
        return

    table = Table(title="Findings")
    table.add_column("Severity", style="bold")
    table.add_column("File")
    table.add_column("Description")

    severity_colors = {
        "blocker": "red",
        "major": "yellow",
        "critical": "red",
        "warning": "cyan",
        "minor": "cyan",
        "suggestion": "dim",
    }

    for finding in critique.findings:
        color = severity_colors.get(finding.severity, "white")
        table.add_row(
            f"[{color}]{finding.severity}[/{color}]",
            finding.file or "-",
            finding.description[:80],
        )

    console.print(table)


def print_validation_results(report: ValidationReport) -> None:
    status = "[green]PASSED[/green]" if report.passed else "[red]FAILED[/red]"
    console.print(f"\n[bold]Validation:[/bold] {status}")

    table = Table(title="Validation Checks")
    table.add_column("Check", style="cyan")
    table.add_column("Result")
    table.add_column("Severity")
    table.add_column("Details")

    for check in report.checks:
        result = "[green]OK[/green]" if check.passed else "[red]FAIL[/red]"
        severity_style = {
            "blocker": "red",
            "warning": "yellow",
            "info": "dim",
        }.get(check.severity, "white")

        table.add_row(
            check.name,
            result,
            f"[{severity_style}]{check.severity}[/{severity_style}]",
            check.details[:60] if check.details else "-",
        )

    console.print(table)


def print_build_progress(build_number: int, max_builds: int) -> None:
    console.print(f"\n[bold cyan]Build Attempt[/bold cyan] {build_number}/{max_builds}")


def print_success(output_dir: str | Any, run_id: str) -> None:
    console.print(
        Panel(
            f"[bold green]Game built successfully![/bold green]\n\n"
            f"Output: {output_dir}/{run_id}/latest/\n"
            f"Open index.html in a browser to play.",
            title="Success",
            border_style="green",
        )
    )


def print_failure(reason: str) -> None:
    console.print(
        Panel(
            f"[bold red]Build failed[/bold red]\n\n{reason}",
            title="Failed",
            border_style="red",
        )
    )


def print_metrics(metrics: dict[str, Any]) -> None:
    table = Table(title="Run Metrics", show_header=False)
    table.add_column("Metric", style="cyan")
    table.add_column("Value")

    llm = metrics.get("llm", {})
    table.add_row("LLM Calls", str(llm.get("calls", 0)))
    table.add_row("LLM Errors", str(llm.get("errors", 0)))
    table.add_row("Tokens Used", str(int(llm.get("tokens", 0))))

    builds = metrics.get("builds", {})
    table.add_row("Build Attempts", str(int(builds.get("attempts", 0))))
    table.add_row("Repair Cycles", str(int(builds.get("repairs", 0))))

    console.print(table)


def create_progress() -> Progress:
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        console=console,
    )
