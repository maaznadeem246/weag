"""
Action generation utilities for Test Purple Agent.

⚠️ DEPRECATED: This module is kept for reference only.
With the new MCP proxy tools approach, actions should be generated inline
and passed directly to call_mcp_tool("browsergym", "execute_actions", {...}).

Legacy utility: Generate BrowserGym actions from parsed observations and agent analysis.
Implements Generate click/type actions from parsed observation.
"""

from typing import Any, Dict, Optional


def generate_action_from_analysis(
    action_type: str,
    bid: str,
    text: Optional[str] = None,
    **kwargs
) -> Dict[str, Any]:
    """
    Generate BrowserGym action from agent analysis.
    
    Supports common action types: click, type, scroll, wait.
    
    Args:
        action_type: Type of action (click, type, scroll, wait)
        bid: Browser ID for target element
        text: Text to type (required for type actions)
        **kwargs: Additional action parameters
        
    Returns:
        BrowserGym action dict ready for mcp_execute_action
    """
    action = {
        "action_type": action_type,
        "bid": bid
    }
    
    # Add text for type actions
    if action_type == "type" and text:
        action["text"] = text
    
    # Add any additional parameters
    action.update(kwargs)
    
    return action


def generate_click_action(bid: str) -> Dict[str, Any]:
    """
    Generate click action.
    
    Args:
        bid: Browser ID for element to click
        
    Returns:
        Click action dict
    """
    return generate_action_from_analysis("click", bid)


def generate_type_action(bid: str, text: str) -> Dict[str, Any]:
    """
    Generate type action.
    
    Args:
        bid: Browser ID for input field
        text: Text to type
        
    Returns:
        Type action dict
    """
    return generate_action_from_analysis("type", bid, text=text)


def generate_wait_action(duration_ms: int = 1000) -> Dict[str, Any]:
    """
    Generate wait action.
    
    Args:
        duration_ms: Duration to wait in milliseconds
        
    Returns:
        Wait action dict
    """
    return {
        "action_type": "wait",
        "duration_ms": duration_ms
    }


__all__ = [
    "generate_action_from_analysis",
    "generate_click_action",
    "generate_type_action",
    "generate_wait_action",
]
