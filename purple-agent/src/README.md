# Test Purple Agent

Minimal reference implementation of a Purple Agent using OpenAI Agents SDK for integration testing with the BrowserGym Green Agent.

## Overview

This test purple agent demonstrates:
- **A2A Protocol**: Communication with Green Agent via Agent-to-Agent protocol
- **MCP Client**: Using Green Agent's MCP tools for BrowserGym environment interaction
- **Agentic Orchestration**: Task execution with Gemini 2.5 Flash and OpenAI Agents SDK
- **Complete Flow**: Evaluation request → task execution → artifact submission

**⚠️ Note**: This is a **minimal test agent** for integration validation, not a production-ready implementation. It demonstrates the integration pattern but is not optimized for task performance.

## Features

- **5 Agent Tools**: MCP connection, observation retrieval, action execution, observation parsing, action generation
- **Gemini 2.5 Flash LLM**: Cost-effective model ($0.001-0.05/eval) with temperature=0.3
- **Langfuse Tracing**: Optional observability for agent reasoning and tool calls
- **Error Handling**: 3-retry MCP connection with exponential backoff, 30s tool timeouts
- **Configurable**: Environment variables for all settings (no hardcoded values)

## Requirements

- Python 3.11+
- OpenAI Agents SDK (v0.2.9+)
- MCP Python SDK
- httpx (for A2A communication)
- Langfuse (optional, for tracing)

## Installation

```bash
# Install dependencies (already included in main pyproject.toml)
pip install -e .

# Or install separately
pip install "openai-agents-python @ git+https://github.com/openai/openai-agents-python.git@v0.2.9"
pip install mcp httpx langfuse
```

## Configuration

All configuration via environment variables:

### Required
- `GREEN_AGENT_URL`: Green Agent base URL (default: `http://localhost:9009`)
- `GEMINI_API_KEY`: Google Gemini API key

### Optional
- `GEMINI_BASE_URL`: Gemini API base URL (default: OpenAI-compatible endpoint)
- `GEMINI_MODEL`: LLM model (default: `gemini-2.5-flash`)
- `GEMINI_TEMPERATURE`: Sampling temperature (default: `0.3`)
- `GEMINI_MAX_ITERATIONS`: Max agent iterations (default: `20`)
- `DEFAULT_TIMEOUT`: Default timeout in seconds (default: `300`)
- `MCP_CONNECTION_TIMEOUT`: MCP connection timeout (default: `30`)
- `MCP_CONNECTION_RETRIES`: MCP connection retries (default: `3`)
- `LANGFUSE_PUBLIC_KEY`: Langfuse public key (optional)
- `LANGFUSE_SECRET_KEY`: Langfuse secret key (optional)
- `LANGFUSE_HOST`: Langfuse host URL (optional)

## Usage

### Command Line

```bash
# Run single evaluation
python -m tests.purple_agent.main \
    --task-id miniwob.click-test \
    --benchmark miniwob \
    --timeout 120

# With task description
python -m tests.purple_agent.main \
    --task-id miniwob.click-test \
    --benchmark miniwob \
    --task-description "Click the button with bid 12" \
    --timeout 120
```

### Integration Test

```bash
# Linux/macOS
bash tests/integration/test_purple_agent_integration.sh

# Windows PowerShell
.\tests\integration\test_purple_agent_integration.ps1
```

### Programmatic Usage

```python
from tests.purple_agent.main import run_evaluation

# Run evaluation
result = await run_evaluation(
    task_id="miniwob.click-test",
    benchmark="miniwob",
    task_description="Click the button",
    timeout=120
)

print(f"Status: {result['status']}")
print(f"Artifact: {result['artifact']}")
```

## Architecture

### Components

1. **A2A Client** (`a2a_client.py`): Submits evaluation requests, subscribes to SSE events, extracts MCP connection details
2. **Agent Factory** (`agent/agent_factory.py`): Creates agent with 5 tools, Gemini LLM, Langfuse tracing
3. **Agent Context** (`agent/context.py`): Pydantic model with task info, MCP connection, session state
4. **MCP Tools** (`tools/mcp_tools.py`): 3 MCP client tools (connect, observe, act)
5. **Utilities** (`tools/observation_parser.py`, `tools/action_generator.py`): Parse observations, generate actions

### Workflow

```
1. Submit evaluation request to Green Agent via A2A
2. Subscribe to SSE events to receive MCP connection details
3. Connect to Green Agent's MCP server (stdio subprocess)
   - NOTE: Environment is already initialized by Green Agent on MCP startup
4. Loop:
   a. Get observation (HTML, AXTree, done, reward) - environment ready immediately
   b. Parse observation (extract clickable elements, input fields)
   c. Generate action (click, type based on task)
   d. Execute action via MCP
   e. Check if done=True or reward received
5. Task completes - Green Agent automatically handles cleanup
6. Submit artifact to Green Agent
```

### Agent Tools

| Tool | Purpose | MCP/Local | Notes |
|------|---------|-----------|-------|
| `connect_to_mcp_server` | Establish MCP stdio connection | Local | |
| `mcp_get_observation` | Get current observation | MCP | Use immediately after connection |
| `mcp_execute_action` | Execute browser action | MCP | |
| `parse_observation_for_actions` | Extract actionable elements | Local | |
| `generate_action_from_analysis` | Generate action dict | Local | |

## Example Tasks

### MiniWoB Click Test

```bash
python -m tests.purple_agent.main \
    --task-id miniwob.click-test \
    --benchmark miniwob
```

Agent workflow:
1. Connect to MCP (environment already initialized by Green Agent)
2. Get observation, parse AXTree for button with specific bid
3. Generate click action: `{"action_type": "click", "bid": "12"}`
4. Execute action, observe result (done=True, reward=1.0)
5. Task completes - Green Agent handles cleanup automatically

### MiniWoB Navigation

```bash
python -m tests.purple_agent.main \
    --task-id miniwob.click-link \
    --benchmark miniwob
```

Agent workflow:
1. Parse observation for link elements
2. Identify target link by label
3. Click link with corresponding bid
4. Verify navigation success

## Troubleshooting

### MCP Connection Timeout

**Error**: "Timeout waiting for MCP connection details"

**Solution**:
- Verify Green Agent is running: `curl http://localhost:9009/health`
- Check Green Agent logs for MCP server startup
- Increase `MCP_CONNECTION_TIMEOUT` (default: 30s)

### Agent Exceeds Max Iterations

**Error**: "Agent exceeded max iterations"

**Solution**:
- Increase `GEMINI_MAX_ITERATIONS` (default: 20)
- Simplify task or provide clearer task description
- Check agent reasoning in Langfuse traces

### Gemini API Key Invalid

**Error**: "Authentication failed"

**Solution**:
- Set valid `GEMINI_API_KEY` environment variable
- Verify API key has access to gemini-2.5-flash model
- Check `GEMINI_BASE_URL` is correct

### No Clickable Elements Found

**Error**: "Failed to find clickable elements"

**Solution**:
- Check observation parser regex patterns in `observation_parser.py`
- Verify AXTree format matches expected structure
- Add debug logging to see raw AXTree content

## Development

### Running Tests

```bash
# Unit tests
pytest tests/purple_agent/test_*.py -v

# Integration test
bash tests/integration/test_purple_agent_integration.sh
```

### Adding New Tools

```python
from agents import function_tool
from langfuse.decorators import observe

@function_tool
@observe(name="custom_tool")
async def my_custom_tool(ctx, param1: str):
    """Tool description for agent."""
    context = ctx.context
    # Tool implementation
    return {"result": "success"}

# Add to PURPLE_AGENT_TOOLS in agent_factory.py
```

### Custom LLM Configuration

```python
from tests.purple_agent.agent import create_test_purple_agent
from tests.purple_agent.config import PurpleAgentConfig

config = PurpleAgentConfig()
config.gemini_model = "gemini-2.0-flash-exp"
config.gemini_temperature = 0.5
config.gemini_max_iterations = 30

agent = create_test_purple_agent(config)
```

## Limitations

This is a **minimal test agent** with intentional limitations:

- **No task-specific optimization**: Generic click/type strategy, no domain knowledge
- **Limited observation parsing**: Simple regex patterns, not robust to AXTree variations
- **No planning/reasoning**: Reactive agent, no multi-step planning
- **No memory**: No history of previous actions or observations
- **Single-benchmark focus**: Optimized for MiniWoB, not WebArena/WorkArena
- **No error recovery**: Basic retry logic, no sophisticated error handling

For production purple agents, consider:
- Task-specific prompting and domain knowledge
- Advanced observation preprocessing (vision models, HTML parsing)
- Multi-step planning with reasoning traces
- Session memory and context accumulation
- Benchmark-specific optimization
- Robust error recovery and fallback strategies

## License

Same as main project (see root LICENSE file).

## Contact

For questions or issues, refer to main project documentation or open an issue.
