
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
    player: { x: 400, y: 550, width: 50, height: 30, speed: 5, color: 'blue' },
    asteroids: [],
    asteroidSpawnInterval: 2000,
    lastAsteroidSpawn: 0,
    score: 0,
    lastScoreUpdate: 0,
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
    if (event.key === 'ArrowLeft') {
        gameState.player.x -= gameState.player.speed;
    }
    if (event.key === 'ArrowRight') {
        gameState.player.x += gameState.player.speed;
    }
    // Ensure player stays within bounds
    gameState.player.x = Math.max(0, Math.min(canvas.width - gameState.player.width, gameState.player.x));
}

function restartGame() {
    gameState.player.x = 400;
    gameState.asteroids = [];
    gameState.score = 0;
    gameState.isGameOver = false;
    gameState.lastAsteroidSpawn = 0;
    gameState.lastScoreUpdate = 0;
}

function update(timestamp) {
    if (!gameState.isGameOver) {
        // Spawn asteroids
        if (timestamp - gameState.lastAsteroidSpawn > gameState.asteroidSpawnInterval) {
            spawnAsteroid();
            gameState.lastAsteroidSpawn = timestamp;
        }

        // Move asteroids
        gameState.asteroids.forEach(asteroid => {
            asteroid.y += asteroid.speed;
        });

        // Remove off-screen asteroids
        gameState.asteroids = gameState.asteroids.filter(asteroid => asteroid.y < canvas.height);

        // Check for collisions
        gameState.asteroids.forEach(asteroid => {
            if (isColliding(gameState.player, asteroid)) {
                gameState.isGameOver = true;
            }
        });

        // Update score based on survival time
        if (timestamp - gameState.lastScoreUpdate > 1000) {
            gameState.score += 1;
            gameState.lastScoreUpdate = timestamp;
        }
    }
}

function draw() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Draw player
    ctx.fillStyle = gameState.player.color;
    ctx.fillRect(gameState.player.x, gameState.player.y, gameState.player.width, gameState.player.height);

    // Draw asteroids
    gameState.asteroids.forEach(asteroid => {
        ctx.fillStyle = asteroid.color;
        ctx.fillRect(asteroid.x, asteroid.y, asteroid.width, asteroid.height);
    });

    // Draw score
    ctx.font = '16px Arial';
    ctx.fillStyle = '#fff';
    ctx.fillText('Score: ' + gameState.score, 8, 20);

    // Draw game over
    if (gameState.isGameOver) {
        ctx.font = '48px Arial';
        ctx.fillStyle = '#FF0000';
        ctx.fillText('Game Over', canvas.width / 2 - 120, canvas.height / 2);
    }
}

function gameLoop(timestamp) {
    update(timestamp);
    draw();
    requestAnimationFrame(gameLoop);
}

function spawnAsteroid() {
    const x = Math.random() * (canvas.width - 40);
    const asteroid = { x: x, y: 0, width: 40, height: 40, speed: 3, color: 'gray' };
    gameState.asteroids.push(asteroid);
}

function isColliding(rect1, rect2) {
    return rect1.x < rect2.x + rect2.width &&
           rect1.x + rect1.width > rect2.x &&
           rect1.y < rect2.y + rect2.height &&
           rect1.y + rect1.height > rect2.y;
}

init();
