# Quickstart: OSWorld Purple Agent

**For**: `001-osworld-purple-agent-scaffold`  
**Date**: 2026-04-03

---

## Prerequisites

- Python 3.11+
- `uv` or `pip` for package management
- An API key for one of: OpenAI, Google Gemini, or OpenRouter (LiteLLM)
- Docker (for containerised testing and submission)
- OSWorld green agent running on port 9009 (for end-to-end testing)

---

## 1. Local Development Setup

```powershell
# From repo root
cd osworld-purple-agent

# Create virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1        # Windows
# source .venv/bin/activate          # Linux/macOS

# Install dependencies
pip install -e ".[dev,test]"
```

---

## 2. Configure Environment Variables

```powershell
# Copy the example file
copy .env.example .env
```

Edit `.env` and set your credentials. Minimum required for the default `litellm` provider:

```env
# Required: LiteLLM via OpenRouter (default provider)
OSWORLD_OPENROUTER_API_KEY=sk-or-...

# Optional: override provider
# OSWORLD_LLM_PROVIDER=openai
# OSWORLD_OPENAI_API_KEY=sk-...

# Optional: override provider to Gemini
# OSWORLD_LLM_PROVIDER=gemini
# OSWORLD_GEMINI_API_KEY=...
```

---

## 3. Start the Agent

```powershell
# From osworld-purple-agent/
python -m uvicorn src.server:app --host 0.0.0.0 --port 8000 --reload
```

Expected output:
```
INFO:     Started server process [12345]
INFO:     Waiting for application startup.
INFO:osworld_agent.server:OSWorld Purple Agent starting on 0.0.0.0:8000
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

---

## 4. Verify the Agent Card

```powershell
curl http://localhost:8000/
```

Expected response (abbreviated):
```json
{
  "name": "OSWorld Purple Agent",
  "skills": [{"id": "osworld_task", ...}]
}
```

---

## 5. Send a Test Step (without green agent)

Use `httpx` or any HTTP client to send a minimal step message:

```python
import httpx, base64, json

# Encode a dummy screenshot (1x1 white PNG)
dummy_png = base64.b64encode(b'\x89PNG\r\n...(minimal PNG bytes)...').decode()

payload = {
    "id": "test-task-001",
    "sessionId": "test-session-001",
    "message": {
        "role": "user",
        "parts": [
            {"type": "text", "text": "Open a text editor"},
            {"type": "data", "data": {"env_config": {"action_space": "pyautogui", "observation_type": "screenshot"}}},
            {"type": "file", "file": {"name": "screenshot.png", "mimeType": "image/png", "bytes": dummy_png}}
        ]
    }
}

resp = httpx.post("http://localhost:8000/", json=payload, timeout=60)
print(json.dumps(resp.json(), indent=2))
```

Expected response contains `actions` list in the data part.

---

## 6. Run Tests

```powershell
# Unit tests (no API key required)
pytest tests/unit/ -v

# Contract tests (validates A2A schema conformance)
pytest tests/contract/ -v

# All tests
pytest -v
```

---

## 7. Docker Build and Run

```powershell
# From osworld-purple-agent/
docker build -t osworld-purple-agent:latest .

# Run with environment variables
docker run --rm -p 8000:8000 \
  -e OSWORLD_OPENROUTER_API_KEY=sk-or-... \
  osworld-purple-agent:latest

# Verify agent card
curl http://localhost:8000/
```

---

## 8. End-to-End Test with Green Agent

```powershell
# Start the OSWorld green agent
docker run --rm -p 9009:9009 ghcr.io/rdi-foundation/osworld-green:latest

# In another terminal, start the purple agent
docker run --rm -p 8000:8000 \
  -e OSWORLD_OPENROUTER_API_KEY=sk-or-... \
  osworld-purple-agent:latest

# From repo root, run a quick assessment
python -c "
import httpx, json
resp = httpx.post('http://localhost:9009/', json={
    'id': 'e2e-test-001',
    'skillId': 'osworld_eval',
    'message': {
        'role': 'user',
        'parts': [{'type': 'text', 'text': 'test with purple_agent_url=http://host.docker.internal:8000'}]
    }
}, timeout=120)
print(resp.status_code)
"
```

---

## 9. Push to GHCR for Submission

```powershell
# Login to GHCR
echo $GITHUB_TOKEN | docker login ghcr.io -u USERNAME --password-stdin

# Tag and push
docker tag osworld-purple-agent:latest ghcr.io/YOUR_ORG/osworld-purple-agent:latest
docker push ghcr.io/YOUR_ORG/osworld-purple-agent:latest
```

Then register at https://agentbeats.dev and submit via Quick Submit or `scenario.toml`.

---

## Environment Variables Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `OSWORLD_LLM_PROVIDER` | `litellm` | LLM provider: `openai \| gemini \| litellm` |
| `OSWORLD_OPENAI_API_KEY` | — | OpenAI API key (if provider=openai) |
| `OSWORLD_OPENAI_MODEL` | `gpt-4o` | OpenAI model name |
| `OSWORLD_GEMINI_API_KEY` | — | Google Gemini API key (if provider=gemini) |
| `OSWORLD_GEMINI_MODEL` | `gemini-2.5-flash` | Gemini model name |
| `OSWORLD_OPENROUTER_API_KEY` | — | OpenRouter API key (if provider=litellm) |
| `OSWORLD_LITELLM_MODEL` | `google/gemini-2.0-flash-exp:free` | OpenRouter model identifier |
| `HOST` | `0.0.0.0` | Server bind address |
| `PORT` | `8000` | Server port |
| `LOG_LEVEL` | `INFO` | Logging level: `DEBUG \| INFO \| WARNING \| ERROR` |
| `AGENT_NAME` | `OSWorld Purple Agent` | Name shown in agent card |
| `AGENT_VERSION` | `0.1.0` | Version shown in agent card |
