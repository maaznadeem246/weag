"""
A2A Protocol Types for BrowserGym Green Agent.

This module re-exports official A2A SDK types and provides ONLY custom types
that are NOT in the SDK (ErrorType, A2AErrorData for evaluation-specific errors).

SDK Types (use directly from a2a.types or from this module):
- Task, TaskStatus, TaskState, TaskStatusUpdateEvent, TaskArtifactUpdateEvent
- Message, Part, TextPart, DataPart, FilePart, Role
- Artifact, AgentCard, AgentCapabilities, AgentSkill

Custom Types (NOT in SDK - evaluation-specific):
- ErrorType: Error category enumeration
- A2AErrorData: Structured error data model

Reference: https://google.github.io/A2A/
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

# Re-export SDK types for convenience
from a2a.types import (
    # Task lifecycle
    Task,
    TaskStatus,
    TaskState,
    TaskStatusUpdateEvent,
    TaskArtifactUpdateEvent,
    # Message content
    Message,
    Part,
    TextPart,
    DataPart,
    FilePart,
    Role,
    # Artifacts
    Artifact,
    # Agent discovery
    AgentCard,
    AgentCapabilities,
    AgentSkill,
)

# Re-export SDK utility function
from a2a.utils.message import new_agent_text_message


# =============================================================================
# Custom Types (NOT in A2A SDK)
# =============================================================================

class ErrorType(str, Enum):
    """
    Error category enumeration for BrowserGym evaluation errors.
    
    NOT part of A2A SDK - specific to green agent evaluation.
    """
    VALIDATION = "validation"       # Invalid task_id, missing params
    TIMEOUT = "timeout"             # Evaluation timeout
    ENVIRONMENT = "environment"     # BrowserGym/Playwright errors
    COMMUNICATION = "communication" # A2A communication failures
    INTERNAL = "internal"           # Unexpected internal errors


class A2AErrorData(BaseModel):
    """
    Structured error data for evaluation error artifacts.
    
    NOT part of A2A SDK - provides detailed error context including
    partial metrics collected before failure (per FR-010).
    """
    error_code: str = Field(..., alias="errorCode")
    error_type: ErrorType = Field(..., alias="errorType")
    error_message: str = Field(..., alias="errorMessage")
    partial_metrics: Optional[dict[str, Any]] = Field(None, alias="partialMetrics")
    stack_trace: Optional[str] = Field(None, alias="stackTrace")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat() + "Z"
    )
    
    model_config = {"populate_by_name": True}
