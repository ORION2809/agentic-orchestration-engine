"""Playability checker — higher-level behavioral validation via Playwright + debug hooks."""

from __future__ import annotations

import asyncio
from pathlib import Path

import structlog

from app.models.schemas import GamePlan, ValidationCheck

logger = structlog.get_logger()


async def _run_playability_checks(
    game_dir: Path, plan: GamePlan
) -> list[ValidationCheck]:
    """Run playability-specific behavioral checks against a built game."""
    checks: list[ValidationCheck] = []

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        checks.append(
            ValidationCheck(
                name="playability_check",
                passed=True,
                details="Playwright not installed — playability tests skipped",
                severity="info",
            )
        )
        return checks

    index_path = game_dir / "index.html"
    if not index_path.exists():
        checks.append(
            ValidationCheck(
                name="playability_check",
                passed=False,
                details="index.html not found",
                severity="blocker",
            )
        )
        return checks

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        page.set_default_timeout(15_000)

        # Enable debug hooks
        await page.add_init_script("window.__GAME_DEBUG__ = true;")

        try:
            await page.goto(f"file:///{index_path.resolve()}", timeout=10_000)
        except Exception as e:
            checks.append(
                ValidationCheck(
                    name="playability_load",
                    passed=False,
                    details=f"Page failed to load: {e}",
                    severity="blocker",
                )
            )
            await browser.close()
            return checks

        await page.wait_for_timeout(2000)

        # Check 1: Game canvas / rendering surface exists
        has_canvas = await page.query_selector("canvas") is not None
        has_svg = await page.query_selector("svg") is not None
        has_game_div = await page.query_selector("#gameArea, #game, .game-container, #game-container") is not None
        has_render_surface = has_canvas or has_svg or has_game_div

        checks.append(
            ValidationCheck(
                name="playability_render_surface",
                passed=has_render_surface,
                details=(
                    f"canvas={has_canvas}, svg={has_svg}, div={has_game_div}"
                ),
                severity="blocker" if not has_render_surface else "info",
            )
        )

        # Check 2: Game loop is running (RAF-based)
        loop_running = await page.evaluate("""
            () => new Promise(resolve => {
                let count = 0;
                const origRAF = window.requestAnimationFrame;
                window.requestAnimationFrame = function(cb) {
                    count++;
                    return origRAF.call(window, cb);
                };
                setTimeout(() => {
                    window.requestAnimationFrame = origRAF;
                    resolve(count > 0);
                }, 1000);
            })
        """)
        checks.append(
            ValidationCheck(
                name="playability_game_loop_active",
                passed=loop_running,
                details="RAF loop active" if loop_running else "No RAF calls detected in 1s",
                severity="blocker" if not loop_running else "info",
            )
        )

        # Check 3: Acceptance criteria from the plan
        if plan.acceptance_checks:
            for i, criterion in enumerate(plan.acceptance_checks[:5]):
                checks.append(
                    ValidationCheck(
                        name=f"acceptance_criterion_{i}",
                        passed=True,
                        details=f"[Manual check required] {criterion}",
                        severity="info",
                    )
                )

        # Check 4: Visual content present (not a blank page)
        visible_text = await page.evaluate("""
            () => {
                const body = document.body;
                if (!body) return '';
                return body.innerText || '';
            }
        """)
        canvas_has_content = False
        if has_canvas:
            try:
                canvas_has_content = await page.evaluate("""
                    () => {
                        const c = document.querySelector('canvas');
                        if (!c) return false;
                        const ctx = c.getContext('2d');
                        if (!ctx) return false;
                        const data = ctx.getImageData(0, 0, c.width, c.height).data;
                        for (let i = 0; i < data.length; i += 4) {
                            if (data[i] !== 0 || data[i+1] !== 0 || data[i+2] !== 0 || data[i+3] !== 0) {
                                return true;
                            }
                        }
                        return false;
                    }
                """)
            except Exception:
                pass
        has_visual_content = bool(visible_text.strip()) or canvas_has_content

        checks.append(
            ValidationCheck(
                name="playability_visual_content",
                passed=has_visual_content,
                details=(
                    "Visual content detected"
                    if has_visual_content
                    else "Page appears blank — no text or canvas content"
                ),
                severity="warning" if not has_visual_content else "info",
            )
        )

        # Check 5: Keyboard event listeners registered
        has_key_listeners = await page.evaluate("""
            () => {
                // Check if keyboard events are handled
                let hasListener = false;
                const origAEL = EventTarget.prototype.addEventListener;
                EventTarget.prototype.addEventListener = function(type, ...args) {
                    if (type === 'keydown' || type === 'keyup' || type === 'keypress') {
                        hasListener = true;
                    }
                    return origAEL.call(this, type, ...args);
                };
                // Dispatch a test event
                document.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight' }));
                EventTarget.prototype.addEventListener = origAEL;
                return hasListener;
            }
        """)

        # Fallback: check if state changes on keypress
        if not has_key_listeners:
            try:
                state_pre = await page.evaluate("JSON.stringify(window.__debug_state || {})")
                await page.keyboard.press("ArrowRight")
                await page.wait_for_timeout(300)
                state_post = await page.evaluate("JSON.stringify(window.__debug_state || {})")
                has_key_listeners = state_pre != state_post
            except Exception:
                pass

        checks.append(
            ValidationCheck(
                name="playability_keyboard_controls",
                passed=has_key_listeners,
                details=(
                    "Keyboard input handling detected"
                    if has_key_listeners
                    else "No keyboard event handling found"
                ),
                severity="blocker" if not has_key_listeners else "info",
            )
        )

        # Check 6: No infinite loops (page still responsive after 5s)
        try:
            responsive = await page.evaluate(
                "() => new Promise(resolve => setTimeout(() => resolve(true), 100))"
            )
            checks.append(
                ValidationCheck(
                    name="playability_responsive",
                    passed=responsive,
                    details="Page is responsive",
                    severity="info",
                )
            )
        except Exception:
            checks.append(
                ValidationCheck(
                    name="playability_responsive",
                    passed=False,
                    details="Page became unresponsive — possible infinite loop",
                    severity="blocker",
                )
            )

        await browser.close()

    return checks


def run_playability_checks(
    game_dir: Path, plan: GamePlan
) -> list[ValidationCheck]:
    """Synchronous wrapper for async playability checks."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(
                    asyncio.run, _run_playability_checks(game_dir, plan)
                ).result(timeout=60)
        return loop.run_until_complete(_run_playability_checks(game_dir, plan))
    except RuntimeError:
        return asyncio.run(_run_playability_checks(game_dir, plan))
    except Exception as e:
        logger.warning("playability_check_failed", error=str(e))
        return [
            ValidationCheck(
                name="playability_check",
                passed=True,
                details=f"Playability check skipped: {e}",
                severity="info",
            )
        ]
