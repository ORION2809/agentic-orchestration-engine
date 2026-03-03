"""Orchestrator: deterministic state machine driving the game-building pipeline."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

import structlog

from app.config import Config
from app.models.errors import BudgetExhaustedError, GameBuilderError, StateViolationError
from app.models.schemas import GeneratedGame, RunResult, ValidationReport
from app.models.state import TRANSITIONS, AgentState, RunContext

# Agents
from app.agents.builder import BuilderAgent
from app.agents.clarifier import ClarifierAgent
from app.agents.critic import CriticAgent
from app.agents.planner import PlannerAgent, score_complexity

# LLM
from app.llm.model_selector import AdaptiveModelSelector
from app.llm.provider import LLMProvider
from app.llm.structured import StructuredLLM
from app.llm.token_tracker import TokenTracker

# Validators
from app.validators.code_validator import run_code_validation
from app.validators.schema_validator import (
    validate_clarification,
    validate_critique,
    validate_game_files,
    validate_plan,
)
from app.validators.security_scanner import has_blockers, scan_generated_code

# Persistence
from app.persistence.base import ArtifactStore, CheckpointStore
from app.persistence.file_store import FileArtifactStore, FileCheckpointStore

# Budget
from app.budget.adaptive_budget import AdaptiveTokenBudget
from app.budget.backpressure import GlobalTokenBackpressure

# Debug and fallback
from app.debug.ast_injector import write_artifacts
from app.fallback.deterministic_generator import generate_fallback

# Observability
from app.observability.metrics import METRICS
from app.observability.model_tracker import ModelQualityTracker

# Chaos
from app.testing.chaos import ChaosInjector

# IO
from app.io import console as con
from app.io.artifacts import write_context_snapshot, write_markdown_report, write_run_result

logger = structlog.get_logger()


def create_stores(config: Config) -> tuple[CheckpointStore, ArtifactStore]:
    """Create persistence stores based on configured backend."""
    output_dir = Path(config.output_dir)
    if config.persistence_backend == "file":
        return FileCheckpointStore(output_dir), FileArtifactStore(output_dir)
    return FileCheckpointStore(output_dir), FileArtifactStore(output_dir)


class Orchestrator:
    """Deterministic state-machine orchestrator for the full pipeline."""

    def __init__(
        self,
        config: Config,
        checkpoint_store: CheckpointStore | None = None,
        artifact_store: ArtifactStore | None = None,
    ) -> None:
        self.config = config
        self.state = AgentState.INIT
        self.context = RunContext()
        self.retry_count = 0
        self.max_retries = config.max_retries
        self.build_number = 0

        # Persistence
        if checkpoint_store and artifact_store:
            self.checkpoint_store = checkpoint_store
            self.artifact_store = artifact_store
        else:
            self.checkpoint_store, self.artifact_store = create_stores(config)

        # LLM infrastructure
        self.token_tracker = TokenTracker()
        self.model_selector = AdaptiveModelSelector(
            overrides=config.phase_model_overrides,
            escalation=config.phase_escalation_models,
        )
        self.llm = LLMProvider(
            model=config.llm_model,
            fallback_models=config.fallback_models,
            tracker=self.token_tracker,
            model_selector=self.model_selector,
        )
        self.structured_llm = StructuredLLM(
            model=config.llm_model,
            tracker=self.token_tracker,
            model_selector=self.model_selector,
        )

        # Agents
        self.clarifier = ClarifierAgent(config, self.llm, self.structured_llm)
        self.planner = PlannerAgent(config, self.llm, self.structured_llm)
        self.builder = BuilderAgent(config, self.llm, self.structured_llm)
        self.critic = CriticAgent(config, self.llm, self.structured_llm)

        # Budget
        self.budget: AdaptiveTokenBudget | None = None
        self.backpressure = GlobalTokenBackpressure(
            window_seconds=config.backpressure_window,
            max_tokens=config.backpressure_max_tokens,
            max_cost=config.backpressure_max_cost,
        )

        # Observability / chaos
        self.model_tracker = ModelQualityTracker()
        self.chaos = ChaosInjector(config) if config.chaos_mode else None

        # Timing
        self._phase_start: float = 0.0
        self._run_start: float = 0.0

    def transition(self, new_state: AgentState) -> None:
        """Transition to a new state with transition-graph guard enforcement."""
        allowed = TRANSITIONS.get(self.state, [])
        if new_state not in allowed:
            raise StateViolationError(
                f"Illegal transition: {self.state.value} -> {new_state.value}",
                current_state=self.state.value,
                attempted_state=new_state.value,
            )

        old_state = self.state
        self.state = new_state
        elapsed = time.time() - self._phase_start if self._phase_start else 0
        self._phase_start = time.time()

        logger.info(
            "state_transition",
            old=old_state.value,
            new=new_state.value,
            elapsed_s=round(elapsed, 2),
            retry_count=self.retry_count,
            build_number=self.build_number,
        )

        METRICS.phase_duration.observe(elapsed, phase=old_state.value)
        con.print_phase(new_state)
        self._checkpoint()

    def _checkpoint(self) -> None:
        """Persist current state and context for crash recovery."""
        snapshot = {
            "run_id": self.context.run_id,
            "state": self.state.value,
            "retry_count": self.retry_count,
            "build_number": self.build_number,
            "context": self.context.to_dict(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "token_summary": self.token_tracker.get_summary(),
        }
        try:
            self.checkpoint_store.save(self.context.run_id, snapshot)
        except Exception as exc:  # pragma: no cover
            logger.warning("checkpoint_failed", error=str(exc))

    def run(self, idea: str) -> RunResult:
        """Execute the full game-building pipeline from user idea to output."""
        self._run_start = time.time()
        self._phase_start = time.time()
        self.context.original_idea = idea

        METRICS.runs_started.inc()
        METRICS.active_runs.inc()
        con.print_banner()

        # Global backpressure guard
        estimated_tokens = 30_000
        can_accept, reason = self.backpressure.can_accept_new_run(estimated_tokens)
        if not can_accept:
            METRICS.active_runs.dec()
            logger.warning("backpressure_rejected", reason=reason)
            return RunResult(
                run_id=self.context.run_id,
                success=False,
                status="rejected",
                error=reason,
                reason=reason,
            )

        # If resuming from a checkpoint, skip the initial transition
        if self.state == AgentState.INIT:
            self.transition(AgentState.CLARIFYING)

        while self.state not in (AgentState.DONE, AgentState.FAILED):
            try:
                if self.state == AgentState.CLARIFYING:
                    self._phase_clarify()
                elif self.state == AgentState.PLANNING:
                    self._phase_plan()
                elif self.state == AgentState.BUILDING:
                    self._phase_build()
                elif self.state == AgentState.CRITIQUING:
                    self._phase_critique()
                elif self.state == AgentState.VALIDATING:
                    self._phase_validate()
            except BudgetExhaustedError as exc:
                logger.error("budget_exhausted", error=str(exc))
                self.transition(AgentState.FAILED)
            except GameBuilderError as exc:
                logger.error(
                    "phase_error",
                    phase=self.state.value,
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
                self.transition(AgentState.FAILED)
            except Exception as exc:  # pragma: no cover
                logger.exception("unexpected_error", phase=self.state.value, error=str(exc))
                self.transition(AgentState.FAILED)

        return self._finalize()

    def _phase_clarify(self) -> None:
        if self.budget and not self.budget.can_afford("clarifier"):
            raise BudgetExhaustedError("Clarifier token budget exhausted")

        before_tokens = self.token_tracker.total_tokens
        result = self.clarifier.run(self.context)
        after_tokens = self.token_tracker.total_tokens

        if self.budget:
            self.budget.record("clarifier", max(0, after_tokens - before_tokens))

        self.context.clarification = result

        check = validate_clarification(result)
        if not check.passed:
            logger.warning("clarification_schema_errors", details=check.details)

        con.print_clarification_summary(
            confidence=result.confidence_score,
            assumptions=len(result.assumptions),
            questions_asked=len(result.questions_asked),
        )
        self.transition(AgentState.PLANNING)

    def _phase_plan(self) -> None:
        if self.budget and not self.budget.can_afford("planner"):
            raise BudgetExhaustedError("Planner token budget exhausted")

        before_tokens = self.token_tracker.total_tokens
        result = self.planner.run(self.context)
        after_tokens = self.token_tracker.total_tokens

        if self.budget:
            self.budget.record("planner", max(0, after_tokens - before_tokens))

        self.context.plan = result

        check = validate_plan(result)
        if not check.passed:
            raise GameBuilderError(f"Planner produced invalid plan: {check.details}")

        assessment = score_complexity(result)
        self.context.complexity_tier = assessment.tier
        self.budget = AdaptiveTokenBudget.from_complexity(assessment)

        # Bounded simplification loop: max one round
        if assessment.tier == "complex" and self.config.max_simplification_rounds > 0:
            logger.info("simplifying_plan", score=assessment.score)
            METRICS.simplifications.inc()
            result = self.planner.simplify(result, self.context)
            self.context.plan = result

        con.print_plan_summary(
            framework=result.framework,
            entities=len(result.entities),
            mechanics=len(result.core_mechanics),
            complexity=self.context.complexity_tier,
        )
        self.transition(AgentState.BUILDING)

    def _phase_build(self) -> None:
        self.build_number += 1
        self.context.build_number = self.build_number
        METRICS.build_attempts.inc()

        if self.budget and not self.budget.can_afford("builder"):
            raise BudgetExhaustedError("Builder token budget exhausted")

        if self.chaos:
            self.chaos.maybe_inject()

        if self.retry_count > 0:
            METRICS.escalations.inc()

        before_tokens = self.token_tracker.total_tokens
        result = self.builder.run(self.context)
        after_tokens = self.token_tracker.total_tokens

        if self.budget:
            self.budget.record("builder", max(0, after_tokens - before_tokens))

        check = validate_game_files(result)
        if not check.passed:
            self.context.repair_instructions = [
                f"[SCHEMA] {check.name}: {check.details}",
            ]
            if self.retry_count < self.max_retries:
                self.retry_count += 1
                METRICS.repair_cycles.inc()
                self.transition(AgentState.BUILDING)
                return
            raise GameBuilderError(f"Builder produced invalid game files: {check.details}")

        self.context.game_files = result.files

        security_findings = scan_generated_code(self.context.game_files)
        if has_blockers(security_findings):
            logger.warning(
                "security_blockers_found",
                count=sum(1 for f in security_findings if f.severity == "blocker"),
            )
            self.context.repair_instructions = [
                f"[SECURITY] {f.description} in {f.file}:{f.line or '?'}"
                for f in security_findings
                if f.severity == "blocker"
            ]
            if self.retry_count < self.max_retries:
                self.retry_count += 1
                METRICS.repair_cycles.inc()
                self.transition(AgentState.BUILDING)
                return
            raise GameBuilderError("Security blockers found in generated output")

        output_dir = Path(self.config.output_dir)
        write_artifacts(
            game_files=self.context.game_files,
            output_dir=output_dir,
            build_number=self.build_number,
            run_id=self.context.run_id,
        )

        self.transition(AgentState.CRITIQUING)

    def _phase_critique(self) -> None:
        if self.budget and not self.budget.can_afford("critic"):
            raise BudgetExhaustedError("Critic token budget exhausted")

        before_tokens = self.token_tracker.total_tokens
        critique = self.critic.run(self.context)
        after_tokens = self.token_tracker.total_tokens

        if self.budget:
            self.budget.record("critic", max(0, after_tokens - before_tokens))

        self.context.critique = critique

        check = validate_critique(critique)
        if not check.passed:
            logger.warning("critique_schema_warning", details=check.details)

        con.print_critique_results(critique)

        critical_findings = [
            f
            for f in critique.findings
            if f.severity in ("blocker", "major", "critical")
        ]
        if critical_findings and self.retry_count < self.max_retries:
            self.context.repair_instructions = [
                f"[{f.severity.upper()}] {f.description}"
                + (f" in {f.file}" if f.file else "")
                for f in critical_findings
            ]
            self.retry_count += 1
            METRICS.repair_cycles.inc()
            # Record failure for quality tracking
            self.model_tracker.record_failure(
                model=self.model_selector.get_model("builder"),
                phase="builder",
            )
            logger.info(
                "critique_triggered_repair",
                critical_count=len(critical_findings),
                retry=self.retry_count,
            )
            self.transition(AgentState.BUILDING)
            return

        self.transition(AgentState.VALIDATING)

    def _phase_validate(self) -> None:
        game_files = self.context.game_files or {}
        game = GeneratedGame.from_file_map(game_files)

        code_checks = run_code_validation(game)
        all_checks = list(code_checks)

        # Optional runtime validation (Playwright)
        try:
            from app.validators.runtime_validator import run_runtime_validation

            plan = self.context.plan
            if isinstance(plan, dict):
                from app.models.schemas import GamePlan

                plan = GamePlan(**plan)

            if plan is not None:
                debug_dir = (
                    Path(self.config.output_dir)
                    / self.context.run_id
                    / f"build_{self.build_number}"
                    / "debug"
                )
                all_checks.extend(run_runtime_validation(debug_dir, plan))
        except Exception as exc:
            logger.warning("runtime_validation_skipped", error=str(exc))

        # Optional playability checks (Playwright behavioral)
        try:
            from app.validators.playability_checker import run_playability_checks

            plan = self.context.plan
            if isinstance(plan, dict):
                from app.models.schemas import GamePlan

                plan = GamePlan(**plan)

            if plan is not None:
                game_dir = (
                    Path(self.config.output_dir)
                    / self.context.run_id
                    / f"build_{self.build_number}"
                    / "game"
                )
                all_checks.extend(run_playability_checks(game_dir, plan))
        except Exception as exc:
            logger.warning("playability_checks_skipped", error=str(exc))

        blocker_failures = [c for c in all_checks if not c.passed and c.severity == "blocker"]
        report = ValidationReport(passed=len(blocker_failures) == 0, checks=all_checks)
        self.context.validation_report = report

        METRICS.validation_checks.inc(amount=len(all_checks))
        METRICS.validation_blockers.inc(amount=len(blocker_failures))
        con.print_validation_results(report)

        if report.passed:
            # Record success for quality tracking
            self.model_tracker.record_success(
                model=self.model_selector.get_model("builder"),
                phase="builder",
            )
            self.transition(AgentState.DONE)
            return

        if self.retry_count < self.max_retries:
            self.context.validation_errors = [
                f"[{c.severity.upper()}] {c.name}: {c.details}"
                for c in all_checks
                if not c.passed and c.severity in ("blocker", "warning")
            ]
            self.retry_count += 1
            METRICS.repair_cycles.inc()
            self.model_selector.record_validation_failure("builder")
            self.model_tracker.record_failure(
                model=self.model_selector.get_model("builder"),
                phase="builder",
            )
            logger.info(
                "validation_triggered_repair",
                blockers=len(blocker_failures),
                retry=self.retry_count,
            )
            self.transition(AgentState.BUILDING)
            return

        logger.error("max_retries_exhausted", retries=self.retry_count)
        self.transition(AgentState.FAILED)

    def _finalize(self) -> RunResult:
        """Build and persist final run result."""
        METRICS.active_runs.dec()
        elapsed = time.time() - self._run_start

        success = self.state == AgentState.DONE
        if success:
            METRICS.runs_completed.inc()
        else:
            METRICS.runs_failed.inc()

        game_files = self.context.game_files or {}
        status = "done" if success else "failed"

        if not success and not game_files:
            logger.info("using_deterministic_fallback")
            METRICS.runs_fallback.inc()
            game_files = generate_fallback(self.context.original_idea)
            self.context.game_files = game_files
            write_artifacts(
                game_files=game_files,
                output_dir=Path(self.config.output_dir),
                build_number=self.build_number + 1,
                run_id=self.context.run_id,
            )
            status = "degraded_fallback"

        output_path = ""
        if game_files:
            output_path = str(Path(self.config.output_dir) / self.context.run_id / "latest")

        cost = self.token_tracker.cost_estimate_usd()
        effective_success = success or status == "degraded_fallback"
        result = RunResult(
            run_id=self.context.run_id,
            success=effective_success,
            status=status,
            error=None if effective_success else "Pipeline failed after max retries",
            reason=(
                "Generated via deterministic fallback due upstream model failures"
                if status == "degraded_fallback"
                else ("" if effective_success else "Pipeline did not satisfy quality gates")
            ),
            output_path=output_path,
            output_dir=output_path,
            game_files=game_files if game_files else None,
            build_number=self.build_number,
            total_tokens=int(self.token_tracker.total_tokens),
            cost_usd=cost,
            estimated_cost_usd=cost,
            duration_seconds=round(elapsed, 2),
            elapsed_seconds=round(elapsed, 2),
        )

        # Record final usage into global backpressure window.
        self.backpressure.record_usage(result.total_tokens, result.cost_usd)

        try:
            output_dir = Path(self.config.output_dir)
            write_run_result(result, output_dir)
            write_context_snapshot(self.context, output_dir)
            write_markdown_report(self.context, output_dir, metrics=METRICS.get_summary())

            # Write run_manifest.json with prompt version hashes (§14a)
            try:
                from app.prompts.versioning import get_manifest as get_prompt_manifest
                import json as _json

                prompt_manifest = get_prompt_manifest(self.config.prompt_dir)
                prompt_versions = {
                    f"{name}.md": v.sha256 for name, v in prompt_manifest.items()
                }
                manifest = {
                    "run_id": self.context.run_id,
                    "model": self.config.llm_model,
                    "prompt_versions": prompt_versions,
                    "token_summary": self.token_tracker.get_summary(),
                    "success": result.success,
                    "status": result.status,
                    "build_number": self.build_number,
                }
                manifest_path = output_dir / self.context.run_id / "run_manifest.json"
                manifest_path.parent.mkdir(parents=True, exist_ok=True)
                manifest_path.write_text(
                    _json.dumps(manifest, indent=2, default=str),
                    encoding="utf-8",
                )
            except Exception as exc:
                logger.warning("manifest_write_failed", error=str(exc))

            # Save game files via artifact store (§I2)
            if game_files:
                try:
                    self.artifact_store.save_game(
                        self.context.run_id, game_files, self.build_number
                    )
                except Exception as exc:
                    logger.warning("artifact_store_save_failed", error=str(exc))
        except Exception as exc:  # pragma: no cover
            logger.warning("output_write_failed", error=str(exc))

        if result.success:
            con.print_success(self.config.output_dir, self.context.run_id)
        else:
            con.print_failure(result.error or "Unknown error")

        con.print_metrics(METRICS.get_summary())
        logger.info(
            "run_complete",
            run_id=self.context.run_id,
            success=result.success,
            status=result.status,
            builds=self.build_number,
            retries=self.retry_count,
            tokens=result.total_tokens,
            cost_usd=round(result.cost_usd, 4),
            duration_s=round(elapsed, 2),
        )
        return result

    @classmethod
    def resume(
        cls,
        run_id: str,
        config: Config,
        checkpoint_store: CheckpointStore | None = None,
        artifact_store: ArtifactStore | None = None,
    ) -> Orchestrator:
        """Resume a crashed run from its checkpoint snapshot."""
        stores = (checkpoint_store, artifact_store)
        if not stores[0] or not stores[1]:
            stores = create_stores(config)

        snapshot = stores[0].load(run_id)
        if not snapshot:
            raise ValueError(f"No checkpoint found for run_id={run_id}")

        instance = cls(config, stores[0], stores[1])
        instance.state = AgentState(snapshot["state"])
        instance.retry_count = snapshot.get("retry_count", 0)
        instance.build_number = snapshot.get("build_number", 0)
        instance.context = RunContext.from_dict(snapshot["context"])

        logger.info(
            "run_resumed",
            run_id=run_id,
            state=instance.state.value,
            retry_count=instance.retry_count,
            build_number=instance.build_number,
        )
        return instance
