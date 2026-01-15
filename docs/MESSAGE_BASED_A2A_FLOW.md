# Message-Based A2A Flow - Architecture Update

## Problem Statement

The original Purple Agent implementation treated A2A like a REST API:
- Sent evaluation request with task details
- Expected immediate synchronous response with MCP connection details
- Pre-populated agent context with MCP details before running LLM

This violated the A2A protocol's message-based nature where:
- Green Agent sends MCP details via async A2A messages
- Purple Agent LLM should process incoming messages
- Tools extract needed information from message stream

## Solution: Message-Driven Architecture

### Changes Made

#### 1. Purple Agent Context (`src/purple_agent/agent/context.py`)
**Added:**
```python
# A2A Message Handling
incoming_messages: list[dict[str, Any]] = Field(
    default_factory=list,
    description="Incoming A2A messages from Green Agent (contains MCP details, task info, etc.)"
)
```

**Purpose:** Store all incoming A2A messages for agent tools to process

#### 2. Agent Instructions (`src/purple_agent/agent/instructions.py`)
**Updated:** Clarified that:
- Agent receives messages from Green Agent
- `connect_to_mcp_server` tool automatically extracts MCP details
- LLM doesn't need to manually parse messages

#### 3. MCP Connection Tool (`src/purple_agent/tools/mcp_tools.py`)
**Enhanced:** `connect_to_mcp_server` now:
1. Checks `context.mcp_connection_details` (backward compatibility)
2. If not present, searches `context.incoming_messages` for MCP details
3. Extracts from multiple possible locations:
   - Direct message with `command` and `transport` fields
   - Nested in `data` field
   - Explicit `mcp_connection_details` field

#### 4. A2A Client (`src/purple_agent/a2a_client.py`)
**Enhanced:** `submit_evaluation_request` now:
- Collects ALL incoming messages (not just extracts MCP details)
- Returns `{"messages": [...], "mcp_connection_details": ...}`
- Backward compatible: still extracts MCP details if found

#### 5. Purple Agent Main (`src/purple_agent/main.py`)
**Updated:**
- Stores `incoming_messages` in context
- Still populates `mcp_connection_details` for backward compatibility
- Changed initial message to generic: "You are ready to evaluate BrowserGym tasks..."

## Message Flow

### Before (REST-like):
```
1. Purple → Green: POST /evaluate {task_id, benchmark}
2. Green → Purple: 200 OK {mcp_connection_details: {...}}
3. Purple: Pre-populate context.mcp_connection_details
4. Purple: Start LLM (already has MCP details)
5. LLM: Call connect_to_mcp_server (reads pre-populated details)
```

### After (Message-based):
```
1. Purple → Green: A2A message "Ready for evaluation"
2. Green → Purple: A2A message stream with MCP details
3. Purple: Collect all messages into context.incoming_messages
4. Purple: Start LLM with messages in context
5. LLM: Call connect_to_mcp_server
6. Tool: Extract MCP details from incoming_messages
7. Tool: Establish MCP connection
```

## Backward Compatibility

All changes are backward compatible:
- If `mcp_connection_details` is pre-populated, tool uses it directly
- If not, tool searches `incoming_messages`
- A2A client returns both formats
- Existing tests continue to work

## Testing Considerations

### Unit Tests
- `connect_to_mcp_server` tool tests should verify both paths:
  1. Direct `mcp_connection_details` in context
  2. Extraction from `incoming_messages`

### Integration Tests
- Kickstart script unchanged (backward compatible)
- Full A2A flow tests both Green and Purple agents
- Message collection tested end-to-end

## Future Improvements

1. **Remove backward compatibility layer** once Green Agent fully implements message-based MCP details delivery
2. **Add message filtering tools** for LLM to query specific message types
3. **Implement message acknowledgment** so Purple Agent confirms receipt
4. **Add message history tool** for LLM to review past communications

## Migration Notes

For developers:
- Purple Agent now supports both synchronous (pre-populated) and asynchronous (message-based) MCP detail delivery
- Tools automatically handle extraction - no LLM prompt engineering needed
- `incoming_messages` field provides full A2A communication history to agent

For Green Agent:
- Can send MCP details via `task_updater.update_status(message=msg)` where `msg` contains DataPart with MCP details
- Purple Agent will automatically collect and process these messages
