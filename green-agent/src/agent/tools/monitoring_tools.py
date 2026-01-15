"""
Monitoring tools for evaluation progress tracking.

Tools for:
- Context details retrieval
- Progress monitoring with adaptive polling
- Current state retrieval
"""

import time
from datetime import datetime
from typing import Any
from agents.run_context import RunContextWrapper

from src.agent.context import AgentContext, MonitoringResult
from src.agent.monitoring import check_evaluation_state
from src.utils.logging import get_logger

logger = get_logger(__name__)


# =============================================================================
# Context Details Tool
# =============================================================================

async def get_context_details(ctx: RunContextWrapper[AgentContext]) -> dict:
    """
    Get current context details including task configuration and evaluation state.
    
    Use this tool to inspect:
    - Task configuration (task_id, benchmark, timeout)
    - MCP server state (spawned, session_id, connection details)
    - Evaluation progress (complete, success, reward)
    - Incoming messages from Purple agent and system
    - Purple agent identification
    
    Returns dict with all context fields for decision-making.
    """
    context: AgentContext = ctx.context
    
    # Normalize start_time to unix timestamp
    if isinstance(context.start_time, datetime):
        start_ts = context.start_time.timestamp()
    else:
        start_ts = float(context.start_time)
    
    elapsed = time.time() - start_ts
    
    return {
        "status": "success",
        "context": {
            # Task configuration
            "session_id": context.session_id,
            "task_id": context.task_id,
            "benchmark": context.benchmark,
            "timeout_seconds": context.timeout_seconds,
            "max_timeout": context.max_timeout,  # Deprecated alias
            
            # Purple agent info
            "purple_agent_id": context.purple_agent_id,
            
            # MCP server state
            "mcp_server_spawned": context.mcp_server_spawned,
            "mcp_session_id": context.mcp_session_id,
            "mcp_connection_details": context.mcp_connection_details,
            
            # Evaluation state
            "evaluation_complete": context.evaluation_complete,
            "task_success": context.task_success,
            "final_reward": context.final_reward,
            "current_step": context.current_step,
            "error_message": context.error_message,
            
            # Timing
            "start_time": start_ts,
            "elapsed_seconds": elapsed,
            
            # Messages
            "incoming_messages": list(context.incoming_messages),
            "message_count": len(context.incoming_messages),
            
            # Background monitoring
            "background_monitor_active": context.background_monitor_active,
            "background_monitor_interval": context.background_monitor_interval,
        },
        "message": f"Context retrieved: task={context.task_id}, benchmark={context.benchmark}, elapsed={elapsed:.1f}s"
    }


# =============================================================================
# Get Current State Tool
# =============================================================================

async def get_current_state(ctx: RunContextWrapper[AgentContext]) -> dict:
    """
    Retrieve current task state from AgentContext.
    
    Returns quick snapshot of:
    - task_id, benchmark
    - step_count
    - elapsed_time, remaining_timeout
    
    Useful for agent reasoning about current progress without full monitoring.
    """
    context: AgentContext = ctx.context
    
    # Normalize start_time to a unix timestamp (seconds)
    if isinstance(context.start_time, datetime):
        start_ts = context.start_time.timestamp()
    else:
        start_ts = float(context.start_time)

    now = time.time()
    elapsed_time = now - start_ts

    if isinstance(context.max_timeout, datetime):
        max_timeout_seconds = context.max_timeout.timestamp() - start_ts
    else:
        max_timeout_seconds = float(context.max_timeout)

    remaining_timeout = max_timeout_seconds - elapsed_time
    
    # Read state for step count
    state_manager = context.shared_state_manager
    state = state_manager.read_state()
    
    return {
        "task_id": context.task_id,
        "benchmark": context.benchmark,
        "session_id": context.session_id,
        "step_count": state.action_count,
        "elapsed_time": elapsed_time,
        "remaining_timeout": remaining_timeout,
        "mcp_server_healthy": context.mcp_server_healthy,
        "tools_verified": context.mcp_tools_verified,
    }


__all__ = [
    "monitor_progress",
    "get_current_state",
]
