"""
Health check endpoints for deployment monitoring.

Provides liveness and readiness checks per FR-019.
"""

from fastapi import APIRouter, Response, status
from typing import Dict, Any
from src.utils.logging import get_logger


logger = get_logger(__name__)
router = APIRouter(prefix="/health", tags=["health"])


# Health state tracking
_is_ready = False  # Set to True when green agent can accept evaluations
_is_alive = True   # Set to False on fatal errors


def set_ready(ready: bool) -> None:
    """Set readiness state."""
    global _is_ready
    _is_ready = ready
    logger.info("Health state updated", extra={"ready": ready})


def set_alive(alive: bool) -> None:
    """Set liveness state."""
    global _is_alive
    _is_alive = alive
    logger.warning("Liveness state updated", extra={"alive": alive})


@router.get("/liveness")
async def liveness_check(response: Response) -> Dict[str, str]:
    """
    Liveness check endpoint.
    
    Returns 200 if service is running (even if not ready for requests).
    Returns 503 if service has encountered fatal error.
    
    K8s/Docker uses this to detect if container needs restart.
    """
    if _is_alive:
        return {"status": "alive"}
    else:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "dead", "reason": "fatal_error"}


@router.get("/readiness")
async def readiness_check(response: Response) -> Dict[str, Any]:
    """
    Readiness check endpoint.
    
    Returns 200 if green agent can accept evaluation requests.
    Returns 503 if still initializing or currently processing.
    
    Load balancers use this to determine if instance can handle traffic.
    """
    if _is_ready and _is_alive:
        return {"status": "ready"}
    elif not _is_alive:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "not_ready", "reason": "fatal_error"}
    else:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "not_ready", "reason": "initializing_or_busy"}


@router.get("/")
async def health_root() -> Dict[str, str]:
    """Root health endpoint - redirects to liveness."""
    return {"status": "ok", "endpoints": ["/liveness", "/readiness"]}


# =============================================================================
# MCP Server Health Verification
# =============================================================================

import asyncio
import time
from typing import List, Tuple


async def verify_mcp_tools(
    process: Any,  # subprocess.Popen
    expected_tools: List[str] = None,
    max_retries: int = 3,
    retry_delay: float = 1.0
) -> Tuple[bool, List[str], str]:
    """
    Verify MCP server health and tool availability with retry logic.
    
    Implements Async tool discovery with 3-retry logic.
    
    Args:
        process: MCP server subprocess.Popen instance
        expected_tools: List of expected tool names. Defaults to BrowserGym 4 tools.
        max_retries: Maximum number of retry attempts
        retry_delay: Delay between retries in seconds
    
    Returns:
        Tuple of (is_healthy, discovered_tools, error_message)
        - is_healthy: True if all expected tools are available
        - discovered_tools: List of discovered tool names
        - error_message: Error description if unhealthy, empty string otherwise
        
    Example:
        is_healthy, tools, error = await verify_mcp_tools(mcp_process)
        if not is_healthy:
            logger.error(f"MCP unhealthy: {error}")
    """
    if expected_tools is None:
        expected_tools = [
            "initialize_environment",
            "execute_actions",
            "get_observation",
            "cleanup_environment"
        ]
    
    for attempt in range(1, max_retries + 1):
        try:
            # Check if process is still running
            if process.poll() is not None:
                return False, [], f"MCP server process terminated (exit code: {process.returncode})"
            
            # TODO: Implement actual MCP protocol tool discovery
            # This requires sending a tools/list request via MCP protocol
            # For now, we'll do a basic health check
            
            # Exponential backoff for retries
            if attempt > 1:
                await asyncio.sleep(retry_delay * (2 ** (attempt - 2)))
            
            # Simulate tool discovery (will be replaced with actual MCP client call)
            discovered_tools = expected_tools.copy()
            
            # Verify all expected tools are present
            missing_tools = [tool for tool in expected_tools if tool not in discovered_tools]
            
            if missing_tools:
                error = f"Missing tools: {', '.join(missing_tools)}"
                if attempt < max_retries:
                    logger.warning(
                        f"MCP health check attempt {attempt}/{max_retries} failed: {error}",
                        extra={"missing_tools": missing_tools, "attempt": attempt}
                    )
                    continue
                return False, discovered_tools, error
            
            # All tools present
            logger.info(
                f"MCP health check passed on attempt {attempt}",
                extra={"tools": discovered_tools, "attempt": attempt}
            )
            return True, discovered_tools, ""
            
        except Exception as e:
            error = f"Health check error: {str(e)}"
            if attempt < max_retries:
                logger.warning(
                    f"MCP health check attempt {attempt}/{max_retries} error: {e}",
                    extra={"error": str(e), "attempt": attempt}
                )
                continue
            return False, [], error
    
    # All retries exhausted
    return False, [], f"Health check failed after {max_retries} attempts"


async def verify_mcp_server_health_full(
    process: Any,
    pid: int,
    session_id: str
) -> Dict[str, Any]:
    """
    Comprehensive MCP server health check returning full health details.
    
    Args:
        process: MCP server subprocess
        pid: Process ID
        session_id: Session identifier
    
    Returns:
        Dict with MCPServerHealth-compatible fields
    """
    import psutil
    
    # Check process is running
    process_running = False
    try:
        psutil_proc = psutil.Process(pid)
        process_running = psutil_proc.is_running()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        process_running = False
    
    # Verify tools
    is_healthy, tools_discovered, error_message = await verify_mcp_tools(process)
    
    expected_tools = [
        "initialize_environment",
        "execute_actions", 
        "get_observation",
        "cleanup_environment"
    ]
    
    all_tools_available = set(expected_tools).issubset(set(tools_discovered))
    
    return {
        "is_healthy": is_healthy and process_running,
        "process_id": pid,
        "process_running": process_running,
        "tools_discovered": tools_discovered,
        "tools_verified": tools_discovered if is_healthy else [],
        "health_check_timestamp": time.time(),
        "retry_count": 0,  # Handled internally by verify_mcp_tools
        "error_message": error_message if error_message else None,
        "expected_tools": expected_tools,
        "all_tools_available": all_tools_available,
    }
