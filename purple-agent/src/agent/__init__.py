"""
Agent module for Test Purple Agent.

Exports context, instructions, and agent factory.
"""

from src.agent.agent_factory import create_test_purple_agent, PURPLE_AGENT_TOOLS
from src.agent.context import TestPurpleAgentContext
from src.agent.instructions import TEST_PURPLE_AGENT_INSTRUCTIONS

__all__ = [
    "TestPurpleAgentContext",
    "TEST_PURPLE_AGENT_INSTRUCTIONS",
    "create_test_purple_agent",
    "PURPLE_AGENT_TOOLS",
]
