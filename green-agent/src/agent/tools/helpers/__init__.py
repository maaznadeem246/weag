"""
Helper functions for LLM agent tools.

These utilities support the @function_tool decorated LLM agent functions.

Note: Multi-task orchestration helpers have been moved to the Assessment class.
Only single-task and environment cleanup helpers remain here.
"""

import time
from typing import Any, Dict, List, Tuple

from src.agent.context import EvaluationResult, AgentContext
from src.utils.shared_state import EvaluationState
from src.utils.logging import get_logger

logger = get_logger(__name__)


# =============================================================================
# Evaluation Tool Helpers
# =============================================================================

def build_evaluation_artifact_dict(
    context: AgentContext,
    evaluation_result: EvaluationResult,
    state: EvaluationState
) -> Dict[str, Any]:
    """
    Build evaluation artifact dictionary following A2A schema.
    
    Args:
        context: Agent context with task and session info
        evaluation_result: Calculated efficiency metrics
        state: Final evaluation state from shared state manager
        
    Returns:
        Complete artifact dict with all evaluation data
    """
    end_time = time.time()
    
    return {
        # Core evaluation results
        "task_id": context.task_id,
        "benchmark": context.benchmark,
        "session_id": context.session_id,
        "task_success": evaluation_result.task_success,
        "final_score": evaluation_result.final_score,
        
        # Efficiency metrics (C/L/F mandates)
        "token_cost": evaluation_result.token_cost,
        "latency_seconds": evaluation_result.latency_seconds,
        "step_count": evaluation_result.step_count,
        "efficiency_penalty": evaluation_result.efficiency_penalty,
        
        # Timing
        "start_time": context.start_time,
        "end_time": end_time,
        "elapsed_time": end_time - context.start_time,
        
        # Environment state
        "environment_state": {
            "done": state.done,
            "truncated": state.truncated,
            "final_reward": state.final_reward,
            "total_tokens": state.total_tokens,
            "total_latency_ms": state.total_latency_ms,
            "action_count": state.action_count,
            "observation_count": state.observation_count,
            "mcp_tool_invocations": state.mcp_tool_invocations,
        },
        
        # Action history summary
        "action_history": {
            "total_actions": state.action_count,
            "last_tool": state.last_tool,
            "last_tool_timestamp": state.last_tool_timestamp,
        },
        
        # Error log
        "error_log": [state.error] if state.error else [],
        
        # Metadata (A2A protocol compliance)
        "metadata": {
            "session_id": context.session_id,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        },
    }


def calculate_benchmark_aggregates(task_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Calculate aggregated metrics for a benchmark's task results.
    
    Args:
        task_results: List of individual task result dicts
        
    Returns:
        Dict with aggregated metrics (success_rate, avg_score, avg_token_cost, etc.)
    """
    if not task_results:
        return {
            "success_rate": 0.0,
            "avg_score": 0.0,
            "avg_token_cost": 0,
            "avg_latency": 0.0,
        }
    
    successes = sum(1 for r in task_results if r.get("success", False))
    total_tasks = len(task_results)
    
    # Calculate average score from successful tasks only
    scores = [r.get("score", 0.0) for r in task_results if r.get("success")]
    avg_score = sum(scores) / len(scores) if scores else 0.0
    
    # Calculate average token cost and latency from all tasks
    total_tokens = sum(r.get("tokens", 0) for r in task_results)
    total_latency = sum(r.get("latency", 0.0) for r in task_results)
    
    return {
        "success_rate": successes / total_tasks,
        "avg_score": avg_score,
        "avg_token_cost": total_tokens / total_tasks,
        "avg_latency": total_latency / total_tasks,
    }


def build_overall_batch_result(
    per_benchmark_results: List[Dict[str, Any]],
    context: AgentContext,
    execution_mode: str,
    stop_on_error: bool
) -> Dict[str, Any]:
    """
    Build overall batch evaluation result with aggregated metrics.
    
    Args:
        per_benchmark_results: List of per-benchmark result dicts
        context: Agent context with session info
        execution_mode: Execution mode (sequential/parallel)
        stop_on_error: Whether stop-on-error was enabled
        
    Returns:
        Complete batch evaluation result with overall aggregates
    """
    overall_task_count = sum(r["tasks_evaluated"] for r in per_benchmark_results)
    overall_success_count = sum(r["successes"] for r in per_benchmark_results)
    overall_token_cost = sum(r["total_tokens"] for r in per_benchmark_results)
    overall_latency = sum(r["total_latency"] for r in per_benchmark_results)
    
    return {
        "status": "success",
        "benchmarks_evaluated": len(per_benchmark_results),
        "total_tasks_evaluated": overall_task_count,
        "overall_success_count": overall_success_count,
        "overall_success_rate": (
            overall_success_count / overall_task_count if overall_task_count > 0 else 0.0
        ),
        "overall_avg_token_cost": (
            overall_token_cost / overall_task_count if overall_task_count > 0 else 0
        ),
        "overall_avg_latency": (
            overall_latency / overall_task_count if overall_task_count > 0 else 0.0
        ),
        "per_benchmark_results": per_benchmark_results,
        "metadata": {
            "session_id": context.session_id,
            "execution_mode": execution_mode,
            "stop_on_error": stop_on_error,
        }
    }


def create_benchmark_result_dict(
    benchmark_name: str,
    task_results: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Create a benchmark result dictionary with calculated aggregates.
    
    Args:
        benchmark_name: Name of the benchmark
        task_results: List of task result dicts
        
    Returns:
        Complete benchmark result dict with aggregates
    """
    successes = sum(1 for r in task_results if r.get("success", False))
    failures = len(task_results) - successes
    total_tokens = sum(r.get("tokens", 0) for r in task_results)
    total_latency = sum(r.get("latency", 0.0) for r in task_results)
    
    result = {
        "benchmark": benchmark_name,
        "tasks_evaluated": len(task_results),
        "successes": successes,
        "failures": failures,
        "total_tokens": total_tokens,
        "total_latency": total_latency,
        "task_results": task_results,
    }
    
    # Add aggregates if tasks were evaluated
    if task_results:
        aggregates = calculate_benchmark_aggregates(task_results)
        result.update(aggregates)
    else:
        result.update({
            "success_rate": 0.0,
            "avg_score": 0.0,
            "avg_token_cost": 0,
            "avg_latency": 0.0,
        })
    
    return result


def format_batch_error_result(
    error_message: str,
    completed_benchmarks: int,
    current_benchmark: str,
    per_benchmark_results: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Format error result for batch evaluation failure.
    
    Args:
        error_message: Error description
        completed_benchmarks: Number of benchmarks completed before error
        current_benchmark: Benchmark that failed
        per_benchmark_results: Results collected so far
        
    Returns:
        Formatted error result dict
    """
    return {
        "error": error_message,
        "status": "failed",
        "completed_benchmarks": completed_benchmarks,
        "current_benchmark": current_benchmark,
        "per_benchmark_results": per_benchmark_results,
    }


# =============================================================================
# Multi-Task Tool Helpers
# =============================================================================

def calculate_task_metrics(
    start_state: Any, 
    current_state: Any
) -> Dict[str, int]:
    """
    Calculate delta metrics between start and current state.
    
    Args:
        start_state: State at task start
        current_state: Current state
        
    Returns:
        Dictionary with metric deltas (tokens, latency_ms, actions, observations, mcp_calls)
    """
    if not start_state or not current_state:
        return {
            "tokens": 0,
            "latency_ms": 0,
            "actions": 0,
            "observations": 0,
            "mcp_calls": 0,
        }
    
    return {
        "tokens": max(0, current_state.total_tokens - start_state.total_tokens),
        "latency_ms": max(0, current_state.total_latency_ms - start_state.total_latency_ms),
        "actions": max(0, current_state.action_count - start_state.action_count),
        "observations": max(0, current_state.observation_count - start_state.observation_count),
        "mcp_calls": max(0, current_state.mcp_tool_invocations - start_state.mcp_tool_invocations),
    }


def format_multi_task_progress(
    current_index: int,
    total_tasks: int,
    environment_action: str = "maintained"
) -> str:
    """
    Format multi-task progress message for Purple Agent.
    
    Args:
        current_index: Current task index (0-based)
        total_tasks: Total number of tasks
        environment_action: Action taken on environment (reset/recreated/maintained)
        
    Returns:
        Formatted progress message
    """
    task_num = current_index + 1
    return (
        f"\n\nMULTI-TASK MODE: This is task {task_num} of {total_tasks}. "
        f"Environment {environment_action}. "
        f"Complete this task (done=True or reward>0) then wait for next task."
    )


def display_assessment_summary(results: Dict[str, Any]) -> None:
    """
    Display comprehensive assessment metrics in formatted console output.
    
    Args:
        results: Final assessment results dictionary
    """
    print("\n" + "=" * 80)
    print("🎯 ASSESSMENT COMPLETED - FINAL METRICS")
    print("=" * 80)
    
    # Overview
    print(f"\n📊 Overview:")
    print(f"   Mode: {results.get('mode', 'unknown').upper()}")
    print(f"   Run ID: {results.get('run_id', 'N/A')}")
    orchestration = "LLM-controlled" if results.get('orchestrated_by_llm') else "Programmatic"
    print(f"   Orchestration: {orchestration}")
    
    # Task Results
    total = results.get('total_tasks', 0)
    passed = results.get('passed_tasks', 0)
    failed = total - passed
    success_rate = results.get('success_rate', 0.0)
    
    print(f"\n✅ Task Results:")
    print(f"   Total Tasks: {total}")
    print(f"   Passed: {passed} ({success_rate * 100:.1f}%)")
    print(f"   Failed: {failed}")
    
    # Per-task status breakdown
    task_results = results.get('task_results', [])
    if task_results:
        print(f"\n📋 Per-Task Breakdown:")
        for tr in task_results:
            status_icon = "✓" if tr.get('success') else "✗"
            task_id = tr.get('task_id', 'unknown')
            reward = tr.get('final_reward', 0.0)
            status = tr.get('status', 'unknown')
            completion_time = tr.get('completion_time', 0)
            print(f"   {status_icon} {task_id}: reward={reward:.2f}, status={status}, time={completion_time:.1f}s")
    
    # Efficiency Metrics
    total_tokens = results.get('total_tokens', 0)
    total_latency_ms = results.get('total_latency_ms', 0)
    total_actions = results.get('total_actions', 0)
    
    print(f"\n⚡ Efficiency Metrics:")
    print(f"   Total Tokens: {total_tokens:,}")
    print(f"   Total Latency: {total_latency_ms / 1000:.2f}s")
    print(f"   Total Actions: {total_actions}")
    
    if total > 0:
        print(f"\n📈 Average per Task:")
        print(f"   Avg Tokens: {total_tokens // total}")
        print(f"   Avg Latency: {total_latency_ms / total / 1000:.2f}s")
        print(f"   Avg Actions: {total_actions / total:.1f}")
    
    # Participants Summary (if multi-participant)
    participants = results.get('participants', {})
    if participants and len(participants) > 1:
        print(f"\n👥 Participants Summary:")
        for participant, data in participants.items():
            participant_tasks = data.get('tasks', [])
            participant_passed = sum(1 for t in participant_tasks if t.get('success'))
            print(f"   {participant}: {participant_passed}/{len(participant_tasks)} tasks passed")
    
    print("\n" + "=" * 80)
    print("🏁 Assessment Complete")
    print("=" * 80 + "\n")


# =============================================================================
# Environment Tool Helpers
# =============================================================================

def terminate_mcp_process(mcp_process_id: int) -> Tuple[bool, str]:
    """
    Terminate MCP server process.
    
    Args:
        mcp_process_id: Process ID to terminate
        
    Returns:
        Tuple of (success, error_message)
    """
    try:
        from src.resources.process_monitor import kill_process_tree
        killed = kill_process_tree(mcp_process_id)
        return (killed > 0, "" if killed > 0 else "No processes killed")
    except Exception as e:
        error_msg = f"MCP termination failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return (False, error_msg)


def cleanup_state_files(shared_state_manager) -> Tuple[bool, str]:
    """
    Cleanup shared state files.
    
    Args:
        shared_state_manager: Shared state manager instance
        
    Returns:
        Tuple of (success, error_message)
    """
    try:
        shared_state_manager.cleanup()
        return (True, "")
    except Exception as e:
        error_msg = f"State cleanup failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return (False, error_msg)


def determine_cleanup_status(
    mcp_terminated: bool,
    session_closed: bool,
    resources_cleaned: bool,
    errors: List[str]
) -> Tuple[str, str]:
    """
    Determine overall cleanup status and message.
    
    Args:
        mcp_terminated: Whether MCP server was terminated
        session_closed: Whether session was closed
        resources_cleaned: Whether resources were cleaned
        errors: List of error messages
        
    Returns:
        Tuple of (status, message)
    """
    if mcp_terminated and session_closed and resources_cleaned:
        return ("success", "Cleanup completed successfully")
    elif mcp_terminated or resources_cleaned:
        return ("partial", f"Cleanup partially complete: {', '.join(errors)}")
    else:
        return ("failure", f"Cleanup failed: {', '.join(errors)}")


__all__ = [
    # Single-task evaluation helper (still needed for non-Assessment workflows)
    "build_evaluation_artifact_dict",
    
    # Environment cleanup helpers
    "terminate_mcp_process",
    "cleanup_state_files",
    "determine_cleanup_status",
]
