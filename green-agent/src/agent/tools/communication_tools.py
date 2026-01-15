"""
Communication tools for A2A protocol interaction.

Tools for:
- Sending task details and MCP connection info to Purple Agent via A2A messages
- Emitting task status updates

The message sent to Purple Agent is a comprehensive TEXT message that includes:
- Task details (ID, benchmark, objective)
- MCP server connection details
- Available MCP tools with full documentation (dynamically extracted)
- Execution instructions

Purple Agent processes text only - no structured data parsing required.
"""

from typing import Any, Optional
import json
import uuid
import httpx
from agents.run_context import RunContextWrapper

from src.agent.context import AgentContext
from src.a2a.message_handler import emit_task_update
from src.benchmarks.profiles import (
    BenchmarkProfileRegistry,
    BenchmarkProfile,
    get_profile_for_task,
)
from src.utils.shared_state import DEFAULT_MAX_TOOL_CALLS
from src.mcp import (
    ToolMetadata,
    get_all_tools_metadata,
    format_tools_documentation,
)
from src.a2a.message_builders import (
    build_task_message as _build_task_message,
)
from a2a.types import TaskStatus, TaskState, Message, Part, TextPart, Role
from a2a.client import A2ACardResolver, ClientFactory, ClientConfig
from src.utils.logging import get_logger

logger = get_logger(__name__)


# =============================================================================
# Task Message Builder
# =============================================================================

# Imported from message_builders module for better modularity
_build_task_message = _build_task_message


# =============================================================================
# Send Task Details Tool (renamed from send_mcp_details_to_purple_agent)
# =============================================================================

async def send_task_details_to_purple_agent(ctx: RunContextWrapper[AgentContext]) -> dict:
    """
    Send comprehensive task details to Purple Agent
    
    Builds and sends a detailed TEXT message containing:
    - Task identification (task_id, benchmark)
    - Benchmark-specific configuration (token limits, observation mode)
    - MCP server connection details
    - Complete tool documentation with arguments and examples
    - Step-by-step execution instructions
    
    Purple Agent processes this as plain text - no structured data parsing required.
    The environment is already initialized by Green Agent before this is called.
    
    Returns:
        dict with status, message, and sent flag
    """
    # Extract context
    try:
        if hasattr(ctx, "context"):
            context = ctx.context
        elif isinstance(ctx, AgentContext):
            context = ctx
        else:
            return {
                "status": "error",
                "message": "Invalid context: expected RunContextWrapper or AgentContext",
                "sent": False
            }
    except Exception as e:
        logger.error(f"Failed to resolve context: {e}")
        return {"status": "error", "message": str(e), "sent": False}
    
    # Validate task_id and benchmark
    task_id = context.task_id or context.default_task_id
    benchmark = context.benchmark or context.default_benchmark
    
    if not task_id:
        logger.error("No task_id available in context")
        return {"status": "error", "message": "No task_id configured", "sent": False}
    
    # Validate benchmark exists in registry
    try:
        profile = get_profile_for_task(task_id)
        logger.info(f"Validated task: {task_id} -> benchmark={profile.benchmark_id}")
    except Exception as e:
        logger.warning(f"Could not validate benchmark profile: {e}, using default")
        profile = None
    
    # Check MCP server health
    if not context.mcp_server_healthy:
        logger.error("MCP server not healthy", extra={"session_id": context.session_id})
        return {
            "status": "error",
            "message": "MCP server not healthy",
            "sent": False
        }
    
    # Check MCP connection details available
    if not context.mcp_connection_details:
        logger.error("MCP connection details not available", extra={"session_id": context.session_id})
        return {
            "status": "error",
            "message": "MCP connection details not available",
            "sent": False
        }
    
    # Get MCP connection details as dict
    mcp_dict = context.mcp_connection_details.model_dump()
    
    # Get Purple Agent URL from context
    purple_agent_url = context.purple_agent_url
    if not purple_agent_url:
        logger.error("No Purple Agent URL in context")
        return {
            "status": "error",
            "message": "No Purple Agent URL configured",
            "sent": False
        }
    
    try:
        # Get tool metadata from mcp_connection_details if available, otherwise extract dynamically
        tools_details = []
        if context.mcp_connection_details and hasattr(context.mcp_connection_details, 'tools_details'):
            tools_details = context.mcp_connection_details.tools_details or []
        
        if not tools_details:
            # Dynamically extract tool metadata from MCP server
            logger.info("Extracting MCP tool metadata dynamically...")
            tools_details = get_all_tools_metadata(benchmark)
            logger.info(f"Extracted {len(tools_details)} MCP tools")
        
        # Get task goal from session's current observation (if available)
        task_goal = None
        if context.shared_state_manager:
            try:
                from src.environment.session_manager import SessionManager
                session_mgr = SessionManager()
                session = session_mgr.get_session()
                if session and session.current_observation:
                    task_goal = session.current_observation.get("goal", "")
                    if task_goal:
                        logger.info(f"Retrieved task goal from observation: {task_goal[:100]}...")
            except Exception as e:
                logger.warning(f"Could not retrieve task goal: {e}")
        
        # Build comprehensive task message (TEXT only)
        task_message = _build_task_message(
            task_id=task_id,
            benchmark=benchmark,
            mcp_details=mcp_dict,
            tools_details=tools_details,
            profile=profile,
            task_goal=task_goal,
        )
        print(task_message)
        logger.info(
            f"Built task message for Purple Agent",
            extra={
                "task_id": task_id,
                "benchmark": benchmark,
                "message_length": len(task_message),
            }
        )
        
        # Create A2A client to send message TO Purple Agent
        # Extended timeout for agent processing (5 minutes for complex tasks)
        timeout = httpx.Timeout(300.0, connect=10.0, read=300.0, write=30.0)
        async with httpx.AsyncClient(timeout=timeout) as httpx_client:
            # Get Purple Agent card
            logger.info(f"Connecting to Purple Agent at {purple_agent_url}")
            base_url = str(purple_agent_url).rstrip('/')
            
            # Pre-flight health check to provide better error message if server is down
            try:
                health_resp = await httpx_client.get(f"{base_url}/health", timeout=5.0)
                if health_resp.status_code != 200:
                    logger.warning(f"Purple Agent health check returned {health_resp.status_code}")
            except Exception as e:
                logger.error(f"Purple Agent unreachable at {base_url}: {e}")
                return {
                    "status": "error",
                    "message": f"Purple Agent unreachable at {base_url}. Ensure Purple Agent server is running on port 9010.",
                    "sent": False
                }

            resolver = A2ACardResolver(httpx_client=httpx_client, base_url=base_url)
            try:
                purple_agent_card = await resolver.get_agent_card()
            except Exception as e:
                logger.error(f"Failed to fetch Purple Agent card: {e}")
                return {
                    "status": "error",
                    "message": f"Failed to fetch Purple Agent card from {base_url}. Error: {str(e)}",
                    "sent": False
                }
            
            logger.info(f"Connected to Purple Agent: {purple_agent_card.name}")
            
            # Create A2A client with streaming enabled
            client_config = ClientConfig(httpx_client=httpx_client, streaming=True)
            factory = ClientFactory(client_config)
            a2a_client = factory.create(purple_agent_card)
            
            # Build A2A message with TEXT part only (Purple Agent processes text)
            message = Message(
                kind="message",
                role=Role.user,
                parts=[
                    Part(root=TextPart(kind="text", text=task_message)),
                ],
                message_id=uuid.uuid4().hex,
            )
            
            logger.info("Sending task details to Purple Agent...")
            
            # Send message and process streaming response
            send_result = a2a_client.send_message(message)
            
            response = None
            chunk_count = 0
            
            if hasattr(send_result, "__aiter__"):
                async for chunk in send_result:
                    chunk_count += 1
                    logger.info(f"Received chunk {chunk_count} from Purple Agent")
                    response = chunk
            else:
                response = await send_result

            logger.info(
                "[OK] Task details sent to Purple Agent",
                extra={
                    "session_id": context.session_id,
                    "task_id": task_id,
                    "benchmark": benchmark,
                    "chunks_received": chunk_count,
                    "response_preview": str(response)[:200] if response else "None"
                }
            )
            
            return {
                "status": "success",
                "message": f"Task details sent to Purple Agent. Task: {task_id} ({benchmark}). Waiting for completion.",
                "task_id": task_id,
                "benchmark": benchmark,
                "mcp_url": mcp_dict.get("url"),
                "sent": True
            }
        
    except Exception as e:
        logger.error(f"Failed to send task details to Purple Agent: {e}", exc_info=True)
        return {"status": "error", "message": str(e), "sent": False}


# =============================================================================
# Send Task Update Tool
# =============================================================================

async def send_task_update(
    ctx: RunContextWrapper[AgentContext],
    status: str,
    message: str,
    final: bool = False
) -> dict:
    """
    Send task status update via A2A protocol.
    
    Args:
        ctx: RunContextWrapper with AgentContext
        status: Status string ('initialization', 'running', 'complete', 'error')
        message: Human-readable status message
        final: Whether this is the final update
    
    Returns:
        Dict with update status
    """
    context: AgentContext = ctx.context
    
    # Emit via task updater
    await emit_task_update(
        updater=context.task_updater,
        status=status,
        message=message,
        final=final
    )
    
    logger.info(
        f"Task update sent: {status}",
        extra={
            "session_id": context.session_id,
            "status": status,
            "task_message": message,
            "final": final,
        }
    )
    
    return {
        "status": "sent",
        "update_status": status,
        "message": message,
        "final": final
    }


__all__ = [
    "send_task_details_to_purple_agent",
    "send_task_update",
]
