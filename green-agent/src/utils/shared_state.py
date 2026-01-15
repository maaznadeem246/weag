"""
Shared state for communication between green agent and MCP subprocess.

Uses a JSON file for inter-process communication since MCP runs as stdio subprocess.
"""

import json
import os
import tempfile
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
import threading
import time

from src.utils.logging import get_logger

# Default maximum tool calls per task (centralized constant)
DEFAULT_MAX_TOOL_CALLS = 6

logger = get_logger(__name__)


@dataclass
class EvaluationState:
    """
    Shared evaluation state between green agent and MCP subprocess.
    
    Written by MCP on each tool invocation.
    Read by green agent during monitoring.
    """
    session_id: str = ""
    benchmark_id: str = ""  # Benchmark identifier (miniwob, webarena, etc.)
    task_id: str = ""  # Full task identifier (e.g., miniwob.click-test)
    
    # Task completion state (from BrowserGym)
    task_completed: bool = False
    task_success: bool = False
    final_reward: float = 0.0
    done: bool = False
    truncated: bool = False
    
    # Accumulated metrics
    total_tokens: int = 0
    total_latency_ms: int = 0
    action_count: int = 0
    observation_count: int = 0
    mcp_tool_invocations: int = 0
    
    # Tool call limit (per task)
    max_tool_calls: int = DEFAULT_MAX_TOOL_CALLS  # Default limit per task
    tool_calls_exceeded: bool = False
    
    # Tool invocation log (for streaming updates)
    last_tool: str = ""
    last_tool_timestamp: str = ""
    
    # Error state
    error: Optional[str] = None
    
    # Lifecycle
    initialized: bool = False
    cleanup_called: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EvaluationState":
        """Create from dictionary."""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class SharedStateManager:
    """
    Manages shared state file for green agent ↔ MCP communication.
    
    Usage:
        # In MCP (writer):
        manager = SharedStateManager(session_id)
        manager.update_metrics(tokens=100, latency_ms=50)
        manager.mark_completed(reward=1.0, done=True)
        
        # In Green Agent (reader):
        manager = SharedStateManager(session_id)
        state = manager.read_state()
        if state.cleanup_called:
            # Evaluation complete
    """
    
    def __init__(self, session_id: str, state_dir: Optional[str] = None, 
                 benchmark_id: str = "", task_id: str = ""):
        """
        Initialize shared state manager.
        
        Args:
            session_id: Unique session identifier
            state_dir: Directory for state files (defaults to temp dir)
            benchmark_id: Benchmark identifier (miniwob, webarena, etc.)
            task_id: Full task identifier (e.g., miniwob.click-test)
        """
        self.session_id = session_id
        self.benchmark_id = benchmark_id
        self.task_id = task_id
        self.state_dir = Path(state_dir) if state_dir else Path(tempfile.gettempdir())
        self.state_file = self.state_dir / f"browsergym_eval_{session_id}.json"
        self._lock = threading.Lock()
        self._state = EvaluationState(
            session_id=session_id, 
            benchmark_id=benchmark_id,
            task_id=task_id
        )
    
    def initialize(self) -> None:
        """Initialize state file (called by MCP on initialize_environment)."""
        self._state = EvaluationState(
            session_id=self.session_id, 
            benchmark_id=self.benchmark_id,
            task_id=self.task_id,
            initialized=True
        )
        self._write_state()
        logger.debug(f"Initialized shared state: {self.state_file}")
    
    def read_state(self) -> EvaluationState:
        """
        Read current state from file.
        
        Returns:
            Current evaluation state (or empty state if file doesn't exist)
        """
        try:
            if self.state_file.exists():
                with open(self.state_file, 'r') as f:
                    data = json.load(f)
                    return EvaluationState.from_dict(data)
        except Exception as e:
            logger.warning(f"Failed to read state file: {e}")
        
        return EvaluationState(session_id=self.session_id)
    
    def _write_state(self) -> None:
        """Write current state to file."""
        try:
            with self._lock:
                self.state_file.parent.mkdir(parents=True, exist_ok=True)
                with open(self.state_file, 'w') as f:
                    json.dump(self._state.to_dict(), f, indent=2)
        except Exception as e:
            logger.error(f"Failed to write state file: {e}")
    
    def update_tool_invocation(self, tool_name: str) -> None:
        """Record a tool invocation."""
        self._state.mcp_tool_invocations += 1
        self._state.last_tool = tool_name
        self._state.last_tool_timestamp = datetime.utcnow().isoformat()
        self._write_state()
    
    def check_tool_limit(self) -> bool:
        """
        Check if tool call limit has been exceeded.
        
        Returns:
            True if limit exceeded, False otherwise
        """
        if self._state.mcp_tool_invocations >= self._state.max_tool_calls:
            self._state.tool_calls_exceeded = True
            self._state.truncated = True
            self._state.task_completed = True
            self._write_state()
            return True
        return False
    
    def set_max_tool_calls(self, limit: int) -> None:
        """Set the maximum tool calls allowed per task."""
        self._state.max_tool_calls = limit
        self._write_state()
    
    def add_tokens(self, tokens: int) -> None:
        """Add tokens to cumulative count."""
        self._state.total_tokens += tokens
        self._state.observation_count += 1
        self._write_state()
    
    def add_latency(self, latency_ms: int) -> None:
        """Add latency to cumulative time."""
        self._state.total_latency_ms += latency_ms
        self._write_state()
    
    def add_actions(self, count: int) -> None:
        """Add to action count."""
        self._state.action_count += count
        self._write_state()
    
    def update_task_state(self, reward: float, done: bool, truncated: bool) -> None:
        """
        Update task completion state from BrowserGym step result.
        
        Args:
            reward: Reward from environment
            done: Task completion flag
            truncated: Episode truncation flag
        """
        self._state.final_reward = max(self._state.final_reward, reward)
        self._state.done = done
        self._state.truncated = truncated
        
        # Task is successful if done=True (BrowserGym SDK signals task completion)
        # Note: miniwob tasks return done=True with reward=0 for successful completion
        if done or truncated:
            self._state.task_completed = True
            # Success based on done flag (done=True means task goal achieved)
            # or positive reward for benchmarks that use reward signals
            self._state.task_success = done or self._state.final_reward > 0
        
        self._write_state()

    def reset_for_new_task(self, task_id: str, benchmark_id: str = "") -> None:
        """Reset task-specific fields for running another task in the same assessment.

        This keeps cumulative metrics (tokens/latency/actions/tool calls) intact,
        but clears completion/reward/error fields so the Green Agent can monitor
        the next task independently.

        Args:
            task_id: New task identifier (e.g., miniwob.click-test)
            benchmark_id: Benchmark identifier (e.g., miniwob)
        """
        self._state.task_id = task_id
        if benchmark_id:
            self._state.benchmark_id = benchmark_id

        # Clear task completion state
        self._state.task_completed = False
        self._state.task_success = False
        self._state.final_reward = 0.0
        self._state.done = False
        self._state.truncated = False
        self._state.error = None
        
        # Reset tool call tracking for new task
        self._state.mcp_tool_invocations = 0
        self._state.tool_calls_exceeded = False

        # Clear last-tool markers (optional, but avoids confusion in logs)
        self._state.last_tool = ""
        self._state.last_tool_timestamp = ""

        self._write_state()
    
    def mark_task_completed(self, success: bool = False, reason: str = "") -> None:
        """
        Explicitly mark the current task as completed.
        
        Used when task ends due to timeout, error, or explicit signal
        rather than BrowserGym done/truncated flags.
        
        Args:
            success: Whether the task was successful
            reason: Reason for completion (e.g., "timeout", "error", "explicit")
        """
        self._state.task_completed = True
        self._state.task_success = success
        if reason == "timeout":
            self._state.truncated = True
        if reason and not self._state.error:
            self._state.error = f"Task ended: {reason}"
        self._write_state()
        logger.info(f"Task marked completed: success={success}, reason={reason}")
    
    def mark_cleanup_called(self) -> None:
        """Mark that cleanup_environment was called."""
        self._state.cleanup_called = True
        self._state.task_completed = True
        # Final determination of task success
        self._state.task_success = self._state.final_reward > 0
        self._write_state()
    
    def set_error(self, error: str) -> None:
        """Set error state."""
        self._state.error = error
        self._write_state()
    
    def cleanup(self) -> None:
        """Remove state file."""
        try:
            if self.state_file.exists():
                self.state_file.unlink()
                logger.debug(f"Cleaned up state file: {self.state_file}")
        except Exception as e:
            logger.warning(f"Failed to cleanup state file: {e}")
    
    def get_state(self) -> EvaluationState:
        """Get current in-memory state (for MCP use)."""
        return self._state


# Global state manager instance (for MCP subprocess)
_global_state_manager: Optional[SharedStateManager] = None


def get_state_manager() -> Optional[SharedStateManager]:
    """Get global state manager instance."""
    return _global_state_manager


def set_state_manager(manager: SharedStateManager) -> None:
    """Set global state manager instance."""
    global _global_state_manager
    _global_state_manager = manager


def create_state_manager(session_id: str, benchmark_id: str = "", task_id: str = "") -> SharedStateManager:
    """Create and set global state manager."""
    manager = SharedStateManager(session_id, benchmark_id=benchmark_id, task_id=task_id)
    set_state_manager(manager)
    return manager
