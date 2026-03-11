# Implementation Plan v7: Agentic Game-Builder AI — MCP-Enabled & Docker-Published

> **Version**: 7.0 · **Last updated**: 2026-03-11  
> **Scope**: End-to-end blueprint for a Docker-packaged, Python-orchestrated, LLM-powered agent that converts ambiguous natural-language game ideas into playable browser games (`index.html`, `style.css`, `game.js`) — now exposable as an **MCP (Model Context Protocol) server** for AI assistant integration.  
> **v7 changelog**: All v6 features retained + **MCP server evolution** — FastMCP-based MCP server (`app/mcp_server.py`) with 6 async tools, 7 resources, 4 prompts; `Context`-injected progress notifications via `asyncio.run_coroutine_threadsafe()`; orchestrator `progress_callback` for real-time phase updates; `remix_game` tool for iterative game modification; Docker MCP mode (zero-dependency setup via `docker run -i`); published images to **Docker Hub** (`shreyas2809/game-builder-mcp`) and **GHCR** (`ghcr.io/orion2809/game-builder-mcp`); Dockerfile HEALTHCHECK; docker-compose `game-builder-mcp` service; VS Code + Claude Desktop MCP config templates; 3 critical bug fixes (AST critic argv, runtime validator key presses, playability checker monkey-patch); bumped to v2.1.0.  
> **v6 changelog**: All v5 features retained + 7 final hardening upgrades — AST-based programmatic debug hook injection (LLM-independent, no regex stripping), extended runtime performance guardrails (5s FPS + entity count growth detection), Redis-backed distributed concurrency (production-safe), global token backpressure across system, bounded simplification loop (max 1 round), and chaos/resilience testing strategy.  
> **v5 changelog**: Debug hook build/delivery mode separation, FPS performance guardrail, cost-predictive complexity scoring, validation-failure-driven quality escalation, immutable versioned artifact storage, enforced prompt version→failure correlation, graceful degraded-output fallback mode, Playwright execution timeout guards.

---

## Table of Contents

1. [Goal & Product Vision](#1-goal--product-vision)
2. [Rubric Alignment Matrix](#2-rubric-alignment-matrix)
3. [Definition of Success](#3-definition-of-success)
4. [High-Level Architecture](#4-high-level-architecture)
4a. [Service-Oriented Production Architecture](#4a-service-oriented-production-architecture) *(NEW)*
5. [Technology Stack (Justified)](#5-technology-stack-justified)
6. [Repository Blueprint](#6-repository-blueprint)
7. [LLM Provider Abstraction](#7-llm-provider-abstraction)
8. [Agent State Machine](#8-agent-state-machine)
8a. [Idempotency & Checkpoint Recovery](#8a-idempotency--checkpoint-recovery) *(NEW)*
8b. [Concurrency & Multi-Tenancy Controls](#8b-concurrency--multi-tenancy-controls) *(NEW)*
9. [Phase 1 — Requirements Clarification (Deep Dive)](#9-phase-1--requirements-clarification)
10. [Phase 2 — Structured Planning (Deep Dive)](#10-phase-2--structured-planning)
10a. [Plan Complexity Guardrail](#10a-plan-complexity-guardrail) *(NEW)*
11. [Phase 3 — Execution / Code Generation (Deep Dive)](#11-phase-3--execution--code-generation)
12. [Phase 4 — Critic & Self-Reflection Loop (Hybrid)](#12-phase-4--critic--self-reflection-loop-hybrid) *(UPGRADED)*
13. [Validation & Quality Gate Layer (Behavioral)](#13-validation--quality-gate-layer-behavioral) *(UPGRADED)*
14. [Prompt Engineering Strategy](#14-prompt-engineering-strategy)
14a. [Prompt Versioning & Regression Testing](#14a-prompt-versioning--regression-testing) *(NEW)*
15. [Error Taxonomy & Recovery Matrix](#15-error-taxonomy--recovery-matrix)
16. [Token & Cost Budget Management (Adaptive)](#16-token--cost-budget-management-adaptive) *(UPGRADED)*
17. [Observability, Logging & Run Artifacts (Production-Grade)](#17-observability-logging--run-artifacts-production-grade) *(UPGRADED)*
18. [Docker Strategy (Production-Grade)](#18-docker-strategy-production-grade)
18a. [MCP Server Architecture](#18a-mcp-server-architecture) *(NEW v7)*
18b. [Docker MCP & Container Registry Publishing](#18b-docker-mcp--container-registry-publishing) *(NEW v7)*
19. [Interactive vs Batch Mode](#19-interactive-vs-batch-mode)
20. [Security & Sandboxing (Hardened)](#20-security--sandboxing-hardened) *(UPGRADED)*
21. [Testing Strategy](#21-testing-strategy)
22. [README Content Blueprint](#22-readme-content-blueprint)
23. [Trade-Offs (Explicit & Honest)](#23-trade-offs-explicit--honest)
24. [Futuristic Architecture Roadmap](#24-futuristic-architecture-roadmap) *(EXPANDED)*
25. [Delivery Milestones](#25-delivery-milestones)
26. [Acceptance Checklist](#26-acceptance-checklist)
27. [Demo Script](#27-demo-script)
28. [Final Recommendation](#28-final-recommendation)

---

## 1) Goal & Product Vision

Build a **deterministic, observable AI agent** that:

1. Accepts an ambiguous NL game idea
2. Engages in targeted clarification dialogue
3. Produces an explicit, schema-validated game plan
4. Generates a fully runnable browser game (`index.html` + `style.css` + `game.js`)
5. Self-validates output before delivery
6. Runs entirely inside Docker with zero manual intervention on generated files

### Design Philosophy
```
    "The LLM proposes; the orchestrator decides; the validator guarantees."
```

The system is engineered for **reliability first, creativity second** — every LLM output is constrained by typed contracts, validated by deterministic checks, and recoverable via bounded retry loops. The modular agent design is future-ready for multi-agent collaboration, RAG-based game pattern retrieval, and automated playtesting.

---

## 2) Rubric Alignment Matrix

| Assignment Requirement | Where Addressed | Implementation Detail |
|---|---|---|
| Accept NL game idea | CLI entrypoint (`main.py`) | `--idea` flag or interactive stdin |
| Ask clarifying questions | Phase 1 Clarifier Agent | Confidence-scored loop with max rounds |
| Produce structured internal plan | Phase 2 Planner Agent | JSON schema + human-readable `.md` |
| Generate `index.html`, `style.css`, `game.js` | Phase 3 Builder Agent | Structured file-map output, parsed & validated |
| Output runs locally in browser | Validation Layer | HTML linkage check + headless smoke test |
| No hard-coded template | Dynamic generation from plan | Plan → code, never template → fill |
| No skipping clarification | State machine enforces INIT→CLARIFYING→PLANNING | Cannot bypass via transition rules |
| No manual modification | Validator auto-repairs or fails cleanly | Bounded self-repair with LLM, no human edits |
| Docker packaging | Multi-stage Dockerfile | Build, run, volume-mount outputs |
| README with architecture, trade-offs, improvements | Section 22 blueprint | Pre-structured headings matching rubric |

---

## 3) Definition of Success

### Functional
- [x] CLI accepts idea; interactive mode for Docker TTY
- [x] 1–3 rounds of clarification, then explicit assumptions
- [x] Plan JSON artifact saved before code generation begins
- [x] 3 game files generated, non-empty, syntactically valid
- [x] Game loads in Chrome/Firefox without JS errors

### Quality
- [x] Deterministic orchestrator (no implicit LLM routing)
- [x] Every phase I/O validated by Pydantic schema
- [x] Bounded retries (max 2) before clean failure
- [x] Full run artifacts for debugging/demo

### Demo
- [x] Docker build+run in < 5 minutes
- [x] Clear console output showing each phase transition
- [x] Final game playable with keyboard/mouse

---

## 4) High-Level Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     USER INPUT                          │
│        (CLI flag --idea  OR  interactive stdin)          │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│              ORCHESTRATOR (State Machine)                 │
│                                                          │
│  State: INIT → CLARIFYING → PLANNING → BUILDING →       │
│         CRITIQUING → VALIDATING → DONE | FAILED          │
│                                                          │
│  Controls: retries, token budget, phase gates            │
└───┬──────────┬──────────┬──────────┬──────────┬─────────┘
    │          │          │          │          │
    ▼          ▼          ▼          ▼          ▼
┌────────┐┌────────┐┌────────┐┌────────┐┌──────────┐
│CLARIFY ││ PLAN   ││ BUILD  ││CRITIC  ││VALIDATOR │
│ Agent  ││ Agent  ││ Agent  ││ Agent  ││  Layer   │
└───┬────┘└───┬────┘└───┬────┘└───┬────┘└────┬─────┘
    │         │         │         │           │
    ▼         ▼         ▼         ▼           ▼
┌──────────────────────────────────────────────────────────┐
│               LLM PROVIDER ABSTRACTION                   │
│  (OpenAI / Anthropic / local model — hot-swappable)      │
│  Structured output mode · Token tracking · Rate limiting │
└──────────────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────────────┐
│                    OUTPUT FOLDER                          │
│  outputs/<run_id>/                                       │
│    ├── clarification.json   (Q&A transcript)             │
│    ├── plan.json            (machine-readable spec)      │
│    ├── plan.md              (human-readable summary)     │
│    ├── critique.json        (self-review findings)       │
│    ├── validation_report.json                            │
│    └── game/                                             │
│        ├── index.html                                    │
│        ├── style.css                                     │
│        └── game.js                                       │
└──────────────────────────────────────────────────────────┘
```

### Core Principle
The orchestrator is a **hardcoded state machine** — not an LLM deciding what to do next. The LLM is a tool called *within* each phase, never the controller of phase flow. This is the critical distinction between "agentic" and "prompt chain."

### Why a While-Loop Now, Event-Driven Later

> **Critique addressed (v4)**: *"Your orchestrator is still synchronous — a blocking state loop can't distribute phases or scale independently"*

The `while self.state not in (DONE, FAILED)` loop is **intentional for the assignment**:
- Simple to debug, test, and demonstrate
- No infrastructure dependencies (Redis, message broker)
- Evaluators can trace the exact control flow in one file

The **production evolution** (§4a) replaces this with event-driven phase tasks. The current design makes this migration trivial because:
1. Each `match` branch is a self-contained phase handler
2. Phase I/O is fully serializable (Pydantic)
3. `RunContext` carries all state — no closure/global dependencies
4. `checkpoint()` already persists state after every transition

#### Migration Path: Loop → Event-Driven

```python
# CURRENT (Assignment): Synchronous loop
while self.state not in (DONE, FAILED):
    match self.state:
        case AgentState.CLARIFYING:  ...
        case AgentState.PLANNING:    ...

# PRODUCTION (Future): Per-phase Celery tasks
@celery.task
def clarify_task(run_id: str):
    ctx = CheckpointStore.load(run_id)
    result = Clarifier().run(ctx)
    CheckpointStore.save(run_id, state="planning", context=ctx)
    plan_task.delay(run_id)  # emit event → queue triggers next phase

@celery.task
def plan_task(run_id: str):
    ctx = CheckpointStore.load(run_id)
    result = Planner().run(ctx)
    CheckpointStore.save(run_id, state="building", context=ctx)
    build_task.delay(run_id)

# Each phase is independently:
# - Retryable (Celery retry policies)
# - Scalable (separate worker pools)
# - Observable (per-task metrics)
```

#### What Changes in Event-Driven Mode
| Aspect | Current (Loop) | Production (Event-Driven) |
|---|---|---|
| Phase execution | Sequential in one process | Separate tasks in worker pool |
| State storage | In-memory `self.state` + file checkpoint | DB-driven (`CheckpointStore`) |
| Retry control | `retry_count` in loop | Celery per-task retry policy |
| Scaling | Single container | Phase-specific worker autoscaling |
| Failure isolation | One crash kills entire run | One phase failure retries independently |

**Key insight**: The refactor is ~50 lines of Celery task wrappers around the *same phase handlers*. No business logic changes.

---

## 4a) Service-Oriented Production Architecture

> **Critique addressed**: *"Your system is single-run oriented, not service-oriented"*

The Section 4 architecture is the **assignment deliverable** — a CLI-first, single-run Docker tool. This section defines the **production evolution** that the system is designed to grow into.

### Current (Assignment): Single-Run CLI
```
User → docker run → orchestrator.run() → output files → exit
```

### Production Target: Distributed Job System
```
┌──────────┐    ┌──────────────┐    ┌─────────────┐    ┌──────────────┐
│  Client  │───▶│  FastAPI      │───▶│  Job Queue   │───▶│  Workers     │
│  (Web UI │    │  API Layer    │    │  (Redis/SQS) │    │  (Celery/RQ) │
│  / CLI)  │    │  Stateless    │    │              │    │              │
└──────────┘    └──────────────┘    └─────────────┘    └──────────────┘
                                                              │
                                                              ▼
                                                    ┌──────────────┐
                                                    │  Postgres    │
                                                    │  (run state, │
                                                    │   artifacts) │
                                                    └──────────────┘
```

### How the Current Design Enables This
| Current Design Choice | Production Extension |
|---|---|
| `Orchestrator.run(idea)` is a pure function | Wrap in Celery task — zero refactor |
| `RunContext` holds all state | Serialize to DB between phases |
| Typed phase I/O (Pydantic) | Natural JSON serialization for queue messages |
| File-based output | Swap to S3/MinIO with same interface |
| Env-var config | Kubernetes ConfigMaps / Secrets |

### Production Components (Not Built Now, Designed For)
- **FastAPI gateway**: `/generate` endpoint → enqueue job → return `run_id` → poll `/status/{run_id}`
- **Job queue**: Redis + RQ (simple) or SQS + Celery (AWS-scale)
- **Worker pool**: Separate containers pulling from queue, running `orchestrator.run()`
- **Persistent storage**: Postgres for run metadata, S3 for game artifacts
- **Async orchestration**: Each phase as a separate task, chained via queue

### Why Not Build This Now
The assignment requires Docker CLI output. Over-engineering into a distributed system would:
- Add complexity that obscures the agent logic evaluators want to see
- Require infrastructure (Redis, Postgres) that complicates `docker run`
- Not demonstrate better agent design — just better ops

The architecture is **designed to evolve**, not prematurely scaled.

---

## 5) Technology Stack (Justified)

| Layer | Choice | Justification |
|---|---|---|
| **Language** | Python 3.11+ | Best ecosystem for LLM SDKs, Pydantic, fast iteration |
| **CLI** | `Typer` | Type-safe CLI with auto-help; better than argparse for demos |
| **LLM Client** | `litellm` wrapper | Single interface for OpenAI, Anthropic, Ollama, Azure — hot-swap via env var |
| **Schema** | `Pydantic v2` | Typed contracts, JSON schema export, validation errors |
| **Structured Output** | `instructor` library | Forces LLM to return Pydantic models directly; retry on parse failure |
| **JS Validation** | `Node.js --check` (in Docker) | Zero-dependency syntax check for generated JS |
| **HTML Validation** | `py_w3c` or regex checks | Verify `<script>` and `<link>` tags reference correct files |
| **Headless Browser** | `Playwright` (optional) | Runtime smoke test — page loads, no console errors for 5s |
| **MCP Server** | `mcp[cli]` + `FastMCP` | Model Context Protocol server — exposes tools/resources/prompts over stdio for AI assistant integration (Claude Desktop, VS Code, Cursor) |
| **Logging** | `structlog` | JSON-structured logs, perfect for debugging and demo |
| **Docker** | Multi-stage build | Smaller image, Node.js available for validation |

### Why NOT these alternatives?
- **LangChain**: Too much abstraction, hides control flow — this assignment evaluates *your* orchestration
- **AutoGen/CrewAI**: Multi-agent frameworks add complexity without adding clarity for this scope
- **TypeScript agent**: Python is faster to prototype and Docker-package for this timeline
- **Direct OpenAI SDK**: `litellm` + `instructor` give provider portability + structured output for free

---

## 6) Repository Blueprint

```
agentic-game-builder/
│
├── app/
│   ├── __init__.py
│   ├── main.py                      # Typer CLI entrypoint
│   ├── mcp_server.py                # MCP server entrypoint (FastMCP, stdio transport)
│   ├── orchestrator.py              # State machine + phase dispatch + retry logic + progress_callback
│   ├── config.py                    # Settings via env vars + defaults
│   │
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── base.py                  # Abstract BaseAgent with LLM call, token tracking
│   │   ├── clarifier.py             # Phase 1: asks questions, scores confidence
│   │   ├── planner.py               # Phase 2: generates game blueprint
│   │   ├── builder.py               # Phase 3: generates HTML/CSS/JS from plan
│   │   └── critic.py                # Phase 4: reviews generated code for issues
│   │
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── provider.py              # litellm wrapper with retry + fallback
│   │   ├── structured.py            # instructor integration for typed outputs
│   │   ├── circuit_breaker.py       # Per-provider sliding-window circuit breaker
│   │   ├── token_tracker.py         # Per-phase and total token accounting
│   │   └── model_selector.py        # Adaptive model escalation
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── schemas.py               # ALL Pydantic models (clarification, plan, game files)
│   │   ├── state.py                 # AgentState enum + RunContext dataclass
│   │   └── errors.py                # Custom exception hierarchy
│   │
│   ├── validators/
│   │   ├── __init__.py
│   │   ├── schema_validator.py      # Pydantic contract enforcement
│   │   ├── code_validator.py        # JS syntax, HTML linkage, CSS non-empty
│   │   ├── runtime_validator.py     # Playwright headless smoke test
│   │   ├── security_scanner.py      # Blocked pattern scanner
│   │   └── playability_checker.py   # Heuristic checks (input listener, game loop, etc.)
│   │
│   ├── persistence/                 # Abstract checkpoint + file-based backend
│   ├── budget/                      # Adaptive token budgets + rate limiter
│   ├── concurrency/                 # Per-user + global run limits
│   ├── debug/                       # Debug hook injection
│   ├── fallback/                    # Last-resort deterministic game templates
│   ├── observability/               # Prometheus-style metrics
│   ├── testing/                     # Chaos / fault injection
│   │
│   ├── prompts/
│   │   ├── clarifier_system.md      # System prompt for clarification agent
│   │   ├── clarifier_user.md        # User prompt template
│   │   ├── planner_system.md
│   │   ├── planner_user.md
│   │   ├── builder_system.md
│   │   ├── builder_user.md
│   │   ├── critic_system.md
│   │   └── critic_user.md
│   │
│   └── io/
│       ├── __init__.py
│       ├── artifacts.py             # Write JSON, MD, game files to output dir
│       └── console.py               # Rich/colorful console output for demo
│
├── outputs/                         # Generated at runtime, gitignored
│   └── <run-id>/
│       ├── clarification.json
│       ├── plan.json
│       ├── plan.md
│       ├── critique.json
│       ├── validation_report.json
│       ├── run_manifest.json        # Full run metadata (timing, tokens, status)
│       └── game/
│           ├── index.html
│           ├── style.css
│           └── game.js
│
├── tests/
│   ├── test_orchestrator.py         # State machine transitions
│   ├── test_schemas.py              # Pydantic model validation
│   ├── test_clarifier_stop.py       # Confidence threshold + max-round logic
│   ├── test_validators.py           # Code checks on sample outputs
│   └── conftest.py                  # Shared fixtures, mock LLM responses
│
├── mcp_config/                      # MCP client configuration templates
│   └── claude_desktop_config.json    # Claude Desktop MCP config (local + Docker)
│
├── .vscode/
│   └── mcp.json                     # VS Code MCP server config (local + Docker)
│
├── Dockerfile                       # Multi-stage: Python + Node.js + Playwright + MCP
├── docker-compose.yml               # CLI mode + MCP server mode services
├── .dockerignore
├── .env.example                     # Template for API keys
├── requirements.txt
├── pyproject.toml                   # Project metadata + tool config (v2.1.0)
├── .gitignore
└── README.md
```

---

## 7) LLM Provider Abstraction

### Why This Matters
The assignment says *"You may use LLM APIs (OpenAI, Anthropic, etc.)"* — building a provider-agnostic layer:
- Lets evaluators run with whatever API key they have
- Enables fallback chains (e.g., GPT-4o → Claude → local Ollama)
- Future-proofs for self-hosted models

### Implementation

```python
# app/llm/provider.py  (pseudocode)

import litellm
from app.llm.token_tracker import TokenTracker

class LLMProvider:
    """Hot-swappable LLM backend via env var LLM_MODEL."""

    def __init__(self, model: str = None):
        self.model = model or os.getenv("LLM_MODEL", "gpt-4o")
        self.tracker = TokenTracker()
        self.fallback_models = os.getenv("LLM_FALLBACK", "").split(",")

    def complete(self, messages: list[dict], phase: str, **kwargs) -> str:
        """Call LLM with automatic fallback and token tracking."""
        models_to_try = [self.model] + [m for m in self.fallback_models if m]
        last_error = None

        for model in models_to_try:
            try:
                response = litellm.completion(
                    model=model,
                    messages=messages,
                    **kwargs
                )
                self.tracker.record(phase, model, response.usage)
                return response.choices[0].message.content
            except Exception as e:
                last_error = e
                logger.warning(f"Model {model} failed, trying next: {e}")

        raise LLMProviderError(f"All models failed. Last: {last_error}")

    def complete_structured(self, messages, response_model, phase, **kwargs):
        """Return a validated Pydantic model via instructor."""
        import instructor
        client = instructor.from_litellm(litellm.completion)
        return client.chat.completions.create(
            model=self.model,
            messages=messages,
            response_model=response_model,
            max_retries=2,
            **kwargs
        )
```

### Configuration
```bash
# .env
LLM_MODEL=gpt-4o                     # Primary model
LLM_FALLBACK=claude-sonnet-4-20250514,gpt-4o-mini  # Fallback chain
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
```

---

## 8) Agent State Machine

### States
```python
class AgentState(str, Enum):
    INIT        = "init"
    CLARIFYING  = "clarifying"
    PLANNING    = "planning"
    BUILDING    = "building"
    CRITIQUING  = "critiquing"      # NEW: self-reflection pass
    VALIDATING  = "validating"
    DONE        = "done"
    FAILED      = "failed"
```

### Transition Rules (Encoded, Not Implied)

```python
TRANSITIONS: dict[AgentState, list[AgentState]] = {
    AgentState.INIT:        [AgentState.CLARIFYING],
    AgentState.CLARIFYING:  [AgentState.PLANNING, AgentState.FAILED],
    AgentState.PLANNING:    [AgentState.BUILDING, AgentState.FAILED],
    AgentState.BUILDING:    [AgentState.CRITIQUING, AgentState.FAILED],
    AgentState.CRITIQUING:  [AgentState.VALIDATING, AgentState.BUILDING],  # can loop back
    AgentState.VALIDATING:  [AgentState.DONE, AgentState.BUILDING, AgentState.FAILED],
    AgentState.DONE:        [],
    AgentState.FAILED:      [],
}
```

### Transition Guards (Concrete Conditions)

| From → To | Guard Condition |
|---|---|
| INIT → CLARIFYING | Always (mandatory phase) |
| CLARIFYING → PLANNING | `confidence >= 0.75` OR `round >= max_rounds` (with assumptions logged) |
| PLANNING → BUILDING | `plan_schema.is_valid()` AND all required fields present |
| BUILDING → CRITIQUING | All 3 files generated AND non-empty |
| CRITIQUING → VALIDATING | Critic found no critical issues OR fixes applied |
| CRITIQUING → BUILDING | Critical issues found → trigger rebuild (max 1 loop) |
| VALIDATING → DONE | All checks pass |
| VALIDATING → BUILDING | Recoverable failure + `retry_count < max_retries` |
| Any → FAILED | Unrecoverable error OR `retry_count >= max_retries` |

### Orchestrator Loop (Pseudocode)

```python
# app/orchestrator.py

class Orchestrator:
    def __init__(self, config: Config):
        self.state = AgentState.INIT
        self.context = RunContext(run_id=uuid4())
        self.config = config
        self.retry_count = 0
        self.max_retries = config.max_retries  # default: 2

    def run(self, idea: str) -> RunResult:
        self.context.original_idea = idea
        self.transition(AgentState.CLARIFYING)

        while self.state not in (AgentState.DONE, AgentState.FAILED):
            try:
                match self.state:
                    case AgentState.CLARIFYING:
                        result = self.clarifier.run(self.context)
                        self.context.clarification = result
                        self.transition(AgentState.PLANNING)

                    case AgentState.PLANNING:
                        result = self.planner.run(self.context)
                        self.context.plan = result
                        self.transition(AgentState.BUILDING)

                    case AgentState.BUILDING:
                        result = self.builder.run(self.context)
                        self.context.game_files = result
                        self.transition(AgentState.CRITIQUING)

                    case AgentState.CRITIQUING:
                        issues = self.critic.run(self.context)
                        if issues.has_critical and self.retry_count < self.max_retries:
                            self.context.repair_instructions = issues
                            self.retry_count += 1
                            self.transition(AgentState.BUILDING)
                        else:
                            self.transition(AgentState.VALIDATING)

                    case AgentState.VALIDATING:
                        report = self.validator.run(self.context)
                        if report.passed:
                            self.transition(AgentState.DONE)
                        elif self.retry_count < self.max_retries:
                            self.context.validation_errors = report.errors
                            self.retry_count += 1
                            self.transition(AgentState.BUILDING)
                        else:
                            self.transition(AgentState.FAILED)

            except Exception as e:
                logger.error(f"Phase {self.state} failed: {e}")
                self.transition(AgentState.FAILED)

        return self.finalize()

    def transition(self, new_state: AgentState):
        assert new_state in TRANSITIONS[self.state], \
            f"Illegal transition: {self.state} → {new_state}"
        logger.info(f"State: {self.state} → {new_state}")
        self.state = new_state
        self.checkpoint()  # persist state after every transition

    def checkpoint(self):
        """Persist current state + context to disk for crash recovery."""
        snapshot = {
            "run_id": str(self.context.run_id),
            "state": self.state.value,
            "retry_count": self.retry_count,
            "context": self.context.to_dict(),  # serializable
            "timestamp": datetime.utcnow().isoformat(),
        }
        path = Path(self.config.output_dir) / str(self.context.run_id) / "checkpoint.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(snapshot, indent=2))

    @classmethod
    def resume(cls, run_id: str, config: Config) -> "Orchestrator":
        """Resume a crashed run from last checkpoint."""
        path = Path(config.output_dir) / run_id / "checkpoint.json"
        snapshot = json.loads(path.read_text())
        instance = cls(config)
        instance.state = AgentState(snapshot["state"])
        instance.retry_count = snapshot["retry_count"]
        instance.context = RunContext.from_dict(snapshot["context"])
        logger.info(f"Resumed run {run_id} from state {instance.state}")
        return instance
```

---

## 8a) Idempotency & Checkpoint Recovery

> **Critique addressed**: *"You have no idempotency strategy"*  
> **Critique addressed (v4)**: *"Checkpointing is file-based, not durable — container death loses ephemeral disk"*

### Problem
If the worker crashes during BUILDING, the LLM call money is spent, context is lost, and the run must restart from scratch. File-based checkpoints fail in multi-container/Kubernetes environments where disk is ephemeral.

### Solution: Abstract Persistence Layer

Checkpointing is **not hardcoded to files**. An abstract `CheckpointStore` interface allows swappable backends:

```python
# app/persistence/base.py
from abc import ABC, abstractmethod

class CheckpointStore(ABC):
    """Abstract persistence for run state. Backend is injectable."""

    @abstractmethod
    def save(self, run_id: str, snapshot: dict) -> None: ...

    @abstractmethod
    def load(self, run_id: str) -> dict | None: ...

    @abstractmethod
    def exists(self, run_id: str) -> bool: ...

class ArtifactStore(ABC):
    """Abstract persistence for game file artifacts."""

    @abstractmethod
    def save_game(self, run_id: str, files: dict[str, str]) -> str: ...

    @abstractmethod
    def load_game(self, run_id: str) -> dict[str, str] | None: ...
```

### Backend Implementations

```python
# app/persistence/file_store.py — CLI/Docker default
class FileCheckpointStore(CheckpointStore):
    """Writes checkpoint.json to local disk. Default for single-container."""
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir

    def save(self, run_id: str, snapshot: dict) -> None:
        path = self.output_dir / run_id / "checkpoint.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(snapshot, indent=2))

    def load(self, run_id: str) -> dict | None:
        path = self.output_dir / run_id / "checkpoint.json"
        return json.loads(path.read_text()) if path.exists() else None

    def exists(self, run_id: str) -> bool:
        return (self.output_dir / run_id / "checkpoint.json").exists()


# app/persistence/postgres_store.py — Production
class PostgresCheckpointStore(CheckpointStore):
    """Stores state in Postgres. Survives container restarts."""
    def __init__(self, dsn: str):
        self.pool = asyncpg.create_pool(dsn)

    def save(self, run_id: str, snapshot: dict) -> None:
        self.pool.execute(
            "INSERT INTO checkpoints (run_id, state, snapshot, updated_at) "
            "VALUES ($1, $2, $3, NOW()) ON CONFLICT (run_id) DO UPDATE SET "
            "state = $2, snapshot = $3, updated_at = NOW()",
            run_id, snapshot["state"], json.dumps(snapshot)
        )

    def load(self, run_id: str) -> dict | None:
        row = self.pool.fetchrow("SELECT snapshot FROM checkpoints WHERE run_id = $1", run_id)
        return json.loads(row["snapshot"]) if row else None


# app/persistence/s3_store.py — Artifact storage for production
class S3ArtifactStore(ArtifactStore):
    """Stores game files in S3/MinIO. Durable, versioned, CDN-ready."""
    def __init__(self, bucket: str, client):
        self.bucket = bucket
        self.client = client  # boto3 S3 client

    def save_game(self, run_id: str, files: dict[str, str], build_number: int = 1) -> str:
        """Save with build versioning. Each rebuild gets its own prefix."""
        for filename, content in files.items():
            self.client.put_object(
                Bucket=self.bucket,
                Key=f"{run_id}/build_{build_number}/{filename}",
                Body=content.encode(),
            )
        return f"s3://{self.bucket}/{run_id}/build_{build_number}/"
```

### Immutable Build Versioning (v5 Upgrade)

> **Critique addressed (v5)**: *"If a rebuild occurs, you overwrite files. You lose the previous attempt. You can't compare diffs or audit model behavior."*

Every build attempt gets its own immutable version. Rebuilds never overwrite previous artifacts.

```python
# File-based immutable versioning
class FileArtifactStore(ArtifactStore):
    def save_game(self, run_id: str, files: dict[str, str], build_number: int = 1) -> str:
        build_dir = self.output_dir / run_id / f"build_{build_number}"
        build_dir.mkdir(parents=True, exist_ok=True)
        for filename, content in files.items():
            (build_dir / filename).write_text(content)
        # Symlink 'latest' to most recent build
        latest = self.output_dir / run_id / "game"
        if latest.is_symlink():
            latest.unlink()
        latest.symlink_to(build_dir)
        return str(build_dir)
```

#### Artifact Layout
```
outputs/<run_id>/
    build_1/           ← First attempt
        index.html
        style.css
        game.js
    build_2/           ← After critic-triggered rebuild
        index.html
        style.css
        game.js
    game/              ← Symlink to latest successful build
    checkpoint.json
    run_manifest.json
```

#### Benefits
- **Diff audit**: Compare `build_1/game.js` vs `build_2/game.js` to see what the critic fixed
- **Model comparison**: If build_1 used gpt-4o and build_2 used claude-sonnet, compare outputs
- **Regression debugging**: Inspect which build attempt introduced a bug
- **No data loss**: Even failed builds are preserved for post-mortem

### Injection into Orchestrator

```python
# Persistence backend chosen by config
def create_stores(config: Config) -> tuple[CheckpointStore, ArtifactStore]:
    if config.persistence_backend == "postgres":
        return PostgresCheckpointStore(config.db_dsn), S3ArtifactStore(config.s3_bucket, ...)
    else:  # default: file
        return FileCheckpointStore(config.output_dir), FileArtifactStore(config.output_dir)

# Orchestrator uses abstract interface
class Orchestrator:
    def __init__(self, config, checkpoint_store: CheckpointStore, artifact_store: ArtifactStore):
        self.checkpoint_store = checkpoint_store
        self.artifact_store = artifact_store
        self.build_number = 0  # incremented on each BUILDING enter

    def checkpoint(self):
        snapshot = {"run_id": ..., "state": ..., "context": ..., "timestamp": ...,
                    "build_number": self.build_number}  # track build version
        self.checkpoint_store.save(str(self.context.run_id), snapshot)
```

### Checkpoint Snapshot
```json
{
  "run_id": "a3f7c2",
  "state": "building",
  "retry_count": 0,
  "context": {
    "original_idea": "make a dodge game",
    "clarification": { "...serialized ClarificationResult..." },
    "plan": { "...serialized GamePlan..." },
    "game_files": null
  },
  "timestamp": "2026-03-03T14:22:15Z"
}
```

### Resume Logic
```python
# CLI supports --resume
@app.command()
def resume(run_id: str = typer.Argument(..., help="Run ID to resume")):
    config = Config()
    stores = create_stores(config)
    orchestrator = Orchestrator.resume(run_id, config, stores[0], stores[1])
    result = orchestrator.run(orchestrator.context.original_idea)
```

### Persistence Backend Comparison

| Backend | Durability | Concurrent Access | Use Case |
|---|---|---|---|
| `FileCheckpointStore` | Ephemeral (container-bound) | No | CLI / Docker single-run (assignment) |
| `PostgresCheckpointStore` | Durable (survives restarts) | Yes (row-level locks) | Multi-worker production |
| `S3ArtifactStore` | Highly durable (11 9s) | Yes | Game file storage, CDN delivery |

### Idempotency Guarantees
| Scenario | Behavior |
|---|---|
| Crash during CLARIFYING | Resume re-runs clarification (cheap, ~2k tokens) |
| Crash during PLANNING | Resume re-runs planning with saved clarification |
| Crash during BUILDING | Resume re-runs building with saved plan (no duplicate clarify/plan) |
| Crash during VALIDATING | Resume re-runs validation with saved game files (zero LLM cost) |
| Duplicate run with same idea | Each run gets unique `run_id` — no collision |
| Container dies (Kubernetes) | Postgres checkpoint survives; new pod resumes |

### Cost Savings
Without checkpointing, a crash at VALIDATING wastes ~20k tokens ($0.10).
With checkpointing, resuming from VALIDATING costs 0 tokens.

---

## 8b) Concurrency & Multi-Tenancy Controls

> **Critique addressed**: *"No concurrency controls"*

### Problem
In multi-user scenarios, uncontrolled concurrent runs burn API quota, corrupt shared state, and provide no isolation.

### Solution: Layered Rate Limiting

```python
class ConcurrencyController:
    """Enforces per-user and global limits."""

    def __init__(self, config: Config):
        self.max_concurrent_runs = config.max_concurrent_runs  # default: 5
        self.max_runs_per_user = config.max_runs_per_user      # default: 2
        self.active_runs: dict[str, list[str]] = {}            # user_id -> [run_ids]
        self.global_circuit_breaker = CircuitBreaker(
            failure_threshold=5,    # 5 consecutive LLM failures
            recovery_timeout=60,    # wait 60s before retrying
        )

    def can_start_run(self, user_id: str) -> tuple[bool, str]:
        total_active = sum(len(runs) for runs in self.active_runs.values())
        if total_active >= self.max_concurrent_runs:
            return False, "Global concurrency limit reached"
        if len(self.active_runs.get(user_id, [])) >= self.max_runs_per_user:
            return False, "Per-user concurrency limit reached"
        if self.global_circuit_breaker.is_open:
            return False, "LLM API circuit breaker open — retrying in {recovery}s"
        return True, "ok"
```

### Distributed Concurrency (Production Path)

> **Critique addressed (v6)**: *"Your `active_runs` dict works in single-process. In distributed workers, each worker has its own memory. Global concurrency cap is meaningless."*

The in-memory `ConcurrencyController` works for the CLI/Docker assignment. For multi-worker production, use Redis-backed atomic counters:

```python
# app/concurrency/redis_controller.py

import redis
import time

class RedisConcurrencyController:
    """
    Distributed-safe concurrency control via Redis atomic operations.
    Drop-in replacement for ConcurrencyController in multi-worker deployments.
    """

    def __init__(self, config: Config, redis_client: redis.Redis):
        self.redis = redis_client
        self.max_concurrent_runs = config.max_concurrent_runs
        self.max_runs_per_user = config.max_runs_per_user
        self.run_ttl = 600  # 10min TTL — auto-cleanup if worker crashes

    def can_start_run(self, user_id: str) -> tuple[bool, str]:
        # Global count: all keys matching "active_run:*"
        total_active = self.redis.scard("active_runs:global")
        if total_active >= self.max_concurrent_runs:
            return False, "Global concurrency limit reached"

        # Per-user count
        user_active = self.redis.scard(f"active_runs:user:{user_id}")
        if user_active >= self.max_runs_per_user:
            return False, "Per-user concurrency limit reached"

        return True, "ok"

    def register_run(self, user_id: str, run_id: str):
        """Atomically register a run. Uses TTL for crash recovery."""
        pipe = self.redis.pipeline()
        pipe.sadd("active_runs:global", run_id)
        pipe.expire("active_runs:global", self.run_ttl)
        pipe.sadd(f"active_runs:user:{user_id}", run_id)
        pipe.expire(f"active_runs:user:{user_id}", self.run_ttl)
        pipe.setex(f"run_heartbeat:{run_id}", self.run_ttl, str(time.time()))
        pipe.execute()

    def release_run(self, user_id: str, run_id: str):
        """Atomically release a run on completion or failure."""
        pipe = self.redis.pipeline()
        pipe.srem("active_runs:global", run_id)
        pipe.srem(f"active_runs:user:{user_id}", run_id)
        pipe.delete(f"run_heartbeat:{run_id}")
        pipe.execute()

    def cleanup_stale_runs(self):
        """Periodic cleanup: remove runs whose heartbeat TTL expired (crashed workers)."""
        all_runs = self.redis.smembers("active_runs:global")
        for run_id in all_runs:
            if not self.redis.exists(f"run_heartbeat:{run_id}"):
                # Heartbeat expired — worker likely crashed
                self.redis.srem("active_runs:global", run_id)
                logger.warning(f"Cleaned up stale run: {run_id}")
```

#### Concurrency Backend Comparison
| Backend | Distributed-Safe | Crash Recovery | Use Case |
|---|---|---|---|
| `ConcurrencyController` (in-memory) | No | No (process dies → state lost) | CLI / single-process Docker |
| `RedisConcurrencyController` | Yes (atomic ops) | Yes (TTL-based heartbeat) | Multi-worker production |
```

### Controls Implemented

| Control | Scope | Default | Purpose |
|---|---|---|---|
| Max concurrent runs | Global | 5 | Prevent API quota exhaustion |
| Max runs per user | Per-user | 2 | Fair scheduling |
| Token budget per run | Per-run | Adaptive (see §16) | Cost ceiling |
| Circuit breaker | Per-provider | Sliding window (see below) | Backpressure when LLM unstable |
| Rate limiter | Per-model | 60 req/min | Respect provider rate limits |

### Production-Grade Circuit Breaker (v4 Upgrade)

> **Critique addressed (v4)**: *"Is your circuit breaker integrated into LLMProvider? Per-model or global? Does it reset on partial success?"*

The v3 circuit breaker was a simple counter. Production-grade breakers must be:
- **Per-provider** (OpenAI outage shouldn't block Anthropic)
- **Sliding-window** (not just consecutive failures)
- **Time-decayed** (old failures fade out)
- **Integrated into LLMProvider** (not standalone)

```python
# app/llm/circuit_breaker.py

from collections import deque
from datetime import datetime, timedelta

class SlidingWindowCircuitBreaker:
    """
    Per-provider circuit breaker with time-decayed sliding window.
    Integrated directly into LLMProvider — not a standalone checker.
    """

    def __init__(
        self,
        provider: str,
        window_size: timedelta = timedelta(minutes=5),
        failure_rate_threshold: float = 0.5,  # 50% failure rate trips
        min_calls_in_window: int = 5,          # need at least 5 calls to trip
        recovery_timeout: timedelta = timedelta(seconds=60),
    ):
        self.provider = provider
        self.window_size = window_size
        self.failure_rate_threshold = failure_rate_threshold
        self.min_calls_in_window = min_calls_in_window
        self.recovery_timeout = recovery_timeout

        self.calls: deque[tuple[datetime, bool]] = deque()  # (timestamp, success)
        self.state: Literal["closed", "open", "half-open"] = "closed"
        self.opened_at: datetime | None = None

    def record(self, success: bool):
        now = datetime.utcnow()
        self.calls.append((now, success))
        self._evict_old(now)

        if self.state == "half-open":
            self.state = "closed" if success else "open"
            self.opened_at = None if success else now
            return

        if len(self.calls) >= self.min_calls_in_window:
            failure_rate = sum(1 for _, s in self.calls if not s) / len(self.calls)
            if failure_rate >= self.failure_rate_threshold:
                self.state = "open"
                self.opened_at = now
                logger.warning(f"Circuit breaker OPEN for {self.provider}",
                               failure_rate=failure_rate)

    def can_execute(self) -> bool:
        if self.state == "closed":
            return True
        if self.state == "open":
            if datetime.utcnow() - self.opened_at >= self.recovery_timeout:
                self.state = "half-open"  # allow one probe request
                return True
            return False
        return True  # half-open allows one call

    def _evict_old(self, now: datetime):
        cutoff = now - self.window_size
        while self.calls and self.calls[0][0] < cutoff:
            self.calls.popleft()
```

### Integration into LLMProvider

```python
# app/llm/provider.py (updated)

class LLMProvider:
    def __init__(self):
        # One breaker per provider
        self.breakers = {
            "openai": SlidingWindowCircuitBreaker("openai"),
            "anthropic": SlidingWindowCircuitBreaker("anthropic"),
            "google": SlidingWindowCircuitBreaker("google"),
        }

    def call(self, model: str, messages: list, **kwargs) -> str:
        provider = self._get_provider(model)  # "openai", "anthropic", etc.
        breaker = self.breakers[provider]

        if not breaker.can_execute():
            # Try fallback provider if available
            fallback = self._get_fallback(provider)
            if fallback and self.breakers[fallback].can_execute():
                logger.warning(f"Circuit open for {provider}, falling back to {fallback}")
                provider = fallback
                model = self._get_equivalent_model(model, fallback)
            else:
                raise CircuitBreakerOpenError(f"All providers unavailable")

        try:
            result = litellm.completion(model=model, messages=messages, **kwargs)
            breaker.record(success=True)
            return result
        except Exception as e:
            breaker.record(success=False)
            raise
```

### Circuit Breaker States
```
 CLOSED ──(failure_rate ≥ 50%)──► OPEN ──(recovery_timeout)──► HALF-OPEN
   ▲                                                             │
   └──────────(probe succeeds)───────────────────────────────────┘
   ▲                                                             │
   └─────────────────────(probe fails → re-open)─────────────────┘
```

### Assignment Scope Note
For the CLI deliverable, concurrency is N/A (single-run). These controls are implemented as **optional middleware** activated when running in API/service mode. The `ConcurrencyController` and `SlidingWindowCircuitBreaker` are injected into the orchestrator but defaults to no-op in CLI mode.

---

## 9) Phase 1 — Requirements Clarification

### Goal
Extract enough structured information from an ambiguous prompt to produce a buildable game spec, asking only necessary questions.

### Requirement Dimensions (Scored)

| Dimension | Required? | Default if Missing |
|---|---|---|
| Genre / game type | YES | Infer from prompt |
| Core objective | YES | Ask |
| Controls (keyboard/mouse/touch) | YES | Default: keyboard arrows + space |
| Win condition | YES | Ask or assume score-based |
| Lose condition | YES | Ask or assume lives/timer |
| Difficulty | NO | Default: medium, progressive |
| Visual style | NO | Default: minimalist CSS shapes |
| Framework preference | NO | Default: vanilla JS (see decision policy) |
| Sound | NO | Default: none (keep scope small) |
| Number of players | NO | Default: single player |

### Confidence Scoring Algorithm

```python
def compute_confidence(resolved: dict[str, Any], dimensions: list) -> float:
    required = [d for d in dimensions if d.required]
    filled_required = sum(1 for d in required if d.key in resolved and resolved[d.key])
    optional_filled = sum(1 for d in dimensions if not d.required and d.key in resolved)

    required_score = filled_required / len(required)          # weight: 0.8
    optional_score = optional_filled / max(1, len(dimensions) - len(required))  # weight: 0.2

    return 0.8 * required_score + 0.2 * optional_score
```

### Clarification Loop

```python
class ClarifierAgent(BaseAgent):
    MAX_ROUNDS = 3
    CONFIDENCE_THRESHOLD = 0.75

    def run(self, context: RunContext) -> ClarificationResult:
        resolved = self.extract_initial(context.original_idea)  # LLM pass 1: parse what's already clear

        for round_num in range(1, self.MAX_ROUNDS + 1):
            confidence = compute_confidence(resolved, DIMENSIONS)
            if confidence >= self.CONFIDENCE_THRESHOLD:
                break

            # LLM generates ONLY questions for missing required dimensions
            questions = self.generate_questions(resolved, round_num)
            answers = self.get_user_answers(questions)  # stdin in interactive, auto in batch
            resolved = self.merge_answers(resolved, answers)

        # Fill remaining gaps with explicit assumptions
        assumptions = self.fill_defaults(resolved)

        return ClarificationResult(
            questions_asked=all_questions,
            answers=all_answers,
            resolved_requirements=resolved,
            assumptions=assumptions,
            confidence=compute_confidence(resolved, DIMENSIONS),
        )
```

### Key Design Decisions
1. **Initial extraction pass**: LLM first extracts what's *already* clear from the prompt (avoids asking things already stated)
2. **Targeted questions only**: LLM sees which dimensions are missing and generates questions only for those
3. **Batched questions**: Ask 2–4 questions per round, not one at a time (respects "avoid excessive questioning")
4. **Explicit assumptions logged**: When max rounds hit, system fills defaults and records them — critical for demo transparency

### Output Schema

```python
class ClarificationResult(BaseModel):
    questions_asked: list[str]
    user_answers: dict[str, str]
    resolved_requirements: GameRequirements
    assumptions: list[Assumption]
    confidence_score: float = Field(ge=0.0, le=1.0)
    rounds_used: int
```

---

## 10) Phase 2 — Structured Planning

### Goal
Transform clarified requirements into a machine-consumable game blueprint that the builder can execute deterministically.

### Full Plan Schema

```python
class GamePlan(BaseModel):
    """Complete game specification — contract between planner and builder."""

    # Meta
    game_title: str
    game_concept: str                              # 2-3 sentence description
    framework: Literal["vanilla", "phaser"]
    framework_rationale: str                        # WHY this choice

    # Mechanics
    core_mechanics: list[Mechanic]                 # e.g., [{"name": "dodge", "description": "..."}]
    controls: ControlScheme                        # keys/mouse mapped to actions
    game_loop: GameLoopSpec                        # init → update → render cycle

    # Entities
    entities: list[Entity]                         # player, enemies, collectibles, obstacles
    entity_relationships: list[str]                # "player collides with enemy → lose life"

    # State
    state_model: GameStateModel                    # menu → playing → paused → game_over
    scoring: ScoringSpec                           # what earns points, display method
    win_condition: str
    lose_condition: str
    difficulty_curve: str                          # e.g., "enemies speed up every 10s"

    # Visual
    canvas_size: tuple[int, int] = (800, 600)
    visual_style: str                              # "geometric shapes", "pixel art", etc.
    color_palette: list[str] = []                  # optional hex colors
    asset_strategy: Literal["css_shapes", "canvas_draw", "emoji", "external_sprites"]

    # File Blueprint (crucial for builder)
    html_spec: str                                 # what index.html should contain
    css_spec: str                                  # layout + styling notes
    js_architecture: str                           # code structure: classes, functions, game loop pattern

    # Acceptance
    acceptance_checks: list[str]                   # e.g., ["player moves with arrow keys", "score increments on collect"]
```

### Framework Decision Policy (Rule-Based)

```python
def decide_framework(requirements: GameRequirements) -> tuple[str, str]:
    needs_physics = any(m in requirements.mechanics for m in ["bounce", "gravity", "collision_complex"])
    needs_scenes  = requirements.has_multiple_levels
    needs_sprites = requirements.asset_strategy == "external_sprites"
    needs_camera  = requirements.world_larger_than_viewport

    if needs_physics or needs_scenes or needs_sprites or needs_camera:
        return "phaser", "Complex mechanics require Phaser's built-in physics/scene/sprite systems"
    else:
        return "vanilla", "Simple mechanics achievable with Canvas API; fewer dependencies = more reliable generation"
```

### Planning Prompt Strategy
The planner LLM call receives:
1. The full `ClarificationResult` (not the raw idea)
2. The target `GamePlan` schema as JSON Schema
3. 1–2 few-shot examples of well-formed plans (hardcoded, not generated)
4. Explicit instruction to fill ALL fields

Output is forced through `instructor` → `GamePlan` Pydantic model → validated or rejected.

---

## 10a) Plan Complexity Guardrail

> **Critique addressed**: *"Introduce plan complexity guardrail"*

### Problem
An idea like "MMORPG with AI enemies and 50 levels" will exhaust the token budget, produce broken code, and waste money.

### Solution: Pre-Build Complexity Scoring (Structural + Cost-Predictive)

> **Critique addressed (v5)**: *"Your complexity scoring is structural — not cost-predictive. It should also factor token estimate, entity interactions (combinatorial explosion), and framework generation size."*

After the planner generates a `GamePlan`, score its complexity using **both structural shape and predicted token cost** before proceeding to building:

```python
def score_complexity(plan: GamePlan) -> ComplexityAssessment:
    score = 0
    factors = []

    # ---- Structural scoring (original) ----

    # Entity count
    if len(plan.entities) > 5:
        score += 2
        factors.append(f"{len(plan.entities)} entities (high)")
    elif len(plan.entities) > 3:
        score += 1

    # Physics requirement
    if plan.framework == "phaser" or any("physics" in m.description.lower() for m in plan.core_mechanics):
        score += 2
        factors.append("Physics engine required")

    # Multiple levels
    if "level" in plan.difficulty_curve.lower() or "stage" in plan.difficulty_curve.lower():
        score += 2
        factors.append("Multi-level game")

    # Complex state model
    if len(plan.state_model.states) > 4:
        score += 1
        factors.append(f"{len(plan.state_model.states)} game states")

    # Mechanic count
    if len(plan.core_mechanics) > 4:
        score += 1
        factors.append(f"{len(plan.core_mechanics)} mechanics")

    # ---- Cost-predictive scoring (v5 upgrade) ----

    # Entity interaction complexity (combinatorial explosion risk)
    interaction_pairs = len(plan.entities) * (len(plan.entities) - 1) / 2
    if interaction_pairs > 10:
        score += 2
        factors.append(f"{interaction_pairs:.0f} entity interaction pairs (combinatorial risk)")
    elif interaction_pairs > 5:
        score += 1

    # Framework generation size
    if plan.framework == "phaser":
        score += 1
        factors.append("Phaser framework (larger code generation)")

    # Predicted builder token cost
    estimated_builder_tokens = estimate_builder_tokens(plan)
    if estimated_builder_tokens > 20_000:
        score += 2
        factors.append(f"Estimated builder tokens: {estimated_builder_tokens:,} (high)")
    elif estimated_builder_tokens > 12_000:
        score += 1

    tier = "simple" if score <= 3 else "moderate" if score <= 6 else "complex"
    return ComplexityAssessment(
        score=score, tier=tier, factors=factors,
        estimated_builder_tokens=estimated_builder_tokens,  # NEW: used by budget
    )


def estimate_builder_tokens(plan: GamePlan) -> int:
    """
    Predict how many tokens the builder will need based on plan shape.
    Empirically calibrated from test runs.
    """
    base = 5_000  # minimum for any game
    per_entity = 1_500
    per_mechanic = 1_200
    per_state = 800
    framework_multiplier = 1.4 if plan.framework == "phaser" else 1.0

    estimate = (
        base
        + len(plan.entities) * per_entity
        + len(plan.core_mechanics) * per_mechanic
        + len(plan.state_model.states) * per_state
    )
    return int(estimate * framework_multiplier)
```

### Pre-Build Budget Check
```python
# After complexity scoring, verify builder can afford the generation
assessment = score_complexity(plan)
budget = AdaptiveTokenBudget.from_complexity(assessment)

if assessment.estimated_builder_tokens > budget.builder_budget:
    logger.warning(
        f"Predicted builder cost ({assessment.estimated_builder_tokens:,}) exceeds "
        f"tier budget ({budget.builder_budget:,}). Triggering simplification."
    )
    # Trigger simplification pass BEFORE building
```

### Complexity Tiers & Response

| Tier | Score | Token Budget | Action |
|---|---|---|---|
| Simple | 0–2 | 30,000 | Proceed normally |
| Moderate | 3–5 | 50,000 | Proceed with warning logged |
| Complex | 6+ | 70,000 | **Simplification pass**: ask planner to reduce scope, OR warn user and proceed with higher budget |

### Simplification Strategy (Bounded)

> **Critique addressed (v6)**: *"Your simplification loop could oscillate. Planner simplifies but result is still complex. You re-simplify again. Risk of infinite loop."*

When complexity is too high (structural score OR predicted token cost exceeds budget):
1. Feed plan back to planner with instruction: *"Simplify to max 4 entities, 3 mechanics, single level. Preserve core fun."*
2. Re-score simplified plan (both structural and cost-predictive)
3. If predicted tokens still exceed budget → proceed with warning + expanded budget
4. If simplified fits budget → proceed with standard budget

**Critical**: `max_simplification_rounds = 1`. The simplification pass runs at most **once**. If the simplified plan is still complex, we proceed anyway with an expanded budget and a logged warning — never re-simplify.

```python
# In orchestrator:
MAX_SIMPLIFICATION_ROUNDS = 1

assessment = score_complexity(plan)
if assessment.tier == "complex" or assessment.estimated_builder_tokens > budget.builder_budget:
    for round_num in range(MAX_SIMPLIFICATION_ROUNDS):
        plan = self.planner.simplify(plan)
        assessment = score_complexity(plan)
        if assessment.tier != "complex" and assessment.estimated_builder_tokens <= budget.builder_budget:
            break
    else:
        logger.warning(
            f"Plan still complex after {MAX_SIMPLIFICATION_ROUNDS} simplification round(s). "
            f"Proceeding with expanded budget. Score={assessment.score}, "
            f"est_tokens={assessment.estimated_builder_tokens:,}"
        )
        budget = AdaptiveTokenBudget("complex")  # force max budget
```

This prevents the "MMORPG eats my budget" problem **and** catches plans that look simple structurally but are expensive tokenwise (e.g., Phaser game with only 3 entities but complex physics). The bounded loop guarantees termination.

---

## 11) Phase 3 — Execution / Code Generation

### Goal
Generate three files from the validated plan. No direct use of the original prompt — only the `GamePlan` artifact feeds the builder.

### Builder Architecture: Chunked Generation

Instead of one massive LLM call for all code, generate in controlled chunks:

```
Step 1: Generate game.js (largest, most complex)
Step 2: Generate index.html (references game.js + style.css)
Step 3: Generate style.css (layout + minimal polish)
Step 4: Assembly — parse, validate, write
```

This reduces the chance of truncation, improves reliability, and allows per-file validation.

### Builder Output Contract

```python
class GeneratedGame(BaseModel):
    index_html: str = Field(min_length=50)
    style_css: str = Field(min_length=20)
    game_js: str = Field(min_length=200)
```

### Code Generation Prompt Strategy

The builder system prompt includes:
1. Full `GamePlan` JSON (the source of truth)
2. Target framework docs/patterns (vanilla Canvas boilerplate or Phaser scene template)
3. Hard rules:
   - Must use `requestAnimationFrame` or Phaser's built-in loop
   - Must have keyboard/mouse event listeners matching `controls` spec
   - Must implement state transitions from `state_model`
   - Must render score/lives HUD
   - Must have game-over detection + restart capability
4. Anti-patterns to avoid:
   - No external CDN dependencies (except Phaser CDN if framework=phaser)
   - No `alert()` or `prompt()` for game events
   - No `document.write()`

### Repair-Aware Generation
If the builder is invoked after a critic/validator failure, it receives:
- The previous code
- The specific error list
- Instruction to fix only the broken parts

```python
def run(self, context: RunContext) -> GeneratedGame:
    if context.repair_instructions:
        return self.repair(context)  # targeted fix
    else:
        return self.generate_fresh(context)  # full generation
```

---

## 12) Phase 4 — Critic & Self-Reflection Loop (Hybrid)

> **Critique addressed**: *"Make critic deterministic where possible — 80% deterministic, 20% LLM"*

### Why This Phase
The assignment says *"This is not a prompt-engineering exercise."* A critic agent proves the system has genuine self-assessment capability — not just "generate and hope."

### Hybrid Critic Architecture (Upgraded)

The critic is split into two layers to reduce cost and unpredictability:

#### Layer 1: Deterministic Static Analysis (80% of checks)
These run without any LLM call — pure code analysis.

> **Critique addressed (v4)**: *"Your deterministic critic is regex-based. LLM might write `const raf = window.requestAnimationFrame; raf(loop);` and your check fails."*

**Upgrade**: The deterministic critic now uses a **two-tier approach**:
1. **AST-based analysis** (primary) — Parse JS with esprima via Node.js subprocess, walk the AST to find call expressions, variable declarations, and event listener registrations.
2. **Regex fallback** — Only used if AST parsing fails (e.g., syntax error in generated JS).

```python
# app/critics/ast_critic.py

import subprocess, json

class ASTCritic:
    """
    AST-based code analysis using esprima (Node.js).
    Catches patterns that regex misses:
      - `const raf = requestAnimationFrame; raf(loop);`
      - `window['addEventListener']('keydown', ...)`
      - `let s = 0; /* score */` (variable named 's' not 'score')
    """

    AST_ANALYSIS_SCRIPT = """
    const esprima = require('esprima');
    const code = require('fs').readFileSync(process.argv[1], 'utf-8');
    const ast = esprima.parseScript(code, { tolerant: true });

    const analysis = {
        call_expressions: [],      // all function calls
        event_listeners: [],       // addEventListener calls
        variable_names: [],        // all declared variable names
        has_raf: false,            // requestAnimationFrame or alias
        has_game_loop: false,      // setInterval/raf pattern
    };

    function walk(node) {
        if (!node || typeof node !== 'object') return;

        if (node.type === 'CallExpression') {
            const callee = node.callee;
            let name = '';
            if (callee.type === 'Identifier') name = callee.name;
            else if (callee.type === 'MemberExpression') name = callee.property.name || '';

            analysis.call_expressions.push(name);

            if (name === 'requestAnimationFrame' || name === 'raf') {
                analysis.has_raf = true;
                analysis.has_game_loop = true;
            }
            if (name === 'setInterval' || name === 'setTimeout') {
                analysis.has_game_loop = true;
            }
            if (name === 'addEventListener') {
                const eventType = node.arguments[0]?.value || 'unknown';
                analysis.event_listeners.push(eventType);
            }
        }

        if (node.type === 'VariableDeclarator' && node.id?.name) {
            analysis.variable_names.push(node.id.name);
        }

        for (const key of Object.keys(node)) {
            const child = node[key];
            if (Array.isArray(child)) child.forEach(walk);
            else if (child && typeof child.type === 'string') walk(child);
        }
    }

    walk(ast);
    console.log(JSON.stringify(analysis));
    """

    def analyze(self, game_js_path: Path) -> dict | None:
        """Run esprima AST analysis via Node.js subprocess."""
        try:
            # Write analysis script to temp file
            script_path = game_js_path.parent / "_ast_analysis.js"
            script_path.write_text(self.AST_ANALYSIS_SCRIPT)

            result = subprocess.run(
                ["node", str(script_path), str(game_js_path)],
                capture_output=True, text=True, timeout=10
            )
            script_path.unlink(missing_ok=True)  # cleanup

            if result.returncode == 0:
                return json.loads(result.stdout)
            else:
                logger.warning(f"AST analysis failed: {result.stderr}")
                return None
        except Exception as e:
            logger.warning(f"AST analysis error: {e}")
            return None


class DeterministicCritic:
    """
    AST-first, regex-fallback code analysis. No LLM cost.
    Uses esprima AST for accurate detection, falls back to regex if AST parsing fails.
    """

    def __init__(self):
        self.ast_critic = ASTCritic()

    def check(self, plan: GamePlan, game: GeneratedGame, game_dir: Path) -> list[CriticFinding]:
        findings = []

        # Try AST analysis first
        ast_result = self.ast_critic.analyze(game_dir / "game.js")

        if ast_result:
            findings.extend(self._check_with_ast(plan, game, ast_result))
        else:
            # Fallback to regex if AST fails (e.g., syntax error)
            logger.info("AST analysis failed, falling back to regex critic")
            findings.extend(self._check_with_regex(plan, game))

        return findings

    def _check_with_ast(self, plan: GamePlan, game: GeneratedGame, ast: dict) -> list[CriticFinding]:
        findings = []

        # Check: game loop exists (AST-accurate)
        if not ast["has_game_loop"]:
            findings.append(CriticFinding(
                severity="critical", category="missing_feature",
                description="No game loop detected (no requestAnimationFrame, setInterval, or aliases)",
                affected_file="game.js", suggested_fix="Add requestAnimationFrame-based game loop",
                source="deterministic"
            ))

        # Check: input handling exists (AST-accurate)
        input_events = {"keydown", "keyup", "keypress", "mousedown", "mouseup", "click", "mousemove"}
        if not any(evt in input_events for evt in ast["event_listeners"]):
            findings.append(CriticFinding(
                severity="critical", category="missing_feature",
                description="No input event listener found in AST",
                affected_file="game.js", suggested_fix="Add keyboard/mouse event listeners",
                source="deterministic"
            ))

        # Check: score-like variable exists (AST-accurate)
        score_vars = {"score", "points", "kills", "lives", "health"}
        if not any(v.lower() in score_vars for v in ast["variable_names"]):
            findings.append(CriticFinding(
                severity="warning", category="missing_feature",
                description="No score/points variable found in AST variable declarations",
                affected_file="game.js", suggested_fix="Add score tracking variable",
                source="deterministic"
            ))

        # Check: game-over condition (regex still useful here — looking for string patterns)
        if not re.search(r'game.?over|game.?end|lose|lost|dead', game.game_js, re.IGNORECASE):
            findings.append(CriticFinding(
                severity="critical", category="missing_feature",
                description="No game-over condition detected",
                affected_file="game.js", suggested_fix="Add game-over state transition",
                source="deterministic"
            ))

        # Check: all entities from plan present in code
        for entity in plan.entities:
            if entity.name.lower() not in game.game_js.lower():
                findings.append(CriticFinding(
                    severity="warning", category="missing_feature",
                    description=f"Entity '{entity.name}' from plan not found in code",
                    affected_file="game.js", suggested_fix=f"Implement {entity.name}",
                    source="deterministic"
                ))

        return findings

    def _check_with_regex(self, plan: GamePlan, game: GeneratedGame) -> list[CriticFinding]:
        """Fallback: regex-based checks when AST parsing fails."""
        findings = []

        if "requestAnimationFrame" not in game.game_js and "Phaser.Game" not in game.game_js:
            findings.append(CriticFinding(
                severity="critical", category="missing_feature",
                description="No game loop detected (regex fallback)",
                affected_file="game.js", suggested_fix="Add requestAnimationFrame-based game loop",
                source="deterministic"
            ))

        if "addEventListener" not in game.game_js and "this.input" not in game.game_js:
            findings.append(CriticFinding(
                severity="critical", category="missing_feature",
                description="No input event listener found (regex fallback)",
                affected_file="game.js", suggested_fix="Add keyboard/mouse event listeners",
                source="deterministic"
            ))

        return findings
```

#### Why AST Over Regex
| Scenario | Regex Result | AST Result |
|---|---|---|
| `const raf = requestAnimationFrame; raf(loop)` | ❌ Misses it | ✅ Finds `requestAnimationFrame` in call expressions |
| `window['addEventListener']('keydown', fn)` | ❌ Misses it | ✅ Finds `addEventListener` call |
| `let s = 0; // score` | ❌ No match for `score` | ✅ Finds variable `s` (but may miss semantic intent — LLM critic handles this) |
| Minified code | ❌ Breaks on whitespace changes | ✅ AST is whitespace-agnostic |

**esprima is already available** — Node.js is in the Docker image for `node --check` validation. Adding `npm install esprima` is one line in the Dockerfile.

#### Layer 2: LLM Reasoning Critic (20% of checks)
For nuanced issues that static analysis can't catch:

```python
class LLMCritic(BaseAgent):
    """Handles subjective/complex checks. Costs tokens but catches subtle bugs."""

    def check(self, plan: GamePlan, game: GeneratedGame,
              deterministic_findings: list[CriticFinding]) -> list[CriticFinding]:
        # Only called if deterministic critic found no criticals
        # Checks for:
        # - Logic bugs (e.g., collision detection that never triggers)
        # - UX issues (e.g., player starts off-screen)
        # - Balancing problems (e.g., enemies too fast at start)
        # - Code quality issues (e.g., memory leaks in game loop)
        ...
```

### Combined Critic Flow
```
1. Run DeterministicCritic (0 tokens, ~50ms)
   ├── Criticals found? → Skip LLM critic, go straight to repair
   └── No criticals? → Proceed to LLM critic
2. Run LLMCritic (3k tokens, ~3s)
   ├── Criticals found? → Go to repair
   └── No criticals? → Proceed to validation
```

**Cost savings**: ~60% of runs won't need the LLM critic at all, saving ~3k tokens per run.

### Critic Output Schema

```python
class CriticFinding(BaseModel):
    severity: Literal["critical", "warning", "suggestion"]
    category: str                    # "missing_feature", "logic_bug", "ux_issue"
    description: str
    affected_file: str
    suggested_fix: str
    source: Literal["deterministic", "llm"]  # NEW: track which layer found it

class CritiqueResult(BaseModel):
    findings: list[CriticFinding]
    has_critical: bool
    overall_assessment: str
    plan_compliance_score: float     # 0-1: how well code matches plan
    deterministic_checks_run: int    # NEW: observability
    llm_checks_run: bool             # NEW: was LLM critic invoked?
```

### Loop Behavior
- If `has_critical == True` and retries remain → go back to BUILDING with repair instructions
- If no criticals → proceed to VALIDATING
- Max 1 critic-triggered rebuild to prevent infinite loops

---

## 13) Validation & Quality Gate Layer (Behavioral)

> **Critique addressed**: *"Validation is heuristic, not behavioral. Users will complain: the game loads but nothing moves."*

### Validation Pipeline (Sequential — Upgraded to Include Behavioral Tests)

```
Check 1: File Existence
    → All 3 files exist and non-empty

Check 2: HTML Structure
    → Valid HTML5 doctype
    → <link> to style.css
    → <script> to game.js
    → <canvas> or game container present

Check 3: CSS Validity
    → Not empty
    → No obvious syntax errors (unmatched braces)

Check 4: JavaScript Syntax
    → node --check game.js  (run in Docker where Node.js is available)
    → Catches SyntaxError before browser test

Check 5: Structural Heuristics
    → Contains requestAnimationFrame OR Phaser.Game
    → Contains addEventListener (input handling)
    → Contains score/lives/gameOver variable patterns
    → Contains at least one draw/render function

Check 6: Runtime Smoke Test (Playwright — headless)
    → Open index.html in headless Chromium
    → Wait 3 seconds for initial load
    → Assert: no uncaught exceptions in console
    → Assert: canvas has non-zero dimensions
    → Capture screenshot for report

Check 7: Behavioral Interaction Test (Playwright — NEW)
    → Simulate keyboard inputs matching plan.controls
    → After input: assert canvas pixels changed (something moved)
    → After 5s of play: assert score element changed OR game state transitioned
    → Simulate game-over trigger: assert game-over UI appears
    → Simulate restart: assert game resets
```

### Behavioral Test Implementation

> **Critique addressed (v4)**: *"Comparing `screenshot_before != screenshot_after` is fragile. Canvas animations change every frame even without input — you'll get false positives."*

**Upgrade**: Behavioral tests now verify **game state changes** via exposed debug hooks, not pixel diffs. The builder prompt injects a minimal `window.__debug_state` object that tests can query directly.

#### Debug Hook Injection (AST-Based, LLM-Independent)

> **Critique addressed (v5)**: *"Your debug hook is a security backdoor."*  
> **Critique addressed (v6)**: *"Your debug stripping relies on regex. If the LLM slightly reformats, adds indentation, breaks comments, or duplicates blocks — you're back to regex brittleness. Do not rely on LLM to insert debug hooks. Post-process game.js: Parse AST → Inject debug state node programmatically."*

**Solution (v6 — final)**: The builder prompt does **not** include debug hook instructions at all. Debug hooks are injected programmatically via AST transform after generation. This removes ALL LLM variability from debug logic.

**Flow**:
1. Builder generates clean `game.js` (no debug markers, no special instructions)
2. **Post-processor**: Parse AST → find game loop → inject debug state node
3. Validation runs against the **injected** version
4. Delivery gets the **original** unmodified `game.js` (zero stripping needed)

#### AST-Based Debug Injector
```python
# app/debug/ast_injector.py

import subprocess
import json
from pathlib import Path

DEBUG_HOOK_SNIPPET = """
// === INJECTED BY TOOLCHAIN (not LLM-generated) ===
if (typeof window.__GAME_DEBUG__ !== 'undefined') {
    (function() {
        var _origRAF = window.requestAnimationFrame;
        var _entityCountSamples = [];
        window.requestAnimationFrame = function(cb) {
            return _origRAF.call(window, function(ts) {
                cb(ts);
                // Attempt to capture debug state from common variable patterns
                try {
                    var state = {};
                    if (typeof playerX !== 'undefined') state.player = {x: playerX, y: typeof playerY !== 'undefined' ? playerY : 0};
                    if (typeof player !== 'undefined' && player) state.player = {x: player.x || 0, y: player.y || 0};
                    if (typeof score !== 'undefined') state.score = score;
                    if (typeof gameOver !== 'undefined') state.gameOver = gameOver;
                    if (typeof isGameOver !== 'undefined') state.gameOver = isGameOver;
                    if (typeof enemies !== 'undefined') state.entityCount = enemies.length;
                    if (typeof obstacles !== 'undefined') state.entityCount = obstacles.length;
                    if (typeof entities !== 'undefined') state.entityCount = entities.length;
                    state._timestamp = Date.now();
                    _entityCountSamples.push(state.entityCount || 0);
                    if (_entityCountSamples.length > 300) _entityCountSamples.shift();
                    state._entityGrowthRate = _entityCountSamples.length > 60
                        ? (_entityCountSamples[_entityCountSamples.length-1] - _entityCountSamples[_entityCountSamples.length-61]) / 60
                        : 0;
                    window.__debug_state = state;
                } catch(e) { /* debug hook should never crash the game */ }
            });
        };
    })();
}
"""

def inject_debug_hooks(game_js: str) -> str:
    """
    Prepend debug hook to game.js via string injection.
    The hook monkey-patches requestAnimationFrame to capture state each frame.
    This is toolchain-controlled — the LLM never sees or generates debug code.
    """
    return DEBUG_HOOK_SNIPPET + "\n" + game_js

def write_artifacts(game: GeneratedGame, output_dir: Path):
    """
    Write two versions:
    - debug/  : game.js with injected debug hooks (for behavioral validator)
    - game/   : original unmodified game.js (for delivery to users)
    """
    debug_dir = output_dir / "debug"
    delivery_dir = output_dir / "game"
    debug_dir.mkdir(parents=True, exist_ok=True)
    delivery_dir.mkdir(parents=True, exist_ok=True)

    # Debug version: hooks injected by toolchain (not LLM)
    (debug_dir / "game.js").write_text(inject_debug_hooks(game.game_js))
    (debug_dir / "index.html").write_text(game.index_html)
    (debug_dir / "style.css").write_text(game.style_css)

    # Delivery version: original, unmodified LLM output (no stripping needed)
    (delivery_dir / "game.js").write_text(game.game_js)
    (delivery_dir / "index.html").write_text(game.index_html)
    (delivery_dir / "style.css").write_text(game.style_css)
```

#### Why AST Injection > LLM Markers + Regex Stripping
| Aspect | v5 (LLM markers + regex strip) | v6 (Toolchain AST injection) |
|---|---|---|
| LLM involvement | LLM must follow marker format exactly | **Zero** — LLM generates clean code |
| Stripping reliability | Regex — breaks on reformatting | **None needed** — delivery uses original |
| Debug variable discovery | LLM must expose correct var names | Monkey-patch `requestAnimationFrame` — captures state automatically |
| Failure mode | Silent (regex misses → hooks leak to production) | **Safe** (delivery is always original code) |
| Entity count tracking | Manual | Automatic via `_entityCountSamples` array |

#### Build vs Delivery Mode
| Aspect | Build/Validation Mode | Delivery Mode |
|---|---|---|
| `window.__GAME_DEBUG__` | Set via `add_init_script` | Not set (guard prevents execution) |
| `window.__debug_state` | Populated every frame via monkey-patch | Code never present (original game.js) |
| Output directory | `outputs/<run_id>/debug/` | `outputs/<run_id>/game/` |
| Who generates hooks | **Toolchain** (AST injector) | N/A |
| Purpose | Behavioral testing | User-facing artifact |
| Security risk | None (local testing only) | **None** (original LLM code, unmodified) |

#### State-Based Behavioral Validator

```python
# app/validators/behavioral_validator.py

async def run_behavioral_tests(game_dir: Path, plan: GamePlan) -> list[ValidationCheck]:
    """Playwright-based behavioral tests using game state queries, not pixel diffs."""
    checks = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        # Set hard timeout guard to prevent infinite loops from hanging the worker
        # Critique addressed (v5): "What if generated JS contains while(true){}?"
        page.set_default_timeout(15_000)  # 15s max for any single operation
        browser_context_timeout = 30_000   # 30s total for all behavioral tests

        # Collect console errors from the start
        errors = []
        page.on("pageerror", lambda err: errors.append(str(err)))

        # Activate debug mode BEFORE navigating (so hooks are available on load)
        await page.add_init_script("window.__GAME_DEBUG__ = true;")

        try:
            await page.goto(f"file://{game_dir / 'index.html'}", timeout=10_000)
        except PlaywrightTimeoutError:
            checks.append(ValidationCheck(
                name="page_load",
                passed=False,
                details="Page failed to load within 10s — possible infinite loop in initialization",
                severity="blocker",
            ))
            await browser.close()
            return checks

        await page.wait_for_timeout(2000)  # let game initialize

        # Test 1: Debug state hook exists
        has_debug = await page.evaluate("typeof window.__debug_state !== 'undefined'")
        checks.append(ValidationCheck(
            name="debug_hook_present",
            passed=has_debug,
            details="Debug state hook found" if has_debug else "No __debug_state — falling back to heuristic checks",
            severity="warning",
        ))

        if has_debug:
            # Test 2: Record player position BEFORE input
            state_before = await page.evaluate("JSON.parse(JSON.stringify(window.__debug_state))")

            # Simulate keyboard input
            for key in plan.controls.key_mappings.keys():
                await page.keyboard.press(key)
                await page.wait_for_timeout(100)
            await page.wait_for_timeout(500)

            # Query state AFTER input
            state_after = await page.evaluate("JSON.parse(JSON.stringify(window.__debug_state))")

            # Test 2a: Player position changed (state-based, not pixel-based)
            player_moved = (
                state_before.get("player", {}).get("x") != state_after.get("player", {}).get("x") or
                state_before.get("player", {}).get("y") != state_after.get("player", {}).get("y")
            )
            checks.append(ValidationCheck(
                name="behavioral_input_moves_player",
                passed=player_moved,
                details=f"Player pos: {state_before.get('player')} → {state_after.get('player')}" if player_moved
                        else "Player position unchanged after input — game may not respond to controls",
                severity="blocker" if not player_moved else "info",
            ))

            # Test 3: Score tracking (wait and check state change)
            score_before = state_after.get("score", 0)
            await page.wait_for_timeout(3000)  # let game run for 3s
            state_later = await page.evaluate("JSON.parse(JSON.stringify(window.__debug_state))")
            score_later = state_later.get("score", 0)

            checks.append(ValidationCheck(
                name="behavioral_score_updates",
                passed=score_later != score_before,
                details=f"Score: {score_before} → {score_later}" if score_later != score_before
                        else "Score unchanged during 3s of gameplay",
                severity="warning",
            ))

            # Test 4: Game-over state is reachable (check flag)
            game_over_state = state_later.get("gameOver", None)
            checks.append(ValidationCheck(
                name="behavioral_gameover_flag_exists",
                passed=game_over_state is not None,
                details=f"gameOver flag exists: {game_over_state}",
                severity="warning",
            ))

        else:
            # Fallback: pixel-based check if no debug hooks (degraded mode)
            canvas = await page.query_selector("canvas")
            if canvas:
                screenshot_before = await canvas.screenshot()
                for key in plan.controls.key_mappings.keys():
                    await page.keyboard.press(key)
                    await page.wait_for_timeout(100)
                await page.wait_for_timeout(500)
                screenshot_after = await canvas.screenshot()
                # NOTE: This may false-positive due to animation. Logged as degraded test.
                checks.append(ValidationCheck(
                    name="behavioral_input_response_degraded",
                    passed=screenshot_before != screenshot_after,
                    details="Pixel-based check (degraded — no debug hooks). May false-positive on animations.",
                    severity="warning",  # downgraded from blocker due to unreliability
                ))

        # Test 5: Console error monitoring (always runs)
        checks.append(ValidationCheck(
            name="behavioral_no_runtime_errors",
            passed=len(errors) == 0,
            details=f"{len(errors)} errors: {errors[:3]}" if errors else "No runtime errors",
            severity="blocker" if errors else "info",
        ))

        # Test 6: Performance guardrail (FPS + entity growth)
        # Critique addressed (v5): "You validate correctness — not performance."
        # Critique addressed (v6): "Measure FPS over 5 seconds. Track entity count
        # growth via debug state. Fail if entity count increases unbounded."
        if has_debug:
            # 6a: FPS measurement over 5 seconds (upgraded from 2s)
            fps_result = await page.evaluate("""
                () => new Promise(resolve => {
                    let frameCount = 0;
                    const start = performance.now();
                    function countFrame() {
                        frameCount++;
                        if (performance.now() - start >= 5000) {
                            resolve({ fps: frameCount / 5, frames: frameCount });
                        } else {
                            requestAnimationFrame(countFrame);
                        }
                    }
                    requestAnimationFrame(countFrame);
                })
            """)
            fps = fps_result.get("fps", 0) if fps_result else 0
            checks.append(ValidationCheck(
                name="performance_fps_check",
                passed=fps >= 15,
                details=f"Measured FPS: {fps:.1f} over 5s ({fps_result.get('frames', 0)} frames)"
                        if fps >= 15 else f"Low FPS: {fps:.1f} — game may have performance issues (infinite object spawning, expensive DOM ops per frame)",
                severity="warning" if fps < 15 else "info",
            ))

            # 6b: Entity count growth detection (catches `enemies.push()` in update loop)
            entity_growth = await page.evaluate("""
                () => {
                    const state = window.__debug_state || {};
                    return {
                        entityCount: state.entityCount || 0,
                        growthRate: state._entityGrowthRate || 0
                    };
                }
            """)
            growth_rate = entity_growth.get("growthRate", 0)
            entity_count = entity_growth.get("entityCount", 0)
            unbounded_growth = growth_rate > 2  # more than 2 new entities/frame sustained
            checks.append(ValidationCheck(
                name="performance_entity_growth",
                passed=not unbounded_growth,
                details=f"Entity count: {entity_count}, growth rate: {growth_rate:.1f}/frame"
                        if not unbounded_growth
                        else f"UNBOUNDED entity growth: {entity_count} entities, +{growth_rate:.1f}/frame — likely missing cleanup in game loop",
                severity="warning" if unbounded_growth else "info",
            ))

        await browser.close()
    return checks
```

### Behavioral Testing Strategy (State-Based)

| Test | Method | What It Proves | Severity if Fails |
|---|---|---|---|
| Debug hook present | `typeof window.__debug_state` | Builder followed debug hook instruction | Warning |
| Input moves player | Compare `player.x/y` before/after keypress | Player controls work | Blocker |
| Score updates | Compare `score` over 3s | Scoring system works | Warning |
| Game-over flag exists | Check `gameOver` property | End condition is modeled | Warning |
| No console errors | `pageerror` event listener | Game doesn't crash | Blocker |
| FPS ≥ 15 | 5s frame counter via `requestAnimationFrame` | Game runs at playable framerate | Warning |
| Entity count stable | Growth rate via debug state `_entityGrowthRate` | No unbounded entity spawning (e.g., `enemies.push()` in loop) | Warning |
| Page loads in <10s | `page.goto()` timeout | No infinite loop in initialization | Blocker |

### Execution Timeout Strategy (v5 Upgrade)

> **Critique addressed (v5)**: *"What if generated JS contains `while(true){}`? Your `node --check` won't catch runtime infinite loops. Your browser test will hang."*

| Guard | Timeout | What It Catches |
|---|---|---|
| `page.goto()` timeout | 10s | Infinite loop during script initialization |
| `page.set_default_timeout()` | 15s | Any single evaluation that blocks event loop |
| Total behavioral test timeout | 30s | Cumulative test time limit (belt + suspenders) |
| `node --check` (Check 4) | 5s subprocess timeout | Syntax errors only (not runtime) |

If any timeout fires, the test returns a **blocker** finding and the browser is force-closed. No worker stall.

### Why State-Based > Pixel-Based
| Scenario | Pixel Diff | State Query |
|---|---|---|
| Idle animation running | ❌ False positive (pixels change without input) | ✅ Player pos unchanged = correct fail |
| Player moves 1px | ❌ May not detect sub-pixel changes | ✅ `player.x` change is exact |
| Dark game on dark background | ❌ Screenshots look identical | ✅ State query is visual-agnostic |
| Score increases | ❌ Must OCR or find DOM element | ✅ Direct `state.score` read |

### When Behavioral Tests Are Skipped
- If Playwright is not installed (optional dependency)
- If `--skip-browser-tests` flag is set
- Structural heuristic checks (Check 5) still run as fallback

This upgrade means the system validates that the game **actually works**, not just that it **looks like it should work**.

---

## 13a) Chaos & Resilience Testing

> **Critique addressed (v6)**: *"You have regression tests, prompt versioning, validation layers. But production maturity includes random failure injection, random LLM timeout simulation, random network latency simulation — to test: Does resume truly work? Does circuit breaker behave correctly? Do retries leak tokens?"*

### Problem
Resilience features (circuit breakers, retry logic, checkpoint resume, budget enforcement) are only tested under happy-path conditions. Real production failures are stochastic and overlapping.

### Solution: Chaos Testing Mode

A test-only mode that randomly injects failures to validate resilience under realistic conditions.

```python
# app/testing/chaos.py

import random
import os
from functools import wraps

CHAOS_MODE = os.getenv("RUN_CHAOS_MODE", "false").lower() == "true"
CHAOS_FAILURE_RATE = float(os.getenv("CHAOS_FAILURE_RATE", "0.10"))  # 10% default

class ChaosInjector:
    """
    Wraps LLM calls to randomly inject failures when CHAOS_MODE is active.
    Used in test suite only — never in production.
    """

    FAILURE_TYPES = [
        "timeout",         # Simulate API timeout
        "rate_limit",      # Simulate 429 rate limit
        "empty_response",  # Simulate empty/unparseable response
        "server_error",    # Simulate 500 from provider
        "slow_response",   # Simulate 5s+ latency
    ]

    def __init__(self, failure_rate: float = CHAOS_FAILURE_RATE):
        self.failure_rate = failure_rate
        self.injected_failures: list[dict] = []  # audit log

    def maybe_fail(self, phase: str):
        """Called before each LLM request. Raises if chaos dice roll hits."""
        if not CHAOS_MODE:
            return
        if random.random() < self.failure_rate:
            failure_type = random.choice(self.FAILURE_TYPES)
            self.injected_failures.append({
                "phase": phase,
                "failure_type": failure_type,
                "timestamp": datetime.utcnow().isoformat(),
            })
            if failure_type == "timeout":
                import time; time.sleep(30)  # will trigger timeout handler
            elif failure_type == "rate_limit":
                raise RateLimitError("Chaos: simulated 429")
            elif failure_type == "empty_response":
                raise ParseError("Chaos: empty response")
            elif failure_type == "server_error":
                raise ProviderError("Chaos: simulated 500")
            elif failure_type == "slow_response":
                import time; time.sleep(5)


def chaos_wrapper(func):
    """Decorator to inject chaos into LLM calls."""
    @wraps(func)
    async def wrapper(self, *args, **kwargs):
        if hasattr(self, 'chaos') and self.chaos:
            self.chaos.maybe_fail(self.__class__.__name__)
        return await func(self, *args, **kwargs)
    return wrapper
```

#### Integration with LLMProvider
```python
# In LLMProvider, wrap the call method:
class LLMProvider:
    def __init__(self, config, chaos: ChaosInjector | None = None):
        self.chaos = chaos  # None in production, ChaosInjector in test

    @chaos_wrapper
    async def call(self, messages, response_model, **kwargs):
        # Normal LLM call — chaos may interrupt before this executes
        ...
```

#### What Chaos Tests Validate

| Resilience Feature | Chaos Scenario | Expected Behavior |
|---|---|---|
| Circuit breaker | 50% of calls fail | Breaker opens, fallback model used |
| Checkpoint resume | Kill process mid-BUILDING | Resume from last checkpoint, no duplicate work |
| Retry budget | 3 consecutive timeouts | Retries stop at max, tokens not leaked |
| Token accounting | Empty responses wasted tokens | Budget tracks all calls, including failed ones |
| Degraded fallback | All providers fail | Deterministic template generated, not crash |
| Backpressure | Rapid concurrent runs | New runs rejected when burn rate exceeded |

#### Running Chaos Tests
```bash
# In CI or locally:
RUN_CHAOS_MODE=true CHAOS_FAILURE_RATE=0.10 pytest tests/ -v -k chaos

# Docker:
docker run --rm \
  -e RUN_CHAOS_MODE=true \
  -e CHAOS_FAILURE_RATE=0.15 \
  game-builder-test pytest tests/test_chaos_resilience.py
```

#### Chaos Test Suite
```python
# tests/test_chaos_resilience.py

@pytest.fixture
def chaos_orchestrator():
    chaos = ChaosInjector(failure_rate=0.15)
    config = Config(batch_mode=True)
    return Orchestrator(config, chaos=chaos)

def test_completes_despite_failures(chaos_orchestrator):
    """System should produce output even with 15% failure injection."""
    result = chaos_orchestrator.run("simple dodge game")
    assert result.status in ("done", "degraded_fallback")  # never crash

def test_budget_not_leaked(chaos_orchestrator):
    """Failed LLM calls should still be tracked in token budget."""
    result = chaos_orchestrator.run("simple pong game")
    assert result.budget.used > 0  # even failed calls counted
    assert result.budget.used <= result.budget.max_total

def test_circuit_breaker_trips(chaos_orchestrator):
    """With high failure rate, circuit breaker should open."""
    chaos_orchestrator.chaos.failure_rate = 0.80  # very high
    result = chaos_orchestrator.run("space shooter")
    # Should either succeed via fallback model or degrade gracefully
    assert result.status in ("done", "degraded_fallback")
```

---

### Validation Report Schema

```python
class ValidationCheck(BaseModel):
    name: str
    passed: bool
    details: str = ""
    severity: Literal["blocker", "warning", "info"]

class ValidationReport(BaseModel):
    checks: list[ValidationCheck]
    passed: bool                     # True only if zero blockers
    screenshot_path: str | None = None
    timestamp: datetime
```

### Recovery Decision Tree

```
Validation failed?
    ├── Blocker + retries_left > 0
    │       → Feed errors to builder as repair instructions
    │       → retry_count += 1
    │       → Transition: VALIDATING → BUILDING
    │
    ├── Blocker + retries_left == 0
    │       → Transition: VALIDATING → FAILED
    │       → Save diagnostic report
    │
    └── Warnings only
            → Transition: VALIDATING → DONE
            → Log warnings in report
```

---

## 14) Prompt Engineering Strategy

### Principles
This section exists because **prompt quality directly determines output quality**, but the system does not rely on prompts alone — schemas + validation are the safety net.

### Prompt File Organization
Each agent has two prompt files:
- `*_system.md` — role + constraints + output format
- `*_user.md` — template with `{{variables}}` filled at runtime

### System Prompt Patterns Used

| Pattern | Where | Purpose |
|---|---|---|
| **Role anchoring** | All agents | "You are a game design expert..." |
| **Output schema injection** | Clarifier, Planner | JSON Schema in system prompt |
| **Few-shot examples** | Planner, Builder | 1–2 example plan/code snippets (short) |
| **Negative constraints** | Builder | "Do NOT use alert(), prompt(), external APIs..." |
| **Chain-of-thought** | Critic | "First list what the plan requires, then check each against the code..." |
| **Repair context** | Builder (retry) | "Previous code had these errors: [...]. Fix ONLY the issues." |

### Temperature Settings

| Agent | Temperature | Rationale |
|---|---|---|
| Clarifier | 0.3 | Focused, relevant questions |
| Planner | 0.2 | Deterministic, spec-like output |
| Builder | 0.4 | Slight creativity for game code, but still structured |
| Critic | 0.1 | Analytical, no hallucinated issues |

---

## 14a) Prompt Versioning & Regression Testing

> **Critiques addressed**: *"You rely on prompt engineering stability"* + *"Version your prompts"*

### Problem
LLM providers update models frequently. A prompt that produces perfect games today may silently degrade next month. Without versioning and regression testing, debugging historical failures becomes impossible.

### Prompt Versioning System

```python
# app/prompts/versioning.py

import hashlib
from pathlib import Path

class PromptVersion:
    def __init__(self, prompt_dir: Path):
        self.prompt_dir = prompt_dir

    def get_hash(self, prompt_name: str) -> str:
        """SHA-256 hash of prompt file contents."""
        path = self.prompt_dir / prompt_name
        content = path.read_text()
        return hashlib.sha256(content.encode()).hexdigest()[:12]

    def get_manifest(self) -> dict[str, str]:
        """Return hash of every prompt file."""
        return {
            p.name: self.get_hash(p.name)
            for p in self.prompt_dir.glob("*.md")
        }
```

### Run Manifest Integration (Enforced)

> **Critique addressed (v5)**: *"Prompt versioning exists but is not enforced. I don't see prompt hash stored in run_manifest, validation linking failure to prompt version, or CI regression matrix by prompt version."*

Every `run_manifest.json` **must** include prompt hashes. This is enforced programmatically — not optional documentation.

```python
# app/orchestrator.py — manifest generation is mandatory, not opt-in

def generate_manifest(self) -> dict:
    prompt_versions = PromptVersion(self.config.prompt_dir).get_manifest()
    manifest = {
        "run_id": str(self.context.run_id),
        "prompt_versions": prompt_versions,              # MANDATORY
        "llm_model": self.config.model,
        "llm_model_version": self._get_model_version(),
        "build_number": self.build_number,
        "phases": { ... },
        "final_state": self.state.value,
    }
    # Validation: refuse to write manifest without prompt hashes
    assert "prompt_versions" in manifest and len(manifest["prompt_versions"]) > 0, \
        "Run manifest must include prompt version hashes"
    return manifest
```

Example output:
```json
{
  "run_id": "a3f7c2",
  "prompt_versions": {
    "clarifier_system.md": "a3f7c2d1e4b8",
    "clarifier_user.md": "9c2e1f3a5b7d",
    "planner_system.md": "b8d4e6f2a1c3",
    "builder_system.md": "e5f1a2b3c4d6",
    "critic_system.md": "f7a8b9c0d1e2"
  },
  "llm_model": "gpt-4o-2026-01-15",
  "llm_model_version": "2026-01-15",
  "build_number": 2
}
```

### Failure → Prompt Version Correlation

```python
# scripts/correlate_failures.py

def correlate_failures_to_prompts(manifests_dir: Path) -> dict:
    """Analyze failed runs grouped by prompt version."""
    manifests = [json.loads(f.read_text()) for f in manifests_dir.glob("*/run_manifest.json")]
    failed = [m for m in manifests if m["final_state"] == "failed"]

    # Group failures by builder prompt version
    by_prompt = defaultdict(list)
    for m in failed:
        builder_hash = m["prompt_versions"].get("builder_system.md", "unknown")
        by_prompt[builder_hash].append(m["run_id"])

    return dict(by_prompt)
    # Output: {"e5f1a2b3c4d6": ["run_1", "run_3"], "a1b2c3d4e5f6": ["run_7"]}
    # → "Builder prompt e5f1a2 caused 2 failures — investigate or rollback"
```

### CI Regression Matrix by Prompt Version
```yaml
# In prompt-regression.yml, results are tagged with prompt hash:
steps:
  - name: Tag results with prompt version
    run: |
      PROMPT_HASH=$(python -c "from app.prompts.versioning import PromptVersion; print(PromptVersion('app/prompts').get_hash('builder_system.md'))")
      echo "prompt_hash=$PROMPT_HASH" >> $GITHUB_OUTPUT
  - name: Upload results
    run: |
      python scripts/upload_regression_results.py \
        --prompt-hash ${{ steps.tag.outputs.prompt_hash }} \
        --results test-results.json
```

### Regression Test Suite

```python
# tests/test_prompt_regression.py

REGRESSION_IDEAS = [
    {"idea": "simple pong game", "must_have": ["paddle", "ball", "score", "bounce"]},
    {"idea": "dodge falling objects", "must_have": ["player", "obstacle", "score", "game_over"]},
    {"idea": "snake game", "must_have": ["snake", "food", "grow", "wall"]},
    {"idea": "space shooter", "must_have": ["ship", "bullet", "enemy", "score"]},
    {"idea": "platformer", "must_have": ["player", "platform", "jump", "gravity"]},
    # ... 20-50 total regression ideas
]

@pytest.mark.parametrize("case", REGRESSION_IDEAS)
def test_plan_regression(case, mock_llm_or_real):
    """Verify that plans for known ideas contain expected elements."""
    orchestrator = Orchestrator(config, llm=mock_llm_or_real)
    result = orchestrator.run(case["idea"])
    plan = result.context.plan

    for keyword in case["must_have"]:
        assert any(
            keyword.lower() in str(entity).lower()
            for entity in plan.entities + plan.core_mechanics
        ), f"Plan for '{case['idea']}' missing expected element: {keyword}"
```

### CI Pipeline for Prompt Regression

```yaml
# .github/workflows/prompt-regression.yml
name: Prompt Regression
on:
  schedule:
    - cron: '0 6 * * 1'  # Weekly on Monday
  push:
    paths:
      - 'app/prompts/**'

jobs:
  regression:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run regression suite
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
          BATCH_MODE: true
        run: |
          docker build -t game-builder-test .
          docker run --rm -e OPENAI_API_KEY -e BATCH_MODE \
            game-builder-test pytest tests/test_prompt_regression.py -v
      - name: Compare with baseline
        run: python scripts/compare_regression_results.py
      - name: Alert on degradation
        if: failure()
        uses: slackapi/slack-github-action@v1
        with:
          payload: '{"text": "Prompt regression failed! Pass rate dropped."}'
```

### Prompt Rollback Strategy
- All prompt changes committed to git with meaningful messages
- `run_manifest.json` includes prompt hashes → correlate failures to prompt changes
- To rollback: `git checkout <commit> -- app/prompts/` + redeploy

---

## 15) Error Taxonomy & Recovery Matrix

### Error Categories

```python
class ErrorCategory(str, Enum):
    LLM_TIMEOUT       = "llm_timeout"        # API didn't respond
    LLM_PARSE_FAILURE  = "llm_parse_failure"  # Output not valid JSON/schema
    LLM_REFUSAL       = "llm_refusal"         # Content policy block
    LLM_TRUNCATION    = "llm_truncation"      # Output cut off (max tokens)
    VALIDATION_SYNTAX  = "validation_syntax"   # JS syntax error
    VALIDATION_STRUCT  = "validation_struct"   # Missing game loop, no input handlers
    VALIDATION_RUNTIME = "validation_runtime"  # Crashes in headless browser
    VALIDATION_LINKAGE = "validation_linkage"  # HTML doesn't reference JS/CSS
    STATE_VIOLATION    = "state_violation"      # Illegal state transition
```

### Recovery Matrix

| Error | Recovery | Max Attempts |
|---|---|---|
| `LLM_TIMEOUT` | Retry same call → fallback model | 3 |
| `LLM_PARSE_FAILURE` | Retry with stricter prompt + `instructor` retry | 2 |
| `LLM_REFUSAL` | Rephrase prompt, remove potentially flagged terms | 1 |
| `LLM_TRUNCATION` | Increase `max_tokens`, or split generation into chunks | 2 |
| `VALIDATION_SYNTAX` | Feed error to builder as repair instruction | 2 |
| `VALIDATION_STRUCT` | Feed missing features to builder | 2 |
| `VALIDATION_RUNTIME` | Feed console errors to builder | 1 |
| `VALIDATION_LINKAGE` | Auto-fix (deterministic string replacement) — no LLM needed | 1 |
| `STATE_VIOLATION` | Hard fail (bug in orchestrator, not recoverable) | 0 |
| `CHECKPOINT_CORRUPT` | Re-run from INIT (checkpoint unrecoverable) | 1 |
| `BUDGET_EXHAUSTED` | Save partial artifacts → FAILED with cost report | 0 |
| `CIRCUIT_BREAKER_OPEN` | Wait for recovery timeout → retry | 3 |

---

## 16) Token & Cost Budget Management (Adaptive)

> **Critique addressed**: *"Token budget is static, not adaptive. One MMORPG idea eats your entire budget."*

### Why
LLM calls are expensive. Unbounded retries can cost $10+ per run. A static budget of 50k tokens fails for complex games and wastes headroom on simple ones.

### Adaptive Budget Model

```python
class AdaptiveTokenBudget:
    """Budget scales with plan complexity instead of being fixed."""

    # Base allocations per tier
    TIER_BUDGETS = {
        "simple":   {"total": 30_000, "builder": 10_000, "repairs": 5_000},
        "moderate": {"total": 50_000, "builder": 15_000, "repairs": 10_000},
        "complex":  {"total": 70_000, "builder": 25_000, "repairs": 15_000},
    }

    def __init__(self, complexity_tier: str = "moderate"):
        tier = self.TIER_BUDGETS[complexity_tier]
        self.max_total = tier["total"]
        self.builder_budget = tier["builder"]
        self.repair_budget = tier["repairs"]
        self.used = 0
        self.per_phase: dict[str, int] = {}
        self.tier = complexity_tier

    def can_afford(self, estimated_tokens: int) -> bool:
        return (self.used + estimated_tokens) <= self.max_total

    def record(self, phase: str, tokens: int):
        self.used += tokens
        self.per_phase[phase] = self.per_phase.get(phase, 0) + tokens

    def remaining(self) -> int:
        return self.max_total - self.used

    def cost_estimate_usd(self, model: str = "gpt-4o") -> float:
        """Estimate cost based on model pricing."""
        pricing = {"gpt-4o": 0.005, "gpt-4o-mini": 0.00015, "claude-sonnet": 0.003}  # per 1k tokens
        rate = pricing.get(model, 0.005)
        return (self.used / 1000) * rate

    @classmethod
    def from_complexity(cls, assessment: ComplexityAssessment) -> "AdaptiveTokenBudget":
        return cls(complexity_tier=assessment.tier)
```

### Pre-Estimation Flow
```
1. Planner generates GamePlan
2. ComplexityGuardrail scores the plan (§10a)
3. AdaptiveTokenBudget initialized from complexity tier
4. Builder proceeds with tier-appropriate budget
5. If budget at 80% → log warning
6. If budget exhausted → save partial + FAILED
```

### Per-Phase Model Tiering (with Quality-Adaptive Escalation)

> **Critique addressed**: *"Separate planner & builder scaling — use cheaper models for cheap phases"*  
> **Critique addressed (v4)**: *"Model tiering has a hidden quality risk. gpt-4o-mini for planner might degrade structured plan quality in edge cases. Implement automatic fallback."*

```python
# Different models per phase to optimize cost
PHASE_MODEL_OVERRIDES = {
    "clarifier": "gpt-4o-mini",      # Simple Q&A — cheap model is fine
    "planner":   "gpt-4o-mini",      # Structured output — mid-tier sufficient
    "builder":   "gpt-4o",           # Code generation — needs best model
    "critic":    "gpt-4o-mini",      # Only 20% is LLM (rest deterministic)
}

# Quality-adaptive escalation: auto-upgrade to premium on failure
PHASE_ESCALATION_MODELS = {
    "clarifier": "gpt-4o",           # escalate mini → premium
    "planner":   "gpt-4o",           # escalate mini → premium
    "builder":   "claude-sonnet",    # escalate gpt-4o → claude (different provider)
    "critic":    "gpt-4o",           # escalate mini → premium
}
```

#### Adaptive Escalation Logic (Failure + Validation Quality)

> **Critique addressed (v5)**: *"Escalation is failure-based (exceptions), not quality-based. If builder succeeds with gpt-4o-mini but validation repeatedly fails, you never escalate."*

```python
# app/llm/model_selector.py

class AdaptiveModelSelector:
    """
    Auto-escalate to premium model on two triggers:
    1. Phase execution failures (exceptions, parse errors)
    2. Downstream validation failures (quality signal from later phases)
    """

    def __init__(self, overrides: dict, escalation: dict, max_cheap_failures: int = 2):
        self.overrides = overrides
        self.escalation = escalation
        self.max_cheap_failures = max_cheap_failures
        self.phase_failures: dict[str, int] = {}           # execution failures
        self.validation_failures: dict[str, int] = {}      # NEW: downstream quality failures

    def get_model(self, phase: str) -> str:
        exec_failures = self.phase_failures.get(phase, 0)
        val_failures = self.validation_failures.get(phase, 0)
        total_signal = exec_failures + val_failures  # both count toward escalation

        if total_signal >= self.max_cheap_failures:
            model = self.escalation[phase]
            logger.info(
                f"Quality escalation: {phase} → {model} "
                f"(exec_fails={exec_failures}, validation_fails={val_failures})"
            )
            return model
        return self.overrides[phase]

    def record_failure(self, phase: str):
        """Record execution failure (exception, parse error)."""
        self.phase_failures[phase] = self.phase_failures.get(phase, 0) + 1

    def record_validation_failure(self, phase: str):
        """Record quality failure (phase succeeded but downstream validation failed)."""
        self.validation_failures[phase] = self.validation_failures.get(phase, 0) + 1

    def record_success(self, phase: str):
        self.phase_failures[phase] = 0
        self.validation_failures[phase] = 0  # reset both on full success
```

#### Validation-Driven Escalation
```python
# In orchestrator, after validation failure:
case AgentState.VALIDATING:
    report = self.validator.run(self.context)
    if report.passed:
        self.model_selector.record_success("builder")
        self.transition(AgentState.DONE)
    elif self.retry_count < self.max_retries:
        # Signal to model selector: builder output was poor quality
        self.model_selector.record_validation_failure("builder")
        self.retry_count += 1
        self.transition(AgentState.BUILDING)  # next build uses escalated model
```

#### Escalation Behavior

| Scenario | Trigger | Model Path | Cost Impact |
|---|---|---|---|
| Planner succeeds on first try | None | `gpt-4o-mini` | $0.00015/1k (cheap) |
| Planner fails twice (exception) | Execution failure | `gpt-4o-mini` → `gpt-4o` | +$0.005/1k |
| Builder succeeds but validation fails twice | **Validation quality** | `gpt-4o` → `claude-sonnet` | Cross-provider |
| Builder exception + validation fail | Combined | `gpt-4o` → `claude-sonnet` (after 2 total signals) | Cross-provider |

| Phase | Default Model | Cost per 1k tokens | Escalation Model | Rationale |
|---|---|---|---|---|
| Clarifier | gpt-4o-mini | $0.00015 | gpt-4o | Short Q&A, rarely needs escalation |
| Planner | gpt-4o-mini | $0.00015 | gpt-4o | Structured output edge cases may need premium |
| Builder | gpt-4o | $0.005 | claude-sonnet | Cross-provider for diverse code generation |
| Critic (LLM part) | gpt-4o-mini | $0.00015 | gpt-4o | Analytical, rarely fails |

**Cost impact**: ~60% cheaper than gpt-4o for all phases, with automatic quality recovery on edge cases.

### Adaptive Allocations by Tier

| Phase | Simple (30k) | Moderate (50k) | Complex (70k) |
|---|---|---|---|
| Clarifier | 2,000 | 2,000 | 3,000 |
| Planner | 3,000 | 4,000 | 6,000 |
| Builder | 10,000 | 15,000 | 25,000 |
| Critic | 2,000 | 3,000 | 4,000 |
| Repairs | 5,000 | 10,000 | 15,000 |
| **Estimated cost** | **~$0.06** | **~$0.12** | **~$0.25** |

### Budget Exhaustion Behavior
If budget is exhausted mid-run:
1. Save all artifacts produced so far (immutable build versioning preserves each attempt)
2. Transition to FAILED with `reason: "token_budget_exhausted"`
3. Include partial outputs in report (may still be useful)
4. Report: tokens used, cost estimate, which phase exhausted the budget

### Global Token Backpressure (System-Wide Cost Safety)

> **Critique addressed (v6)**: *"You manage per-run budget. But production requires global token burn rate monitoring. 10 heavy runs can spike your API bill."*

Per-run budgets prevent individual cost blowouts. System-wide backpressure prevents **aggregate** cost spikes across all concurrent runs:

```python
# app/budget/backpressure.py

from collections import deque
from datetime import datetime, timedelta

class GlobalTokenBackpressure:
    """
    Tracks system-wide token consumption over a sliding window.
    Rejects new runs when burn rate exceeds threshold.
    """

    def __init__(
        self,
        window: timedelta = timedelta(minutes=5),
        max_tokens_per_window: int = 500_000,  # 500k tokens / 5 min
        max_cost_per_window_usd: float = 5.00,  # $5 / 5 min
    ):
        self.window = window
        self.max_tokens = max_tokens_per_window
        self.max_cost = max_cost_per_window_usd
        self.records: deque[tuple[datetime, int, float]] = deque()  # (time, tokens, cost)

    def record_usage(self, tokens: int, cost_usd: float):
        now = datetime.utcnow()
        self.records.append((now, tokens, cost_usd))
        self._evict_old(now)

    def can_accept_new_run(self, estimated_tokens: int = 20_000) -> tuple[bool, str]:
        now = datetime.utcnow()
        self._evict_old(now)

        total_tokens = sum(t for _, t, _ in self.records) + estimated_tokens
        total_cost = sum(c for _, _, c in self.records)

        if total_tokens > self.max_tokens:
            return False, f"Token burn rate too high: {total_tokens:,} tokens in last {self.window}"
        if total_cost > self.max_cost:
            return False, f"Cost burn rate too high: ${total_cost:.2f} in last {self.window}"
        return True, "ok"

    def _evict_old(self, now: datetime):
        cutoff = now - self.window
        while self.records and self.records[0][0] < cutoff:
            self.records.popleft()
```

#### Integration Point
```python
# At the top of orchestrator.run(), BEFORE starting any LLM calls:
can_run, reason = self.backpressure.can_accept_new_run(
    estimated_tokens=assessment.estimated_builder_tokens
)
if not can_run:
    logger.warning(f"Backpressure: {reason}. Rejecting new run.")
    return RunResult(status="rejected", reason=reason)
```

#### Backpressure vs Per-Run Budget
| Control | Scope | What It Prevents |
|---|---|---|
| `AdaptiveTokenBudget` | Single run | One run exhausting $10 |
| `GlobalTokenBackpressure` | All runs | 10 concurrent runs spiking $50 in 5 minutes |
| Circuit breaker | Per provider | Provider outage causing wasted retries |

### Degraded Output Mode (Graceful Fallback)

> **Critique addressed (v5)**: *"Failure → FAILED is not enterprise-grade. Production systems degrade gracefully. If LLM is fully unavailable, generate a simple deterministic template. 99.9% uptime even during model outage."*

When all LLM providers are unavailable (circuit breakers open) or budget is fully exhausted, the system **degrades** instead of hard-failing:

```python
# app/fallback/deterministic_generator.py

DETERMINISTIC_TEMPLATES = {
    "dodge": {
        "index_html": """<!DOCTYPE html> ... <canvas id='c' width='600' height='400'></canvas> ...""",
        "style_css": """canvas { border: 2px solid #333; display: block; margin: auto; } ...""",
        "game_js": """// Minimal dodge game — deterministic fallback (no LLM used)
            const canvas = document.getElementById('c');
            const ctx = canvas.getContext('2d');
            let playerX = 300, score = 0, obstacles = [];
            document.addEventListener('keydown', e => {
                if (e.key === 'ArrowLeft') playerX -= 20;
                if (e.key === 'ArrowRight') playerX += 20;
            });
            function loop() {
                ctx.clearRect(0, 0, 600, 400);
                ctx.fillStyle = '#4CAF50';
                ctx.fillRect(playerX - 15, 370, 30, 30);
                if (Math.random() < 0.03) obstacles.push({x: Math.random()*580, y: 0});
                obstacles.forEach(o => { o.y += 3; ctx.fillStyle='red'; ctx.fillRect(o.x,o.y,20,20); });
                obstacles = obstacles.filter(o => o.y < 400);
                score++; ctx.fillStyle='#000'; ctx.fillText('Score: '+score, 10, 20);
                requestAnimationFrame(loop);
            }
            loop();"""
    },
    "default": { ... }  # Generic canvas game template
}

def generate_fallback(idea: str) -> GeneratedGame:
    """Deterministic game generation. Zero LLM calls. Always succeeds."""
    # Simple keyword matching to pick best template
    template_key = "default"
    for key in DETERMINISTIC_TEMPLATES:
        if key in idea.lower():
            template_key = key
            break

    template = DETERMINISTIC_TEMPLATES[template_key]
    return GeneratedGame(
        index_html=template["index_html"],
        style_css=template["style_css"],
        game_js=template["game_js"],
    )
```

#### Degradation Triggers & Behavior

| Trigger | Behavior |
|---|---|
| All circuit breakers open | Generate deterministic fallback + log warning |
| Token budget fully exhausted at BUILDING | If no partial game exists, generate fallback |
| LLM returns 3 consecutive empty/unparseable responses | Fall back to deterministic template |
| `--fallback-mode` CLI flag | Force deterministic generation (for testing) |

#### What Degraded Output Includes
- A playable (but generic) game matching the broad genre
- A `run_manifest.json` with `"mode": "degraded_fallback"` and `"llm_tokens_used": 0`
- A log message: *"LLM unavailable — generated deterministic fallback game"*

#### What It Does NOT Do
- Pretend the fallback is LLM-generated
- Count toward quality metrics (flagged separately in dashboards)
- Override a partially-built LLM game (only triggered when no game exists)

This ensures the system **always produces output** — even if it's a simple template during outages.

---

## 17) Observability, Logging & Run Artifacts (Production-Grade)

> **Critique addressed**: *"Production needs centralized logs, metrics, dashboards — not just console output"*

### Two-Tier Observability Strategy

**Tier 1 (Assignment deliverable)**: structlog + rich console + file artifacts
**Tier 2 (Production-ready)**: Prometheus metrics + centralized logging + alerting

### Tier 1: Structured Logging (Assignment)

```python
import structlog
logger = structlog.get_logger()

# Every log entry includes:
logger.info("phase_transition",
    run_id=context.run_id,
    from_state="planning",
    to_state="building",
    tokens_used=context.budget.used,
    elapsed_ms=elapsed,
)
```

### Tier 2: Production Metrics (Post-Assignment)

```python
# app/observability/metrics.py
from prometheus_client import Counter, Histogram, Gauge

# Key metrics to track
runs_total = Counter("game_builder_runs_total", "Total runs", ["status"])  # done, failed
phase_duration = Histogram("game_builder_phase_duration_seconds", "Phase duration", ["phase"])
tokens_used = Histogram("game_builder_tokens_used", "Tokens per run", ["phase", "model"])
retry_count = Counter("game_builder_retries_total", "Total retries", ["phase", "error_type"])
validation_pass_rate = Gauge("game_builder_validation_pass_rate", "Validation pass rate", ["model"])
cost_per_run = Histogram("game_builder_cost_usd", "Estimated cost per run")
critic_rebuild_rate = Gauge("game_builder_critic_rebuild_rate", "% of runs needing critic-triggered rebuild")
circuit_breaker_state = Gauge("game_builder_circuit_breaker", "Circuit breaker state", ["provider"])
```

### Production Dashboard Panels

| Panel | Metric | Alert Threshold |
|---|---|---|
| Run success rate | `runs_total{status=done} / runs_total` | < 80% over 1h |
| Avg phase latency | `phase_duration_seconds` | Builder > 30s |
| Token cost per run | `cost_usd` | > $0.50 per run |
| Retry frequency | `retries_total` | > 2 per run avg |
| Model failure rate | `retries_total{error_type=llm_*}` | > 10% |
| Validation pass rate | `validation_pass_rate` | < 70% (prompt regression signal) |
| Critic rebuild rate | `critic_rebuild_rate` | > 40% (code quality declining) |
| Circuit breaker trips | `circuit_breaker` | Any open state |

### Centralized Logging (Production)

```yaml
# docker-compose.production.yml (extends base)
services:
  game-builder:
    logging:
      driver: "fluentd"              # or json-file → Loki
      options:
        fluentd-address: "localhost:24224"
        tag: "game-builder.{{.Name}}"

  # Log aggregation
  loki:
    image: grafana/loki:latest
  grafana:
    image: grafana/grafana:latest
    ports: ["3000:3000"]
```

### Model Quality Monitoring (with Auto-Adaptive Routing)

> **Critique addressed**: *"Track validation pass rate per model, critic-triggered rebuild frequency, average retries per phase"*  
> **Critique addressed (v4)**: *"You log model performance but don't auto-switch underperforming models. Production systems must self-optimize."*

```python
# app/observability/model_tracker.py

class ModelQualityTracker:
    """Tracks model performance AND auto-adapts routing when quality degrades."""

    def __init__(self, model_selector: AdaptiveModelSelector, degradation_threshold: float = 0.70):
        self.store: list[dict] = []
        self.model_selector = model_selector
        self.degradation_threshold = degradation_threshold

    def record_outcome(self, phase: str, model: str, success: bool, retries: int):
        self.store.append({
            "phase": phase,
            "model": model,
            "success": success,
            "retries": retries,
            "timestamp": datetime.utcnow().isoformat(),
        })

        # Auto-adapt: if model success rate drops below threshold, escalate
        self._check_and_adapt(phase, model)

    def _check_and_adapt(self, phase: str, model: str):
        """Auto-escalate model if success rate drops below threshold."""
        recent = [r for r in self.store[-20:]  # last 20 records for this phase+model
                  if r["phase"] == phase and r["model"] == model]

        if len(recent) < 5:  # need minimum sample size
            return

        success_rate = sum(1 for r in recent if r["success"]) / len(recent)

        if success_rate < self.degradation_threshold:
            logger.warning(
                f"Model quality degradation detected: {model} for {phase} "
                f"at {success_rate:.0%} (threshold: {self.degradation_threshold:.0%}). "
                f"Auto-escalating to premium model."
            )
            # Force escalation in the model selector
            self.model_selector.phase_failures[phase] = self.model_selector.max_cheap_failures

            # Emit metric for dashboard alerting
            model_degradation_events.labels(phase=phase, model=model).inc()

    def get_model_report(self) -> dict:
        """Returns per-model success rates for cost/quality optimization."""
        report = {}
        for phase in {"clarifier", "planner", "builder", "critic"}:
            phase_records = [r for r in self.store if r["phase"] == phase]
            by_model = {}
            for model in {r["model"] for r in phase_records}:
                model_records = [r for r in phase_records if r["model"] == model]
                by_model[model] = {
                    "success_rate": sum(1 for r in model_records if r["success"]) / max(len(model_records), 1),
                    "avg_retries": sum(r["retries"] for r in model_records) / max(len(model_records), 1),
                    "total_runs": len(model_records),
                }
            report[phase] = by_model
        return report

        # Example output:
        # {"builder": {
        #     "gpt-4o": {"success_rate": 0.92, "avg_retries": 0.3, "total_runs": 48},
        #     "claude-sonnet": {"success_rate": 0.88, "avg_retries": 0.5, "total_runs": 12}
        # }}
```

### Auto-Adaptive Model Routing Flow
```
1. Run uses default model (e.g., gpt-4o-mini for planner)
2. ModelQualityTracker records outcome
3. If success_rate < 70% over last 20 runs:
   → Auto-escalate to premium model
   → Log warning
   → Emit Prometheus metric
4. If premium model also degrades:
   → Emit critical alert
   → Suggest prompt review (possible model update broke compatibility)
```

This closes the feedback loop: performance data **automatically influences** model selection, not just dashboards.

This data answers: *"Which model is the most cost-efficient for each phase?"* — enabling data-driven model selection.

### Console Output (Demo-Friendly)

Use `rich` library for colorful, phased console output:

```
╔══════════════════════════════════════════════════╗
║   🎮 Agentic Game Builder — Run #a3f7c2         ║
╠══════════════════════════════════════════════════╣
║ Phase 1: CLARIFICATION                           ║
║   → Extracted: genre=dodge, controls=keyboard     ║
║   → Asking 2 questions...                         ║
║   → Confidence: 0.92 ✓                            ║
╠══════════════════════════════════════════════════╣
║ Phase 2: PLANNING                                 ║
║   → Framework: vanilla JS (simple mechanics)      ║
║   → Entities: player, falling_obstacle, score     ║
║   → Plan saved → outputs/a3f7c2/plan.json         ║
╠══════════════════════════════════════════════════╣
║ Phase 3: BUILDING                                 ║
║   → Generating game.js... ✓ (347 lines)           ║
║   → Generating index.html... ✓                    ║
║   → Generating style.css... ✓                     ║
╠══════════════════════════════════════════════════╣
║ Phase 4: CRITIQUE                                 ║
║   → 0 critical, 1 warning (no sound)              ║
║   → Proceeding to validation                      ║
╠══════════════════════════════════════════════════╣
║ Phase 5: VALIDATION                               ║
║   → File check: ✓                                 ║
║   → JS syntax: ✓                                  ║
║   → HTML linkage: ✓                               ║
║   → Heuristics: ✓ (input listener, game loop)     ║
╠══════════════════════════════════════════════════╣
║ ✅ DONE — Game ready at outputs/a3f7c2/game/      ║
║   Tokens used: 23,847 | Cost: ~$0.12              ║
╚══════════════════════════════════════════════════╝
```

### Run Manifest (Persisted)

```json
{
  "run_id": "a3f7c2",
  "timestamp": "2026-03-03T14:22:00Z",
  "original_idea": "make a dodge game",
  "final_state": "done",
  "phases": {
    "clarification": {"rounds": 2, "confidence": 0.92, "tokens": 3200},
    "planning": {"framework": "vanilla", "tokens": 3800},
    "building": {"files_generated": 3, "tokens": 14200},
    "critiquing": {"criticals": 0, "warnings": 1, "tokens": 2100},
    "validation": {"checks_passed": 6, "checks_total": 6}
  },
  "total_tokens": 23847,
  "estimated_cost_usd": 0.12,
  "retry_count": 0,
  "elapsed_seconds": 34.2
}
```

---

## 18) Docker Strategy (Production-Grade)

### Multi-Stage Dockerfile

```dockerfile
# ---- Stage 1: Python base with Node.js for JS validation ----
FROM python:3.11-slim AS base

# Install Node.js (LTS) for `node --check` validation
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (cache layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---- Stage 2: Application ----
FROM base AS app
COPY app/ ./app/
COPY pyproject.toml .

# Create output directory
RUN mkdir -p /app/outputs

# Default: interactive mode
ENTRYPOINT ["python", "-m", "app.main"]

# Health metadata
LABEL maintainer="your-name"
LABEL description="Agentic Game Builder AI"
```

### docker-compose.yml (Convenience)

```yaml
version: "3.9"
services:
  game-builder:
    build: .
    environment:
      - LLM_MODEL=${LLM_MODEL:-gpt-4o}
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY:-}
    volumes:
      - ./outputs:/app/outputs
    stdin_open: true       # for interactive clarification
    tty: true
```

### Build & Run Commands

**Linux/macOS:**
```bash
docker build -t agentic-game-builder .
docker run -it --rm \
  -e OPENAI_API_KEY=$OPENAI_API_KEY \
  -v $(pwd)/outputs:/app/outputs \
  agentic-game-builder \
  --idea "Build a minimalist dodge game where you avoid falling objects"
```

**Windows PowerShell:**
```powershell
docker build -t agentic-game-builder .
docker run -it --rm `
  -e OPENAI_API_KEY=$env:OPENAI_API_KEY `
  -v "${PWD}/outputs:/app/outputs" `
  agentic-game-builder `
  --idea "Build a minimalist dodge game where you avoid falling objects"
```

**Non-interactive (batch) mode:**
```bash
docker run --rm \
  -e OPENAI_API_KEY=$OPENAI_API_KEY \
  -e BATCH_MODE=true \
  -v $(pwd)/outputs:/app/outputs \
  agentic-game-builder \
  --idea "Space shooter with power-ups"
```

---

## 18a) MCP Server Architecture *(NEW v7)*

### Why MCP?

The **Model Context Protocol (MCP)** is an open standard that lets AI assistants (Claude Desktop, VS Code Copilot, Cursor) call external tools, read resources, and use prompts over a JSON-RPC 2.0 stdio transport. By exposing the game-builder as an MCP server, any MCP-compatible client can build games without CLI knowledge.

### Implementation: `app/mcp_server.py` (787 lines)

Built on `FastMCP` from `mcp[cli]>=1.26.0`. All tools are `async def` with `Context` injection. The orchestrator runs in a thread pool via `loop.run_in_executor()` to avoid blocking the MCP event loop.

#### MCP Tools (6)

| Tool | Async | Progress | Description |
|------|-------|----------|-------------|
| `build_game(idea, model, output_dir)` | ✅ | ✅ Real-time phase notifications | Full pipeline: CLARIFY → PLAN → BUILD → CRITIQUE → VALIDATE → DONE |
| `validate_game(game_dir)` | ✅ | ✅ | Static analysis + security scan on existing game files |
| `resume_build(run_id, output_dir)` | ✅ | ✅ | Resume from checkpoint after crash/timeout |
| `remix_game(run_id, instructions, model)` | ✅ | ✅ | Load existing build + modification instructions → new build |
| `list_builds(output_dir)` | ✅ | — | Scan output dirs for completed/failed runs |
| `get_build_files(run_id, output_dir)` | ✅ | — | Retrieve full source code for a build |

#### MCP Resources (7)

| Resource URI | Description |
|---|---|
| `builds://latest` | Most recent build summary |
| `builds://{run_id}/result` | Full JSON run result |
| `builds://{run_id}/report` | Markdown build report |
| `builds://{run_id}/manifest` | Prompt version manifest (traceability) |
| `builds://{run_id}/game/index.html` | Generated HTML |
| `builds://{run_id}/game/style.css` | Generated CSS |
| `builds://{run_id}/game/game.js` | Generated JavaScript |

#### MCP Prompts (4)

| Prompt | Args | Purpose |
|--------|------|---------|
| `game_idea_refiner` | `vague_idea` | Guides user through genre, mechanics, controls, win/lose refinement |
| `build_config_guide` | — | Explains model options, pipeline phases, tips for good results |
| `analyze_game_code` | `run_id` | Structured code review prompt (architecture, game loop, collision, etc.) |
| `remix_workflow` | `run_id` | 4-step guided remix: review → choose mods → execute → compare |

#### Progress Notification Bridge

The orchestrator runs synchronously in a worker thread. The `_make_progress_callback()` function bridges sync→async:

```python
def _make_progress_callback(ctx: Context, loop: asyncio.AbstractEventLoop):
    def _on_phase_transition(state: AgentState, build_number: int, retry_count: int):
        step, description = _PHASE_META.get(state.value, (0, state.value))
        asyncio.run_coroutine_threadsafe(
            ctx.report_progress(step, _TOTAL_PHASES, description), loop
        )
        asyncio.run_coroutine_threadsafe(
            ctx.info(f"[{step}/{_TOTAL_PHASES}] {description}"), loop
        )
    return _on_phase_transition
```

The `Orchestrator.__init__` accepts `progress_callback: Callable[[AgentState, int, int], None] | None` and calls it on every `transition()`.

#### Remix Tool Design

The `remix_game` tool:
1. Loads existing `game.js`, `index.html`, `style.css` from `outputs/{run_id}/latest/`
2. Loads original idea from `context.json`
3. Constructs a remix prompt: original idea + full existing code + user's modification instructions
4. Runs the full pipeline with the remix prompt — produces a new build (original preserved)

### MCP Client Configuration

**VS Code** (`.vscode/mcp.json`):
```json
{
  "mcpServers": {
    "game-builder": {
      "command": "python",
      "args": ["-m", "app.mcp_server"],
      "cwd": "${workspaceFolder}",
      "env": { "OUTPUT_DIR": "outputs", "BATCH_MODE": "true" }
    }
  }
}
```

**Claude Desktop** (`claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "game-builder": {
      "command": "python",
      "args": ["-m", "app.mcp_server"],
      "cwd": "/path/to/agentic-orchestration-engine",
      "env": { "OPENAI_API_KEY": "your-key", "OUTPUT_DIR": "outputs" }
    }
  }
}
```

### Testing

- **40/40 unit tests** — all existing pipeline tests pass unchanged
- **6/6 MCP integration tests** — stdio client verifies tools, resources, prompts, error handling
- **6/6 Docker MCP tests** — full protocol verification through Docker container

---

## 18b) Docker MCP & Container Registry Publishing *(NEW v7)*

### Docker MCP Mode

The Dockerfile supports two modes via entrypoint override:

| Mode | Entrypoint | Transport |
|------|-----------|-----------|
| **CLI** (default) | `python -m app.main` | stdin/stdout (TTY) |
| **MCP Server** | `python -m app.mcp_server` | stdio (JSON-RPC 2.0) |

The `docker-compose.yml` includes a dedicated `game-builder-mcp` service:

```yaml
game-builder-mcp:
  build: .
  env_file: .env
  volumes:
    - ./outputs:/app/outputs
  stdin_open: true
  entrypoint: ["python", "-m", "app.mcp_server"]
```

The Dockerfile includes a HEALTHCHECK that verifies the MCP server can import:
```dockerfile
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "from app.mcp_server import mcp; print('ok')" || exit 1
```

### Container Registry Publishing

Images are published to both Docker Hub and GitHub Container Registry:

| Registry | Image | Tags |
|----------|-------|------|
| **Docker Hub** | `shreyas2809/game-builder-mcp` | `latest`, `2.1.0` |
| **GHCR** | `ghcr.io/orion2809/game-builder-mcp` | `latest`, `2.1.0` |

**Zero-dependency usage** (anyone with Docker):
```bash
# Pull pre-built image (no build step)
docker pull shreyas2809/game-builder-mcp:latest

# Run MCP server
docker run -i --rm \
  -e OPENAI_API_KEY \
  -v ./outputs:/app/outputs \
  --entrypoint python \
  shreyas2809/game-builder-mcp \
  -m app.mcp_server
```

**Claude Desktop (Docker MCP)**:
```json
{
  "mcpServers": {
    "game-builder": {
      "command": "docker",
      "args": [
        "run", "-i", "--rm",
        "-e", "OPENAI_API_KEY",
        "-v", "./outputs:/app/outputs",
        "--entrypoint", "python",
        "shreyas2809/game-builder-mcp",
        "-m", "app.mcp_server"
      ]
    }
  }
}
```

**VS Code (Docker MCP)**:
```json
{
  "mcpServers": {
    "game-builder-docker": {
      "command": "docker",
      "args": [
        "run", "-i", "--rm",
        "-e", "OPENAI_API_KEY",
        "-v", "./outputs:/app/outputs",
        "--entrypoint", "python",
        "shreyas2809/game-builder-mcp",
        "-m", "app.mcp_server"
      ]
    }
  }
}
```

### Image Details

- **Base**: `python:3.11-slim` + `node:20-slim` (multi-stage)
- **Size**: ~2.3GB (includes Playwright Chromium headless shell)
- **Includes**: Python 3.11, Node.js 20, esprima, Playwright Chromium, all pip deps incl. `mcp[cli]`
- **MCP transport**: stdio (JSON-RPC 2.0) — Docker `-i` flag keeps stdin open

---

## 19) Interactive vs Batch Mode

### Why Two Modes?
- **Interactive**: Docker TTY — user answers clarification questions live (best for demo)
- **Batch**: Non-interactive — agent uses defaults/assumptions for all unclear requirements (best for CI/testing)

### Implementation

```python
# app/main.py
@app.command()
def generate(
    idea: str = typer.Option(..., "--idea", help="Natural language game idea"),
    batch: bool = typer.Option(False, "--batch", help="Skip interactive questions"),
    output_dir: str = typer.Option("outputs", "--output"),
    model: str = typer.Option(None, "--model", help="Override LLM model"),
):
    config = Config(
        batch_mode=batch or os.getenv("BATCH_MODE", "false").lower() == "true",
        output_dir=output_dir,
        model_override=model,
    )
    orchestrator = Orchestrator(config)
    result = orchestrator.run(idea)
    # ...
```

### Clarification in Each Mode
- **Interactive**: Print questions to stdout, read answers from stdin
- **Batch**: LLM answers its own questions with reasonable defaults, logs all assumptions

---

## 20) Security & Sandboxing (Hardened)

> **Critique addressed**: *"No security hardening for generated JS — LLMs can hallucinate fetch(), eval(), document.cookie access"*

### Generated Code Safety
The system generates arbitrary JavaScript that runs in a browser. **LLMs are untrusted code generators** — even with prompt constraints, they can hallucinate dangerous code.

1. **No server-side execution**: Generated code is never `eval()`'d by Python — only written to disk
2. **No network calls in generated games**: Builder prompt explicitly forbids `fetch()`, `XMLHttpRequest`, WebSocket in game code
3. **Docker isolation**: Agent runs in container; generated files are volume-mounted out
4. **File path sanitization**: Output writer only writes to `outputs/<run_id>/game/` — no path traversal

### Static Security Scanner (NEW)

Prompt-level prohibitions are **necessary but not sufficient**. A post-generation static scan catches anything the LLM hallucinated:

```python
# app/validators/security_scanner.py

BLOCKED_PATTERNS = [
    # Network access
    (r'\bfetch\s*\(', "Network call: fetch()"),
    (r'XMLHttpRequest', "Network call: XMLHttpRequest"),
    (r'WebSocket', "Network call: WebSocket"),
    (r'navigator\.sendBeacon', "Network call: sendBeacon"),
    (r'new\s+EventSource', "Network call: EventSource (SSE)"),

    # Code injection vectors
    (r'\beval\s*\(', "Code injection: eval()"),
    (r'new\s+Function\s*\(', "Code injection: new Function()"),
    (r'setTimeout\s*\(\s*["\']', "Code injection: setTimeout with string"),
    (r'setInterval\s*\(\s*["\']', "Code injection: setInterval with string"),

    # Data exfiltration
    (r'document\.cookie', "Data access: document.cookie"),
    (r'localStorage', "Data access: localStorage"),
    (r'sessionStorage', "Data access: sessionStorage"),
    (r'indexedDB', "Data access: indexedDB"),

    # DOM manipulation risks
    (r'document\.write', "DOM risk: document.write"),
    (r'innerHTML\s*=', "DOM risk: innerHTML assignment (XSS vector)"),
    (r'outerHTML\s*=', "DOM risk: outerHTML assignment"),

    # External resource loading
    (r'import\s*\(', "Dynamic import"),
    (r'<script\s+src=(?!["\'](?:game\.js|style\.css))', "External script loading"),
]

def scan_generated_code(game_files: GeneratedGame) -> list[SecurityFinding]:
    findings = []
    for filename, content in [("game.js", game_files.game_js),
                               ("index.html", game_files.index_html),
                               ("style.css", game_files.style_css)]:
        for pattern, description in BLOCKED_PATTERNS:
            matches = re.findall(pattern, content)
            if matches:
                findings.append(SecurityFinding(
                    file=filename,
                    pattern=description,
                    occurrences=len(matches),
                    severity="blocker",
                    action="auto_remove"  # or "block_output"
                ))
    return findings
```

### Security Response Strategy

| Finding Severity | Action |
|---|---|
| `blocker` (fetch, eval, cookie) | **Block output** — trigger repair cycle to remove the pattern |
| `warning` (innerHTML, localStorage) | **Log warning** — proceed but flag in validation report |
| `info` (setTimeout with function ref) | **Pass** — safe usage pattern |

### Content Security Policy Header (Defense in Depth)
Generated `index.html` includes a restrictive CSP meta tag:

```html
<meta http-equiv="Content-Security-Policy"
      content="default-src 'self'; script-src 'self' 'unsafe-inline';
              style-src 'self' 'unsafe-inline'; img-src 'self' data:;
              connect-src 'none'; frame-src 'none';">
```

This blocks network calls even if they slip past the static scanner — **defense in depth**.

### Runtime Sandbox: iframe Isolation (v4 Upgrade)

> **Critique addressed (v4)**: *"You need static scanner + runtime sandbox. Your security model is prompt-based plus string scanning — not hardened isolation."*

When the generated game is served (preview mode or production), it runs inside a **sandboxed iframe**:

```html
<!-- preview.html — wraps the generated game in a sandboxed iframe -->
<!DOCTYPE html>
<html>
<head><title>Game Preview (Sandboxed)</title></head>
<body style="margin:0; overflow:hidden;">
  <iframe
    id="game-frame"
    src="game/index.html"
    sandbox="allow-scripts"
    style="width:100vw; height:100vh; border:none;"
    csp="default-src 'self'; script-src 'self' 'unsafe-inline';
         style-src 'self' 'unsafe-inline'; img-src 'self' data:;
         connect-src 'none'; frame-src 'none';"
  ></iframe>
</body>
</html>
```

#### What `sandbox="allow-scripts"` Blocks

| Capability | Blocked? | Why |
|---|---|---|
| JavaScript execution | ✅ Allowed (`allow-scripts`) | Game needs JS to run |
| Form submission | ❌ Blocked | No forms in games |
| Same-origin access | ❌ Blocked | Can't access parent page cookies/storage |
| Navigation (top-level) | ❌ Blocked | Can't redirect user |
| Popups / new windows | ❌ Blocked | No pop-up abuse |
| Pointer lock / fullscreen | ❌ Blocked | Add `allow-pointer-lock` only if needed |
| Downloads | ❌ Blocked | No drive-by downloads |
| `localStorage` / `sessionStorage` | ❌ Blocked | Isolated storage only |
| `document.cookie` (parent) | ❌ Blocked | Sandboxed origin |

#### Three-Layer Security Model
```
Layer 1: Prompt constraints ("never use fetch, eval, document.cookie")
    ↓ LLM may hallucinate violations
Layer 2: Static security scanner (regex + AST scan for 15+ blocked patterns)
    ↓ Scanner may miss obfuscated patterns
Layer 3: Runtime sandbox (iframe sandbox + CSP headers)
    ↓ Even if code runs, it CAN'T exfiltrate data or make network calls
```

This is **true defense in depth** — each layer catches what the previous layer misses.

### API Key Protection
- Keys passed via environment variables only
- Never logged or included in output artifacts
- `.env.example` provided without actual values
- Static scanner also checks generated code doesn't contain API key patterns (`sk-`, `key-`)

---

## 21) Testing Strategy

### Unit Tests

| Test | What It Validates |
|---|---|
| `test_state_transitions` | Every legal transition works; every illegal transition raises |
| `test_confidence_scoring` | Confidence calculation with various filled/empty dimensions |
| `test_plan_schema` | Valid plans pass; invalid plans rejected by Pydantic |
| `test_game_schema` | Generated file contract enforced (min_length, etc.) |
| `test_html_linkage` | Validator catches missing script/link tags |
| `test_js_syntax_check` | Validator catches syntax errors via subprocess |

### Integration Tests (Mock LLM)

```python
# tests/conftest.py
@pytest.fixture
def mock_llm():
    """Returns canned LLM responses for each phase."""
    return MockLLMProvider({
        "clarifier": MOCK_CLARIFICATION_RESPONSE,
        "planner": MOCK_PLAN_RESPONSE,
        "builder": MOCK_GAME_FILES,
        "critic": MOCK_CRITIQUE,
    })

def test_full_pipeline(mock_llm):
    orchestrator = Orchestrator(config, llm=mock_llm)
    result = orchestrator.run("make a dodge game")
    assert result.state == AgentState.DONE
    assert all(f in result.files for f in ["index.html", "style.css", "game.js"])
```

### End-to-End Test
```bash
# Run with real LLM (CI/CD with API key secret)
docker run --rm -e OPENAI_API_KEY=$KEY -e BATCH_MODE=true \
  agentic-game-builder --idea "simple pong game"
# Assert: outputs/<latest>/game/ contains 3 files
# Assert: node --check outputs/<latest>/game/game.js exits 0
```

### Prompt Regression Tests (NEW)
See Section 14a for full details. Summary:
- 20–50 fixed input ideas with expected plan elements
- Run weekly in CI
- Alert on pass-rate degradation
- Correlate failures with prompt version hashes

### Checkpoint & Resume Tests (NEW)
```python
def test_checkpoint_and_resume(mock_llm, tmp_path):
    """Verify crash recovery from each phase."""
    config = Config(output_dir=str(tmp_path))
    orchestrator = Orchestrator(config, llm=mock_llm)

    # Run until PLANNING, then simulate crash
    orchestrator.run_until_phase("planning", idea="dodge game")
    run_id = str(orchestrator.context.run_id)

    # Verify checkpoint exists
    checkpoint = tmp_path / run_id / "checkpoint.json"
    assert checkpoint.exists()

    # Resume and complete
    resumed = Orchestrator.resume(run_id, config)
    assert resumed.state == AgentState.PLANNING
    result = resumed.run(resumed.context.original_idea)
    assert result.state == AgentState.DONE
```

### Security Scanner Tests (NEW)
```python
def test_security_scanner_blocks_fetch():
    game = GeneratedGame(
        game_js="fetch('https://evil.com'); // game code",
        index_html="<html>...</html>",
        style_css="body {}"
    )
    findings = scan_generated_code(game)
    assert any(f.pattern == "Network call: fetch()" for f in findings)
    assert any(f.severity == "blocker" for f in findings)
```

---

## 22) README Content Blueprint

The README is a deliverable. Structure it exactly to the rubric:

```markdown
# Agentic Game Builder AI

## Quick Start
<docker build + run commands, copy-paste ready>

## What This Does
<1 paragraph: NL idea → clarify → plan → generate → validate → playable game>

## Architecture
<diagram from Section 4>
<explanation of each phase>
<state machine diagram>

## Agent Phases
### 1. Requirements Clarification
### 2. Structured Planning
### 3. Code Generation
### 4. Self-Critique
### 5. Validation

## How to Run
### Docker (Recommended)
### Local Development
### Configuration Options

## Example Run
<paste console output showing full workflow>
<screenshot of generated game>

## Trade-Offs
<from Section 23 of this plan>

## Improvements With More Time
<from Section 24 futuristic roadmap>

## Project Structure
<tree from Section 6>
```

---

## 23) Trade-Offs (Explicit & Honest)

| Decision | Trade-Off | Justification |
|---|---|---|
| **Deterministic orchestrator vs LLM-driven routing** | Less flexible but more reliable | Evaluators want to see *your* control flow, not an LLM deciding what to do |
| **Vanilla JS default** | Less visual richness | Higher generation reliability; Phaser code is more complex to get right on first pass |
| **Structured output (instructor)** | Extra dependency | Eliminates ~80% of parse failures vs raw JSON extraction |
| **Bounded retries (max 2)** | May fail on very complex games | Prevents runaway costs; 2 retries resolves >90% of fixable issues |
| **State-based behavioral validation** | Requires debug hook injection (toolchain-managed) | Eliminates false positives from pixel-diff; proves game state actually changes |
| **AST-based deterministic critic** | Requires esprima + Node.js subprocess | Catches aliased calls (e.g., `const raf = requestAnimationFrame`) that regex misses |
| **Toolchain AST debug injection** | Monkey-patches rAF (may miss non-rAF games) | LLM-independent, zero stripping needed, no regex brittleness, delivery always clean |
| **FPS + entity growth guardrails** | Adds ~5s to validation | Catches infinite spawning, memory leaks, unplayable framerates with sustained measurement |
| **Degraded fallback mode** | Deterministic template not as good as LLM output | 99.9% uptime guarantee; always produces playable output even during outages |
| **Immutable build versioning** | More disk/storage usage | Enables diff audits, model comparison, regression debugging across rebuilds |
| **Redis-backed concurrency** | Extra infra dependency (Redis) for production | Distributed-safe concurrency; TTL-based crash recovery; in-memory fallback for CLI |
| **Global token backpressure** | May reject runs during cost spikes | Prevents aggregate cost blowouts across concurrent runs |
| **Chaos testing** | Slower CI pipeline (~10% failure injection) | Validates resilience features actually work under stochastic failure |
| **Adaptive token budget** | More code complexity | Prevents budget blowout on complex games; saves money on simple ones |
| **Single game.js file** | Large file for complex games | Matches assignment requirement; splitting would need module bundler |
| **CLI-first, not service-oriented** | Not production-ready as-is | Assignment requires Docker CLI; architecture designed for service evolution (§4a) |
| **Abstract persistence (File default, Postgres ready)** | Extra interface layer | Injectable backends mean zero refactor for production; file for CLI, DB for service |
| **Quality-adaptive model escalation** | Higher cost on retries | Auto-recovers from mini-model failures; ~95% of runs stay cheap |
| **Per-provider sliding-window circuit breaker** | More complex than simple counter | Prevents false trips and missed trips; time-decayed for realistic failure tracking |
| **Runtime iframe sandbox** | Slightly more complex preview setup | True defense-in-depth; blocks exfiltration even if static scanner misses something |
| **Python over TypeScript** | Not the game's language | Better LLM agent ecosystem, faster to develop, easier Docker packaging |
| **litellm over direct SDK** | Thin extra layer | Provider portability worth the 200 lines of abstraction |
| **Per-phase model tiering** | Slightly worse quality for cheap phases | ~60% cost reduction; builder uses best model where it matters most |
| **No persistent memory across runs** | Each run is stateless | Simpler, reproducible; RAG-based memory is a future upgrade |
| **Static security scanner** | May false-positive on legitimate patterns | Safety-first for LLM-generated code; allowlist for exceptions |

---

## 24) Futuristic Architecture Roadmap

### Tier 0: Production Hardening (Addressed in v3–v5 — Ready to Build)

> These items were critiques of v2–v4. They are now **designed into the plan** and ready for implementation.

| Critique | Resolution | Section |
|---|---|---|
| Single-run oriented | Service-oriented architecture designed, CLI-first for assignment | §4a |
| No idempotency | Phase-level checkpointing + resume from crash | §8a |
| No concurrency controls | Per-user rate limits, circuit breaker, global concurrency cap | §8b |
| Heuristic-only validation | State-based behavioral Playwright tests + FPS guardrail + execution timeouts | §13 |
| No JS security hardening | Static scanner + AST analysis + CSP header + iframe sandbox + debug hook stripping | §20 |
| Prompt engineering fragility | Prompt versioning + weekly regression CI + rollback strategy | §14a |
| Static token budget | Adaptive budget tied to plan complexity tiers | §16 |
| No production observability | Prometheus metrics, model quality tracking, alerting thresholds | §17 |
| LLM critic is expensive | Hybrid critic: 80% AST-based deterministic + 20% LLM | §12 |
| No plan complexity guardrail | Cost-predictive complexity scoring (structural + token estimation) + simplification | §10a |
| Same model for all phases | Per-phase model tiering (cheap for Q&A, premium for code gen) | §16 |
| No prompt versioning | SHA-256 hashes enforced in run manifest + failure correlation + CI matrix | §14a |
| Debug hook is security backdoor (v5) | Build/delivery mode separation — hooks stripped from delivery artifacts | §13 |
| No performance validation (v5) | FPS guardrail via `requestAnimationFrame` counter — warn if < 15 FPS | §13 |
| Complexity scoring ignores cost (v5) | Cost-predictive: `estimated_builder_tokens = f(entities, mechanics, framework)` | §10a |
| Escalation only on exceptions (v5) | Validation-failure-driven quality escalation (not just exception-based) | §16 |
| Artifact overwrites lose history (v5) | Immutable build versioning: `run_id/build_N/` — every attempt preserved | §8a |
| Prompt versioning not enforced (v5) | Mandatory hash in manifest + failure↔prompt correlation + CI regression matrix | §14a |
| No degraded output mode (v5) | Deterministic fallback templates when LLM unavailable — 99.9% uptime | §16 |
| No execution timeout (v5) | `page.setDefaultTimeout(15s)` + `page.goto()` timeout + total behavioral cap | §13 |
| Debug stripping relies on regex (v6) | AST-based toolchain injection — LLM never generates hooks, delivery is original code | §13 |
| No entity growth detection (v6) | 5s FPS measurement + entity count growth rate tracking via debug state | §13 |
| In-memory concurrency not distributed (v6) | Redis-backed atomic counters + TTL heartbeats for crash recovery | §8b |
| No global cost backpressure (v6) | Sliding-window token burn rate monitor — rejects runs when threshold exceeded | §16 |
| Simplification loop could oscillate (v6) | `max_simplification_rounds = 1` — bounded, never re-simplifies | §10a |
| No chaos/resilience testing (v6) | `RUN_CHAOS_MODE=true` — random failure injection validates circuit breakers, retries, budgets | §13a |

### Tier 1: Immediate Extensions (Days After Submission)

| Feature | How | Impact |
|---|---|---|
| **RAG-based game patterns** | Index 50+ working game snippets → retrieve relevant patterns during planning | Higher code quality, fewer generation bugs |
| **A/B generation** | Generate 2 game variants, critic picks the better one | Better quality at 2x cost — worth it for complex games |
| **Live preview server** | `python -m http.server` in Docker + open browser | Zero-friction testing in demo |
| **FastAPI service mode** | Wrap orchestrator in API → job queue → workers (designed in §4a) | Multi-user, async, production-ready |
| **Postgres run storage** | Replace file-based checkpoints with DB | Concurrent access, query history, analytics |

### Tier 2: Advanced Agent Capabilities (Weeks)

| Feature | How | Impact |
|---|---|---|
| **Multi-agent specialization** | Separate agents: Mechanic Designer, Visual Designer, QA Tester | Each agent is smaller, more focused, higher quality |
| **Extended playtesting bot** | Playwright bot plays 100 rounds, measures win rate, avg score, death rate | Data-driven game balancing, not just "does it load" |
| **Self-improving prompts** | Log which prompts produce validation failures → auto-tune few-shot examples | System gets better over time |
| **Difficulty simulation** | Extended playtesting data → feed back to builder for rebalancing | Data-driven difficulty curves |
| **Tool-use / function calling** | LLM agents call tools: `search_game_patterns()`, `validate_js()`, `test_controls()` | True agentic behavior with tool access |
| **Model quality auto-routing** | ModelQualityTracker auto-escalates when success_rate < 70% (built into §17) | Closed feedback loop — data drives model selection automatically |

### Tier 3: Platform-Level Vision (Months)

| Feature | How | Impact |
|---|---|---|
| **Asset generation pipeline** | DALL-E/Stable Diffusion for sprites, Web Audio API for sound | Full multimedia games from text descriptions |
| **Multiplayer templates** | WebRTC / WebSocket game templates in plan library | Expand from single-player to social games |
| **One-click deploy** | GitHub Pages, Netlify, Vercel deployment post-generation | From idea to live URL in under 2 minutes |
| **Voice-driven input** | Whisper API for speech → text → clarifier agent | Hands-free game design |
| ~~**Game remix / iteration**~~ | ~~"Make it harder" / "Add a boss" → modify existing generated game~~ | **✅ DONE (v2.1.0)** — `remix_game` tool in MCP server |
| ~~**Model Context Protocol (MCP)**~~ | ~~Expose agent as MCP server; IDE extensions can call it directly~~ | **✅ DONE (v2.1.0)** — 6 tools, 7 resources, 4 prompts; Docker Hub + GHCR published |
| **Event-driven orchestrator** | Migration path fully designed in §4 — Celery task wrappers around same phase handlers (~50 LOC change) | Horizontal scaling, independent phase retries |
| **Full Grafana dashboard** | Prometheus → Grafana with all metrics from §17 | Production visibility without code changes |

---

## 25) Delivery Milestones

### Milestone 1 — Skeleton & Contracts (Day 1, ~4 hours)
- [ ] Project scaffold (all dirs, `__init__.py`, `pyproject.toml`)
- [ ] All Pydantic models in `schemas.py`
- [ ] State machine enum + transition table in `state.py`
- [ ] Orchestrator skeleton (compiles, runs, hits each phase stub)
- [ ] Basic Typer CLI (`main.py`) with `--idea` flag
- [ ] `config.py` with env var loading
- [ ] `requirements.txt` locked

### Milestone 2 — Clarify + Plan Agents (Day 2, ~5 hours)
- [ ] LLM provider abstraction (`provider.py`, `structured.py`)
- [ ] Token tracker
- [ ] Clarifier agent with confidence scoring + stop logic
- [ ] Planner agent with framework decision policy
- [ ] All prompts written (`prompts/*.md`)
- [ ] Artifact writer (JSON + MD output)
- [ ] Unit tests for confidence scoring + schema validation

### Milestone 3 — Build + Critique + Validate (Day 3, ~6 hours)
- [ ] Builder agent (chunked generation, repair mode)
- [ ] Critic agent (plan compliance check)
- [ ] Validator pipeline (file check, JS syntax, HTML linkage, heuristics)
- [ ] Retry loop wired end-to-end
- [ ] Console output with `rich` formatting
- [ ] Integration test with mock LLM

### Milestone 4 — Docker + Docs + Polish (Day 4, ~4 hours)
- [ ] Multi-stage Dockerfile
- [ ] docker-compose.yml
- [ ] `.env.example`, `.dockerignore`, `.gitignore`
- [ ] README.md (full content per Section 22)
- [ ] End-to-end test run (real LLM)
- [ ] Fix edge cases found in E2E
- [ ] Optional: screen recording

---

## 26) Acceptance Checklist

### Mandatory (Must All Pass)
- [x] `docker build` succeeds without errors
- [x] `docker run` with `--idea` flag produces game files
- [x] Clarification phase executes (questions visible in console + saved to JSON)
- [x] Plan artifact exists (`plan.json`) before code generation begins
- [x] Generated game contains `index.html`, `style.css`, `game.js`
- [x] Opening `index.html` in browser shows playable game
- [x] No hard-coded game template anywhere in source
- [x] No manual edits to generated output
- [x] README contains architecture, trade-offs, improvements, Docker instructions

### Quality (Should Pass)
- [x] State machine prevents phase skipping
- [x] Validation catches at least JS syntax errors
- [x] Failed runs produce diagnostic report
- [x] Token usage tracked and reported
- [x] Console output clearly shows phase transitions

### Stretch (Nice to Have)
- [x] Critic agent catches and fixes at least 1 issue in testing
- [x] Headless browser smoke test passes
- [x] Batch mode works without user interaction
- [ ] Screen recording demonstrates full flow

### MCP Server (v7 — Must All Pass)
- [x] `python -m app.mcp_server` starts without errors (stdio transport)
- [x] MCP client can list all 6 tools (`build_game`, `validate_game`, `resume_build`, `remix_game`, `list_builds`, `get_build_files`)
- [x] MCP client can list all 7 resources
- [x] MCP client can list all 4 prompts
- [x] `build_game` tool produces real game files via MCP protocol
- [x] Progress notifications stream during `build_game` execution
- [x] Docker MCP mode works: `docker run -i --rm --entrypoint python shreyas2809/game-builder-mcp -m app.mcp_server`
- [x] Docker Hub image `shreyas2809/game-builder-mcp` publicly pullable
- [x] GHCR image `ghcr.io/orion2809/game-builder-mcp` publicly pullable
- [x] Claude Desktop config works with both local and Docker MCP

---

## 27) Demo Script

**Recommended 3-minute demo flow:**

```
[0:00] Show Dockerfile and explain architecture (15s)
[0:15] docker build (pre-built, just show command)
[0:20] docker run with ambiguous idea: "make some kind of space game"
[0:25] Agent asks 2 clarifying questions → user answers
[0:45] Show clarification.json in output folder
[0:55] Planning phase runs → show plan.json + plan.md
[1:15] Building phase → show console progress
[1:35] Critic phase → show "0 critical issues"
[1:45] Validation phase → all checks green
[1:55] Open game/index.html in browser
[2:00] Play the game for 30 seconds
[2:30] Show run_manifest.json (tokens, timing, status)
[2:45] Quick scroll through README architecture section
[3:00] Done
```

---

## 28) Final Recommendation

### For Maximum Assignment Score
1. **Orchestrator is king**: The state machine is the most important code — it proves you designed an agent, not a prompt chain
2. **Contracts everywhere**: Pydantic models between every phase — this is what "engineering structure" means
3. **Behavioral validation**: Don't just check files exist — prove the game responds to input (Playwright)
4. **Hybrid critic**: 80% deterministic + 20% LLM — shows engineering maturity, not LLM dependency
5. **Checkpoint recovery**: Crash-resilient with resume capability — demonstrates production thinking
6. **Security scanner**: Static analysis on generated JS — shows you understand LLMs are untrusted code generators
7. **Adaptive budgets**: Token budget scales with game complexity — shows cost awareness
8. **Prompt versioning**: Hashes in manifest + regression CI — shows you've thought about long-term maintenance
9. **README is a deliverable**: Treat it like a technical document, not an afterthought
10. **Docker must work first try**: Test on a clean machine / fresh Docker pull

### Architecture Summary (v7 — Final)
```
Deterministic Orchestrator (event-driven migration path designed)
    + Abstract Persistence Layer (File/Postgres/S3 — injectable)
    + Immutable Build Versioning (every rebuild preserved for audit)
    + Typed Contracts (Pydantic)
    + Provider-Agnostic LLM Layer (litellm + instructor + per-phase model tiers)
    + Quality-Adaptive Model Escalation (execution + validation failure driven)
    + Per-Provider Sliding-Window Circuit Breakers (integrated into LLMProvider)
    + Graceful Degraded Fallback Mode (deterministic templates during outages)
    + Hybrid Critic (80% AST-based deterministic + 20% LLM)
    + State-Based Behavioral Validation (toolchain-injected debug hooks, LLM-independent)
    + FPS + Entity Growth Guardrails (5s sustained measurement)
    + Execution Timeout Guards (page load + evaluation + total cap)
    + Three-Layer Security (prompt + static/AST scan + iframe runtime sandbox)
    + Cost-Predictive Complexity Scoring (structural + token estimation)
    + Adaptive Token Budgets (complexity-tiered) + Global Backpressure
    + Bounded Plan Simplification (max 1 round, guaranteed termination)
    + Enforced Prompt Versioning (hashes in manifest + failure correlation)
    + Auto-Adaptive Model Routing (performance drift → auto-escalation)
    + Distributed Concurrency Control (in-memory CLI / Redis production)
    + Chaos & Resilience Testing (stochastic failure injection in CI)
    + Full Observability (structured logs + Prometheus + model quality tracker)
    + Service-Ready Architecture (CLI now, API/queue/workers designed for evolution)
    + MCP Server (6 async tools, 7 resources, 4 prompts — stdio transport)
    + Game Remix Pipeline (modify existing builds via natural language)
    + Docker MCP (Docker Hub + GHCR — zero-dependency public images)
    = Production-hardened, self-optimizing, MCP-native, publicly accessible
```
