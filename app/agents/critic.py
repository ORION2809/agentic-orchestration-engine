"""Phase 4: Critic Agent — hybrid deterministic (AST) + LLM self-reflection."""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import structlog

from app.agents.base import BaseAgent
from app.models.schemas import (
    CriticFinding,
    CritiqueResult,
    GamePlan,
    GeneratedGame,
)
from app.models.state import RunContext

logger = structlog.get_logger()

# ────────────────────────────────────
# AST-based analysis script (esprima)
# ────────────────────────────────────

AST_ANALYSIS_SCRIPT = r"""
const esprima = require('esprima');
const code = require('fs').readFileSync(process.argv[1], 'utf-8');

try {
    const ast = esprima.parseScript(code, { tolerant: true });

    const analysis = {
        call_expressions: [],
        event_listeners: [],
        variable_names: [],
        has_raf: false,
        has_game_loop: false,
    };

    function walk(node) {
        if (!node || typeof node !== 'object') return;

        if (node.type === 'CallExpression') {
            const callee = node.callee;
            let name = '';
            if (callee.type === 'Identifier') name = callee.name;
            else if (callee.type === 'MemberExpression')
                name = callee.property ? (callee.property.name || callee.property.value || '') : '';

            analysis.call_expressions.push(name);

            if (name === 'requestAnimationFrame' || name === 'raf') {
                analysis.has_raf = true;
                analysis.has_game_loop = true;
            }
            if (name === 'setInterval' || name === 'setTimeout') {
                analysis.has_game_loop = true;
            }
            if (name === 'addEventListener') {
                const eventType = node.arguments && node.arguments[0] ? node.arguments[0].value : 'unknown';
                analysis.event_listeners.push(eventType || 'unknown');
            }
        }

        if (node.type === 'VariableDeclarator' && node.id && node.id.name) {
            analysis.variable_names.push(node.id.name);
        }

        for (const key of Object.keys(node)) {
            if (key === 'type') continue;
            const child = node[key];
            if (Array.isArray(child)) child.forEach(walk);
            else if (child && typeof child === 'object' && typeof child.type === 'string') walk(child);
        }
    }

    walk(ast);
    console.log(JSON.stringify(analysis));
} catch (e) {
    console.error(JSON.stringify({ error: e.message }));
    process.exit(1);
}
"""


class ASTCritic:
    """AST-based code analysis using esprima (Node.js subprocess)."""

    def analyze(self, game_js_content: str) -> dict | None:
        """Run esprima AST analysis on game.js content."""
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                js_path = Path(tmpdir) / "game.js"
                script_path = Path(tmpdir) / "_ast_analysis.js"

                js_path.write_text(game_js_content, encoding="utf-8")
                script_path.write_text(AST_ANALYSIS_SCRIPT, encoding="utf-8")

                # Build NODE_PATH so esprima can be found from temp dir
                # In Docker: ENV NODE_PATH=/usr/local/lib/node_modules (global install)
                # Locally: project-root/node_modules (npm install esprima)
                import os
                env = os.environ.copy()
                project_node_modules = str(Path(__file__).resolve().parent.parent.parent / "node_modules")
                paths = [p for p in [project_node_modules, env.get("NODE_PATH", "")] if p]
                env["NODE_PATH"] = os.pathsep.join(paths)

                result = subprocess.run(
                    ["node", str(script_path), str(js_path)],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    env=env,
                )

                if result.returncode == 0 and result.stdout.strip():
                    return json.loads(result.stdout.strip())
                else:
                    logger.warning(
                        "ast_analysis_failed",
                        stderr=result.stderr[:200] if result.stderr else "",
                    )
                    return None
        except FileNotFoundError:
            logger.warning("node_not_found", msg="Node.js not available for AST analysis")
            return None
        except Exception as e:
            logger.warning("ast_analysis_error", error=str(e))
            return None


class DeterministicCritic:
    """AST-first, regex-fallback code analysis. No LLM cost."""

    def __init__(self) -> None:
        self.ast_critic = ASTCritic()

    def check(
        self, plan: GamePlan, game: GeneratedGame
    ) -> list[CriticFinding]:
        findings: list[CriticFinding] = []

        # Try AST analysis first
        ast_result = self.ast_critic.analyze(game.game_js)

        if ast_result:
            findings.extend(self._check_with_ast(plan, game, ast_result))
        else:
            logger.info("ast_unavailable_falling_back_to_regex")
            findings.extend(self._check_with_regex(plan, game))

        # HTML structural checks (always run)
        findings.extend(self._check_html(game))
        # CSS checks
        findings.extend(self._check_css(game))

        return findings

    def _check_with_ast(
        self, plan: GamePlan, game: GeneratedGame, ast: dict
    ) -> list[CriticFinding]:
        findings: list[CriticFinding] = []

        # Game loop
        if not ast.get("has_game_loop"):
            findings.append(
                CriticFinding(
                    severity="critical",
                    category="missing_feature",
                    description="No game loop detected (no requestAnimationFrame, setInterval, or aliases)",
                    affected_file="game.js",
                    suggested_fix="Add requestAnimationFrame-based game loop",
                    source="deterministic",
                )
            )

        # Input handling
        input_events = {"keydown", "keyup", "keypress", "mousedown", "mouseup", "click", "mousemove"}
        listeners = set(ast.get("event_listeners", []))
        if not listeners.intersection(input_events):
            findings.append(
                CriticFinding(
                    severity="critical",
                    category="missing_feature",
                    description="No input event listener found in AST",
                    affected_file="game.js",
                    suggested_fix="Add keyboard/mouse event listeners",
                    source="deterministic",
                )
            )

        # Score variable
        score_vars = {"score", "points", "kills", "lives", "health"}
        var_names = {v.lower() for v in ast.get("variable_names", [])}
        if not var_names.intersection(score_vars):
            findings.append(
                CriticFinding(
                    severity="warning",
                    category="missing_feature",
                    description="No score/points variable found in AST variable declarations",
                    affected_file="game.js",
                    suggested_fix="Add score tracking variable",
                    source="deterministic",
                )
            )

        # Game-over condition (regex — looking for string patterns)
        if not re.search(r"game.?over|game.?end|lose|lost|dead|isGameOver", game.game_js, re.IGNORECASE):
            findings.append(
                CriticFinding(
                    severity="critical",
                    category="missing_feature",
                    description="No game-over condition detected",
                    affected_file="game.js",
                    suggested_fix="Add game-over state transition",
                    source="deterministic",
                )
            )

        # Entity coverage
        for entity in plan.entities:
            if entity.name.lower() not in game.game_js.lower():
                findings.append(
                    CriticFinding(
                        severity="warning",
                        category="missing_feature",
                        description=f"Entity '{entity.name}' from plan not found in code",
                        affected_file="game.js",
                        suggested_fix=f"Implement {entity.name}",
                        source="deterministic",
                    )
                )

        return findings

    def _check_with_regex(
        self, plan: GamePlan, game: GeneratedGame
    ) -> list[CriticFinding]:
        """Fallback regex-based checks when AST parsing fails."""
        findings: list[CriticFinding] = []

        if "requestAnimationFrame" not in game.game_js and "Phaser.Game" not in game.game_js:
            findings.append(
                CriticFinding(
                    severity="critical",
                    category="missing_feature",
                    description="No game loop detected (regex fallback)",
                    affected_file="game.js",
                    suggested_fix="Add requestAnimationFrame-based game loop",
                    source="deterministic",
                )
            )

        if "addEventListener" not in game.game_js and "this.input" not in game.game_js:
            findings.append(
                CriticFinding(
                    severity="critical",
                    category="missing_feature",
                    description="No input event listener found (regex fallback)",
                    affected_file="game.js",
                    suggested_fix="Add keyboard/mouse event listeners",
                    source="deterministic",
                )
            )

        if not re.search(r"game.?over|game.?end|lose|lost|dead", game.game_js, re.IGNORECASE):
            findings.append(
                CriticFinding(
                    severity="critical",
                    category="missing_feature",
                    description="No game-over condition detected (regex fallback)",
                    affected_file="game.js",
                    suggested_fix="Add game-over state transition",
                    source="deterministic",
                )
            )

        return findings

    def _check_html(self, game: GeneratedGame) -> list[CriticFinding]:
        findings: list[CriticFinding] = []

        if "game.js" not in game.index_html:
            findings.append(
                CriticFinding(
                    severity="critical",
                    category="linkage",
                    description="index.html does not reference game.js",
                    affected_file="index.html",
                    suggested_fix='Add <script src="game.js"></script>',
                    source="deterministic",
                )
            )

        if "style.css" not in game.index_html:
            findings.append(
                CriticFinding(
                    severity="critical",
                    category="linkage",
                    description="index.html does not reference style.css",
                    affected_file="index.html",
                    suggested_fix='Add <link rel="stylesheet" href="style.css">',
                    source="deterministic",
                )
            )

        if "<canvas" not in game.index_html.lower() and "phaser" not in game.index_html.lower():
            findings.append(
                CriticFinding(
                    severity="warning",
                    category="missing_feature",
                    description="No <canvas> element found in index.html",
                    affected_file="index.html",
                    suggested_fix="Add <canvas> element for game rendering",
                    source="deterministic",
                )
            )

        return findings

    def _check_css(self, game: GeneratedGame) -> list[CriticFinding]:
        findings: list[CriticFinding] = []
        if len(game.style_css.strip()) < 10:
            findings.append(
                CriticFinding(
                    severity="warning",
                    category="quality",
                    description="CSS is nearly empty",
                    affected_file="style.css",
                    suggested_fix="Add meaningful game styling",
                    source="deterministic",
                )
            )
        return findings


class CriticAgent(BaseAgent):
    """Hybrid critic: 80% deterministic (AST), 20% LLM reasoning."""

    PHASE_NAME = "critic"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.deterministic = DeterministicCritic()

    def run(self, context: RunContext) -> CritiqueResult:
        plan_data = context.plan or {}
        plan = GamePlan(**plan_data) if isinstance(plan_data, dict) else plan_data
        game_files = context.game_files or {}
        game = GeneratedGame.from_file_map(game_files) if isinstance(game_files, dict) else game_files

        logger.info("critic_start")

        # Layer 1: Deterministic checks (free, fast)
        det_findings = self.deterministic.check(plan, game)
        has_critical_det = any(f.severity == "critical" for f in det_findings)

        logger.info(
            "deterministic_critic_done",
            findings=len(det_findings),
            has_critical=has_critical_det,
        )

        # Layer 2: LLM critic — only if no deterministic criticals
        llm_findings: list[CriticFinding] = []
        llm_ran = False
        if not has_critical_det:
            try:
                llm_findings = self._run_llm_critic(plan, game)
                llm_ran = True
            except Exception as e:
                logger.warning("llm_critic_failed", error=str(e))

        all_findings = det_findings + llm_findings
        has_critical = any(f.severity == "critical" for f in all_findings)

        result = CritiqueResult(
            findings=all_findings,
            has_critical=has_critical,
            overall_assessment=self._summarize(all_findings),
            plan_compliance_score=self._compliance_score(all_findings, plan),
            deterministic_checks_run=len(det_findings),
            llm_checks_run=llm_ran,
        )

        logger.info(
            "critic_done",
            total_findings=len(all_findings),
            has_critical=has_critical,
            compliance=result.plan_compliance_score,
        )

        return result

    def _run_llm_critic(
        self, plan: GamePlan, game: GeneratedGame
    ) -> list[CriticFinding]:
        """LLM reasoning critic for subtle issues."""
        system_prompt = self.load_prompt("critic_system.md")
        prompt = f"""Review this game code against the plan. Look for:
1. Logic bugs (collision detection that never triggers, etc.)
2. UX issues (player starts off-screen, text unreadable, etc.)
3. Balancing problems (enemies too fast, impossible difficulty, etc.)
4. Missing plan features that deterministic checks missed

Game Plan:
{plan.model_dump_json(indent=2)}

game.js (first 3000 chars):
{game.game_js[:3000]}

index.html:
{game.index_html[:1000]}

List issues as JSON array of objects with: severity, category, description, affected_file, suggested_fix.
Only report real issues. If the code looks good, return an empty array []."""

        try:
            response = self.call_llm(
                messages=[
                    {
                        "role": "system",
                        "content": system_prompt or "You are an expert code reviewer for browser games.",
                    },
                    {"role": "user", "content": prompt},
                ]
            )

            # Parse LLM response as JSON
            # Try to extract JSON array from the response
            match = re.search(r"\[.*\]", response, re.DOTALL)
            if match:
                issues = json.loads(match.group())
                return [
                    CriticFinding(
                        severity=issue.get("severity", "warning"),
                        category=issue.get("category", "llm_review"),
                        description=issue.get("description", ""),
                        affected_file=issue.get("affected_file", "game.js"),
                        suggested_fix=issue.get("suggested_fix", ""),
                        source="llm",
                    )
                    for issue in issues
                    if isinstance(issue, dict)
                ]
            return []
        except Exception as e:
            logger.warning("llm_critic_parse_failed", error=str(e))
            return []

    def _summarize(self, findings: list[CriticFinding]) -> str:
        criticals = sum(1 for f in findings if f.severity == "critical")
        warnings = sum(1 for f in findings if f.severity == "warning")
        if criticals:
            return f"{criticals} critical issue(s), {warnings} warning(s) — rebuild required"
        if warnings:
            return f"{warnings} warning(s) — proceeding with caution"
        return "No issues found — code looks good"

    def _compliance_score(
        self, findings: list[CriticFinding], plan: GamePlan
    ) -> float:
        total_checks = max(len(plan.entities) + 5, 1)  # entities + basic checks
        failures = sum(1 for f in findings if f.severity in ("critical", "warning"))
        return round(max(0.0, 1.0 - failures / total_checks), 2)
