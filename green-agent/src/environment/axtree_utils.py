"""
AXTree utilities for extracting element information from BrowserGym observations.

Provides functions to:
- Find button bids from AXTree observations
- Map DOM element IDs to BrowserGym numeric bids
"""

import re
from typing import Any, Dict, Optional, List, Union


def find_button_bid_from_observation(observation: Union[Dict[str, Any], str]) -> Optional[str]:
    """
    Find the browsergym_id of a button element from an observation.
    
    Searches the AXTree for nodes with role 'button' and returns the first
    browsergym_id found.
    
    Args:
        observation: Parsed observation dict or serialized AXTree string
        
    Returns:
        Numeric browsergym_id as string, or None if no button found
    """
    # If observation is a dict, try to extract axtree_object or axtree
    if isinstance(observation, dict):
        # Try axtree_object first (structured dict)
        axtree_obj = observation.get("axtree_object")
        if isinstance(axtree_obj, dict):
            bid = _find_button_in_axtree_dict(axtree_obj)
            if bid:
                return bid
        
        # Try initial_observation.axtree_object
        initial_obs = observation.get("initial_observation")
        if isinstance(initial_obs, dict):
            axtree_obj = initial_obs.get("axtree_object")
            if isinstance(axtree_obj, dict):
                bid = _find_button_in_axtree_dict(axtree_obj)
                if bid:
                    return bid
        
        # Try axtree as string
        axtree_str = observation.get("axtree") or observation.get("axtree_str")
        if isinstance(axtree_str, str):
            bid = _find_button_in_axtree_string(axtree_str)
            if bid:
                return bid
        
        # Try observation.axtree
        obs_field = observation.get("observation")
        if isinstance(obs_field, dict):
            axtree_str = obs_field.get("axtree") or obs_field.get("axtree_str")
            if isinstance(axtree_str, str):
                bid = _find_button_in_axtree_string(axtree_str)
                if bid:
                    return bid
    
    # If observation is a string, parse it directly
    elif isinstance(observation, str):
        return _find_button_in_axtree_string(observation)
    
    return None


def _find_button_in_axtree_dict(axtree: Dict[str, Any]) -> Optional[str]:
    """
    Find button bid in a structured AXTree dict.
    
    Args:
        axtree: AXTree object with 'nodes' list
        
    Returns:
        browsergym_id of first button node, or None
    """
    nodes = axtree.get("nodes", [])
    
    for node in nodes:
        # Extract role
        role = None
        role_field = node.get("role")
        if isinstance(role_field, dict):
            role = role_field.get("value", "")
        elif isinstance(role_field, str):
            role = role_field
        
        # Check if this is a button
        if role and "button" in str(role).lower():
            bgid = node.get("browsergym_id")
            if bgid:
                return str(bgid)
    
    return None


def _find_button_in_axtree_string(axtree_str: str) -> Optional[str]:
    """
    Find button bid in a serialized AXTree string using regex.
    
    Args:
        axtree_str: Serialized AXTree (JSON-like or Python repr)
        
    Returns:
        browsergym_id of first button node, or None
    """
    # Pattern 1: Look for button role followed by browsergym_id
    # Match patterns like: 'role': {'type': 'role', 'value': 'button'} ... 'browsergym_id': '13'
    # We need to find nodes that are buttons and extract their browsergym_id
    
    # First, try to find all browsergym_id values associated with button roles
    # Pattern: node dict containing both role=button and browsergym_id
    
    # Simpler approach: find all nodes with role 'button' and their browsergym_ids
    # Look for pattern: 'value': 'button' ... 'browsergym_id': 'N'
    button_pattern = r"'role'[^}]*'value':\s*'button'[^}]*}[^}]*'browsergym_id':\s*'(\d+)'"
    match = re.search(button_pattern, axtree_str)
    if match:
        return match.group(1)
    
    # Alternative pattern for JSON format
    button_pattern_json = r'"role"[^}]*"value":\s*"button"[^}]*}[^}]*"browsergym_id":\s*"(\d+)"'
    match = re.search(button_pattern_json, axtree_str)
    if match:
        return match.group(1)
    
    # Fallback: try to find any browsergym_id near a button mention
    # This is less precise but catches edge cases
    if "button" in axtree_str.lower():
        # Find all browsergym_ids
        bgid_pattern = r"'browsergym_id':\s*'(\d+)'"
        matches = re.findall(bgid_pattern, axtree_str)
        if matches:
            # Return the highest numbered one (buttons tend to be later in tree)
            return max(matches, key=int)
        
        # Try JSON format
        bgid_pattern_json = r'"browsergym_id":\s*"(\d+)"'
        matches = re.findall(bgid_pattern_json, axtree_str)
        if matches:
            return max(matches, key=int)
    
    return None


def map_dom_id_to_bid(
    observation: Dict[str, Any],
    dom_id: str
) -> Optional[str]:
    """
    Map a DOM element ID to its BrowserGym numeric bid.
    
    Args:
        observation: Parsed observation dict containing extra_element_properties
        dom_id: DOM element ID attribute (e.g., 'subbtn')
        
    Returns:
        Numeric browsergym_id as string, or None if not found
    """
    # Try extra_element_properties mapping
    props = observation.get("extra_element_properties", {})
    
    for bid, prop_data in props.items():
        if isinstance(prop_data, dict):
            attrs = prop_data.get("attributes", {})
            if isinstance(attrs, dict) and attrs.get("id") == dom_id:
                return str(bid)
    
    # Try initial_observation.extra_element_properties
    initial_obs = observation.get("initial_observation", {})
    if isinstance(initial_obs, dict):
        props = initial_obs.get("extra_element_properties", {})
        for bid, prop_data in props.items():
            if isinstance(prop_data, dict):
                attrs = prop_data.get("attributes", {})
                if isinstance(attrs, dict) and attrs.get("id") == dom_id:
                    return str(bid)
    
    return None


def find_clickable_element_bid(
    observation: Union[Dict[str, Any], str],
    preferred_dom_id: Optional[str] = None
) -> Optional[str]:
    """
    Find a clickable element's bid from observation.
    
    Combines multiple strategies:
    1. If preferred_dom_id given, try mapping it first
    2. Look for button in AXTree
    3. Fallback to any clickable element
    
    Args:
        observation: Parsed observation dict or string
        preferred_dom_id: Optional DOM ID to prefer (e.g., 'subbtn')
        
    Returns:
        Numeric browsergym_id as string, or None if not found
    """
    # Strategy 1: Map preferred DOM ID if provided
    if preferred_dom_id and isinstance(observation, dict):
        bid = map_dom_id_to_bid(observation, preferred_dom_id)
        if bid:
            return bid
    
    # Strategy 2: Find button in AXTree
    bid = find_button_bid_from_observation(observation)
    if bid:
        return bid
    
    return None
