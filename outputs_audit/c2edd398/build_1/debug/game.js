
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

// Game state
window.gameState = {
    player: { x: 400, y: 550, width: 50, height: 10, speed: 5 },
    ball: { x: 400, y: 0, radius: 10, speed: 3 },
    score: 0,
    gameOver: false
};

// Initialize game
function init() {
    document.addEventListener('keydown', handleKeyDown);
    requestAnimationFrame(gameLoop);
}

// Handle keyboard input
function handleKeyDown(event) {
    const { player } = window.gameState;
    if (event.key === 'ArrowLeft') {
        player.x -= player.speed;
    } else if (event.key === 'ArrowRight') {
        player.x += player.speed;
    } else if (event.key === 'r' || event.key === 'R') {
        restartGame();
    }
}

// Restart game
function restartGame() {
    window.gameState.player.x = 400;
    window.gameState.ball.x = 400;
    window.gameState.ball.y = 0;
    window.gameState.score = 0;
    window.gameState.gameOver = false;
}

// Update game state
function update() {
    const { player, ball } = window.gameState;
    if (window.gameState.gameOver) return;

    // Update ball position
    ball.y += ball.speed;

    // Check for collision with player
    if (
        ball.y + ball.radius >= player.y &&
        ball.x >= player.x &&
        ball.x <= player.x + player.width
    ) {
        ball.y = 0;
        ball.x = Math.random() * (canvas.width - ball.radius * 2) + ball.radius;
        window.gameState.score += 1;
    }

    // Check for game over
    if (ball.y > canvas.height) {
        window.gameState.gameOver = true;
    }

    // Keep player within bounds
    if (player.x < 0) player.x = 0;
    if (player.x + player.width > canvas.width) player.x = canvas.width - player.width;
}

// Draw everything
function draw() {
    const { player, ball, score } = window.gameState;
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Draw player
    ctx.fillStyle = 'blue';
    ctx.fillRect(player.x, player.y, player.width, player.height);

    // Draw ball
    ctx.beginPath();
    ctx.arc(ball.x, ball.y, ball.radius, 0, Math.PI * 2);
    ctx.fillStyle = 'red';
    ctx.fill();
    ctx.closePath();

    // Draw score
    ctx.fillStyle = 'black';
    ctx.font = '20px Arial';
    ctx.fillText('Score: ' + score, 10, 20);

    // Draw game over
    if (window.gameState.gameOver) {
        ctx.fillStyle = 'black';
        ctx.font = '40px Arial';
        ctx.fillText('Game Over', canvas.width / 2 - 100, canvas.height / 2);
    }
}

// Main game loop
function gameLoop() {
    update();
    draw();
    requestAnimationFrame(gameLoop);
}

// Start the game
init();
