"""
Shared monitoring logic for evaluation progress.

Provides:
- check_evaluation_state: Core monitoring logic used by both agent tool and system
- BackgroundMonitor: System background monitoring task that runs in parallel with agent
- Message prefixing utilities for system and purple agent messages
"""

import asyncio
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from src.utils.logging import get_logger

logger = get_logger(__name__)
from src.agent.message_utils import format_system_message, format_purple_agent_message


def check_evaluation_state(
    shared_state_manager: Any,
    task_id: str,
    benchmark: str
) -> Dict[str, Any]:
    """
    Check current evaluation state from shared state manager.
    
    This is the CORE monitoring logic used by:
    1. Background monitor - runs every 3-4 seconds automatically
    2. Other monitoring components as needed
    
    Args:
        shared_state_manager: SharedStateManager instance
        task_id: Task identifier
        benchmark: Benchmark name
        
    Returns:
        Dict with monitoring results:
        {
            "is_complete": bool,
            "task_success": bool,
            "final_reward": float,
            "total_tokens": int,
            "total_latency_ms": float,
            "action_count": int,
            "observation_count": int,
            "mcp_tool_invocations": int,
            "error": Optional[str],
            "done": bool,
            "truncated": bool,
            "cleanup_called": bool,
            "task_completed": bool
        }
    """
    try:
        # Read shared state
        state = shared_state_manager.read_state()
        
        # Determine if evaluation is complete
        is_complete = state.cleanup_called or (state.task_completed and state.done)
        
        return {
            "is_complete": is_complete,
            "task_success": state.task_success,
            "final_reward": state.final_reward,
            "total_tokens": state.total_tokens,
            "total_latency_ms": state.total_latency_ms,
            "action_count": state.action_count,
            "observation_count": state.observation_count,
            "mcp_tool_invocations": state.mcp_tool_invocations,
            "error": state.error,
            "done": state.done,
            "truncated": state.truncated,
            "cleanup_called": state.cleanup_called,
            "task_completed": state.task_completed,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error(f"Error checking evaluation state: {e}", exc_info=True)
        return {
            "is_complete": False,
            "task_success": False,
            "final_reward": 0.0,
            "total_tokens": 0,
            "total_latency_ms": 0.0,
            "action_count": 0,
            "observation_count": 0,
            "mcp_tool_invocations": 0,
            "error": str(e),
            "done": False,
            "truncated": False,
            "cleanup_called": False,
            "task_completed": False,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }





class BackgroundMonitor:
    """
    Background monitoring task that runs in parallel with agent execution.
    
    Responsibilities:
    1. Poll shared state every N seconds (default: 3s)
    2. Detect evaluation state changes (completion, errors, timeouts)
    3. Send formatted messages to agent via context.incoming_messages
    4. Stop automatically when evaluation completes or timeout reaches
    """
    
    def __init__(
        self,
        agent_context: Any,
        interval: float = 3.0,
        timeout_seconds: int = 600
    ):
        """
        Initialize background monitor.
        
        Args:
            agent_context: AgentContext instance
            interval: Polling interval in seconds (default: 3.0)
            timeout_seconds: Maximum evaluation timeout
        """
        self.context = agent_context
        self.interval = interval
        self.timeout_seconds = timeout_seconds
        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
        
    async def start(self) -> None:
        """Start background monitoring task."""
        if self._task is not None:
            logger.warning("Background monitor already running")
            return
        
        self.context.background_monitor_active = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info(f"Background monitor started (interval: {self.interval}s, timeout: {self.timeout_seconds}s)")
    
    async def stop(self) -> None:
        """Stop background monitoring task."""
        if self._task is None:
            return
        
        self._stop_event.set()
        await self._task
        self._task = None
        self.context.background_monitor_active = False
        logger.info("Background monitor stopped")
    
    async def _monitor_loop(self) -> None:
        """Main monitoring loop - polls shared state and sends updates to agent."""
        start_time = datetime.now(timezone.utc)
        last_state = None
        
        try:
            while not self._stop_event.is_set():
                # Check timeout
                elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
                if elapsed > self.timeout_seconds:
                    msg = format_system_message(
                        f"Evaluation timeout reached ({self.timeout_seconds}s). Consider generating final artifact."
                    )
                    self.context.incoming_messages.append(msg)
                    logger.warning(f"Background monitor: timeout reached ({self.timeout_seconds}s)")
                    break
                
                # Check evaluation state using shared monitoring logic
                state = check_evaluation_state(
                    self.context.shared_state_manager,
                    self.context.task_id,
                    self.context.benchmark
                )
                
                # Detect changes and send messages to agent
                if state != last_state:
                    # Send state update to agent
                    if state["is_complete"]:
                        msg = format_system_message(
                            f"Evaluation complete! Task success: {state['task_success']}, "
                            f"Final reward: {state['final_reward']:.4f}, "
                            f"Total tokens: {state['total_tokens']}, "
                            f"Action count: {state['action_count']}"
                        )
                        self.context.incoming_messages.append(msg)
                        logger.info("Background monitor: evaluation complete, stopping monitor")
                        break
                    
                    elif state["error"]:
                        msg = format_system_message(f"MCP error detected: {state['error']}")
                        self.context.incoming_messages.append(msg)
                        logger.error(f"Background monitor: error detected: {state['error']}")
                        break
                    
                    elif state["task_completed"] and not state["cleanup_called"]:
                        msg = format_system_message(
                            f"Task completed (done: {state['done']}, truncated: {state['truncated']}). "
                            "Waiting for cleanup_environment call..."
                        )
                        self.context.incoming_messages.append(msg)
                        logger.info("Background monitor: task completed, waiting for cleanup")
                    
                    # Update state tracking with significant changes only
                    if (
                        last_state is None or
                        state["is_complete"] != last_state.get("is_complete") or
                        state["error"] != last_state.get("error") or
                        state["task_completed"] != last_state.get("task_completed")
                    ):
                        last_state = state
                
                # Wait for next poll interval
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=self.interval)
                    break  # Stop event was set
                except asyncio.TimeoutError:
                    continue  # Continue monitoring
        
        except Exception as e:
            logger.error(f"Background monitor error: {e}", exc_info=True)
            msg = format_system_message(f"Background monitor error: {e}")
            self.context.incoming_messages.append(msg)
        
        finally:
            self.context.background_monitor_active = False
            logger.info("Background monitor loop exited")
