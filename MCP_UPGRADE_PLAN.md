# MCP Server Upgrade Plan

## Version History

| Version | Date       | Description                                     |
|---------|------------|-------------------------------------------------|
| 2.0.0   | 2026-03-10 | Initial MCP server — 5 sync tools, 7 resources, 3 prompts |
| 2.1.0   | 2026-03-11 | Async tools, progress notifications, remix_game, 4 prompts |

---

## What Was Implemented (v2.0.0 → v2.1.0)

### Architecture Overview

The MCP server (`app/mcp_server.py`) wraps the existing CLI-based game builder as a Model Context Protocol service. Any MCP-compatible client — Claude Desktop, VS Code Copilot, Cursor, Windsurf — can connect via stdio transport and call tools to build, validate, remix, and inspect games.

```
┌──────────────────────────────────────────────────────────┐
│ MCP Client (Claude Desktop / VS Code / Cursor)          │
│                                                          │
│  "build me a space shooter"                              │
│        ↓ tool_call: build_game                           │
│        ↓ progress: [1/6] Clarifying game idea            │
│        ↓ progress: [2/6] Planning architecture           │
│        ↓ progress: [3/6] Generating game code            │
│        ↓ progress: [4/6] Reviewing code for bugs         │
│        ↓ progress: [5/6] Running validation checks       │
│        ↓ progress: [6/6] Build complete                  │
│        ↓ result: {run_id, success, game_files, cost}     │
│                                                          │
│  "add neon effects and sound"                            │
│        ↓ tool_call: remix_game                           │
│        ↓ (same progress flow)                            │
│        ↓ result: {new_run_id, original preserved}        │
└──────────────────────────────────────────────────────────┘
         ↕ stdio (JSON-RPC 2.0)
┌──────────────────────────────────────────────────────────┐
│ MCP Server (app/mcp_server.py)                           │
│                                                          │
│  FastMCP("game-builder")                                 │
│  ├── 6 Tools (async, threaded orchestrator)              │
│  ├── 7 Resources (static + templates)                    │
│  ├── 4 Prompts (idea refiner, config, analyze, remix)    │
│  └── Progress callback → ctx.report_progress()           │
│                                                          │
│  Orchestrator runs in thread pool executor               │
│  Progress callback uses run_coroutine_threadsafe()       │
└──────────────────────────────────────────────────────────┘
         ↕ Python function calls
┌──────────────────────────────────────────────────────────┐
│ Orchestrator Pipeline (app/orchestrator.py)               │
│                                                          │
│  INIT → CLARIFY → PLAN → BUILD → CRITIQUE → VALIDATE    │
│                     ↑        ↓                           │
│                     └────────┘ (repair cycle, max 2)     │
│                                                          │
│  6 agents, AST critic, Playwright validator              │
│  Deterministic state machine with checkpoint/resume      │
└──────────────────────────────────────────────────────────┘
```

### Issue 1: Sync Tools Blocking the Event Loop (FIXED)

**Problem:** All 5 tools were defined as synchronous `def` functions. The `build_game` tool calls `orchestrator.run()` which takes 60–180 seconds. Even though FastMCP wraps sync tools in a thread internally, this was implicit and the MCP event loop couldn't process any concurrent messages (like cancellation requests) during that time.

**Solution:** All tools that do I/O are now `async def` with explicit `Context` injection:

```python
@mcp.tool()
async def build_game(idea: str, ctx: Context, model: str = "gpt-4o", output_dir: str = "outputs") -> str:
    loop = asyncio.get_running_loop()
    # Orchestrator runs in thread pool — event loop stays responsive
    result = await loop.run_in_executor(None, orchestrator.run, idea)
    return _format_result(result)
```

**Why `run_in_executor` instead of just `async def`:** The orchestrator and all its agents are synchronous code (they use `requests`/`httpx` sync calls under the hood via litellm). We can't easily make the entire pipeline async. Running it in a thread pool executor is the correct pattern — it keeps the event loop free to handle progress notifications, cancellations, and concurrent tool calls.

### Issue 2: Silent 2–3 Minute Builds — No Progress (FIXED)

**Problem:** The client sent a `build_game` call and got nothing back for 60–180 seconds. No indication of what phase the pipeline was in, whether it was stuck, or how far along it was.

**Solution:** Added a progress callback mechanism that bridges the sync orchestrator → async MCP notifications:

1. **Orchestrator side** (`app/orchestrator.py`): Added an optional `progress_callback` parameter to `__init__`. The `transition()` method calls it on every state change:

```python
def transition(self, new_state: AgentState) -> None:
    # ... existing transition logic ...
    if self._progress_callback:
        try:
            self._progress_callback(new_state, self.build_number, self.retry_count)
        except Exception:
            pass  # Never break the pipeline for notification failures
```

2. **MCP server side** (`app/mcp_server.py`): The callback is created per-request and uses `asyncio.run_coroutine_threadsafe()` to schedule async notifications from the worker thread back onto the event loop:

```python
def _make_progress_callback(ctx: Context, loop: asyncio.AbstractEventLoop):
    def _on_phase_transition(state, build_number, retry_count):
        step, description = _PHASE_META.get(state.value, (0, state.value))
        asyncio.run_coroutine_threadsafe(
            ctx.report_progress(step, _TOTAL_PHASES, description), loop
        )
        asyncio.run_coroutine_threadsafe(
            ctx.info(f"[{step}/{_TOTAL_PHASES}] {description}"), loop
        )
    return _on_phase_transition
```

**Progress phases reported:**
| Step | Phase        | Description                      |
|------|-------------|----------------------------------|
| 0    | init        | Initializing pipeline            |
| 1    | clarifying  | Clarifying game idea             |
| 2    | planning    | Planning architecture & mechanics|
| 3    | building    | Generating game code             |
| 4    | critiquing  | Reviewing code for bugs          |
| 5    | validating  | Running validation checks        |
| 6    | done/failed | Build complete / Build failed    |

Retry cycles are annotated: `"Generating game code (retry 1)"`.

Clients that send a `progressToken` in the tool call metadata see a real-time progress bar. All clients see `notifications/message` log entries.

### Issue 3: Missing `remix_game` Tool (ADDED)

**Problem:** The project roadmap mentions a remix workflow but it wasn't implemented. Building games is one-shot — users can't iterate on what the AI generated.

**Solution:** Added `remix_game` tool that:

1. Loads the existing game source from `outputs/{run_id}/latest/`
2. Loads the original idea from `context.json`
3. Constructs a remix prompt that includes ALL existing code + the user's modification instructions
4. Runs the full pipeline (CLARIFY → PLAN → BUILD → CRITIQUE → VALIDATE)
5. Outputs a NEW build (original is preserved)

```python
@mcp.tool()
async def remix_game(
    run_id: str,
    instructions: str,
    ctx: Context,
    model: str = "gpt-4o",
    output_dir: str = "outputs",
) -> str:
```

**Remix workflow example:**
```
User: "list_builds" → sees run_id=41323c2e (Space Dodger)
User: "remix_game(run_id='41323c2e', instructions='Add neon glow effects, screen shake, and a high score display')"
→ New build created as a separate run_id
→ Original 41323c2e preserved
```

Also added a `remix_workflow` prompt that guides users through the review → choose modifications → execute → compare cycle.

---

## Complete MCP Surface (v2.1.0)

### Tools (6)

| Tool | Type | Description |
|------|------|-------------|
| `build_game` | async + progress | Full pipeline: idea → playable HTML5 game |
| `validate_game` | async | File existence, HTML/CSS/JS checks, security scan |
| `resume_build` | async + progress | Resume interrupted build from checkpoint |
| `remix_game` | async + progress | Modify existing build with new instructions |
| `list_builds` | async | List all builds with status and metrics |
| `get_build_files` | async | Retrieve game source code for a build |

### Resources (7)

| URI | Type | Description |
|-----|------|-------------|
| `builds://latest` | Static | Most recent build summary |
| `builds://{run_id}/result` | Template | Full JSON run result |
| `builds://{run_id}/report` | Template | Markdown build report |
| `builds://{run_id}/manifest` | Template | Prompt version manifest |
| `builds://{run_id}/game/index.html` | Template | Generated HTML |
| `builds://{run_id}/game/style.css` | Template | Generated CSS |
| `builds://{run_id}/game/game.js` | Template | Generated JavaScript |

### Prompts (4)

| Prompt | Args | Description |
|--------|------|-------------|
| `game_idea_refiner` | `vague_idea` | Refine rough ideas into detailed specs |
| `build_config_guide` | none | Configuration options reference |
| `analyze_game_code` | `run_id` | Code review guide for generated games |
| `remix_workflow` | `run_id` | Interactive remix workflow guide |

---

## Files Changed

| File | Change |
|------|--------|
| `app/mcp_server.py` | Complete rewrite: sync→async, Context injection, progress callbacks, remix_game tool, remix_workflow prompt |
| `app/orchestrator.py` | Added `progress_callback` parameter, `Callable` import, callback invocation in `transition()` |

---

## Testing Verification

### Smoke Test (programmatic)
Connects as a real stdio MCP client (same transport as Claude Desktop):

- **Tool discovery**: 6 tools registered with descriptions and schemas ✓
- **Tool calls**: `list_builds`, `get_build_files`, `validate_game`, `resume_build` — all return valid JSON, handle errors gracefully ✓
- **Resources**: 1 static + 6 templates, all readable with real build data ✓
- **Prompts**: 4 prompts listed, all return correct content ✓
- **Async**: All tools are properly `async def` ✓
- **Progress**: `_make_progress_callback` constructs callback, `run_coroutine_threadsafe` bridges thread→event-loop ✓

### Integration Test (real build data)
Against `outputs_final/41323c2e` (Space Dodger, 18,121 tokens, $0.045):
- `list_builds` → found 1 build ✓
- `get_build_files` → index.html (348), style.css (210), game.js (3,744 chars) ✓
- All 6 resource URIs → readable ✓
- `validate_game` → passed=True, 5/5 checks ✓

### Existing test suite
40/40 tests pass (no regressions from orchestrator changes) ✓

---

## Future Roadmap

### Near-term (planned for v2.2.0)

1. **Streaming tool output** — For `build_game` and `remix_game`, stream intermediate artifacts (e.g., the game plan, critique findings) as the build progresses, not just progress bar numbers.

2. **Cancel running builds** — MCP supports request cancellation. Wire `ctx.request_context` cancellation signals to abort the orchestrator mid-pipeline gracefully.

3. **Multi-game workspace** — Add a `workspace://` resource scheme that provides a project-level view across all builds, with comparison tools.

4. **Template library** — Pre-built game templates (platformer, shooter, puzzle) that can be used as starting points instead of generating from scratch. Would dramatically improve quality for common genres.

### Medium-term (v3.0.0)

5. **SSE transport** — Add HTTP/SSE transport alongside stdio for web-based MCP clients and remote access.

6. **Persistent sessions** — Track conversation context across multiple tool calls so `remix_game` can reference "the game we built earlier" without explicit run_ids.

7. **A/B generation** — Generate two variants of a game simultaneously and let the user compare/choose the better one.

8. **Asset generation** — Integrate with image generation APIs to create actual sprite assets instead of rectangles/circles.
