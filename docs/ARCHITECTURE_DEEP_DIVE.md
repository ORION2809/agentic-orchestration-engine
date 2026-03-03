# Architecture Deep Dive

> For a quick overview, see the main [README](../README.md). This document covers the internal design in depth.

---

## State Machine

The orchestrator uses a **deterministic finite state machine** with 8 states and encoded transitions. The LLM never decides what state to move to — the orchestrator evaluates guard conditions and makes the transition.

```
States:  INIT → CLARIFYING → PLANNING → BUILDING → CRITIQUING → VALIDATING → DONE
                                                                             → FAILED
```

### Transition Rules

| From | To | Guard Condition |
|------|----|----------------|
| INIT | CLARIFYING | Always (run started) |
| CLARIFYING | PLANNING | Confidence ≥ threshold (default 0.75) |
| CLARIFYING | FAILED | Max clarification rounds exceeded |
| PLANNING | BUILDING | Plan passes schema validation |
| PLANNING | FAILED | Planning error or budget exceeded |
| BUILDING | CRITIQUING | Code generated successfully |
| BUILDING | FAILED | Token budget exhausted |
| CRITIQUING | VALIDATING | Critic score ≥ threshold |
| CRITIQUING | BUILDING | Repair needed (retry ≤ max_retries) |
| VALIDATING | DONE | All validators pass |
| VALIDATING | BUILDING | Runtime failure (retry ≤ max_retries) |
| VALIDATING | FAILED | Budget exhausted or max retries |

### Why Deterministic?

LLM-driven routing (e.g., "decide what to do next") is:
- **Non-reproducible** — same input can take different paths
- **Hard to debug** — no clear state to inspect
- **Expensive** — routing decisions cost tokens
- **Risky** — LLM can loop infinitely

Our state machine is:
- **Reproducible** — same input always takes the same path (given same LLM output)
- **Inspectable** — current state is always known and logged
- **Free** — transitions cost zero tokens
- **Bounded** — infinite loops are impossible by construction

---

## Agent Design

All agents inherit from `BaseAgent` ABC, which provides:

```python
class BaseAgent(ABC):
    @abstractmethod
    async def run(self, context: RunContext) -> RunContext:
        """Execute this agent's phase and return updated context."""
```

### Clarifier

- **Goal:** Extract structured requirements from vague natural language
- **Method:** Asks targeted questions about game type, mechanics, controls, scoring
- **Output:** `ClarificationResult` Pydantic model with confidence score
- **Stop condition:** Confidence ≥ threshold OR max rounds reached
- **Model tier:** Cheap (gpt-4o-mini) — this is Q&A, not code generation

### Planner

- **Goal:** Design game architecture before any code is written
- **Method:** Takes clarified requirements, produces entity list, game loop design, rendering approach
- **Output:** `GamePlan` Pydantic model with complexity assessment
- **Model tier:** Medium (gpt-4o) — needs reasoning but not code generation quality

### Builder

- **Goal:** Generate complete, working HTML5 game files
- **Method:** Takes game plan, generates `index.html` + `style.css` + `game.js`
- **Modes:** Initial generation OR targeted repair (receives critic issues)
- **Output:** `GeneratedGame` Pydantic model with file map
- **Model tier:** Premium (gpt-4o) — code quality matters most here

### Critic

- **Goal:** Find bugs and missing features before runtime validation
- **Method:** Two-layer approach:
  1. **Deterministic (AST):** Parse JS with esprima, check for game loop, `requestAnimationFrame`, event listeners, collision detection patterns
  2. **LLM (conditional):** Only invoked if AST score is borderline — reviews code for logic errors, missing features relative to the plan
- **Output:** `CritiqueResult` with severity-scored issues
- **Cost optimization:** ~60% of runs skip the LLM critic entirely

---

## Validation Pipeline

Validators run in sequence (fail-fast):

```
Schema Validator → Code Validator → Security Scanner → Runtime Validator → Playability Checker
```

### Schema Validator
Validates that all Pydantic models in the pipeline are well-formed. Catches corrupted outputs or missing fields before they cause downstream failures.

### Code Validator
Static checks on generated HTML/CSS/JS:
- HTML has proper structure (`<html>`, `<head>`, `<body>`)
- CSS/JS files referenced in HTML actually exist
- JS passes `node --check` syntax validation
- Game loop pattern detected (`requestAnimationFrame` or `setInterval`)

### Security Scanner
Scans for dangerous patterns that should never appear in a local game:
- Network: `fetch()`, `XMLHttpRequest`, `WebSocket`, `navigator.sendBeacon`
- Storage: `localStorage`, `sessionStorage`, `document.cookie`, `indexedDB`
- Execution: `eval()`, `Function()`, `setTimeout(string)`, `innerHTML` with variables
- External: `<script src=`, `<link href=http`, `<iframe>`

### Runtime Validator (Playwright)
Launches headless Chromium, loads the game, checks:
- Page loads without errors (no uncaught exceptions in console)
- Canvas element exists and has non-zero dimensions
- No network requests attempted (security double-check)

### Playability Checker (Playwright)
Goes beyond "does it load" to "can you play it":
- Simulates keyboard input (arrow keys, space)
- Checks if score display changes over time
- Verifies game responds to interaction (canvas pixels change)

---

## LLM Layer

### Provider Abstraction (litellm)
All LLM calls go through `litellm`, which provides:
- Unified API across OpenAI, Anthropic, and other providers
- Automatic retry with exponential backoff
- Model-specific token counting

### Structured Output (instructor)
Every LLM call returns a **typed Pydantic model**, not raw text:
```python
result = await structured_call(
    model="gpt-4o",
    response_model=GamePlan,
    messages=[...]
)
# result is a GamePlan instance, not a string
```
This eliminates ~80% of JSON parse failures compared to regex extraction.

### Circuit Breaker
Per-provider sliding window breaker:
- Tracks failure rate over last N calls
- Opens circuit if failure rate exceeds threshold
- Automatically falls back to next provider in chain
- Half-open state for recovery probing

### Token Tracker
Per-phase token and cost tracking:
- Enforces per-phase budgets (cheap phase can't consume premium budget)
- Tracks cumulative cost across the entire run
- Aborts if total budget exceeded

### Model Selector
Adaptive model escalation:
- Starts with configured model
- Escalates to more capable model if structured output fails
- Falls back to cheaper model if budget is tight

---

## Persistence

Abstract `CheckpointStore` interface with file-based implementation:

```python
class CheckpointStore(ABC):
    async def save(self, run_id: str, context: RunContext) -> None: ...
    async def load(self, run_id: str) -> RunContext: ...
    async def exists(self, run_id: str) -> bool: ...
```

The file-based backend stores checkpoints as JSON in the output directory. The abstract interface is designed for drop-in replacement with Redis, Postgres, or S3 for production deployments.

---

## Cost Control

### Adaptive Token Budgets
Token budgets scale with game complexity:
- **Simple** (e.g., pong): ~15k tokens
- **Medium** (e.g., platformer): ~30k tokens  
- **Complex** (e.g., RPG): ~50k tokens

### Per-Phase Model Tiering
Not all phases need the best model:
- Clarifier: gpt-4o-mini (Q&A is cheap)
- Planner: gpt-4o (needs reasoning)
- Builder: gpt-4o (code quality matters)
- Critic LLM: gpt-4o-mini (reviewing, not generating)

This achieves ~60% cost reduction vs using gpt-4o everywhere.

### Backpressure
Global rate limiter prevents token budget blowout across concurrent runs.

---

## Resilience

### Deterministic Fallback
If the LLM fails completely (API outage, budget exhausted), the system falls back to pre-built game templates. The output won't be customized, but the system **always produces something playable**.

### Chaos Testing
Built-in fault injection for testing resilience:
- Random LLM call failures
- Token budget exhaustion mid-run
- Corrupted structured output
- Checkpoint corruption

Enable with `CHAOS_MODE=true` for development testing.
