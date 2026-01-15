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

# Set Playwright cache path BEFORE installation
ENV PLAYWRIGHT_BROWSERS_PATH=/home/agent/.cache/ms-playwright

# Install Playwright browsers (NO cache mount - browsers must persist in image)
RUN uv run playwright install chromium
ENV DISPLAY=:99

# =============================================================================
# Default configuration from scenario-docker.toml
# All can be overridden at runtime via docker-compose or -e flags
# =============================================================================

# Agent card and MCP URLs (for Docker networking)
ENV AGENT_CARD_URL=""
ENV MCP_EXTERNAL_URL=""

# Assessment settings (from [config] section)
ENV BROWSER_HEADLESS=true
ENV MAX_STEPS=10
ENV MAX_TASKS_PER_BENCHMARK=2
ENV TIMEOUT_SECONDS=120

# LLM Provider settings (from [green_agent].env)
# API keys should be passed at runtime, not baked into image
# ENV GREEN_LLM_PROVIDER=openrouter
# ENV GREEN_OPENAI_MODEL=google/gemini-2.5-flash
# ENV GREEN_OPENAI_API_KEY=  # Pass at runtime
# ENV GREEN_GEMINI_API_KEY=  # Pass at runtime
# ENV GREEN_OPENROUTER_API_KEY=  # Pass at runtime

# Langfuse tracing (optional - pass at runtime if needed)
# ENV LANGFUSE_PUBLIC_KEY=
# ENV LANGFUSE_SECRET_KEY=

# Use module execution (-m) to avoid import path conflicts
# Running as a module ensures the installed a2a-sdk package takes precedence
# over the local src/a2a/ directory
ENTRYPOINT ["uv", "run", "python", "-m", "src.main"]
CMD ["--host", "0.0.0.0", "--port", "9009"]
EXPOSE 9009
EXPOSE 8001
