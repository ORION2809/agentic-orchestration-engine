"""Debug AST injector — injects debug hooks into generated game JS for behavioral testing."""

from __future__ import annotations

import re
from pathlib import Path

import structlog

logger = structlog.get_logger()

# JavaScript snippet that monkey-patches requestAnimationFrame to expose game state.
# When window.__GAME_DEBUG__ is set, the hook intercepts the RAF callback and
# captures any state object attached to the callback function or global scope.
DEBUG_HOOK_SNIPPET = """
// === DEBUG HOOK (injected by Agentic Game-Builder) ===
(function() {
    if (!window.__GAME_DEBUG__) return;

    window.__debug_state = {};
    window.__debug_frames = 0;
    window.__debug_fps_samples = [];

    var _origRAF = window.requestAnimationFrame;
    var _lastTime = performance.now();
    var _entityCountPrev = 0;

    window.requestAnimationFrame = function(callback) {
        return _origRAF.call(window, function(timestamp) {
            // FPS tracking
            window.__debug_frames++;
            var delta = timestamp - _lastTime;
            _lastTime = timestamp;
            if (delta > 0) {
                window.__debug_fps_samples.push(1000 / delta);
                if (window.__debug_fps_samples.length > 60) {
                    window.__debug_fps_samples.shift();
                }
            }

            // Execute the original callback
            callback(timestamp);

            // Attempt to capture game state from common patterns
            try {
                // Look for common global game state objects
                var stateKeys = ['gameState', 'state', 'game', 'GAME', 'gs'];
                for (var i = 0; i < stateKeys.length; i++) {
                    var candidate = window[stateKeys[i]];
                    if (candidate && typeof candidate === 'object') {
                        // Shallow copy relevant properties
                        var s = {};
                        var keys = Object.keys(candidate);
                        for (var j = 0; j < keys.length; j++) {
                            var k = keys[j];
                            var v = candidate[k];
                            if (typeof v !== 'function') {
                                s[k] = v;
                            }
                        }
                        // Extract player position
                        if (candidate.player && typeof candidate.player === 'object') {
                            s.player = { x: candidate.player.x, y: candidate.player.y };
                        }
                        // Extract score
                        if ('score' in candidate) s.score = candidate.score;
                        if ('gameOver' in candidate) s.gameOver = candidate.gameOver;

                        // Entity growth tracking
                        var entityCount = 0;
                        if (Array.isArray(candidate.entities)) entityCount = candidate.entities.length;
                        else if (Array.isArray(candidate.enemies)) entityCount = candidate.enemies.length;
                        else if (Array.isArray(candidate.objects)) entityCount = candidate.objects.length;
                        s.entityCount = entityCount;
                        s._entityGrowthRate = entityCount - _entityCountPrev;
                        _entityCountPrev = entityCount;

                        window.__debug_state = s;
                        break;
                    }
                }
            } catch (e) {
                // Silently fail — do not interfere with game
            }
        });
    };
})();
// === END DEBUG HOOK ===
"""


def inject_debug_hooks(js_content: str) -> str:
    """Inject debug hooks at the top of JS content.

    The hook is prepended so it patches requestAnimationFrame before
    the game code runs.

    Args:
        js_content: Original JavaScript source code.

    Returns:
        Modified JS with debug hooks prepended.
    """
    if "window.__GAME_DEBUG__" in js_content:
        logger.debug("debug_hooks_already_present")
        return js_content

    return DEBUG_HOOK_SNIPPET + "\n" + js_content


def inject_debug_hooks_into_html(html_content: str) -> str:
    """Inject debug hooks as a <script> block before the first game script in HTML.

    If the game includes inline JS or external script tags, the hook is inserted
    as an early <script> block right after <head> or before the first <script>.
    """
    if "window.__GAME_DEBUG__" in html_content:
        logger.debug("debug_hooks_already_present_in_html")
        return html_content

    hook_script = f"<script>\n{DEBUG_HOOK_SNIPPET}\n</script>"

    # Strategy 1: Insert before first <script> tag
    pattern = re.compile(r"(<script[\s>])", re.IGNORECASE)
    match = pattern.search(html_content)
    if match:
        insert_pos = match.start()
        return html_content[:insert_pos] + hook_script + "\n" + html_content[insert_pos:]

    # Strategy 2: Insert at end of <head>
    head_close = html_content.lower().find("</head>")
    if head_close != -1:
        return html_content[:head_close] + hook_script + "\n" + html_content[head_close:]

    # Strategy 3: Insert at beginning of <body>
    body_open = re.search(r"<body[^>]*>", html_content, re.IGNORECASE)
    if body_open:
        end = body_open.end()
        return html_content[:end] + "\n" + hook_script + "\n" + html_content[end:]

    # Fallback: prepend
    return hook_script + "\n" + html_content


def write_artifacts(
    game_files: dict[str, str],
    output_dir: Path,
    build_number: int,
    run_id: str,
) -> tuple[Path, Path]:
    """Write game artifacts to both debug/ and game/ directories.

    The debug/ directory gets files WITH debug hooks injected.
    The game/ directory gets the clean production files.

    Args:
        game_files: filename → source content mapping
        output_dir: Base output directory
        build_number: Current build iteration number
        run_id: Unique run identifier

    Returns:
        Tuple of (debug_dir, game_dir) paths
    """
    run_dir = output_dir / run_id
    debug_dir = run_dir / f"build_{build_number}" / "debug"
    game_dir = run_dir / f"build_{build_number}" / "game"

    debug_dir.mkdir(parents=True, exist_ok=True)
    game_dir.mkdir(parents=True, exist_ok=True)

    for filename, content in game_files.items():
        # Write clean version to game/
        game_path = game_dir / filename
        game_path.parent.mkdir(parents=True, exist_ok=True)
        game_path.write_text(content, encoding="utf-8")

        # Write debug version to debug/
        debug_content = content
        if filename.endswith(".js"):
            debug_content = inject_debug_hooks(content)
        elif filename.endswith(".html"):
            debug_content = inject_debug_hooks_into_html(content)

        debug_path = debug_dir / filename
        debug_path.parent.mkdir(parents=True, exist_ok=True)
        debug_path.write_text(debug_content, encoding="utf-8")

    logger.info(
        "artifacts_written",
        run_id=run_id,
        build_number=build_number,
        files=list(game_files.keys()),
        debug_dir=str(debug_dir),
        game_dir=str(game_dir),
    )

    # Also copy to a "latest" symlink / directory
    latest_dir = run_dir / "latest"
    import shutil
    if latest_dir.exists():
        shutil.rmtree(latest_dir)
    shutil.copytree(game_dir, latest_dir)

    return debug_dir, game_dir
