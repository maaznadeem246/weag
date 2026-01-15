"""
Observation utilities for BrowserGym environment.

This module provides utilities for processing BrowserGym observations,
using the official browsergym.utils.obs APIs where possible.

The BrowserGym observation space includes:
- axtree_object: Accessibility tree (dict with nodes)
- dom_object: DOM tree representation
- screenshot: Page screenshot (numpy array)
- extra_element_properties: Additional element info (attributes, visibility, etc.)
- goal: Task goal text
- goal_object: Structured goal (for chat mode)
- url: Current page URL
- open_pages_urls: URLs of all open tabs
- open_pages_titles: Titles of all open tabs
- active_page_index: Index of active tab
- last_action: Previous action taken
- last_action_error: Error from previous action (if any)
- chat_messages: Chat history (for chat mode)
"""

import re
from typing import Any, Dict, List, Optional, Tuple

from src.utils.logging import get_logger

logger = get_logger(__name__)


# Try to import official BrowserGym utilities
try:
    from browsergym.utils.obs import flatten_axtree_to_str, flatten_dom_to_str, prune_html
    BROWSERGYM_UTILS_AVAILABLE = True
except ImportError:
    BROWSERGYM_UTILS_AVAILABLE = False
    logger.warning("browsergym.utils.obs not available, using fallback implementations")


def format_axtree(
    observation: Dict[str, Any],
    with_visible: bool = False,
    with_clickable: bool = False,
    skip_generic: bool = True,
    filter_visible_only: bool = False,
) -> str:
    """
    Format accessibility tree into a readable string.
    
    Uses the official BrowserGym flatten_axtree_to_str when available.
    
    Args:
        observation: BrowserGym observation dict
        with_visible: Include visibility information
        with_clickable: Include clickability information
        skip_generic: Skip generic/container elements
        filter_visible_only: Only include visible elements
        
    Returns:
        Formatted AXTree string
    """
    axtree_object = _extract_axtree_object(observation)
    
    if axtree_object is None:
        return ""
    
    extra_properties = observation.get("extra_element_properties", {})
    if not extra_properties:
        # Check nested observation
        inner_obs = observation.get("initial_observation", {})
        extra_properties = inner_obs.get("extra_element_properties", {})
    
    if BROWSERGYM_UTILS_AVAILABLE:
        try:
            return flatten_axtree_to_str(
                axtree_object,
                extra_properties=extra_properties,
                with_visible=with_visible,
                with_clickable=with_clickable,
                skip_generic=skip_generic,
                filter_visible_only=filter_visible_only,
            )
        except Exception as e:
            logger.warning(f"Error using flatten_axtree_to_str: {e}")
    
    # Fallback: simple formatting
    return _format_axtree_fallback(axtree_object)


def format_html(observation: Dict[str, Any], max_length: int = 50000) -> str:
    """
    Format and prune HTML for agent consumption.
    
    Uses the official BrowserGym prune_html and flatten_dom_to_str when available.
    
    Args:
        observation: BrowserGym observation dict
        max_length: Maximum HTML length
        
    Returns:
        Pruned HTML string
    """
    dom_object = observation.get("dom_object")
    if dom_object is None:
        inner_obs = observation.get("initial_observation", {})
        dom_object = inner_obs.get("dom_object")
    
    if dom_object is None:
        return ""
    
    if BROWSERGYM_UTILS_AVAILABLE:
        try:
            flat_dom = flatten_dom_to_str(dom_object)
            return prune_html(flat_dom)[:max_length]
        except Exception as e:
            logger.warning(f"Error using DOM utilities: {e}")
    
    # Fallback: return raw string representation
    return str(dom_object)[:max_length]


def get_goal(observation: Dict[str, Any]) -> str:
    """
    Extract goal text from observation.
    
    Args:
        observation: BrowserGym observation dict
        
    Returns:
        Goal text string
    """
    # Direct goal field
    goal = observation.get("goal", "")
    if goal:
        return goal
    
    # Check nested observation
    inner_obs = observation.get("initial_observation", {})
    goal = inner_obs.get("goal", "")
    if goal:
        return goal
    
    # Check goal_object (structured goal)
    goal_object = observation.get("goal_object", [])
    if goal_object:
        texts = []
        for item in goal_object:
            if isinstance(item, dict) and item.get("type") == "text":
                texts.append(item.get("text", ""))
        return " ".join(texts)
    
    return ""


def get_url(observation: Dict[str, Any]) -> str:
    """
    Extract current page URL from observation.
    
    Args:
        observation: BrowserGym observation dict
        
    Returns:
        Current URL string
    """
    url = observation.get("url", "")
    if url:
        return url
    
    inner_obs = observation.get("initial_observation", {})
    return inner_obs.get("url", "")


def get_last_action_error(observation: Dict[str, Any]) -> Optional[str]:
    """
    Get error from last action if any.
    
    Args:
        observation: BrowserGym observation dict
        
    Returns:
        Error string or None
    """
    error = observation.get("last_action_error")
    if error:
        return str(error)
    
    inner_obs = observation.get("initial_observation", {})
    error = inner_obs.get("last_action_error")
    return str(error) if error else None


def find_elements_by_role(
    observation: Dict[str, Any],
    role: str,
    include_children: bool = False
) -> List[Dict[str, Any]]:
    """
    Find all elements with a specific role in the AXTree.
    
    Args:
        observation: BrowserGym observation dict
        role: Role to search for (e.g., "button", "textbox", "link")
        include_children: Whether to include elements with matching child roles
        
    Returns:
        List of matching element dicts with their browsergym_id (bid)
    """
    axtree_object = _extract_axtree_object(observation)
    if axtree_object is None:
        return []
    
    nodes = axtree_object.get("nodes", [])
    matches = []
    
    for node in nodes:
        node_role = _get_node_role(node)
        if node_role and node_role.lower() == role.lower():
            bid = node.get("browsergym_id")
            if bid:
                matches.append({
                    "bid": str(bid),
                    "role": node_role,
                    "name": _get_node_name(node),
                    "node": node
                })
    
    return matches


def find_element_by_text(
    observation: Dict[str, Any],
    text: str,
    role: Optional[str] = None,
    exact: bool = False
) -> Optional[str]:
    """
    Find an element's bid by its text content.
    
    Args:
        observation: BrowserGym observation dict
        text: Text to search for
        role: Optional role filter (e.g., "button", "link")
        exact: Whether to match text exactly
        
    Returns:
        Element's browsergym_id (bid) or None
    """
    axtree_object = _extract_axtree_object(observation)
    if axtree_object is None:
        return None
    
    nodes = axtree_object.get("nodes", [])
    text_lower = text.lower()
    
    for node in nodes:
        bid = node.get("browsergym_id")
        if not bid:
            continue
        
        # Check role filter
        if role:
            node_role = _get_node_role(node)
            if not node_role or node_role.lower() != role.lower():
                continue
        
        # Check text match
        node_name = _get_node_name(node)
        if node_name:
            if exact:
                if node_name == text:
                    return str(bid)
            else:
                if text_lower in node_name.lower():
                    return str(bid)
    
    return None


def find_clickable_element(
    observation: Dict[str, Any],
    preferred_text: Optional[str] = None,
    preferred_role: str = "button"
) -> Optional[str]:
    """
    Find a clickable element's bid.
    
    This is a generic helper that tries multiple strategies:
    1. If preferred_text given, search for element with that text
    2. Find first element with preferred_role (default: button)
    3. Find any clickable element (link, button, etc.)
    
    Args:
        observation: BrowserGym observation dict
        preferred_text: Preferred element text to find
        preferred_role: Preferred element role (default: "button")
        
    Returns:
        Element's browsergym_id (bid) or None
    """
    # Strategy 1: Find by text if given
    if preferred_text:
        bid = find_element_by_text(observation, preferred_text)
        if bid:
            return bid
    
    # Strategy 2: Find by preferred role
    elements = find_elements_by_role(observation, preferred_role)
    if elements:
        return elements[0]["bid"]
    
    # Strategy 3: Try common clickable roles
    clickable_roles = ["button", "link", "menuitem", "tab", "checkbox", "radio"]
    for role in clickable_roles:
        if role == preferred_role:
            continue  # Already tried
        elements = find_elements_by_role(observation, role)
        if elements:
            return elements[0]["bid"]
    
    return None


def find_input_element(
    observation: Dict[str, Any],
    input_type: Optional[str] = None,
    name: Optional[str] = None
) -> Optional[str]:
    """
    Find an input element's bid.
    
    Args:
        observation: BrowserGym observation dict
        input_type: Input type filter (e.g., "text", "email", "password")
        name: Input name or placeholder text to match
        
    Returns:
        Element's browsergym_id (bid) or None
    """
    # Search for textbox, searchbox, or spinbutton roles
    input_roles = ["textbox", "searchbox", "spinbutton", "combobox"]
    
    for role in input_roles:
        elements = find_elements_by_role(observation, role)
        
        for elem in elements:
            if name:
                elem_name = elem.get("name", "").lower()
                if name.lower() in elem_name:
                    return elem["bid"]
            else:
                return elem["bid"]
    
    return None


def map_dom_id_to_bid(
    observation: Dict[str, Any],
    dom_id: str
) -> Optional[str]:
    """
    Map a DOM element id to its BrowserGym bid.
    
    This uses extra_element_properties which contains
    the mapping between bids and their DOM attributes.
    
    Args:
        observation: BrowserGym observation dict
        dom_id: DOM element id attribute value
        
    Returns:
        Element's browsergym_id (bid) or None
    """
    # The MCP/get_observation response can nest properties in several
    # places (observation, initial_observation, results[*].observation, etc.).
    # Walk these possible locations to find `extra_element_properties`.

    def _find_extra_props(obj: Any) -> Optional[Dict[str, Any]]:
        if not obj:
            return None

        # Direct mapping
        if isinstance(obj, dict) and "extra_element_properties" in obj:
            return obj.get("extra_element_properties")

        # If this is the typical MCP result wrapper
        if isinstance(obj, dict) and "observation" in obj:
            return _find_extra_props(obj.get("observation"))

        # Nested initial observation
        if isinstance(obj, dict) and "initial_observation" in obj:
            return _find_extra_props(obj.get("initial_observation"))

        # Sometimes the axtree/extra props are inside a list of results
        if isinstance(obj, dict) and "results" in obj and isinstance(obj.get("results"), list):
            for item in obj.get("results", []):
                # Each result may contain an observation dict
                ep = _find_extra_props(item)
                if ep:
                    return ep

        # If obj itself looks like extra_element_properties (mapping bids->props)
        if isinstance(obj, dict):
            # Heuristic: keys are numeric strings and values are dicts with 'attributes'
            keys = list(obj.keys())
            if keys:
                sample_key = keys[0]
                sample_val = obj.get(sample_key)
                if isinstance(sample_val, dict) and ("attributes" in sample_val or "visible" in sample_val):
                    return obj

        return None

    extra_props = _find_extra_props(observation)
    if not extra_props:
        return None

    for bid, props in extra_props.items():
        if not isinstance(props, dict):
            continue
        attrs = props.get("attributes", {})
        if not isinstance(attrs, dict):
            continue
        if attrs.get("id") == dom_id:
            return str(bid)

    return None


# ============================================================================
# Internal helpers
# ============================================================================

def _extract_axtree_object(observation: Any) -> Optional[Dict]:
    """Extract axtree_object from various observation formats."""
    if observation is None:
        return None
    
    if isinstance(observation, str):
        # Try to parse as Python dict repr or JSON
        try:
            import ast
            return ast.literal_eval(observation)
        except:
            pass
        try:
            import json
            return json.loads(observation)
        except:
            return None
    
    if isinstance(observation, dict):
        # Direct axtree_object (dict form)
        if "axtree_object" in observation:
            axtree_obj = observation["axtree_object"]
            if isinstance(axtree_obj, dict):
                return axtree_obj
            # It might be a string that needs parsing
            return _extract_axtree_object(axtree_obj)
        
        # axtree as string (common in MCP responses)
        if "axtree" in observation:
            axtree_str = observation["axtree"]
            if isinstance(axtree_str, str):
                return _extract_axtree_object(axtree_str)
            elif isinstance(axtree_str, dict):
                return axtree_str
        
        # Nested in observation (MCP get_observation response)
        if "observation" in observation:
            return _extract_axtree_object(observation["observation"])
        
        # Nested in initial_observation
        inner_obs = observation.get("initial_observation", {})
        if isinstance(inner_obs, dict):
            if "axtree_object" in inner_obs:
                return _extract_axtree_object(inner_obs["axtree_object"])
            if "axtree" in inner_obs:
                return _extract_axtree_object(inner_obs["axtree"])
        
        # The observation itself might be the axtree
        if "nodes" in observation:
            return observation
    
    return None


def _get_node_role(node: Dict) -> Optional[str]:
    """Extract role from AXTree node."""
    role = node.get("role")
    
    if role is None:
        return None
    
    if isinstance(role, str):
        return role
    
    if isinstance(role, dict):
        return role.get("value")
    
    return None


def _get_node_name(node: Dict) -> Optional[str]:
    """Extract name/label from AXTree node."""
    name = node.get("name")
    
    if name is None:
        return None
    
    if isinstance(name, str):
        return name
    
    if isinstance(name, dict):
        return name.get("value")
    
    return None


def _format_axtree_fallback(axtree: Dict) -> str:
    """
    Fallback AXTree formatting when official utils unavailable.
    
    Produces a simple text representation showing role, name, and bid.
    """
    lines = []
    nodes = axtree.get("nodes", [])
    
    for node in nodes:
        role = _get_node_role(node)
        name = _get_node_name(node)
        bid = node.get("browsergym_id")
        
        if not bid:
            continue
        
        # Skip generic containers
        if role and role.lower() in ("generic", "none"):
            continue
        
        # Format line
        parts = [f"[{bid}]"]
        if role:
            parts.append(role)
        if name:
            parts.append(f'"{name}"')
        
        lines.append(" ".join(parts))
    
    return "\n".join(lines)


# ============================================================================
# Legacy compatibility aliases (deprecated)
# ============================================================================

def find_button_bid_from_observation(observation: Any) -> Optional[str]:
    """
    DEPRECATED: Use find_clickable_element() instead.
    
    Find a button element's bid from observation.
    """
    logger.warning("find_button_bid_from_observation is deprecated, use find_clickable_element()")
    return find_clickable_element(observation, preferred_role="button")


def find_clickable_element_bid(
    observation: Any,
    preferred_dom_id: Optional[str] = None
) -> Optional[str]:
    """
    DEPRECATED: Use find_clickable_element() or map_dom_id_to_bid() instead.
    
    Find a clickable element's bid, optionally by DOM id.
    """
    logger.warning("find_clickable_element_bid is deprecated, use find_clickable_element() or map_dom_id_to_bid()")
    
    if preferred_dom_id:
        bid = map_dom_id_to_bid(observation, preferred_dom_id)
        if bid:
            return bid
    
    return find_clickable_element(observation, preferred_role="button")
