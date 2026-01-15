"""
Activity Watchdog for Green Agent orchestration.

Provides centralized activity tracking with auto-reset timeouts using modern Python patterns:

1. Context Manager Pattern (recommended):
   async with watchdog.track("operation_name"):
       await some_long_operation()
   # Automatically resets timer on entry and records completion

2. Decorator Pattern:
   @watchdog.tracked("my_function")
   async def my_function():
       ...
   # Automatically tracks activity around function calls

3. Direct API (for MCP/A2A hooks):
   watchdog.pulse("mcp_tool", "execute_actions")
   # Simple one-liner to reset timer

Activity sources that reset the timer:
- Purple Agent MCP tool calls
- Purple Agent A2A messages  
- Green Agent LLM tool calls
- Any significant operation
"""

import asyncio
import functools
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional, Callable, Any, Coroutine, TypeVar, ParamSpec
from dataclasses import dataclass, field
from enum import Enum

from src.utils.logging import get_logger

logger = get_logger(__name__)

P = ParamSpec('P')
T = TypeVar('T')


class ActivityType(Enum):
    """Types of activity that reset the watchdog timer."""
    MCP_TOOL_CALL = "mcp_tool"
    A2A_MESSAGE = "a2a_message"
    GREEN_AGENT_ACTION = "green_action"
    LLM_RESPONSE = "llm_response"
    ENVIRONMENT_STEP = "env_step"
    HEARTBEAT = "heartbeat"


@dataclass
class ActivityRecord:
    """Record of a single activity event."""
    activity_type: ActivityType
    timestamp: float  # Unix timestamp
    details: str = ""
    
    @property
    def age_seconds(self) -> float:
        """How many seconds ago this activity occurred."""
        return time.time() - self.timestamp


class ActivityWatchdog:
    """
    Centralized activity tracking with auto-reset timeouts.
    
    Modern Python patterns for clean integration:
    
    # Context manager (recommended for scoped operations)
    async with watchdog.track("sending_task"):
        await send_task_to_purple()
    
    # Decorator (for functions that should always be tracked)
    @watchdog.tracked("wait_completion")
    async def wait_for_completion():
        ...
    
    # Simple pulse (for hooks in existing code)
    watchdog.pulse("mcp_tool", "execute_actions")
    """
    
    def __init__(
        self, 
        timeout_seconds: float = 8.0,
        first_task_timeout: float = 20.0,
        on_timeout: Optional[Callable[[], None]] = None
    ):
        """
        Initialize the activity watchdog with differentiated timeouts.
        
        Args:
            timeout_seconds: Seconds of inactivity before timeout after first interaction (default: 8)
            first_task_timeout: Longer timeout for initial setup before first pulse (default: 20)
            on_timeout: Optional callback when timeout occurs
        """
        self._timeout_seconds = timeout_seconds
        self._initial_timeout = first_task_timeout
        self._on_timeout = on_timeout
        self._lock = threading.RLock()
        
        # Initialize with current time (evaluation start)
        self._last_activity_time = time.time()
        self._last_activity_type = ActivityType.HEARTBEAT
        self._last_activity_details = "watchdog_initialized"
        self._activity_count = 0
        self._is_paused = False
        self._is_first_task = True  # Track if we're still waiting for first interaction
        
        # Activity history (limited to last N for debugging)
        self._history: list[ActivityRecord] = []
        self._max_history = 100
        
        logger.info(
            f"✅ Created global ActivityWatchdog with {timeout_seconds}s timeout "
            f"(initial: {first_task_timeout}s until first interaction)"
        )
    
    # ========================================
    # Modern Python Patterns
    # ========================================
    
    @asynccontextmanager
    async def track(self, operation: str = "operation"):
        """
        Context manager that tracks activity for a scoped operation.
        
        Resets timer on entry and records completion on exit.
        
        Usage:
            async with watchdog.track("sending_task"):
                await send_task_to_purple()
        """
        self.pulse(ActivityType.GREEN_AGENT_ACTION, f"{operation}:start")
        try:
            yield self
        finally:
            self.pulse(ActivityType.GREEN_AGENT_ACTION, f"{operation}:end")
    
    def tracked(self, operation: str = ""):
        """
        Decorator that tracks activity around async function calls.
        
        Usage:
            @watchdog.tracked("my_operation")
            async def my_function():
                ...
        """
        def decorator(func: Callable[P, Coroutine[Any, Any, T]]) -> Callable[P, Coroutine[Any, Any, T]]:
            op_name = operation or func.__name__
            
            @functools.wraps(func)
            async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
                async with self.track(op_name):
                    return await func(*args, **kwargs)
            
            return wrapper
        return decorator
    
    def pulse(
        self, 
        activity_type: ActivityType | str = ActivityType.HEARTBEAT,
        details: str = ""
    ) -> None:
        """
        Record an activity pulse and reset the timeout timer.
        
        Simple one-liner for hooks in existing code:
            watchdog.pulse("mcp_tool", "execute_actions")
        
        After the first real interaction (MCP tool call, A2A message, etc.),
        the timeout switches from initial (20s) to normal (8s).
        
        Args:
            activity_type: Type of activity (MCP_TOOL_CALL, A2A_MESSAGE, etc.)
            details: Optional details about the activity
        """
        with self._lock:
            now = time.time()
            
            # Convert string to enum if needed
            if isinstance(activity_type, str):
                try:
                    activity_type = ActivityType(activity_type)
                except ValueError:
                    activity_type = ActivityType.HEARTBEAT
            
            # Update state
            self._last_activity_time = now
            self._last_activity_type = activity_type
            self._last_activity_details = details
            self._activity_count += 1
            
            # Switch to normal timeout after first real interaction
            # (MCP tool calls, A2A messages, environment steps count as real interactions)
            if self._is_first_task and activity_type in (
                ActivityType.MCP_TOOL_CALL,
                ActivityType.A2A_MESSAGE,
                ActivityType.ENVIRONMENT_STEP,
            ):
                self._is_first_task = False
                logger.info(
                    f"🎯 First interaction detected ({activity_type.value}) - "
                    f"switching to {self._timeout_seconds}s timeout (from {self._initial_timeout}s)"
                )
            
            # Add to history
            record = ActivityRecord(activity_type, now, details)
            self._history.append(record)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history:]
            
            logger.debug(
                f"⚡ Activity pulse: {activity_type.value} - {details} "
                f"(count: {self._activity_count})"
            )
    
    # ========================================
    # Timeout Checking
    # ========================================
    
    @property
    def timeout_seconds(self) -> float:
        """Current timeout setting in seconds (dynamic based on first task status)."""
        with self._lock:
            return self._initial_timeout if self._is_first_task else self._timeout_seconds
    
    @timeout_seconds.setter
    def timeout_seconds(self, value: float) -> None:
        """Update timeout setting."""
        with self._lock:
            self._timeout_seconds = max(1.0, value)  # Minimum 1 second
            logger.debug(f"Watchdog timeout updated to {self._timeout_seconds}s")
    
    def mark_first_task_completed(self) -> None:
        """Mark that first task/interaction phase is completed, switch to normal timeout.
        
        Note: This is now also triggered automatically on first real interaction (pulse).
        """
        with self._lock:
            if self._is_first_task:
                self._is_first_task = False
                logger.info(
                    f"🎯 Initial phase completed - now using {self._timeout_seconds}s timeout "
                    f"(was {self._initial_timeout}s)"
                )
    
    @property
    def seconds_since_activity(self) -> float:
        """Seconds elapsed since last activity."""
        with self._lock:
            return time.time() - self._last_activity_time
    
    @property
    def time_remaining(self) -> float:
        """Seconds until timeout (negative if already timed out)."""
        with self._lock:
            return self._timeout_seconds - self.seconds_since_activity
    
    @property
    def is_timed_out(self) -> bool:
        """Check if inactivity timeout has been exceeded."""
        if self._is_paused:
            return False
            
        with self._lock:
            elapsed = self.seconds_since_activity
            current_timeout = self._initial_timeout if self._is_first_task else self._timeout_seconds
            timed_out = elapsed > current_timeout
            
            if timed_out:
                timeout_type = "first-task" if self._is_first_task else "standard"
                logger.warning(
                    f"⏰ Inactivity timeout ({timeout_type}): {elapsed:.1f}s > {current_timeout}s "
                    f"(last: {self._last_activity_type.value})"
                )
                if self._on_timeout:
                    try:
                        self._on_timeout()
                    except Exception as e:
                        logger.error(f"Timeout callback failed: {e}")
            
            return timed_out
    
    # ========================================
    # Activity-Aware Async Wait
    # ========================================
    
    async def wait_with_timeout(
        self,
        coro: Coroutine[Any, Any, T],
        check_interval: float = 0.5
    ) -> T:
        """
        Wait for a coroutine with activity-aware timeout.
        
        Unlike asyncio.wait_for which has a fixed timeout, this method
        periodically checks the watchdog and only times out if there has
        been no activity across the system.
        
        Args:
            coro: Coroutine to await
            check_interval: How often to check for timeout (seconds)
            
        Returns:
            Result of the coroutine
            
        Raises:
            asyncio.TimeoutError: If watchdog timeout exceeded
        """
        task = asyncio.create_task(coro)
        
        try:
            while not task.done():
                # Check if we should timeout
                if self.is_timed_out:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                    raise asyncio.TimeoutError(
                        f"Activity watchdog timeout: {self.seconds_since_activity:.1f}s inactivity"
                    )
                
                # Wait a bit then check again
                try:
                    return await asyncio.wait_for(
                        asyncio.shield(task),
                        timeout=check_interval
                    )
                except asyncio.TimeoutError:
                    # Just the check interval, not actual timeout
                    continue
            
            return task.result()
            
        except asyncio.CancelledError:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            raise
    
    # ========================================
    # Control Methods
    # ========================================
    
    def reset(self) -> None:
        """Explicitly reset the timer (equivalent to a heartbeat pulse)."""
        self.pulse(ActivityType.HEARTBEAT, "manual_reset")
    
    def pause(self) -> None:
        """Pause timeout checking (useful during expected delays)."""
        with self._lock:
            self._is_paused = True
            logger.debug("Watchdog paused")
    
    def resume(self) -> None:
        """Resume timeout checking and reset timer."""
        with self._lock:
            self._is_paused = False
            self._last_activity_time = time.time()
            logger.debug("Watchdog resumed")
    
    # ========================================
    # Status & Debugging
    # ========================================
    
    def get_status(self) -> dict:
        """Get current watchdog status as a dictionary."""
        with self._lock:
            return {
                "timeout_seconds": self._timeout_seconds,
                "seconds_since_activity": self.seconds_since_activity,
                "time_remaining": self.time_remaining,
                "last_activity_type": self._last_activity_type.value,
                "last_activity_details": self._last_activity_details,
                "activity_count": self._activity_count,
                "is_paused": self._is_paused,
                "is_timed_out": self.is_timed_out if not self._is_paused else False,
            }
    
    def get_recent_activity(self, count: int = 10) -> list[dict]:
        """Get recent activity records for debugging."""
        with self._lock:
            records = self._history[-count:]
            return [
                {
                    "type": r.activity_type.value,
                    "timestamp": r.timestamp,
                    "details": r.details,
                    "age_seconds": r.age_seconds
                }
                for r in records
            ]


# ========================================
# Global Watchdog Instance & Helpers
# ========================================

_global_watchdog: Optional[ActivityWatchdog] = None


def get_watchdog() -> Optional[ActivityWatchdog]:
    """Get the global activity watchdog instance."""
    return _global_watchdog


def create_watchdog(
    timeout_seconds: float = 8.0,
    first_task_timeout: float = 20.0
) -> ActivityWatchdog:
    """Create and set the global activity watchdog with differentiated timeouts.
    
    Args:
        timeout_seconds: Timeout after first interaction (default: 8s)
        first_task_timeout: Initial timeout before first interaction (default: 20s)
    """
    global _global_watchdog
    _global_watchdog = ActivityWatchdog(
        timeout_seconds=timeout_seconds,
        first_task_timeout=first_task_timeout
    )
    return _global_watchdog


def pulse(activity_type: ActivityType | str = ActivityType.HEARTBEAT, details: str = "") -> None:
    """Record activity pulse on the global watchdog if it exists."""
    if _global_watchdog:
        _global_watchdog.pulse(activity_type, details)


# Backwards compatibility aliases
def record_activity(activity_type: ActivityType | str, details: str = "") -> None:
    """Alias for pulse() - backwards compatibility."""
    pulse(activity_type, details)


def reset_watchdog() -> None:
    """Reset the global watchdog timer if it exists."""
    if _global_watchdog:
        _global_watchdog.reset()
