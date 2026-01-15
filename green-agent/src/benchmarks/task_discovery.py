"""
Task Discovery Module for BrowserGym Green Agent.

Handles discovering and managing tasks from the benchmarks directory structure.
This replaces the temporary task discovery logic in the kickstart script.

Supported benchmark structures:
- benchmarks/miniwob/html/miniwob/*.html -> miniwob.<name> tasks
- benchmarks/webarena/ (future)
- benchmarks/visualwebarena/ (future)
- benchmarks/workarena/ (future)
- benchmarks/assistantbench/ (future)
- benchmarks/weblinx/ (future)
"""

import os
from pathlib import Path
from typing import Dict, List, Optional, Set
from dataclasses import dataclass
import logging

import gymnasium as gym

from src.benchmarks.constants import (
    SUPPORTED_BENCHMARKS,
    DEFAULT_EVALUATION_BENCHMARKS,
    DEFAULT_MAX_TASKS_PER_BENCHMARK,
)

logger = logging.getLogger(__name__)


@dataclass
class TaskInfo:
    """Information about a discovered task."""
    
    task_id: str  # e.g., "miniwob.click-test"
    benchmark: str  # e.g., "miniwob"
    name: str  # e.g., "click-test"
    file_path: Optional[Path] = None  # Path to task file if applicable
    metadata: Optional[Dict[str, str]] = None  # Additional task metadata


class TaskDiscovery:
    """
    Manages task discovery from benchmarks directory.
    
    This class handles finding available tasks for each benchmark
    by scanning the appropriate benchmark directories.
    """
    
    def __init__(self, benchmarks_root: Optional[Path] = None):
        """
        Initialize task discovery.
        
        Args:
            benchmarks_root: Root directory containing benchmark data.
                           Defaults to project_root/benchmarks
        """
        self.benchmarks_root = benchmarks_root or self._find_project_root() / "benchmarks"
        logger.info(f"TaskDiscovery initialized with benchmarks_root: {self.benchmarks_root}")
        self._task_cache: Dict[str, List[TaskInfo]] = {}
        self._all_tasks_cache: Optional[List[TaskInfo]] = None
    
    def _find_project_root(self) -> Path:
        """Find the workspace root directory containing the benchmarks folder.
        
        Looks for the 'benchmarks' directory first, then falls back to pyproject.toml.
        This ensures we find the workspace root (weag/) not a subproject (green-agent/).
        """
        current = Path.cwd()
        
        # First, look for a 'benchmarks' directory (primary indicator of workspace root)
        search = current
        while search != search.parent:
            benchmarks_dir = search / "benchmarks"
            if benchmarks_dir.exists() and benchmarks_dir.is_dir():
                # Check if it contains miniwob (to confirm it's the right one)
                if (benchmarks_dir / "miniwob").exists():
                    logger.debug(f"Found workspace root with benchmarks: {search}")
                    return search
            search = search.parent
        
        # Fallback: look for pyproject.toml (original behavior)
        search = current
        while search != search.parent:
            if (search / "pyproject.toml").exists():
                return search
            search = search.parent
        
        # Final fallback: use current working directory
        return Path.cwd()
    
    def discover_miniwob_tasks(self, max_tasks: Optional[int] = None) -> List[TaskInfo]:
        """
        Discover MiniWoB++ tasks from benchmarks/miniwob/html/miniwob/*.html files.
        
        Args:
            max_tasks: Maximum number of tasks to return (None for all)
            
        Returns:
            List of discovered TaskInfo objects
        """
        task_dir = self.benchmarks_root / "miniwob" / "html" / "miniwob"
        
        if not task_dir.exists():
            logger.warning(f"MiniWoB dataset directory not found: {task_dir}")
            return []
        
        tasks: List[TaskInfo] = []
        html_files = sorted([p for p in task_dir.glob("*.html") if p.is_file()])
        
        for html_file in html_files:
            task_name = html_file.stem
            task_id = f"miniwob.{task_name}"
            
            task_info = TaskInfo(
                task_id=task_id,
                benchmark="miniwob",
                name=task_name,
                file_path=html_file,
                metadata={"type": "widget", "format": "html"}
            )
            
            tasks.append(task_info)
            
            # Apply limit if specified
            if max_tasks and len(tasks) >= max_tasks:
                break
        
        logger.info(f"Discovered {len(tasks)} MiniWoB tasks from {task_dir}")
        return tasks
    
    def discover_webarena_tasks(self, max_tasks: Optional[int] = None) -> List[TaskInfo]:
        """
        Discover WebArena tasks from benchmarks/webarena/ directory.
        
        Note: WebArena tasks are typically defined in JSON configuration files.
        This is a placeholder implementation for future WebArena support.
        
        Args:
            max_tasks: Maximum number of tasks to return (None for all)
            
        Returns:
            List of discovered TaskInfo objects
        """
        task_dir = self.benchmarks_root / "webarena"
        
        if not task_dir.exists():
            logger.warning(f"WebArena dataset directory not found: {task_dir}")
            return []
        
        # TODO: Implement WebArena task discovery
        # WebArena tasks are usually defined in JSON files with task definitions
        logger.info("WebArena task discovery not yet implemented")
        return []
    
    def discover_visualwebarena_tasks(self, max_tasks: Optional[int] = None) -> List[TaskInfo]:
        """
        Discover VisualWebArena tasks from benchmarks/visualwebarena/ directory.
        
        Args:
            max_tasks: Maximum number of tasks to return (None for all)
            
        Returns:
            List of discovered TaskInfo objects
        """
        task_dir = self.benchmarks_root / "visualwebarena"
        
        if not task_dir.exists():
            logger.warning(f"VisualWebArena dataset directory not found: {task_dir}")
            return []
        
        # TODO: Implement VisualWebArena task discovery
        logger.info("VisualWebArena task discovery not yet implemented")
        return []
    
    def discover_workarena_tasks(self, max_tasks: Optional[int] = None) -> List[TaskInfo]:
        """
        Discover WorkArena tasks from benchmarks/workarena/ directory.
        
        Args:
            max_tasks: Maximum number of tasks to return (None for all)
            
        Returns:
            List of discovered TaskInfo objects
        """
        task_dir = self.benchmarks_root / "workarena"
        
        if not task_dir.exists():
            logger.warning(f"WorkArena dataset directory not found: {task_dir}")
            return []
        
        # TODO: Implement WorkArena task discovery
        logger.info("WorkArena task discovery not yet implemented")
        return []
    
    def discover_assistantbench_tasks(self, max_tasks: Optional[int] = None) -> List[TaskInfo]:
        """
        Discover AssistantBench tasks from gym registry.
        
        AssistantBench tasks are registered as browsergym/assistantbench.* after importing
        the browsergym.assistantbench module.
        
        Args:
            max_tasks: Maximum number of tasks to return (None for all)
            
        Returns:
            List of discovered TaskInfo objects
        """
        tasks: List[TaskInfo] = []

        # Import browsergym.assistantbench to register tasks
        try:
            import browsergym.assistantbench
        except ImportError:
            logger.warning("browsergym-assistantbench not installed - run: pip install browsergym-assistantbench")
            return []

        # AssistantBench tasks are registered as browsergym/assistantbench.*
        env_ids = [
            env_id for env_id in gym.envs.registry.keys()
            if env_id.startswith("browsergym/assistantbench")
        ]

        if not env_ids:
            logger.warning("AssistantBench tasks not found in gym registry (browsergym/assistantbench.*)")
            return []

        env_ids = sorted(env_ids)
        for env_id in env_ids:
            # env_id format: browsergym/assistantbench.validation.0
            task_suffix = env_id[len("browsergym/"):]
            task_id = task_suffix  # assistantbench.validation.0
            benchmark = task_id.split(".")[0]
            name = ".".join(task_id.split(".")[1:]) if "." in task_id else task_id

            tasks.append(TaskInfo(task_id=task_id, benchmark=benchmark, name=name))

            if max_tasks and len(tasks) >= max_tasks:
                break

        logger.info(f"Discovered {len(tasks)} AssistantBench tasks from gym registry")
        return tasks
    
    def discover_weblinx_tasks(self, max_tasks: Optional[int] = None) -> List[TaskInfo]:
        """
        Discover WebLINX tasks from benchmarks/weblinx/ directory.
        
        Args:
            max_tasks: Maximum number of tasks to return (None for all)
            
        Returns:
            List of discovered TaskInfo objects
        """
        task_dir = self.benchmarks_root / "weblinx"
        
        if not task_dir.exists():
            logger.warning(f"WebLINX dataset directory not found: {task_dir}")
            return []
        
        # TODO: Implement WebLINX task discovery
        logger.info("WebLINX task discovery not yet implemented")
        return []
    
    def discover_benchmark_tasks(self, benchmark: str, max_tasks: Optional[int] = None) -> List[TaskInfo]:
        """
        Discover tasks for a specific benchmark.
        
        Args:
            benchmark: Benchmark identifier (e.g., "miniwob", "webarena")
            max_tasks: Maximum number of tasks to return (None for all)
            
        Returns:
            List of discovered TaskInfo objects for the benchmark
            
        Raises:
            ValueError: If benchmark is not supported
        """
        benchmark = benchmark.lower()
        
        # Use cache if available
        cache_key = f"{benchmark}:{max_tasks}"
        if cache_key in self._task_cache:
            return self._task_cache[cache_key]
        
        # Discover tasks based on benchmark
        discovery_methods = {
            "miniwob": self.discover_miniwob_tasks,
            "webarena": self.discover_webarena_tasks,
            "visualwebarena": self.discover_visualwebarena_tasks,
            "workarena": self.discover_workarena_tasks,
            "assistantbench": self.discover_assistantbench_tasks,
            "weblinx": self.discover_weblinx_tasks,
        }
        
        discovery_method = discovery_methods.get(benchmark)
        if not discovery_method:
            supported = ", ".join(discovery_methods.keys())
            raise ValueError(f"Unsupported benchmark: {benchmark}. Supported: {supported}")
        
        tasks = discovery_method(max_tasks=max_tasks)
        
        # Cache the results
        self._task_cache[cache_key] = tasks
        
        return tasks
    
    def discover_all_tasks(self, max_tasks_per_benchmark: int = DEFAULT_MAX_TASKS_PER_BENCHMARK) -> Dict[str, List[TaskInfo]]:
        """
        Discover tasks for all supported benchmarks.
        
        Args:
            max_tasks_per_benchmark: Maximum tasks to discover per benchmark
            
        Returns:
            Dictionary mapping benchmark names to lists of TaskInfo objects
        """
        all_benchmarks = SUPPORTED_BENCHMARKS
        tasks_by_benchmark: Dict[str, List[TaskInfo]] = {}
        
        for benchmark in all_benchmarks:
            try:
                tasks = self.discover_benchmark_tasks(benchmark, max_tasks=max_tasks_per_benchmark)
                if tasks:  # Only include benchmarks with discovered tasks
                    tasks_by_benchmark[benchmark] = tasks
            except Exception as e:
                logger.warning(f"Failed to discover tasks for {benchmark}: {e}")
                tasks_by_benchmark[benchmark] = []
        
        return tasks_by_benchmark
    
    def get_task_ids_for_benchmark(self, benchmark: str, max_tasks: Optional[int] = None) -> List[str]:
        """
        Get list of task IDs for a benchmark.
        
        Args:
            benchmark: Benchmark identifier
            max_tasks: Maximum number of task IDs to return
            
        Returns:
            List of task ID strings (e.g., ["miniwob.click-test", "miniwob.click-button"])
        """
        tasks = self.discover_benchmark_tasks(benchmark, max_tasks=max_tasks)
        return [task.task_id for task in tasks]
    
    def get_all_task_ids(self, max_tasks_per_benchmark: int = DEFAULT_MAX_TASKS_PER_BENCHMARK) -> List[str]:
        """
        Get all task IDs across all benchmarks.
        
        Args:
            max_tasks_per_benchmark: Maximum tasks per benchmark
            
        Returns:
            Flat list of all task IDs
        """
        all_tasks: List[str] = []
        tasks_by_benchmark = self.discover_all_tasks(max_tasks_per_benchmark)
        
        for tasks in tasks_by_benchmark.values():
            all_tasks.extend(task.task_id for task in tasks)
        
        return all_tasks
    
    def get_supported_benchmarks(self) -> List[str]:
        """
        Get list of supported benchmark identifiers.
        
        Returns:
            List of benchmark IDs
        """
        return SUPPORTED_BENCHMARKS
    
    def validate_task_id(self, task_id: str) -> bool:
        """
        Validate if a task ID exists in the discovered tasks.
        
        Args:
            task_id: Task identifier to validate
            
        Returns:
            True if task exists, False otherwise
        """
        if not task_id or "." not in task_id:
            return False
        
        benchmark = task_id.split(".")[0].lower()
        if benchmark not in self.get_supported_benchmarks():
            return False
        
        # Get all tasks for the benchmark and check if task_id exists
        try:
            tasks = self.discover_benchmark_tasks(benchmark)
            return any(task.task_id == task_id for task in tasks)
        except Exception:
            return False
    
    def clear_cache(self) -> None:
        """Clear the task discovery cache."""
        self._task_cache.clear()
        self._all_tasks_cache = None
        logger.info("Task discovery cache cleared")


# =============================================================================
# Global task discovery instance
# =============================================================================

_task_discovery_instance: Optional[TaskDiscovery] = None


def get_task_discovery(benchmarks_root: Optional[Path] = None) -> TaskDiscovery:
    """
    Get global task discovery instance (singleton pattern).
    
    Args:
        benchmarks_root: Root directory containing benchmarks (only used for first call)
        
    Returns:
        TaskDiscovery singleton instance
    """
    global _task_discovery_instance
    
    if _task_discovery_instance is None:
        _task_discovery_instance = TaskDiscovery(benchmarks_root)
    
    return _task_discovery_instance


def discover_tasks_for_benchmark(benchmark: str, max_tasks: Optional[int] = None) -> List[str]:
    """
    Convenience function to discover task IDs for a benchmark.
    
    Args:
        benchmark: Benchmark identifier
        max_tasks: Maximum number of tasks to return
        
    Returns:
        List of task ID strings
    """
    discovery = get_task_discovery()
    return discovery.get_task_ids_for_benchmark(benchmark, max_tasks)


def discover_all_tasks(max_tasks_per_benchmark: int = DEFAULT_MAX_TASKS_PER_BENCHMARK) -> Dict[str, List[str]]:
    """
    Convenience function to discover all tasks across benchmarks.
    
    Args:
        max_tasks_per_benchmark: Maximum tasks per benchmark
        
    Returns:
        Dictionary mapping benchmark names to task ID lists
    """
    discovery = get_task_discovery()
    tasks_by_benchmark = discovery.discover_all_tasks(max_tasks_per_benchmark)
    
    # Convert TaskInfo objects to task ID strings
    return {
        benchmark: [task.task_id for task in tasks]
        for benchmark, tasks in tasks_by_benchmark.items()
    }