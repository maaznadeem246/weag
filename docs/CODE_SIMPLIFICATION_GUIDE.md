# Code Simplification Guide for Green Agent

This document outlines recommended simplifications for the Green Agent codebase to improve clarity, modularity, and maintainability while preserving all functionality.

## Overview

The current codebase is functional but contains areas that can be simplified:
1. **Long functions** with multiple responsibilities
2. **Repeated code patterns** across similar functions
3. **Complex nesting** that reduces readability
4. **Inline logic** that could be extracted to helper functions
5. **Inconsistent error handling** patterns

## Key Improvements Implemented

### 1. Multi-Task Tools (`src/green_agent/agent/tools/`)

**Created: `multi_task_helpers.py`** - Extract reusable helper functions:

```python
# Helper functions for common operations
- calculate_task_metrics() - Calculate delta metrics between states
- create_task_result() - Create standardized task result dict
- store_task_result() - Store result and update context
- format_multi_task_progress() - Format progress messages
- check_activity_timeout() - Check for inactivity timeouts
- display_assessment_summary() - Display final metrics
```

**Benefits:**
- ✅ Eliminates 200+ lines of duplicated code
- ✅ Each function has single responsibility
- ✅ Easier to test and maintain
- ✅ Clear function names explain purpose

### 2. Simplification Patterns Applied

#### Pattern 1: Extract Helper Functions

**Before:**
```python
async def send_first_task_to_purple_agent(ctx):
    # 150+ lines of mixed logic:
    # - MCP server initialization
    # - Environment setup
    # - Message building
    # - Error handling
    pass
```

**After:**
```python
async def _initialize_mcp_server() -> Dict[str, Any]:
    """Single responsibility: Initialize MCP server"""
    # Clear, focused logic
    pass

async def _setup_environment_for_task(...) -> Dict[str, Any]:
    """Single responsibility: Setup environment"""
    # Clear, focused logic
    pass

async def send_first_task_to_purple_agent(ctx):
    """Orchestrate task sending using helpers"""
    mcp_result = await _initialize_mcp_server()
    if mcp_result["status"] != "success":
        return mcp_result
    
    env_result = await _setup_environment_for_task(...)
    # Clear flow, easy to follow
    pass
```

#### Pattern 2: Consolidate Duplicate Logic

**Before (Repeated 5+ times):**
```python
# In each failure handler:
metrics = {}
if start_state:
    metrics = {
        "tokens": max(0, current_state.total_tokens - start_state.total_tokens),
        "latency_ms": max(0, current_state.total_latency_ms - start_state.total_latency_ms),
        # ... 3 more lines
    }

task_result = {
    "task_id": current_task,
    "benchmark": multi_config.get("current_benchmark", "unknown"),
    # ... 10 more lines
}

# Store result in context
results = multi_config.setdefault("results_by_participant", {})
participant_results = results.setdefault("purple_agent", {"tasks": []})
participant_results["tasks"].append(task_result)

# Update context flags
multi_config["last_task_completed"] = True
multi_config["last_task_success"] = False
# ... more updates
```

**After (Single helper function):**
```python
def _handle_task_failure(...) -> Dict[str, Any]:
    """Centralized failure handling"""
    metrics = calculate_task_metrics(start_state, current_state)
    task_result = create_task_result(...)
    store_task_result(multi_config, context, task_result, ...)
    return {...}

# Usage in each failure scenario:
return _handle_task_failure(
    context=context,
    multi_config=multi_config,
    current_task=current_task,
    failure_reason="inactivity_timeout",
    # ... specific fields
)
```

#### Pattern 3: Use Type Hints Consistently

**Before:**
```python
async def send_first_task_to_purple_agent(ctx) -> dict:
    """Returns dict with status"""
    pass
```

**After:**
```python
async def send_first_task_to_purple_agent(
    ctx: RunContextWrapper[AgentContext]
) -> Dict[str, Any]:
    """
    Initialize multi-task assessment and send first task.
    
    Returns:
        Dictionary with status and task details
    """
    pass
```

## Recommended Simplifications for Other Modules

### `src/green_agent/mcp_server.py`

**Current Issues:**
- `execute_actions` tool has 200+ lines with nested logic
- Repetitive validation code across tools
- Complex TypedDict definitions

**Recommended Changes:**
```python
# Extract action validation
def _validate_action(action: ActionDict, action_type: str) -> tuple[bool, Optional[str]]:
    """Validate action has required fields for its type"""
    # Centralized validation logic
    pass

# Extract action execution
def _execute_single_action(action: ActionDict, session: EnvironmentSession) -> Dict:
    """Execute one action and return result"""
    # Single action logic
    pass

# Simplified main tool
@mcp.tool()
async def execute_actions(actions: list[ActionDict]) -> dict:
    """Execute batch of actions"""
    session = session_manager.get_session()
    results = []
    
    for action in actions:
        is_valid, error = _validate_action(action, ...)
        if not is_valid:
            return {"error": error}
        
        result = await _execute_single_action(action, session)
        results.append(result)
    
    return {"results": results, ...}
```

### `src/green_agent/environment/session_manager.py`

**Current Issues:**
- `create_session` method has 150+ lines
- Complex environment variable logic inline
- Nested error handling

**Recommended Changes:**
```python
class SessionManager:
    def _validate_task_id(self, task_id: str) -> tuple[bool, Optional[str]]:
        """Extract validation logic"""
        pass
    
    def _setup_environment_vars(self, benchmark: str, task_id: str) -> None:
        """Extract environment variable setup"""
        pass
    
    def _create_gym_environment(self, config: EnvironmentConfig) -> gym.Env:
        """Extract gym environment creation"""
        pass
    
    def create_session(self, config: EnvironmentConfig) -> EnvironmentSession:
        """Orchestrate session creation using helpers"""
        # Validation
        is_valid, error = self._validate_task_id(config.task_id)
        if not is_valid:
            raise ValueError(error)
        
        # Setup
        self._setup_environment_vars(...)
        
        # Create
        env = self._create_gym_environment(config)
        
        # Return
        return EnvironmentSession(...)
```

### `src/green_agent/main.py`

**Current Issues:**
- File is 1700+ lines (too large)
- Multiple responsibilities mixed together
- Hard to navigate and understand

**Recommended Changes:**
```
Split into modules:
- main.py (100 lines) - Entry point and server setup
- handlers/evaluation_handler.py - Handle evaluation requests
- handlers/artifact_handler.py - Handle artifact submissions
- orchestration/multi_task_orchestrator.py - Multi-task logic
- orchestration/single_task_orchestrator.py - Single-task logic
```

## Simplification Checklist

For each file/function, ask:

- [ ] **Single Responsibility**: Does this function do one thing well?
- [ ] **Clear Naming**: Is the purpose obvious from the name?
- [ ] **Short Length**: Is it under 50 lines (functions) or 300 lines (files)?
- [ ] **No Duplication**: Is similar code extracted to helpers?
- [ ] **Type Hints**: Are all parameters and returns typed?
- [ ] **Docstrings**: Is there clear documentation?
- [ ] **Error Handling**: Are errors handled consistently?
- [ ] **Testability**: Can this be easily unit tested?

## Implementation Priority

1. **High Priority** (Most Impact):
   - ✅ `multi_task_tools.py` - Completed helpers extraction
   - ⏳ `mcp_server.py` - Extract action validation/execution
   - ⏳ `session_manager.py` - Extract environment setup

2. **Medium Priority**:
   - `main.py` - Split into modules
   - `shared_state.py` - Simplify state management
   - `observation_filter.py` - Extract filtering logic

3. **Low Priority** (Already Good):
   - `models.py` - Already clean dataclasses
   - `entities.py` - Already well-structured
   - `metrics/tracker.py` - Already focused

## Testing After Simplification

After each simplification:
1. Run existing unit tests
2. Run integration tests
3. Test with sample tasks
4. Verify metrics are unchanged

```bash
# Verify no functionality changed
E:/Maaz/Projects/weag/.venv/Scripts/python.exe -m pytest tests/unit/ -v
E:/Maaz/Projects/weag/.venv/Scripts/python.exe scripts/kickstart_assessment.py --task miniwob.click-test
```

## Example: Complete Simplified Function

**Before (Complex, 80 lines):**
```python
async def wait_for_purple_completion(ctx, timeout_seconds=120):
    # 80 lines of nested ifs
    # Repeated metric calculations
    # Duplicate result creation
    # Mixed concerns
    pass
```

**After (Clear, 40 lines):**
```python
async def wait_for_purple_completion(
    ctx: RunContextWrapper[AgentContext],
    timeout_seconds: int = 120
) -> Dict[str, Any]:
    """
    Wait for Purple Agent task completion with timeout monitoring.
    
    Args:
        ctx: Agent context wrapper
        timeout_seconds: Maximum wait time
        
    Returns:
        Dictionary with completion status and results
    """
    context = ctx.context
    multi_config = context.multi_task_config or {}
    shared_state = context.shared_state_manager
    
    if not shared_state:
        return {"status": "error", "message": "No shared state available"}
    
    # Initialize monitoring
    start_time = time.time()
    start_state = shared_state.read_state()
    last_activity = start_time
    last_mcp_calls = start_state.mcp_tool_invocations
    
    # Monitor loop
    while time.time() - start_time < timeout_seconds:
        current_state = shared_state.read_state()
        
        # Update activity tracking
        if current_state.mcp_tool_invocations > last_mcp_calls:
            last_activity = time.time()
            last_mcp_calls = current_state.mcp_tool_invocations
        
        # Check failure conditions (using helpers)
        if _is_inactive(last_activity):
            return _handle_task_failure(..., reason="inactivity_timeout")
        
        if current_state.error:
            return _handle_task_failure(..., reason="error")
        
        if current_state.tool_calls_exceeded:
            return _handle_task_failure(..., reason="tool_limit_exceeded")
        
        # Check completion
        if current_state.task_completed:
            return _handle_task_success(...)
        
        await asyncio.sleep(0.5)
    
    # Timeout
    return _handle_task_failure(..., reason="timeout")
```

## Conclusion

These simplifications make the code:
- **Easier to understand** - Clear function names and responsibilities
- **Easier to maintain** - Changes are localized to specific functions
- **Easier to test** - Small, focused functions are testable
- **More reliable** - Consistent patterns reduce bugs
- **Better documented** - Clear docstrings and type hints

**Remember**: Preserve ALL functionality - only change HOW code is written, not WHAT it does!
