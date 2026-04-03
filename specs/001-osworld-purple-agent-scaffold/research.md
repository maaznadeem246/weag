# Research: OSWorld Purple Agent — Initial Scaffold

**Phase 0 output for**: `001-osworld-purple-agent-scaffold`  
**Date**: 2026-04-03  
**Status**: Complete — no NEEDS CLARIFICATION items remain

All research findings below were derived from:
- `OSWORLD_RESEARCH.md` (existing repo file — exhaustive prior research)
- `purple-agent/src/llm_provider.py` (direct code reading)
- `purple-agent/pyproject.toml` (dependency versions)
- AgentBeats agent-template: https://github.com/RDI-Foundation/agent-template
- OSWorld green agent: https://github.com/RDI-Foundation/osworld-green

---

## Decision 1: Directory and package name

- **Decision**: `osworld-purple-agent/` at repo root, Python package `src/`
- **Rationale**: Follows kebab-case convention already used in this repo
  (`green-agent/`, `purple-agent/`). Clear and unambiguous. User confirmed.
- **Alternatives considered**: `osworld-agent/` (less explicit about role),
  `osworld_agent/` (snake_case, inconsistent with repo style)

---

## Decision 2: A2A framework and server structure

- **Decision**: Use `a2a-sdk[http-server]>=0.3.20` with the official
  agent-template structure: `server.py` → `executor.py` → `agent.py`
- **Rationale**: AgentBeats requires conformance to the official template.
  The `a2a-sdk` handles all A2A protocol details (task lifecycle, artifact
  streaming, SSE) — no wheel to reinvent.
- **Key classes used**:
  - `AgentCard`, `AgentSkill`, `AgentCapabilities` — agent identity
  - `DefaultRequestHandler` — routes A2A tasks to the executor
  - `A2AStarletteApplication` — wraps as ASGI app
  - `AgentExecutor` — base class for `OsworldAgentExecutor`
  - `TaskUpdater` — sends status updates and artifacts back to caller
- **Alternatives considered**: Raw FastAPI + custom protocol (rejected —
  non-standard, breaks automated assessment pipelines)

---

## Decision 3: LLM orchestration via OpenAI Agents SDK

- **Decision**: `openai-agents[litellm]>=0.6.4` with `Runner.run()` for all
  LLM calls. Screenshots passed as `image_url` content parts.
- **Rationale**: The SDK handles multimodal input natively. Using
  `Runner.run(agent, [{"role": "user", "content": [...image_url...]}])`
  avoids building a custom VLM pipeline. Consistent with the existing
  `purple-agent/` pattern the team already understands.
- **Image passing pattern**:
  ```python
  content = [
      {"type": "text", "text": instruction},
      {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64data}"}}
  ]
  result = await Runner.run(agent, [{"role": "user", "content": content}])
  ```
- **Alternatives considered**: Direct OpenAI `chat.completions.create()` call
  (rejected — bypasses SDK session/tracing); separate VLM layer (rejected —
  user confirmed this is unnecessary)

---

## Decision 4: LLM provider abstraction

- **Decision**: Copy `purple-agent/src/llm_provider.py` verbatim and change
  the env var prefix from `PURPLE_` to `OSWORLD_`. No other changes.
- **Rationale**: Constitution Principle V mandates reuse before creating. The
  existing `LLMConfig` / `LLMClientFactory` / `setup_llm_client()` pattern is
  battle-tested, covers all three providers, and is well-documented.
- **Default provider**: `litellm` (user confirmed — lowest cost for dev/competition)
- **Provider env var logic** (prefix=`OSWORLD_`, fallback to unprefixed):
  - `OSWORLD_LLM_PROVIDER` or `LLM_PROVIDER` → `openai | gemini | litellm`
  - OpenAI: `OSWORLD_OPENAI_API_KEY`, model default `gpt-4o`
  - Gemini: `OSWORLD_GEMINI_API_KEY`, base_url OpenAI-compat, model `gemini-2.5-flash`
  - LiteLLM: `OSWORLD_OPENROUTER_API_KEY`, model `openrouter/google/gemini-2.0-flash-exp:free`
- **SDK integration**: `set_default_openai_api("chat_completions")` required
  for Gemini; `set_default_openai_client(client)` for OpenAI/Gemini;
  `LitellmModel` passed directly as `Agent.model` for LiteLLM
- **Alternatives considered**: New abstraction from scratch (rejected — duplication),
  third-party `litellm` proxy for all providers (rejected — adds complexity)

---

## Decision 5: Conversation history storage

- **Decision**: In-memory `dict[str, list[dict]]` keyed by `context_id`,
  stored in `OsworldAgentExecutor`. Cleared when the process restarts.
- **Rationale**: OSWorld tasks are ≤15 steps. Sessions are shortlived. No
  need for persistence across restarts in competition mode. Matches the
  tau2 reference implementation's `ctx_id_to_messages` pattern. User confirmed.
- **History format**: List of OpenAI-format messages
  `[{"role": "user", "content": [...]}, {"role": "assistant", "content": "..."}]`
  — directly reusable in `Runner.run()` input.
- **Alternatives considered**: `SQLiteSession` from OpenAI Agents SDK (rejected —
  adds filesystem dependency, unnecessary for ≤15 steps)

---

## Decision 6: Action parsing from LLM output

- **Decision**: Extract `{"actions": [...]}` from the LLM's text output using
  regex or JSON parsing. Follow the OSWorld PromptAgent pattern:
  1. Try to parse a JSON block from the response
  2. Accept plain pyautogui code lines as individual actions
  3. Accept bare `WAIT`, `DONE`, or `FAIL` as special single-action responses
- **Rationale**: OSWorld green agent (`src/agent.py`) expects a `DataPart`
  with `{"actions": [...]}` — the format is fixed by the protocol.
- **Failure fallback**: On any LLM error or empty response, return
  `{"actions": ["FAIL"]}` with an error reasoning text (user confirmed).
- **Alternatives considered**: Structured output / response_format JSON schema
  (deferred — adds model compatibility complexity; plain parsing is sufficient
  for scaffold)

---

## Decision 7: Docker image base and build

- **Decision**: `python:3.11-slim` base image, multi-stage not needed for
  this size. `EXPOSE 8000`, CMD runs `uvicorn` directly.
- **Rationale**: Slim keeps the image under 500 MB. Single-stage is sufficient
  — there are no compiled native extensions to separate. Consistent with
  `purple-agent/Dockerfile` already in the repo.
- **GHCR tagging**: `ghcr.io/{owner}/osworld-purple-agent:latest`
- **Alternatives considered**: `python:3.11-alpine` (rejected — binary compat
  issues with some wheels); multi-stage (unnecessary at this scope)

---

## Decision 8: amber-manifest.json5 defaults

- **Decision**: Port `8000`, host `0.0.0.0`, skill id `osworld_task`,
  default LLM provider `litellm`
- **Rationale**: Port 8000 is the AgentBeats convention for purple agents
  (green agent is 9009). `amber-manifest.json5` is read by AgentBeats to
  configure deployment defaults. User confirmed port.

---

## No NEEDS CLARIFICATION items remain

All five user clarifications are resolved. Technical context is fully
determined. Phase 1 design can proceed immediately.
