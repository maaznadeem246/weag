# OSWorld Purple Agent — Research & Development

## OSWorld Benchmark

**Source**: https://os-world.github.io/
**Paper**: https://arxiv.org/abs/2404.07972
**Code**: https://github.com/xlang-ai/OSWorld

- 369 real-world computer tasks on Ubuntu VMs (QEMU-based DesktopEnv)
- Tasks span: desktop apps (LibreOffice, GIMP, terminal), web browsers, file management, cross-app workflows
- Execution-based evaluation — not just text matching
- Best model achieves ~12.24% success vs 72.36% human — massive gap
- Now **OSWorld-Verified** (July 2025 upgrade) with fixed examples, AWS support, updated benchmark results
- VM credentials: `user` / `password`
- 8 Google Drive tasks can be excluded (361 tasks accepted for leaderboard)

## OSWorld-Verified Green Agent

**Source**: https://github.com/RDI-Foundation/osworld-green
**Docker**: `ghcr.io/rdi-foundation/osworld-green:latest`
**Port**: 9009

### How It Works
The green agent wraps the original OSWorld `DesktopEnv` (QEMU Ubuntu VMs) and acts as both:
1. **A2A server** — receives evaluation requests from AgentBeats
2. **A2A client** — calls the purple agent per step via `A2AClientAgent.predict()`

### Key Source Files (github.com/RDI-Foundation/osworld-green)
- `src/agent.py` — `A2AClientAgent` class (sends messages TO purple agent) + `Agent` class (evaluation orchestrator)
- `src/executor.py` — Standard A2A executor, creates Agent per context_id
- `src/server.py` — AgentCard name="OSWorld Green Agent", skill id="osworld_eval", port 9009
- `src/messenger.py` — A2A messaging utilities
- `amber-manifest.json5` — Default config values

### Green → Purple Message Format (per step)
Each step, the green agent sends a multi-part A2A message:
- **TextPart**: task instruction (e.g., "Open LibreOffice Calc and create a chart...")
- **DataPart**: `{"env_config": {"action_space": "pyautogui", "observation_type": "screenshot"}}`
- **FilePart**: screenshot PNG (base64-encoded, full Ubuntu desktop)
- **DataPart**: `{"accessibility_tree": "..."}` (optional, if observation_type includes a11y)
- **DataPart**: `{"terminal": "..."}` (optional, terminal output)

### Purple → Green Response Format
- **TextPart**: LLM reasoning/thought text
- **DataPart**: `{"actions": ["pyautogui.click(500, 300)", "import time; time.sleep(1)"]}`
- Special actions: `WAIT`, `DONE`, `FAIL` (strings, not pyautogui code)

### Default Config (from amber-manifest.json5)
```json
{
  "action_space": "pyautogui",
  "observation_type": "screenshot",
  "max_steps": 15,
  "num_workers": 3,
  "test_all_meta_name": "test_nogdrive",
  "sleep_after_execution": 0.0
}
```

## Original OSWorld PromptAgent (Reference Implementation)

**Source**: https://github.com/xlang-ai/OSWorld/blob/main/mm_agents/agent.py
**Prompts**: https://github.com/xlang-ai/OSWorld/blob/main/mm_agents/prompts.py

### Key Patterns
- `PromptAgent` class with `predict(instruction, obs) -> (response, actions)`
- Supports GPT-4V, Gemini, Claude, Qwen, CogAgent, Llama3
- Manages trajectory history (`max_trajectory_length=3` — keeps last 3 screenshot+action pairs)
- Parses pyautogui code from markdown triple-backtick blocks
- Handles WAIT/DONE/FAIL special commands
- `parse_code_from_string()` extracts code from ```python blocks
- `linearize_accessibility_tree()` converts XML to tab-separated format
- `trim_accessibility_tree()` truncates to max_tokens

### Action Space: pyautogui
```python
# Common pyautogui actions
pyautogui.click(x, y)
pyautogui.doubleClick(x, y)
pyautogui.rightClick(x, y)
pyautogui.moveTo(x, y)
pyautogui.typewrite("text", interval=0.05)
pyautogui.hotkey("ctrl", "s")
pyautogui.scroll(clicks, x, y)
pyautogui.press("enter")
pyautogui.keyDown("shift")
pyautogui.keyUp("shift")
import time; time.sleep(1)
```

### Observation Types
- `screenshot` — PNG image of full desktop (default)
- `a11y_tree` — accessibility tree XML
- `screenshot_a11y_tree` — both
- `som` — Set-of-Marks annotated screenshot

## AgentBeats Platform

**App**: https://agentbeats.dev
**Tutorial**: https://docs.agentbeats.dev/tutorial
**Competition**: https://rdi.berkeley.edu/agentx-agentbeats

### Phase 2 Timeline
- Phase 2: March 2 – May 24, 2026
- Sprint 2: March 23 – April 12, 2026
- Track: Computer Use & Web Agent → OSWorld-Verified

### Purple Agent Registration & Submission
1. Build container image, publish to GHCR
2. Register as purple agent on agentbeats.dev
3. Submit assessment via **Quick Submit** (form on green agent page) or **Manual Submit** (scenario.toml + GitHub Actions)
4. Scores appear on leaderboard after PR merge

### Agent Template
**Source**: https://github.com/RDI-Foundation/agent-template

Official template structure:
```
src/
├── server.py      # A2A server with AgentCard, uvicorn
├── executor.py    # AgentExecutor, per-context_id agent instances, TaskUpdater
├── agent.py       # Agent.run(message, updater) — your logic here
└── messenger.py   # A2A messaging utilities
tests/
└── test_agent.py  # A2A conformance tests
Dockerfile
pyproject.toml     # a2a-sdk[http-server]>=0.3.20, uvicorn>=0.38.0
amber-manifest.json5
```

Key patterns from template:
- `server.py`: AgentCard → DefaultRequestHandler → A2AStarletteApplication → uvicorn
- `executor.py`: `self.agents: dict[str, Agent]` per context_id, `TaskUpdater` for status/artifacts
- `agent.py`: `Agent.run(message, updater)` — receives Message, uses updater.update_status() / updater.add_artifact()
- `messenger.py`: `Messenger.talk_to_agent(message, url)` for calling other agents

### Tau2 Example (Working Purple Agent)
**Source**: https://github.com/RDI-Foundation/agentbeats-tutorial/blob/v1/scenarios/tau2/tau2_agent.py

Single-file purple agent showing:
- AgentCard with AgentSkill
- `Tau2AgentExecutor(AgentExecutor)` with `ctx_id_to_messages` dict for conversation history
- `context.get_user_input()` to extract text from A2A message
- `litellm.completion()` for LLM calls with message history
- `new_agent_text_message()` to send response back
- CLI args: --host, --port, --card-url, --agent-llm

## WEAG Existing Codebase Patterns (for reference)

### OpenAI Agents SDK Usage
Both green and purple agents use the same SDK pattern:
```python
from agents import Agent, Runner, function_tool, RunContextWrapper

# Agent creation
agent = Agent[MyContext](
    name="AgentName",
    instructions="system prompt",
    tools=[...],  # list of @function_tool decorated functions
    model=model_name,  # string or LitellmModel
)

# Execution — supports multimodal input!
result = await Runner.run(
    agent,
    [{"role": "user", "content": [
        {"type": "text", "text": "instruction"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}
    ]}],
    context=my_context,
    session=session,  # optional, for multi-turn
    max_turns=10,
)
output = result.final_output  # string
```

### LLM Provider Pattern (purple-agent/src/llm_provider.py)
Multi-provider abstraction supporting 3 backends — **copy this file directly** for the new agent:

**Classes:**
- `LLMProvider` enum: `OPENAI`, `GEMINI`, `LITELLM`
- `LLMConfig(BaseModel)` — all config fields with env var loading
- `LLMClientFactory` — factory with `create_client()` and `create_litellm_model()`
- `setup_llm_client()` — top-level convenience function

**Config loading:** `LLMConfig.from_env(prefix="OSWORLD_")` reads env vars with prefix fallback:
```
OSWORLD_LLM_PROVIDER / LLM_PROVIDER → openai | gemini | litellm
OSWORLD_GEMINI_API_KEY / GEMINI_API_KEY → API key
OSWORLD_GEMINI_MODEL / GEMINI_MODEL → model name (default: gemini-2.5-flash)
OSWORLD_OPENAI_API_KEY / OPENAI_API_KEY → API key
OSWORLD_OPENAI_MODEL / OPENAI_MODEL → model name (default: gpt-4o)
OSWORLD_OPENROUTER_API_KEY / OPENROUTER_API_KEY → API key
OSWORLD_LITELLM_MODEL / LITELLM_MODEL → model name (default: google/gemini-2.0-flash-exp:free)
```

**Provider setup:**
- **OpenAI**: `AsyncOpenAI(api_key=key)` → returns (client, "gpt-4o")
- **Gemini**: `AsyncOpenAI(api_key=key, base_url="https://generativelanguage.googleapis.com/v1beta/openai/")` → returns (client, "gemini-2.5-flash")
- **LiteLLM**: `LitellmModel(model="openrouter/...", api_key=key)` → returns (None, LitellmModel)

**SDK integration (agent_factory.py):**
```python
from agents import set_default_openai_api, set_default_openai_client

set_default_openai_api("chat_completions")  # Required for Gemini
client, model, config = setup_llm_client(prefix="OSWORLD_")

if client is not None:  # OpenAI or Gemini
    set_default_openai_client(client, use_for_tracing=True)
    model_name = model  # string
else:  # LiteLLM
    model_name = model  # LitellmModel instance

agent = Agent(name="...", instructions="...", tools=[], model=model_name)
```

**Key detail:** For LiteLLM, `setup_llm_client()` returns `(None, LitellmModel, config)` — the LitellmModel IS the model, no client needed. For OpenAI/Gemini it returns `(AsyncOpenAI, model_string, config)`.

### Key SDK Discovery
**`Runner.run()` accepts multimodal input** (confirmed in installed SDK v0.13.2):
- `input: str | list[TResponseInputItem] | RunState[TContext]`
- Can pass `[{"role": "user", "content": [...image_url parts...]}]`
- This means we DON'T need to manually call VLM APIs — the SDK handles it

## Critical Differences: BrowserGym vs OSWorld

| Aspect | Current Purple (BrowserGym) | New Purple (OSWorld) |
|--------|---------------------------|---------------------|
| Communication | MCP tools via proxy | Pure A2A messages |
| Observations | Accessibility tree (text) | Desktop screenshots (PNG) |
| Actions | BrowserGym JSON `{"action":"click","bid":"13"}` | pyautogui code `pyautogui.click(500,300)` |
| Environment | Web browser (Chromium) | Full Ubuntu desktop (QEMU VM) |
| Model need | Text LLM sufficient | Vision-Language Model required |
| History | Single-shot per MCP call | Multi-turn conversation (same context_id) |
| Task types | Web forms, clicks, navigation | Desktop apps, terminal, files, web + more |
| SDK tools | 4 MCP proxy tools | None (pure reasoning) |
