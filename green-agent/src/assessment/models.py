"""
Data models for assessment tracking.

Provides type-safe dataclasses for task entries, participants, and configuration.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class TaskStatus(Enum):
    """Status of a task in the assessment plan."""
    PENDING = "pending"           # Not yet sent
    SENT = "sent"                 # Sent to Purple Agent
    RUNNING = "running"           # Purple Agent is working on it
    COMPLETED = "completed"       # Finished successfully
    TIMEOUT = "timeout"           # Timed out
    FAILED = "failed"             # Failed (error or reward=0)
    SEND_TIMEOUT = "send_timeout" # Timeout during send
    TOOL_LIMIT = "tool_limit"     # Exceeded tool call limit
    
    def is_terminal(self) -> bool:
        """Check if this is a terminal (final) state."""
        return self in (
            TaskStatus.COMPLETED,
            TaskStatus.TIMEOUT, 
            TaskStatus.FAILED,
            TaskStatus.SEND_TIMEOUT,
            TaskStatus.TOOL_LIMIT,
        )


@dataclass
class TaskEntry:
    """
    Single task entry in the assessment plan.
    
    Tracks both the task definition and its execution result.
    """
    task_id: str
    benchmark: str
    index: int
    
    # Status tracking
    status: TaskStatus = TaskStatus.PENDING
    
    # Result data (populated after completion)
    success: bool = False
    final_reward: float = 0.0
    done: bool = False
    truncated: bool = False
    
    # Metrics
    metrics: Dict[str, int] = field(default_factory=lambda: {
        "tokens": 0,
        "latency_ms": 0,
        "actions": 0,
        "observations": 0,
        "mcp_calls": 0,
    })
    
    # Timing
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    completion_time_seconds: float = 0.0
    
    # Error tracking
    error_message: Optional[str] = None
    
    # State snapshot (for delta metrics calculation)
    start_snapshot: Optional[Dict[str, Any]] = None  # EvaluationState at task start
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "task_id": self.task_id,
            "benchmark": self.benchmark,
            "task_index": self.index,
            "status": self.status.value,
            "success": self.success,
            "final_reward": self.final_reward,
            "done": self.done,
            "truncated": self.truncated,
            "metrics": self.metrics.copy(),
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "completion_time": self.completion_time_seconds,
            "error": self.error_message,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskEntry":
        """Create from dictionary."""
        return cls(
            task_id=data["task_id"],
            benchmark=data["benchmark"],
            index=data.get("task_index", data.get("index", 0)),
            status=TaskStatus(data.get("status", "pending")),
            success=data.get("success", False),
            final_reward=data.get("final_reward", 0.0),
            done=data.get("done", False),
            truncated=data.get("truncated", False),
            metrics=data.get("metrics", {}),
            completion_time_seconds=data.get("completion_time", 0.0),
            error_message=data.get("error"),
        )


@dataclass
class ParticipantInfo:
    """
    Information about a participant (Purple Agent) in the assessment.
    """
    role: str              # e.g., "purple_agent"
    endpoint: str          # e.g., "http://127.0.0.1:9010/"
    id: str = ""           # Unique identifier for message prefixing
    
    def to_dict(self) -> Dict[str, str]:
        """Convert to dictionary."""
        return {
            "role": self.role,
            "endpoint": self.endpoint,
            "id": self.id,
        }


@dataclass
class AssessmentConfig:
    """
    Initial configuration for a multi-task assessment.
    
    This is the input to AssessmentTracker - contains all the
    information needed to set up and run an assessment.
    """
    run_id: str
    benchmarks: List[str]
    tasks_by_benchmark: Dict[str, List[str]]
    
    # Session identifier (for artifact building)
    session_id: str = ""
    
    # Limits
    max_steps: int = 10
    max_tool_calls: int = 3
    timeout_seconds: int = 300
    
    # Participants
    participants: Dict[str, ParticipantInfo] = field(default_factory=dict)
    
    # Primary participant (convenience)
    primary_participant_url: str = ""
    primary_participant_role: str = "purple_agent"
    
    def get_total_task_count(self) -> int:
        """Get total number of tasks across all benchmarks."""
        return sum(len(tasks) for tasks in self.tasks_by_benchmark.values())
    
    def get_flat_task_list(self) -> List[str]:
        """Get flattened list of all task IDs in order."""
        task_list = []
        for benchmark in self.benchmarks:
            tasks = self.tasks_by_benchmark.get(benchmark, [])
            task_list.extend(tasks)
        return task_list
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "run_id": self.run_id,
            "benchmarks": self.benchmarks.copy(),
            "tasks_by_benchmark": {k: v.copy() for k, v in self.tasks_by_benchmark.items()},
            "max_steps": self.max_steps,
            "max_tool_calls": self.max_tool_calls,
            "timeout_seconds": self.timeout_seconds,
            "participants": {k: v.to_dict() for k, v in self.participants.items()},
            "primary_participant_url": self.primary_participant_url,
            "total_tasks": self.get_total_task_count(),
        }
