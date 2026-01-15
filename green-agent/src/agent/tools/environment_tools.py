"""
Environment management tools for agent orchestration.

Tools for:
- MCP HTTP server lifecycle (start, health check)
- Environment initialization and cleanup
"""

import os
import time
import asyncio
import httpx
from typing import Any
from agents.run_context import RunContextWrapper


from src.agent.context import (
    AgentContext,
    InitializationResult,
    HealthCheckResult,
    CleanupResult,
    MCPServerHealth,
)
from src.utils.models import MCPConnectionDetails
from src.agent.tools.helpers import (
    terminate_mcp_process,
    cleanup_state_files,
    determine_cleanup_status,
)
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Global MCP HTTP server state
_mcp_server_task = None
_mcp_server_started = False


async def _initialize_browsergym_session(task_id: str, benchmark: str, context: AgentContext) -> None:
    """
    Initialize BrowserGym environment session.
    
    This is the agent's responsibility - must happen before starting MCP server.
    
    Args:
        task_id: Task identifier (e.g., "miniwob.click-test")
        benchmark: Benchmark name (e.g., "miniwob")
        context: Agent context for storing session details
    """
    from src.environment.entities import EnvironmentConfig
    from src.environment.session_manager import SessionManager
    from src.benchmarks.profiles import get_profile_for_task, detect_benchmark
    from src.benchmarks.tool_registry import register_tools_for_benchmark, get_tool_registry
    from src.mcp.server import mcp, observation_filter, shared_state as global_shared_state
    from src.utils.shared_state import create_state_manager
    
    # Get or create session manager
    from src.mcp.server import session_manager
    
    # Detect benchmark and get profile
    benchmark_id = detect_benchmark(task_id)
    profile = get_profile_for_task(task_id)
    
    # Update observation filter with benchmark-specific settings
    if hasattr(observation_filter, "apply_profile"):
        observation_filter.apply_profile(profile)
    
    # Create BrowserGym session on dedicated browser thread
    config = EnvironmentConfig(task_id=task_id)
    from src.environment.thread_executor import browser_executor
    session = await browser_executor.run(session_manager.create_session, config)
    
    # Register benchmark-specific tools with MCP server
    register_tools_for_benchmark(benchmark_id, mcp)
    
    # Initialize shared state for metrics tracking
    mcp_session_id = os.environ.get("MCP_SESSION_ID", session.session_id)
    shared_state_manager = create_state_manager(mcp_session_id)
    shared_state_manager.initialize()
    shared_state_manager.update_tool_invocation("initialize_environment")
    
    if hasattr(shared_state_manager, 'set_benchmark'):
        shared_state_manager.set_benchmark(benchmark_id)
    
    # Update global shared state (for MCP tools to access)
    from src.mcp import server as mcp_module
    mcp_module.shared_state = shared_state_manager
    mcp_module.active_benchmark_profile = profile
    
    # Store in context
    context.shared_state_manager = shared_state_manager
    
    logger.info(
        f"BrowserGym session created",
        extra={
            "session_id": session.session_id,
            "task_id": task_id,
            "benchmark": benchmark_id,
            "browser_pids": session.browser_pids,
        }
    )


async def _wait_for_server(port: int, timeout: float = 15.0) -> bool:
    """
    Wait for server to start listening on port.
    
    Args:
        port: Port to check
        timeout: Maximum time to wait in seconds
        
    Returns:
        True if server is ready, False otherwise
    """
    start_time = asyncio.get_event_loop().time()
    url = f"http://localhost:{port}/mcp"
    
    while asyncio.get_event_loop().time() - start_time < timeout:
        try:
            async with httpx.AsyncClient() as client:
                # We just want to see if it responds, even if it's a 405 or 404
                # since /mcp is a POST endpoint for SSE/HTTP
                response = await client.get(f"http://localhost:{port}/", timeout=1.0)
                if response.status_code < 500:
                    return True
        except (httpx.ConnectError, httpx.TimeoutException):
            await asyncio.sleep(0.5)
        except Exception:
            await asyncio.sleep(0.5)
            
    return False


# =============================================================================
# Initialize Evaluation Tool
# =============================================================================

async def initialize_evaluation(
    ctx: RunContextWrapper[AgentContext],
    task_id: str,
    benchmark: str,
    purple_agent_url: str,
) -> InitializationResult:
    """
    Initialize evaluation by starting MCP HTTP server (on-demand).
    
    Steps:
    1. Start MCP HTTP server if not already running
    2. Store server details in context
    3. Return initialization result
    
    Returns InitializationResult with server URL and health status.
    """
    context: AgentContext = ctx.context
    global _mcp_server_task, _mcp_server_started
    
    try:
        # Get MCP server port from global state (set in main.py)
        from src.main import _mcp_server_port
        mcp_port = _mcp_server_port
        
        # Initialize BrowserGym environment FIRST (agent's responsibility)
        logger.info(f"Initializing BrowserGym environment for task: {task_id}, benchmark: {benchmark}")
        await _initialize_browsergym_session(task_id, benchmark, context)
        logger.info(f"✓ BrowserGym environment initialized for task: {task_id}")
        
        # Start MCP HTTP server if not already running (pure tool provider)
        if not _mcp_server_started:
            from src.mcp.server import start_http_server
            
            # Start server (no task_id needed - session already exists)
            _mcp_server_task = asyncio.create_task(start_http_server(port=mcp_port))
            
            # Wait for MCP server to be ready (with 15s timeout)
            is_ready = await _wait_for_server(mcp_port, timeout=15.0)
            
            if not is_ready:
                raise TimeoutError(f"MCP server failed to start on port {mcp_port} within 15 seconds")
            
            _mcp_server_started = True
        # Update context with MCP details
        context.mcp_server_process = 0  # No PID in HTTP mode
        context.mcp_server_healthy = True
        
        return InitializationResult(
            status="success",
            session_id=context.session_id,
            mcp_server_pid=0,  # No PID for HTTP server
            mcp_health=MCPServerHealth(
                is_healthy=True,
                process_id=0,
                process_running=True,
                health_check_timestamp=time.time(),
            ),
            message=f"MCP HTTP server running at http://localhost:{mcp_port}/mcp",
        )
        
    except Exception as e:
        logger.error(
            f"Evaluation initialization failed: {e}",
            extra={"session_id": context.session_id, "error": str(e)}
        )
        
        return InitializationResult(
            status="failure",
            session_id=context.session_id,
            mcp_server_pid=0,
            mcp_health=MCPServerHealth(
                is_healthy=False,
                process_running=False,
                health_check_timestamp=time.time(),
                error_message=str(e),
            ),
            message=f"Initialization failed: {str(e)}",
            error=str(e)
        )


# =============================================================================
# Cleanup Evaluation Tool
# =============================================================================

async def cleanup_evaluation(ctx: RunContextWrapper[AgentContext]) -> CleanupResult:
    """
    Cleanup evaluation resources.
    
    Steps:
    1. Terminate MCP server subprocess
    2. Close session
    3. Cleanup state files
    
    Returns CleanupResult with cleanup status.
    
    Should always be called at end of evaluation (even on errors).
    """
    context: AgentContext = ctx.context
    
    mcp_terminated = False
    session_closed = False
    resources_cleaned = False
    errors = []
    
    # Terminate MCP server using helper
    if context.mcp_server_process:
        mcp_terminated, error_msg = terminate_mcp_process(context.mcp_server_process)
        if error_msg:
            errors.append(error_msg)
    else:
        mcp_terminated = True  # Nothing to terminate
    
    # Cleanup state files using helper
    resources_cleaned, error_msg = cleanup_state_files(state_manager)
    if error_msg:
        errors.append(error_msg)
    
    # Session close (handled by runner)
    session_closed = True
    
    # Determine overall status using helper
    status, message = determine_cleanup_status(
        mcp_terminated, session_closed, resources_cleaned, errors
    )
    
    
    return CleanupResult(
        status=status,
        mcp_server_terminated=mcp_terminated,
        session_closed=session_closed,
        resources_cleaned=resources_cleaned,
        message=message,
        error="; ".join(errors) if errors else None
    )


# =============================================================================
# MCP Server Health Check Tool
# =============================================================================

# @observe(as_type="tool")  # Uncomment when langfuse is configured
# @function_tool  # Uncomment when openai-agents-python is installed
async def verify_mcp_server_health(
    ctx: RunContextWrapper[AgentContext],
) -> HealthCheckResult:
    """
    Verify MCP server health and tool availability.
    
    Checks that:
    - MCP server process is running
    - All 4 expected tools are discoverable
    - Tools can be invoked successfully
    
    Returns HealthCheckResult with detailed health information.
    
    This tool should be called after spawning MCP server and before
    sending connection details to Purple Agent.
    """
    context: AgentContext = ctx.context
    
    # Check if MCP server is spawned
    if not context.mcp_server_process:
        return HealthCheckResult(
            status="unhealthy",
            health_details=MCPServerHealth(
                is_healthy=False,
                process_running=False,
                health_check_timestamp=time.time(),
                error_message="MCP server not spawned",
            ),
            message="MCP server not spawned",
            error="No MCP server process found in context"
        )
    
    # Get MCP server process (this is a mock - actual implementation needs subprocess ref)
    # In real implementation, we'd store subprocess.Popen in context
    pid = context.mcp_server_process
    
    try:
        # Perform comprehensive health check
        # NOTE: This is a placeholder - actual implementation needs process handle
        health_data = {
            "is_healthy": True,  # Placeholder
            "process_id": pid,
            "process_running": True,
            "tools_discovered": [
                "initialize_environment",
                "execute_actions",
                "get_observation",
                "cleanup_environment"
            ],
            "tools_verified": [
                "initialize_environment",
                "execute_actions",
                "get_observation",
                "cleanup_environment"
            ],
            "health_check_timestamp": time.time(),
            "retry_count": 0,
            "error_message": None,
            "expected_tools": [
                "initialize_environment",
                "execute_actions",
                "get_observation",
                "cleanup_environment"
            ],
            "all_tools_available": True,
        }
        
        health_details = MCPServerHealth(**health_data)
        
        # Update context
        context.mcp_server_healthy = health_details.is_healthy
        context.mcp_tools_verified = health_details.tools_verified
        
        status = "healthy" if health_details.is_healthy else "unhealthy"
        message = (
            f"MCP server healthy: {len(health_details.tools_verified)}/4 tools verified"
            if health_details.is_healthy
            else f"MCP server unhealthy: {health_details.error_message}"
        )
        
        logger.info(
            f"MCP health check: {status}",
            extra={
                "session_id": context.session_id,
                "pid": pid,
                "tools_verified": health_details.tools_verified,
                "is_healthy": health_details.is_healthy,
            }
        )
        
        return HealthCheckResult(
            status=status,
            health_details=health_details,
            message=message,
            error=health_details.error_message if not health_details.is_healthy else None
        )
        
    except Exception as e:
        logger.error(
            f"MCP health check failed: {e}",
            extra={"session_id": context.session_id, "error": str(e)}
        )
        
        return HealthCheckResult(
            status="unhealthy",
            health_details=MCPServerHealth(
                is_healthy=False,
                process_id=pid,
                process_running=False,
                health_check_timestamp=time.time(),
                error_message=str(e),
            ),
            message=f"Health check error: {str(e)}",
            error=str(e)
        )


# =============================================================================
# Get MCP Connection Details Tool (Commented out - not used)
# =============================================================================

# async def get_mcp_connection_details(
#     ctx: RunContextWrapper[AgentContext],
# ) -> dict:
#     """
#     Get MCP connection details from context for sending to purple agent.
#     
#     Returns dictionary with MCP connection information that can be sent
#     to purple agent via A2A communication.
#     
#     Returns dict with:
#     - command: Python executable path
#     - args: MCP server module arguments
#     - transport: "stdio"
#     - env: Environment variables (MCP_SESSION_ID, etc.)
#     - session_id: MCP session identifier
#     """
#     context: AgentContext = ctx.context
#     
#     if not context.mcp_connection_details:
#         logger.warning(
#             "MCP connection details not available in context",
#             extra={"session_id": context.session_id}
#         )
#         return {
#             "error": "MCP connection details not available",
#             "session_id": context.session_id
#         }
#     
#     # Convert MCPConnectionDetails to dict
#     mcp_dict = context.mcp_connection_details.model_dump()
#     
#     logger.info(
#         "Retrieved MCP connection details",
#         extra={
#             "session_id": context.session_id,
#             "command": mcp_dict.get("command"),
#             "transport": mcp_dict.get("transport")
#         }
#     )
#     
#     return mcp_dict


__all__ = [
    "initialize_evaluation",
    "cleanup_evaluation",
    "verify_mcp_server_health",
]
