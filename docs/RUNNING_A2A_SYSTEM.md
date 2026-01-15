# Running A2A Evaluation System

## The Issue You're Experiencing

Both agents are running as **servers**, waiting for incoming requests. They won't communicate until someone sends the **initial trigger** to Green Agent.

Think of it like this:
- 🟢 Green Agent (port 9009) = waiting for evaluation requests
- 🟣 Purple Agent (port 9010) = waiting for task assignments
- 🔧 MCP Server (port 8001) = waiting for tool calls

**No one has told Green Agent to start an evaluation yet!**

## Solution: Send Initial Request

Use the test script to trigger the flow:

```powershell
# Make sure all 3 servers are running first:
# Terminal 1: Green Agent
# Terminal 2: Purple Agent  
# Terminal 3: MCP Server

# Terminal 4: Trigger the evaluation
.\.venv\Scripts\python.exe scripts\test_a2a_flow.py
```

## Complete Setup Instructions

### Step 1: Start All Servers

**Terminal 1 - Green Agent:**
```powershell
.\.venv\Scripts\python.exe -m src.green_agent.main --port 9009
```

**Terminal 2 - Purple Agent:**
```powershell
.\.venv\Scripts\python.exe -m src.purple_agent.main --port 9010
```

**Terminal 3 - MCP Server:**
```powershell
.\.venv\Scripts\python.exe scripts\run_mcp_server_standalone.py
```

Wait until you see these messages:
- ✅ Green Agent: "Starting BrowserGym Green Agent A2A server"
- ✅ Purple Agent: "Purple Agent ready to receive tasks from Green Agent"
- ✅ MCP Server: "Uvicorn running on http://0.0.0.0:8001"

### Step 2: Trigger Evaluation

**Terminal 4 - Send Request:**
```powershell
.\.venv\Scripts\python.exe scripts\test_a2a_flow.py
```

This sends an evaluation request to Green Agent with:
- Task: `miniwob.click-test`
- Purple Agent URL: `http://127.0.0.1:9010/`

### Step 3: Watch the Flow

You should see this sequence in the logs:

**Green Agent Terminal:**
```
✓ Received A2A assessment request
✓ Creating agent orchestration...
✓ MCP server prepared: http://localhost:8001/mcp
✓ Connecting to Purple Agent at http://127.0.0.1:9010/
✓ Task assignment sent to Purple Agent
```

**Purple Agent Terminal:**
```
✓ Received A2A message from Green Agent
✓ Extracted task info: task_id=miniwob.click-test
✓ Creating Purple Agent with OpenAI Agents SDK...
✓ Starting agent execution...
```

**MCP Server Terminal:**
```
✓ Tool called: initialize_environment
✓ Tool called: get_observation
✓ Tool called: execute_actions
✓ Tool called: cleanup_environment
```

## Customizing the Request

```powershell
# Different task
.\.venv\Scripts\python.exe scripts\test_a2a_flow.py --task-id miniwob.click-button --benchmark miniwob

# Different ports
.\.venv\Scripts\python.exe scripts\test_a2a_flow.py --green-url http://localhost:9009/ --purple-url http://localhost:9010/
```

## Troubleshooting

### "Could not connect to Green Agent"
**Solution:** Make sure Green Agent is running on port 9009

### "Purple Agent URL not configured"
**Solution:** Check that you're passing `purple_agent` in the participants field

### "MCP server not healthy"
**Solution:** Make sure MCP server is running on port 8001

### Green Agent starts but doesn't send to Purple
**Problem:** You haven't triggered the evaluation  
**Solution:** Run `scripts\test_a2a_flow.py`

### Agents are running but nothing happens
**Problem:** Both agents are servers - they need an initial request  
**Solution:** The test script sends the initial request that starts everything

## How It Works

```
┌─────────────────────────────────────────────────────────────┐
│  Step 1: You run test_a2a_flow.py                          │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
          ┌──────────────────────┐
          │    Green Agent       │  Receives evaluation request
          │    (A2A Server)      │  with Purple Agent URL
          └──────────┬───────────┘
                     │
                     ▼
          ┌──────────────────────┐
          │  Green Agent calls:  │  1. initialize_evaluation()
          │  Agent Tools         │  2. send_mcp_details_to_purple_agent()
          └──────────┬───────────┘
                     │
                     ▼
          ┌──────────────────────┐
          │  Green → Purple      │  Sends A2A message TO Purple
          │  (A2A Client)        │  with task + MCP details
          └──────────┬───────────┘
                     │
                     ▼
          ┌──────────────────────┐
          │   Purple Agent       │  Receives message, extracts
          │   (A2A Server)       │  task and MCP connection info
          └──────────┬───────────┘
                     │
                     ▼
          ┌──────────────────────┐
          │  Purple Agent runs   │  Uses proxy tools to:
          │  OpenAI Agents SDK   │  - connect_to_mcp
          └──────────┬───────────┘  - call_mcp_tool
                     │              - disconnect_mcp
                     ▼
          ┌──────────────────────┐
          │   MCP Server         │  Executes BrowserGym actions
          │   (Port 8001)        │  
          └──────────┬───────────┘
                     │
                     ▼
          ┌──────────────────────┐
          │  Purple → Green      │  Sends result back
          │  (A2A Response)      │  
          └──────────┬───────────┘
                     │
                     ▼
          ┌──────────────────────┐
          │   Green Agent        │  Generates final artifact
          │   Completes Task     │  
          └──────────────────────┘
```

## Quick Test

To verify everything is working:

```powershell
# Run this after all servers are up
.\.venv\Scripts\python.exe scripts\test_a2a_flow.py
```

Expected output:
```
🚀 Triggering A2A Evaluation Flow
══════════════════════════════════════════════════════════════════
Green Agent:  http://127.0.0.1:9009/
Purple Agent: http://127.0.0.1:9010/
Task:         miniwob.click-test (miniwob)
══════════════════════════════════════════════════════════════════

📤 Sending request to Green Agent...
✓ Response received: HTTP 200

✅ Task Created: <task-id>
   Status: submitted

🔄 Green Agent is now:
   1. Initializing MCP server (port 8001)
   2. Calling send_mcp_details_to_purple_agent tool
   3. Sending A2A message TO Purple Agent with:
      - Task assignment (task_id, benchmark)
      - MCP connection details (URL, transport)

🟣 Purple Agent will:
   1. Receive A2A message from Green Agent
   2. Extract task and MCP details
   3. Connect to MCP server
   4. Execute task using proxy tools
   5. Send result back to Green Agent

👀 Check the agent terminal logs to see the flow!
```
