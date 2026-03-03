"""Agent state machine: states, transitions, and run context."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


class AgentState(str, Enum):
    """All states in the orchestrator state machine."""

    INIT = "init"
    CLARIFYING = "clarifying"
    PLANNING = "planning"
    BUILDING = "building"
    CRITIQUING = "critiquing"
    VALIDATING = "validating"
    DONE = "done"
    FAILED = "failed"


# Encoded transition rules. The orchestrator enforces these.
TRANSITIONS: dict[AgentState, list[AgentState]] = {
    AgentState.INIT: [AgentState.CLARIFYING],
    AgentState.CLARIFYING: [AgentState.PLANNING, AgentState.FAILED],
    AgentState.PLANNING: [AgentState.BUILDING, AgentState.FAILED],
    AgentState.BUILDING: [AgentState.CRITIQUING, AgentState.FAILED],
    AgentState.CRITIQUING: [AgentState.VALIDATING, AgentState.BUILDING],
    AgentState.VALIDATING: [AgentState.DONE, AgentState.BUILDING, AgentState.FAILED],
    AgentState.DONE: [],
    AgentState.FAILED: [],
}


@dataclass
class RunContext:
    """Mutable run state persisted across phases and checkpoints."""

    run_id: str = field(default_factory=lambda: str(uuid4())[:8])
    original_idea: str = ""
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # Phase outputs
    clarification: Any | None = None
    plan: Any | None = None
    game_files: dict[str, str] | None = None
    critique: Any | None = None
    validation_report: Any | None = None

    # Repair context for rebuild loops
    repair_instructions: list[str] | None = None
    validation_errors: list[str] | None = None

    # Metadata
    complexity_tier: str = "moderate"
    build_number: int = 0

    def _serialize(self, value: Any) -> Any:
        """Convert models and nested values into JSON-safe data."""
        if value is None:
            return None
        if hasattr(value, "model_dump"):
            return value.model_dump()
        if isinstance(value, dict):
            return {k: self._serialize(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._serialize(v) for v in value]
        return value

    def to_dict(self) -> dict[str, Any]:
        """Serialize context into a JSON-safe dictionary."""
        return {
            "run_id": self.run_id,
            "original_idea": self.original_idea,
            "started_at": self.started_at,
            "clarification": self._serialize(self.clarification),
            "plan": self._serialize(self.plan),
            "game_files": self._serialize(self.game_files),
            "critique": self._serialize(self.critique),
            "validation_report": self._serialize(self.validation_report),
            "repair_instructions": self._serialize(self.repair_instructions),
            "validation_errors": self._serialize(self.validation_errors),
            "complexity_tier": self.complexity_tier,
            "build_number": self.build_number,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RunContext:
        """Deserialize context from checkpoint dictionary."""
        return cls(
            run_id=str(data.get("run_id", str(uuid4())[:8])),
            original_idea=data.get("original_idea", ""),
            started_at=data.get("started_at", datetime.now(timezone.utc).isoformat()),
            clarification=data.get("clarification"),
            plan=data.get("plan"),
            game_files=data.get("game_files"),
            critique=data.get("critique"),
            validation_report=data.get("validation_report"),
            repair_instructions=data.get("repair_instructions"),
            validation_errors=data.get("validation_errors"),
            complexity_tier=data.get("complexity_tier", "moderate"),
            build_number=data.get("build_number", 0),
        )
