const canvas = document.getElementById('gameCanvas');
const ctx = canvas.getContext('2d');

const gameState = {
    player: { x: canvas.width / 2 - 25, y: canvas.height - 50, width: 50, height: 30, speed: 5, color: 'blue' },
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
    gameState.player.x = canvas.width / 2 - 25;
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
            // Increase difficulty by decreasing spawn interval
            gameState.asteroidSpawnInterval = Math.max(500, gameState.asteroidSpawnInterval * 0.98);
        }

        // Move asteroids
        gameState.asteroids.forEach(asteroid => {
            asteroid.y += asteroid.speed;
            // Increase asteroid speed over time
            asteroid.speed += 0.01;
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
