"""
Benchmarks Module for BrowserGym Green Agent.

This module provides benchmark-specific configurations and dynamic MCP tool
registration per Approach III (Dynamic MCP Server) from AgentBeats.

Components:
- profiles: BenchmarkProfile registry with 6 supported benchmarks
- tool_registry: Dynamic MCP tool registration via FastMCP

Supported Benchmarks:
- miniwob: Simple widget tasks (2000 token limit)
- webarena: Complex web navigation (5000 token limit)
- visualwebarena: Visual-dependent tasks (3500 token limit)
- workarena: ServiceNow workflows (4500 token limit)
- assistantbench: Information retrieval (3000 token limit)
- weblinx: Dialogue-based navigation (4000 token limit)
"""

from src.benchmarks.profiles import (
    BenchmarkProfile,
    BenchmarkProfileRegistry,
    ObservationMode,
    FilteringStrategy,
    ToolDefinition,
    get_profile_for_task,
    detect_benchmark,
)

from src.benchmarks.tool_registry import (
    ToolRegistry,
    get_tool_registry,
    register_tools_for_benchmark,
    cleanup_benchmark_tools,
)

from src.benchmarks.task_discovery import (
    TaskInfo,
    TaskDiscovery,
    get_task_discovery,
    discover_tasks_for_benchmark,
    discover_all_tasks,
    SUPPORTED_BENCHMARKS,
    DEFAULT_EVALUATION_BENCHMARKS,
)

from src.benchmarks.manager import (
    BenchmarkManager,
    get_benchmark_manager,
    create_assessment_task_plan,
    validate_assessment_config,
)

__all__ = [
    # Profiles
    "BenchmarkProfile",
    "BenchmarkProfileRegistry",
    "ObservationMode",
    "FilteringStrategy",
    "ToolDefinition",
    "get_profile_for_task",
    "detect_benchmark",
    # Tool Registry
    "ToolRegistry",
    "get_tool_registry",
    "register_tools_for_benchmark",
    "cleanup_benchmark_tools",
    # Task Discovery
    "TaskInfo",
    "TaskDiscovery",
    "get_task_discovery",
    "discover_tasks_for_benchmark",
    "discover_all_tasks",
    # Manager
    "BenchmarkManager",
    "get_benchmark_manager",
    "create_assessment_task_plan",
    "validate_assessment_config",
]
