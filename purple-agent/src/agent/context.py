"""
Context model for Test Purple Agent.

Stores evaluation state and MCP connection details.
"""

from typing import Any, Optional
from pydantic import BaseModel, HttpUrl, Field, ConfigDict


class TestPurpleAgentContext(BaseModel):
    """
    Context passed to purple agent tools.
    
    Contains:
    - Task information (task_id, benchmark)
    - MCP connection details (from Green Agent)
    - Session state
    - Green Agent URL
    """
    
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra='forbid'  # Forbid extra fields for OpenAI Agents SDK compatibility
    )
    
    # Task Information - may be unknown at start; Green Agent will provide details via A2A
    task_id: Optional[str] = Field(default=None, description="Task identifier (format: {benchmark}.{task_name})")
    benchmark: Optional[str] = Field(default=None, description="Benchmark name")
    task_description: Optional[str] = Field(
        default=None,
        description="Human-readable task description"
    )
    
    # Green Agent Communication
    green_agent_url: HttpUrl = Field(description="Green Agent A2A endpoint URL")
    interaction_id: Optional[str] = Field(
        default=None,
        description="A2A interaction ID for event subscription"
    )
    
    # MCP Connection Details (received from Green Agent via A2A)
    mcp_connection_details: Optional[dict[str, Any]] = Field(
        default=None,
        description="MCP server connection details (transport, url, command, args)"
    )
    mcp_connected: bool = Field(default=False, description="Whether MCP client is connected")
    mcp_session_id: Optional[str] = Field(
        default=None,
        description="MCP environment session ID (after initialization)"
    )
    
    # Session State
    actions_taken: int = Field(default=0, description="Number of actions executed")
    task_complete: bool = Field(default=False, description="Whether task is complete")
    final_reward: float = Field(default=0.0, description="Final task reward")
    
    # MCP Registry for dynamic connections (supports multiple MCP servers)
    mcp_registry: dict[str, Any] = Field(
        default_factory=dict,
        description="Registry of connected MCP servers (server_name -> ClientSession)",
        exclude=True  # Runtime only, not serialized
    )


__all__ = ["TestPurpleAgentContext"]
