"""
Green Executor for A2A protocol integration.
Bridges LLM Agent with A2A SDK's AgentExecutor interface.

New architecture: LLM handles all messages, background orchestrator runs independently.
"""

from abc import abstractmethod
from typing import Optional
from pydantic import ValidationError

from agents import Runner
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import (
    Task,
    TaskState,
    Part,
    TextPart,
    DataPart,
)
from a2a.utils import (
    new_agent_text_message,
    new_task,
)
from a2a.utils.errors import ServerError
from a2a.types import InvalidParamsError as InvalidParamsModel

from src.utils.models import EvalRequest
from src.agent.context import AgentContext
from src.utils.logging import get_logger

logger = get_logger(__name__)


class GreenAgent:
    """
    Abstract base class for Green Agent implementations.
    Defines the interface for context setup.
    """
    
    @abstractmethod
    def setup_context(self, request: EvalRequest) -> AgentContext:
        """
        Setup agent context from evaluation request.
        
        Args:
            request: EvalRequest with participants and config
            
        Returns:
            Configured AgentContext
        """
        pass
    
    @abstractmethod
    def validate_request(self, request: EvalRequest) -> tuple[bool, str]:
        """
        Validate assessment request.
        
        Args:
            request: EvalRequest to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        pass


class GreenExecutor(AgentExecutor):
    """
    A2A protocol executor for green agents.
    
    New architecture:
    - Every A2A message goes to Runner.run(LLM)
    - LLM responds immediately via final_output
    - LLM can call start_assessment() to start background orchestrator
    - Background orchestrator runs independently
    """
    
    def __init__(self, green_agent: GreenAgent):
        """
        Initialize executor with green agent instance.
        
        Args:
            green_agent: Instance of BrowserGymGreenAgent
        """
        self._green_agent = green_agent
        self._context: Optional[AgentContext] = None
    
    async def execute(
        self,
        request: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """
        Execute A2A message by routing to LLM agent.
        
        This method:
        1. Extracts user message from A2A request
        2. Sets up context if first message
        3. Calls Runner.run() with LLM agent
        4. Returns LLM's final_output as A2A response
        
        Args:
            request: A2A request context
            event_queue: Event queue for A2A responses
        """
        logger.info(
            "Processing A2A message",
            extra={
                "context_id": request.context_id,
                "message_id": request.message.message_id if request.message else None
            }
        )
        
        # Extract user message text
        user_message = self._extract_user_message(request)
        
        # Parse EvalRequest if this is an initial request (for context setup)
        eval_request = self._try_parse_eval_request(request)
        
        # Setup context if needed (first message or new request)
        if self._context is None or eval_request:
            if eval_request:
                self._context = self._green_agent.setup_context(eval_request)
                logger.info("Created new AgentContext from EvalRequest")
            else:
                logger.warning("No context and no EvalRequest - using minimal context")
                # Create minimal context for follow-up messages
                self._context = AgentContext()
        
        # Create A2A task
        task = new_task(request.message)
        await event_queue.enqueue_event(task)
        
        # Create task updater
        updater = TaskUpdater(
            event_queue=event_queue,
            task_id=task.id,
            context_id=task.context_id
        )
        
        try:
            # Update to working state
            await updater.update_status(
                state=TaskState.working,
                message=new_agent_text_message("Processing message...")
            )
            
            # Get LLM agent (lazy import to avoid circular imports)
            from src.agent.agent_factory import get_evaluation_agent
            agent = get_evaluation_agent()
            
            # Run LLM with user message
            logger.info(f"Calling Runner.run() with message: {user_message[:100]}...")
            result = await Runner.run(
                agent,
                user_message,
                context=self._context,
            )
            
            # Get LLM response
            llm_response = result.final_output if result.final_output else "Processing complete."
            
            logger.info(f"LLM response: {llm_response[:200]}...")
            
            # Send response back to Purple Agent
            await updater.update_status(
                state=TaskState.completed,
                message=new_agent_text_message(llm_response)
            )
            
            logger.info("A2A message processed successfully")
            
        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
            
            try:
                await updater.update_status(
                    state=TaskState.failed,
                    message=new_agent_text_message(f"Error: {str(e)}")
                )
            except RuntimeError:
                pass  # Task already terminal
    
    def _extract_user_message(self, request: RequestContext) -> str:
        """Extract text message from A2A request."""
        try:
            return request.get_user_input()
        except Exception:
            # Fallback: extract from parts
            for part in request.message.parts:
                if hasattr(part, 'root'):
                    root = part.root
                    if hasattr(root, 'text'):
                        return root.text
            return "Hello"
    
    def _try_parse_eval_request(self, request: RequestContext) -> Optional[EvalRequest]:
        """Try to parse EvalRequest from A2A message (for initial requests)."""
        try:
            # Check for DataPart first
            for part in request.message.parts:
                if hasattr(part, 'root'):
                    root = part.root
                    if hasattr(root, 'kind') and root.kind == 'data' and hasattr(root, 'data'):
                        return EvalRequest.model_validate(root.data)
            
            # Try JSON parsing
            user_input = request.get_user_input()
            try:
                return EvalRequest.model_validate_json(user_input)
            except Exception:
                pass
            
            # Not a structured request - return None
            return None
            
        except Exception as e:
            logger.debug(f"Could not parse EvalRequest: {e}")
            return None
    
    async def cancel(
        self,
        request: RequestContext,
        event_queue: EventQueue
    ) -> Task | None:
        """
        Cancel ongoing assessment.
        
        Args:
            request: A2A request context
            event_queue: Event queue for A2A responses
            
        Returns:
            Cancelled task or None
        """
        logger.info("Cancellation requested")
        
        try:
            # Cancel orchestrator if running
            if self._context and self._context.assessment_tracker:
                assessment = self._context.assessment_tracker
                if assessment.orchestrator_task and not assessment.orchestrator_task.done():
                    assessment.orchestrator_task.cancel()
                    logger.info("Cancelled orchestrator task")
            
            return None
            
        except Exception as e:
            logger.error(f"Error during cancellation: {e}", exc_info=True)
            return None
