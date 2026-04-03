# OSWorld Purple Agent — Implementation Plan

## Goal
Build a purple agent for the **OSWorld-Verified** green agent in AgentBeats Phase 2, Sprint 2 (deadline: April 12, 2026). The agent receives Ubuntu desktop screenshots via A2A and returns pyautogui actions.

## Base
- **Template**: https://github.com/RDI-Foundation/agent-template
- **Reference**: https://github.com/RDI-Foundation/agentbeats-tutorial/blob/v1/scenarios/tau2/tau2_agent.py
- **SDK**: OpenAI Agents SDK with multimodal `Runner.run()` (same as WEAG agents)
- **VLM**: Gemini 2.5 Flash (primary), GPT-4o / Claude 3.5 Sonnet (alternatives)

## Project Structure

```
osworld-purple-agent/
├── src/
│   ├── server.py          # A2A server with AgentCard
│   ├── executor.py        # Parse multi-part A2A messages, call agent, format response
│   ├── agent.py           # OpenAI Agents SDK, Runner.run() with multimodal input
│   ├── llm_provider.py    # Multi-provider LLM support (OpenAI/Gemini/LiteLLM) — copied from WEAG
│   ├── messenger.py       # A2A messaging utilities (from template)
│   ├── prompts.py         # System prompt (pyautogui, Ubuntu desktop, WAIT/DONE/FAIL)
│   └── action_parser.py   # Extract pyautogui code from LLM output
├── tests/
│   └── test_agent.py      # A2A conformance + custom tests
├── Dockerfile
├── pyproject.toml
├── amber-manifest.json5
└── README.md
```

## Implementation Phases

### Phase 1: Project Scaffold
- [ ] Create repo from agent-template (or fork it)
- [ ] Update `pyproject.toml`:
  ```toml
  dependencies = [
      "a2a-sdk[http-server]>=0.3.20",
      "uvicorn>=0.38.0",
      "openai-agents[litellm]>=0.6.4",
      "openai>=1.0.0",
      "python-dotenv>=1.1.1",
      "langfuse>=2.0.0",
  ]
  ```
- [ ] Update `amber-manifest.json5`:
  - config_schema: LLM_PROVIDER, GEMINI_API_KEY (secret), OPENAI_API_KEY (secret), OPENROUTER_API_KEY (secret)
  - program.entrypoint: `uv run python src/server.py --host 0.0.0.0 --port 9010`
  - network.endpoints: port 9010
- [ ] Update `Dockerfile` — expose port 9010

### Phase 2: A2A Server + Message Handling
- [ ] `src/server.py` — AgentCard:
  - name: "OSWorld Purple Agent"
  - skill id: "desktop_automation"
  - default_input_modes: ["text", "image"]
  - capabilities: streaming=True
  - port: 9010
- [ ] `src/executor.py` — Parse incoming multi-part A2A messages:
  - Extract TextPart → instruction
  - Extract DataPart → env_config (action_space, observation_type)
  - Extract FilePart → screenshot (base64 PNG)
  - Extract DataPart → accessibility_tree (optional)
  - Extract DataPart → terminal (optional)
  - Pass all to Agent.run()
  - Format response: TextPart (reasoning) + DataPart ({"actions": [...]})
- [ ] `src/messenger.py` — copy from agent-template (no changes needed)

### Phase 3: Agent Core
- [ ] `src/llm_provider.py` — **Copy from** `purple-agent/src/llm_provider.py` (same multi-provider pattern):
  - `LLMProvider` enum: OPENAI, GEMINI, LITELLM
  - `LLMConfig.from_env(prefix="OSWORLD_")` — reads env vars with prefix fallback
  - `LLMClientFactory` — creates AsyncOpenAI (OpenAI/Gemini) or LitellmModel (LiteLLM)
  - `setup_llm_client()` — returns (client_or_none, model_name_or_litellm_model, config)
  - Only change: prefix from `PURPLE_` to `OSWORLD_`, HTTP-Referer header
- [ ] `src/agent.py`:
  - Configure OpenAI Agents SDK using `setup_llm_client()`:
    ```python
    set_default_openai_api("chat_completions")
    client, model, config = setup_llm_client(prefix="OSWORLD_")
    if client is not None:  # OpenAI or Gemini
        set_default_openai_client(client, use_for_tracing=True)
    agent = Agent(name="OSWorldAgent", instructions=SYSTEM_PROMPT, tools=[], model=model)
    ```
  - Call `Runner.run()` with multimodal content parts:
    ```python
    result = await Runner.run(
        agent,
        [{"role": "user", "content": [
            {"type": "text", "text": f"{trajectory_text}\n\nTask: {instruction}"},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{screenshot_b64}"}}
        ]}],
        context=agent_context,
    )
    ```
  - Maintain trajectory per context_id: list of (step_number, action_taken)
  - Limit to last 3 steps (configurable)
  - Parse `result.final_output` → extract actions via action_parser

- [ ] `src/prompts.py` — System prompt covering:
  - You are an agent controlling an Ubuntu desktop via pyautogui
  - Available pyautogui actions with examples:
    - `pyautogui.click(x, y)`, `doubleClick`, `rightClick`
    - `pyautogui.typewrite("text")`, `pyautogui.hotkey("ctrl", "s")`
    - `pyautogui.moveTo(x, y)`, `pyautogui.scroll(clicks)`
    - `pyautogui.press("enter")`, `pyautogui.keyDown/keyUp`
    - `import time; time.sleep(1)` for waiting
  - Special commands: WAIT (need more time), DONE (task complete), FAIL (cannot complete)
  - Output format: wrap pyautogui code in ```python blocks
  - Strategy: observe screenshot carefully → plan next step → execute ONE action at a time
  - Start from official prompts: github.com/xlang-ai/OSWorld/mm_agents/prompts.py

- [ ] `src/action_parser.py`:
  - Extract code from ```python ... ``` blocks in LLM output
  - Handle WAIT, DONE, FAIL as special return values
  - Return list of action strings for the DataPart response
  - Handle multi-line code (multiple pyautogui calls)

### Phase 4: Testing & Deployment
- [ ] `tests/test_agent.py`:
  - Keep A2A conformance tests from template (agent card, message format)
  - Add: mock screenshot → verify TextPart + DataPart({"actions":[]}) response
  - Add: action_parser unit tests (code extraction, special commands)
- [ ] Local testing:
  ```bash
  docker pull ghcr.io/rdi-foundation/osworld-green:latest
  # Run green agent
  docker run -p 9009:9009 ghcr.io/rdi-foundation/osworld-green:latest
  # Run purple agent
  uv run src/server.py --host 0.0.0.0 --port 9010
  # Run conformance tests
  uv run pytest --agent-url http://localhost:9010
  ```
- [ ] Build & publish Docker image to GHCR
- [ ] Register on agentbeats.dev as purple agent
- [ ] Quick Submit to osworld-verified leaderboard

## Key Decisions

| Decision | Choice | Reason |
|----------|--------|--------|
| Base | agent-template | Official AgentBeats template, clean structure |
| SDK | OpenAI Agents SDK | Same as WEAG agents, supports multimodal Runner.run() |
| VLM | Multi-provider (Gemini/OpenAI/LiteLLM) | Same `llm_provider.py` pattern as WEAG agents. Default: Gemini 2.5 Flash |
| Tools | None (pure reasoning) | Agent sees screenshot, returns actions directly |
| Protocol | Pure A2A (no MCP) | OSWorld green agent doesn't use MCP |
| Observation | Screenshot only | Default in green agent config, simplest to start |
| Trajectory | Last 3 steps (text) | Matches original PromptAgent, avoids sending past screenshots |
| Project | Separate repo | Doesn't touch existing WEAG code |

## Environment Variables

### Option A: Gemini (recommended — cheapest, good vision)
```env
OSWORLD_LLM_PROVIDER=gemini
OSWORLD_GEMINI_API_KEY=your-gemini-api-key
OSWORLD_GEMINI_MODEL=gemini-2.5-flash
LOG_LEVEL=INFO
```

### Option B: OpenAI (strongest vision)
```env
OSWORLD_LLM_PROVIDER=openai
OSWORLD_OPENAI_API_KEY=your-openai-api-key
OSWORLD_OPENAI_MODEL=gpt-4o
LOG_LEVEL=INFO
```

### Option C: LiteLLM / OpenRouter (access to many models)
```env
OSWORLD_LLM_PROVIDER=litellm
OSWORLD_OPENROUTER_API_KEY=your-openrouter-api-key
OSWORLD_LITELLM_MODEL=google/gemini-2.0-flash-exp:free
LOG_LEVEL=INFO
```

Note: Unprefixed vars (e.g., `GEMINI_API_KEY`) work as fallbacks. `OSWORLD_` prefix takes priority.

## References
- OSWorld benchmark: https://os-world.github.io/
- OSWorld green agent: https://github.com/RDI-Foundation/osworld-green
- Original PromptAgent: https://github.com/xlang-ai/OSWorld/blob/main/mm_agents/agent.py
- Official prompts: https://github.com/xlang-ai/OSWorld/blob/main/mm_agents/prompts.py
- Agent template: https://github.com/RDI-Foundation/agent-template
- Tau2 example: https://github.com/RDI-Foundation/agentbeats-tutorial/blob/v1/scenarios/tau2/tau2_agent.py
- AgentBeats tutorial: https://docs.agentbeats.dev/tutorial/#2-purple-agents
- WEAG codebase: this repo (purple-agent/src/ for LLM provider, SDK patterns)
