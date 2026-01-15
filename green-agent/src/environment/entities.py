"""
Environment management entities for BrowserGym Green Agent.

Defines EnvironmentConfig and EnvironmentSession for MCP tool lifecycle.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Any
import uuid


class CleanupStatus(Enum):
    """Environment cleanup state."""
    ACTIVE = "active"
    CLEANUP_REQUESTED = "cleanup_requested"
    CLEANED = "cleaned"


@dataclass
class EnvironmentConfig:
    """
    Configuration for BrowserGym environment initialization.
    
    Attributes:
        task_id: Benchmark task identifier (e.g., "miniwob.click-test")
        start_url: Optional override for starting URL
        max_steps: Optional maximum evaluation steps
        seed: Optional random seed for reproducibility
    """
    task_id: str
    start_url: Optional[str] = None
    max_steps: Optional[int] = None
    seed: Optional[int] = None
    task_kwargs: Optional[dict[str, Any]] = None
    wait_for_user_message: Optional[bool] = None
    viewport: Optional[dict[str, int]] = None
    
    # Supported BrowserGym benchmarks
    SUPPORTED_BENCHMARKS = [
        "miniwob",
        "webarena",
        "visualwebarena",
        "workarena",
        "assistantbench",
        "weblinx"
    ]
    
    def get_benchmark(self) -> str:
        """
        Extract benchmark name from task_id.
        
        Supports all six BrowserGym benchmarks:
        - miniwob: "miniwob.task-name"
        - webarena: "webarena.task-name"
        - visualwebarena: "visualwebarena.task-name"
        - workarena: "workarena.task-name"
        - assistantbench: "assistantbench.task-name"
        - weblinx: "weblinx.task-name"
        
        Returns:
            Benchmark name or "unknown" if not recognized
        """
        if "." not in self.task_id:
            return "unknown"
        
        benchmark = self.task_id.split(".")[0].lower()
        return benchmark if benchmark in self.SUPPORTED_BENCHMARKS else "unknown"
    
    def validate_task_id(self) -> tuple[bool, str]:
        """
        Validate task_id format matches benchmark patterns.
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not self.task_id:
            return False, "task_id cannot be empty"
        
        if "." not in self.task_id:
            return False, "task_id must be in format 'benchmark.task-name'"
        
        parts = self.task_id.split(".")
        if len(parts) < 2:
            return False, "task_id must contain at least benchmark and task name"
        
        benchmark = parts[0].lower()
        if benchmark not in self.SUPPORTED_BENCHMARKS:
            return False, f"Unsupported benchmark '{benchmark}'. Supported: {', '.join(self.SUPPORTED_BENCHMARKS)}"
        
        task_name = ".".join(parts[1:])
        if not task_name:
            return False, "task_id must include task name after benchmark"
        
        return True, ""
    
    def get_benchmark_specific_config(self) -> dict[str, Any]:
        """
        Get benchmark-specific configuration parameters for gym.make().
        
        Note: seed is NOT passed to gym.make() - it's used in env.reset()
        Note: max_steps, start_url are task-specific, not environment creation params
        
        Returns:
            Dict of kwargs passed to gym.make()
        """
        config: dict[str, Any] = {}

        # If caller provided task_kwargs explicitly, pass through
        if self.task_kwargs:
            config["task_kwargs"] = self.task_kwargs
        elif self.start_url:
            # Convenience: allow start_url to flow into task_kwargs for openended-style tasks
            config["task_kwargs"] = {"start_url": self.start_url}

        if self.wait_for_user_message is not None:
            config["wait_for_user_message"] = self.wait_for_user_message

        if self.viewport:
            config["viewport"] = self.viewport

        # NOTE: max_steps is NOT passed to gym.make() - BrowserEnv doesn't accept it
        # max_steps is managed externally by the agent/wrapper, not the environment

        return config


@dataclass
class EnvironmentSession:
    """
    Represents a single BrowserGym environment instance.
    
    Tracks lifecycle from initialize_environment to cleanup_environment.
    
    Attributes:
        session_id: Unique session identifier (UUID)
        task_id: Benchmark task identifier
        benchmark: Benchmark name (miniwob, webarena, etc.)
        config: Configuration used for initialization
        env_instance: BrowserGym environment object (Gymnasium.Env)
        initialized_at: Environment creation timestamp
        last_action_at: Most recent action timestamp
        cleanup_status: Current cleanup state
        current_observation: Latest observation from environment
        action_history: List of executed actions
        browser_pids: List of PIDs for browser processes spawned by this session
    """
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str = ""
    benchmark: str = ""
    config: Optional[EnvironmentConfig] = None
    env_instance: Optional[Any] = None  # Gymnasium.Env type
    initialized_at: datetime = field(default_factory=datetime.utcnow)
    last_action_at: Optional[datetime] = None
    cleanup_status: CleanupStatus = CleanupStatus.ACTIVE
    current_observation: Optional[dict] = None
    action_history: list = field(default_factory=list)
    browser_pids: list = field(default_factory=list)  # PIDs of spawned browser processes
    
    def update_observation(self, observation: dict) -> None:
        """Update current observation and timestamp."""
        self.current_observation = observation
        self.last_action_at = datetime.utcnow()
    
    def add_action(self, action: dict) -> None:
        """Add action to history."""
        self.action_history.append({
            "action": action,
            "timestamp": datetime.utcnow().isoformat()
        })
    
    def request_cleanup(self) -> None:
        """Mark session for cleanup."""
        self.cleanup_status = CleanupStatus.CLEANUP_REQUESTED
    
    def mark_cleaned(self) -> None:
        """Mark session as cleaned."""
        self.cleanup_status = CleanupStatus.CLEANED
    
    @property
    def is_active(self) -> bool:
        """Check if session is active (not cleaned up)."""
        return self.cleanup_status == CleanupStatus.ACTIVE and self.env_instance is not None
