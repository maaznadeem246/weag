"""
Dynamic MCP Tool Registry for BrowserGym Green Agent.

Implements Approach III (Dynamic MCP Server) per AgentBeats official guidance.
Manages base tools and benchmark-specific tool registration/deregistration.

Per research.md Decision 3.
"""

import asyncio
import base64
from typing import Any, Callable, Optional
from datetime import datetime
from mcp.server.fastmcp import FastMCP

from src.environment.thread_executor import browser_executor
from src.benchmarks.profiles import (
    BenchmarkProfile,
    BenchmarkProfileRegistry,
    ToolDefinition,
    get_profile_for_task,
)
from src.benchmarks.tool_handlers import get_tool_handler_mapping
from src.utils.logging import get_logger

logger = get_logger(__name__)


class ToolRegistry:
    """Registry for dynamic MCP tool management.
    
    Manages:
    - Base tools (always available): initialize_environment, execute_actions, 
      get_observation, cleanup_environment
    - Benchmark-specific tools: Registered on initialize_environment, 
      removed on cleanup_environment
    
    Per research.md Decision 3 - Approach III pattern.
    """
    
    _instance: Optional["ToolRegistry"] = None
    
    def __new__(cls) -> "ToolRegistry":
        """Singleton pattern for tool registry."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._mcp: Optional[FastMCP] = None
            cls._instance._active_benchmark: Optional[str] = None
            cls._instance._registered_tools: set[str] = set()
            cls._instance._base_tools: set[str] = {
                "execute_actions", 
                "get_observation",
            }
            cls._instance._tool_handlers: dict[str, Callable] = {}
        return cls._instance
    
    def set_mcp(self, mcp: FastMCP) -> None:
        """Set the MCP server instance for dynamic tool registration."""
        self._mcp = mcp
    
    @property
    def active_benchmark(self) -> Optional[str]:
        """Get the currently active benchmark ID."""
        return self._active_benchmark
    
    @property
    def registered_tools(self) -> set[str]:
        """Get set of currently registered benchmark-specific tools."""
        return self._registered_tools.copy()
    
    def register_benchmark_tools(self, benchmark_id: str) -> list[str]:
        """Register benchmark-specific tools for the given benchmark.
        
        Called by initialize_environment after environment creation.
        
        Args:
            benchmark_id: The benchmark identifier (e.g., 'webarena')
            
        Returns:
            List of tool names that were registered
            
        Raises:
            ValueError: If benchmark is not supported
        """
        if not self._mcp:
            raise RuntimeError("MCP server not set. Call set_mcp() first.")
        
        # Clean up any previously registered tools
        if self._active_benchmark:
            self.deregister_benchmark_tools()
        
        registry = BenchmarkProfileRegistry.instance()
        profile = registry.get_or_raise(benchmark_id)
        
        registered = []
        for tool_def in profile.extra_tools:
            try:
                handler = self._get_tool_handler(tool_def.name)
                if handler:
                    # Register tool with MCP server
                    self._mcp.add_tool(
                        handler,
                        name=tool_def.name,
                        description=tool_def.description,
                    )
                    self._registered_tools.add(tool_def.name)
                    registered.append(tool_def.name)
                    logger.info(
                        f"Registered benchmark tool: {tool_def.name}",
                        extra={
                            "benchmark": benchmark_id,
                            "tool_name": tool_def.name,
                        }
                    )
            except Exception as e:
                logger.error(
                    f"Failed to register tool {tool_def.name}: {e}",
                    extra={"benchmark": benchmark_id, "tool_name": tool_def.name},
                    exc_info=True
                )
        
        self._active_benchmark = benchmark_id
        logger.info(
            f"Registered {len(registered)} benchmark-specific tools for {benchmark_id}",
            extra={
                "benchmark": benchmark_id,
                "tools": registered,
            }
        )
        
        return registered
    
    def deregister_benchmark_tools(self) -> list[str]:
        """Remove all benchmark-specific tools.
        
        Called by cleanup_environment to reset tool state.
        
        Returns:
            List of tool names that were deregistered
        """
        if not self._mcp:
            return []
        
        deregistered = []
        for tool_name in list(self._registered_tools):
            try:
                # FastMCP doesn't have a remove_tool method, but we track state
                # Tools will be overwritten on next registration
                self._registered_tools.discard(tool_name)
                deregistered.append(tool_name)
                logger.info(
                    f"Deregistered benchmark tool: {tool_name}",
                    extra={"tool_name": tool_name}
                )
            except Exception as e:
                logger.error(
                    f"Failed to deregister tool {tool_name}: {e}",
                    extra={"tool_name": tool_name},
                    exc_info=True
                )
        
        previous_benchmark = self._active_benchmark
        self._active_benchmark = None
        
        logger.info(
            f"Deregistered {len(deregistered)} benchmark-specific tools",
            extra={
                "previous_benchmark": previous_benchmark,
                "tools": deregistered,
            }
        )
        
        return deregistered
    
    def get_all_tools(self) -> list[str]:
        """Get all currently available tools (base + benchmark-specific).
        
        Returns:
            List of tool names
        """
        return list(self._base_tools | self._registered_tools)
    
    def get_registered_tools(self, benchmark_id: Optional[str] = None) -> list[str]:
        """Get registered benchmark-specific tools.
        
        Args:
            benchmark_id: Optional benchmark ID (for validation)
            
        Returns:
            List of registered benchmark-specific tool names
        """
        if benchmark_id and self._active_benchmark != benchmark_id:
            logger.warning(
                f"Requested tools for {benchmark_id} but active benchmark is {self._active_benchmark}"
            )
        return list(self._registered_tools)
    
    def _get_tool_handler(self, tool_name: str) -> Optional[Callable]:
        """Get the handler function for a benchmark-specific tool.
        
        Args:
            tool_name: Name of the tool
            
        Returns:
            Handler function or None if not found
        """
        if tool_name in self._tool_handlers:
            return self._tool_handlers[tool_name]
        
        # Get handler mapping from tool_handlers module
        handlers = get_tool_handler_mapping()
        return handlers.get(tool_name)
    
    @classmethod
    def instance(cls) -> "ToolRegistry":
        """Get singleton instance."""
        return cls()


# =============================================================================
# Module-Level Functions
# =============================================================================

def get_tool_registry() -> ToolRegistry:
    """Get the singleton tool registry instance."""
    return ToolRegistry.instance()


def register_tools_for_benchmark(benchmark_id: str, mcp: FastMCP) -> list[str]:
    """Convenience function to register benchmark tools.
    
    Args:
        benchmark_id: The benchmark identifier
        mcp: FastMCP server instance
        
    Returns:
        List of registered tool names
    """
    registry = get_tool_registry()
    registry.set_mcp(mcp)
    return registry.register_benchmark_tools(benchmark_id)


def cleanup_benchmark_tools() -> list[str]:
    """Convenience function to deregister benchmark tools.
    
    Returns:
        List of deregistered tool names
    """
    registry = get_tool_registry()
    return registry.deregister_benchmark_tools()
