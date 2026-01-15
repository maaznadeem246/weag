"""
Process monitoring utility for Mandate F compliance.

Optional verification of Chromium process cleanup using psutil.
"""

import psutil
from typing import List, Dict, Any
from src.utils.logging import get_logger


logger = get_logger(__name__)


def find_chromium_processes() -> List[Dict[str, Any]]:
    """
    Find all running Chromium/Chrome processes.
    
    Returns:
        List of process info dicts with pid, name, cmdline
    """
    chromium_processes = []
    
    # Process names to search for
    chromium_names = ["chromium", "chrome", "chromium-browser", "google-chrome"]
    
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            proc_name = proc.info["name"].lower() if proc.info["name"] else ""
            
            # Check if process name contains chromium/chrome
            if any(name in proc_name for name in chromium_names):
                chromium_processes.append({
                    "pid": proc.info["pid"],
                    "name": proc.info["name"],
                    "cmdline": " ".join(proc.info["cmdline"]) if proc.info["cmdline"] else "",
                })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            # Process may have terminated or we lack permissions
            continue
    
    return chromium_processes


def verify_no_chromium_processes() -> tuple[bool, int, List[Dict[str, Any]]]:
    """
    Verify that no Chromium processes are running (Mandate F).
    
    Returns:
        Tuple of (is_clean, process_count, process_list)
        - is_clean: True if zero Chromium processes found
        - process_count: Number of Chromium processes
        - process_list: List of process info dicts
    """
    processes = find_chromium_processes()
    process_count = len(processes)
    is_clean = process_count == 0
    
    if not is_clean:
        logger.warning(
            "Chromium processes still running after cleanup",
            extra={
                "chromium_process_count": process_count,
                "processes": [p["pid"] for p in processes],
            }
        )
    
    return is_clean, process_count, processes


def get_current_chromium_pids() -> List[int]:
    """
    Get PIDs of all currently running Chromium/Chrome processes.
    
    Returns:
        List of PIDs
    """
    processes = find_chromium_processes()
    return [p["pid"] for p in processes]


def kill_process_tree(pid: int) -> int:
    """
    Kill a specific process and all its children.
    
    This is the safe way to clean up a browser - only kill the specific
    process tree we spawned, not the user's other browser windows.
    
    Args:
        pid: Process ID to kill (along with children)
        
    Returns:
        Number of processes killed
    """
    killed_count = 0
    
    try:
        parent = psutil.Process(pid)
        # Get all children recursively first
        children = parent.children(recursive=True)
        
        # Terminate children first (reverse order - deepest first)
        for child in reversed(children):
            try:
                child.terminate()
                killed_count += 1
                logger.debug(f"Terminated child process {child.pid}")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        
        # Give children time to terminate gracefully
        gone, still_alive = psutil.wait_procs(children, timeout=2)
        
        # Force kill any remaining children
        for child in still_alive:
            try:
                child.kill()
                logger.debug(f"Force killed child process {child.pid}")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        
        # Now terminate/kill the parent
        try:
            parent.terminate()
            parent.wait(timeout=2)
            killed_count += 1
            logger.info(f"Terminated parent process {pid}")
        except psutil.TimeoutExpired:
            parent.kill()
            logger.info(f"Force killed parent process {pid}")
            killed_count += 1
        except psutil.NoSuchProcess:
            pass  # Already gone
            
    except psutil.NoSuchProcess:
        logger.debug(f"Process {pid} already terminated")
    except psutil.AccessDenied:
        logger.warning(f"Cannot kill process {pid} (access denied)")
    except Exception as e:
        logger.error(f"Error killing process tree for {pid}: {e}")
    
    return killed_count


import os


def kill_specific_browser_pids(pids: List[int]) -> int:
    """
    Kill specific browser processes by PID (and their children).
    
    This is safer than kill_chromium_processes() because it only
    terminates the browser instances we spawned, not the user's
    personal browser windows.
    
    Args:
        pids: List of browser PIDs to kill
        
    Returns:
        Total number of processes killed
    """
    total_killed = 0
    
    for pid in pids:
        killed = kill_process_tree(pid)
        total_killed += killed
        
    logger.info(
        f"Killed {total_killed} processes from {len(pids)} browser PIDs",
        extra={"pids": pids, "killed_count": total_killed}
    )
    
    return total_killed


def kill_chromium_processes() -> int:
    """
    Force kill all Chromium processes (emergency cleanup).
    
    WARNING: This kills ALL Chrome/Chromium processes on the system,
    including the user's personal browser windows. Use kill_specific_browser_pids()
    instead when possible.
    
    Returns:
        Number of processes killed
    """
    processes = find_chromium_processes()
    killed_count = 0
    
    for proc_info in processes:
        try:
            proc = psutil.Process(proc_info["pid"])
            proc.terminate()  # Try graceful termination first
            proc.wait(timeout=3)
            killed_count += 1
            logger.info(
                "Terminated Chromium process",
                extra={"pid": proc_info["pid"], "name": proc_info["name"]}
            )
        except (psutil.NoSuchProcess, psutil.TimeoutExpired):
            # Process already gone or didn't terminate - try kill
            try:
                proc.kill()
                killed_count += 1
                logger.warning(
                    "Force killed Chromium process",
                    extra={"pid": proc_info["pid"], "name": proc_info["name"]}
                )
            except psutil.NoSuchProcess:
                pass  # Already gone
        except psutil.AccessDenied:
            logger.error(
                "Cannot kill Chromium process (access denied)",
                extra={"pid": proc_info["pid"]}
            )
    
    return killed_count
