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