"""
MCP Tool Details Extractor.

Provides functions to extract tool metadata from MCP server tools
and format them for Purple Agent consumption.
"""

from typing import Any, Optional

from src.mcp.tool_introspection import (
    ToolMetadata,
    ToolParameter,
    extract_tool_metadata,
    format_tools_for_agent,
)
from src.benchmarks.profiles import (
    BenchmarkProfileRegistry,
    ToolDefinition,
)
from src.utils.logging import get_logger

logger = get_logger(__name__)


def get_mcp_base_tools_metadata() -> list[ToolMetadata]:
    """
    Extract metadata from MCP server base tools.
    
    Imports the MCP server module and extracts tool metadata from
    the decorated tool functions using Python introspection.
    
    Returns:
        List of ToolMetadata for base MCP tools (execute_actions, get_observation, cleanup_environment)
    """
    tools = []
    
    try:
        # Import MCP server module to access tool functions
        from src.mcp import server as mcp_server
        
        # Use the BASE_MCP_TOOLS list defined in mcp_server
        # This avoids hardcoded string names and keeps everything in one place
        if not hasattr(mcp_server, 'BASE_MCP_TOOLS'):
            raise AttributeError(
                "BASE_MCP_TOOLS not found in mcp_server module. "
                "Check that src/green_agent/mcp/server.py defines BASE_MCP_TOOLS."
            )
        
        tool_functions = mcp_server.BASE_MCP_TOOLS
        
        for func in tool_functions:
            try:
                metadata = extract_tool_metadata(func)
                tools.append(metadata)
                logger.debug(f"Extracted metadata for MCP tool: {metadata.name}")
            except Exception as e:
                logger.warning(f"Failed to extract metadata for {func.__name__}: {e}")
        
        logger.info(f"Extracted metadata for {len(tools)} MCP base tools")
        
    except Exception as e:
        logger.error(f"Failed to import MCP server module: {e}")
    
    return tools


def get_benchmark_tools_metadata(benchmark_id: str) -> list[ToolMetadata]:
    """
    Get metadata for benchmark-specific tools.
    
    Converts ToolDefinition objects from benchmark profiles to ToolMetadata
    for consistent formatting.
    
    Args:
        benchmark_id: Benchmark identifier (e.g., 'miniwob', 'webarena')
        
    Returns:
        List of ToolMetadata for benchmark-specific tools
    """
    tools = []
    
    try:
        registry = BenchmarkProfileRegistry.instance()
        profile = registry.get(benchmark_id)
        
        if profile and profile.extra_tools:
            for tool_def in profile.extra_tools:
                metadata = _tool_definition_to_metadata(tool_def)
                tools.append(metadata)
                logger.debug(f"Converted benchmark tool: {tool_def.name}")
            
            logger.info(f"Extracted {len(tools)} benchmark-specific tools for {benchmark_id}")
    
    except Exception as e:
        logger.warning(f"Failed to get benchmark tools for {benchmark_id}: {e}")
    
    return tools


def _tool_definition_to_metadata(tool_def: ToolDefinition) -> ToolMetadata:
    """
    Convert a ToolDefinition to ToolMetadata.
    
    Args:
        tool_def: ToolDefinition from benchmark profile
        
    Returns:
        ToolMetadata with equivalent information
    """
    # Parse input_schema for parameters
    parameters = []
    schema = tool_def.input_schema or {}
    props = schema.get("properties", {})
    required_fields = schema.get("required", [])
    
    for name, prop in props.items():
        param = ToolParameter(
            name=name,
            type_hint=prop.get("type", "any"),
            required=name in required_fields,
            default=prop.get("default"),
            description=prop.get("description", ""),
        )
        parameters.append(param)
    
    return ToolMetadata(
        name=tool_def.name,
        description=tool_def.description,
        parameters=parameters,
        returns="dict with operation results",
        examples=[],
        is_async=True,  # Assume async for MCP tools
    )


def get_all_tools_metadata(benchmark_id: str) -> list[ToolMetadata]:
    """
    Get complete list of available tool metadata.
    
    Combines base MCP tools with benchmark-specific tools.
    
    Args:
        benchmark_id: Benchmark identifier
        
    Returns:
        List of all ToolMetadata objects
    """
    tools = get_mcp_base_tools_metadata()
    benchmark_tools = get_benchmark_tools_metadata(benchmark_id)
    tools.extend(benchmark_tools)
    
    return tools


def format_tools_documentation(
    tools: list[ToolMetadata],
    benchmark_id: Optional[str] = None,
) -> str:
    """
    Format tool metadata as documentation for assessment.
    
    Args:
        tools: List of ToolMetadata objects
        benchmark_id: Optional benchmark ID for section headers
        
    Returns:
        Formatted markdown documentation with tool names, descriptions, and arguments
    """
    sections = ["## AVAILABLE MCP TOOLS\n"]
    
    # Separate base and benchmark-specific tools
    base_tools = []
    benchmark_tools = []
    
    # Only execute_actions and get_observation are exposed to Purple Agent
    # cleanup_environment is removed - Green Agent handles cleanup
    base_names = {"execute_actions", "get_observation"}
    for tool in tools:
        if tool.name in base_names:
            base_tools.append(tool)
        else:
            benchmark_tools.append(tool)
    
    # Format base tools
    if base_tools:
        for tool in base_tools:
            sections.append(tool.format_for_agent())
            sections.append("")
    
    # Format benchmark-specific tools
    if benchmark_tools:
        header = f"### Benchmark-Specific Tools"
        if benchmark_id:
            header += f" ({benchmark_id})"
        sections.append(f"\n{header}\n")
        for tool in benchmark_tools:
            sections.append(tool.format_for_agent())
            sections.append("")
    
    return "\n".join(sections)


__all__ = [
    "get_mcp_base_tools_metadata",
    "get_benchmark_tools_metadata",
    "get_all_tools_metadata",
    "format_tools_documentation",
]
