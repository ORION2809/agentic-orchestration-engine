# ---- Stage 1: Node.js for esprima AST analysis ----
FROM node:20-slim AS node-base
RUN npm install -g esprima

# ---- Stage 2: Python application ----
FROM python:3.11-slim

# Copy Node.js binary and global modules from stage 1
COPY --from=node-base /usr/local/bin/node /usr/local/bin/node
COPY --from=node-base /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/.bin/esparse /usr/local/bin/esparse 2>/dev/null || true

# Make globally-installed npm modules findable by require()
ENV NODE_PATH=/usr/local/lib/node_modules

# Install system dependencies for Playwright
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Set workdir
WORKDIR /app

# Copy requirements first for Docker layer caching
COPY requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright Chromium browser (for behavioral testing)
RUN playwright install chromium --with-deps

# Copy application code (prompts, agents, models, etc.)
COPY app/ ./app/
COPY .env.example ./.env.example

# Create output directory
RUN mkdir -p outputs

# Default to batch mode in Docker (no TTY)
ENV BATCH_MODE=true
ENV OUTPUT_DIR=/app/outputs

# Health check — verify Python and MCP server can import
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "from app.mcp_server import mcp; print('ok')" || exit 1

# Default entrypoint (CLI mode)
# Override with: --entrypoint python ... -m app.mcp_server  (for MCP mode)
ENTRYPOINT ["python", "-m", "app.main"]
CMD ["--help"]
