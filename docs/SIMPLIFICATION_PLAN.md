# Code Simplification Plan for Green Agent

## Executive Summary

Analysis of `src/green_agent` folder identified **65 Python files** totaling **~14,500 lines of code**. The top 10 files account for **~6,700 lines (46%)** of the codebase. Simplification will focus on these high-impact files.

## Complexity Analysis

### 🔴 High Priority (1000+ lines, Immediate Simplification)
1. **main.py** (1,684 lines) - Entry point, multiple responsibilities
   - Split into modules: handlers, orchestration, server setup
   - Expected reduction: 1,684 → ~400 lines (main), rest in modules

2. **multi_task_tools.py** (795 lines) - Multi-task orchestration tools
   - Extract helpers (already done: multi_task_helpers.py)
   - Integrate helpers to reduce duplication
   - Expected reduction: 795 → ~450 lines

### 🟡 Medium Priority (500-1000 lines, Significant Impact)
3. **a2a/streaming.py** (669 lines) - SSE streaming implementation
   - Extract message formatting functions
   - Simplify stream handling logic
   - Expected reduction: 669 → ~500 lines

4. **benchmarks/tool_registry.py** (650 lines) - Dynamic tool registration
   - Consolidate benchmark-specific logic
   - Extract tool definition builders
   - Expected reduction: 650 → ~450 lines

5. **environment/observation_filter.py** (594 lines) - Observation filtering
   - Extract filter strategies
   - Simplify token counting logic
   - Expected reduction: 594 → ~400 lines

6. **environment/session_manager.py** (545 lines) - Environment lifecycle
   - Extract environment setup helpers
   - Simplify validation logic
   - Expected reduction: 545 → ~350 lines

7. **environment/observation_utils.py** (531 lines) - Observation parsing
   - Consolidate parsing functions
   - Extract AXTree processing
   - Expected reduction: 531 → ~350 lines

8. **mcp_server.py** (516 lines) - MCP server with FastMCP
   - Extract action validation
   - Extract action execution
   - Expected reduction: 516 → ~300 lines

### 🟢 Low Priority (Good Structure, Minor Improvements)
9-15. Files under 500 lines with good structure
   - Minor refactoring only where duplication exists

## Detailed Simplification Strategy

### Phase 1: Create Helper Modules (Day 1)
✅ **Completed**: `multi_task_helpers.py` (218 lines)
- 6 reusable functions for multi-task orchestration

🔲 **Next**: `mcp_helpers.py`
- Extract action validation logic
- Extract action execution logic
- Extract error formatting

🔲 **Create**: `observation_helpers.py`
- Extract AXTree parsing functions
- Extract text extraction functions
- Extract filtering strategies

🔲 **Create**: `environment_helpers.py`
- Extract environment variable setup
- Extract gym environment creation
- Extract validation functions

### Phase 2: Integrate Helpers (Day 2-3)

#### 2.1 Simplify multi_task_tools.py
**Target**: 795 → 450 lines (43% reduction)

Current issues:
- Repeated metrics calculation (5+ times)
- Repeated result creation (5+ times)
- Repeated state updates (5+ times)
- Long functions (80-150 lines)

Approach:
```python
# Before (150 lines)
async def wait_for_purple_completion(...):
    # 150 lines of nested logic
    
# After (60 lines using helpers)
async def wait_for_purple_completion(...):
    # Initialize monitoring
    monitor = TaskMonitor(shared_state, start_time)
    
    # Monitor loop
    while not monitor.is_timeout():
        current_state = monitor.check_state()
        
        # Check failure conditions
        if failure := monitor.check_failures(current_state):
            return handle_task_failure(..., reason=failure.reason)
        
        # Check completion
        if current_state.task_completed:
            return handle_task_success(...)
```

#### 2.2 Simplify mcp_server.py
**Target**: 516 → 300 lines (42% reduction)

Current issues:
- `execute_actions` tool is 200+ lines
- Repetitive validation across actions
- Mixed validation and execution logic

Approach:
```python
# Extract to mcp_helpers.py
def validate_action(action: ActionDict) -> Result[ActionDict, str]:
    """Validate action has required fields"""
    
def execute_single_action(action: ActionDict, session: Session) -> ActionResult:
    """Execute one validated action"""

# Simplified tool
@mcp.tool()
async def execute_actions(actions: list[ActionDict]) -> dict:
    """Execute batch of actions"""
    session = session_manager.get_session()
    results = []
    
    for action in actions:
        # Validate
        if error := validate_action(action):
            return {"error": error}
        
        # Execute
        result = await execute_single_action(action, session)
        results.append(result)
        
        if result.early_termination:
            break
    
    return format_batch_results(results)
```

#### 2.3 Simplify session_manager.py
**Target**: 545 → 350 lines (36% reduction)

Current issues:
- `create_session` method is 150+ lines
- Environment variable logic is inline
- Complex nested error handling

Approach:
```python
# Extract to environment_helpers.py
def setup_benchmark_environment(benchmark: str, task_id: str) -> None:
    """Setup environment variables for benchmark"""

def create_gym_env(config: EnvironmentConfig) -> gym.Env:
    """Create and configure gymnasium environment"""

def validate_task_format(task_id: str) -> Result[str, str]:
    """Validate task ID format"""

# Simplified session manager
class SessionManager:
    def create_session(self, config: EnvironmentConfig) -> EnvironmentSession:
        """Create environment session"""
        # Validate
        if error := validate_task_format(config.task_id):
            raise ValueError(error)
        
        # Setup
        setup_benchmark_environment(...)
        
        # Create
        env = create_gym_env(config)
        
        # Wrap
        return EnvironmentSession(env=env, config=config)
```

### Phase 3: Split Large Files (Day 4-5)

#### 3.1 Split main.py
**Target**: 1,684 → 400 + modules (modular structure)

New structure:
```
src/green_agent/
  main.py (400 lines) - Entry point, server setup
  orchestration/
    multi_task_orchestrator.py (500 lines)
    single_task_orchestrator.py (300 lines)
    agent_communication.py (200 lines)
  handlers/
    evaluation_handler.py (400 lines)
    artifact_handler.py (200 lines)
```

Benefits:
- Clear separation of concerns
- Easier to navigate and understand
- Better testability
- Reduced cognitive load

### Phase 4: Verification (Day 6)

Test suite to run after each simplification:
```bash
# Unit tests
python -m pytest tests/unit/ -v

# Integration tests
python -m pytest tests/integration/ -v

# Real task test
python scripts/kickstart_assessment.py --task miniwob.click-test

# Verify metrics unchanged
# Compare before/after: tokens, latency, actions, success_rate
```

## Implementation Checklist

### Week 1: Helper Modules
- [x] Create multi_task_helpers.py
- [ ] Create mcp_helpers.py
- [ ] Create observation_helpers.py
- [ ] Create environment_helpers.py
- [ ] Run tests after each helper creation

### Week 2: Integration
- [ ] Integrate helpers into multi_task_tools.py
- [ ] Integrate helpers into mcp_server.py  
- [ ] Integrate helpers into session_manager.py
- [ ] Integrate helpers into observation_filter.py
- [ ] Run full test suite

### Week 3: Module Splitting
- [ ] Split main.py into modules
- [ ] Split observation_utils.py if needed
- [ ] Split tool_registry.py if needed
- [ ] Update imports across codebase
- [ ] Run full test suite

### Week 4: Polish & Verify
- [ ] Add docstrings to all new functions
- [ ] Add type hints consistently
- [ ] Update documentation
- [ ] Final test suite run
- [ ] Performance benchmarking

## Expected Results

### Lines of Code Reduction
| File | Before | After | Reduction |
|------|--------|-------|-----------|
| main.py | 1,684 | 400 | 76% |
| multi_task_tools.py | 795 | 450 | 43% |
| mcp_server.py | 516 | 300 | 42% |
| session_manager.py | 545 | 350 | 36% |
| observation_filter.py | 594 | 400 | 33% |
| **Total Top 5** | **4,134** | **1,900** | **54%** |

### Code Quality Improvements
- ✅ Single responsibility functions
- ✅ Consistent error handling
- ✅ Clear type hints throughout
- ✅ Comprehensive docstrings
- ✅ Modular, testable code
- ✅ Reduced duplication (DRY)
- ✅ Better separation of concerns

### Maintainability Gains
- 🎯 Easier to understand (shorter functions, clear names)
- 🎯 Easier to modify (isolated responsibilities)
- 🎯 Easier to test (pure functions, dependency injection)
- 🎯 Easier to debug (less nesting, clear flow)
- 🎯 Easier to onboard (modular structure)

## Risk Mitigation

### Risks
1. **Breaking existing functionality** - Mitigated by comprehensive test suite
2. **Performance regression** - Mitigated by benchmarking
3. **Import circular dependencies** - Mitigated by careful module design

### Rollback Strategy
- Git commits after each change
- Keep backup files (.backup)
- Can revert individual changes if needed

## Success Criteria

✅ All existing tests pass
✅ Metrics remain identical (tokens, latency, actions)
✅ Code is more readable (shorter functions, clearer names)
✅ Code is more maintainable (isolated functions, less duplication)
✅ Documentation is up to date

## Timeline

- **Week 1**: Helper modules creation
- **Week 2**: Integration into existing files
- **Week 3**: Module splitting (main.py)
- **Week 4**: Polish, documentation, verification

**Total Estimated Time**: 4 weeks (can be done in parallel with other work)

## Next Steps

1. Review and approve this plan
2. Create branch: `feature/code-simplification`
3. Start with Phase 1: Create helper modules
4. Test after each change
5. Review and merge incrementally

---

**Note**: This is a quality improvement project. Current code is production-ready and competition-worthy. Simplification can be done after competition submission if preferred.
