"""
Evaluation tools for metrics calculation and artifact generation.

Tools for:
- Efficiency score calculation
- Evaluation artifact generation
- Multi-benchmark batch evaluation orchestration
"""

import time
from typing import Any, Dict
from agents.run_context import RunContextWrapper

from src.agent.context import AgentContext, EvaluationResult, BenchmarkConfig
from src.metrics.penalty_calculator import PenaltyCalculator
from src.agent.tools.helpers import build_evaluation_artifact_dict
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Supported benchmarks (FR-024)
SUPPORTED_BENCHMARKS = [
    "miniwob",
    "webarena",
    "visualwebarena",
    "workarena",
    "assistantbench",
    "weblinx",
]


# =============================================================================
# Calculate Efficiency Score Tool
# =============================================================================

async def calculate_efficiency_score(ctx: RunContextWrapper[AgentContext]) -> EvaluationResult:
    """
    Calculate efficiency metrics and penalties.
    
    Wraps PenaltyCalculator to compute:
    - Token cost (C mandate)
    - Latency (L mandate)
    - Step count (efficiency)
    - Final score with penalties applied
    
    Returns EvaluationResult with all metrics.
    """
    context: AgentContext = ctx.context
    
    # Read final state
    state_manager = context.shared_state_manager
    state = state_manager.read_state()
    
    # Calculate metrics
    token_cost = state.total_tokens
    latency_seconds = state.total_latency_ms / 1000.0
    step_count = state.action_count
    task_success = state.task_success
    
    # Calculate efficiency penalty using PenaltyCalculator
    calculator = PenaltyCalculator()
    efficiency_penalty = calculator.calculate_penalty(
        tokens_used=token_cost,
        latency_ms=state.total_latency_ms,
        action_count=step_count
    )
    
    # Final score: base reward minus efficiency penalty
    base_reward = state.final_reward
    final_score = max(0.0, base_reward - efficiency_penalty)
    
    logger.info(
        f"Efficiency score calculated",
        extra={
            "session_id": context.session_id,
            "task_success": task_success,
            "final_score": final_score,
            "base_reward": base_reward,
            "efficiency_penalty": efficiency_penalty,
            "token_cost": token_cost,
            "latency_seconds": latency_seconds,
            "step_count": step_count,
        }
    )
    
    return EvaluationResult(
        status="success",
        task_success=task_success,
        final_score=final_score,
        token_cost=token_cost,
        latency_seconds=latency_seconds,
        step_count=step_count,
        efficiency_penalty=efficiency_penalty,
        message=f"Score: {final_score:.3f} (reward: {base_reward:.3f}, penalty: {efficiency_penalty:.3f})"
    )


async def send_task_update(ctx: RunContextWrapper[AgentContext], status: str, message: str, final: bool = False) -> Dict[str, Any]:
    """Emit a task update using TaskUpdater if available; return status."""
    context: AgentContext = ctx.context
    try:
        if getattr(context, "task_updater", None):
            # best-effort call; tests may patch emit_task_update elsewhere
            from src.a2a.message_handler import emit_task_update
            await emit_task_update(context.task_updater, status, message, final)

        return {"status": "sent", "update_status": status, "message": message, "final": final}
    except Exception as e:
        return {"status": "failed", "error": str(e)}


# =============================================================================
# Generate Evaluation Artifact Tool
# =============================================================================

async def generate_evaluation_artifact(
    ctx: RunContextWrapper[AgentContext],
    evaluation_result: EvaluationResult
) -> Dict[str, Any]:
    """
    Generate final evaluation artifact following A2A schema.
    
    Args:
        ctx: RunContextWrapper with AgentContext
        evaluation_result: EvaluationResult from calculate_efficiency_score
    
    Returns:
        Artifact dict following AgentBeats freeform schema
    """
    context: AgentContext = ctx.context
    
    # Read final state
    state_manager = context.shared_state_manager
    state = state_manager.read_state()
    
    # Build artifact using helper
    artifact = build_evaluation_artifact_dict(context, evaluation_result, state)
    
    logger.info(
        "Evaluation artifact generated",
        extra={
            "session_id": context.session_id,
            "task_success": artifact["task_success"],
            "final_score": artifact["final_score"],
        }
    )
    
    return artifact


# =============================================================================
# Multi-Benchmark Batch Evaluation Orchestration
# =============================================================================

async def orchestrate_batch_evaluation(ctx: RunContextWrapper[AgentContext]) -> Dict[str, Any]:
    """
    Orchestrate sequential evaluation across multiple benchmarks.
    
    LLM tool wrapper that delegates to Assessment.execute_batch_evaluation().
    
    Implements Batch evaluation with task selection, isolation, and aggregation.
    
    Features:
    - Sequential execution only (parallel out-of-scope per FR-027)
    - Per-benchmark task selection (random/sequential/specific)
    - Benchmark isolation (separate sessions, no cross-contamination per FR-014)
    - Result aggregation (per-benchmark and overall metrics)
    - Stop-on-error support
    
    Args:
        ctx: RunContextWrapper with AgentContext containing batch_config and assessment
        
    Returns:
        Aggregated batch evaluation results with per-benchmark metrics
        
    Example:
        batch_config = BatchEvaluationConfig(
            benchmarks=[
                BenchmarkConfig(benchmark_name="miniwob", max_tasks=10),
                BenchmarkConfig(benchmark_name="webarena", max_tasks=5),
            ]
        )
        result = await orchestrate_batch_evaluation(ctx_with_batch_config)
    """
    context: AgentContext = ctx.context
    
    # Get assessment instance
    assessment = context.assessment_tracker
    if not assessment:
        return {
            "error": "No Assessment instance in context",
            "status": "failed"
        }
    
    # Get batch configuration
    if not context.batch_config:
        return {
            "error": "No batch configuration provided",
            "status": "failed"
        }
    
    batch_config = context.batch_config
    
    # Delegate to Assessment
    return assessment.execute_batch_evaluation(
        benchmarks=batch_config.benchmarks,
        execution_mode=batch_config.execution_mode,
        stop_on_error=batch_config.stop_on_error,
        supported_benchmarks=SUPPORTED_BENCHMARKS
    )


__all__ = [
    "calculate_efficiency_score",
    "generate_evaluation_artifact",
    "orchestrate_batch_evaluation",
    "send_task_update",
    "SUPPORTED_BENCHMARKS",
]
