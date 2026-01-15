"""
Artifact generation helpers for Green Agent evaluations.

Extracted from main.py to improve modularity and testability.
"""

from datetime import datetime, timezone
from typing import Optional

from src.utils.models import EvaluationArtifact, EvaluationSession
from src.metrics.tracker import EfficiencyMetrics
from src.metrics.penalty_calculator import calculate_efficiency_penalty
from src.utils.shared_state import EvaluationState
from src.utils.logging import get_logger


logger = get_logger(__name__)


def extract_benchmark_from_task_id(task_id: str) -> str:
    """
    Extract benchmark identifier from task_id.
    
    Args:
        task_id: Task identifier (e.g., "miniwob.click-test")
        
    Returns:
        Benchmark identifier (e.g., "miniwob")
    """
    if not task_id:
        return "unknown"
    return task_id.split(".")[0] if "." in task_id else "unknown"


def get_metrics_from_state(
    evaluation_state: Optional[EvaluationState],
    fallback_metrics: EfficiencyMetrics
) -> dict:
    """
    Get evaluation metrics from shared state or fallback to local metrics.
    
    Args:
        evaluation_state: Shared evaluation state (may be None)
        fallback_metrics: Local metrics tracker as fallback
        
    Returns:
        Dict with metric values
    """
    if evaluation_state:
        return {
            "total_tokens": evaluation_state.total_tokens,
            "total_latency_ms": evaluation_state.total_latency_ms,
            "action_count": evaluation_state.action_count,
            "observation_count": evaluation_state.observation_count,
            "mcp_tool_invocations": evaluation_state.mcp_tool_invocations,
            "task_success": evaluation_state.task_success,
            "final_reward": evaluation_state.final_reward,
        }
    
    # Fallback to local metrics
    metrics_dict = fallback_metrics.to_dict()
    return {
        "total_tokens": metrics_dict.get("total_tokens", 0),
        "total_latency_ms": metrics_dict.get("total_latency_ms", 0),
        "action_count": metrics_dict.get("action_count", 0),
        "observation_count": metrics_dict.get("observation_count", 0),
        "mcp_tool_invocations": metrics_dict.get("mcp_tool_invocations", 0),
        "task_success": False,
        "final_reward": 0.0,
    }


def calculate_final_score(
    task_success: bool,
    total_tokens: int,
    total_latency_ms: float
) -> tuple[float, float]:
    """
    Calculate efficiency penalty and final score.
    
    Args:
        task_success: Whether task was completed successfully
        total_tokens: Total tokens consumed
        total_latency_ms: Total latency in milliseconds
        
    Returns:
        Tuple of (efficiency_penalty, final_score)
    """
    efficiency_penalty = calculate_efficiency_penalty(
        total_tokens=total_tokens,
        total_latency_seconds=total_latency_ms / 1000.0
    )
    
    final_score = float(task_success) * efficiency_penalty
    
    return efficiency_penalty, final_score


def create_evaluation_artifact(
    task_id: str,
    task_success: bool,
    metrics: dict,
    efficiency_penalty: float,
    final_score: float,
    duration_seconds: float,
    session_id: str,
    additional_metrics: Optional[dict] = None
) -> EvaluationArtifact:
    """
    Create evaluation artifact with all metrics.
    
    Args:
        task_id: Task identifier
        task_success: Whether task completed successfully
        metrics: Dict with metric values
        efficiency_penalty: Calculated efficiency penalty
        final_score: Final evaluation score
        duration_seconds: Evaluation duration
        session_id: Session identifier
        additional_metrics: Optional additional metrics (memory, processes, etc.)
        
    Returns:
        Complete evaluation artifact
    """
    benchmark = extract_benchmark_from_task_id(task_id)
    
    # Extract additional metrics
    additional = additional_metrics or {}
    peak_memory_mb = additional.get("peak_memory_mb", 0)
    chromium_process_count = additional.get("chromium_process_count", 0)
    
    return EvaluationArtifact(
        task_success=task_success,
        task_id=task_id,
        benchmark=benchmark,
        total_tokens=metrics["total_tokens"],
        total_latency_ms=metrics["total_latency_ms"],
        peak_memory_mb=peak_memory_mb,
        chromium_process_count=chromium_process_count,
        efficiency_penalty=efficiency_penalty,
        final_score=final_score,
        mcp_tool_invocations=metrics["mcp_tool_invocations"],
        observation_count=metrics["observation_count"],
        action_count=metrics["action_count"],
        evaluation_duration_seconds=duration_seconds,
        metadata={
            "session_id": session_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    )


def create_error_artifact(
    error_message: str,
    task_id: Optional[str],
    duration_seconds: float,
    session_id: str
) -> EvaluationArtifact:
    """
    Create error artifact when evaluation fails.
    
    Args:
        error_message: Error description
        task_id: Task identifier if available
        duration_seconds: Duration before failure
        session_id: Session identifier
        
    Returns:
        Error evaluation artifact with zero metrics
    """
    task_id = task_id or "unknown"
    benchmark = extract_benchmark_from_task_id(task_id)
    
    return EvaluationArtifact(
        task_success=False,
        task_id=task_id,
        benchmark=benchmark,
        total_tokens=0,
        total_latency_ms=0,
        peak_memory_mb=0,
        chromium_process_count=0,
        efficiency_penalty=0.0,
        final_score=0.0,
        mcp_tool_invocations=0,
        observation_count=0,
        action_count=0,
        evaluation_duration_seconds=duration_seconds,
        metadata={
            "session_id": session_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": error_message
        }
    )


def log_evaluation_completion(artifact: EvaluationArtifact) -> None:
    """
    Log evaluation completion with key metrics.
    
    Args:
        artifact: Completed evaluation artifact
    """
    logger.info(
        f"✅ Evaluation complete: {artifact.task_id} | "
        f"Success: {artifact.task_success} | "
        f"Score: {artifact.final_score:.4f} | "
        f"Tokens: {artifact.total_tokens} | "
        f"Latency: {artifact.total_latency_ms}ms"
    )
