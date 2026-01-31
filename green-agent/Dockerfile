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
    git \
    && rm -rf /var/lib/apt/lists/*

RUN adduser agent
USER agent
WORKDIR /home/agent

# Copy dependency files first for better caching
COPY --chown=agent:agent pyproject.toml uv.lock README.md ./

# Copy source
COPY --chown=agent:agent src src

# Install dependencies with docker extras for all benchmarks
# Use docker-minimal for faster builds with only miniwob + assistantbench
# Use docker for full benchmark support (slower build)
ARG DOCKER_EXTRAS=docker-minimal
RUN --mount=type=cache,target=/home/agent/.cache/uv,uid=1000 \
    uv sync --locked --extra ${DOCKER_EXTRAS}

# Install Playwright browsers
RUN uv run playwright install chromium

# Download benchmark datasets at build time
RUN mkdir -p /home/agent/datasets/miniwob && \
    TEMP_DIR="/tmp/miniwob_clone" && \
    git clone --depth 1 --filter=blob:none --sparse \
        https://github.com/Farama-Foundation/miniwob-plusplus.git "$TEMP_DIR" && \
    cd "$TEMP_DIR" && git sparse-checkout set miniwob/html && cd /home/agent && \
    cp -r "$TEMP_DIR/miniwob/html" /home/agent/datasets/miniwob/ && \
    rm -rf "$TEMP_DIR"

RUN uv run python -c "\
from huggingface_hub import hf_hub_download; \
hf_hub_download( \
    repo_id='McGill-NLP/weblinx-browsergym', \
    repo_type='dataset', \
    filename='metadata.json', \
    local_dir='datasets/weblinx' \
)"

# WebLINX configuration - only register test_iid split to keep import fast
ENV BROWSERGYM_WEBLINX_CACHE_DIR=/home/agent/datasets/weblinx
ENV BROWSERGYM_WEBLINX_REGISTER_TRAIN=false
ENV BROWSERGYM_WEBLINX_REGISTER_VALID=false
ENV BROWSERGYM_WEBLINX_REGISTER_TEST=true
ENV BROWSERGYM_WEBLINX_REGISTER_TEST_OOD=false

# Set environment for headless browser
ENV PLAYWRIGHT_BROWSERS_PATH=/home/agent/.cache/ms-playwright
ENV DISPLAY=:99

# Default configuration (can be overridden at runtime)
# For standalone deployment, set these environment variables:
# - AGENT_CARD_URL: External URL for agent card (e.g., https://your-domain.com/)
# - MCP_EXTERNAL_URL: External MCP URL for Docker/remote networking (e.g., http://green-agent:8001/mcp)
ENV AGENT_CARD_URL=""
ENV MCP_EXTERNAL_URL=""

# Entrypoint starts the agent
ENTRYPOINT ["uv", "run", "python", "-m", "src.main"]
CMD ["--host", "0.0.0.0", "--port", "9009"]
EXPOSE 9009
EXPOSE 8001
