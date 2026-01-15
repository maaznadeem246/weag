"""
A2A SSE Streaming Module for BrowserGym Green Agent.

Provides Server-Sent Events (SSE) streaming for real-time evaluation updates.
Implements FR-005 (streaming updates) and FR-012 (final status update).

Components:
- StreamingEventEmitter: Thread-safe async queue for SSE events
- Status update generation: A2AStatusUpdate events
- Artifact update generation: A2AArtifactUpdate events
- SharedState monitor integration for automatic emission

Reference:
- data-model.md: A2AStatusUpdate, A2AArtifactUpdate schemas
- A2A Protocol: https://google.github.io/A2A/
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Optional
from uuid import uuid4
from dataclasses import dataclass
from enum import Enum

from a2a.types import (
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
    TaskArtifactUpdateEvent,
    Part,
    TextPart,
    DataPart,
    Artifact,
)

from src.utils.shared_state import EvaluationState, SharedStateManager
from src.a2a.streaming_helpers import (
    build_status_update_data,
    build_artifact_update_data,
    build_tool_invocation_metadata,
)
from src.utils.logging import get_logger

logger = get_logger(__name__)


class StreamEventType(str, Enum):
    """SSE event types per A2A protocol."""
    STATUS_UPDATE = "status-update"
    ARTIFACT_UPDATE = "artifact-update"


@dataclass
class StreamEvent:
    """
    Generic streaming event wrapper.
    
    Wraps either status-update or artifact-update events
    for the SSE event queue.
    """
    event_type: StreamEventType
    data: dict[str, Any]
    task_id: str
    context_id: str
    final: bool = False
    
    def to_sse_format(self) -> str:
        """
        Format as Server-Sent Event string.
        
        Returns:
            SSE-formatted string (event: type\\ndata: json\\n\\n)
        """
        return f"event: {self.event_type.value}\ndata: {json.dumps(self.data)}\n\n"


class StreamingEventEmitter:
    """
    Thread-safe async queue for SSE event emission.
    
    Implements Event emitter with asyncio.Queue for thread-safe events.
    
    Usage:
        emitter = StreamingEventEmitter(task_id, context_id)
        
        # Emit status update
        await emitter.emit_status(TaskState.working, "Processing...")
        
        # Subscribe and iterate
        async for event in emitter.subscribe():
            yield event.to_sse_format()
    """
    
    def __init__(self, task_id: str, context_id: str):
        """
        Initialize streaming event emitter.
        
        Args:
            task_id: A2A task identifier
            context_id: A2A context identifier
        """
        self.task_id = task_id
        self.context_id = context_id
        self._queue: asyncio.Queue[StreamEvent] = asyncio.Queue()
        self._closed = False
        self._subscribers: list[asyncio.Queue[StreamEvent]] = []
        
    async def emit_status(
        self,
        state: TaskState,
        message: str,
        final: bool = False,
        metadata: Optional[dict[str, Any]] = None
    ) -> None:
        """
        Emit a status-update event.
        
        Args:
            state: TaskState enum value
            message: Human-readable status message
            final: Whether this is the final status update (FR-012)
            metadata: Optional additional metadata
        """
        # Build A2AStatusUpdate using helper
        status_data = build_status_update_data(
            task_id=self.task_id,
            context_id=self.context_id,
            state=state,
            message=message,
            final=final,
            metadata=metadata
        )
        
        event = StreamEvent(
            event_type=StreamEventType.STATUS_UPDATE,
            data=status_data,
            task_id=self.task_id,
            context_id=self.context_id,
            final=final
        )
        
        await self._emit(event)
        
        logger.debug(
            "Emitted status-update event",
            extra={
                "task_id": self.task_id,
                "state": state.value,
                "final": final
            }
        )
    
    async def emit_artifact(
        self,
        artifact_name: str,
        parts: list[dict[str, Any]],
        append: bool = False,
        last_chunk: bool = True,
        description: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None
    ) -> None:
        """
        Emit an artifact-update event.
        
        Args:
            artifact_name: Name of the artifact
            parts: List of A2A part dicts (TextPart, DataPart, etc.)
            append: Whether to append to existing artifact
            last_chunk: Whether this is the last chunk
            description: Optional artifact description
            metadata: Optional additional metadata
        """
        # Build A2AArtifactUpdate using helper
        artifact_data = build_artifact_update_data(
            task_id=self.task_id,
            context_id=self.context_id,
            artifact_name=artifact_name,
            parts=parts,
            append=append,
            last_chunk=last_chunk,
            description=description,
            metadata=metadata
        )
        
        event = StreamEvent(
            event_type=StreamEventType.ARTIFACT_UPDATE,
            data=artifact_data,
            task_id=self.task_id,
            context_id=self.context_id
        )
        
        await self._emit(event)
        
        logger.debug(
            "Emitted artifact-update event",
            extra={
                "task_id": self.task_id,
                "artifact_name": artifact_name,
                "last_chunk": last_chunk
            }
        )
    
    async def emit_tool_invocation(
        self,
        tool_name: str,
        action_count: int,
        observation_count: int,
        total_tokens: int
    ) -> None:
        """
        Emit status update for MCP tool invocation.
        
        Convenience method for emitting tool invocation updates
        during evaluation monitoring.
        
        Args:
            tool_name: Name of invoked tool
            action_count: Cumulative action count
            observation_count: Cumulative observation count
            total_tokens: Cumulative token count
        """
        # Build metadata using helper
        metadata = build_tool_invocation_metadata(
            tool_name=tool_name,
            action_count=action_count,
            observation_count=observation_count,
            total_tokens=total_tokens
        )
        
        await self.emit_status(
            state=TaskState.working,
            message=f"MCP tool invoked: {tool_name}",
            metadata=metadata
        )
    
    async def emit_final_status(
        self,
        state: TaskState,
        task_success: bool,
        final_reward: float,
        message: Optional[str] = None
    ) -> None:
        """
        Emit final status update (FR-012).
        
        Must be called when evaluation completes (success or failure).
        Sets final=true per A2A protocol.
        
        Args:
            state: Final TaskState (completed or failed)
            task_success: Whether the task succeeded
            final_reward: BrowserGym final reward
            message: Optional completion message
        """
        if message is None:
            if state == TaskState.completed:
                message = f"Evaluation completed. Success: {task_success}, Reward: {final_reward:.2f}"
            elif state == TaskState.failed:
                message = "Evaluation failed"
            else:
                message = f"Evaluation ended with state: {state.value}"
        
        metadata = {
            "completion": {
                "taskSuccess": task_success,
                "finalReward": final_reward
            }
        }
        
        await self.emit_status(
            state=state,
            message=message,
            final=True,
            metadata=metadata
        )
        
        logger.info(
            "Emitted final status-update",
            extra={
                "task_id": self.task_id,
                "state": state.value,
                "task_success": task_success,
                "final_reward": final_reward
            }
        )
    
    async def _emit(self, event: StreamEvent) -> None:
        """
        Internal emit to queue and all subscribers.
        
        Args:
            event: StreamEvent to emit
        """
        if self._closed:
            logger.warning("Attempted to emit to closed emitter")
            return
        
        await self._queue.put(event)
        
        # Also send to all active subscribers
        for subscriber_queue in self._subscribers:
            try:
                await subscriber_queue.put(event)
            except Exception as e:
                logger.warning(f"Failed to emit to subscriber: {e}")
    
    async def subscribe(self) -> AsyncGenerator[StreamEvent, None]:
        """
        Subscribe to event stream.
        
        Yields:
            StreamEvent objects as they are emitted
        """
        subscriber_queue: asyncio.Queue[StreamEvent] = asyncio.Queue()
        self._subscribers.append(subscriber_queue)
        
        try:
            while not self._closed:
                try:
                    # Wait with timeout to allow checking closed status
                    event = await asyncio.wait_for(
                        subscriber_queue.get(),
                        timeout=1.0
                    )
                    yield event
                    
                    # Stop after final event
                    if event.final:
                        break
                        
                except asyncio.TimeoutError:
                    # Continue loop to check if closed
                    continue
        finally:
            self._subscribers.remove(subscriber_queue)
    
    def close(self) -> None:
        """Close the emitter, stopping all subscriptions."""
        self._closed = True
        logger.debug(f"Closed streaming emitter for task {self.task_id}")
    
    @property
    def is_closed(self) -> bool:
        """Check if emitter is closed."""
        return self._closed


class SharedStateMonitor:
    """
    Monitor shared state and emit streaming updates.
    
    Watches the shared state file for changes and automatically
    emits status-update events when tool invocations occur.
    
    Usage:
        monitor = SharedStateMonitor(state_manager, emitter)
        await monitor.start()
        # ... evaluation runs ...
        await monitor.stop()
    """
    
    def __init__(
        self,
        state_manager: SharedStateManager,
        emitter: StreamingEventEmitter,
        poll_interval: float = 0.5
    ):
        """
        Initialize shared state monitor.
        
        Args:
            state_manager: SharedStateManager to monitor
            emitter: StreamingEventEmitter for updates
            poll_interval: Polling interval in seconds
        """
        self.state_manager = state_manager
        self.emitter = emitter
        self.poll_interval = poll_interval
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._last_invocation_count = 0
        self._last_tool = ""
    
    async def start(self) -> None:
        """Start monitoring in background task."""
        if self._running:
            return
        
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        
        logger.info(
            "Started shared state monitor",
            extra={"session_id": self.state_manager.session_id}
        )
    
    async def stop(self) -> None:
        """Stop monitoring."""
        self._running = False
        
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        
        logger.info(
            "Stopped shared state monitor",
            extra={"session_id": self.state_manager.session_id}
        )
    
    async def _monitor_loop(self) -> None:
        """
        Main monitoring loop.
        
        Polls shared state and emits events on changes.
        """
        while self._running:
            try:
                state = self.state_manager.read_state()
                await self._process_state(state)
                await asyncio.sleep(self.poll_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in state monitor: {e}", exc_info=True)
                await asyncio.sleep(self.poll_interval)
    
    async def _process_state(self, state: EvaluationState) -> None:
        """
        Process state changes and emit appropriate events.
        
        Args:
            state: Current evaluation state
        """
        # Check for new tool invocations
        if state.mcp_tool_invocations > self._last_invocation_count:
            if state.last_tool != self._last_tool:
                await self.emitter.emit_tool_invocation(
                    tool_name=state.last_tool,
                    action_count=state.action_count,
                    observation_count=state.observation_count,
                    total_tokens=state.total_tokens
                )
                self._last_tool = state.last_tool
            self._last_invocation_count = state.mcp_tool_invocations
        
        # Check for completion
        if state.cleanup_called:
            final_state = TaskState.completed if state.task_success else TaskState.failed
            await self.emitter.emit_final_status(
                state=final_state,
                task_success=state.task_success,
                final_reward=state.final_reward
            )
            self._running = False
        
        # Check for errors
        if state.error:
            await self.emitter.emit_status(
                state=TaskState.failed,
                message=f"Error: {state.error}",
                final=True
            )
            self._running = False


async def stream_events_as_sse(
    emitter: StreamingEventEmitter
) -> AsyncGenerator[str, None]:
    """
    Stream events from emitter as SSE-formatted strings.
    
    Used by the /message/stream endpoint to yield SSE data.
    
    Args:
        emitter: StreamingEventEmitter to stream from
        
    Yields:
        SSE-formatted strings
    """
    async for event in emitter.subscribe():
        yield event.to_sse_format()


# Module-level emitter registry for active tasks
_active_emitters: dict[str, StreamingEventEmitter] = {}


def get_or_create_emitter(task_id: str, context_id: str) -> StreamingEventEmitter:
    """
    Get existing emitter or create new one for task.
    
    Args:
        task_id: A2A task identifier
        context_id: A2A context identifier
        
    Returns:
        StreamingEventEmitter for the task
    """
    if task_id not in _active_emitters:
        _active_emitters[task_id] = StreamingEventEmitter(task_id, context_id)
    return _active_emitters[task_id]


def remove_emitter(task_id: str) -> None:
    """
    Remove and close emitter for task.
    
    Args:
        task_id: A2A task identifier
    """
    if task_id in _active_emitters:
        _active_emitters[task_id].close()
        del _active_emitters[task_id]


def get_emitter(task_id: str) -> Optional[StreamingEventEmitter]:
    """
    Get emitter for task if exists.
    
    Args:
        task_id: A2A task identifier
        
    Returns:
        StreamingEventEmitter or None
    """
    return _active_emitters.get(task_id)

def map_agent_event_to_sse(
    event_type: str,
    event_data: dict[str, Any],
    task_id: str,
    context_id: str
) -> TaskStatusUpdateEvent:
    """
    Map agent events to A2A TaskStatusUpdateEvent for SSE streaming.
    
    Converts OpenAI Agents SDK events (tool calls, agent thinking, guardrails)
    into A2A protocol status-update events.
    
    Args:
        event_type: Agent event type ('tool_call', 'tool_result', 'agent_thinking', 'guardrail')
        event_data: Event data from agent execution
        task_id: A2A task identifier
        context_id: A2A context identifier
    
    Returns:
        TaskStatusUpdateEvent formatted for A2A protocol
        
    Example:
        event = map_agent_event_to_sse(
            'tool_call',
            {'tool_name': 'send_mcp_details_to_purple_agent', 'args': {...}},
            'task_123',
            'ctx_456'
        )
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    
    # Map event types to A2A status states and messages
    if event_type == "tool_call":
        tool_name = event_data.get("tool_name", "unknown")
        state = TaskState.working
        message = f"Tool invoked: {tool_name}"
        
    elif event_type == "tool_result":
        tool_name = event_data.get("tool_name", "unknown")
        status = event_data.get("status", "unknown")
        state = TaskState.working
        message = f"Tool completed: {tool_name} ({status})"
        
    elif event_type == "agent_thinking":
        reasoning = event_data.get("reasoning", "")
        state = TaskState.working
        message = f"Agent reasoning: {reasoning[:100]}"  # Truncate long reasoning
        
    elif event_type == "guardrail":
        guardrail_type = event_data.get("guardrail_type", "unknown")
        is_valid = event_data.get("is_valid", False)
        state = TaskState.working if is_valid else TaskState.blocked
        message = f"Guardrail {guardrail_type}: {'passed' if is_valid else 'blocked'}"
        
    else:
        state = TaskState.working
        message = f"Agent event: {event_type}"
    
    # Create A2A TaskStatusUpdateEvent
    return TaskStatusUpdateEvent(
        taskId=task_id,
        contextId=context_id,
        status=TaskStatus(
            state=state,
            message=message,
            timestamp=timestamp
        ),
        final=False,
        metadata=event_data
    )
