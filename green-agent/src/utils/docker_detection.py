"""Docker environment detection utilities."""

import os
from src.utils.logging import get_logger

logger = get_logger(__name__)


def is_running_in_docker() -> bool:
    """Detect if running inside a Docker container.
    
    Uses multiple detection methods for reliability:
    1. Check for .dockerenv file (most reliable)
    2. Check hostname patterns (container names)
    3. Check cgroup for docker
    
    Returns:
        True if running in Docker, False otherwise
    """
    # Method 1: Check for .dockerenv file
    if os.path.exists("/.dockerenv"):
        logger.debug("Docker detected via /.dockerenv file")
        return True
    
    # Method 2: Check if hostname matches common Docker patterns
    hostname = os.environ.get("HOSTNAME", "")
    if hostname and (
        hostname.startswith("green-agent") or 
        hostname.startswith("purple") or
        len(hostname) == 12  # Docker generates 12-char hostnames
    ):
        logger.debug(f"Docker detected via hostname pattern: {hostname}")
        return True
    
    # Method 3: Check cgroup for docker
    try:
        with open("/proc/self/cgroup", "r") as f:
            if "docker" in f.read():
                logger.debug("Docker detected via cgroup")
                return True
    except Exception:
        pass
    
    return False
