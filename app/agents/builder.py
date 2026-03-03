"""Phase 3: Builder Agent — generates HTML/CSS/JS game files from a plan."""

from __future__ import annotations

from typing import Any

import structlog

from app.agents.base import BaseAgent
from app.models.schemas import GamePlan, GeneratedGame
from app.models.state import RunContext

logger = structlog.get_logger()


class BuilderAgent(BaseAgent):
    """Generates three game files (index.html, style.css, game.js) from a GamePlan.

    Supports two modes:
        - Fresh generation (from plan)
        - Repair mode (fix specific issues from critic/validator)
    """

    PHASE_NAME = "builder"

    def run(self, context: RunContext) -> GeneratedGame:
        if context.repair_instructions or context.validation_errors:
            return self._repair(context)
        return self._generate_fresh(context)

    def _generate_fresh(self, context: RunContext) -> GeneratedGame:
        """Full generation from the game plan."""
        plan_data = context.plan or {}
        plan = GamePlan(**plan_data) if isinstance(plan_data, dict) else plan_data

        logger.info("builder_fresh_start", title=plan.game_title)

        system_prompt = self.load_prompt("builder_system.md")
        user_prompt = self._build_generation_prompt(plan)

        game = self.call_structured(
            messages=[
                {
                    "role": "system",
                    "content": system_prompt or self._default_system_prompt(),
                },
                {"role": "user", "content": user_prompt},
            ],
            response_model=GeneratedGame,
            max_retries=2,
        )

        logger.info(
            "builder_fresh_done",
            html_len=len(game.index_html),
            css_len=len(game.style_css),
            js_len=len(game.game_js),
        )
        return game

    def _repair(self, context: RunContext) -> GeneratedGame:
        """Targeted repair — fix specific issues in existing code."""
        plan_data = context.plan or {}
        plan = GamePlan(**plan_data) if isinstance(plan_data, dict) else plan_data
        previous_files = context.game_files or {}

        errors: list[str] = []
        if context.repair_instructions:
            errors.extend(str(item) for item in context.repair_instructions)
        if context.validation_errors:
            errors.extend(str(item) for item in context.validation_errors)
        if not errors:
            errors.append("General quality issues detected; improve reliability.")

        logger.info("builder_repair_start", num_errors=len(errors))

        system_prompt = self.load_prompt("builder_system.md")
        prompt = f"""The previous code had these errors that must be fixed:

{chr(10).join(f"- {e}" for e in errors)}

Previous game.js:
```javascript
{previous_files.get('game.js', previous_files.get('game_js', ''))}
```

Previous index.html:
```html
{previous_files.get('index.html', previous_files.get('index_html', ''))}
```

Previous style.css:
```css
{previous_files.get('style.css', previous_files.get('style_css', ''))}
```

Game plan for reference:
{plan.model_dump_json(indent=2)}

Fix ONLY the issues listed above. Keep all working code intact.
Return the complete, corrected files."""

        game = self.call_structured(
            messages=[
                {
                    "role": "system",
                    "content": system_prompt or self._default_system_prompt(),
                },
                {"role": "user", "content": prompt},
            ],
            response_model=GeneratedGame,
            max_retries=2,
        )

        logger.info(
            "builder_repair_done",
            html_len=len(game.index_html),
            css_len=len(game.style_css),
            js_len=len(game.game_js),
        )
        return game

    def _build_generation_prompt(self, plan: GamePlan) -> str:
        user_template = self.load_prompt("builder_user.md")
        plan_json = plan.model_dump_json(indent=2)

        if user_template:
            return user_template.replace("{{plan_json}}", plan_json)

        return f"""Generate a complete, playable browser game based on this plan:

{plan_json}

Requirements:
1. Generate complete index.html with proper HTML5 structure
2. Include <link rel="stylesheet" href="style.css"> and <script src="game.js"></script>
3. Include a <canvas> element for rendering (or appropriate container)
4. Include a Content-Security-Policy meta tag: default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'none'; frame-src 'none';

5. Generate style.css with game layout and styling
6. Canvas should be centered on the page with a border
7. Include HUD styling for score/lives display

8. Generate complete game.js implementing ALL mechanics from the plan:
   - Use requestAnimationFrame for the game loop
   - Add keyboard event listeners matching the control scheme
   - Implement ALL entities from the plan
   - Implement scoring, win/lose conditions
   - Implement game state transitions (menu → playing → game_over)
   - Include restart capability
   - Draw score/lives HUD on canvas

HARD RULES:
- NO external CDN dependencies (except Phaser CDN if framework=phaser)
- NO fetch(), XMLHttpRequest, or WebSocket calls
- NO eval() or new Function()
- NO alert() or prompt() for game events
- NO document.write()
- NO localStorage or sessionStorage
- Use ONLY requestAnimationFrame or Phaser's built-in loop
- All game code must be self-contained in these 3 files"""

    def _default_system_prompt(self) -> str:
        return """You are an expert browser game developer. You generate complete, playable
HTML5/CSS/JavaScript games from detailed game plans.

Your output must be three complete files:
1. index_html: Valid HTML5 with correct references to CSS and JS
2. style_css: Clean CSS for game layout
3. game_js: Complete, working game implementation

Rules:
- Games must work immediately when opened in a browser
- Use Canvas API for rendering (vanilla JS)
- Always include requestAnimationFrame-based game loop
- Always include keyboard/mouse event listeners
- Always include score tracking and display
- Always include game-over detection and restart
- Never use external APIs, fetch, eval, or document.write
- Code must be clean, well-commented, and self-contained"""
