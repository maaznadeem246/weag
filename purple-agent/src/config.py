"""
Configuration for Test Purple Agent.

Environment Variables:
- GREEN_AGENT_URL: Green agent A2A endpoint (default: http://localhost:9009)
- GEMINI_API_KEY: Gemini API key for agent LLM
- GEMINI_BASE_URL: Gemini API base URL
- LOG_LEVEL: Logging level (default: INFO)
- TIMEOUT: Default timeout for operations in seconds (default: 300)
"""

import os
from typing import Optional


class PurpleAgentConfig:
    """Configuration for test purple agent."""
    
    def __init__(self):
        """Initialize configuration from environment variables."""
        
        # Green Agent connection
        self.green_agent_url: str = os.getenv("GREEN_AGENT_URL", "http://localhost:9009")
        self.green_agent_health_endpoint: str = f"{self.green_agent_url}/health"
        self.green_agent_events_endpoint: str = f"{self.green_agent_url}/events"
        
        # Gemini API configuration
        self.gemini_api_key: Optional[str] = os.getenv("GEMINI_API_KEY")
        self.gemini_base_url: str = os.getenv(
            "GEMINI_BASE_URL",
            "https://generativelanguage.googleapis.com/v1beta/openai/"
        )
        self.gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self.gemini_temperature: float = float(os.getenv("GEMINI_TEMPERATURE", "0.3"))
        self.gemini_max_iterations: int = int(os.getenv("GEMINI_MAX_ITERATIONS", "20"))
        
        # Langfuse tracing (optional)
        self.langfuse_enabled: bool = (
            os.getenv("LANGFUSE_ENABLED", "false").lower() == "true"
        )
        self.langfuse_public_key: Optional[str] = os.getenv("LANGFUSE_PUBLIC_KEY")
        self.langfuse_secret_key: Optional[str] = os.getenv("LANGFUSE_SECRET_KEY")
        self.langfuse_host: str = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
        
        # Timeouts and retries
        self.default_timeout: int = int(os.getenv("TIMEOUT", "300"))
        self.mcp_connection_timeout: int = int(os.getenv("MCP_CONNECTION_TIMEOUT", "30"))
        self.mcp_connection_retries: int = int(os.getenv("MCP_CONNECTION_RETRIES", "3"))
        self.mcp_tool_timeout: int = int(os.getenv("MCP_TOOL_TIMEOUT", "30"))
        
        # Logging
        self.log_level: str = os.getenv("LOG_LEVEL", "INFO")
        self.log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


# Global config instance
config = PurpleAgentConfig()


__all__ = ["config", "PurpleAgentConfig"]
