"""
Extract benchmark-specific action definitions from BrowserGym SDK.

Provides functions to:
1. Get the list of allowed action strings for a benchmark
2. Extract parameter requirements for each action
3. Format action documentation for Purple Agent
"""

import inspect
from typing import Dict, List, Any, Optional
from browsergym.core.action.highlevel import ACTION_SUBSETS
from src.utils.logging import get_logger

logger = get_logger(__name__)


def get_benchmark_actions(benchmark_id: str) -> List[str]:
    """
    Get list of allowed action strings for a benchmark.

    Dynamically queries BrowserGym's ACTION_SUBSETS to find the matching action set.
    Tries multiple strategies:
    1. Direct lookup (e.g., 'assistantbench')
    2. Common variants (e.g., 'miniwob' → 'miniwob_all')
    3. Fallback to related subsets

    Args:
        benchmark_id: Benchmark identifier (e.g., 'assistantbench', 'miniwob', 'webarena')

    Returns:
        List of action function names (strings)
    """
    # Strategy 1: Try direct lookup
    action_functions = ACTION_SUBSETS.get(benchmark_id)

    if action_functions:
        action_names = [func.__name__ for func in action_functions]
        logger.info(f"Found {len(action_names)} actions for '{benchmark_id}' (direct match)")
        return action_names

    # Strategy 2: Try common variants
    variants_to_try = [
        f"{benchmark_id}_all",      # e.g., miniwob → miniwob_all
        f"{benchmark_id}++",         # e.g., workarena → workarena++
        benchmark_id.replace("_", "-"),  # e.g., visual_webarena → visual-webarena
    ]

    for variant in variants_to_try:
        action_functions = ACTION_SUBSETS.get(variant)
        if action_functions:
            action_names = [func.__name__ for func in action_functions]
            logger.info(f"Found {len(action_names)} actions for '{benchmark_id}' using variant '{variant}'")
            return action_names

    # Strategy 3: Search for any subset key containing the benchmark name
    benchmark_lower = benchmark_id.lower()
    for subset_key in ACTION_SUBSETS.keys():
        if benchmark_lower in subset_key.lower():
            action_functions = ACTION_SUBSETS[subset_key]
            action_names = [func.__name__ for func in action_functions]
            logger.info(f"Found {len(action_names)} actions for '{benchmark_id}' using fuzzy match '{subset_key}'")
            return action_names

    # No match found - log warning and return empty
    logger.warning(f"No action subset found for benchmark '{benchmark_id}'. Available subsets: {list(ACTION_SUBSETS.keys())}")
    return []


def get_action_signature(action_func) -> Dict[str, Any]:
    """
    Extract parameter signature from an action function.

    Args:
        action_func: Action function from browsergym.core.action.functions

    Returns:
        Dict with 'params' (list of param names) and 'required' (list of required params)
    """
    sig = inspect.signature(action_func)
    params = []
    required = []

    for param_name, param in sig.parameters.items():
        params.append(param_name)
        # Required if no default value
        if param.default is inspect.Parameter.empty:
            required.append(param_name)

    return {
        "params": params,
        "required": required,
    }


def get_action_docstring(action_func) -> str:
    """
    Get the docstring for an action function.

    Args:
        action_func: Action function from browsergym.core.action.functions

    Returns:
        Cleaned docstring or empty string
    """
    docstring = inspect.getdoc(action_func) or ""
    return docstring.strip()


def _get_action_functions_for_benchmark(benchmark_id: str) -> List:
    """
    Internal helper to get action function objects for a benchmark.

    Uses the same 3-strategy lookup as get_benchmark_actions() but returns
    the actual function objects instead of just their names.

    Args:
        benchmark_id: Benchmark identifier

    Returns:
        List of action function objects
    """
    # Strategy 1: Try direct lookup
    action_functions = ACTION_SUBSETS.get(benchmark_id)
    if action_functions:
        logger.debug(f"Found action functions for '{benchmark_id}' (direct match)")
        return action_functions

    # Strategy 2: Try common variants
    variants_to_try = [
        f"{benchmark_id}_all",      # e.g., miniwob → miniwob_all
        f"{benchmark_id}++",         # e.g., workarena → workarena++
        benchmark_id.replace("_", "-"),  # e.g., visual_webarena → visual-webarena
    ]

    for variant in variants_to_try:
        action_functions = ACTION_SUBSETS.get(variant)
        if action_functions:
            logger.debug(f"Found action functions for '{benchmark_id}' using variant '{variant}'")
            return action_functions

    # Strategy 3: Search for any subset key containing the benchmark name
    benchmark_lower = benchmark_id.lower()
    for subset_key in ACTION_SUBSETS.keys():
        if benchmark_lower in subset_key.lower():
            action_functions = ACTION_SUBSETS[subset_key]
            logger.debug(f"Found action functions for '{benchmark_id}' using fuzzy match '{subset_key}'")
            return action_functions

    # No match found
    logger.warning(f"No action functions found for benchmark '{benchmark_id}'")
    return []


def build_benchmark_action_docs(benchmark_id: str) -> str:
    """
    Build comprehensive action documentation for a specific benchmark.

    Extracts:
    - List of allowed action strings
    - Parameter requirements for each action
    - Examples from docstrings

    Args:
        benchmark_id: Benchmark identifier

    Returns:
        Formatted markdown documentation
    """
    # Get action functions dynamically using the same lookup strategy
    action_functions = _get_action_functions_for_benchmark(benchmark_id)

    if not action_functions:
        available_subsets = list(ACTION_SUBSETS.keys())
        return f"No action subset found for benchmark '{benchmark_id}'.\n\nAvailable subsets: {', '.join(available_subsets)}"

    lines = [
        "**Allowed actions for this benchmark:**",
        ""
    ]

    # Group actions by category
    categories = {
        "Element Interaction": ["click", "dblclick", "hover", "fill", "clear", "focus", "select_option", "press", "drag_and_drop"],
        "Keyboard": ["keyboard_type", "keyboard_press", "keyboard_insert_text", "keyboard_down", "keyboard_up"],
        "Scrolling": ["scroll", "scroll_at"],
        "Mouse": ["mouse_move", "mouse_click", "mouse_dblclick", "mouse_down", "mouse_up", "mouse_drag_and_drop"],
        "Navigation": ["goto", "go_back", "go_forward"],
        "Tab Management": ["new_tab", "tab_close", "tab_focus"],
        "Communication": ["send_msg_to_user", "report_infeasible"],
        "Other": ["noop", "upload_file", "mouse_upload_file"],
    }

    # Organize actions by category
    categorized = {cat: [] for cat in categories}
    uncategorized = []

    for func in action_functions:
        name = func.__name__
        found = False
        for cat, actions in categories.items():
            if name in actions:
                categorized[cat].append(func)
                found = True
                break
        if not found:
            uncategorized.append(func)

    # Format by category
    for category, funcs in categorized.items():
        if not funcs:
            continue

        lines.append(f"**{category}:**")
        for func in funcs:
            name = func.__name__
            sig = get_action_signature(func)
            required_params = ", ".join(sig["required"]) if sig["required"] else "none"
            lines.append(f"- `{name}` (required params: {required_params})")
        lines.append("")

    # Add uncategorized
    if uncategorized:
        lines.append("**Other:**")
        for func in uncategorized:
            name = func.__name__
            sig = get_action_signature(func)
            required_params = ", ".join(sig["required"]) if sig["required"] else "none"
            lines.append(f"- `{name}` (required params: {required_params})")
        lines.append("")

    return "\n".join(lines)


def get_action_parameter_mapping() -> Dict[str, Dict[str, Any]]:
    """
    Get a complete mapping of action names to their parameter requirements.

    This provides a reference for what parameters each action needs,
    independent of benchmark.

    Returns:
        Dict mapping action name to parameter info
    """
    # Import all action functions
    from browsergym.core.action import functions as action_functions_module

    mapping = {}

    # Get all action functions from the module
    for name in dir(action_functions_module):
        if name.startswith("_"):
            continue

        obj = getattr(action_functions_module, name)
        if callable(obj) and not isinstance(obj, type):
            sig = get_action_signature(obj)
            docstring = get_action_docstring(obj)

            mapping[name] = {
                "params": sig["params"],
                "required": sig["required"],
                "docstring": docstring[:200] + "..." if len(docstring) > 200 else docstring,
            }

    return mapping


__all__ = [
    "get_benchmark_actions",
    "get_action_signature",
    "get_action_docstring",
    "build_benchmark_action_docs",
    "get_action_parameter_mapping",
]
