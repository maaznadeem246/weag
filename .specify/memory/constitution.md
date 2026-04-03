<!--
Sync Impact Report
==================
- Version change: 0.0.0 → 1.0.0 (MAJOR — initial ratification)
- Modified principles: N/A (initial creation)
- Added sections:
  - Core Principles (6 principles)
  - Technology Constraints
  - Development Workflow
  - Governance
- Removed sections: N/A
- Templates requiring updates:
  - .specify/templates/plan-template.md — ✅ no updates needed
    (Constitution Check section is generic/dynamic)
  - .specify/templates/spec-template.md — ✅ no updates needed
    (user story structure is compatible)
  - .specify/templates/tasks-template.md — ✅ no updates needed
    (phase structure accommodates these principles)
- Follow-up TODOs: None
-->

# OSWorld Purple Agent Constitution

## Core Principles

### I. A2A Protocol Conformance (NON-NEGOTIABLE)

All communication with the OSWorld Green Agent MUST use the A2A
(Agent-to-Agent) protocol. The purple agent MUST:

- Parse incoming multi-part messages: TextPart (instruction),
  DataPart (env_config), FilePart (screenshot), DataPart
  (accessibility_tree), DataPart (terminal)
- Respond with: TextPart (reasoning) + DataPart containing
  `{"actions": ["pyautogui.click(x, y)", ...]}`
- Support special action strings: `WAIT`, `DONE`, `FAIL`
- Maintain per-context_id conversation state for multi-step
  evaluation (same task across multiple steps, max 15 by default)

**Rationale**: The green agent dictates the protocol. Any
deviation causes evaluation failure — there is zero tolerance
for malformed A2A messages.

### II. Agent Template Alignment

The agent MUST follow the official AgentBeats agent-template
structure (`server.py`, `executor.py`, `agent.py`,
`messenger.py`) and use the `a2a-sdk` package:

- `server.py`: AgentCard → DefaultRequestHandler →
  A2AStarletteApplication → uvicorn
- `executor.py`: Per-context_id agent instances via
  `AgentExecutor`, `TaskUpdater` for status/artifacts
- `agent.py`: Core logic in `Agent.run(message, updater)`
- Dockerized for GHCR deployment with `amber-manifest.json5`

**Rationale**: AgentBeats judges evaluate conformance to the
official template. Deviating breaks automated assessment
pipelines and disqualifies submissions.

### III. OpenAI Agents SDK as Single Orchestration Layer

All LLM interactions MUST go through the OpenAI Agents SDK
(`agents` package). There MUST NOT be separate VLM/LLM call
paths:

- Use `Agent` + `Runner.run()` for all model calls
- Pass screenshots as multimodal content:
  `{"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}`
- Use `@function_tool` for any tool definitions
- Multi-provider support via `LLMClientFactory` pattern:
  OpenAI, Gemini (via OpenAI-compatible endpoint), LiteLLM

**Rationale**: A single orchestration layer reduces complexity,
enables consistent tracing, and matches the proven pattern
already used in the existing WEAG green and purple agents.

### IV. Simplicity Over Cleverness

Code MUST be minimal, linear, and directly solve the problem:

- No abstract base classes or factory patterns unless shared
  by 3+ concrete implementations
- No custom wrappers around SDK functionality that already
  exists (e.g., do not wrap `Runner.run()`)
- Prefer flat module structure over deep nesting
- Functions MUST be under 50 lines; split if longer
- Use standard library and SDK primitives before third-party

**Rationale**: Competition deadline is April 12, 2026. Every
abstraction layer is a liability under time pressure. Simple
code is faster to debug, review, and extend.

### V. Reuse Before Creating

Before writing new code, existing WEAG codebase MUST be checked
for reusable components:

- `purple-agent/src/llm_provider.py` — copy and adapt for
  multi-provider LLM support
- `purple-agent/src/config.py` — environment variable loading
  pattern
- A2A messaging patterns from existing green/purple agents
- If unsure whether to reuse or create, ask the user first

**Rationale**: The WEAG repo already contains battle-tested
implementations for LLM providers, config loading, and A2A
messaging. Duplicating effort wastes time and introduces
inconsistency.

### VI. Observability and Traceability

Every evaluation step MUST be traceable for debugging:

- Log incoming A2A message parts (instruction text, config,
  screenshot size, a11y tree length) at INFO level
- Log outgoing actions and reasoning at INFO level
- Log LLM provider, model name, and token usage at DEBUG level
- Use structured logging (`logging` module with consistent
  format)
- Support Langfuse `@observe` decorator integration for
  production tracing

**Rationale**: OSWorld tasks run on remote VMs with no
interactive debugging. Logs are the only way to diagnose
failures. Competition scoring depends on understanding why
tasks fail.

## Technology Constraints

- **Language**: Python 3.11+
- **LLM SDK**: `openai-agents[litellm]` >=0.13.0
- **A2A SDK**: `a2a-sdk[http-server]` >=0.3.20
- **Server**: `uvicorn` >=0.38.0
- **Config**: `pydantic` for settings, `python-dotenv` for
  env loading
- **LLM Providers**: OpenAI (GPT-4o), Gemini (2.5 Flash via
  OpenAI-compatible API), LiteLLM (OpenRouter and others)
- **Action Space**: `pyautogui` code strings only (executed by
  green agent on the VM — purple agent generates, not executes)
- **Container**: Docker image published to GHCR for submission
- **No** additional ML frameworks, browser automation libraries,
  or GUI toolkits — the purple agent is a pure reasoning agent

## Development Workflow

- **Branch strategy**: Feature branches off `main`, PR-based
  merge
- **Testing**: Unit tests for message parsing, action
  formatting, and LLM provider setup. Contract tests for A2A
  message schema conformance.
- **Local testing**: Run against green agent Docker container
  (`ghcr.io/rdi-foundation/osworld-green:latest`) on port 9009
- **Submission**: Build Docker image → push to GHCR → register
  on agentbeats.dev → Quick Submit or scenario.toml
- **Deadline**: Sprint 2 ends April 12, 2026 — all code MUST
  be submission-ready before this date

## Governance

This constitution supersedes all other development practices
for the OSWorld purple agent. All code changes MUST comply
with these principles.

- Amendments require updating this file with a version bump
  and sync impact report
- Version follows semantic versioning: MAJOR (principle
  removal/redefinition), MINOR (new principle/section),
  PATCH (clarification/wording)
- Use `AGENTS.md` and `OSWORLD_RESEARCH.md` as runtime
  development guidance

**Version**: 1.0.0 | **Ratified**: 2026-04-03 | **Last Amended**: 2026-04-03
