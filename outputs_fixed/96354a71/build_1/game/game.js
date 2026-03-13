const canvas = document.getElementById('gameCanvas');
const ctx = canvas.getContext('2d');

// Game state object
window.gameState = {
    player: { x: 50, y: 300, width: 50, height: 50, dy: 0 },
    obstacles: [],
    score: 0,
    gameOver: false
};

const gravity = 0.5;
const jumpStrength = -10;
const obstacleSpeed = 5;
let obstacleSpawnCounter = 0;

function init() {
    document.addEventListener('keydown', handleKeyDown);
    requestAnimationFrame(gameLoop);
}

function handleKeyDown(event) {
    if (event.code === 'Space' && window.gameState.player.y >= 300) {
        window.gameState.player.dy = jumpStrength;
    }
    if (event.code === 'KeyR' && window.gameState.gameOver) {
        restartGame();
    }
}

function update() {
    if (window.gameState.gameOver) return;

    // Update player
    window.gameState.player.dy += gravity;
    window.gameState.player.y += window.gameState.player.dy;
    if (window.gameState.player.y > 300) {
        window.gameState.player.y = 300;
        window.gameState.player.dy = 0;
    }

    // Spawn obstacles
    obstacleSpawnCounter++;
    if (obstacleSpawnCounter > 100) {
        spawnObstacle();
        obstacleSpawnCounter = 0;
    }

    // Update obstacles
    window.gameState.obstacles.forEach(obstacle => {
        obstacle.x -= obstacleSpeed;
    });

    // Remove off-screen obstacles
    window.gameState.obstacles = window.gameState.obstacles.filter(obstacle => obstacle.x + obstacle.width > 0);

    // Check collisions
    window.gameState.obstacles.forEach(obstacle => {
        if (isColliding(window.gameState.player, obstacle)) {
            window.gameState.gameOver = true;
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
    ctx.fillStyle = 'red';
    window.gameState.obstacles.forEach(obstacle => {
        ctx.fillRect(obstacle.x, obstacle.y, obstacle.width, obstacle.height);
    });

    // Draw score
    ctx.fillStyle = 'black';
    ctx.font = '20px Arial';
    ctx.fillText('Score: ' + window.gameState.score, 10, 20);

    // Draw game over
    if (window.gameState.gameOver) {
        ctx.fillStyle = 'black';
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
    const height = Math.random() * 100 + 20;
    window.gameState.obstacles.push({
        x: canvas.width,
        y: 400 - height,
        width: 20,
        height: height
    });
}

function restartGame() {
    window.gameState.player.y = 300;
    window.gameState.player.dy = 0;
    window.gameState.obstacles = [];
    window.gameState.score = 0;
    window.gameState.gameOver = false;
}

init();