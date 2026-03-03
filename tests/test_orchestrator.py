"""Tests for state transitions and RunContext serialization."""

from __future__ import annotations

from app.models.state import AgentState, RunContext, TRANSITIONS


def test_all_states_have_transitions() -> None:
    for state in AgentState:
        assert state in TRANSITIONS


def test_terminal_states() -> None:
    assert TRANSITIONS[AgentState.DONE] == []
    assert TRANSITIONS[AgentState.FAILED] == []


def test_core_transition_graph() -> None:
    assert TRANSITIONS[AgentState.INIT] == [AgentState.CLARIFYING]
    assert AgentState.PLANNING in TRANSITIONS[AgentState.CLARIFYING]
    assert AgentState.BUILDING in TRANSITIONS[AgentState.PLANNING]
    assert AgentState.CRITIQUING in TRANSITIONS[AgentState.BUILDING]
    assert AgentState.VALIDATING in TRANSITIONS[AgentState.CRITIQUING]
    assert AgentState.DONE in TRANSITIONS[AgentState.VALIDATING]


def test_no_self_transitions() -> None:
    for state, targets in TRANSITIONS.items():
        assert state not in targets


def test_run_context_roundtrip(sample_clarification, sample_plan, sample_critique, sample_validation_report) -> None:
    ctx = RunContext(run_id="test-rt")
    ctx.original_idea = "make a platformer"
    ctx.clarification = sample_clarification
    ctx.plan = sample_plan
    ctx.critique = sample_critique
    ctx.validation_report = sample_validation_report
    ctx.game_files = {
        "index.html": "<html></html>",
        "style.css": "body{}",
        "game.js": "console.log('x');",
    }
    ctx.repair_instructions = ["fix loop"]
    ctx.validation_errors = ["js syntax"]
    ctx.complexity_tier = "simple"
    ctx.build_number = 2

    data = ctx.to_dict()
    restored = RunContext.from_dict(data)

    assert restored.run_id == "test-rt"
    assert restored.original_idea == "make a platformer"
    assert restored.complexity_tier == "simple"
    assert restored.build_number == 2
    assert restored.plan is not None
    assert restored.clarification is not None
