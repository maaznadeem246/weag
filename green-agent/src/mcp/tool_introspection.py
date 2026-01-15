"""
MCP Tool Introspection Module.

Extracts tool metadata from decorated MCP functions using Python introspection.
Similar to how OpenAI Agents SDK extracts tool schemas from @function_tool decorated functions.

Uses:
- inspect module: Extract function signatures and type annotations
- docstring_parser (or griffe): Parse Google/Sphinx/NumPy style docstrings
- pydantic: Build JSON schemas from type hints

This enables dynamic tool documentation generation for Purple Agent messages.
"""

import inspect
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, get_type_hints

from docstring_parser import parse as parse_docstring

from src.mcp.introspection_helpers import (
    get_type_string,
    expand_typeddict_type,
    parse_docstring_metadata,
    python_type_to_json_type,
)
from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ToolParameter:
    """Represents a single tool parameter with metadata."""
    
    name: str
    type_hint: str
    required: bool = True
    default: Optional[Any] = None
    description: str = ""
    
    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        result = {
            "name": self.name,
            "type": self.type_hint,
            "required": self.required,
            "description": self.description,
        }
        if self.default is not None:
            result["default"] = self.default
        return result


@dataclass
class ToolMetadata:
    """Complete metadata for an MCP tool."""
    
    name: str
    description: str
    parameters: list[ToolParameter] = field(default_factory=list)
    returns: str = ""
    examples: list[str] = field(default_factory=list)
    is_async: bool = False
    raw_docstring: str = ""  # Store the full original docstring
    
    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": [p.to_dict() for p in self.parameters],
            "returns": self.returns,
            "examples": self.examples,
            "is_async": self.is_async,
        }
    
    def to_json_schema(self) -> dict:
        """Generate JSON schema for tool parameters."""
        properties = {}
        required = []
        
        for param in self.parameters:
            prop = {
                "type": python_type_to_json_type(param.type_hint),
                "description": param.description,
            }
            if param.default is not None:
                prop["default"] = param.default
            
            properties[param.name] = prop
            
            if param.required:
                required.append(param.name)
        
        return {
            "type": "object",
            "properties": properties,
            "required": required,
        }
    
    def format_for_agent(self) -> str:
        """
        Format tool as simple documentation: name + full docstring.
        
        This follows the MCP/FastMCP pattern where tool.description contains
        the complete docstring with Args, Returns, Examples sections intact.
        """
        lines = [f"**{self.name}**"]
        
        # Use raw docstring if available, otherwise use parsed description
        if self.raw_docstring:
            lines.append(self.raw_docstring)
        else:
            lines.append(self.description)
        
        return "\n".join(lines)


# Helper functions imported from introspection_helpers module
# (_get_type_string, _expand_typeddict_type, _parse_docstring_metadata, _python_type_to_json_type)


def extract_tool_metadata(func: Callable) -> ToolMetadata:
    """
    Extract complete metadata from a Python function.
    
    Uses inspect module to get:
    - Function name
    - Signature (parameters, types, defaults)
    - Docstring (parsed for description, arg descriptions, returns)
    
    Args:
        func: The function to extract metadata from
        
    Returns:
        ToolMetadata with complete tool information
    """
    # Get function name
    name = func.__name__
    
    # Check if async
    is_async = inspect.iscoroutinefunction(func)
    
    # Get signature
    sig = inspect.signature(func)
    
    # Try to get type hints (may fail for some functions)
    try:
        hints = get_type_hints(func)
    except Exception:
        hints = {}
    
    # Parse docstring using docstring_parser library
    docstring = inspect.getdoc(func) or ""
    parsed_doc = parse_docstring_metadata(docstring)
    
    # Extract parameters
    parameters = []
    for param_name, param in sig.parameters.items():
        # Skip 'self' and context parameters
        if param_name in ("self", "ctx", "context"):
            continue
        
        # Get type hint
        type_hint = hints.get(param_name, param.annotation)
        type_str = get_type_string(type_hint)
        
        # Check if required (has no default)
        has_default = param.default is not inspect.Parameter.empty
        default_value = param.default if has_default else None
        
        # Get description from docstring
        arg_description = parsed_doc["args"].get(param_name, "")
        
        parameters.append(ToolParameter(
            name=param_name,
            type_hint=type_str,
            required=not has_default,
            default=default_value if has_default and default_value is not None else None,
            description=arg_description,
        ))
    
    # Get return type
    return_hint = hints.get("return", sig.return_annotation)
    return_type = get_type_string(return_hint) if return_hint is not inspect.Parameter.empty else "Any"
    returns_desc = parsed_doc["returns"] or f"{return_type}"
    
    return ToolMetadata(
        name=name,
        description=parsed_doc["description"],
        parameters=parameters,
        returns=returns_desc,
        examples=parsed_doc["examples"],
        is_async=is_async,
        raw_docstring=docstring,  # Store full original docstring
    )


def extract_tools_from_module(module: Any, tool_names: Optional[list[str]] = None) -> list[ToolMetadata]:
    """
    Extract metadata for multiple tools from a module.
    
    Args:
        module: The module containing tool functions
        tool_names: Optional list of specific tool names to extract.
                   If None, extracts all callable functions.
        
    Returns:
        List of ToolMetadata objects
    """
    tools = []
    
    for name in dir(module):
        if name.startswith("_"):
            continue
        
        if tool_names and name not in tool_names:
            continue
        
        obj = getattr(module, name)
        if callable(obj) and not isinstance(obj, type):
            try:
                metadata = extract_tool_metadata(obj)
                tools.append(metadata)
                logger.debug(f"Extracted metadata for tool: {name}")
            except Exception as e:
                logger.warning(f"Failed to extract metadata for {name}: {e}")
    
    return tools


def format_tools_for_agent(tools: list[ToolMetadata], header: str = "") -> str:
    """
    Format multiple tools as documentation for agent consumption.
    
    Args:
        tools: List of ToolMetadata objects
        header: Optional header text
        
    Returns:
        Formatted markdown documentation
    """
    sections = []
    
    if header:
        sections.append(header)
        sections.append("")
    
    for tool in tools:
        sections.append(tool.format_for_agent())
        sections.append("")  # Blank line between tools
    
    return "\n".join(sections)


__all__ = [
    "ToolParameter",
    "ToolMetadata", 
    "extract_tool_metadata",
    "extract_tools_from_module",
    "format_tools_for_agent",
]
