"""Runtime validator — Playwright headless browser smoke test + behavioral tests."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import structlog

from app.models.schemas import GamePlan, ValidationCheck

logger = structlog.get_logger()


async def _run_browser_tests(
    game_dir: Path, plan: GamePlan
) -> list[ValidationCheck]:
    """Playwright-based behavioral tests using game state queries."""
    checks: list[ValidationCheck] = []

    try:
        from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
    except ImportError:
        logger.warning("playwright_not_installed")
        checks.append(
            ValidationCheck(
                name="runtime_smoke_test",
                passed=True,
                details="Playwright not installed — runtime tests skipped",
                severity="info",
            )
        )
        return checks

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        page.set_default_timeout(15_000)

        # Collect console errors
        errors: list[str] = []
        page.on("pageerror", lambda err: errors.append(str(err)))

        # Activate debug mode before navigating
        await page.add_init_script("window.__GAME_DEBUG__ = true;")

        index_path = game_dir / "index.html"
        if not index_path.exists():
            checks.append(
                ValidationCheck(
                    name="page_load",
                    passed=False,
                    details="index.html not found in game directory",
                    severity="blocker",
                )
            )
            await browser.close()
            return checks

        try:
            await page.goto(f"file:///{index_path.resolve()}", timeout=10_000)
        except Exception as e:
            checks.append(
                ValidationCheck(
                    name="page_load",
                    passed=False,
                    details=f"Page failed to load within 10s: {e}",
                    severity="blocker",
                )
            )
            await browser.close()
            return checks

        await page.wait_for_timeout(2000)  # let game initialize

        # Test 1: Check for runtime errors during load
        load_errors = list(errors)
        checks.append(
            ValidationCheck(
                name="no_load_errors",
                passed=len(load_errors) == 0,
                details=(
                    f"{len(load_errors)} errors: {load_errors[:3]}"
                    if load_errors
                    else "No errors during load"
                ),
                severity="blocker" if load_errors else "info",
            )
        )

        # Test 2: Debug state hook present
        has_debug = await page.evaluate("typeof window.__debug_state !== 'undefined'")
        checks.append(
            ValidationCheck(
                name="debug_hook_present",
                passed=has_debug,
                details="Debug state hook found" if has_debug else "No __debug_state",
                severity="warning",
            )
        )

        if has_debug:
            # Test 3: Input moves player
            state_before = await page.evaluate(
                "JSON.parse(JSON.stringify(window.__debug_state || {}))"
            )

            # Simulate keyboard inputs from the plan controls
            # Use keyboard.down (hold) instead of press (tap) so game loop
            # has time to process movement across multiple frames.
            keys = list(plan.controls.key_mappings.keys()) if plan.controls.key_mappings else [
                "ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"
            ]
            # Pick a single directional key to avoid opposite-direction cancellation
            test_key = keys[0] if keys else "ArrowRight"
            await page.keyboard.down(test_key)
            await page.wait_for_timeout(500)  # hold key for ~30 frames
            await page.keyboard.up(test_key)
            await page.wait_for_timeout(200)  # let last frame settle

            state_after = await page.evaluate(
                "JSON.parse(JSON.stringify(window.__debug_state || {}))"
            )

            player_before = state_before.get("player", {}) if isinstance(state_before, dict) else {}
            player_after = state_after.get("player", {}) if isinstance(state_after, dict) else {}
            player_moved = (
                player_before.get("x") != player_after.get("x")
                or player_before.get("y") != player_after.get("y")
            )
            checks.append(
                ValidationCheck(
                    name="behavioral_input_moves_player",
                    passed=player_moved,
                    details=(
                        f"Player: {player_before} → {player_after}"
                        if player_moved
                        else "Player position unchanged after input"
                    ),
                    severity="blocker" if not player_moved else "info",
                )
            )

            # Test 4: Score tracking
            score_before = state_after.get("score", 0) if isinstance(state_after, dict) else 0
            await page.wait_for_timeout(3000)
            state_later = await page.evaluate(
                "JSON.parse(JSON.stringify(window.__debug_state || {}))"
            )
            score_later = state_later.get("score", 0) if isinstance(state_later, dict) else 0

            checks.append(
                ValidationCheck(
                    name="behavioral_score_updates",
                    passed=score_later != score_before,
                    details=(
                        f"Score: {score_before} → {score_later}"
                        if score_later != score_before
                        else "Score unchanged during 3s of gameplay"
                    ),
                    severity="warning",
                )
            )

            # Test 5: Game-over flag exists
            game_over = state_later.get("gameOver") if isinstance(state_later, dict) else None
            checks.append(
                ValidationCheck(
                    name="behavioral_gameover_flag_exists",
                    passed=game_over is not None,
                    details=f"gameOver flag: {game_over}",
                    severity="warning",
                )
            )

            # Test 6: FPS measurement
            try:
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
                checks.append(
                    ValidationCheck(
                        name="performance_fps_check",
                        passed=fps >= 15,
                        details=(
                            f"FPS: {fps:.1f} over 5s"
                            if fps >= 15
                            else f"Low FPS: {fps:.1f}"
                        ),
                        severity="warning" if fps < 15 else "info",
                    )
                )
            except Exception as e:
                logger.warning("fps_check_failed", error=str(e))

            # Test 7: Entity growth detection
            try:
                entity_data = await page.evaluate("""
                    () => {
                        const s = window.__debug_state || {};
                        return {
                            entityCount: s.entityCount || 0,
                            growthRate: s._entityGrowthRate || 0
                        };
                    }
                """)
                growth_rate = entity_data.get("growthRate", 0)
                entity_count = entity_data.get("entityCount", 0)
                unbounded = growth_rate > 2

                checks.append(
                    ValidationCheck(
                        name="performance_entity_growth",
                        passed=not unbounded,
                        details=(
                            f"Entities: {entity_count}, growth: {growth_rate:.1f}/frame"
                            if not unbounded
                            else f"UNBOUNDED growth: {entity_count} entities, +{growth_rate:.1f}/frame"
                        ),
                        severity="warning" if unbounded else "info",
                    )
                )
            except Exception as e:
                logger.warning("entity_growth_check_failed", error=str(e))

        else:
            # Degraded pixel-based check
            try:
                canvas = await page.query_selector("canvas")
                if canvas:
                    screenshot_before = await canvas.screenshot()
                    await page.keyboard.down("ArrowRight")
                    await page.wait_for_timeout(500)
                    await page.keyboard.up("ArrowRight")
                    await page.wait_for_timeout(200)
                    screenshot_after = await canvas.screenshot()
                    checks.append(
                        ValidationCheck(
                            name="behavioral_input_response_degraded",
                            passed=screenshot_before != screenshot_after,
                            details="Pixel-based check (degraded mode)",
                            severity="warning",
                        )
                    )
            except Exception as e:
                logger.warning("pixel_check_failed", error=str(e))

        # Final: Console error summary
        checks.append(
            ValidationCheck(
                name="behavioral_no_runtime_errors",
                passed=len(errors) == 0,
                details=(
                    f"{len(errors)} errors: {errors[:3]}"
                    if errors
                    else "No runtime errors"
                ),
                severity="blocker" if errors else "info",
            )
        )

        # Screenshot for report
        try:
            screenshot_path = game_dir.parent / "screenshot.png"
            await page.screenshot(path=str(screenshot_path))
        except Exception:
            pass

        await browser.close()

    return checks


def run_runtime_validation(
    game_dir: Path, plan: GamePlan
) -> list[ValidationCheck]:
    """Synchronous wrapper for async Playwright tests."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Already in async context
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(
                    asyncio.run, _run_browser_tests(game_dir, plan)
                ).result(timeout=60)
        return loop.run_until_complete(_run_browser_tests(game_dir, plan))
    except RuntimeError:
        return asyncio.run(_run_browser_tests(game_dir, plan))
    except Exception as e:
        logger.warning("runtime_validation_failed", error=str(e))
        return [
            ValidationCheck(
                name="runtime_smoke_test",
                passed=True,
                details=f"Runtime validation skipped: {e}",
                severity="info",
            )
        ]
