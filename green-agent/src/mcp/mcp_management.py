"""
MCP server management helpers for Green Agent.

Extracted from main.py to improve modularity and cleanup logic clarity.
"""

import asyncio
import os
from typing import Optional
import subprocess

from src.utils.logging import get_logger


logger = get_logger(__name__)


async def terminate_process_gracefully(
    process: subprocess.Popen,
    timeout: float = 5.0
) -> bool:
    """
    Terminate process gracefully, with fallback to force kill.
    
    Args:
        process: Subprocess to terminate
        timeout: Seconds to wait before force kill
        
    Returns:
        True if terminated gracefully, False if force killed
    """
    try:
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=timeout)
            logger.info(f"Process {process.pid} terminated gracefully")
            return True
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            logger.warning(f"Process {process.pid} forcefully killed")
            return False
    except Exception as e:
        logger.error(f"Error terminating process {process.pid}: {e}", exc_info=True)
        return False


def kill_orphaned_mcp_servers() -> int:
    """
    Kill any orphaned Python MCP server processes.
    
    Returns:
        Number of processes killed
    """
    try:
        import psutil
        current_pid = os.getpid()
        killed_count = 0
        
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                # Skip current process
                if proc.info['pid'] == current_pid:
                    continue
                
                # Kill Python processes running mcp_server
                if proc.info['name'] and 'python' in proc.info['name'].lower():
                    cmdline = proc.info.get('cmdline', [])
                    if cmdline and any('mcp_server' in arg for arg in cmdline):
                        logger.info(f"Killing orphaned MCP server process: {proc.info['pid']}")
                        proc.kill()
                        proc.wait(timeout=3)
                        killed_count += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired):
                pass
        
        return killed_count
        
    except ImportError:
        logger.warning("psutil not available for orphaned process cleanup")
        return 0
    except Exception as e:
        logger.error(f"Error cleaning up orphaned processes: {e}", exc_info=True)
        return 0


def cleanup_browser_session(session_manager) -> dict:
    """
    Cleanup browser session using session manager.
    
    Args:
        session_manager: SessionManager instance from mcp_server
        
    Returns:
        Cleanup result dict with status and metrics
    """
    try:
        cleanup_result = session_manager.cleanup_session()
        browser_session_id = getattr(session_manager, 'current_session_id', None) or "unknown"
        
        logger.info(
            f"✓ Browser environment cleaned up for session {browser_session_id}",
            extra={
                "browser_session_id": browser_session_id,
                "cleanup_status": cleanup_result.get("cleanup_status"),
                "killed_pids": cleanup_result.get("killed_browser_pids", []),
                "orphaned_processes": cleanup_result.get("orphaned_processes", 0)
            }
        )
        
        return cleanup_result
        
    except Exception as e:
        logger.error(f"Error cleaning up browser session: {e}", exc_info=True)
        
        # Fallback: Try to cleanup all sessions as last resort
        try:
            session_manager.cleanup_all_sessions()
            logger.info("Fallback: cleaned up all sessions")
            return {"cleanup_status": "fallback_success"}
        except Exception as fallback_error:
            logger.error(f"Fallback cleanup also failed: {fallback_error}")
            return {"cleanup_status": "failed", "error": str(fallback_error)}


def cleanup_shared_state(shared_state_manager) -> None:
    """
    Cleanup shared state file.
    
    Args:
        shared_state_manager: SharedStateManager instance
    """
    if not shared_state_manager:
        return
    
    try:
        shared_state_manager.cleanup()
        logger.info("Shared state cleaned up")
    except Exception as e:
        logger.error(f"Error cleaning up shared state: {e}", exc_info=True)


async def comprehensive_cleanup(
    mcp_process: Optional[subprocess.Popen],
    session_manager,
    shared_state_manager,
    active_session_id: Optional[str] = None
) -> dict:
    """
    Perform comprehensive cleanup of MCP server, browsers, and shared state.
    
    Args:
        mcp_process: MCP server subprocess if managed by green agent
        session_manager: SessionManager instance from mcp_server
        shared_state_manager: SharedStateManager instance
        active_session_id: Active session ID for logging
        
    Returns:
        Cleanup result dict with counts and status
    """
    logger.info("Starting comprehensive cleanup...")
    
    results = {
        "mcp_terminated": False,
        "orphaned_killed": 0,
        "browser_cleanup": {},
        "shared_state_cleaned": False
    }
    
    # Cleanup MCP subprocess
    if mcp_process:
        logger.info("Cleaning up MCP server subprocess", extra={"pid": mcp_process.pid})
        results["mcp_terminated"] = await terminate_process_gracefully(mcp_process)
    
    # Kill orphaned MCP servers
    results["orphaned_killed"] = kill_orphaned_mcp_servers()
    
    # Cleanup browser session (tracks spawned PIDs)
    results["browser_cleanup"] = cleanup_browser_session(session_manager)
    
    # Cleanup shared state
    cleanup_shared_state(shared_state_manager)
    results["shared_state_cleaned"] = True
    
    logger.info(
        "Comprehensive cleanup completed",
        extra={
            "session_id": active_session_id or "unknown",
            "results": results
        }
    )
    
    return results
