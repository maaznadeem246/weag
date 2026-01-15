# Assessment Class - Quick Reference

## Assessment Methods Overview

### State Management
```python
# Associate state manager for real-time state access
assessment.set_state_manager(shared_state_manager)

# Read current state from MCP subprocess
current_state = assessment.get_real_time_state()

# Snapshot state at task start (for delta metrics)
assessment.snapshot_task_start(task_index=0)
```

### Metrics Calculation
```python
# Calculate delta metrics for a task (uses snapshots)
metrics = assessment.calculate_task_metrics(task_index=0)
# Returns: {"tokens": 1500, "latency_ms": 3200, "actions": 12, ...}

# Calculate aggregate metrics for benchmark results
aggregates = assessment.calculate_benchmark_aggregates(task_results)
# Returns: {"success_rate": 0.85, "avg_score": 0.78, ...}
```

### Artifact Building
```python
# Build artifact for a single task
artifact = assessment.build_task_artifact(
    task_index=0,
    evaluation_result=eval_result
)

# Build overall batch result
batch_result = assessment.build_batch_result(
    execution_mode="sequential",
    stop_on_error=False
)

# Get per-benchmark result
benchmark_result = assessment.get_benchmark_result("miniwob")

# Format error result
error_result = assessment.format_error_result(
    error_message="Task failed",
    current_benchmark="miniwob"
)
```

### Display Utilities
```python
# Format progress message for Purple Agent
progress_msg = assessment.format_progress(environment_action="reset")
# Returns: "\n\nMULTI-TASK MODE: This is task 2 of 5. Environment reset. ..."

# Display comprehensive summary to console
assessment.display_summary()
# Prints formatted assessment results
```

### Batch Evaluation
```python
# Select tasks for a benchmark
tasks = assessment.select_tasks_for_benchmark(
    benchmark="miniwob",
    max_tasks=10,
    selection_mode="random",  # or "sequential", "specific"
    specific_task_ids=None
)

# Execute full batch evaluation
result = assessment.execute_batch_evaluation(
    benchmarks=[
        BenchmarkConfig(benchmark_name="miniwob", max_tasks=5),
        BenchmarkConfig(benchmark_name="webarena", max_tasks=3),
    ],
    execution_mode="sequential",
    stop_on_error=False,
    supported_benchmarks=["miniwob", "webarena", ...]
)
```

### Core Tracking Methods
```python
# Add a task
assessment.add_task(task_id="miniwob.click-test", benchmark="miniwob")

# Mark task complete
assessment.mark_task_complete(
    task_index=0,
    success=True,
    final_reward=0.95
)

# Advance to next task
assessment.advance_to_next_task()

# Get task by index
task = assessment.get_task(task_index=0)

# Get results summary
summary = assessment.get_results_summary()
```

## LLM Tool Pattern

### Standard Tool Pattern
```python
from agents.function_tool import function_tool
from agents.run_context import RunContextWrapper
from src.green_agent.agent.context import AgentContext
from src.green_agent.assessment import Assessment

@function_tool
async def my_tool(ctx: RunContextWrapper[AgentContext]) -> Dict[str, Any]:
    """Tool docstring for LLM."""
    context: AgentContext = ctx.context
    assessment: Assessment = context.assessment_tracker
    
    # Validation
    if not assessment:
        return {"error": "No Assessment instance in context"}
    
    # Delegate to Assessment
    result = assessment.some_method(...)
    
    return result
```

### Multi-Task Tool Example
```python
@function_tool
async def wait_for_purple_completion(
    ctx: RunContextWrapper[AgentContext],
    timeout_seconds: int = 120
) -> dict:
    """Wait for Purple Agent to complete current task."""
    context: AgentContext = ctx.context
    assessment: Assessment = context.assessment_tracker
    
    # Get task details from Assessment
    task_index = assessment.current_index
    
    # Wait for completion...
    
    # Calculate metrics using Assessment
    metrics = assessment.calculate_task_metrics(task_index)
    
    # Format progress using Assessment
    progress = assessment.format_progress("maintained")
    
    return {
        "status": "completed",
        "metrics": metrics,
        "next_instruction": progress
    }
```

### Batch Evaluation Tool Example
```python
@function_tool
async def orchestrate_batch_evaluation(
    ctx: RunContextWrapper[AgentContext]
) -> Dict[str, Any]:
    """Orchestrate multi-benchmark batch evaluation."""
    context: AgentContext = ctx.context
    assessment: Assessment = context.assessment_tracker
    
    if not assessment or not context.batch_config:
        return {"error": "Missing configuration"}
    
    # Thin wrapper - delegate everything to Assessment
    return assessment.execute_batch_evaluation(
        benchmarks=context.batch_config.benchmarks,
        execution_mode=context.batch_config.execution_mode,
        stop_on_error=context.batch_config.stop_on_error,
        supported_benchmarks=SUPPORTED_BENCHMARKS
    )
```

## Common Usage Patterns

### Pattern 1: Multi-Task Orchestration
```python
# 1. Create Assessment
assessment = create_assessment(config)

# 2. Associate state manager
assessment.set_state_manager(shared_state_manager)

# 3. For each task:
for task_idx in range(assessment.total_tasks):
    # Snapshot start state
    assessment.snapshot_task_start(task_idx)
    
    # Send task to Purple Agent...
    
    # Wait for completion...
    
    # Calculate metrics
    metrics = assessment.calculate_task_metrics(task_idx)
    
    # Mark complete
    assessment.mark_task_complete(task_idx, success=True, final_reward=0.9)
    
    # Advance
    assessment.advance_to_next_task()

# 4. Display summary
assessment.display_summary()
```

### Pattern 2: Batch Evaluation
```python
# 1. Create Assessment (empty - batch mode doesn't use task list)
assessment = create_assessment(config)

# 2. Execute batch
result = assessment.execute_batch_evaluation(
    benchmarks=benchmark_configs,
    execution_mode="sequential",
    stop_on_error=False,
    supported_benchmarks=["miniwob", "webarena", ...]
)

# Result contains per-benchmark results and overall aggregates
```

### Pattern 3: Single-Task Evaluation (Outside Assessment)
```python
# For non-Assessment workflows (e.g., Purple Agent standalone execution)
# Still use helpers:
from src.green_agent.agent.tools.helpers import build_evaluation_artifact_dict

artifact = build_evaluation_artifact_dict(
    context=agent_context,
    evaluation_result=eval_result,
    state=final_state
)
```

## Backward Compatibility

### Old Code (Still Works)
```python
from src.green_agent.assessment import AssessmentTracker, create_tracker_from_config

tracker = create_tracker_from_config(config)
tracker.add_task(...)
```

### New Code (Preferred)
```python
from src.green_agent.assessment import Assessment, create_assessment

assessment = create_assessment(config)
assessment.add_task(...)
```

## Key Differences from Old Pattern

### Before (Scattered Helpers)
```python
# Tools had inline logic
from src.green_agent.agent.tools.helpers import (
    calculate_task_metrics,
    format_multi_task_progress,
    display_assessment_summary
)

# Calculate metrics
start_state = ...
current_state = ...
metrics = calculate_task_metrics(start_state, current_state)

# Format progress
progress = format_multi_task_progress(idx, total, "reset")

# Display summary
display_assessment_summary(results)
```

### After (Assessment Methods)
```python
# Everything through Assessment
assessment = context.assessment_tracker

# Calculate metrics (uses stored snapshots)
metrics = assessment.calculate_task_metrics(task_index)

# Format progress
progress = assessment.format_progress("reset")

# Display summary
assessment.display_summary()
```

## Testing

### Unit Test Pattern
```python
def test_assessment_method():
    config = AssessmentConfig(...)
    assessment = create_assessment(config)
    
    # Test method
    result = assessment.some_method(...)
    
    assert result == expected
```

### Integration Test Pattern
```python
def test_tool_delegates_to_assessment():
    assessment = create_assessment(config)
    context = AgentContext(assessment_tracker=assessment, ...)
    ctx = RunContextWrapper(context)
    
    # Call tool
    result = await my_tool(ctx)
    
    # Verify Assessment method was called
    assert assessment.some_method.called  # Mock verification
```

## Summary

**Assessment Class**: Single source of truth for assessment operations
- ✅ State management with SharedStateManager integration
- ✅ Metrics calculation (delta-based, aggregate-based)
- ✅ Artifact building (task, batch, benchmark, error)
- ✅ Display utilities (progress, summary)
- ✅ Batch evaluation orchestration (task selection, execution)

**LLM Tools**: Thin wrappers that delegate to Assessment
- ✅ Extract context
- ✅ Validate inputs
- ✅ Call Assessment methods
- ✅ Return results

**Benefits**:
- Reusable logic outside LLM tools
- Easier testing (mock Assessment methods)
- Consistent patterns across codebase
- Single source of truth for assessment operations
