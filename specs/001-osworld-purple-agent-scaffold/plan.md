# Implementation Plan: OSWorld Purple Agent — Initial Scaffold

**Branch**: `001-osworld-purple-agent-scaffold` | **Date**: 2026-04-03 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/001-osworld-purple-agent-scaffold/spec.md`

## Summary

Build the initial scaffold for a new OSWorld purple agent (`osworld-purple-agent/`) that speaks
A2A protocol with the OSWorld green agent, uses OpenAI Agents SDK for multimodal (screenshot +
text) LLM calls, supports three providers (OpenAI, Gemini, LiteLLM — default: `litellm`) entirely
via environment variables, and is fully containerised for GHCR submission to the AgentBeats
competition (deadline: April 12, 2026).

The agent follows the official AgentBeats agent-template structure and reuses the proven
`LLMClientFactory` pattern from `purple-agent/src/llm_provider.py` with an `OSWORLD_` prefix.

## Technical Context

**Language/Version**: Python 3.11+  
**Primary Dependencies**: `a2a-sdk[http-server]>=0.3.20`, `openai-agents[litellm]>=0.6.4`,
`uvicorn>=0.38.0`, `pydantic>=2.12.5`, `python-dotenv>=1.1.1`, `openai>=1.0.0`  
**Storage**: In-memory `dict[str, list]` keyed by `context_id` — no external storage needed  
**Testing**: `pytest>=8.0.0`, `pytest-asyncio>=0.24.0`  
**Target Platform**: Linux container (Docker), local Python 3.11+  
**Project Type**: web-service (A2A HTTP server, port 8000)  
**Performance Goals**: Agent card <3 s; full step cycle (receive → LLM → respond) <30 s  
**Constraints**: No ML frameworks, no browser libs — pure reasoning agent; deadline April 12 2026  
**Scale/Scope**: Up to 15 steps per evaluation session, one session per `context_id`

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. A2A Protocol Conformance | ✅ PASS | `a2a-sdk` used throughout; multi-part message parsing in `messenger.py`; response format matches spec |
| II. Agent Template Alignment | ✅ PASS | `server.py / executor.py / agent.py / llm_provider.py` mirrors official agent-template exactly |
| III. OpenAI Agents SDK — single layer | ✅ PASS | All LLM calls via `Runner.run()` with image_url content parts; no direct VLM calls |
| IV. Simplicity Over Cleverness | ✅ PASS | Flat `src/` with 6 modules; no inheritance; functions ≤50 lines |
| V. Reuse Before Creating | ✅ PASS | `llm_provider.py` copied from `purple-agent/src/` with prefix swap; config pattern reused |
| VI. Observability | ✅ PASS | Structured `logging` at INFO/DEBUG; step in/out logged; Langfuse optional |

*Post-design re-check*: ✅ All principles satisfied — no violations.

## Project Structure

### Documentation (this feature)

```text
specs/001-osworld-purple-agent-scaffold/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── a2a-messages.md  # Phase 1 output
└── tasks.md             # Phase 2 output (/speckit.tasks — NOT created here)
```

### Source Code (repository root)

```text
osworld-purple-agent/
├── src/
│   ├── __init__.py
│   ├── server.py          # AgentCard → DefaultRequestHandler → A2AStarletteApplication → uvicorn
│   ├── executor.py        # OsworldAgentExecutor(AgentExecutor) — per-context_id Agent instances
│   ├── agent.py           # OsworldAgent.run(message, updater) — LLM call + action parsing
│   ├── llm_provider.py    # LLMConfig/LLMClientFactory — copied from purple-agent/, OSWORLD_ prefix
│   ├── config.py          # OsworldConfig — env var loading (host, port, log level, etc.)
│   └── messenger.py       # A2A message parsing utilities (extract parts by type)
├── tests/
│   ├── __init__.py
│   ├── unit/
│   │   ├── test_messenger.py     # Part extraction, action parsing edge cases
│   │   └── test_llm_provider.py  # Provider config loading from env vars
│   └── contract/
│       └── test_a2a_schema.py    # A2A agent card and message response schema
├── Dockerfile
├── pyproject.toml
├── amber-manifest.json5
├── .env.example
└── README.md
```

**Structure Decision**: Single flat project under `osworld-purple-agent/` at repo root. Six source
modules only — matches the official agent-template and the existing `purple-agent/` directory for
consistency. No nested packages needed for this scope.

## Complexity Tracking

> No constitution violations — this section is intentionally empty.
