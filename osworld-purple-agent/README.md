# OSWorld Purple Agent

A2A purple agent for the OSWorld computer use benchmark on the AgentBeats platform.
Receives multi-part messages (instruction + screenshot + env config) from the OSWorld green agent,
calls an LLM via the OpenAI Agents SDK, and returns a sequence of pyautogui actions.

## Requirements

- Python 3.11+
- API key for your chosen LLM provider (see `.env.example`)

## Quick Start

```bash
# 1. Install dependencies
pip install -e ".[dev]"

# 2. Configure environment
cp .env.example .env
# Edit .env — set OSWORLD_OPENROUTER_API_KEY (or OSWORLD_OPENAI_API_KEY / OSWORLD_GEMINI_API_KEY)

# 3. Start the agent
osworld-agent
# OR
uvicorn src.server:app --host 0.0.0.0 --port 8000
```

The agent card is available at `GET http://localhost:8000/`.

## Docker

```bash
# Build
docker build -t osworld-purple-agent .

# Run (LiteLLM / OpenRouter — default)
docker run -p 8000:8000 -e OSWORLD_OPENROUTER_API_KEY=<your-key> osworld-purple-agent

# Run with OpenAI
docker run -p 8000:8000 \
  -e OSWORLD_LLM_PROVIDER=openai \
  -e OSWORLD_OPENAI_API_KEY=<your-key> \
  osworld-purple-agent
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `OSWORLD_LLM_PROVIDER` | `litellm` | LLM provider: `openai`, `gemini`, or `litellm` |
| `OSWORLD_OPENROUTER_API_KEY` | — | OpenRouter API key (required for `litellm`) |
| `OSWORLD_OPENAI_API_KEY` | — | OpenAI API key (required for `openai`) |
| `OSWORLD_GEMINI_API_KEY` | — | Google Gemini API key (required for `gemini`) |
| `OSWORLD_LITELLM_MODEL` | `google/gemini-2.0-flash-exp:free` | OpenRouter model identifier |
| `OSWORLD_OPENAI_MODEL` | `gpt-4o` | OpenAI model name |
| `OSWORLD_GEMINI_MODEL` | `gemini-2.5-flash` | Gemini model name |
| `OSWORLD_HOST` | `0.0.0.0` | Bind host |
| `OSWORLD_PORT` | `8000` | Bind port |
| `OSWORLD_LOG_LEVEL` | `INFO` | Logging level |
| `OSWORLD_LLM_MAX_ITERATIONS` | `20` | Max agent iterations per step |

## A2A Protocol

The agent conforms to the A2A protocol spec and accepts steps from the OSWorld green agent.
Each step contains:
1. **TextPart** — task instruction
2. **DataPart** — `env_config` (action_space, observation_type)
3. **FilePart** (optional) — `screenshot.png` as base64 PNG
4. **DataPart** (optional) — `accessibility_tree`
5. **DataPart** (optional) — `terminal` output

Each step returns:
1. **TextPart** — LLM reasoning chain-of-thought
2. **DataPart** — `{"actions": ["pyautogui.click(100, 200)", ...]}` or `["FAIL"]` on error

## Tests

```bash
pytest tests/ -v
```
