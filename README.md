# WEAG - Web Environment Agent Green

> **Production-grade A2A evaluation system for web automation benchmarks**

**🔗 AgentBeats Links:**
- **Green Agent**: https://agentbeats.dev/maaznadeem246/weag-green
- **Purple Agent**: https://agentbeats.dev/maaznadeem246/weag-purple
- **Project Demo (Loom)**: https://www.loom.com/share/eba41cb621b24b0aa925b6a8f1ebb054

---

## Overview

WEAG (Web Environment Agent Green) is a complete Agent-to-Agent (A2A) assessment platform built for the [AgentBeats](https://agentbeats.ai) competition. It provides:

- **Green Agent**: Orchestrator that manages task evaluation, spawns MCP servers, and tracks metrics
- **Purple Agent**: Reference implementation that executes web automation tasks via browser control
- **BrowserGym Integration**: Supports multiple web automation benchmarks with standardized APIs
- **A2A Protocol**: Agent-to-agent communication using the official A2A SDK
- **MCP Server**: Model Context Protocol server exposing browser control action tools
- **Production Ready**: Docker containers, comprehensive logging, error handling, and result artifacts


---

## Supported Benchmarks

| Benchmark | Tasks | Description | Status |
|-----------|-------|-------------|--------|
| **MiniWoB** | 125+ | Simple web tasks (clicks, forms, navigation) | ✅ Ready |
| **AssistantBench** | 214 | Real-world assistant tasks (search, research) | ✅ Ready |
| **WebLinx** | 1,200+ | Real-world web navigation from human demonstrations | ✅ Ready |
| **WebArena** | 812 | E-commerce and CMS tasks | 🚧 Planned |
| **VisualWebArena** | 910 | Vision-based web navigation | 🚧 Planned |
| **WorkArena** | 33 | Office automation tasks | 🚧 Planned |

---

## Quick Start

### Prerequisites

- **Python 3.11+** (for local runs)
- **Docker Desktop** (for containerized runs)
- **API Keys**: OpenAI or Gemini (set in `.env` file)

### Setup

```bash
# Clone repository
git clone https://github.com/maaznadeem246/weag.git
cd weag

# Create environment file
cp sample.env .env

# Add your API keys to .env
# OPENAI_API_KEY=your_openai_key
# GEMINI_API_KEY=your_gemini_key
```

---

## Running Without Docker (Local Development)

### 0. Download Local Datasets

Run the dataset setup script once before local runs:

```powershell
python scripts/setup_local_datasets.py
```

### 1. Install UV (Python Package Manager)

This project uses [uv](https://docs.astral.sh/uv/) for fast, reliable dependency management.

```bash
# Windows PowerShell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# Linux/macOS
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Verify installation:
```bash
uv --version
```

### 1. Build and Start Containers

```powershell
# Build Docker images
.\docker-test.ps1 -Build

# Start containers in background
.\docker-test.ps1 -Start
```

### 2. Run Assessment from Host Machine

```powershell
# Activate virtual environment
.\green-agent\.venv\Scripts\Activate.ps1

# Run assessment (connects to Docker containers)
python kickstart_assessment.py --config scenarios/browsergym/scenario-local.toml

# Or run single task
python kickstart_assessment.py --task miniwob.click-test
```

**Important:** Install Green Agent packages (`uv sync` in green-agent) and activate its venv. When running commands from the repo root, prefer using the Green Agent Python directly:

```powershell
.\green-agent\.venv\Scripts\python.exe <command>
```

**Root-level examples (recommended):**

```powershell
.\green-agent\.venv\Scripts\python.exe kickstart_assessment.py --config scenarios/browsergym/scenario-local.toml
.\green-agent\.venv\Scripts\python.exe kickstart_assessment.py --task weblinx.scicrdo.1 --output results.json
```

**Local (no Docker) — run with Python from the green-agent venv:**

```powershell
.\green-agent\.venv\Scripts\python.exe kickstart_assessment.py --config scenarios/browsergym/scenario-local.toml --visible
```

**Task-specific run (no Docker):**

```powershell
.\green-agent\.venv\Scripts\python.exe kickstart_assessment.py --task weblinx.scicrdo.1 --output results.json
```

> The same commands also work after Docker build/start (they will connect to the running containers).

### 3. View Logs

```powershell
# Follow container logs
.\docker-test.ps1 -Logs

# Or view specific container
docker logs -f weag-green-agent
docker logs -f weag-purple-agent
```

### 4. View Results

Results are saved to:
- `output/results.json` - Detailed task results
- `results/agentbeats-results-*.json` - Timestamped assessment artifacts
- Docker logs - Complete execution trace

### 5. Cleanup

```powershell
# Stop containers
.\docker-test.ps1 -Stop

# Or clean everything (containers, networks, volumes)
.\docker-test.ps1 -Clean
```

### 6. Rebuild After Code Changes

```powershell
# Restart with rebuild
.\docker-test.ps1 -Restart

# Or manual rebuild
.\docker-test.ps1 -Stop
.\docker-test.ps1 -Build
.\docker-test.ps1 -Start
```

---

## Configuration

### Environment Variables (.env file)

**All API keys and secrets must be defined in `.env` file:**

```bash
# LLM API Keys (required - choose one)
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=...
OPENROUTER_API_KEY=sk-or-v1-...

# Observability (optional)
LANGFUSE_PUBLIC_KEY=pk-...
LANGFUSE_SECRET_KEY=sk-...
LANGFUSE_HOST=https://cloud.langfuse.com
```

These keys are automatically loaded and used by the scenario TOML configuration.

### Scenario Configuration (TOML files)

**All other configurations come from TOML files** (e.g., `scenarios/browsergym/scenario-local.toml`):

```toml
# Assessment settings
[assessment]
timeout_seconds = 120          # Per-task timeout
max_steps = 10                 # Max actions per task
max_tasks_per_benchmark = 2    # Tasks to run per benchmark
headless = true                # Browser visibility

# Green Agent LLM configuration (uses API keys from .env)
[green_agent.env]
GREEN_LLM_PROVIDER = "openai"
GREEN_OPENAI_MODEL = "gpt-4o"
# GREEN_OPENAI_API_KEY is automatically loaded from .env

# Purple Agent LLM configuration (uses API keys from .env)
[purple_agent.env]
PURPLE_LLM_PROVIDER = "openai"
PURPLE_OPENAI_MODEL = "gpt-4o"
# PURPLE_OPENAI_API_KEY is automatically loaded from .env

# Benchmark selection (auto-discovers tasks)
# Uncomment benchmarks you want to run:
# [[benchmarks]]
# id = "miniwob"
# max_tasks = 2

# [[benchmarks]]
# id = "assistantbench"
# max_tasks = 1
```

**Key Points:**
- ✅ **API Keys**: Always in `.env` file (never commit to git)
- ✅ **All Other Settings**: In TOML files (task limits, timeouts, models, benchmarks)
- ✅ **TOML References .env**: Uses `${OPENAI_API_KEY}` syntax to load keys automatically

---

## Project Structure

```
weag/
├── green-agent/              # Green Agent (evaluator/orchestrator)
│   ├── src/
│   │   ├── main.py          # A2A server entry point
│   │   ├── a2a/             # A2A message handling
│   │   ├── mcp/             # MCP server (browser tools)
│   │   ├── agent/           # LLM orchestration
│   │   ├── assessment/      # Task tracking & metrics
│   │   ├── benchmarks/      # Task discovery
│   │   └── environment/     # BrowserGym integration
│   └── datasets/            # Benchmark datasets (MiniWoB HTML)
│
├── purple-agent/             # Purple Agent (task executor)
│   ├── src/
│   │   ├── main.py          # A2A client entry point
│   │   ├── executor.py      # Task execution logic
│   │   ├── agent/           # Agent with MCP tools
│   │   └── tools/           # MCP client integration
│   └── tests/
│
├── kickstart_assessment.py   # Orchestration script (local + Docker)
├── scenarios/                # Assessment configurations
├── docs/                     # Documentation
└── output/                   # Results and artifacts
```

---

## Common Commands

### Local Development

```bash
# Run tests
pytest tests/unit/ -v

# View logs
tail -f logs/green-agent.log

# Debug MCP server standalone
python -m src.green_agent.mcp.server

# Check environment
python -c "import browsergym; print(browsergym.__version__)"
```

### Docker Operations

```bash
# View running containers
docker ps

# Check logs
docker compose logs green-agent
docker compose logs purple_web_agent

# Shell into container
docker exec -it <container_id> bash

# Check image sizes
docker images | grep weag

# Clean up everything
docker compose down -v
docker system prune -a
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError` | Activate virtual environment first: `.\.venv\Scripts\Activate.ps1` |
| Langfuse auth error | Add keys to `.env` or ignore (non-blocking) |
| Browser not visible | Use `--visible` flag or set `headless = false` in config |
| Task timeout | Increase `--timeout` or `timeout_seconds` in config |
| MCP connection error | Check that MCP server started on port 8001 |
| Docker build slow | Use `--no-cache` flag or check Docker Desktop resources |
| Port conflicts | Ensure ports 8001, 9009, 9010 are available |

---

## Development

### Adding New Benchmarks

1. Add dataset to `green-agent/datasets/`
2. Update `src/benchmarks/task_discovery.py`
3. Add profile to `src/benchmarks/profiles.py`
4. Register tools in `src/benchmarks/tool_registry.py`

### Modifying Agents

- **Green Agent**: Edit `green-agent/src/` files
- **Purple Agent**: Edit `purple-agent/src/` files
- **Both**: Rebuild Docker images after changes

---

## License

MIT License

