"""
Pydantic models for A2A protocol and evaluation sessions.
Based on AgentBeats tutorial patterns.
"""

from typing import Any, Optional
from datetime import datetime, timezone
from enum import Enum
from pydantic import BaseModel, HttpUrl, Field


def utcnow() -> datetime:
    """Helper to get current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)


class EvaluationStatus(str, Enum):
    """Status of an evaluation session."""
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class EvalRequest(BaseModel):
    """
    A2A assessment request structure.
    Received from AgentBeats platform.
    """
    participants: dict[str, HttpUrl] = Field(
        description="Mapping of role names to A2A endpoint URLs"
    )
    config: dict[str, Any] = Field(
        description="Assessment-specific configuration (task_id, max_steps, seed, etc.)"
    )


class EvaluationSession(BaseModel):
    """
    Represents a complete A2A assessment task with a purple agent.
    Tracks MCP subprocess, status, and final results.
    """
    task_id: str = Field(description="Unique task identifier for this evaluation")
    session_id: str = Field(default="", description="Session ID for shared state communication")
    purple_agent_endpoint: str = Field(description="Purple agent A2A endpoint URL")
    mcp_process: Optional[Any] = Field(
        default=None, 
        description="asyncio subprocess handle for MCP server"
    )
    status: EvaluationStatus = Field(
        default=EvaluationStatus.CREATED,
        description="Current status of the evaluation"
    )
    created_at: datetime = Field(default_factory=utcnow)
    completed_at: Optional[datetime] = None
    final_artifact: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    
    class Config:
        arbitrary_types_allowed = True  # Allow asyncio.subprocess.Process
        use_enum_values = True


class MCPConnectionDetails(BaseModel):
    """
    MCP server connection details returned to purple agent.
    
    Supports both HTTP and stdio transports:
    - HTTP: Modern approach, one server handles all connections via HTTP
    - stdio: Legacy subprocess pattern (deprecated)
    """
    # HTTP transport fields (new)
    url: str | None = Field(default=None, description="HTTP URL for MCP server (e.g., http://localhost:8001/mcp)")
    transport: str = Field(default="http", description="Transport protocol (http or stdio)")
    
    # stdio transport fields (deprecated, kept for backwards compatibility)
    command: str | None = Field(default=None, description="[Deprecated] Python command to execute for stdio")
    args: list[str] | None = Field(default=None, description="[Deprecated] Arguments for MCP server subprocess")
    env: dict[str, str] | None = Field(default=None, description="[Deprecated] Environment variables to set when spawning MCP subprocess")
    
    # Common fields
    session_id: str = Field(default="", description="Unique evaluation session identifier")
    tools_details: list[Any] = Field(
        default_factory=list,
        description="List of ToolMetadata objects with complete documentation for all available MCP tools"
    )


class EvaluationArtifact(BaseModel):
    """
    Final evaluation results artifact.
    Returned via A2A protocol at assessment completion.
    """
    task_success: bool = Field(description="Whether the task was completed successfully")
    task_id: str = Field(description="BrowserGym task identifier")
    benchmark: str = Field(description="Benchmark name (miniwob, webarena, etc.)")
    
    # Efficiency metrics (Constitutional Mandates C/L/F)
    total_tokens: int = Field(description="Total tokens across all observations (Mandate C)")
    total_latency_ms: int = Field(description="Total MCP tool invocation latency (Mandate L)")
    peak_memory_mb: int = Field(description="Peak memory usage (Mandate F)")
    chromium_process_count: int = Field(description="Orphaned processes at cleanup (Mandate F)")
    
    # Calculated scores
    efficiency_penalty: float = Field(description="Penalty score: 1 - 0.01*log(C) - 0.1*L")
    final_score: float = Field(description="task_success × efficiency_penalty")
    
    # Additional context
    mcp_tool_invocations: int = Field(description="Total MCP tool calls")
    observation_count: int = Field(description="Number of observations retrieved")
    action_count: int = Field(description="Number of actions executed")
    evaluation_duration_seconds: float = Field(description="Total evaluation time")
    
    # A2A metadata (required by output guardrails)
    metadata: dict[str, str] = Field(
        default_factory=dict,
        description="A2A metadata with session_id and timestamp"
    )
    
    error_message: Optional[str] = Field(
        default=None,
        description="Error message if evaluation failed"
    )
