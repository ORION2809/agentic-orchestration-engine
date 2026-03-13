
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

const canvas = document.getElementById('gameCanvas');
const ctx = canvas.getContext('2d');

const gameState = {
    ball: { x: 400, y: 300, radius: 10, dx: 2, dy: 2 },
    score: 0,
    isGameOver: false
};

window.gameState = gameState;

function init() {
    document.addEventListener('keydown', handleKeyDown);
    requestAnimationFrame(gameLoop);
}

function handleKeyDown(event) {
    if (event.key === 'r' || event.key === 'R') {
        restartGame();
    }
}

function restartGame() {
    gameState.ball.x = 400;
    gameState.ball.y = 300;
    gameState.ball.dx = 2;
    gameState.ball.dy = 2;
    gameState.score = 0;
    gameState.isGameOver = false;
}

function update() {
    if (!gameState.isGameOver) {
        gameState.ball.x += gameState.ball.dx;
        gameState.ball.y += gameState.ball.dy;

        // Bounce off walls
        if (gameState.ball.x < gameState.ball.radius || gameState.ball.x > canvas.width - gameState.ball.radius) {
            gameState.ball.dx *= -1;
        }
        if (gameState.ball.y < gameState.ball.radius || gameState.ball.y > canvas.height - gameState.ball.radius) {
            gameState.ball.dy *= -1;
        }

        // Update score
        gameState.score += 1;

        // Game over condition
        if (gameState.ball.y > canvas.height - gameState.ball.radius) {
            gameState.isGameOver = true;
        }
    }
}

function draw() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Draw ball
    ctx.beginPath();
    ctx.arc(gameState.ball.x, gameState.ball.y, gameState.ball.radius, 0, Math.PI * 2);
    ctx.fillStyle = '#0095DD';
    ctx.fill();
    ctx.closePath();

    // Draw score
    ctx.font = '16px Arial';
    ctx.fillStyle = '#000';
    ctx.fillText('Score: ' + gameState.score, 8, 20);

    // Draw game over
    if (gameState.isGameOver) {
        ctx.font = '48px Arial';
        ctx.fillStyle = '#FF0000';
        ctx.fillText('Game Over', canvas.width / 2 - 120, canvas.height / 2);
    }
}

function gameLoop() {
    update();
    draw();
    requestAnimationFrame(gameLoop);
}

init();