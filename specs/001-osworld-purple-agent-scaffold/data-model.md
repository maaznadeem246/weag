# Data Model: OSWorld Purple Agent — Initial Scaffold

**Phase 1 output for**: `001-osworld-purple-agent-scaffold`  
**Date**: 2026-04-03

---

## Entities

### StepMessage

Represents one incoming evaluation step from the OSWorld green agent.
Extracted from the raw A2A `Message` object by `messenger.py`.

| Field | Type | Required | Source | Description |
|-------|------|----------|--------|-------------|
| `instruction` | `str` | ✅ | `TextPart` | Task instruction text (e.g., "Open LibreOffice Calc and create a chart") |
| `env_config` | `dict` | ✅ | `DataPart` (key: `env_config`) | Env config: `{"action_space": "pyautogui", "observation_type": "screenshot"}` |
| `screenshot_b64` | `str \| None` | ❌ | `FilePart` (mime: `image/png`) | Base64-encoded PNG of the full Ubuntu desktop. None if not provided. |
| `a11y_tree` | `str \| None` | ❌ | `DataPart` (key: `accessibility_tree`) | Linearised accessibility tree XML. None if observation_type excludes it. |
| `terminal` | `str \| None` | ❌ | `DataPart` (key: `terminal`) | Recent terminal output. None if not provided. |

**Validation rules**:
- `instruction` must be non-empty; if empty, log WARNING and use `"(no instruction provided)"`.
- `screenshot_b64` is optional; if absent, proceed text-only and log a WARNING.
- `env_config` defaults to `{"action_space": "pyautogui", "observation_type": "screenshot"}` if DataPart is missing.

---

### StepResponse

Represents the purple agent's reply to one evaluation step.
Sent back to the green agent as a two-part A2A response.

| Field | Type | Description |
|-------|------|-------------|
| `reasoning` | `str` | LLM's chain-of-thought text — sent as `TextPart` |
| `actions` | `list[str]` | Ordered list of pyautogui commands or special values — sent as `DataPart({"actions": [...]})` |

**Valid action values**:
- Any valid pyautogui Python expression string, e.g. `"pyautogui.click(500, 300)"`
- `"WAIT"` — pause and wait for the next step
- `"DONE"` — task is complete
- `"FAIL"` — task cannot be completed (also used on LLM error)

**Rules**:
- `actions` must be a non-empty list; fallback to `["FAIL"]` on parse failure.
- `reasoning` must be a non-empty string; fallback to `"(no reasoning)"` if blank.

---

### EvaluationSession

Holds the in-memory conversation history for one task attempt.
Stored in `OsworldAgentExecutor.sessions` dict.

| Field | Type | Description |
|-------|------|-------------|
| `context_id` | `str` | Unique ID for this task attempt — provided by the A2A framework |
| `history` | `list[dict]` | OpenAI-format message list: `[{"role": "user", "content": [...]}, {"role": "assistant", "content": "..."}]` |
| `step_count` | `int` | Number of steps processed so far (for logging; max 15 by default) |

**Rules**:
- A new empty session is created automatically on first message for an unknown `context_id`.
- Sessions are never persisted — cleared when the process restarts.
- History grows by two entries per step: one user message (instruction + screenshot) and one assistant message (reasoning + actions).

---

### LLMProviderConfig

Runtime-resolved LLM configuration. Created once at startup by `setup_llm_client(prefix="OSWORLD_")`.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `provider` | `LLMProvider` | `litellm` | Active provider: `openai \| gemini \| litellm` |
| `openai_api_key` | `str \| None` | None | OpenAI API key |
| `gemini_api_key` | `str \| None` | None | Google Gemini API key |
| `openrouter_api_key` | `str \| None` | None | OpenRouter API key (used by litellm) |
| `openai_model` | `str` | `gpt-4o` | OpenAI model name |
| `gemini_model` | `str` | `gemini-2.5-flash` | Gemini model name |
| `litellm_model` | `str` | `google/gemini-2.0-flash-exp:free` | OpenRouter model identifier |
| `max_iterations` | `int` | `20` | Max SDK `Runner.run()` turns |

**State transitions**:
```
Startup
  └─ LLMConfig.from_env(prefix="OSWORLD_")
       └─ LLMClientFactory.create_client(config)
            ├─ provider=openai  → AsyncOpenAI(api_key) + set_default_openai_client()
            ├─ provider=gemini  → AsyncOpenAI(api_key, base_url=gemini_url) + set_default_openai_client()
            └─ provider=litellm → LitellmModel(model, api_key) — used directly as Agent.model
```

**Error transitions**:
- Missing required API key → `ValueError` at startup → logged + process exits with code 1
- Invalid `LLM_PROVIDER` value → falls back to `litellm`, logs WARNING

---

### OsworldAgentConfig

Server-level configuration loaded at startup from environment variables.

| Field | Env Var | Default | Description |
|-------|---------|---------|-------------|
| `host` | `HOST` | `0.0.0.0` | Server bind address |
| `port` | `PORT` | `8000` | Server listening port |
| `log_level` | `LOG_LEVEL` | `INFO` | Python logging level |
| `agent_name` | `AGENT_NAME` | `OSWorld Purple Agent` | Name shown in agent card |
| `agent_version` | `AGENT_VERSION` | `0.1.0` | Version shown in agent card |
| `skill_id` | — | `osworld_task` | Fixed skill identifier (not configurable) |

---

## Relationships

```
OsworldAgentExecutor
├── sessions: dict[context_id → EvaluationSession]   (1 executor : N sessions)
└── agent: OsworldAgent
      └── llm_config: LLMProviderConfig               (1 agent : 1 config)

OsworldAgent.run(message)
├── reads  → StepMessage  (parsed from A2A Message by messenger.py)
└── writes → StepResponse (serialised to A2A parts by messenger.py)

EvaluationSession
└── history: list[OpenAI message dicts]  (grows by 2 per step)
```
