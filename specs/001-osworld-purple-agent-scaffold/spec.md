# Feature Specification: OSWorld Purple Agent — Initial Scaffold

**Feature Branch**: `001-osworld-purple-agent-scaffold`  
**Created**: 2026-04-03  
**Status**: Draft  
**Input**: User description: "initialize the new purple agent, develop the basic structure and configuration and docker things, all basic files and folder structure with initial code also"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Runnable A2A Service (Priority: P1)

A developer clones the repo, sets their LLM API key in an `.env` file, and
starts the new OSWorld purple agent. The agent comes up, registers its
capabilities via an agent card, and is immediately reachable by the OSWorld
green agent over HTTP. One correctly handled step request (receive message →
return actions) proves the scaffold is end-to-end functional.

**Why this priority**: Without a running service that speaks A2A, nothing else
can be built or tested. This is the minimum deliverable that unblocks all
further work.

**Independent Test**: Start the agent locally with a valid API key and call its
agent card endpoint — it returns a JSON document listing the `osworld_task`
skill. Then send a synthetic A2A step message with a screenshot and
instruction text; the agent responds with a reasoning text part and an
`{"actions": [...]}` data part.

**Acceptance Scenarios**:

1. **Given** the agent is started with a valid LLM API key, **When** its
   discovery endpoint is requested, **Then** it returns an agent card
   containing skill id `osworld_task` with input/output mode `message`.
2. **Given** a running agent, **When** a multi-part A2A step message
   (instruction + screenshot + env_config) is sent to it, **Then** the
   agent replies with a text reasoning part and a data part holding an
   `actions` list within 30 seconds.
3. **Given** the agent receives a step with no screenshot part, **When**
   processing the message, **Then** it returns a graceful error response
   rather than crashing.

---

### User Story 2 - Multi-Provider LLM Configuration (Priority: P2)

A developer switches between OpenAI (GPT-4o), Gemini (2.5 Flash), and
LiteLLM (OpenRouter) by changing a single environment variable. No code
change is needed. The agent starts correctly for each provider and processes
a step request.

**Why this priority**: Competition scoring depends on cost-effective model
selection. The ability to swap providers without touching code is a hard
requirement for production use.

**Independent Test**: Start the agent three times, each time with a
different `LLM_PROVIDER` env var value (`openai`, `gemini`, `litellm`). In
each case the agent starts without error and its agent card is reachable.

**Acceptance Scenarios**:

1. **Given** `LLM_PROVIDER=openai` in the environment, **When** the agent
   starts, **Then** it connects via the OpenAI provider and the agent card
   is accessible.
2. **Given** `LLM_PROVIDER=gemini` in the environment, **When** the agent
   starts, **Then** it connects via the Gemini provider using the
   OpenAI-compatible endpoint.
3. **Given** `LLM_PROVIDER=litellm` in the environment, **When** the agent
   starts, **Then** it connects via LiteLLM (e.g., OpenRouter) and the
   agent card is accessible.
4. **Given** an invalid or missing `LLM_PROVIDER` value, **When** the agent
   starts, **Then** it logs a clear error message and exits rather than
   starting in a broken state.

---

### User Story 3 - Docker Build and Deployment (Priority: P3)

A developer builds the Docker image with a single `docker build` command and
runs it with environment variables passed via `docker run`. The agent starts
inside the container and is reachable on the configured port. The image is
suitable for pushing to GHCR for competition submission.

**Why this priority**: AgentBeats competition submission requires a
GHCR-hosted Docker image. Without a working Dockerfile the agent cannot be
submitted.

**Independent Test**: Run `docker build -t osworld-purple-agent .` from the
agent directory — it completes without error. Run the container with an LLM
API key env var and confirm the agent card endpoint is reachable from the
host.

**Acceptance Scenarios**:

1. **Given** the agent directory with a `Dockerfile`, **When** `docker build`
   is executed, **Then** it completes successfully and produces an image
   under 2 GB.
2. **Given** a built image, **When** `docker run` is executed with LLM
   credentials as env vars, **Then** the agent starts and responds to the
   agent card request on the exposed port.
3. **Given** a running container, **When** the OSWorld green agent sends it
   a step message, **Then** the container processes it and returns valid
   actions just as it would locally.

---

### Edge Cases

- If the screenshot FilePart contains invalid or empty base64 data, the
  agent logs a warning and proceeds with text-only context.
- If the LLM times out, returns an empty response, or raises an API error,
  the agent returns `{"actions": ["FAIL"]}` with an error reasoning text part.
- If a step message arrives for an unknown `context_id`, a new empty history
  is initialised for that session.
- If no env vars are provided, the agent logs a clear startup error and exits
  with a non-zero code.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The agent MUST expose an A2A-compliant HTTP endpoint on port
  `8000` (configurable via env var) that returns an agent card with skill id
  `osworld_task`.
- **FR-002**: The agent MUST accept multi-part A2A step messages containing
  at minimum a text instruction and a screenshot image part.
- **FR-003**: The agent MUST respond to each step with a text reasoning part
  and a data part containing an `actions` list of pyautogui command strings
  or the special values `WAIT`, `DONE`, or `FAIL`.
- **FR-004**: The agent MUST maintain separate conversation history per
  `context_id` using an in-memory dict (keyed by `context_id`, cleared on
  restart) so multi-step tasks within a single evaluation session are coherent.
- **FR-005**: The agent MUST support three LLM backend providers selectable
  entirely via environment variables, with no code changes required. When
  `LLM_PROVIDER` is unset, the agent MUST default to `litellm`.
- **FR-006**: The agent MUST be runnable as a Docker container, exposing its
  HTTP port, with all secrets passed as environment variables.
- **FR-007**: The agent MUST provide an `.env.example` file listing all
  required and optional environment variables with documentation.
- **FR-008**: The agent MUST log each incoming step (instruction text,
  screenshot size, env config) and each outgoing response (reasoning
  summary, action count) at a level sufficient for post-hoc debugging.
- **FR-009**: The agent MUST start and pass its agent card health check
  within 10 seconds of container start.
- **FR-010**: When the LLM call fails for any reason (timeout, rate limit,
  API error), the agent MUST return a response with a descriptive error
  reasoning text part and `{"actions": ["FAIL"]}` — it MUST NOT crash or
  hang the evaluation session.

### Key Entities

- **Step Message**: A single evaluation step from the green agent —
  contains the task instruction, current screenshot, and optionally
  accessibility tree and terminal output.
- **Step Response**: The agent's reply to one step — contains LLM reasoning
  text and a list of desktop actions to execute.
- **Evaluation Session**: A series of step messages sharing the same
  `context_id`, representing one complete task attempt (up to 15 steps).
- **LLM Provider Config**: The set of environment variables that select and
  authenticate a specific LLM backend for model inference.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The agent card endpoint responds within 3 seconds of the
  service starting.
- **SC-002**: The agent correctly parses and acknowledges all five A2A
  message part types — instruction text, env config, screenshot, accessibility
  tree, terminal — within a single step cycle.
- **SC-003**: A full step cycle (receive message → call LLM → return actions)
  completes in under 30 seconds for a typical screenshot and instruction.
- **SC-004**: The Docker image builds in under 5 minutes on a standard
  developer machine and runs the agent without additional setup.
- **SC-005**: Switching LLM providers (by changing one env var) takes under
  1 minute and requires zero edits to source files.
- **SC-006**: All three LLM providers start and process at least one step
  without errors when valid credentials are supplied.

## Clarifications

### Session 2026-04-03

- Q: What should the top-level directory for the new OSWorld purple agent be named? → A: `osworld-purple-agent/`
- Q: How should the agent manage per-context conversation history between steps? → A: In-memory dict keyed by `context_id`, cleared on process restart
- Q: What port should the OSWorld purple agent listen on by default? → A: port `8000`
- Q: Which LLM provider should be used as the default when `LLM_PROVIDER` is not set? → A: `litellm`
- Q: When the LLM call fails mid-step, what should the agent return? → A: `{"actions": ["FAIL"]}` with an error reasoning text part

## Assumptions

- The OSWorld green agent is running separately (Docker or local) on port
  9009 and is not in scope for this feature.
- The existing `purple-agent/src/llm_provider.py` module will be copied and
  adapted — it is the authoritative pattern for multi-provider LLM support.
- The new agent lives in `osworld-purple-agent/` at the repository root,
  separate from the existing `purple-agent/` directory.
- `amber-manifest.json5` default config: host `0.0.0.0`, port `8000`,
  skill id `osworld_task`, default LLM provider `litellm`.
- Vision-capable models (GPT-4o, Gemini 2.5 Flash, or equivalent) are
  assumed to be configured by the user — the scaffold does not enforce a
  specific model but documents this requirement.
- Initial code is functional scaffolding: the LLM interaction in `agent.py`
  will pass the screenshot and instruction to the model and return whatever
  the model outputs parsed as actions. Full prompt engineering is out of
  scope for this scaffold feature.
