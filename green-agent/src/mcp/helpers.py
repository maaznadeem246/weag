"""
Helper functions for MCP server operations.

Extracted from mcp_server.py to improve modularity and testability.
"""

from typing import Dict, Any, Optional, List
from datetime import datetime

from src.environment.action_entities import ActionRequest, ActionBatch
from src.environment.entities import EnvironmentSession
from src.utils.logging import get_logger

logger = get_logger(__name__)


def parse_action_data(action_data: Dict[str, Any], index: int) -> ActionRequest:
    """
    Parse raw action dictionary into ActionRequest object.
    
    Supports multiple field names for compatibility: 'action', 'action_type', 'name'.
    
    Args:
        action_data: Raw action dictionary from tool call
        index: Action index in batch (for error reporting)
        
    Returns:
        Validated ActionRequest object
        
    Raises:
        ValueError: If action data is invalid or missing required fields
    """
    try:
        # Support multiple field names for compatibility
        action_value = (
            action_data.get("action") or 
            action_data.get("action_type") or 
            action_data.get("name", "")
        )
        
        action_request = ActionRequest(
            action=action_value,
            bid=action_data.get("bid"),
            text=action_data.get("text"),
            url=action_data.get("url"),
            direction=action_data.get("direction"),
            dx=action_data.get("dx"),
            dy=action_data.get("dy"),
            key=action_data.get("key"),
            key_comb=action_data.get("key_comb"),
            tab_index=action_data.get("tab_index"),
            options=action_data.get("options"),
            button=action_data.get("button"),
            from_bid=action_data.get("from_bid"),
            to_bid=action_data.get("to_bid"),
        )
        
        # Validate action has required fields
        action_request.validate()
        return action_request
        
    except Exception as e:
        logger.error(
            f"Action validation failed at index {index}",
            extra={"action_index": index, "raw_action_data": action_data, "error": str(e)}
        )
        raise ValueError(f"Invalid action at index {index}: {str(e)}")


def parse_action_batch(actions: List[Dict[str, Any]]) -> List[ActionRequest]:
    """
    Parse and validate a batch of actions.
    
    Args:
        actions: List of raw action dictionaries
        
    Returns:
        List of validated ActionRequest objects
        
    Raises:
        ValueError: If any action is invalid or batch is too large
    """
    if not actions:
        raise ValueError("No actions provided")
    
    if len(actions) > 50:
        raise ValueError(f"Batch size {len(actions)} exceeds limit of 50 actions")
    
    return [parse_action_data(action_data, i) for i, action_data in enumerate(actions)]


def format_action_result(
    observation: Dict[str, Any],
    reward: float,
    done: bool,
    truncated: bool,
    action_index: int,
    error: Optional[str] = None
) -> Dict[str, Any]:
    """
    Format action execution result into standard dictionary.
    
    Args:
        observation: Filtered observation after action
        reward: Reward value from environment
        done: Whether task is complete
        truncated: Whether episode was truncated
        action_index: Index of action in batch
        error: Optional error message
        
    Returns:
        Formatted result dictionary
    """
    return {
        "observation": observation,
        "reward": float(reward),
        "done": bool(done),
        "truncated": bool(truncated),
        "error": error,
        "action_index": action_index,
    }


def format_batch_result(
    results: List[Dict[str, Any]],
    batch_id: str,
    start_time: datetime,
    early_termination: bool = False,
    error: Optional[str] = None
) -> Dict[str, Any]:
    """
    Format batch execution result.
    
    Args:
        results: List of individual action results
        batch_id: Unique identifier for this batch
        start_time: Batch start timestamp
        early_termination: Whether batch stopped early
        error: Optional error message for entire batch
        
    Returns:
        Formatted batch result dictionary
    """
    latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
    
    # Check if any action resulted in task completion
    task_completed = any(r.get("done", False) for r in results)
    final_reward = results[-1].get("reward", 0.0) if results else 0.0
    
    result = {
        "results": results,
        "batch_id": batch_id,
        "latency_ms": latency_ms,
        "early_termination": early_termination,
        # Clear top-level flags for Purple Agent to check
        "task_completed": task_completed,
        "final_reward": final_reward,
    }
    
    # Add explicit message when task is done
    if task_completed:
        result["message"] = "✅ TASK COMPLETED - Stop calling tools. Return your final answer."
    
    if error:
        result["error"] = error
    
    return result


def create_tool_limit_response(tool_count: int, max_calls: int) -> Dict[str, Any]:
    """
    Create response for tool call limit exceeded scenario.
    
    Args:
        tool_count: Current tool call count
        max_calls: Maximum allowed calls
        
    Returns:
        Tool limit exceeded response dictionary
    """
    return {
        "results": [],
        "batch_id": "limit_exceeded",
        "latency_ms": 0,
        "early_termination": True,
        "error": f"Tool call limit exceeded ({max_calls} calls). Task terminated. Green Agent will send next task.",
        "task_terminated": True,
        "tool_calls_used": tool_count,
        "max_tool_calls": max_calls,
    }


def should_terminate_batch(done: bool, error: Optional[str]) -> bool:
    """
    Determine if batch execution should terminate early.
    
    Args:
        done: Whether task is complete
        error: Error message if action failed
        
    Returns:
        True if batch should terminate early
    """
    return done or error is not None


def log_action_payload(actions: List[Dict[str, Any]], logger_func) -> None:
    """
    Log action payload for debugging (with truncation for large payloads).
    
    Args:
        actions: List of action dictionaries
        logger_func: Logger function to use
    """
    try:
        import json
        payload_json = json.dumps(actions, default=str)
        if len(payload_json) < 1000:
            logger_func(f"execute_actions payload: {payload_json}")
        else:
            preview = payload_json[:1000] + "...(truncated)"
            logger_func(f"execute_actions payload_preview: {preview}")
    except Exception:
        logger.debug("execute_actions payload (could not json-dump)", extra={"actions": actions})
