"""
Message formatting utilities for agent/system/purple-agent messages.

This module centralizes message prefixing so it can be reused by monitoring
and the A2A message handler.
"""

from typing import Any


def format_system_message(message: str) -> str:
    """Return a system-prefixed message for the agent.

    Example: "agent_internal_system: Evaluation complete"
    """
    return f"agent_internal_system: {message}"


def format_purple_agent_message(purple_agent_id: str, message: str) -> str:
    """Return a purple-agent-prefixed message.

    Example: "purple_agent_ab12cd34: started step 1"
    """
    return f"purple_agent_{purple_agent_id}: {message}"
