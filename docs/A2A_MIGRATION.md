# Purple Agent A2A Server Migration

## Changes Made

### 1. Purple Agent is Now an A2A Server
**Before**: Purple Agent was A2A client-only (polled Green Agent)  
**After**: Purple Agent runs as A2A server, receives messages from Green Agent

### 2. New Components

#### `src/purple_agent/executor.py`
- Implements `AgentExecutor` interface per A2A SDK
- Handles incoming messages from Green Agent
- Extracts task details and MCP connection info
- Executes evaluation using OpenAI Agents SDK
- Sends results back via event queue

#### `src/purple_agent/agent_card.py`
- Defines Purple Agent capabilities and skills
- Provides agent discovery endpoint

#### `src/purple_agent/main.py` (Refactored)
- Now runs Uvicorn A2A server (not client)
- Port 9010 by default (configurable)
- Endpoints:
  - `/.well-known/agent.json` - Agent card
  - `/health` - Health check
  - `/` - A2A protocol endpoints

### 3. Green Agent Updates

#### `src/green_agent/agent/tools/communication_tools.py`
- `send_mcp_details_to_purple_agent()` now sends A2A message TO Purple Agent
- Uses A2A client to connect to Purple Agent server
- Sends task assignment + MCP details in single message

## Running the System

### Start Servers

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
.\.venv\Scripts\python.exe scripts/run_mcp_server_standalone.py
```

### Test Communication

Send evaluation request to Green Agent (it will forward task to Purple Agent):

```powershell
# Use Green Agent's A2A endpoint
$body = @{
    jsonrpc = "2.0"
    id = "test-123"
    method = "message/send"
    params = @{
        message = @{
            role = "user"
            parts = @(
                @{
                    kind = "data"
                    data = @{
                        participants = @{
                            purple_agent = "http://127.0.0.1:9010/"
                        }
                        config = @{
                            task_id = "miniwob.click-test"
                            benchmark = "miniwob"
                        }
                    }
                }
            )
            messageId = "msg-123"
        }
    }
} | ConvertTo-Json -Depth 10

Invoke-RestMethod -Uri "http://localhost:9009/" -Method POST -Body $body -ContentType "application/json"
```

## Architecture Flow

```
┌──────────────────┐                      ┌──────────────────┐
│   Green Agent    │                      │  Purple Agent    │
│  (A2A Server)    │                      │  (A2A Server)    │
│   Port 9009      │                      │   Port 9010      │
└────────┬─────────┘                      └────────┬─────────┘
         │                                         │
         │  1. Receives task from kickstart        │
         │     or external client                  │
         │                                         │
         │  2. Spawns MCP server (port 8001)       │
         │                                         │
         │  3. Sends A2A message TO Purple ────────►│
         │     with task + MCP details             │
         │                                         │
         │                         4. Purple connects to MCP,
         │                            executes task via tools
         │                                         │
         │  5. Purple sends result back ◄──────────│
         │     (via A2A response)                  │
         │                                         │
         │  6. Green generates artifact            │
         │                                         │
```

## Key Differences

| Aspect | Old (Client-Only) | New (Bidirectional A2A) |
|--------|------------------|-------------------------|
| Purple Agent | Client polling Green | **Server** receiving messages |
| Communication | Purple initiates | Green initiates to Purple |
| `submit_evaluation_request` | Used | **Removed** |
| Message Flow | One-shot request/response | Full A2A protocol streaming |
| Discovery | None | `/.well-known/agent.json` |

## Migration Benefits

✅ **Standards Compliant**: Follows official A2A protocol  
✅ **AgentBeats Compatible**: Matches AgentBeats architecture  
✅ **Bidirectional**: Both agents can send/receive messages  
✅ **Scalable**: Supports multiple Purple Agents  
✅ **Production-Ready**: Uses official A2A SDK patterns
