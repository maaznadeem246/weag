"""
Agent module for agentic evaluation orchestration using OpenAI Agents SDK.

This module provides:
- Agent context management
- Tool implementations (environment, monitoring, communication, evaluation)
- Guardrails (input/output validation)
- Session management (persistent and in-memory)
- Agent factory for creating configured agents
"""

__all__ = ["agent_factory", "context", "instructions", "tools", "guardrails", "sessions"]
