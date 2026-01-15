# Langfuse Tracing Setup and Troubleshooting Guide

## Overview

This project uses **Langfuse** for tracing OpenAI Agents SDK operations with **unified trace context** across both Green and Purple agents. Tracing allows you to:
- Monitor entire assessment flow in a single trace
- See both Green Agent (orchestrator) and Purple Agent (executor) operations together  
- Debug tool calls and agent decisions step-by-step
- Track token usage and latency across the full workflow
- Analyze multi-agent workflows with complete visibility

## Unified Tracing Architecture

The assessment flow uses a **single unified trace** that spans the entire workflow:

```
┌─────────────────────────────────────────────────────────────────┐
│  Kickstart Script (scripts/kickstart_assessment.py)             │
│  ├── Starts top-level trace: "BrowserGym-Assessment"            │
│  ├── Trace ID: {task_id} (e.g., "miniwob.click-test")           │
│  └── Metadata: task, benchmark, timeout, headless mode          │
└─────────────────────────────────────────────────────────────────┘
                             │
                ┌────────────┴────────────┐
                │                         │
                ▼                         ▼
┌─────────────────────────────┐  ┌─────────────────────────────┐
│  Green Agent (Orchestrator) │  │  Purple Agent (Executor)    │
│  ├── Span: "GreenAgent-*"  │  │  ├── Span: "PurpleAgent-*"  │
│  ├── MCP server spawn       │  │  ├── MCP client connection  │
│  ├── A2A message handling   │  │  ├── Environment init       │
│  ├── Monitoring evaluation  │  │  ├── Tool executions        │
│  └── Artifact generation    │  │  └── Task completion        │
└─────────────────────────────┘  └─────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  Langfuse Dashboard: Single Unified Trace                       │
│  ├── Top-level: "Assessment: miniwob.click-test"                │
│  ├── └─ Green Agent operations (spawn MCP, monitor, artifact)   │
│  └── └─ Purple Agent operations (connect, execute, cleanup)     │
└─────────────────────────────────────────────────────────────────┘
```

### How It Works

1. **Kickstart Script** starts assessment and creates top-level trace with `langfuse.start_as_current_span()`
2. **Trace ID Propagation**: Task ID is passed to both agents via `ASSESSMENT_TRACE_ID` environment variable  
3. **Green Agent** reads trace ID and links its operations to the parent trace
4. **Purple Agent** reads trace ID and links its operations to the parent trace
5. **OpenInference** automatically captures all agent tool calls and LLM interactions
6. **Langfuse** displays everything in a single unified trace timeline

## Quick Setup

### 1. Get Langfuse Credentials

1. Sign up for free at [Langfuse Cloud](https://cloud.langfuse.com/)
2. Create a new project (or use existing one)
3. Go to **Project Settings** → **API Keys**
4. Copy your:
   - `LANGFUSE_PUBLIC_KEY` (starts with `pk-lf-...`)
   - `LANGFUSE_SECRET_KEY` (starts with `sk-lf-...`)

### 2. Configure Environment Variables

Create a `.env` file in the project root (or copy from `.env.example`):

```bash
# Required for tracing
LANGFUSE_PUBLIC_KEY=pk-lf-your-key-here
LANGFUSE_SECRET_KEY=sk-lf-your-secret-here
LANGFUSE_HOST=https://cloud.langfuse.com  # EU region
LANGFUSE_ENABLED=true

# LLM Provider (example: Gemini)
LLM_PROVIDER=gemini
GEMINI_API_KEY=your-gemini-api-key
GEMINI_MODEL=gemini-2.5-flash
```

### 3. Run Your Agent

```powershell
# Test Purple Agent
python scripts/kickstart_assessment.py --task miniwob.click-test

# The agents will now report tracing status on startup:
# ✓ Purple Agent: Langfuse client is authenticated and ready!
# ✓ Green Agent: Langfuse client is authenticated and ready!
```

### 4. View Traces in Langfuse

1. Go to [https://cloud.langfuse.com/](https://cloud.langfuse.com/)
2. Select your project
3. Click **Traces** in the sidebar
4. You'll see traces for:
   - `BrowserGymEvaluator` (Green Agent)
   - `TestPurpleAgent` (Purple Agent)

## Architecture

### How Tracing Works

```
┌─────────────────────────────────────────────────────────────────┐
│  OpenAI Agents SDK (Green & Purple Agents)                      │
│  ├── Agent execution (Runner.run)                               │
│  ├── Tool calls (@function_tool decorated functions)            │
│  └── LLM calls (OpenAI client with Gemini/OpenAI/etc.)          │
└─────────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  OpenInference Instrumentation                                   │
│  ├── Captures spans automatically (agent runs, tool calls)      │
│  └── Converts to OpenTelemetry format                           │
└─────────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  Langfuse Client (get_client())                                  │
│  ├── Receives OTel spans from OpenInference                     │
│  ├── Enriches with metadata (user_id, session_id, tags)         │
│  └── Sends to Langfuse Cloud/Self-hosted                        │
└─────────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  Langfuse Dashboard                                              │
│  ├── Traces: Full agent execution timeline                      │
│  ├── Generations: LLM calls with prompts/completions            │
│  ├── Spans: Tool calls, function executions                     │
│  └── Metrics: Token usage, latency, costs                       │
└─────────────────────────────────────────────────────────────────┘
```

### Code Changes Made

#### Green Agent (`src/green_agent/agent/agent_factory.py`)

```python
from langfuse import get_client

# Initialize Langfuse client
langfuse = get_client()
if langfuse.auth_check():
    logger.info("✓ Green Agent: Langfuse authenticated!")
```

#### Purple Agent (`src/purple_agent/agent/agent_factory.py`)

```python
from langfuse import get_client

# Initialize Langfuse client
langfuse = get_client()
if langfuse.auth_check():
    logger.info("✓ Purple Agent: Langfuse authenticated!")
```

## Troubleshooting

### Issue 1: "Langfuse authentication failed"

**Symptom**: Log message shows `⚠ Langfuse authentication failed. Check your credentials.`

**Solution**:
1. Verify your `.env` file has correct keys:
   ```bash
   LANGFUSE_PUBLIC_KEY=pk-lf-...  # Must start with pk-lf-
   LANGFUSE_SECRET_KEY=sk-lf-...  # Must start with sk-lf-
   ```
2. Check that you're using the correct region:
   - EU: `https://cloud.langfuse.com`
   - US: `https://us.cloud.langfuse.com`
3. Ensure the `.env` file is in the project root (same directory as `pyproject.toml`)
4. Restart the agents after updating `.env`

### Issue 2: "No traces appearing in Langfuse"

**Symptom**: Agents run successfully, authentication passes, but no traces appear in dashboard.

**Solution**:
1. **Check Langfuse is enabled**:
   ```bash
   LANGFUSE_ENABLED=true  # Not "false"
   ```

2. **Verify the agent ran long enough to call the LLM**:
   - Traces are created when the agent makes LLM calls
   - If the agent exits immediately (e.g., error), no trace is sent

3. **Check network connectivity**:
   - Ensure your machine can reach `cloud.langfuse.com`
   - Check firewall/proxy settings

4. **Wait a few seconds**:
   - Traces are sent asynchronously
   - Refresh the Langfuse dashboard after 5-10 seconds

### Issue 3: "Failed to initialize Langfuse client"

**Symptom**: Log shows `⚠ Failed to initialize Langfuse client: <error>`

**Solution**:
1. **Missing langfuse package**:
   ```bash
   pip install langfuse
   ```

2. **Import error**:
   - Ensure you're using the project's virtual environment:
     ```powershell
     .\.venv\Scripts\Activate.ps1  # Windows
     source .venv/bin/activate      # Linux/macOS
     ```

3. **Version mismatch**:
   ```bash
   pip install --upgrade langfuse openinference-instrumentation-openai-agents
   ```

### Issue 4: "Traces missing tool calls or agent details"

**Symptom**: Traces appear but don't show tool executions or agent reasoning.

**Solution**:
1. **Ensure OpenInference instrumentation is initialized BEFORE agent creation**:
   - This is already done in `agent_factory.py` at module level:
     ```python
     OpenAIAgentsInstrumentor().instrument()  # Before any agents are created
     ```

2. **Check tool decorators**:
   - All tools must use `@function_tool` decorator
   - Already done for all 7 Purple Agent tools and 10 Green Agent tools

3. **Verify LLM client configuration**:
   - The OpenAI client must be configured before `get_client()` is called
   - Already handled in the factory functions

## Advanced Configuration

### Blocking A2A SDK Spans (Recommended)

The A2A SDK emits very granular OpenTelemetry spans (event queues, consumers, request handlers). These can overwhelm traces.

This project **blocks A2A instrumentation scopes by default** when tracing is enabled. You can override the block list via:

```bash
LANGFUSE_BLOCKED_INSTRUMENTATION_SCOPES=a2a,a2a.server,a2a.client,a2a.server.events,a2a.server.events.event_queue,a2a.server.events.event_consumer,a2a.server.request_handlers,a2a.server.request_handlers.default_request_handler
```

If you set this variable, it will be applied to both Green and Purple agents (and the kickstart orchestrator) via the shared settings.

### Custom Trace Metadata

You can enrich traces with custom metadata:

```python
from agents import trace

with trace("Custom Workflow", user_id="user_123", tags=["production"]):
    result = await Runner.run(agent, input_text, context=context)
```

### Grouping Multiple Agent Runs

```python
with trace("Batch Evaluation"):
    for task in tasks:
        result = await Runner.run(agent, task, context=context)
```

### Linking Langfuse Prompts

If you manage prompts in Langfuse Prompt Management, you can link them to traces. See the [Langfuse documentation](https://langfuse.com/integrations/frameworks/openai-agents#link-langfuse-prompt) for details.

## Testing Your Setup

### Minimal Test Script

Create `test_tracing.py`:

```python
import asyncio
from agents import Agent, Runner
from openinference.instrumentation.openai_agents import OpenAIAgentsInstrumentor
from langfuse import get_client

# Initialize tracing
OpenAIAgentsInstrumentor().instrument()
langfuse = get_client()

if langfuse.auth_check():
    print("✓ Langfuse authenticated!")
else:
    print("✗ Langfuse authentication failed")
    exit(1)

# Create simple agent
agent = Agent(name="TestAgent", instructions="You only respond in haikus.")

# Run agent
async def main():
    result = await Runner.run(agent, "Tell me about Python")
    print(result.final_output)

asyncio.run(main())
```

Run it:
```bash
python test_tracing.py
```

Check Langfuse dashboard for a trace named "TestAgent".

## Resources

- **Langfuse Docs**: [https://langfuse.com/integrations/frameworks/openai-agents](https://langfuse.com/integrations/frameworks/openai-agents)
- **OpenInference**: [https://github.com/Arize-ai/openinference/tree/main/python/instrumentation/openinference-instrumentation-openai-agents](https://github.com/Arize-ai/openinference/tree/main/python/instrumentation/openinference-instrumentation-openai-agents)
- **OpenAI Agents SDK**: [https://openai.github.io/openai-agents-python/](https://openai.github.io/openai-agents-python/)

## Support

If you continue to have issues:
1. Enable debug logging:
   ```bash
   LOG_LEVEL=DEBUG
   LANGFUSE_DEBUG=true
   ```
2. Check the logs in `logs/green_agent.log` and `logs/purple_agent.log`
3. Visit the [Langfuse Discord](https://discord.gg/7NXusRtqYU) for community support
