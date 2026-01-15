"""
Observation parsing utilities for Test Purple Agent.

⚠️ DEPRECATED: This module is kept for reference only.
With the new MCP proxy tools approach, observation parsing should be done
by calling the MCP tool directly and processing the result inline.

Legacy utility: Extract actionable elements from BrowserGym observations (HTML, AXTree).
Implements Parse observation to extract clickable elements and interactive components.
"""

import re
from typing import Any, Dict, List


def parse_observation_for_actions(observation: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parse BrowserGym observation to extract actionable elements.
    
    Extracts clickable elements (buttons, links) and input fields from AXTree.
    Provides simplified view for agent analysis.
    
    Args:
        observation: Raw observation from mcp_get_observation
        
    Returns:
        Parsed observation with clickable_elements and input_fields
    """
    done = observation.get("done", False)
    reward = observation.get("reward", 0.0)
    axtree = observation.get("full_axtree", "")
    
    # Parse clickable elements (buttons, links) from AXTree
    clickable_elements = _extract_clickable_elements(axtree)
    
    # Parse input fields from AXTree
    input_fields = _extract_input_fields(axtree)
    
    return {
        "done": done,
        "reward": reward,
        "clickable_elements": clickable_elements,
        "input_fields": input_fields,
        "raw_axtree_length": len(axtree),
        "summary": f"{len(clickable_elements)} clickable elements, {len(input_fields)} input fields"
    }


def _extract_clickable_elements(axtree: str) -> List[Dict[str, Any]]:
    """
    Extract clickable elements (buttons, links) from AXTree.
    
    Looks for patterns like:
    - [12] button "Submit"
    - [34] link "Click here"
    - [56] RootWebArea "Title"
    
    Args:
        axtree: Accessibility tree text
        
    Returns:
        List of clickable elements with bid, type, label
    """
    clickable_elements = []
    
    # Pattern: [bid] type "label"
    pattern = r'\[(\d+)\]\s+(button|link|RootWebArea)\s+"([^"]*)"'
    
    for match in re.finditer(pattern, axtree):
        bid = match.group(1)
        element_type = match.group(2)
        label = match.group(3)
        
        clickable_elements.append({
            "bid": bid,
            "type": element_type,
            "label": label
        })
    
    return clickable_elements


def _extract_input_fields(axtree: str) -> List[Dict[str, Any]]:
    """
    Extract input fields (textbox, textarea) from AXTree.
    
    Looks for patterns like:
    - [78] textbox "Email"
    - [90] textarea "Message"
    
    Args:
        axtree: Accessibility tree text
        
    Returns:
        List of input fields with bid, type, label
    """
    input_fields = []
    
    # Pattern: [bid] textbox/textarea "label"
    pattern = r'\[(\d+)\]\s+(textbox|textarea)\s+"([^"]*)"'
    
    for match in re.finditer(pattern, axtree):
        bid = match.group(1)
        field_type = match.group(2)
        label = match.group(3)
        
        input_fields.append({
            "bid": bid,
            "type": field_type,
            "label": label
        })
    
    return input_fields


__all__ = ["parse_observation_for_actions"]
