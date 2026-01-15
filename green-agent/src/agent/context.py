"""
Agent context and data models for agentic evaluation orchestration.

Provides:
- AgentContext: Evaluation state passed to all agent tools
- ToolResult subtypes: InitializationResult, MonitoringResult, etc.
- Supporting models: BenchmarkConfig, BatchEvaluationConfig, MCPServerHealth
"""

from typing import Any, Optional, Union, Dict, TYPE_CHECKING
from datetime import datetime
from pydantic import BaseModel, HttpUrl, Field
import time

if TYPE_CHECKING:
    from src.assessment import Assessment


class AgentContext(BaseModel):
    """Evaluation context passed to all agent tools via RunContextWrapper."""
    
    # Identification
    session_id: str = Field(description="Unique session identifier (UUID format)")
    task_id: Optional[str] = Field(default=None, description="Task identifier (format: {benchmark}.{task_name})")
    benchmark: Optional[str] = Field(default=None, description="Benchmark name (must be in SUPPORTED_BENCHMARKS)")
    
    # Default Configuration (Green agent uses these if task_id/benchmark not provided)
    default_task_id: str = Field(default="miniwob.click-test", description="Default task_id if not specified")
    default_benchmark: str = Field(default="miniwob", description="Default benchmark if not specified")
    
    # Purple Agent(s)
    purple_agent_url: HttpUrl = Field(description="Purple agent A2A endpoint URL (primary/first participant)")
    purple_agent_role: str = Field(default="purple_agent", description="Purple agent role identifier")
    purple_agent_id: str = Field(default="", description="Unique purple agent identifier for message prefixing")
    participants: Dict[str, str] = Field(default_factory=dict, description="Map of role to endpoint URL for all participants")
    
    # Message Queue (for system and purple agent messages)
    incoming_messages: list[str] = Field(
        default_factory=list,
        description="Queue of incoming messages from system monitor and purple agent (prefixed with sender ID)"
    )
    
    # Background Monitoring Control
    background_monitor_active: bool = Field(default=False, description="Whether background monitoring task is running")
    background_monitor_interval: float = Field(default=3.0, description="Background monitor polling interval in seconds")
    
    # MCP Server
    mcp_server_process: Optional[int] = Field(
        default=None, 
        description="MCP server subprocess PID"
    )
    mcp_server_healthy: bool = Field(default=False, description="MCP server health status")
    mcp_tools_verified: list[str] = Field(
        default_factory=list,
        description="List of verified MCP tool names"
    )
    mcp_connection_details: Optional[Any] = Field(
        default=None,
        description="MCPConnectionDetails object with connection info and tools documentation for purple agent"
    )
    
    # Evaluation Timing
    # Accept either a Unix timestamp (float) or a datetime instance
    start_time: Union[float, datetime] = Field(description="Evaluation start timestamp (Unix time)")
    timeout_seconds: int = Field(default=600, description="Maximum evaluation timeout in seconds")
    max_timeout: int = Field(default=600, description="Deprecated: use timeout_seconds instead")
    
    # State References (runtime type validation required)
    shared_state_manager: Any = Field(
        description="Reference to SharedStateManager singleton for environment access"
    )
    task_updater: Optional[Any] = Field(
        default=None,
        description="Reference to TaskUpdater for A2A task status updates (official A2A SDK)"
    )
    active_sessions: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Reference to _active_sessions dict from main module for status endpoint updates"
    )
    
    # Assessment (single source of truth for multi-task assessment state)
    assessment_tracker: Optional[Any] = Field(
        default=None,
        description="Assessment instance for multi-task orchestration state (field name kept for backward compatibility)"
    )
    
    @property
    def assessment(self) -> Optional[Any]:
        """Alias for assessment_tracker for cleaner API."""
        return self.assessment_tracker
    
    # Evaluation State Tracking
    current_step: int = Field(default=0, description="Current evaluation step count")
    max_steps: int = Field(default=50, description="Maximum allowed steps")
    evaluation_complete: bool = Field(default=False, description="Whether evaluation has completed")
    task_success: bool = Field(default=False, description="Whether task was successful")
    final_reward: float = Field(default=0.0, description="Final reward from environment")
    error_message: Optional[str] = Field(default=None, description="Error message if evaluation failed")
    mcp_session_id: Optional[str] = Field(default=None, description="MCP session identifier")
    mcp_server_spawned: bool = Field(default=False, description="Whether MCP server has been spawned")
    
    # Batch Evaluation (Optional)
    batch_evaluation_config: Optional['BatchEvaluationConfig'] = Field(
        default=None,
        description="Batch evaluation configuration for multi-benchmark assessments"
    )
    current_batch_index: int = Field(
        default=0,
        description="Current benchmark index in batch evaluation (0-based)"
    )
    
    class Config:
        arbitrary_types_allowed = True


class BenchmarkConfig(BaseModel):
    """Configuration for a single benchmark in batch evaluation."""

    benchmark: str = Field(description="Benchmark name (must be in SUPPORTED_BENCHMARKS)")
    max_tasks: int = Field(default=5, description="Maximum number of tasks to evaluate")
    task_selection_mode: str = Field(
        default="random",
        description="Task selection strategy: 'random', 'sequential', or 'specific'"
    )
    specific_task_ids: list[str] = Field(
        default_factory=list,
        description="Specific task IDs when task_selection_mode='specific'"
    )
    timeout_per_task: int = Field(default=600, description="Timeout per task in seconds")
    environment_params: dict[str, Any] = Field(
        default_factory=dict,
        description="Benchmark-specific environment initialization parameters"
    )


class BatchEvaluationConfig(BaseModel):
    """Configuration for batch evaluation across multiple benchmarks."""
    
    benchmarks: list[BenchmarkConfig] = Field(
        description="List of benchmark configurations to evaluate"
    )
    execution_mode: str = Field(
        default="sequential",
        description="Execution mode: 'sequential' only (parallel is out-of-scope)"
    )
    stop_on_error: bool = Field(
        default=False,
        description="Whether to stop batch evaluation on first error"
    )


class MCPServerHealth(BaseModel):
    """MCP server health check result."""
    
    is_healthy: bool = Field(description="Overall health status")
    process_id: Optional[int] = Field(default=None, description="MCP server process PID")
    process_running: bool = Field(default=False, description="Process is running")
    tools_discovered: list[str] = Field(
        default_factory=list,
        description="List of discovered tool names"
    )
    tools_verified: list[str] = Field(
        default_factory=list,
        description="List of verified (successfully invoked) tool names"
    )
    health_check_timestamp: float = Field(description="Health check timestamp (Unix time)")
    retry_count: int = Field(default=0, description="Number of health check retries")
    error_message: Optional[str] = Field(
        default=None,
        description="Error message if health check failed"
    )
    expected_tools: list[str] = Field(
        default_factory=lambda: [
            "initialize_environment",
            "execute_actions",
            "get_observation",
            "cleanup_environment"
        ],
        description="Expected MCP tool names"
    )
    all_tools_available: bool = Field(
        default=False,
        description="Whether all expected tools are available"
    )


class InitializationResult(BaseModel):
    """Result from initialize_evaluation tool."""
    
    status: str = Field(description="Status: 'success', 'failure', or 'partial'")
    session_id: str = Field(description="Created session identifier")
    mcp_server_pid: int = Field(description="MCP server process ID")
    mcp_health: MCPServerHealth = Field(description="MCP server health check result")
    message: str = Field(default="", description="Human-readable status message")
    error: Optional[str] = Field(default=None, description="Error message if failed")


class MonitoringResult(BaseModel):
    """Result from monitoring operations."""
    
    status: str = Field(description="Status: 'active', 'idle', 'complete', 'timeout', 'error'")
    step_count: int = Field(description="Number of steps/actions taken")
    elapsed_time: float = Field(description="Elapsed time in seconds")
    remaining_timeout: float = Field(description="Remaining timeout in seconds")
    is_complete: bool = Field(default=False, description="Whether evaluation is complete")
    completion_reason: Optional[str] = Field(
        default=None,
        description="Reason for completion (e.g., 'reward_received', 'done_signal', 'timeout')"
    )
    actions_per_minute: float = Field(
        default=0.0,
        description="Activity rate (actions per minute)"
    )
    recommended_poll_interval: int = Field(
        default=5,
        description="Recommended next poll interval in seconds (adaptive)"
    )
    message: str = Field(default="", description="Human-readable status message")


class HealthCheckResult(BaseModel):
    """Result from verify_mcp_server_health tool."""
    
    status: str = Field(description="Status: 'healthy', 'unhealthy', 'degraded'")
    health_details: MCPServerHealth = Field(description="Detailed health check information")
    message: str = Field(default="", description="Human-readable status message")
    error: Optional[str] = Field(default=None, description="Error message if unhealthy")


class EvaluationResult(BaseModel):
    """Result from calculate_efficiency_score or generate_evaluation_artifact tools."""
    
    status: str = Field(description="Status: 'success', 'failure', 'partial'")
    task_success: bool = Field(description="Whether task was successfully completed")
    final_score: float = Field(description="Final evaluation score (0.0-1.0)")
    token_cost: int = Field(default=0, description="Total token cost")
    latency_seconds: float = Field(default=0.0, description="Total latency in seconds")
    step_count: int = Field(default=0, description="Total number of steps")
    efficiency_penalty: float = Field(default=0.0, description="Efficiency penalty applied")
    message: str = Field(default="", description="Human-readable status message")
    error: Optional[str] = Field(default=None, description="Error message if failed")


class CleanupResult(BaseModel):
    """Result from cleanup_evaluation tool."""
    
    status: str = Field(description="Status: 'success', 'failure', 'partial'")
    mcp_server_terminated: bool = Field(default=False, description="MCP server terminated")
    session_closed: bool = Field(default=False, description="Session closed")
    resources_cleaned: bool = Field(default=False, description="Resources cleaned up")
    message: str = Field(default="", description="Human-readable status message")
    error: Optional[str] = Field(default=None, description="Error message if failed")


# === Streaming Event Models ===


class AgentThinkingEvent(BaseModel):
    """Event emitted when agent makes a decision or reasoning step."""
    
    event_type: str = Field(default="agent_thinking", description="Event type identifier")
    timestamp: float = Field(description="Event timestamp (Unix time)")
    session_id: str = Field(description="Session identifier")
    task_id: str = Field(description="Task identifier")
    reasoning: str = Field(description="Agent's reasoning or thought process")
    next_action: Optional[str] = Field(default=None, description="Planned next action")


class ToolCallEvent(BaseModel):
    """Event emitted when agent calls a tool."""
    
    event_type: str = Field(default="tool_call", description="Event type identifier")
    timestamp: float = Field(description="Event timestamp (Unix time)")
    session_id: str = Field(description="Session identifier")
    task_id: str = Field(description="Task identifier")
    tool_name: str = Field(description="Name of tool being called")
    tool_args: dict[str, Any] = Field(default_factory=dict, description="Tool arguments")


class ToolResultEvent(BaseModel):
    """Event emitted when tool execution completes."""
    
    event_type: str = Field(default="tool_result", description="Event type identifier")
    timestamp: float = Field(description="Event timestamp (Unix time)")
    session_id: str = Field(description="Session identifier")
    task_id: str = Field(description="Task identifier")
    tool_name: str = Field(description="Name of tool that executed")
    result_status: str = Field(description="Tool result status: 'success', 'failure', 'partial'")
    result_summary: str = Field(default="", description="Brief summary of result")
    execution_time_ms: float = Field(default=0.0, description="Tool execution time in milliseconds")


class GuardrailEvent(BaseModel):
    """Event emitted when guardrail executes."""
    
    event_type: str = Field(default="guardrail", description="Event type identifier")
    timestamp: float = Field(description="Event timestamp (Unix time)")
    session_id: str = Field(description="Session identifier")
    task_id: str = Field(description="Task identifier")
    guardrail_type: str = Field(description="Guardrail type: 'input' or 'output'")
    guardrail_name: str = Field(description="Name of guardrail function")
    is_valid: bool = Field(description="Whether validation passed")
    violations: list[str] = Field(default_factory=list, description="List of violations if any")
    message: str = Field(default="", description="Validation message")


class StreamingEvent(BaseModel):
    """Base streaming event object used by streaming tests and event models."""

    event_type: str = Field(default="streaming_event", description="Event type identifier")
    timestamp: float = Field(default_factory=lambda: time.time(), description="Event timestamp (Unix time)")
    session_id: str = Field(description="Session identifier")
    task_id: str = Field(description="Task identifier")


__all__ = [
    "AgentContext",
    "BenchmarkConfig",
    "BatchEvaluationConfig",
    "MCPServerHealth",
    "InitializationResult",
    "MonitoringResult",
    "HealthCheckResult",
    "EvaluationResult",
    "CleanupResult",
    "AgentThinkingEvent",
    "ToolCallEvent",
    "ToolResultEvent",
    "GuardrailEvent",
]
