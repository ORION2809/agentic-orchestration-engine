"""Code validator — JS syntax, HTML linkage, CSS non-empty checks."""

from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path
from typing import Iterable

import structlog

from app.models.schemas import GeneratedGame, ValidationCheck

logger = structlog.get_logger()


def check_file_existence(game: GeneratedGame) -> ValidationCheck:
    """Check all 3 files exist and are non-empty."""
    issues = []
    if not game.index_html or len(game.index_html.strip()) < 50:
        issues.append("index.html missing or too short")
    if not game.style_css or len(game.style_css.strip()) < 10:
        issues.append("style.css missing or too short")
    if not game.game_js or len(game.game_js.strip()) < 100:
        issues.append("game.js missing or too short")

    if issues:
        return ValidationCheck(
            name="file_existence",
            passed=False,
            details="; ".join(issues),
            severity="blocker",
        )
    return ValidationCheck(name="file_existence", passed=True, severity="info")


def check_html_structure(game: GeneratedGame) -> ValidationCheck:
    """Validate HTML5 structure, script/link references, and canvas presence."""
    issues = []

    if "<!DOCTYPE html>" not in game.index_html and "<!doctype html>" not in game.index_html:
        issues.append("Missing HTML5 doctype")

    if 'style.css' not in game.index_html:
        issues.append("Missing <link> to style.css")

    if 'game.js' not in game.index_html:
        issues.append("Missing <script> to game.js")

    if "<canvas" not in game.index_html.lower() and "phaser" not in game.index_html.lower():
        issues.append("No <canvas> or game container found")

    if issues:
        return ValidationCheck(
            name="html_structure",
            passed=False,
            details="; ".join(issues),
            severity="blocker",
        )
    return ValidationCheck(name="html_structure", passed=True, severity="info")


def check_css_validity(game: GeneratedGame) -> ValidationCheck:
    """Basic CSS validity check."""
    css = game.style_css.strip()
    if not css:
        return ValidationCheck(
            name="css_validity",
            passed=False,
            details="CSS is empty",
            severity="warning",
        )

    # Check for unmatched braces
    if css.count("{") != css.count("}"):
        return ValidationCheck(
            name="css_validity",
            passed=False,
            details="Unmatched braces in CSS",
            severity="warning",
        )

    return ValidationCheck(name="css_validity", passed=True, severity="info")


def check_js_syntax(game: GeneratedGame) -> ValidationCheck:
    """Run `node --check` on the JS to catch syntax errors."""
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".js", delete=False, encoding="utf-8"
        ) as f:
            f.write(game.game_js)
            f.flush()
            tmp_path = f.name

        result = subprocess.run(
            ["node", "--check", tmp_path],
            capture_output=True,
            text=True,
            timeout=5,
        )

        Path(tmp_path).unlink(missing_ok=True)

        if result.returncode == 0:
            return ValidationCheck(name="js_syntax", passed=True, severity="info")
        else:
            return ValidationCheck(
                name="js_syntax",
                passed=False,
                details=result.stderr[:300] if result.stderr else "Syntax error",
                severity="blocker",
            )
    except FileNotFoundError:
        logger.warning("node_not_found_for_syntax_check")
        return ValidationCheck(
            name="js_syntax",
            passed=True,
            details="Node.js not available — syntax check skipped",
            severity="info",
        )
    except subprocess.TimeoutExpired:
        return ValidationCheck(
            name="js_syntax",
            passed=False,
            details="node --check timed out (5s)",
            severity="blocker",
        )
    except Exception as e:
        return ValidationCheck(
            name="js_syntax",
            passed=False,
            details=f"Syntax check error: {e}",
            severity="warning",
        )


def check_structural_heuristics(game: GeneratedGame) -> ValidationCheck:
    """Check for essential patterns: game loop, input handlers, score tracking."""
    issues = []

    # Game loop
    if (
        "requestAnimationFrame" not in game.game_js
        and "setInterval" not in game.game_js
        and "Phaser.Game" not in game.game_js
    ):
        issues.append("No game loop (requestAnimationFrame/setInterval/Phaser)")

    # Input handlers
    if (
        "addEventListener" not in game.game_js
        and "this.input" not in game.game_js
    ):
        issues.append("No input event listeners")

    # Score/lives tracking
    if not re.search(r"score|points|lives|health", game.game_js, re.IGNORECASE):
        issues.append("No score/points/lives tracking detected")

    # Draw/render function
    if not re.search(r"draw|render|update|paint|tick", game.game_js, re.IGNORECASE):
        issues.append("No draw/render/update function detected")

    if issues:
        return ValidationCheck(
            name="structural_heuristics",
            passed=False,
            details="; ".join(issues),
            severity="blocker" if len(issues) > 1 else "warning",
        )
    return ValidationCheck(name="structural_heuristics", passed=True, severity="info")


def run_code_validation(game: GeneratedGame) -> list[ValidationCheck]:
    """Run all code validation checks sequentially."""
    return [
        check_file_existence(game),
        check_html_structure(game),
        check_css_validity(game),
        check_js_syntax(game),
        check_structural_heuristics(game),
    ]


def load_game_from_dir(
    game_dir: Path,
    filenames: Iterable[str] | None = None,
) -> GeneratedGame:
    """Load generated game files from a directory into a GeneratedGame model."""
    allowed = {"index.html", "style.css", "game.js"}
    selected = set(filenames or allowed)
    selected = {name for name in selected if name in allowed}

    files: dict[str, str] = {}
    for name in selected:
        path = game_dir / name
        if path.exists() and path.is_file():
            files[name] = path.read_text(encoding="utf-8")

    return GeneratedGame.model_construct(  # type: ignore[call-arg]
        index_html=files.get("index.html", ""),
        style_css=files.get("style.css", ""),
        game_js=files.get("game.js", ""),
    )


def run_code_validation_from_dir(
    game_dir: Path,
    filenames: Iterable[str] | None = None,
) -> list[ValidationCheck]:
    """Directory convenience wrapper for static code validation."""
    game = load_game_from_dir(game_dir, filenames)
    return run_code_validation(game)
