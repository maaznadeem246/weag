FROM ghcr.io/astral-sh/uv:python3.11-bookworm

# Install system dependencies for Playwright and BrowserGym
USER root
RUN apt-get update && apt-get install -y \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxkbcommon0 \
    libatspi2.0-0 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

RUN adduser agent
USER agent
WORKDIR /home/agent

# Copy dependency files first for better caching
COPY --chown=agent:agent pyproject.toml uv.lock README.md ./

# Copy source and datasets
COPY --chown=agent:agent src src
COPY --chown=agent:agent datasets datasets

# Install dependencies with docker extras for all benchmarks
# Use docker-minimal for faster builds with only miniwob + assistantbench
# Use docker for full benchmark support (slower build)
ARG DOCKER_EXTRAS=docker-minimal
RUN --mount=type=cache,target=/home/agent/.cache/uv,uid=1000 \
    uv sync --locked --extra ${DOCKER_EXTRAS}

# Set Playwright cache path BEFORE installation for proper caching
ENV PLAYWRIGHT_BROWSERS_PATH=/home/agent/.cache/ms-playwright

# Install Playwright browsers with both cache mounts (uv cache + playwright cache)
RUN --mount=type=cache,target=/home/agent/.cache/uv,uid=1000 \
    --mount=type=cache,target=/home/agent/.cache/ms-playwright,uid=1000 \
    uv run playwright install chromium
ENV DISPLAY=:99

# Default configuration (can be overridden at runtime)
# For standalone deployment, set these environment variables:
# - AGENT_CARD_URL: External URL for agent card (e.g., https://your-domain.com/)
# - MCP_EXTERNAL_URL: External MCP URL for Docker/remote networking (e.g., http://green-agent:8001/mcp)
ENV AGENT_CARD_URL="" 
ENV MCP_EXTERNAL_URL=""

# Use module execution (-m) to avoid import path conflicts
# Running as a module ensures the installed a2a-sdk package takes precedence
# over the local src/a2a/ directory
ENTRYPOINT ["uv", "run", "python", "-m", "src.main"]
CMD ["--host", "0.0.0.0", "--port", "9009"]
EXPOSE 9009
EXPOSE 8001
