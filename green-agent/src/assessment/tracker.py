"""
Assessment - Single source of truth for multi-task assessment state.

Centralizes all assessment-related state management to avoid scattered
dict-based tracking across multiple modules.
"""

import asyncio
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

from src.assessment.models import (
    AssessmentConfig,
    ParticipantInfo,
    TaskEntry,
    TaskStatus,
)
from src.benchmarks.profiles import detect_benchmark
from src.utils.logging import get_logger

if TYPE_CHECKING:
    from src.utils.shared_state import SharedStateManager, EvaluationState

logger = get_logger(__name__)


class Assessment:
    """
    Single source of truth for multi-task assessment state.
    
    Manages:
    - Task plan and progression (which task is current, which are sent)
    - Task status tracking (pending → sent → completed/timeout/failed)
    - Results collection (success, reward, metrics per task)
    - Participant information (Purple Agent endpoints)
    - Metrics aggregation (total tokens, latency, actions)
    - Real-time state access via SharedStateManager
    - Artifact and metrics generation
    
    Thread-safe: All state modifications use a lock.
    
    Usage:
        config = AssessmentConfig(...)
        assessment = Assessment(config)
        
        # Associate state manager
        assessment.set_state_manager(shared_state_manager)
        
        # Send first task
        assessment.mark_task_sent(0)
        
        # Snapshot state at start
        assessment.snapshot_task_start(0)
        
        # Wait for completion, then mark it
        assessment.mark_task_completed(0, success=True, reward=1.0)
        
        # Build artifact
        artifact = assessment.build_task_artifact(0)
        
        # Move to next
        assessment.advance_to_next_task()
        
        # Display summary
        if assessment.is_all_complete():
            assessment.display_summary()
    """
    
    def __init__(self, config: AssessmentConfig):
        """
        Initialize assessment with configuration.
        
        Args:
            config: Assessment configuration with benchmarks, tasks, participants
        """
        self._config = config
        self._task_plan: List[TaskEntry] = []
        self._current_index: int = 0
        self._lock = threading.RLock()
        self._start_time = datetime.utcnow()
        
        # SharedStateManager reference (for real-time state from MCP)
        self._state_manager: Optional['SharedStateManager'] = None
        
        # Orchestrator status fields (for decoupled background execution)
        self._orchestrator_status: str = "idle"  # idle | running | complete | error
        self._orchestrator_task: Optional[asyncio.Task] = None
        self._result_artifact: Optional[Dict[str, Any]] = None
        self._orchestrator_error: Optional[str] = None
        
        # Build task plan from config
        self._build_task_plan()
        
        logger.info(
            f"📋 Assessment initialized: {len(self._task_plan)} tasks, "
            f"benchmarks={config.benchmarks}, run_id={config.run_id}"
        )
    
    def _build_task_plan(self) -> None:
        """Build task plan from configuration."""
        task_list = self._config.get_flat_task_list()
        
        for idx, task_id in enumerate(task_list):
            benchmark = detect_benchmark(task_id)
            entry = TaskEntry(
                task_id=task_id,
                benchmark=benchmark,
                index=idx,
                status=TaskStatus.PENDING,
            )
            self._task_plan.append(entry)
    
    # ========================================================================
    # Task Plan Properties (Read-Only)
    # ========================================================================
    
    @property
    def task_plan(self) -> List[TaskEntry]:
        """Get the full task plan (read-only copy)."""
        with self._lock:
            return self._task_plan.copy()
    
    @property
    def total_tasks(self) -> int:
        """Total number of tasks in plan."""
        return len(self._task_plan)
    
    @property
    def current_index(self) -> int:
        """Current task index (0-based)."""
        with self._lock:
            return self._current_index
    
    @property
    def current_task(self) -> Optional[TaskEntry]:
        """Get current task entry, or None if all complete."""
        with self._lock:
            if self._current_index < len(self._task_plan):
                return self._task_plan[self._current_index]
            return None
    
    @property
    def current_task_id(self) -> Optional[str]:
        """Get current task ID string, or None if all complete."""
        task = self.current_task
        return task.task_id if task else None
    
    @property
    def current_benchmark(self) -> Optional[str]:
        """Get current task's benchmark, or None if all complete."""
        task = self.current_task
        return task.benchmark if task else None
    
    def get_task(self, index: int) -> Optional[TaskEntry]:
        """Get task at specific index."""
        with self._lock:
            if 0 <= index < len(self._task_plan):
                return self._task_plan[index]
            return None
    
    def get_task_by_id(self, task_id: str) -> Optional[TaskEntry]:
        """Find task by task_id."""
        with self._lock:
            for task in self._task_plan:
                if task.task_id == task_id:
                    return task
            return None
    
    # ========================================================================
    # Task Progression Methods
    # ========================================================================
    
    def is_task_sent(self, index: int) -> bool:
        """
        Check if task at index has been sent.
        
        A task is considered "sent" if its status is not PENDING.
        """
        with self._lock:
            if 0 <= index < len(self._task_plan):
                return self._task_plan[index].status != TaskStatus.PENDING
            return False
    
    def mark_task_sent(self, index: int) -> bool:
        """
        Mark task as sent to Purple Agent.
        
        Args:
            index: Task index to mark
            
        Returns:
            True if marked, False if invalid index or already sent
        """
        with self._lock:
            if not (0 <= index < len(self._task_plan)):
                logger.warning(f"Invalid task index: {index}")
                return False
            
            task = self._task_plan[index]
            if task.status != TaskStatus.PENDING:
                logger.debug(f"Task {index} already sent (status={task.status.value})")
                return False
            
            task.status = TaskStatus.SENT
            task.start_time = datetime.utcnow()
            
            logger.info(f"📤 Task {index + 1}/{self.total_tasks} marked SENT: {task.task_id}")
            return True
    
    def mark_task_running(self, index: int) -> bool:
        """
        Mark task as actively running.
        
        Args:
            index: Task index to mark
            
        Returns:
            True if marked, False if invalid
        """
        with self._lock:
            if not (0 <= index < len(self._task_plan)):
                return False
            
            task = self._task_plan[index]
            if task.status.is_terminal():
                return False
            
            task.status = TaskStatus.RUNNING
            logger.debug(f"Task {index + 1} marked RUNNING: {task.task_id}")
            return True
    
    def mark_task_completed(
        self,
        index: int,
        success: bool,
        reward: float = 0.0,
        done: bool = True,
        truncated: bool = False,
        metrics: Optional[Dict[str, int]] = None,
        status: Optional[TaskStatus] = None,
        error: Optional[str] = None,
        completion_time: float = 0.0,
    ) -> bool:
        """
        Mark task as completed with results.
        
        Args:
            index: Task index
            success: Whether task succeeded
            reward: Final reward from environment
            done: Whether task is done (from BrowserGym)
            truncated: Whether task was truncated
            metrics: Efficiency metrics dict
            status: Explicit status (auto-determined if None)
            error: Error message if failed
            completion_time: Time taken in seconds
            
        Returns:
            True if marked, False if invalid index or already terminal
        """
        with self._lock:
            if not (0 <= index < len(self._task_plan)):
                logger.warning(f"Invalid task index for completion: {index}")
                return False
            
            task = self._task_plan[index]
            
            # Don't overwrite terminal states
            if task.status.is_terminal():
                logger.debug(f"Task {index} already terminal (status={task.status.value})")
                return False
            
            # Determine status
            if status:
                task.status = status
            elif success:
                task.status = TaskStatus.COMPLETED
            else:
                task.status = TaskStatus.FAILED
            
            # Update result fields
            task.success = success
            task.final_reward = reward
            task.done = done
            task.truncated = truncated
            task.end_time = datetime.utcnow()
            task.completion_time_seconds = completion_time
            task.error_message = error
            
            # Update metrics if provided
            if metrics:
                task.metrics.update(metrics)
            
            status_emoji = "✓" if success else "✗"
            logger.info(
                f"{status_emoji} Task {index + 1}/{self.total_tasks} marked {task.status.value}: "
                f"{task.task_id} (reward={reward:.2f})"
            )
            return True
    
    def advance_to_next_task(self) -> bool:
        """
        Move to next task in the plan.
        
        Returns:
            True if advanced, False if no more tasks
        """
        with self._lock:
            if self._current_index + 1 < len(self._task_plan):
                self._current_index += 1
                task = self._task_plan[self._current_index]
                logger.info(f"➡️ Advanced to task {self._current_index + 1}/{self.total_tasks}: {task.task_id}")
                return True
            else:
                logger.info("✅ No more tasks to advance to")
                return False
    
    def set_current_index(self, index: int) -> bool:
        """
        Explicitly set current task index.
        
        Use sparingly - prefer advance_to_next_task() for normal flow.
        
        Args:
            index: New current index
            
        Returns:
            True if set, False if invalid index
        """
        with self._lock:
            if 0 <= index <= len(self._task_plan):
                old_index = self._current_index
                self._current_index = index
                logger.info(f"🔄 Set current_index: {old_index} → {index}")
                return True
            return False
    
    def is_all_complete(self) -> bool:
        """Check if all tasks have terminal status or current index is past end."""
        with self._lock:
            if self._current_index >= len(self._task_plan):
                return True
            # Check if all tasks are in terminal state
            return all(task.status.is_terminal() for task in self._task_plan)
    
    # ========================================================================
    # Orchestrator Status (for decoupled background execution)
    # ========================================================================
    
    @property
    def orchestrator_status(self) -> str:
        """Get orchestrator status: idle | running | complete | error"""
        with self._lock:
            return self._orchestrator_status
    
    @property
    def orchestrator_task(self) -> Optional[asyncio.Task]:
        """Get the background orchestrator task."""
        return self._orchestrator_task
    
    @property
    def result_artifact(self) -> Optional[Dict[str, Any]]:
        """Get final result artifact when complete."""
        with self._lock:
            return self._result_artifact
    
    @property
    def orchestrator_error(self) -> Optional[str]:
        """Get error message if orchestrator failed."""
        with self._lock:
            return self._orchestrator_error
    
    def is_orchestrator_running(self) -> bool:
        """Check if orchestrator is currently running."""
        with self._lock:
            return self._orchestrator_status == "running"
    
    def set_orchestrator_running(self, task: asyncio.Task) -> bool:
        """
        Mark orchestrator as running with background task.
        
        Args:
            task: The asyncio.Task running the orchestrator
            
        Returns:
            True if set, False if already running
        """
        with self._lock:
            if self._orchestrator_status == "running":
                logger.warning("Orchestrator already running, cannot start again")
                return False
            self._orchestrator_status = "running"
            self._orchestrator_task = task
            self._orchestrator_error = None
            logger.info("🚀 Orchestrator started")
            return True
    
    def set_orchestrator_complete(self, artifact: Dict[str, Any]) -> None:
        """Mark orchestrator as complete with result artifact."""
        with self._lock:
            self._orchestrator_status = "complete"
            self._result_artifact = artifact
            self._orchestrator_task = None
            logger.info("✅ Orchestrator completed")
    
    def set_orchestrator_error(self, error: str) -> None:
        """Mark orchestrator as failed with error message."""
        with self._lock:
            self._orchestrator_status = "error"
            self._orchestrator_error = error
            self._orchestrator_task = None
            logger.error(f"❌ Orchestrator failed: {error}")
    
    def get_orchestrator_progress(self) -> Dict[str, Any]:
        """Get current orchestrator progress for status checks."""
        with self._lock:
            return {
                "status": self._orchestrator_status,
                "current_task_index": self._current_index,
                "total_tasks": self.total_tasks,
                "completed_tasks": self.get_completed_count(),
                "passed_tasks": self.get_passed_count(),
                "failed_tasks": self.get_failed_count(),
                "current_task_id": self.current_task_id,
                "success_rate": self.get_success_rate(),
                "error": self._orchestrator_error,
            }
    
    # ========================================================================
    # Results & Metrics
    # ========================================================================
    
    def get_passed_count(self) -> int:
        """Count of successful tasks."""
        with self._lock:
            return sum(1 for t in self._task_plan if t.success)
    
    def get_failed_count(self) -> int:
        """Count of failed/timeout tasks."""
        with self._lock:
            return sum(1 for t in self._task_plan if t.status.is_terminal() and not t.success)
    
    def get_completed_count(self) -> int:
        """Count of tasks in any terminal state."""
        with self._lock:
            return sum(1 for t in self._task_plan if t.status.is_terminal())
    
    def get_success_rate(self) -> float:
        """Calculate success rate (0.0 to 1.0)."""
        completed = self.get_completed_count()
        if completed == 0:
            return 0.0
        return self.get_passed_count() / completed
    
    def get_aggregate_metrics(self) -> Dict[str, int]:
        """Get aggregated metrics across all tasks."""
        with self._lock:
            totals = {
                "tokens": 0,
                "latency_ms": 0,
                "actions": 0,
                "observations": 0,
                "mcp_calls": 0,
            }
            for task in self._task_plan:
                for key in totals:
                    totals[key] += task.metrics.get(key, 0)
            return totals
    
    def get_results_summary(self) -> Dict[str, Any]:
        """
        Get comprehensive results summary for finalization.
        
        Returns dict compatible with existing finalize_multi_task_assessment output.
        """
        with self._lock:
            task_results = [t.to_dict() for t in self._task_plan]
            metrics = self.get_aggregate_metrics()
            
            return {
                "mode": "multi",
                "run_id": self._config.run_id,
                "orchestrated_by_llm": True,
                "total_tasks": self.total_tasks,
                "passed_tasks": self.get_passed_count(),
                "failed_tasks": self.get_failed_count(),
                "completed_tasks": self.get_completed_count(),
                "success_rate": self.get_success_rate(),
                "total_tokens": metrics["tokens"],
                "total_latency_ms": metrics["latency_ms"],
                "total_actions": metrics["actions"],
                "benchmarks": self._config.benchmarks.copy(),
                "task_results": task_results,
                "participants": {
                    "purple_agent": {
                        "tasks": task_results
                    }
                },
            }
    
    def get_results_by_participant(self) -> Dict[str, Any]:
        """
        Get results in the legacy format used by multi_task_config.
        
        For backward compatibility with existing code.
        """
        with self._lock:
            task_results = [t.to_dict() for t in self._task_plan if t.status.is_terminal()]
            return {
                "purple_agent": {
                    "tasks": task_results
                }
            }
    
    # ========================================================================
    # Participant Info
    # ========================================================================
    
    @property
    def primary_participant_url(self) -> str:
        """Get primary participant URL."""
        return self._config.primary_participant_url
    
    @property
    def participants(self) -> Dict[str, ParticipantInfo]:
        """Get all participants."""
        return self._config.participants.copy()
    
    # ========================================================================
    # Config Access
    # ========================================================================
    
    @property
    def run_id(self) -> str:
        """Assessment run ID."""
        return self._config.run_id
    
    @property
    def benchmarks(self) -> List[str]:
        """List of benchmarks in this assessment."""
        return self._config.benchmarks.copy()
    
    @property
    def tasks_by_benchmark(self) -> Dict[str, List[str]]:
        """Tasks organized by benchmark."""
        return {k: v.copy() for k, v in self._config.tasks_by_benchmark.items()}
    
    @property
    def max_steps(self) -> int:
        """Max steps per task."""
        return self._config.max_steps
    
    @property
    def max_tool_calls(self) -> int:
        """Max tool calls per task."""
        return self._config.max_tool_calls
    
    @property
    def timeout_seconds(self) -> int:
        """Assessment timeout in seconds."""
        return self._config.timeout_seconds
    
    @property
    def config(self) -> AssessmentConfig:
        """Get the full configuration (read-only)."""
        return self._config
    
    # ========================================================================
    # Logging & Debug
    # ========================================================================
    
    def log_state(self) -> None:
        """Log current state for debugging."""
        with self._lock:
            status_summary = {}
            for task in self._task_plan:
                status = task.status.value
                status_summary[status] = status_summary.get(status, 0) + 1
            
            logger.info(
                f"📊 AssessmentTracker state: "
                f"current_index={self._current_index}/{self.total_tasks}, "
                f"passed={self.get_passed_count()}, "
                f"status_breakdown={status_summary}"
            )
    
    def to_dict(self) -> Dict[str, Any]:
        """Export full state as dict (for JSON serialization/debugging)."""
        with self._lock:
            return {
                "config": self._config.to_dict(),
                "current_index": self._current_index,
                "total_tasks": self.total_tasks,
                "passed_count": self.get_passed_count(),
                "failed_count": self.get_failed_count(),
                "success_rate": self.get_success_rate(),
                "task_plan": [t.to_dict() for t in self._task_plan],
                "start_time": self._start_time.isoformat(),
            }
    
    # ========================================================================
    # Legacy Compatibility
    # ========================================================================
    
    def to_multi_task_config(self) -> Dict[str, Any]:
        """
        Export state in legacy multi_task_config dict format.
        
        For backward compatibility during migration.
        """
        with self._lock:
            current_task = self.current_task
            return {
                "tasks_by_benchmark": self.tasks_by_benchmark,
                "benchmarks": self.benchmarks,
                "max_steps": self.max_steps,
                "max_tool_calls": self.max_tool_calls,
                "run_id": self.run_id,
                "current_task_index": self._current_index,
                "current_task": current_task.task_id if current_task else None,
                "current_benchmark": current_task.benchmark if current_task else None,
                "task_plan": [t.task_id for t in self._task_plan],
                "sent_task_indices": {
                    t.index for t in self._task_plan 
                    if t.status != TaskStatus.PENDING
                },
                "results_by_participant": self.get_results_by_participant(),
                "last_task_completed": (
                    self._task_plan[self._current_index].status.is_terminal()
                    if self._current_index < len(self._task_plan) else True
                ),
                "last_task_status": (
                    self._task_plan[self._current_index].status.value
                    if self._current_index < len(self._task_plan) else None
                ),
                "last_task_success": (
                    self._task_plan[self._current_index].success
                    if self._current_index < len(self._task_plan) else False
                ),
            }
    
    # ========================================================================
    # SharedStateManager Integration
    # ========================================================================
    
    def set_state_manager(self, manager: 'SharedStateManager') -> None:
        """
        Associate SharedStateManager for real-time state access.
        
        Args:
            manager: SharedStateManager instance managing IPC with MCP subprocess
        """
        self._state_manager = manager
        logger.debug(f"SharedStateManager associated with assessment (session={manager.session_id})")
    
    @property
    def state_manager(self) -> Optional['SharedStateManager']:
        """Get associated state manager."""
        return self._state_manager
    
    def get_real_time_state(self) -> Optional['EvaluationState']:
        """
        Read current state from MCP subprocess.
        
        Returns:
            Current evaluation state, or None if no state manager
        """
        if self._state_manager:
            return self._state_manager.read_state()
        return None
    
    def snapshot_task_start(self, task_index: int) -> None:
        """
        Capture state snapshot when task starts for delta calculation.
        
        Args:
            task_index: Task index to snapshot
        """
        state = self.get_real_time_state()
        if state and 0 <= task_index < len(self._task_plan):
            self._task_plan[task_index].start_snapshot = state.to_dict()
            logger.debug(f"Captured state snapshot for task {task_index}: {self._task_plan[task_index].task_id}")
    
    # ========================================================================
    # Artifact Building Methods
    # ========================================================================
    
    def build_task_artifact(
        self,
        task_index: int,
        evaluation_result: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Build evaluation artifact for a task using internal state.
        
        Args:
            task_index: Task index to build artifact for
            evaluation_result: Optional pre-calculated efficiency metrics dict with:
                - task_success, final_score, token_cost, latency_seconds, 
                  step_count, efficiency_penalty
            
        Returns:
            Complete artifact dict following A2A schema
        """
        if not (0 <= task_index < len(self._task_plan)):
            raise ValueError(f"Invalid task index: {task_index}")
        
        task = self._task_plan[task_index]
        state = self.get_real_time_state()
        end_time = time.time()
        start_time = task.start_time.timestamp() if task.start_time else end_time
        
        # Use evaluation_result if provided, otherwise use task data
        if evaluation_result:
            task_success = evaluation_result.get("task_success", task.success)
            final_score = evaluation_result.get("final_score", task.final_reward)
            token_cost = evaluation_result.get("token_cost", task.metrics.get("tokens", 0))
            latency_seconds = evaluation_result.get("latency_seconds", task.metrics.get("latency_ms", 0) / 1000.0)
            step_count = evaluation_result.get("step_count", task.metrics.get("actions", 0))
            efficiency_penalty = evaluation_result.get("efficiency_penalty", 0.0)
        else:
            task_success = task.success
            final_score = task.final_reward
            token_cost = task.metrics.get("tokens", 0)
            latency_seconds = task.metrics.get("latency_ms", 0) / 1000.0
            step_count = task.metrics.get("actions", 0)
            efficiency_penalty = 0.0
        
        artifact = {
            # Core evaluation results
            "task_id": task.task_id,
            "benchmark": task.benchmark,
            "session_id": self._config.session_id,
            "task_success": task_success,
            "final_score": final_score,
            
            # Efficiency metrics (C/L/F mandates)
            "token_cost": token_cost,
            "latency_seconds": latency_seconds,
            "step_count": step_count,
            "efficiency_penalty": efficiency_penalty,
            
            # Timing
            "start_time": start_time,
            "end_time": end_time,
            "elapsed_time": end_time - start_time,
            
            # Metadata (A2A protocol compliance)
            "metadata": {
                "session_id": self._config.session_id,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            },
        }
        
        # Add environment state if available from real-time state
        if state:
            artifact["environment_state"] = {
                "done": state.done,
                "truncated": state.truncated,
                "final_reward": state.final_reward,
                "total_tokens": state.total_tokens,
                "total_latency_ms": state.total_latency_ms,
                "action_count": state.action_count,
                "observation_count": state.observation_count,
                "mcp_tool_invocations": state.mcp_tool_invocations,
            }
            
            artifact["action_history"] = {
                "total_actions": state.action_count,
                "last_tool": state.last_tool,
                "last_tool_timestamp": state.last_tool_timestamp,
            }
            
            artifact["error_log"] = [state.error] if state.error else []
        else:
            # Fallback to task data
            artifact["environment_state"] = {
                "done": task.done,
                "truncated": task.truncated,
                "final_reward": task.final_reward,
                "total_tokens": token_cost,
                "total_latency_ms": int(latency_seconds * 1000),
                "action_count": step_count,
                "observation_count": task.metrics.get("observations", 0),
                "mcp_tool_invocations": task.metrics.get("mcp_calls", 0),
            }
            artifact["action_history"] = {"total_actions": step_count}
            artifact["error_log"] = [task.error_message] if task.error_message else []
        
        return artifact
    
    def build_batch_result(
        self,
        execution_mode: str = "sequential",
        stop_on_error: bool = False
    ) -> Dict[str, Any]:
        """
        Build overall batch evaluation result with aggregated metrics.
        
        Args:
            execution_mode: Execution mode (sequential/parallel)
            stop_on_error: Whether stop-on-error was enabled
            
        Returns:
            Complete batch result with per-benchmark and overall metrics
        """
        # Group tasks by benchmark
        per_benchmark_results = []
        for benchmark in self.benchmarks:
            benchmark_result = self.get_benchmark_result(benchmark)
            per_benchmark_results.append(benchmark_result)
        
        # Calculate overall aggregates
        overall_task_count = sum(r["tasks_evaluated"] for r in per_benchmark_results)
        overall_success_count = sum(r["successes"] for r in per_benchmark_results)
        overall_token_cost = sum(r["total_tokens"] for r in per_benchmark_results)
        overall_latency = sum(r["total_latency"] for r in per_benchmark_results)
        
        return {
            "status": "success",
            "benchmarks_evaluated": len(per_benchmark_results),
            "total_tasks_evaluated": overall_task_count,
            "overall_success_count": overall_success_count,
            "overall_success_rate": (
                overall_success_count / overall_task_count if overall_task_count > 0 else 0.0
            ),
            "overall_avg_token_cost": (
                overall_token_cost / overall_task_count if overall_task_count > 0 else 0
            ),
            "overall_avg_latency": (
                overall_latency / overall_task_count if overall_task_count > 0 else 0.0
            ),
            "per_benchmark_results": per_benchmark_results,
            "metadata": {
                "session_id": self._config.session_id,
                "execution_mode": execution_mode,
                "stop_on_error": stop_on_error,
            }
        }
    
    def get_benchmark_result(self, benchmark: str) -> Dict[str, Any]:
        """
        Get aggregated results for a specific benchmark.
        
        Args:
            benchmark: Benchmark name
            
        Returns:
            Benchmark result dict with aggregates and task results
        """
        with self._lock:
            # Get all tasks for this benchmark
            benchmark_tasks = [t for t in self._task_plan if t.benchmark == benchmark]
            
            # Convert to result dicts
            task_results = [
                {
                    "task_id": t.task_id,
                    "success": t.success,
                    "score": t.final_reward,
                    "tokens": t.metrics.get("tokens", 0),
                    "latency": t.metrics.get("latency_ms", 0) / 1000.0,
                    "actions": t.metrics.get("actions", 0),
                }
                for t in benchmark_tasks if t.status.is_terminal()
            ]
            
            # Calculate aggregates
            successes = sum(1 for r in task_results if r["success"])
            failures = len(task_results) - successes
            total_tokens = sum(r["tokens"] for r in task_results)
            total_latency = sum(r["latency"] for r in task_results)
            
            # Calculate averages
            aggregates = self.calculate_benchmark_aggregates(task_results)
            
            return {
                "benchmark": benchmark,
                "tasks_evaluated": len(task_results),
                "successes": successes,
                "failures": failures,
                "total_tokens": total_tokens,
                "total_latency": total_latency,
                "task_results": task_results,
                **aggregates,
            }
    
    def format_error_result(
        self,
        error_message: str,
        current_benchmark: str
    ) -> Dict[str, Any]:
        """
        Format error result for batch evaluation failure.
        
        Args:
            error_message: Error description
            current_benchmark: Benchmark that failed
            
        Returns:
            Formatted error result dict
        """
        with self._lock:
            # Count completed benchmarks
            completed_benchmarks = set()
            for task in self._task_plan:
                if task.status.is_terminal():
                    completed_benchmarks.add(task.benchmark)
            
            # Get results for completed benchmarks
            per_benchmark_results = [
                self.get_benchmark_result(b) for b in completed_benchmarks
            ]
            
            return {
                "error": error_message,
                "status": "failed",
                "completed_benchmarks": len(completed_benchmarks),
                "current_benchmark": current_benchmark,
                "per_benchmark_results": per_benchmark_results,
            }
    
    # ========================================================================
    # Metrics Calculation Methods
    # ========================================================================
    
    def calculate_task_metrics(self, task_index: int) -> Dict[str, int]:
        """
        Calculate metrics delta for a task using stored snapshots.
        
        Args:
            task_index: Task index
            
        Returns:
            Dict with metric deltas (tokens, latency_ms, actions, observations, mcp_calls)
        """
        if not (0 <= task_index < len(self._task_plan)):
            return {
                "tokens": 0,
                "latency_ms": 0,
                "actions": 0,
                "observations": 0,
                "mcp_calls": 0,
            }
        
        task = self._task_plan[task_index]
        current_state = self.get_real_time_state()
        
        # If we have a start snapshot, calculate delta
        if task.start_snapshot and current_state:
            start = task.start_snapshot
            return {
                "tokens": max(0, current_state.total_tokens - start.get("total_tokens", 0)),
                "latency_ms": max(0, current_state.total_latency_ms - start.get("total_latency_ms", 0)),
                "actions": max(0, current_state.action_count - start.get("action_count", 0)),
                "observations": max(0, current_state.observation_count - start.get("observation_count", 0)),
                "mcp_calls": max(0, current_state.mcp_tool_invocations - start.get("mcp_tool_invocations", 0)),
            }
        
        # Fallback: use task's stored metrics
        return task.metrics.copy()
    
    def calculate_benchmark_aggregates(self, task_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Calculate aggregated metrics for a benchmark's task results.
        
        Args:
            task_results: List of task result dicts with success, score, tokens, latency
            
        Returns:
            Dict with success_rate, avg_score, avg_token_cost, avg_latency
        """
        if not task_results:
            return {
                "success_rate": 0.0,
                "avg_score": 0.0,
                "avg_token_cost": 0,
                "avg_latency": 0.0,
            }
        
        successes = sum(1 for r in task_results if r.get("success", False))
        total_tasks = len(task_results)
        
        # Calculate average score from successful tasks only
        scores = [r.get("score", 0.0) for r in task_results if r.get("success")]
        avg_score = sum(scores) / len(scores) if scores else 0.0
        
        # Calculate average token cost and latency from all tasks
        total_tokens = sum(r.get("tokens", 0) for r in task_results)
        total_latency = sum(r.get("latency", 0.0) for r in task_results)
        
        return {
            "success_rate": successes / total_tasks,
            "avg_score": avg_score,
            "avg_token_cost": total_tokens / total_tasks,
            "avg_latency": total_latency / total_tasks,
        }
    
    # ========================================================================
    # Display & Formatting Methods
    # ========================================================================
    
    def format_progress(self, environment_action: str = "maintained") -> str:
        """
        Format multi-task progress message for Purple Agent.
        
        Args:
            environment_action: Action taken on environment (reset/recreated/maintained)
            
        Returns:
            Formatted progress message string
        """
        task_num = self._current_index + 1
        return (
            f"\n\nMULTI-TASK MODE: This is task {task_num} of {self.total_tasks}. "
            f"Environment {environment_action}. "
            f"Complete this task (done=True or reward>0) then wait for next task."
        )
    
    def display_summary(self) -> None:
        """
        Display comprehensive assessment summary in formatted console output.
        """
        results = self.get_results_summary()
        
        print("\n" + "=" * 80)
        print("🎯 ASSESSMENT COMPLETED - FINAL METRICS")
        print("=" * 80)
        
        # Overview
        print(f"\n📊 Overview:")
        print(f"   Mode: {results.get('mode', 'unknown').upper()}")
        print(f"   Run ID: {results.get('run_id', 'N/A')}")
        orchestration = "LLM-controlled" if results.get('orchestrated_by_llm') else "Programmatic"
        print(f"   Orchestration: {orchestration}")
        
        # Task Results
        total = results.get('total_tasks', 0)
        passed = results.get('passed_tasks', 0)
        failed = total - passed
        success_rate = results.get('success_rate', 0.0)
        
        print(f"\n✅ Task Results:")
        print(f"   Total Tasks: {total}")
        print(f"   Passed: {passed} ({success_rate * 100:.1f}%)")
        print(f"   Failed: {failed}")
        
        # Per-task status breakdown
        task_results = results.get('task_results', [])
        if task_results:
            print(f"\n📋 Per-Task Breakdown:")
            for tr in task_results:
                status_icon = "✓" if tr.get('success') else "✗"
                task_id = tr.get('task_id', 'unknown')
                reward = tr.get('final_reward', 0.0)
                status = tr.get('status', 'unknown')
                completion_time = tr.get('completion_time', 0)
                print(f"   {status_icon} {task_id}: reward={reward:.2f}, status={status}, time={completion_time:.1f}s")
        
        # Efficiency Metrics
        total_tokens = results.get('total_tokens', 0)
        total_latency_ms = results.get('total_latency_ms', 0)
        total_actions = results.get('total_actions', 0)
        
        print(f"\n⚡ Efficiency Metrics:")
        print(f"   Total Tokens: {total_tokens:,}")
        print(f"   Total Latency: {total_latency_ms / 1000:.2f}s")
        print(f"   Total Actions: {total_actions}")
        
        if total > 0:
            print(f"\n📈 Average per Task:")
            print(f"   Avg Tokens: {total_tokens // total}")
            print(f"   Avg Latency: {total_latency_ms / total / 1000:.2f}s")
            print(f"   Avg Actions: {total_actions / total:.1f}")
        
        # Participants Summary (if multi-participant)
        participants = results.get('participants', {})
        if participants and len(participants) > 1:
            print(f"\n👥 Participants Summary:")
            for participant, data in participants.items():
                participant_tasks = data.get('tasks', [])
                participant_passed = sum(1 for t in participant_tasks if t.get('success'))
                print(f"   {participant}: {participant_passed}/{len(participant_tasks)} tasks passed")
        
        print("\n" + "=" * 80)
        print("🏁 Assessment Complete")
        print("=" * 80 + "\n")
    
    # ========================================================================
    # Batch Evaluation Methods
    # ========================================================================
    
    def select_tasks_for_benchmark(
        self,
        benchmark: str,
        max_tasks: int,
        selection_mode: str = "random",
        specific_task_ids: Optional[List[str]] = None
    ) -> List[str]:
        """
        Select tasks for benchmark evaluation based on strategy.
        
        Args:
            benchmark: Benchmark name
            max_tasks: Maximum number of tasks to select
            selection_mode: Selection strategy ('random', 'sequential', 'specific')
            specific_task_ids: List of specific task IDs (for 'specific' mode)
            
        Returns:
            List of selected task IDs
        """
        import random
        
        # For specific mode, use provided task list
        if selection_mode == "specific":
            if not specific_task_ids:
                logger.warning(f"Specific mode selected but no task IDs provided for {benchmark}")
                return []
            tasks = specific_task_ids[:max_tasks]
            logger.info(
                f"Selected {len(tasks)} specific tasks",
                extra={"benchmark": benchmark, "tasks": tasks}
            )
            return tasks
        
        # Generate available tasks list (placeholder - would query benchmark registry)
        # In production, this would query the actual benchmark task registry
        available_tasks = [
            f"{benchmark}.task-{i:03d}" 
            for i in range(1, min(101, max_tasks * 5))
        ]
        
        if selection_mode == "random":
            # Random sampling without replacement
            selected_count = min(max_tasks, len(available_tasks))
            tasks = random.sample(available_tasks, selected_count)
            logger.info(
                f"Randomly selected {len(tasks)} tasks",
                extra={"benchmark": benchmark, "total_available": len(available_tasks)}
            )
            return tasks
        
        elif selection_mode == "sequential":
            # Sequential selection from start
            tasks = available_tasks[:max_tasks]
            logger.info(
                f"Sequentially selected {len(tasks)} tasks",
                extra={"benchmark": benchmark}
            )
            return tasks
        
        else:
            # Default to random
            logger.warning(
                f"Unknown selection mode '{selection_mode}', defaulting to random",
                extra={"benchmark": benchmark}
            )
            selected_count = min(max_tasks, len(available_tasks))
            return random.sample(available_tasks, selected_count)
    
    def execute_batch_evaluation(
        self,
        benchmarks: List[Any],  # List[BenchmarkConfig]
        execution_mode: str = "sequential",
        stop_on_error: bool = False,
        supported_benchmarks: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Execute batch evaluation across multiple benchmarks.
        
        Orchestrates task selection, execution, and aggregation.
        
        Args:
            benchmarks: List of BenchmarkConfig objects
            execution_mode: Execution mode ('sequential' or 'parallel')
            stop_on_error: Whether to stop on first error
            supported_benchmarks: List of supported benchmark names for validation
            
        Returns:
            Overall batch evaluation results with per-benchmark metrics
        """
        if not supported_benchmarks:
            supported_benchmarks = ["miniwob", "webarena", "visualwebarena", 
                                   "workarena", "assistantbench", "weblinx"]
        
        logger.info(
            f"Starting batch evaluation: {len(benchmarks)} benchmarks",
            extra={
                "session_id": self._config.session_id,
                "execution_mode": execution_mode,
            }
        )
        
        per_benchmark_results: List[Dict[str, Any]] = []
        
        # Sequential execution with benchmark isolation
        for batch_index, benchmark_cfg in enumerate(benchmarks):
            benchmark_name = getattr(benchmark_cfg, 'benchmark_name', str(benchmark_cfg))
            
            # Validate benchmark name
            if benchmark_name not in supported_benchmarks:
                error_msg = f"Invalid benchmark '{benchmark_name}'. Must be one of: {supported_benchmarks}"
                logger.error(error_msg)
                
                if stop_on_error:
                    return self.format_error_result(error_msg, benchmark_name)
                else:
                    per_benchmark_results.append({
                        "benchmark": benchmark_name,
                        "status": "failed",
                        "error": error_msg,
                    })
                    continue
            
            # Task selection
            max_tasks = getattr(benchmark_cfg, 'max_tasks', 10)
            selection_mode = getattr(benchmark_cfg, 'task_selection_mode', 'random')
            specific_tasks = getattr(benchmark_cfg, 'specific_task_ids', None)
            
            tasks_to_evaluate = self.select_tasks_for_benchmark(
                benchmark=benchmark_name,
                max_tasks=max_tasks,
                selection_mode=selection_mode,
                specific_task_ids=specific_tasks
            )
            
            logger.info(
                f"Evaluating benchmark {batch_index + 1}/{len(benchmarks)}",
                extra={
                    "benchmark": benchmark_name,
                    "tasks_selected": len(tasks_to_evaluate),
                    "max_tasks": max_tasks,
                }
            )
            
            benchmark_results = {
                "benchmark": benchmark_name,
                "tasks_evaluated": len(tasks_to_evaluate),
                "successes": 0,
                "failures": 0,
                "total_tokens": 0,
                "total_latency": 0.0,
                "avg_score": 0.0,
                "task_results": [],
            }
            
            # Evaluate each task in benchmark
            # Note: Actual task execution would be delegated to task executor
            # For now, this is a placeholder structure
            for task_id in tasks_to_evaluate:
                try:
                    # TODO: Integrate with actual task execution
                    # This would call the single-task evaluation flow
                    task_result = {
                        "task_id": task_id,
                        "success": True,
                        "score": 0.85,
                        "tokens": 1500,
                        "latency": 45.2,
                    }
                    
                    benchmark_results["task_results"].append(task_result)
                    
                    if task_result["success"]:
                        benchmark_results["successes"] += 1
                    else:
                        benchmark_results["failures"] += 1
                    
                    benchmark_results["total_tokens"] += task_result["tokens"]
                    benchmark_results["total_latency"] += task_result["latency"]
                    
                except Exception as e:
                    logger.error(
                        f"Task evaluation failed",
                        extra={"task_id": task_id, "error": str(e)},
                        exc_info=True,
                    )
                    
                    benchmark_results["failures"] += 1
                    benchmark_results["task_results"].append({
                        "task_id": task_id,
                        "success": False,
                        "error": str(e),
                    })
                    
                    if stop_on_error:
                        return {
                            "error": f"Task evaluation failed: {str(e)}",
                            "status": "failed",
                            "completed_benchmarks": batch_index,
                            "current_benchmark": benchmark_name,
                            "per_benchmark_results": per_benchmark_results + [benchmark_results],
                        }
            
            # Calculate per-benchmark aggregates
            if benchmark_results["tasks_evaluated"] > 0:
                aggregates = self.calculate_benchmark_aggregates(benchmark_results["task_results"])
                benchmark_results.update(aggregates)
            
            per_benchmark_results.append(benchmark_results)
        
        # Calculate overall aggregated metrics
        overall_result = self.build_batch_result(execution_mode, stop_on_error)
        overall_result["per_benchmark_results"] = per_benchmark_results
        
        # Recalculate overall metrics from actual results
        overall_task_count = sum(r["tasks_evaluated"] for r in per_benchmark_results)
        overall_success_count = sum(r["successes"] for r in per_benchmark_results)
        overall_token_cost = sum(r["total_tokens"] for r in per_benchmark_results)
        overall_latency = sum(r["total_latency"] for r in per_benchmark_results)
        
        overall_result.update({
            "benchmarks_evaluated": len(per_benchmark_results),
            "total_tasks_evaluated": overall_task_count,
            "overall_success_count": overall_success_count,
            "overall_success_rate": (
                overall_success_count / overall_task_count if overall_task_count > 0 else 0.0
            ),
            "overall_avg_token_cost": (
                overall_token_cost / overall_task_count if overall_task_count > 0 else 0
            ),
            "overall_avg_latency": (
                overall_latency / overall_task_count if overall_task_count > 0 else 0.0
            ),
        })
        
        logger.info(
            "Batch evaluation completed",
            extra={
                "benchmarks_evaluated": len(per_benchmark_results),
                "overall_success_rate": overall_result["overall_success_rate"],
            }
        )
        
        return overall_result


# ============================================================================
# Factory Function
# ============================================================================

def create_assessment(
    run_id: str,
    benchmarks: List[str],
    tasks_by_benchmark: Dict[str, List[str]],
    max_steps: int = 10,
    max_tool_calls: int = 12,
    timeout_seconds: int = 300,
    primary_participant_url: str = "",
    participants: Optional[Dict[str, Dict[str, str]]] = None,
    session_id: str = "",
) -> Assessment:
    """
    Factory function to create Assessment from raw parameters.
    
    Useful for creating assessment from existing multi_task_config dict values.
    
    Args:
        run_id: Assessment run ID
        benchmarks: List of benchmark names
        tasks_by_benchmark: Dict mapping benchmark to task list
        max_steps: Max steps per task
        max_tool_calls: Max tool calls per task  
        timeout_seconds: Total timeout
        primary_participant_url: Primary Purple Agent URL
        participants: Optional dict of participant info
        session_id: Session identifier
        
    Returns:
        Configured Assessment instance
    """
    # Convert participants dict to ParticipantInfo objects
    participant_objs = {}
    if participants:
        for role, info in participants.items():
            if isinstance(info, dict):
                participant_objs[role] = ParticipantInfo(
                    role=role,
                    endpoint=info.get("endpoint", info.get("url", "")),
                    id=info.get("id", ""),
                )
            elif isinstance(info, str):
                participant_objs[role] = ParticipantInfo(role=role, endpoint=info)
    
    config = AssessmentConfig(
        run_id=run_id,
        session_id=session_id,
        benchmarks=benchmarks,
        tasks_by_benchmark=tasks_by_benchmark,
        max_steps=max_steps,
        max_tool_calls=max_tool_calls,
        timeout_seconds=timeout_seconds,
        participants=participant_objs,
        primary_participant_url=primary_participant_url,
    )
    
    return Assessment(config)


# Backward compatibility alias
create_tracker_from_config = create_assessment
