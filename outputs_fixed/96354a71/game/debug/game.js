
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

// Game state object
window.gameState = {
    player: { x: 375, y: 500, width: 50, height: 30, dx: 0, dy: 0, speed: 5 },
    obstacles: [],
    stars: [],
    score: 0,
    gameOver: false
};

const gravity = 0.5;
const jumpStrength = -10;
const obstacleSpeed = 3;
const starSpawnCounterMax = 200;
let obstacleSpawnCounter = 0;
let starSpawnCounter = 0;

function init() {
    document.addEventListener('keydown', handleKeyDown);
    document.addEventListener('keyup', handleKeyUp);
    requestAnimationFrame(gameLoop);
}

function handleKeyDown(event) {
    if (event.code === 'ArrowLeft') {
        window.gameState.player.dx = -window.gameState.player.speed;
    }
    if (event.code === 'ArrowRight') {
        window.gameState.player.dx = window.gameState.player.speed;
    }
    if (event.code === 'Space' && window.gameState.player.y >= 500) {
        window.gameState.player.dy = jumpStrength;
    }
    if (event.code === 'KeyR' && window.gameState.gameOver) {
        restartGame();
    }
}

function handleKeyUp(event) {
    if (event.code === 'ArrowLeft' || event.code === 'ArrowRight') {
        window.gameState.player.dx = 0;
    }
}

function update() {
    if (window.gameState.gameOver) return;

    // Update player
    window.gameState.player.dy += gravity;
    window.gameState.player.x += window.gameState.player.dx;
    window.gameState.player.y += window.gameState.player.dy;
    if (window.gameState.player.y > 500) {
        window.gameState.player.y = 500;
        window.gameState.player.dy = 0;
    }

    // Keep player within bounds
    if (window.gameState.player.x < 0) {
        window.gameState.player.x = 0;
    }
    if (window.gameState.player.x + window.gameState.player.width > canvas.width) {
        window.gameState.player.x = canvas.width - window.gameState.player.width;
    }

    // Spawn obstacles
    obstacleSpawnCounter++;
    if (obstacleSpawnCounter > 100) {
        spawnObstacle();
        obstacleSpawnCounter = 0;
    }

    // Update obstacles
    window.gameState.obstacles.forEach(obstacle => {
        obstacle.y += obstacleSpeed;
    });

    // Remove off-screen obstacles
    window.gameState.obstacles = window.gameState.obstacles.filter(obstacle => obstacle.y < canvas.height);

    // Spawn stars
    starSpawnCounter++;
    if (starSpawnCounter > starSpawnCounterMax) {
        spawnStar();
        starSpawnCounter = 0;
    }

    // Update stars
    window.gameState.stars.forEach(star => {
        star.y += obstacleSpeed;
    });

    // Remove off-screen stars
    window.gameState.stars = window.gameState.stars.filter(star => star.y < canvas.height);

    // Check collisions with obstacles
    window.gameState.obstacles.forEach(obstacle => {
        if (isColliding(window.gameState.player, obstacle)) {
            window.gameState.gameOver = true;
        }
    });

    // Check collisions with stars
    window.gameState.stars.forEach((star, index) => {
        if (isColliding(window.gameState.player, star)) {
            window.gameState.stars.splice(index, 1);
            window.gameState.score += 10; // Increment score by 10 for each star collected
        }
    });

    // Update score
    window.gameState.score++;
}

function draw() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Draw player
    ctx.fillStyle = 'blue';
    ctx.fillRect(window.gameState.player.x, window.gameState.player.y, window.gameState.player.width, window.gameState.player.height);

    // Draw obstacles
    ctx.fillStyle = 'gray';
    window.gameState.obstacles.forEach(obstacle => {
        ctx.fillRect(obstacle.x, obstacle.y, obstacle.width, obstacle.height);
    });

    // Draw stars
    ctx.fillStyle = 'yellow';
    window.gameState.stars.forEach(star => {
        ctx.fillRect(star.x, star.y, star.width, star.height);
    });

    // Draw score
    ctx.fillStyle = 'white';
    ctx.font = '20px Arial';
    ctx.fillText('Score: ' + window.gameState.score, 10, 20);

    // Draw game over
    if (window.gameState.gameOver) {
        ctx.fillStyle = 'white';
        ctx.font = '40px Arial';
        ctx.fillText('Game Over', canvas.width / 2 - 100, canvas.height / 2);
    }
}

function gameLoop() {
    update();
    draw();
    requestAnimationFrame(gameLoop);
}

function isColliding(rect1, rect2) {
    return rect1.x < rect2.x + rect2.width &&
           rect1.x + rect1.width > rect2.x &&
           rect1.y < rect2.y + rect2.height &&
           rect1.y + rect1.height > rect2.y;
}

function spawnObstacle() {
    const width = Math.random() * 40 + 20;
    const x = Math.random() * (canvas.width - width);
    window.gameState.obstacles.push({
        x: x,
        y: 0,
        width: width,
        height: 40
    });
}

function spawnStar() {
    const x = Math.random() * (canvas.width - 20);
    window.gameState.stars.push({
        x: x,
        y: 0,
        width: 20,
        height: 20
    });
}

function restartGame() {
    window.gameState.player.x = 375;
    window.gameState.player.y = 500;
    window.gameState.player.dx = 0;
    window.gameState.player.dy = 0;
    window.gameState.obstacles = [];
    window.gameState.stars = [];
    window.gameState.score = 0;
    window.gameState.gameOver = false;
}

init();
