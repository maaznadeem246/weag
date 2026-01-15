# WEAG - Web Environment Agent Green

**BrowserGym Green Agent for AgentBeats Competition**

---

## Quick Start

### Prerequisites

- Python 3.11+
- `GEMINI_API_KEY` (for LLM)

### Setup

```bash
git clone <your-repo-url>
cd weag

cp sample.env .env
# Edit .env → add GEMINI_API_KEY=your_key_here
```

---

## Running Locally (Without Docker)

```bash
# Activate virtual environment
.\.venv\Scripts\Activate.ps1    # Windows
source .venv/bin/activate        # Linux/Mac

# Run single task
python kickstart_assessment.py --task miniwob.click-test

# Run multi-task (default benchmarks)
python kickstart_assessment.py

# Run with visible browser
python kickstart_assessment.py --task miniwob.click-test --visible
```

**Results:** `output/results.json`

---

## Running with Docker

### Build

```bash
docker build --platform linux/amd64 -t weag-green-agent:latest ./green-agent
docker build --platform linux/amd64 -t weag-purple-agent:latest ./purple-agent
```

### Run

```bash
mkdir -p output results
docker compose up --abort-on-container-exit
```

**Results:** `output/results.json` and `results/agentbeats-results-*.json`

### Rebuild

```bash
docker compose down
docker build --no-cache --platform linux/amd64 -t weag-green-agent:latest ./green-agent
docker build --no-cache --platform linux/amd64 -t weag-purple-agent:latest ./purple-agent
docker compose up --abort-on-container-exit
```

---

## Supported Benchmarks

| Benchmark | Status |
|-----------|--------|
| **miniwob** | ✅ Ready |
| **assistantbench** | ✅ Ready |

---

## Project Structure

```
weag/
├── green-agent/              # Evaluator (A2A + MCP server)
├── purple-agent/             # Participant (A2A client)
├── kickstart_assessment.py   # Orchestration script
└── output/                   # Results
```

---

## Configuration

Edit `scenarios/browsergym/scenario-local.toml`:

```toml
[config]
max_tasks_per_benchmark = 2
headless = true
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError` | Activate venv first |
| Langfuse auth error | Add keys to `.env` or ignore |
| Browser not visible | Use `--visible` flag |
| Timeout | Use `--timeout 300` |

---

## License

MIT License

