"""
A2A Protocol Module for BrowserGym Green Agent.

Provides A2A (Agent-to-Agent) protocol compliance using official SDK types.
Only custom types are ErrorType and A2AErrorData for evaluation-specific errors.

SDK Types (from a2a.types):
- Task, TaskStatus, TaskState - Task lifecycle
- Message, Part, TextPart, DataPart, FilePart - Message content
- Artifact - Evaluation results
- AgentCard, AgentCapabilities, AgentSkill - Agent discovery

Custom Types:
- ErrorType, A2AErrorData - Evaluation error handling

Message Handler Functions:
- validate_task_id, validate_sdk_message - Input validation
- create_evaluation_task, update_task_status - Task management
- create_evaluation_artifact, create_error_artifact - Artifact creation
"""

# SDK types re-exported from models
from src.a2a.models import (
    # Task types
    Task,
    TaskStatus,
    TaskState,
    TaskStatusUpdateEvent,
    TaskArtifactUpdateEvent,
    # Message types
    Message,
    Part,
    TextPart,
    DataPart,
    FilePart,
    Role,
    # Artifact
    Artifact,
    # Agent card
    AgentCard,
    AgentCapabilities,
    AgentSkill,
    # SDK utility
    new_agent_text_message,
    # Custom types (NOT in SDK)
    ErrorType,
    A2AErrorData,
)

# Message handler functions
from src.a2a.message_handler import (
    # Validation
    MessageValidationResult,
    validate_task_id,
    validate_sdk_message,
    # Task creation
    create_evaluation_task,
    update_task_status,
    # Artifact creation
    create_evaluation_artifact,
    create_error_artifact,
    create_validation_error_artifact,
    create_timeout_error_artifact,
    create_environment_error_artifact,
    create_communication_error_artifact,
    # Response formatting
    format_task_response,
    format_error_response,
    # Helpers
    extract_benchmark_from_task_id,
    # Constants
    VALID_BENCHMARKS,
    ERROR_CODE_INVALID_REQUEST,
    ERROR_CODE_INVALID_PARAMS,
    ERROR_CODE_INTERNAL_ERROR,
    ERROR_CODE_TASK_NOT_FOUND,
    ERROR_CODE_TIMEOUT,
)

# Agent card functions
from src.a2a.agent_card import (
    create_agent_card,
    create_evaluation_skill,
    get_agent_card,
    get_agent_card_dict,
    get_extended_agent_card,
    get_agent_description,  # Dynamic function instead of constant
    A2A_PROTOCOL_VERSION,
    AGENT_VERSION,
    AGENT_NAME,
)

# Streaming functions
from src.a2a.streaming import (
    StreamEventType,
    StreamEvent,
    StreamingEventEmitter,
    SharedStateMonitor,
    stream_events_as_sse,
    get_or_create_emitter,
    remove_emitter,
    get_emitter,
)

from src.a2a.streaming_helpers import (
    create_status_update_event,
    create_artifact_update_event,
)

# Executor (A2A protocol executor)
from src.a2a.executor import (
    GreenAgent,
    GreenExecutor,
)

# Artifact helpers (evaluation artifact generation)
from src.a2a.artifact_helpers import (
    extract_benchmark_from_task_id as extract_benchmark,
    get_metrics_from_state,
    calculate_final_score,
    create_evaluation_artifact as create_eval_artifact,
    create_error_artifact as create_err_artifact,
    log_evaluation_completion,
)

# Validation helpers (request validation)
from src.a2a.validation_helpers import (
    validate_evaluation_request,
    validate_required_roles,
    validate_single_task_config,
    validate_multi_task_config,
)

__all__ = [
    # SDK Types
    "Task",
    "TaskStatus",
    "TaskState",
    "TaskStatusUpdateEvent",
    "TaskArtifactUpdateEvent",
    "Message",
    "Part",
    "TextPart",
    "DataPart",
    "FilePart",
    "Role",
    "Artifact",
    "AgentCard",
    "AgentCapabilities",
    "AgentSkill",
    "new_agent_text_message",
    # Custom Types
    "ErrorType",
    "A2AErrorData",
    # Validation
    "MessageValidationResult",
    "validate_task_id",
    "validate_sdk_message",
    # Task Management
    "create_evaluation_task",
    "update_task_status",
    # Artifact Creation
    "create_evaluation_artifact",
    "create_error_artifact",
    "create_validation_error_artifact",
    "create_timeout_error_artifact",
    "create_environment_error_artifact",
    "create_communication_error_artifact",
    # Response Formatting
    "format_task_response",
    "format_error_response",
    # Helpers
    "extract_benchmark_from_task_id",
    # Constants
    "VALID_BENCHMARKS",
    "ERROR_CODE_INVALID_REQUEST",
    "ERROR_CODE_INVALID_PARAMS",
    "ERROR_CODE_INTERNAL_ERROR",
    "ERROR_CODE_TASK_NOT_FOUND",
    "ERROR_CODE_TIMEOUT",
    # Agent Card
    "create_agent_card",
    "create_evaluation_skill",
    "get_agent_card",
    "get_agent_card_dict",
    "get_extended_agent_card",
    "A2A_PROTOCOL_VERSION",
    "AGENT_VERSION",
    "AGENT_NAME",
    "AGENT_DESCRIPTION",
    # Streaming
    "StreamEventType",
    "StreamEvent",
    "StreamingEventEmitter",
    "SharedStateMonitor",
    "create_status_update_event",
    "create_artifact_update_event",
    "stream_events_as_sse",
    "get_or_create_emitter",
    "remove_emitter",
    "get_emitter",
    # Executor
    "GreenAgent",
    "GreenExecutor",
    # Artifact Helpers
    "extract_benchmark",
    "get_metrics_from_state",
    "calculate_final_score",
    "create_eval_artifact",
    "create_err_artifact",
    "log_evaluation_completion",
    # Validation Helpers
    "validate_evaluation_request",
    "validate_required_roles",
    "validate_single_task_config",
    "validate_multi_task_config",
]
