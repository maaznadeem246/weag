"""
Benchmark Management Utilities for BrowserGym Green Agent.

Provides high-level utilities for working with benchmarks and tasks,
integrating profile management and task discovery.

This module serves as the main interface for benchmark-related operations
in the Green Agent.
"""

import os
from pathlib import Path
from typing import Dict, List, Optional, Any
import logging

# Default benchmarks when none are specified in config or env
DEFAULT_BENCHMARKS: List[str] = ["miniwob", "assistantbench"]

from src.benchmarks.constants import DEFAULT_MAX_TASKS_PER_BENCHMARK
from src.benchmarks.profiles import (
    BenchmarkProfile,
    BenchmarkProfileRegistry,
    get_profile_for_task,
    detect_benchmark,
)
from src.benchmarks.task_discovery import (
    TaskInfo,
    TaskDiscovery,
    get_task_discovery,
    discover_tasks_for_benchmark,
    discover_all_tasks,
)

logger = logging.getLogger(__name__)


class BenchmarkManager:
    """
    High-level manager for benchmark profiles and task discovery.
    
    Combines benchmark profiles with task discovery to provide
    a unified interface for benchmark management.
    """
    
    def __init__(self, benchmarks_root: Optional[Path] = None):
        """
        Initialize benchmark manager.
        
        Args:
            benchmarks_root: Root directory containing benchmark data
        """
        self.profile_registry = BenchmarkProfileRegistry.instance()
        self.task_discovery = get_task_discovery(benchmarks_root)
    
    def get_benchmark_profile(self, benchmark_or_task: str) -> BenchmarkProfile:
        """
        Get benchmark profile by benchmark ID or task ID.
        
        Args:
            benchmark_or_task: Benchmark ID (e.g., "miniwob") or task ID (e.g., "miniwob.click-test")
            
        Returns:
            BenchmarkProfile for the specified benchmark
            
        Raises:
            ValueError: If benchmark is not supported
        """
        if "." in benchmark_or_task:
            # Task ID - extract benchmark
            return get_profile_for_task(benchmark_or_task)
        else:
            # Benchmark ID
            return self.profile_registry.get_or_raise(benchmark_or_task)
    
    def get_tasks_for_benchmark(self, benchmark: str, max_tasks: Optional[int] = None) -> List[str]:
        """
        Get task IDs for a specific benchmark.
        
        Args:
            benchmark: Benchmark identifier
            max_tasks: Maximum number of tasks to return
            
        Returns:
            List of task ID strings
        """
        return self.task_discovery.get_task_ids_for_benchmark(benchmark, max_tasks)
    
    def get_all_benchmark_tasks(self, max_tasks_per_benchmark: int = DEFAULT_MAX_TASKS_PER_BENCHMARK) -> Dict[str, List[str]]:
        """
        Get tasks for all supported benchmarks.
        
        Args:
            max_tasks_per_benchmark: Maximum tasks per benchmark
            
        Returns:
            Dictionary mapping benchmark names to task ID lists
        """
        return discover_all_tasks(max_tasks_per_benchmark)
    
    def validate_task(self, task_id: str) -> bool:
        """
        Validate if a task ID is supported and exists.
        
        Args:
            task_id: Task identifier to validate
            
        Returns:
            True if task is valid and exists, False otherwise
        """
        try:
            # Check if benchmark profile exists
            profile = get_profile_for_task(task_id)
            
            # Check if task exists in benchmarks
            return self.task_discovery.validate_task_id(task_id)
        except Exception:
            return False
    
    def get_supported_benchmarks(self) -> List[str]:
        """
        Get list of all supported benchmark identifiers.
        
        Returns:
            List of benchmark IDs
        """
        return self.profile_registry.supported_benchmarks()
    
    def create_task_plan(self, 
                        benchmarks: Optional[List[str]] = None, 
                        max_tasks_per_benchmark: int = DEFAULT_MAX_TASKS_PER_BENCHMARK,
                        specific_tasks: Optional[Dict[str, List[str]]] = None) -> Dict[str, Any]:
        """
        Create a task plan for multi-task evaluation.
        
        Args:
            benchmarks: List of benchmark IDs to include (None for all)
            max_tasks_per_benchmark: Maximum tasks per benchmark
            specific_tasks: Specific tasks per benchmark (overrides discovery)
            
        Returns:
            Task plan dictionary with benchmarks and tasks_by_benchmark
        """
        if specific_tasks:
            # Use provided specific tasks
            tasks_by_benchmark = specific_tasks.copy()
            benchmarks_list = list(specific_tasks.keys())
        else:
            # Discover tasks automatically; use built-in defaults when unspecified
            if benchmarks is None:
                benchmarks = DEFAULT_BENCHMARKS
            
            if benchmarks is None:
                # Get all supported benchmarks with tasks
                all_tasks = self.get_all_benchmark_tasks(max_tasks_per_benchmark)
                tasks_by_benchmark = {k: v for k, v in all_tasks.items() if v}  # Only include benchmarks with tasks
                benchmarks_list = list(tasks_by_benchmark.keys())
            else:
                # Use specified benchmarks
                benchmarks_list = benchmarks
                tasks_by_benchmark = {}
                for benchmark in benchmarks:
                    try:
                        tasks = self.get_tasks_for_benchmark(benchmark, max_tasks_per_benchmark)
                        if tasks:  # Only include if tasks found
                            tasks_by_benchmark[benchmark] = tasks
                    except Exception as e:
                        logger.warning(f"Failed to get tasks for {benchmark}: {e}")
                        tasks_by_benchmark[benchmark] = []
        
        return {
            "benchmarks": benchmarks_list,
            "tasks_by_benchmark": tasks_by_benchmark,
            "max_tasks_per_benchmark": max_tasks_per_benchmark,
        }
    
    def get_benchmark_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about available benchmarks and tasks.
        
        Returns:
            Dictionary with benchmark statistics
        """
        all_tasks = self.get_all_benchmark_tasks(max_tasks_per_benchmark=999)  # Get all tasks
        
        stats = {
            "total_benchmarks": len(self.get_supported_benchmarks()),
            "benchmarks_with_tasks": len([b for b, tasks in all_tasks.items() if tasks]),
            "total_tasks": sum(len(tasks) for tasks in all_tasks.values()),
            "tasks_per_benchmark": {
                benchmark: len(tasks) for benchmark, tasks in all_tasks.items()
            },
            "benchmark_profiles": {
                benchmark: {
                    "display_name": profile.display_name,
                    "token_limit": profile.token_limit,
                    "observation_mode": profile.observation_mode.value,
                }
                for benchmark, profile in {
                    bid: self.profile_registry.get(bid) for bid in self.get_supported_benchmarks()
                }.items()
                if profile
            }
        }
        
        return stats
    
    def clear_caches(self) -> None:
        """Clear all caches in task discovery."""
        self.task_discovery.clear_cache()


# =============================================================================
# Global instance and convenience functions
# =============================================================================

_benchmark_manager_instance: Optional[BenchmarkManager] = None


def get_benchmark_manager(benchmarks_root: Optional[Path] = None) -> BenchmarkManager:
    """
    Get global benchmark manager instance (singleton pattern).
    
    Args:
        benchmarks_root: Root directory containing benchmarks (only used for first call)
        
    Returns:
        BenchmarkManager singleton instance
    """
    global _benchmark_manager_instance
    
    if _benchmark_manager_instance is None:
        _benchmark_manager_instance = BenchmarkManager(benchmarks_root)
    
    return _benchmark_manager_instance


def create_assessment_task_plan(benchmarks: Optional[List[str]] = None, 
                               max_tasks_per_benchmark: int = DEFAULT_MAX_TASKS_PER_BENCHMARK) -> Dict[str, Any]:
    """
    Convenience function to create a task plan for assessment.
    
    Args:
        benchmarks: List of benchmark IDs (None for all available)
        max_tasks_per_benchmark: Maximum tasks per benchmark
        
    Returns:
        Task plan dictionary suitable for Green Agent configuration
    """
    manager = get_benchmark_manager()
    return manager.create_task_plan(benchmarks, max_tasks_per_benchmark)


def validate_assessment_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate and enhance an assessment configuration.
    
    Args:
        config: Assessment configuration dictionary
        
    Returns:
        Enhanced configuration with validation results
    """
    manager = get_benchmark_manager()
    
    validation_results = {
        "valid": True,
        "errors": [],
        "warnings": [],
        "enhanced_config": config.copy()
    }
    
    # Single task validation
    if "task_id" in config:
        task_id = config["task_id"]
        if not manager.validate_task(task_id):
            validation_results["valid"] = False
            validation_results["errors"].append(f"Invalid task ID: {task_id}")
        else:
            # Add benchmark info
            try:
                benchmark = detect_benchmark(task_id)
                validation_results["enhanced_config"]["benchmark"] = benchmark
                
                profile = manager.get_benchmark_profile(task_id)
                validation_results["enhanced_config"]["token_limit"] = profile.token_limit
            except Exception as e:
                validation_results["warnings"].append(f"Could not enhance task config: {e}")
    
    # Multi-task validation
    elif "tasks_by_benchmark" in config:
        tasks_by_benchmark = config["tasks_by_benchmark"]
        
        for benchmark, tasks in tasks_by_benchmark.items():
            # Validate benchmark exists
            try:
                manager.get_benchmark_profile(benchmark)
            except ValueError:
                validation_results["valid"] = False
                validation_results["errors"].append(f"Unsupported benchmark: {benchmark}")
                continue
            
            # Validate tasks exist
            invalid_tasks = []
            for task_id in tasks:
                if not manager.validate_task(task_id):
                    invalid_tasks.append(task_id)
            
            if invalid_tasks:
                validation_results["warnings"].extend([
                    f"Invalid tasks in {benchmark}: {', '.join(invalid_tasks)}"
                ])
    
    return validation_results