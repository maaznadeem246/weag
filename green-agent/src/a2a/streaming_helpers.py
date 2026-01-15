"""
Streaming event formatting helpers for A2A SSE communication.

Extracted from streaming.py to improve modularity and testability.
"""

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from a2a.types import (
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
    TaskArtifactUpdateEvent,
    Part,
    Artifact,
)


def build_status_update_data(
    task_id: str,
    context_id: str,
    state: TaskState,
    message: str,
    final: bool = False,
    metadata: Optional[dict[str, Any]] = None
) -> dict[str, Any]:
    """
    Build status-update event data dict.
    
    Args:
        task_id: A2A task identifier
        context_id: A2A context identifier
        state: TaskState enum value
        message: Human-readable status message
        final: Whether this is the final status update
        metadata: Optional additional metadata
        
    Returns:
        Status update data dict per A2A protocol
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    
    status_data = {
        "kind": "status-update",
        "taskId": task_id,
        "contextId": context_id,
        "status": {
            "state": state.value,
            "message": message,
            "timestamp": timestamp
        },
        "final": final
    }
    
    if metadata:
        status_data["metadata"] = metadata
    
    return status_data


def build_artifact_update_data(
    task_id: str,
    context_id: str,
    artifact_name: str,
    parts: list[dict[str, Any]],
    append: bool = False,
    last_chunk: bool = True,
    description: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None
) -> dict[str, Any]:
    """
    Build artifact-update event data dict.
    
    Args:
        task_id: A2A task identifier
        context_id: A2A context identifier
        artifact_name: Name of the artifact
        parts: List of A2A part dicts
        append: Whether to append to existing artifact
        last_chunk: Whether this is the last chunk
        description: Optional artifact description
        metadata: Optional additional metadata
        
    Returns:
        Artifact update data dict per A2A protocol
    """
    artifact_id = str(uuid4())
    
    artifact_data = {
        "kind": "artifact-update",
        "taskId": task_id,
        "contextId": context_id,
        "artifact": {
            "artifactId": artifact_id,
            "name": artifact_name,
            "parts": parts
        },
        "append": append,
        "lastChunk": last_chunk
    }
    
    if description:
        artifact_data["artifact"]["description"] = description
    
    if metadata:
        artifact_data["artifact"]["metadata"] = metadata
    
    return artifact_data


def build_tool_invocation_metadata(
    tool_name: str,
    action_count: int,
    observation_count: int,
    total_tokens: int
) -> dict[str, Any]:
    """
    Build metadata for tool invocation status updates.
    
    Args:
        tool_name: Name of invoked tool
        action_count: Cumulative action count
        observation_count: Cumulative observation count
        total_tokens: Cumulative token count
        
    Returns:
        Metadata dict for tool invocation
    """
    return {
        "toolInvocation": {
            "toolName": tool_name,
            "actionCount": action_count,
            "observationCount": observation_count,
            "totalTokens": total_tokens
        }
    }


def create_status_update_event(
    task_id: str,
    context_id: str,
    state: TaskState,
    message: str,
    final: bool = False
) -> TaskStatusUpdateEvent:
    """
    Create TaskStatusUpdateEvent using SDK types.
    
    Helper function for creating status updates compatible
    with A2A SDK's TaskUpdater.
    
    Args:
        task_id: A2A task identifier
        context_id: A2A context identifier
        state: TaskState enum value
        message: Status message
        final: Whether this is final update
        
    Returns:
        TaskStatusUpdateEvent SDK object
    """
    return TaskStatusUpdateEvent(
        kind="status-update",
        taskId=task_id,
        contextId=context_id,
        status=TaskStatus(
            state=state,
            message=message,
            timestamp=datetime.now(timezone.utc).isoformat()
        ),
        final=final
    )


def create_artifact_update_event(
    task_id: str,
    context_id: str,
    artifact_name: str,
    parts: list[Part],
    append: bool = False,
    last_chunk: bool = True,
    description: Optional[str] = None
) -> TaskArtifactUpdateEvent:
    """
    Create TaskArtifactUpdateEvent using SDK types.
    
    Helper function for creating artifact updates compatible
    with A2A SDK's TaskUpdater.
    
    Args:
        task_id: A2A task identifier
        context_id: A2A context identifier
        artifact_name: Name of the artifact
        parts: List of Part objects
        append: Whether to append to existing artifact
        last_chunk: Whether this is the last chunk
        description: Optional artifact description
        
    Returns:
        TaskArtifactUpdateEvent SDK object
    """
    artifact = Artifact(
        artifactId=str(uuid4()),
        name=artifact_name,
        parts=parts
    )
    
    if description:
        artifact.description = description
    
    return TaskArtifactUpdateEvent(
        kind="artifact-update",
        taskId=task_id,
        contextId=context_id,
        artifact=artifact,
        append=append,
        lastChunk=last_chunk
    )
