"""
MCP module for Green Agent.

Contains:
- server: MCP server implementation with FastMCP
- tool_introspection: Extract tool metadata from decorated functions
- tool_details: High-level API to get MCP tool documentation
- mcp_management: Cleanup and lifecycle management
"""

from src.mcp.tool_introspection import (
    ToolParameter,
    ToolMetadata,
    extract_tool_metadata,
    extract_tools_from_module,
    format_tools_for_agent,
)

from src.mcp.tool_details import (
    get_mcp_base_tools_metadata,
    get_benchmark_tools_metadata,
    get_all_tools_metadata,
    format_tools_documentation,
)

from src.mcp.mcp_management import (
    comprehensive_cleanup,
)

# Server exports (lazy import to avoid circular dependencies)
# Use: from src.mcp.server import mcp, session_manager, etc.

__all__ = [
    # Introspection
    "ToolParameter",
    "ToolMetadata",
    "extract_tool_metadata",
    "extract_tools_from_module",
    "format_tools_for_agent",
    # Tool Details
    "get_mcp_base_tools_metadata",
    "get_benchmark_tools_metadata",
    "get_all_tools_metadata",
    "format_tools_documentation",
    # Management
    "comprehensive_cleanup",
]
