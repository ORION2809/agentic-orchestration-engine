"""Deterministic fallback generator — last-resort game templates when LLM fails completely."""

from __future__ import annotations

import structlog

logger = structlog.get_logger()

DETERMINISTIC_TEMPLATES: dict[str, dict[str, str]] = {
    "dodge": {
        "index.html": """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Dodge Game</title>
<link rel="stylesheet" href="style.css">
</head>
<body>
<canvas id="gameCanvas" width="480" height="640"></canvas>
<script src="game.js"></script>
</body>
</html>""",
        "style.css": """* { margin: 0; padding: 0; box-sizing: border-box; }
body { display: flex; justify-content: center; align-items: center; min-height: 100vh; background: #111; }
canvas { border: 2px solid #0ff; background: #000; }""",
        "game.js": """// Dodge Game — deterministic fallback
(function() {
    const canvas = document.getElementById('gameCanvas');
    const ctx = canvas.getContext('2d');
    const W = canvas.width, H = canvas.height;

    // Game state
    const gameState = {
        player: { x: W / 2, y: H - 60, w: 30, h: 30 },
        enemies: [],
        score: 0,
        gameOver: false,
        speed: 3,
        spawnRate: 60,
        frame: 0
    };
    window.gameState = gameState;

    const keys = {};
    document.addEventListener('keydown', e => { keys[e.key] = true; e.preventDefault(); });
    document.addEventListener('keyup', e => { keys[e.key] = false; });

    function spawnEnemy() {
        gameState.enemies.push({
            x: Math.random() * (W - 20),
            y: -20,
            w: 20, h: 20,
            vy: 2 + Math.random() * gameState.speed
        });
    }

    function update() {
        if (gameState.gameOver) return;
        const p = gameState.player;

        // Player movement
        if (keys['ArrowLeft'] || keys['a']) p.x -= 5;
        if (keys['ArrowRight'] || keys['d']) p.x += 5;
        if (keys['ArrowUp'] || keys['w']) p.y -= 5;
        if (keys['ArrowDown'] || keys['s']) p.y += 5;
        p.x = Math.max(0, Math.min(W - p.w, p.x));
        p.y = Math.max(0, Math.min(H - p.h, p.y));

        // Spawn enemies
        gameState.frame++;
        if (gameState.frame % gameState.spawnRate === 0) spawnEnemy();

        // Move enemies
        for (let i = gameState.enemies.length - 1; i >= 0; i--) {
            const e = gameState.enemies[i];
            e.y += e.vy;
            if (e.y > H) {
                gameState.enemies.splice(i, 1);
                gameState.score++;
                continue;
            }
            // Collision
            if (p.x < e.x + e.w && p.x + p.w > e.x && p.y < e.y + e.h && p.y + p.h > e.y) {
                gameState.gameOver = true;
            }
        }

        // Increase difficulty
        if (gameState.score > 0 && gameState.score % 10 === 0) {
            gameState.speed = 3 + gameState.score / 10;
            gameState.spawnRate = Math.max(20, 60 - gameState.score);
        }
    }

    function draw() {
        ctx.fillStyle = '#000';
        ctx.fillRect(0, 0, W, H);

        // Player
        ctx.fillStyle = '#0f0';
        const p = gameState.player;
        ctx.fillRect(p.x, p.y, p.w, p.h);

        // Enemies
        ctx.fillStyle = '#f00';
        gameState.enemies.forEach(e => ctx.fillRect(e.x, e.y, e.w, e.h));

        // Score
        ctx.fillStyle = '#fff';
        ctx.font = '20px monospace';
        ctx.fillText('Score: ' + gameState.score, 10, 30);

        if (gameState.gameOver) {
            ctx.fillStyle = 'rgba(0,0,0,0.7)';
            ctx.fillRect(0, 0, W, H);
            ctx.fillStyle = '#f00';
            ctx.font = '40px monospace';
            ctx.textAlign = 'center';
            ctx.fillText('GAME OVER', W/2, H/2 - 20);
            ctx.fillStyle = '#fff';
            ctx.font = '20px monospace';
            ctx.fillText('Score: ' + gameState.score, W/2, H/2 + 20);
            ctx.fillText('Press R to restart', W/2, H/2 + 50);
            ctx.textAlign = 'left';
        }
    }

    document.addEventListener('keydown', e => {
        if (e.key === 'r' || e.key === 'R') {
            if (gameState.gameOver) {
                gameState.player.x = W / 2; gameState.player.y = H - 60;
                gameState.enemies.length = 0;
                gameState.score = 0; gameState.gameOver = false;
                gameState.speed = 3; gameState.spawnRate = 60; gameState.frame = 0;
            }
        }
    });

    function loop() {
        update();
        draw();
        requestAnimationFrame(loop);
    }
    loop();
})();"""
    },

    "default": {
        "index.html": """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Simple Game</title>
<link rel="stylesheet" href="style.css">
</head>
<body>
<canvas id="gameCanvas" width="480" height="480"></canvas>
<script src="game.js"></script>
</body>
</html>""",
        "style.css": """* { margin: 0; padding: 0; box-sizing: border-box; }
body { display: flex; justify-content: center; align-items: center; min-height: 100vh; background: #222; }
canvas { border: 2px solid #fff; background: #000; }""",
        "game.js": """// Simple collector game — deterministic fallback
(function() {
    const canvas = document.getElementById('gameCanvas');
    const ctx = canvas.getContext('2d');
    const W = canvas.width, H = canvas.height;

    const gameState = {
        player: { x: W/2, y: H/2, w: 20, h: 20 },
        items: [],
        score: 0,
        gameOver: false,
        time: 60,
        frame: 0
    };
    window.gameState = gameState;

    const keys = {};
    document.addEventListener('keydown', e => { keys[e.key] = true; e.preventDefault(); });
    document.addEventListener('keyup', e => { keys[e.key] = false; });

    function spawnItem() {
        gameState.items.push({
            x: 20 + Math.random() * (W - 40),
            y: 20 + Math.random() * (H - 40),
            w: 15, h: 15
        });
    }
    for (let i = 0; i < 5; i++) spawnItem();

    let lastSecond = Date.now();

    function update() {
        if (gameState.gameOver) return;

        const p = gameState.player;
        if (keys['ArrowLeft'] || keys['a']) p.x -= 4;
        if (keys['ArrowRight'] || keys['d']) p.x += 4;
        if (keys['ArrowUp'] || keys['w']) p.y -= 4;
        if (keys['ArrowDown'] || keys['s']) p.y += 4;
        p.x = Math.max(0, Math.min(W - p.w, p.x));
        p.y = Math.max(0, Math.min(H - p.h, p.y));

        // Collect items
        for (let i = gameState.items.length - 1; i >= 0; i--) {
            const it = gameState.items[i];
            if (p.x < it.x + it.w && p.x + p.w > it.x && p.y < it.y + it.h && p.y + p.h > it.y) {
                gameState.items.splice(i, 1);
                gameState.score++;
                spawnItem();
            }
        }

        // Timer
        if (Date.now() - lastSecond >= 1000) {
            gameState.time--;
            lastSecond = Date.now();
            if (gameState.time <= 0) gameState.gameOver = true;
        }
    }

    function draw() {
        ctx.fillStyle = '#000';
        ctx.fillRect(0, 0, W, H);

        ctx.fillStyle = '#0f0';
        const p = gameState.player;
        ctx.fillRect(p.x, p.y, p.w, p.h);

        ctx.fillStyle = '#ff0';
        gameState.items.forEach(it => ctx.fillRect(it.x, it.y, it.w, it.h));

        ctx.fillStyle = '#fff';
        ctx.font = '18px monospace';
        ctx.fillText('Score: ' + gameState.score + '  Time: ' + gameState.time, 10, 25);

        if (gameState.gameOver) {
            ctx.fillStyle = 'rgba(0,0,0,0.7)';
            ctx.fillRect(0, 0, W, H);
            ctx.fillStyle = '#ff0';
            ctx.font = '36px monospace';
            ctx.textAlign = 'center';
            ctx.fillText('TIME UP!', W/2, H/2 - 20);
            ctx.fillStyle = '#fff';
            ctx.font = '20px monospace';
            ctx.fillText('Final Score: ' + gameState.score, W/2, H/2 + 20);
            ctx.fillText('Press R to restart', W/2, H/2 + 50);
            ctx.textAlign = 'left';
        }
    }

    document.addEventListener('keydown', e => {
        if ((e.key === 'r' || e.key === 'R') && gameState.gameOver) {
            gameState.player.x = W/2; gameState.player.y = H/2;
            gameState.items.length = 0;
            for (let i = 0; i < 5; i++) spawnItem();
            gameState.score = 0; gameState.time = 60; gameState.gameOver = false;
            lastSecond = Date.now();
        }
    });

    function loop() { update(); draw(); requestAnimationFrame(loop); }
    loop();
})();"""
    },
}


def generate_fallback(idea: str = "") -> dict[str, str]:
    """Generate a deterministic fallback game when LLM generation fails.

    Selects the best template based on keywords in the idea string.

    Args:
        idea: Original game idea string for template selection.

    Returns:
        Dictionary of filename → source content.
    """
    idea_lower = idea.lower()

    # Template selection heuristics
    if any(word in idea_lower for word in ["dodge", "avoid", "enemy", "enemies", "bullet"]):
        template_name = "dodge"
    else:
        template_name = "default"

    logger.info(
        "fallback_generated",
        template=template_name,
        idea_snippet=idea[:80] if idea else "(empty)",
    )

    return dict(DETERMINISTIC_TEMPLATES[template_name])
