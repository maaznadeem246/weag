FROM ghcr.io/astral-sh/uv:python3.11-bookworm

RUN adduser agent
USER agent
WORKDIR /home/agent

# Copy dependency files first for better caching
COPY --chown=agent:agent pyproject.toml uv.lock README.md ./

# Copy source
COPY --chown=agent:agent src src

# Install dependencies
RUN --mount=type=cache,target=/home/agent/.cache/uv,uid=1000 \
    uv sync --locked

# Create logs directory with proper permissions
RUN mkdir -p /home/agent/logs && chown -R agent:agent /home/agent/logs

# Default configuration (can be overridden at runtime)
# For standalone deployment, set this environment variable:
# - AGENT_CARD_URL: External URL for agent card (e.g., https://your-domain.com/)
ENV AGENT_CARD_URL=""

# LLM Provider settings (from scenario-docker.toml)
# API keys should be passed at runtime, not baked into image
ENV PURPLE_LLM_PROVIDER=openai
ENV PURPLE_OPENAI_MODEL=gpt-4o
# ENV PURPLE_OPENAI_API_KEY=  # Pass at runtime

# Use module execution (-m) to avoid import path conflicts
ENTRYPOINT ["uv", "run", "python", "-m", "src.main"]
CMD ["--host", "0.0.0.0", "--port", "9010"]
EXPOSE 9010
