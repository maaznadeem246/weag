# WEAG Green Agent - BrowserGym Evaluator for AgentBeats

A comprehensive Green Agent (evaluator) for the [AgentBeats](https://agentbeats.dev) platform that evaluates web automation agents using the BrowserGym benchmark suite with computational efficiency mandates.

## Abstract

The WEAG Green Agent evaluates Purple Agents (participants) on web-based tasks across 6 benchmark suites (MiniWoB, WebArena, VisualWebArena, WorkArena, AssistantBench, WebLINX). It provides:

- **A2A Protocol**: Agent-to-Agent communication for evaluation orchestration
- **MCP Server**: Exposes BrowserGym environment via Model Context Protocol
- **Efficiency Mandates**: Tracks computational cost (C), latency (L), and failures (F)
- **Multi-Task Support**: LLM-orchestrated evaluation of multiple tasks per session
- **Tracing**: Langfuse integration for observability

## Repository Structure

This is a **public GitHub repository** containing complete source code for competition submission.

```
green-agent/
├── src/                    # Green Agent source code
│   ├── main.py            # A2A server entry point
│   ├── mcp/               # MCP server implementation
│   ├── environment/       # BrowserGym environment management
│   ├── agent/             # Multi-task orchestration agent
│   ├── metrics/           # Efficiency tracking (C/L/F)
│   ├── assessment/        # Evaluation logic
│   ├── a2a/               # A2A protocol handlers
│   └── benchmarks/        # Benchmark profiles and tools
├── datasets/              # Local benchmark datasets (miniwob)
├── tests/                 # A2A conformance tests
├── Dockerfile             # Production Docker image
├── pyproject.toml         # Python dependencies
└── README.md              # This file
```

## Features

### Evaluation Capabilities
- **6 Benchmark Suites**: MiniWoB, WebArena, VisualWebArena, WorkArena, AssistantBench, WebLINX
- **Multi-Task Mode**: Evaluate multiple tasks in a single session (orchestrated by LLM)
- **Efficiency Tracking**: Real-time monitoring of computational cost, latency, and failures
- **Browser Control**: Headless and visible browser modes via Playwright
- **Session Management**: Automatic cleanup and resource monitoring

### Technical Stack
- **OpenAI Agents SDK**: Agent orchestration with tools, guardrails, and sessions
- **Gemini 2.5 Flash**: Cost-effective LLM ($0.001-0.05/eval) via OpenAI-compatible API
- **Langfuse**: Distributed tracing and observability
- **FastMCP**: MCP server with 4 environment tools (observe, execute_action, batch_actions, get_environment_info)
- **BrowserGym**: Web environment with 6 benchmark integrations

## Running Locally

### Prerequisites
- Python 3.11+
- uv package manager
- Environment variables configured (see `../sample.env`)

### Setup

```bash
# Install dependencies
uv sync

# Set environment variables (copy from sample.env at project root)
cp ../sample.env .env
# Edit .env with your API keys:
#   GEMINI_API_KEY=your-gemini-key
#   LANGFUSE_PUBLIC_KEY=your-langfuse-key
#   LANGFUSE_SECRET_KEY=your-langfuse-secret

# Install Playwright browsers
uv run playwright install chromium

# Download MiniWoB dataset (if not already present)
# Datasets are included in datasets/ folder
```

### Run Green Agent

```bash
# Run A2A server
uv run src/main.py --host 127.0.0.1 --port 9009

# In another terminal, test with Purple Agent
cd ../purple-agent
uv run src/main.py --host 127.0.0.1 --port 9010
```

### Run with Visible Browser (for debugging)

```bash
# Set headless=false in environment config
export HEADLESS=false
uv run src/main.py --host 127.0.0.1 --port 9009
```

## Running with Docker

### Build Image

```bash
# Build with all benchmark dependencies
docker build -t weag-green-agent .
```

### Run Container

```bash
# Run with environment file
docker run -p 9009:9009 \
  --env-file .env \
  weag-green-agent
```

## Testing

### A2A Conformance Tests

```bash
# Install test dependencies
uv sync --extra test

# Start Green Agent (in another terminal)
uv run src/main.py --host 127.0.0.1 --port 9009

# Run tests
uv run pytest --agent-url http://localhost:9009 -v
```

### Integration Tests (with Purple Agent)

```bash
# Use the kickstart script at project root
cd ..
python scripts/kickstart_assessment.py --task miniwob.click-test --visible
```

## Docker Image

The Green Agent is packaged as a Docker image and published to GitHub Container Registry via CI/CD:

```bash
# Pull latest image
docker pull ghcr.io/<username>/weag/green-agent:latest

# Pull specific version
docker pull ghcr.io/<username>/weag/green-agent:1.0.0
```

## API Endpoints

- `GET /.well-known/agent-card.json` - Agent card (A2A protocol)
- `POST /tasks` - Submit evaluation request (A2A protocol)
- `GET /health` - Health check endpoint
- `GET /metrics` - Prometheus metrics (efficiency tracking)

## Baseline Purple Agent

See `../purple-agent/` for the baseline Purple Agent implementation that demonstrates how to interact with this Green Agent.

## Environment Variables

See `../sample.env` for required environment variables:
- `GEMINI_API_KEY` - Google Gemini API key
- `LANGFUSE_PUBLIC_KEY` - Langfuse tracing public key
- `LANGFUSE_SECRET_KEY` - Langfuse tracing secret key
- `LANGFUSE_HOST` - Langfuse host (default: https://cloud.langfuse.com)

## Computational Efficiency Mandates

The Green Agent enforces three efficiency mandates:

1. **Mandate C (Cost)**: Total LLM cost per evaluation ≤ $0.05
2. **Mandate L (Latency)**: Average response time ≤ 10 seconds
3. **Mandate F (Failures)**: Action failure rate ≤ 20%

Penalties are applied for violations and included in the evaluation artifact.

## Documentation

- [A2A Migration Guide](../docs/A2A_MIGRATION.md)
- [LLM Abstraction](../docs/LLM_ABSTRACTION.md)
- [Langfuse Tracing](../docs/LANGFUSE_TRACING.md)
- [Running A2A System](../docs/RUNNING_A2A_SYSTEM.md)

## License

MIT License

## Competition Submission

This repository serves as the complete submission for the AgentBeats competition, including:
- ✅ Public GitHub repository with complete source code
- ✅ Comprehensive README with setup instructions
- ✅ Baseline Purple Agent for demonstration
- ✅ Docker image for deployment
- ✅ A2A protocol compliance
- ✅ Multi-task evaluation capability
- ✅ Computational efficiency tracking
