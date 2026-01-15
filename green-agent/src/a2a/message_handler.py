"""
A2A Message Handler for BrowserGym Green Agent.

Handles A2A protocol message validation, task creation, and response formatting.
Implements FR-004 (message/send), FR-006 (task response), FR-007 (artifact generation).

This module uses the official A2A SDK types directly.
Only evaluation-specific error types (ErrorType, A2AErrorData) are custom.

Reference: https://google.github.io/A2A/
"""

import re
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

# Import SDK types directly
from a2a.types import (
    Task,
    TaskState,
    TaskStatus,
    Message,
    Part,
    TextPart,
    DataPart,
    Artifact,
)
from a2a.utils.message import new_agent_text_message

# Import only custom types (NOT in SDK)
from src.a2a.models import ErrorType, A2AErrorData
from src.utils.logging import get_logger


logger = get_logger(__name__)


# =============================================================================
# Task Update Helper - Agent SDK Integration
# =============================================================================

async def emit_task_update(
    updater: Any,  # TaskUpdater from a2a-sdk
    status: str,
    message: str,
    final: bool = False
) -> None:
    """
    Emit A2A task status update via TaskUpdater.
    
    Helper function for agent tools to emit task updates without
    directly coupling to A2A SDK types.
    
    Args:
        updater: TaskUpdater instance from a2a-sdk
        status: Status string ('initialization', 'running', 'complete', 'error')
        message: Human-readable status message
        final: Whether this is the final update
    
    Example:
        await emit_task_update(updater, "initialization", "MCP server spawned")
        await emit_task_update(updater, "running", "Evaluation in progress")
        await emit_task_update(updater, "complete", "Artifact generated", final=True)
    """
    # Map status strings to TaskState enum values
    state_map = {
        "initialization": TaskState.working,
        "running": TaskState.working,
        "complete": TaskState.completed,
        "error": TaskState.failed,
        # 'blocked' is not a member of TaskState in this SDK; map to input_required
        "blocked": TaskState.input_required,
    }
    
    state = state_map.get(status, TaskState.working)
    timestamp = datetime.now(timezone.utc).isoformat()
    
    # Create status message
    status_message = new_agent_text_message(
        message,
        context_id=getattr(updater, 'context_id', None),
        task_id=getattr(updater, 'task_id', None)
    )
    
    # Emit via TaskUpdater (a2a-sdk handles the SSE streaming)
    await updater.update_status(
        state=state,
        message=status_message
    )
    
    logger.debug(
        f"Task update emitted: {status}",
        extra={"status": status, "task_message": message, "final": final}
    )


# =============================================================================
# Constants
# =============================================================================

VALID_BENCHMARKS = {"miniwob", "webarena", "visualwebarena", "workarena", "assistantbench", "weblinx"}
TASK_ID_PATTERN = re.compile(r"^([a-z]+)\.([a-zA-Z0-9_-]+)$")

# JSON-RPC error codes
ERROR_CODE_INVALID_REQUEST = "-32600"
ERROR_CODE_INVALID_PARAMS = "-32602"
ERROR_CODE_INTERNAL_ERROR = "-32000"
ERROR_CODE_TASK_NOT_FOUND = "-32001"
ERROR_CODE_TIMEOUT = "-32002"


# =============================================================================
# Message Validation (FR-013)
# =============================================================================

class MessageValidationResult:
    """Result of A2A message validation."""
    
    def __init__(
        self,
        is_valid: bool,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
        task_id: Optional[str] = None,
        purple_agent_url: Optional[str] = None,
        config: Optional[dict[str, Any]] = None,
    ):
        self.is_valid = is_valid
        self.error_code = error_code
        self.error_message = error_message
        self.task_id = task_id
        self.purple_agent_url = purple_agent_url
        self.config = config or {}


def validate_task_id(task_id: str) -> MessageValidationResult:
    """Validate task_id format and benchmark prefix."""
    if not task_id:
        return MessageValidationResult(
            is_valid=False,
            error_code=ERROR_CODE_INVALID_PARAMS,
            error_message="task_id is required",
        )
    
    match = TASK_ID_PATTERN.match(task_id)
    if not match:
        return MessageValidationResult(
            is_valid=False,
            error_code=ERROR_CODE_INVALID_PARAMS,
            error_message=f"task_id must match format 'benchmark.task_name', got: {task_id}",
        )
    
    benchmark = match.group(1).lower()
    if benchmark not in VALID_BENCHMARKS:
        valid_list = ", ".join(sorted(VALID_BENCHMARKS))
        return MessageValidationResult(
            is_valid=False,
            error_code=ERROR_CODE_INVALID_PARAMS,
            error_message=f"Unknown benchmark '{benchmark}'. Valid benchmarks: {valid_list}",
        )
    
    return MessageValidationResult(is_valid=True, task_id=task_id)


def validate_sdk_message(message: Message) -> MessageValidationResult:
    """
    Validate incoming SDK Message for assessment request format.
    
    Expects a DataPart with: participants.purple_agent (URL) and config.task_id
    """
    data_part_data: Optional[dict] = None
    
    for part in message.parts:
        if hasattr(part, "root"):
            root = part.root
            if hasattr(root, "kind") and root.kind == "data":
                data_part_data = root.data
                break
    
    if not data_part_data:
        return MessageValidationResult(
            is_valid=False,
            error_code=ERROR_CODE_INVALID_REQUEST,
            error_message="Message must include a DataPart with participants and config",
        )
    
    # Validate participants
    participants = data_part_data.get("participants", {})
    purple_agent_url = participants.get("purple_agent")
    if not purple_agent_url or not isinstance(purple_agent_url, str):
        return MessageValidationResult(
            is_valid=False,
            error_code=ERROR_CODE_INVALID_PARAMS,
            error_message="purple_agent URL is required in participants",
        )
    
    # Validate config and task_id
    config = data_part_data.get("config", {})
    task_id = config.get("task_id", "")
    validation_result = validate_task_id(task_id)
    if not validation_result.is_valid:
        return validation_result
    
    return MessageValidationResult(
        is_valid=True,
        task_id=task_id,
        purple_agent_url=purple_agent_url,
        config=config,
    )


# =============================================================================
# Task Creation (FR-006) - Uses SDK Types Directly
# =============================================================================

def create_evaluation_task(
    task_id: str,
    context_id: Optional[str] = None,
    status_message: Optional[str] = None,
) -> Task:
    """Create a new A2A Task for evaluation using SDK types."""
    ctx_id = context_id or str(uuid4())
    a2a_task_id = str(uuid4())
    msg = status_message or f"Evaluation task created for: {task_id}"
    
    return Task(
        id=a2a_task_id,
        context_id=ctx_id,
        status=TaskStatus(
            state=TaskState.submitted,
            message=new_agent_text_message(msg, ctx_id, a2a_task_id),
        ),
        artifacts=[],
        history=[],
    )


def update_task_status(task: Task, state: TaskState, message: Optional[str] = None) -> Task:
    """Update task status using SDK types."""
    status_msg = new_agent_text_message(message, task.context_id, task.id) if message else None
    
    return Task(
        id=task.id,
        context_id=task.context_id,
        status=TaskStatus(state=state, message=status_msg),
        artifacts=task.artifacts,
        history=task.history,
    )


# =============================================================================
# Artifact Creation (FR-007) - Uses SDK Types Directly
# =============================================================================

def create_evaluation_artifact(
    name: str,
    task_success: bool,
    task_id: str,
    benchmark: str,
    total_tokens: int,
    total_latency_ms: int,
    efficiency_penalty: float,
    final_score: float,
    mcp_tool_invocations: int,
    observation_count: int,
    action_count: int,
    evaluation_duration_seconds: float,
    peak_memory_mb: int = 0,
    chromium_process_count: int = 0,
    error_message: Optional[str] = None,
) -> Artifact:
    """Create evaluation result artifact using SDK Artifact type directly."""
    data = {
        "task_success": task_success,
        "task_id": task_id,
        "benchmark": benchmark,
        "efficiency_metrics": {
            "total_tokens": total_tokens,
            "total_latency_ms": total_latency_ms,
            "peak_memory_mb": peak_memory_mb,
            "chromium_process_count": chromium_process_count,
        },
        "efficiency_penalty": efficiency_penalty,
        "final_score": final_score,
        "mcp_tool_invocations": mcp_tool_invocations,
        "observation_count": observation_count,
        "action_count": action_count,
        "evaluation_duration_seconds": evaluation_duration_seconds,
    }
    if error_message:
        data["error_message"] = error_message
    
    summary = (
        f"Task: {task_id} ({benchmark})\n"
        f"Success: {task_success}\n"
        f"Final Score: {final_score:.4f}\n"
        f"Efficiency Penalty: {efficiency_penalty:.4f}\n"
        f"Tokens: {total_tokens}, Latency: {total_latency_ms}ms\n"
        f"Actions: {action_count}, Observations: {observation_count}"
    )
    
    return Artifact(
        artifact_id=str(uuid4()),
        name=name,
        description=f"Evaluation results for {task_id}",
        parts=[
            Part(root=TextPart(kind="text", text=summary)),
            Part(root=DataPart(kind="data", data=data)),
        ],
        metadata={"benchmark": benchmark, "task_id": task_id},
    )


def create_error_artifact(
    error_type: ErrorType,
    error_message: str,
    error_code: str = ERROR_CODE_INTERNAL_ERROR,
    partial_metrics: Optional[dict[str, Any]] = None,
    stack_trace: Optional[str] = None,
) -> Artifact:
    """Create error artifact using SDK Artifact type directly."""
    error_data = A2AErrorData(
        error_code=error_code,
        error_type=error_type,
        error_message=error_message,
        partial_metrics=partial_metrics,
        stack_trace=stack_trace,
    )
    
    return Artifact(
        artifact_id=str(uuid4()),
        name="Error Report",
        description=f"Error: {error_type.value}",
        parts=[
            Part(root=TextPart(kind="text", text=f"Error: {error_message}")),
            Part(root=DataPart(kind="data", data=error_data.model_dump(by_alias=True, exclude_none=True))),
        ],
    )


# Convenience functions for specific error types
def create_validation_error_artifact(error_code: str, error_message: str, task_id: Optional[str] = None) -> Artifact:
    """Create validation error artifact."""
    return create_error_artifact(
        ErrorType.VALIDATION, error_message, error_code,
        partial_metrics={"task_id": task_id} if task_id else None
    )


def create_timeout_error_artifact(timeout_seconds: float, partial_metrics: dict[str, Any]) -> Artifact:
    """Create timeout error artifact with partial metrics."""
    return create_error_artifact(
        ErrorType.TIMEOUT, f"Evaluation timeout after {timeout_seconds}s",
        ERROR_CODE_TIMEOUT, partial_metrics
    )


def create_environment_error_artifact(
    error_message: str,
    partial_metrics: Optional[dict[str, Any]] = None,
    stack_trace: Optional[str] = None
) -> Artifact:
    """Create environment error artifact."""
    return create_error_artifact(
        ErrorType.ENVIRONMENT, error_message, ERROR_CODE_INTERNAL_ERROR,
        partial_metrics, stack_trace
    )


def create_communication_error_artifact(error_message: str, purple_agent_url: Optional[str] = None) -> Artifact:
    """Create communication error artifact."""
    return create_error_artifact(
        ErrorType.COMMUNICATION, error_message, ERROR_CODE_INTERNAL_ERROR,
        {"purple_agent_url": purple_agent_url} if purple_agent_url else None
    )


# =============================================================================
# Response Formatting (FR-006)
# =============================================================================

def format_task_response(task: Task) -> dict[str, Any]:
    """Format SDK Task for JSON-RPC response."""
    return task.model_dump(by_alias=True, exclude_none=True)


def format_error_response(error_code: str, error_message: str, data: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Format JSON-RPC error response."""
    error = {"code": int(error_code), "message": error_message}
    if data:
        error["data"] = data
    return {"error": error}


# =============================================================================
# Helpers
# =============================================================================

def extract_benchmark_from_task_id(task_id: str) -> str:
    """Extract benchmark name from task_id prefix."""
    return task_id.split(".")[0].lower() if "." in task_id else "unknown"
