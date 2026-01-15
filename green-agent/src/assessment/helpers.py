"""
Assessment helper functions for tracker and domain logic.

Provides utility functions for:
- Task result creation and storage
- Activity timeout checking  

These are assessment-domain utilities, not LLM agent tool helpers.
"""

import time
from typing import Any, Dict, Optional

from src.utils.logging import get_logger

logger = get_logger(__name__)


# =============================================================================
# Assessment Domain Helpers
# =============================================================================

def create_task_result(
    task_id: str,
    benchmark: str,
    task_index: int,
    success: bool,
    final_reward: float,
    done: bool,
    truncated: bool,
    metrics: Dict[str, int],
    completion_time: float,
    **extra_fields
) -> Dict[str, Any]:
    """
    Create standardized task result dictionary.
    
    Args:
        task_id: Task identifier
        benchmark: Benchmark name
        task_index: Task index in plan
        success: Whether task succeeded
        final_reward: Final reward value
        done: Whether task is done
        truncated: Whether task was truncated
        metrics: Efficiency metrics
        completion_time: Time taken to complete
        **extra_fields: Additional fields (error, timeout, etc.)
        
    Returns:
        Standardized task result dictionary
    """
    result = {
        "task_id": task_id,
        "benchmark": benchmark,
        "task_index": task_index,
        "success": success,
        "final_reward": float(final_reward),
        "done": done,
        "truncated": truncated,
        "metrics": metrics,
        "completion_time": completion_time,
    }
    result.update(extra_fields)
    return result


def store_task_result(
    context: Any,
    task_success: bool,
    error_message: Optional[str] = None
) -> bool:
    """
    Update context state after task completion.
    
    Note: Task results are now stored directly in AssessmentTracker.
    This function just updates the context flags.
    
    Args:
        context: Agent context object
        task_success: Whether task succeeded
        error_message: Optional error message
        
    Returns:
        True (always succeeds)
    """
    # Update main context
    context.task_success = task_success
    context.error_message = error_message
    
    # Get reward from tracker if available
    if hasattr(context, 'assessment_tracker') and context.assessment_tracker:
        context.final_reward = context.assessment_tracker.get_success_rate()
    
    return True


def check_activity_timeout(
    current_mcp_calls: int,
    last_mcp_calls: int,
    last_activity_time: float,
    inactivity_threshold: float = 12.0
) -> tuple[bool, float]:
    """
    Check if Purple Agent has timed out due to inactivity.
    
    Args:
        current_mcp_calls: Current MCP call count
        last_mcp_calls: Last recorded MCP call count
        last_activity_time: Timestamp of last activity
        inactivity_threshold: Seconds of inactivity before timeout
        
    Returns:
        Tuple of (is_timeout, time_since_activity)
    """
    # Update last activity time if there's new activity
    if current_mcp_calls > last_mcp_calls:
        return False, 0.0
    
    time_since_activity = time.time() - last_activity_time
    return time_since_activity > inactivity_threshold, time_since_activity


__all__ = [
    "create_task_result",
    "store_task_result", 
    "check_activity_timeout",
]