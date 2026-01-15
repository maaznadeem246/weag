"""
Helper functions for environment session management.

Extracted from session_manager.py to improve modularity and testability.
"""

import os
from pathlib import Path
from typing import Tuple, Optional, List

import logging

logger = logging.getLogger(__name__)

# Mapping benchmark -> module import path
BENCHMARK_MODULES = {
    "miniwob": "browsergym.miniwob",
    "webarena": "browsergym.webarena",
    "visualwebarena": "browsergym.webarena",
    "workarena": "browsergym.workarena",
    "assistantbench": "browsergym.assistantbench",
    "weblinx": "browsergym.weblinx",
    "openended": "browsergym.core",
}


def ensure_benchmark_registered(benchmark: str) -> None:
    """
    Ensure benchmark environments are registered with Gymnasium.
    
    Args:
        benchmark: Benchmark identifier
        
    Raises:
        ValueError: If benchmark is not supported
    """
    if benchmark not in BENCHMARK_MODULES:
        raise ValueError(f"Unsupported benchmark: {benchmark}")
    
    module_path = BENCHMARK_MODULES[benchmark]
    try:
        __import__(module_path)
        logger.debug(f"Registered {benchmark} environments via {module_path}")
    except ImportError as e:
        logger.error(f"Failed to import {module_path}: {e}")
        raise RuntimeError(f"Failed to register {benchmark} environments: {e}")


def _find_project_root() -> Path:
    """Find the project root directory by looking for pyproject.toml."""
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / "pyproject.toml").exists():
            return current
        current = current.parent
    # Fallback: use cwd
    return Path.cwd()


# Benchmark dataset path configuration (relative to green-agent root)
# Maps benchmark -> (env_var_name, [relative_paths_to_try])
# Benchmarks with None use remote data (HuggingFace, web APIs) - no local path needed
# Multiple paths are tried in order (Docker uses 'benchmarks/', local uses 'datasets/')
BENCHMARK_PATHS = {
    "miniwob": ("MINIWOB_URL", ["benchmarks/miniwob/html/miniwob", "datasets/miniwob/html/miniwob"]),
    "webarena": ("WEBARENA_BASE_URL", None),  # Remote URL, no local path
    "visualwebarena": ("VISUALWEBARENA_BASE_URL", None),  # Remote URL
    "workarena": ("WORKARENA_BASE_URL", None),  # Remote URL
    "assistantbench": ("ASSISTANTBENCH_DATA_PATH", None),  # HuggingFace dataset, no local path
    "weblinx": ("WEBLINX_DATA_PATH", None),  # Remote dataset, no local path
}


def normalize_benchmark_environment_vars(
    benchmark: str,
    benchmarks_root: Optional[Path] = None
) -> None:
    """
    Auto-configure benchmark-specific environment variables from project structure.
    
    Automatically sets the correct dataset paths based on the project's benchmarks
    directory structure. No manual environment variable configuration needed.
    
    Args:
        benchmark: Benchmark identifier (e.g., "miniwob", "webarena")
        benchmarks_root: Optional override for benchmarks root directory
    """
    if benchmark not in BENCHMARK_PATHS:
        logger.debug(f"No path configuration for benchmark: {benchmark}")
        return
    
    env_var_name, relative_paths = BENCHMARK_PATHS[benchmark]
    
    # Skip benchmarks that use remote URLs (no local path)
    if relative_paths is None:
        logger.debug(f"{benchmark} uses remote URL, skipping local path setup")
        return
    
    # Determine project root
    project_root = benchmarks_root or _find_project_root()
    
    # Try each path in order (Docker uses 'benchmarks/', local uses 'datasets/')
    dataset_path = None
    for relative_path in relative_paths:
        candidate = project_root / relative_path
        if candidate.exists():
            dataset_path = candidate
            break
    
    # Verify path was found
    if dataset_path is None:
        tried_paths = [str(project_root / p) for p in relative_paths]
        logger.warning(
            f"Benchmark dataset not found. Tried: {tried_paths}",
            extra={"benchmark": benchmark}
        )
        return
    
    # Convert to file:// URL for BrowserGym compatibility
    dataset_url = dataset_path.as_uri() + "/"
    
    # Set environment variable (overrides any user-provided value)
    os.environ[env_var_name] = dataset_url
    logger.info(f"Auto-configured {env_var_name}={dataset_url}")


def get_browser_headless_mode() -> bool:
    """
    Determine browser headless mode from environment variable.
    
    Returns:
        True if browser should run in headless mode, False otherwise
    """
    headless_env = os.environ.get("BROWSER_HEADLESS")
    
    if headless_env is None:
        logger.info("BROWSER_HEADLESS not set, defaulting to headless=False (visible)")
        return False
    
    # Accept common truthy/falsey values
    headless = str(headless_env).lower() not in ("0", "false", "no", "off")
    logger.info(f"BROWSER_HEADLESS='{headless_env}' -> headless={headless}")
    
    return headless


def create_env_id(task_id: str) -> str:
    """
    Create Gymnasium environment ID with proper prefix.
    
    Args:
        task_id: Task identifier (e.g., "miniwob.click-test")
        
    Returns:
        Environment ID with browsergym prefix
    """
    if task_id.startswith("browsergym/"):
        return task_id
    return f"browsergym/{task_id}"


def validate_task_id_format(task_id: str) -> Tuple[bool, Optional[str]]:
    """
    Validate task_id format.
    
    Args:
        task_id: Task identifier to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not task_id:
        return False, "task_id cannot be empty"
    
    if not isinstance(task_id, str):
        return False, f"task_id must be string, got {type(task_id)}"
    
    # Check for valid benchmark.task format
    if "." not in task_id and not task_id.startswith("browsergym/"):
        return False, "task_id must be in 'benchmark.task' format (e.g., 'miniwob.click-test')"
    
    return True, None


def extract_benchmark_from_task(task_id: str) -> str:
    """
    Extract benchmark identifier from task_id.
    
    Args:
        task_id: Task identifier (e.g., "miniwob.click-test")
        
    Returns:
        Benchmark identifier (e.g., "miniwob")
    """
    # Strip browsergym/ prefix if present
    if task_id.startswith("browsergym/"):
        task_id = task_id[len("browsergym/"):]
    
    # Extract benchmark (part before first dot)
    return task_id.split(".")[0]


def log_session_creation(
    task_id: str,
    benchmark: str,
    start_url: Optional[str],
    max_steps: int,
    seed: Optional[int],
    headless: bool
) -> None:
    """
    Log environment session creation details.
    
    Args:
        task_id: Task identifier
        benchmark: Benchmark name
        start_url: Starting URL if any
        max_steps: Maximum steps
        seed: Random seed if any
        headless: Whether browser is headless
    """
    logger.info(
        "Creating environment session",
        extra={
            "task_id": task_id,
            "benchmark": benchmark,
            "start_url": start_url,
            "max_steps": max_steps,
            "seed": seed,
            "headless": headless,
        }
    )
