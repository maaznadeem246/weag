"""
OsworldAgentExecutor — A2A AgentExecutor implementation.

Bridges the A2A SDK protocol layer and OsworldAgent:
1. Parses the incoming A2A Message into a StepMessage.
2. Looks up (or initialises) the in-memory conversation history for the context_id.
3. Calls OsworldAgent.run() to get a StepResponse.
4. Appends the exchange to history.
5. Sends the two-part A2A response (TextPart + DataPart) via TaskUpdater.
"""

import logging
from typing import Optional

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue

from .agent import OsworldAgent
from .messenger import build_step_response, parse_step_message

logger = logging.getLogger(__name__)


class OsworldAgentExecutor(AgentExecutor):
    """
    A2A executor for OSWorld Purple Agent.

    Maintains a per-context_id conversation history dict so the LLM can
    observe the full evaluation trajectory.  History is in-memory only
    and cleared when the process restarts.
    """

    def __init__(self, agent: Optional[OsworldAgent] = None) -> None:
        """
        Initialise executor.

        Args:
            agent: Pre-built OsworldAgent, or None to create one from env vars.
        """
        self._agent: OsworldAgent = agent or OsworldAgent()
        self._sessions: dict[str, list[dict]] = {}

    async def execute(
        self,
        request: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """
        Handle one evaluation step.

        Parses the incoming message, runs the agent, and emits a response
        message via the event queue.

        Args:
            request: A2A request context containing the incoming message.
            event_queue: A2A event queue for sending response messages.
        """
        context_id: str = request.context_id or "default"
        history = self._sessions.setdefault(context_id, [])

        # --- Parse incoming message ---
        try:
            step = parse_step_message(request.message)
        except Exception as exc:
            error_msg = f"Failed to parse incoming message: {exc}"
            logger.error(error_msg, exc_info=True)
            response_msg = build_step_response(error_msg, ["FAIL"], context_id, request.task_id)
            await event_queue.enqueue_event(response_msg)
            return

        logger.info(
            "Step received — context=%s instruction=%.80r screenshot=%s",
            context_id,
            step.instruction,
            f"{len(step.screenshot_b64)} bytes" if step.screenshot_b64 else "none",
        )

        # --- Run agent ---
        # agent.run() returns (StepResponse, updated_history) where updated_history
        # is result.to_input_list() — the SDK-idiomatic way to carry history forward.
        response, new_history = await self._agent.run(step, history)
        self._sessions[context_id] = new_history

        logger.info(
            "Step response — context=%s reasoning=%.80r action_count=%d",
            context_id,
            response.reasoning,
            len(response.actions),
        )
        logger.debug(
            "Full history length after step: %d messages, context=%s",
            len(new_history),
            context_id,
        )

        # --- Send response ---
        response_msg = build_step_response(
            response.reasoning, response.actions, context_id, request.task_id
        )
        await event_queue.enqueue_event(response_msg)

    async def cancel(
        self,
        request: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """Handle task cancellation (no-op — steps are atomic)."""
        logger.info("Cancel requested for context=%s — no-op", request.context_id)


__all__ = ["OsworldAgentExecutor"]
