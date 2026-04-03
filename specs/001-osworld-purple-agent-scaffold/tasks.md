---

description: "Task list for OSWorld Purple Agent Initial Scaffold"
---

# Tasks: OSWorld Purple Agent — Initial Scaffold

**Input**: Design documents from `specs/001-osworld-purple-agent-scaffold/`
**Prerequisites**: plan.md ✅, spec.md ✅, data-model.md ✅, contracts/a2a-messages.md ✅, quickstart.md ✅

**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- File paths are relative to `osworld-purple-agent/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the `osworld-purple-agent/` directory tree, project config, and
CI/deployment files so all subsequent story tasks have a home to land in.

- [ ] T001 Create `osworld-purple-agent/` directory structure: `src/`, `tests/unit/`, `tests/contract/` per plan.md
- [ ] T002 [P] Create `osworld-purple-agent/pyproject.toml` with Python 3.11+, a2a-sdk, openai-agents[litellm], uvicorn, pydantic, pytest dependencies
- [ ] T003 [P] Create `osworld-purple-agent/.env.example` with all OSWORLD_ prefixed env vars documented per quickstart.md
- [ ] T004 [P] Create `osworld-purple-agent/amber-manifest.json5` with defaults: host=0.0.0.0, port=8000, skill id=osworld_task, provider=litellm
- [ ] T005 [P] Create `osworld-purple-agent/README.md` with project purpose, setup instructions, and env var table from quickstart.md

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core modules that every user story depends on — config loading, LLM provider
abstraction, and A2A message parsing. ALL story work depends on this phase.

**⚠️ CRITICAL**: No user story implementation can begin until this phase is complete.

- [ ] T006 Create `osworld-purple-agent/src/__init__.py` (empty package marker)
- [ ] T007 Create `osworld-purple-agent/tests/__init__.py` and `tests/unit/__init__.py` and `tests/contract/__init__.py` (empty package markers)
- [ ] T008 Create `osworld-purple-agent/src/config.py` — `OsworldConfig` class loading HOST, PORT, LOG_LEVEL, AGENT_NAME, AGENT_VERSION from env vars with defaults per data-model.md
- [ ] T009 Create `osworld-purple-agent/src/llm_provider.py` — copy `purple-agent/src/llm_provider.py` verbatim and change env var prefix from `PURPLE_` to `OSWORLD_`; update default provider to `litellm` per clarification
- [ ] T010 [P] Create `osworld-purple-agent/src/messenger.py` — `parse_step_message(message) -> StepMessage` extracting TextPart/DataPart/FilePart; `build_step_response(reasoning, actions) -> list[Part]` per contracts/a2a-messages.md
- [ ] T011 [P] Add `StepMessage` and `StepResponse` dataclasses to `osworld-purple-agent/src/messenger.py` with field validation rules from data-model.md

**Checkpoint**: Foundation ready — config, LLM provider, and A2A message parsing are all in place

---

## Phase 3: User Story 1 — Runnable A2A Service (Priority: P1) 🎯 MVP

**Goal**: A running A2A HTTP service with a working agent card and end-to-end step cycle
(receive multi-part message → LLM call → return actions).

**Independent Test**: `GET http://localhost:8000/` returns JSON with `skills[0].id == "osworld_task"`;
POST a step message and receive a response with a reasoning TextPart and `{"actions": [...]}` DataPart.

### Implementation for User Story 1

- [ ] T012 [US1] Create `osworld-purple-agent/src/agent.py` — `OsworldAgent` class with `run(step: StepMessage, history: list[dict]) -> StepResponse`; builds multimodal SDK input (text + image_url); calls `Runner.run()`; parses `actions` from output; catches all LLM exceptions and returns `FAIL` per FR-010
- [ ] T013 [US1] Create `osworld-purple-agent/src/executor.py` — `OsworldAgentExecutor(AgentExecutor)` with `sessions: dict[str, list[dict]]` (in-memory history per FR-004); `execute(context, updater)` method: parse message → call agent → append to history → send response via TaskUpdater
- [ ] T014 [US1] Create `osworld-purple-agent/src/server.py` — `AgentCard` with skill id `osworld_task`, `DefaultRequestHandler`, `A2AStarletteApplication`; `app` ASGI object; `main()` entry point calling `uvicorn.run()` with config from `OsworldConfig`
- [ ] T015 [US1] Add `[project.scripts]` entry in `osworld-purple-agent/pyproject.toml`: `osworld-agent = "src.server:main"`

**Checkpoint**: User Story 1 fully functional — `python -m uvicorn src.server:app --port 8000` starts the agent, agent card is reachable, and a synthetic step message receives a valid response

---

## Phase 4: User Story 2 — Multi-Provider LLM Configuration (Priority: P2)

**Goal**: `OSWORLD_LLM_PROVIDER=openai|gemini|litellm` switches provider with zero code changes;
missing/invalid value defaults to `litellm` with a clear log message.

**Independent Test**: Unit tests pass for all three `LLMConfig.from_env()` provider paths without
making real API calls.

### Implementation for User Story 2

- [ ] T016 [P] [US2] Update `osworld-purple-agent/src/agent.py` — wire `setup_llm_client(prefix="OSWORLD_")` at agent init; apply `set_default_openai_client()` for OpenAI/Gemini; pass `LitellmModel` directly as `Agent.model` for LiteLLM per research.md Decision 4
- [ ] T017 [P] [US2] Add provider validation in `osworld-purple-agent/src/llm_provider.py` — invalid `LLM_PROVIDER` value falls back to `litellm` and logs WARNING; missing required API key raises `ValueError` with install instructions per data-model.md LLMProviderConfig error transitions
- [ ] T018 [US2] Create `osworld-purple-agent/tests/unit/test_llm_provider.py` — unit tests for `LLMConfig.from_env()` with all three providers, missing key validation, and invalid provider fallback (no real API calls — mock env vars only)

**Checkpoint**: User Story 2 complete — all three providers load correctly from env vars; unit tests pass; switching provider requires only an env var change

---

## Phase 5: User Story 3 — Docker Build and Deployment (Priority: P3)

**Goal**: `docker build` produces a working image under 2 GB; `docker run` with env vars starts
the agent; image is GHCR-pushable.

**Independent Test**: `docker build -t osworld-purple-agent .` completes; `docker run -p 8000:8000
-e OSWORLD_OPENROUTER_API_KEY=x osworld-purple-agent` starts and serves the agent card.

### Implementation for User Story 3

- [ ] T019 [US3] Create `osworld-purple-agent/Dockerfile` — `python:3.11-slim` base; WORKDIR `/app`; copy `pyproject.toml` + `src/`; `pip install -e .`; EXPOSE 8000; CMD `["python", "-m", "uvicorn", "src.server:app", "--host", "0.0.0.0", "--port", "8000"]`
- [ ] T020 [P] [US3] Create `osworld-purple-agent/.dockerignore` — exclude `.venv/`, `__pycache__/`, `*.pyc`, `tests/`, `.env`, `.git/`

**Checkpoint**: User Story 3 complete — Docker image builds and runs; agent card accessible from host on port 8000

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Contract tests, logging wiring, and final validation to ensure all FRs are met.

- [ ] T021 [P] Create `osworld-purple-agent/tests/unit/test_messenger.py` — unit tests for `parse_step_message()`: valid 5-part message, missing screenshot (text-only fallback), empty instruction fallback, invalid base64 handling; tests for `build_step_response()`: valid actions list, FAIL fallback on empty
- [ ] T022 [P] Create `osworld-purple-agent/tests/contract/test_a2a_schema.py` — validate agent card JSON schema (skill id, inputModes, outputModes); validate step response structure (TextPart + DataPart with `actions` list) per contracts/a2a-messages.md
- [ ] T023 Add structured logging to `osworld-purple-agent/src/executor.py` — INFO: incoming step (instruction[:80], screenshot size in bytes, env_config); INFO: outgoing response (reasoning[:80], action count); DEBUG: full history length, step_count per FR-008 and Constitution Principle VI
- [ ] T024 [P] Add logging configuration in `osworld-purple-agent/src/server.py` `main()` — `logging.basicConfig(level=config.log_level, format=config.log_format)` on startup per `OsworldConfig`

---

## Dependencies

Story completion order (blocking dependencies):

```
Phase 1 (Setup)
  └─→ Phase 2 (Foundation: config, llm_provider, messenger)
        ├─→ Phase 3 (US1: agent, executor, server)  ← MVP deliverable
        ├─→ Phase 4 (US2: multi-provider wiring)     ← depends on Phase 3 agent.py
        └─→ Phase 5 (US3: Docker)                    ← depends on Phase 3 being runnable
              └─→ Phase 6 (Polish: tests + logging)  ← can start after Phase 3
```

**Parallel opportunities per story:**

- Phase 1: T002, T003, T004, T005 all parallel after T001
- Phase 2: T010 and T011 parallel after T008 and T009
- Phase 3: T012, T013, T014 all sequential (strict dependency chain)
- Phase 4: T016 and T017 parallel after T009
- Phase 5: T019 and T020 parallel
- Phase 6: T021, T022, T024 all parallel after Phase 3

---

## Implementation Strategy

**MVP scope** (minimum for Sprint 2 submission, April 12): **Phase 1 + Phase 2 + Phase 3 + Phase 5**

- Produces a Dockerised A2A agent that speaks the OSWorld protocol end-to-end
- Phase 4 (multi-provider wiring) is already partially done inside Phase 3 via `setup_llm_client()`
- Phase 6 (tests + logging) completes quality requirements but is not blocking for Docker submission

**Suggested execution order for a single developer**:

1. T001–T005 (setup, ~30 min)
2. T006–T011 (foundation, ~45 min — config, copy llm_provider, write messenger)
3. T012–T015 (US1 core: agent + executor + server, ~60 min)
4. T019–T020 (Docker, ~20 min)
5. T016–T018 (US2 multi-provider, ~30 min)
6. T021–T024 (polish: tests + logging, ~45 min)

**Total estimate**: ~4 hours to MVP Docker submission, ~5.5 hours for full feature.

---

## Task Count Summary

| Phase | Tasks | Parallelizable | Story |
|-------|-------|----------------|-------|
| Phase 1: Setup | 5 (T001–T005) | 4 | — |
| Phase 2: Foundation | 6 (T006–T011) | 2 | — |
| Phase 3: US1 Runnable A2A | 4 (T012–T015) | 0 | US1 |
| Phase 4: US2 Multi-Provider | 3 (T016–T018) | 2 | US2 |
| Phase 5: US3 Docker | 2 (T019–T020) | 1 | US3 |
| Phase 6: Polish | 4 (T021–T024) | 3 | — |
| **Total** | **24** | **12** | |
