"""
Helper functions for tool introspection type handling and docstring parsing.

Extracted from tool_introspection.py for better modularity.
"""

from typing import Any, Optional, Union, get_origin, get_args
import sys

from docstring_parser import parse as parse_docstring
from src.utils.logging import get_logger

logger = get_logger(__name__)

# TypedDict compatibility
if sys.version_info >= (3, 12):
    from typing import is_typeddict
else:
    try:
        from typing_extensions import is_typeddict
    except ImportError:
        def is_typeddict(tp):
            return isinstance(tp, type) and issubclass(tp, dict) and hasattr(tp, '__annotations__')


def get_type_string(annotation: Any) -> str:
    """
    Convert Python type annotation to readable string.
    
    Handles: primitives, generics (list[str]), Union, Optional, TypedDict, etc.
    
    Args:
        annotation: Type annotation from function signature
        
    Returns:
        Human-readable type string
    """
    # Handle None type
    if annotation is type(None):
        return "None"
    
    # Handle string annotations
    if isinstance(annotation, str):
        return annotation
    
    # Handle generic types (list[dict], Optional[str], etc.)
    origin = get_origin(annotation)
    if origin is not None:
        args = get_args(annotation)
        if origin is Union:
            # Handle Optional[X] which is Union[X, None]
            non_none_args = [a for a in args if a is not type(None)]
            if len(non_none_args) == 1 and type(None) in args:
                return f"Optional[{get_type_string(non_none_args[0])}]"
            return f"Union[{', '.join(get_type_string(a) for a in args)}]"
        
        origin_name = getattr(origin, "__name__", str(origin))
        if args:
            args_str = ", ".join(get_type_string(a) for a in args)
            return f"{origin_name}[{args_str}]"
        return origin_name
    
    # Handle regular types
    if hasattr(annotation, "__name__"):
        return annotation.__name__
    
    return str(annotation)


def expand_typeddict_type(type_hint_str: str) -> dict[str, str]:
    """
    Expand TypedDict type from a type hint string.
    
    Extracts the TypedDict class and returns its field definitions.
    
    Args:
        type_hint_str: Type hint string (e.g., 'list[ActionDict]', 'ActionDict')
        
    Returns:
        Dict mapping field names to their types, or empty dict if not a TypedDict
    """
    # Extract inner type from list[T] or dict[K,V]
    inner_type = type_hint_str
    if '[' in type_hint_str:
        start = type_hint_str.index('[') + 1
        end = type_hint_str.rindex(']')
        inner_type = type_hint_str[start:end].strip()
    
    # Try to resolve the TypedDict class from mcp_server module
    try:
        from src.mcp import server as mcp_server
        
        if hasattr(mcp_server, inner_type):
            cls = getattr(mcp_server, inner_type)
            
            # Check if it's a TypedDict
            if is_typeddict(cls):
                annotations = getattr(cls, '__annotations__', {})
                return {name: get_type_string(typ) for name, typ in annotations.items()}
    except Exception as e:
        logger.debug(f"Could not expand TypedDict {inner_type}: {e}")
    
    return {}


def parse_docstring_metadata(docstring: str) -> dict:
    """
    Parse docstring using docstring_parser library.
    
    Supports multiple formats: Google, ReST, Numpydoc, Epydoc.
    
    Args:
        docstring: Raw docstring text from function
        
    Returns:
        Dict with description, args, returns, examples
    """
    if not docstring:
        return {"description": "", "args": {}, "returns": "", "examples": []}
    
    # Parse using docstring_parser
    parsed = parse_docstring(docstring)
    
    # Extract description (short + long)
    description_parts = []
    if parsed.short_description:
        description_parts.append(parsed.short_description)
    if parsed.long_description:
        description_parts.append(parsed.long_description)
    description = " ".join(description_parts)
    
    # Extract parameter descriptions
    args = {}
    for param in parsed.params:
        args[param.arg_name] = param.description or ""
    
    # Extract return value description
    returns = parsed.returns.description if parsed.returns else ""
    
    # Extract examples (if any)
    examples = []
    if parsed.examples:
        for example in parsed.examples:
            if hasattr(example, 'description'):
                examples.append(example.description)
    
    return {
        "description": description,
        "args": args,
        "returns": returns,
        "examples": examples,
    }


def python_type_to_json_type(python_type_str: str) -> str:
    """
    Convert Python type string to JSON schema type.
    
    Args:
        python_type_str: Python type string (e.g., 'str', 'int', 'list[str]')
        
    Returns:
        JSON schema type string
    """
    type_mapping = {
        "str": "string",
        "int": "integer",
        "float": "number",
        "bool": "boolean",
        "list": "array",
        "dict": "object",
        "Any": "any",
        "None": "null",
    }
    
    # Handle generic types like list[str], dict[str, int]
    base_type = python_type_str.split('[')[0].strip()
    
    return type_mapping.get(base_type, "string")
