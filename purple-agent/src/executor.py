"""
Purple Agent Executor for A2A protocol integration.
Handles incoming messages from Green Agent and executes evaluation tasks.

Based on A2A SDK AgentExecutor pattern.
"""

import asyncio
import logging
import uuid
import os
from typing import Dict, Any, Optional

from langfuse import observe, get_client
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import Part, TextPart, DataPart, Message, Role
from a2a.utils import new_agent_text_message

from src.agent import create_test_purple_agent, TestPurpleAgentContext
from src.config import PurpleAgentConfig
from agents import Runner

logger = logging.getLogger(__name__)


class PurpleAgentExecutor(AgentExecutor):
    """
    A2A executor for Purple Agent.
    
    Receives messages from Green Agent containing:
    - Task assignment (task_id, benchmark)
    - MCP connection details
    
    Executes the evaluation and sends results back via event queue.
    """
    
    def __init__(self, config: Optional[PurpleAgentConfig] = None):
        """
        Initialize Purple Agent executor.
        
        Args:
            config: Optional configuration (uses default if not provided)
        """
        self.config = config or PurpleAgentConfig()
        self._agent = None
        self._context = None
    
    def _extract_message_data(self, message: Message) -> Dict[str, Any]:
        """
        Extract data from A2A message parts.
        
        Args:
            message: A2A Message object
            
        Returns:
            Dict with extracted text message
        """
        result = {
            "text": "",
        }
        
        for part in message.parts:
            if hasattr(part, 'root'):
                root = part.root
                
                # Extract TextPart - the comprehensive task message from Green Agent
                if hasattr(root, 'kind') and root.kind == 'text' and hasattr(root, 'text'):
                    result["text"] = root.text
                    logger.debug(f"Extracted text message: {root.text[:200]}...")
        
        return result
    
    @observe(name="purple_agent_execute")
    async def execute(
        self,
        request: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """
        Execute evaluation task from Green Agent message.
        
        Args:
            request: A2A request context with message from Green Agent
            event_queue: Event queue for sending responses
        """
        # Link to unified trace if available
        assessment_trace_id = os.environ.get("ASSESSMENT_TRACE_ID")
        if assessment_trace_id:
            try:
                langfuse = get_client()
                langfuse.update_current_trace(
                    id=assessment_trace_id,
                    name=f"purple_agent_task_{request.context_id[:8]}"
                )
                logger.info(f"✓ Purple Agent: Linked to unified trace {assessment_trace_id}")
            except Exception as e:
                logger.warning(f"Failed to link to unified trace: {e}")

        logger.info(f"📨 Received task from Green Agent (context: {request.context_id})")
        
        try:
            # Extract text message from Green Agent
            message_data = self._extract_message_data(request.message)
            message_text = message_data.get("text", "")
            
            if not message_text:
                logger.error("No text message received from Green Agent")
                await event_queue.send_message(
                    new_agent_text_message("Error: No task message received from Green Agent")
                )
                return
            
            # NOTE: Do NOT send early acknowledgment - Green Agent waits for the final result
            # Sending an early message would cause Green Agent to think we're done
            
            # Create minimal agent context (task details are in the message text)
            self._context = TestPurpleAgentContext(
                task_id=request.context_id,  # Use context_id as task identifier
                benchmark="unknown",  # Benchmark info is in the message text
                task_description="Execute task from Green Agent",
                green_agent_url=self.config.green_agent_url,
                interaction_id=request.context_id,
                mcp_connection_details=None,  # MCP details are in the message text
            )
            
            # Create agent if not exists
            if not self._agent:
                self._agent = create_test_purple_agent(self.config)
            
            # Run agent evaluation with the complete text message
            # Pass the ENTIRE message from Green Agent to the LLM
            # The message already contains task details, MCP connection info, tool docs, and instructions
            print(message_text)
            initial_message = message_text
            
            # Run agent with a bounded timeout to avoid indefinite hangs.
            # run_timeout = getattr(self.config, "run_timeout", 300)
            result = None
            try:
                result = await Runner.run(self._agent, initial_message, context=self._context)
                print(f"Runner result: {result}")   
            except asyncio.TimeoutError:
                logger.error(f"Agent execution timed out")
                # Send timeout message back to Green Agent
                timeout_message = new_agent_text_message(
                    f"Purple Agent timed out after while executing task."
                )
                await event_queue.enqueue_event(timeout_message)
                return
            except Exception as e:
                logger.error(f"Agent Runner.run raised exception: {type(e).__name__}: {e}", exc_info=True)
                # Don't raise - send error message and continue to cleanup
                error_msg = new_agent_text_message(
                    f"Purple Agent execution failed: {type(e).__name__}: {str(e)}"
                )
                await event_queue.enqueue_event(error_msg)
                return
            
            logger.info(
                f"Agent execution complete: success={self._context.task_complete}, "
                f"reward={self._context.final_reward}"
            )
            
            # Cleanup MCP connections
            if self._context.mcp_registry:
                for server_name in list(self._context.mcp_registry.keys()):
                    conn_info = self._context.mcp_registry.get(server_name)
                    if conn_info:
                        # Get session from registry (handles both dict and direct session)
                        session = conn_info["session"] if isinstance(conn_info, dict) else conn_info
                        cm = conn_info.get("context_manager") if isinstance(conn_info, dict) else None
                        
                        # Call cleanup tool first
                        try:
                            await asyncio.wait_for(
                                session.call_tool("cleanup_environment", arguments={}),
                                timeout=10.0
                            )
                        except Exception:
                            pass  # Silent cleanup errors
                        
                        # Close session - suppress ConnectionResetError from pipe cleanup
                        if hasattr(session, 'close'):
                            try:
                                await session.close()
                            except Exception:
                                pass  # Silent close errors (ConnectionResetError, RuntimeError, etc.)
                        
                        # Properly exit context manager - suppress all async cleanup errors
                        if cm:
                            try:
                                await cm.__aexit__(None, None, None)
                            except Exception:
                                pass  # Silent exit errors (RuntimeError from cancel scope, ConnectionResetError, etc.)
                        
                        del self._context.mcp_registry[server_name]
            
            # Send final result message
            result_text = (
                f"Evaluation complete. "
                f"Task: {self._context.task_id}, "
                f"Success: {self._context.task_complete}, "
                f"Score: {self._context.final_reward}, "
                f"Actions: {self._context.actions_taken}"
            )
            
                # Send result as message with data part
            final_message = Message(
                kind="message",
                role=Role.agent,
                messageId=uuid.uuid4().hex,
                parts=[
                    Part(root=TextPart(kind="text", text=result_text)),
                    Part(root=DataPart(kind="data", data={
                        "task_id": self._context.task_id,
                        "benchmark": self._context.benchmark,
                        "task_success": self._context.task_complete,
                        "final_score": self._context.final_reward,
                        "actions_taken": self._context.actions_taken,
                    }))
                ]
            )

            # Try sending final message with retry and robust logging to avoid unhandled connection resets
            try:
                await event_queue.enqueue_event(final_message)
                logger.info(f"✅ Sent result to Green Agent: Success={self._context.task_complete}, Score={self._context.final_reward}")
            except Exception as e:
                try:
                    await asyncio.sleep(0.2)
                    await event_queue.enqueue_event(final_message)
                    logger.info(f"✅ Sent result to Green Agent (retry): Success={self._context.task_complete}, Score={self._context.final_reward}")
                except Exception as e2:
                    logger.error(f"Failed to send result: {e2}", exc_info=True)
            
        except Exception as e:
            logger.error(f"Evaluation failed: {e}", exc_info=True)
            
            # Send error message
            error_message = new_agent_text_message(
                f"Purple Agent evaluation failed: {str(e)}"
            )
            await event_queue.enqueue_event(error_message)
    
    async def cancel(
        self,
        request: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """
        Handle cancellation request.
        
        Args:
            request: A2A request context
            event_queue: Event queue for responses
        """
        logger.warning("Cancellation requested but not implemented")
        await event_queue.enqueue_event(
            new_agent_text_message("Cancellation not supported")
        )
