"""
Configuration settings for BrowserGym Green Agent.

Loads settings from environment variables with sensible defaults.
"""

import os
from typing import Optional


class Settings:
    """Application configuration loaded from environment variables."""
    
    def __init__(self):
        """Initialize settings from environment variables."""
        # Server configuration
        self.host: str = os.getenv("HOST", "0.0.0.0")
        self.port: int = int(os.getenv("PORT", "8080"))
        self.mcp_port: int = int(os.getenv("MCP_PORT", "8081"))
        
        # Logging
        self.log_level: str = os.getenv("LOG_LEVEL", "INFO")
        
        # Process monitoring
        self.verify_chromium_processes: bool = (
            os.getenv("VERIFY_CHROMIUM_PROCESSES", "false").lower() == "true"
        )
        
        # === Feature 004: OpenAI Agents SDK Configuration ===
        
        # LLM Provider Configuration
        # Supported providers: openai, gemini, litellm
        self.llm_provider: str = os.getenv("LLM_PROVIDER", "gemini")
        
        # Gemini API configuration (via OpenAI-compatible endpoint)
        self.gemini_api_key: Optional[str] = os.getenv("GEMINI_API_KEY")
        self.gemini_base_url: str = os.getenv(
            "GEMINI_BASE_URL",
            "https://generativelanguage.googleapis.com/v1beta/openai/"
        )
        self.gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self.gemini_temperature: float = float(os.getenv("GEMINI_TEMPERATURE", "0.1"))
        self.gemini_max_iterations: int = int(os.getenv("GEMINI_MAX_ITERATIONS", "50"))
        
        # LiteLLM/OpenRouter configuration (for flexible model access)
        self.litellm_api_key: Optional[str] = os.getenv("OPENROUTER_API_KEY")
        self.litellm_base_url: str = os.getenv(
            "LITELLM_BASE_URL",
            "https://openrouter.ai/api/v1"
        )
        self.litellm_model: str = os.getenv(
            "LITELLM_MODEL",
            "google/gemini-2.0-flash-exp:free"
        )
        
        # OpenAI configuration (optional, for direct OpenAI usage)
        self.openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o")
        self.openai_base_url: Optional[str] = os.getenv("OPENAI_BASE_URL")
        
        # Langfuse tracing configuration
        self.langfuse_public_key: Optional[str] = os.getenv("LANGFUSE_PUBLIC_KEY")
        self.langfuse_secret_key: Optional[str] = os.getenv("LANGFUSE_SECRET_KEY")
        self.langfuse_host: str = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
        self.langfuse_enabled: bool = (
            os.getenv("LANGFUSE_ENABLED", "true").lower() == "true"
        )
        self.langfuse_debug: bool = (
            os.getenv("LANGFUSE_DEBUG", "false").lower() == "true"
        )
        # Optional list of instrumentation scopes to block from Langfuse reporting
        # Example: 'a2a,a2a.server,a2a.client'
        # Note: Langfuse uses exact string matching (no wildcard/regex support)
        blocked = os.getenv("LANGFUSE_BLOCKED_INSTRUMENTATION_SCOPES", "")
        parsed = [s.strip() for s in blocked.split(",") if s.strip()]
        # If the user did not configure blocked scopes, block all known A2A SDK scopes
        if not parsed:
            # Block A2A SDK internal spans to reduce trace noise
            # Langfuse requires exact scope names (no wildcards)
            # NOTE: This only blocks A2A SDK internals, NOT your @observe decorators
            parsed = [
                "a2a",
                "a2a.server",
                "a2a.client",
                "a2a.server.events",
                "a2a.server.events.event_queue",
                "a2a.server.events.event_consumer",
                "a2a.server.request_handlers",
                "a2a.server.request_handlers.default_request_handler",
                "a2a.server.apps",
                "a2a.server.tasks",
                "a2a.client.resolver",
                "a2a.client.factory",
            ]
        self.langfuse_blocked_instrumentation_scopes = parsed
        
        # Agent session configuration
        self.use_persistent_sessions: bool = (
            os.getenv("USE_PERSISTENT_SESSIONS", "true").lower() == "true"
        )
        self.sessions_db_path: str = os.getenv(
            "SESSIONS_DB_PATH",
            "data/sessions.db"
        )
        self.session_ttl_hours: int = int(os.getenv("SESSION_TTL_HOURS", "24"))
        
        # Default evaluation configuration (FR-036)
        self.default_benchmark: str = os.getenv("DEFAULT_BENCHMARK", "miniwob")
        self.default_max_tasks: int = int(os.getenv("DEFAULT_MAX_TASKS", "5"))
        self.default_timeout: int = int(os.getenv("DEFAULT_TIMEOUT", "600"))  # seconds
        
        # Resource limits (FR-048)
        self.max_memory_mb: int = int(os.getenv("MAX_MEMORY_MB", "2048"))  # 2GB
        self.max_cpu_cores: int = int(os.getenv("MAX_CPU_CORES", "2"))
        self.max_browsers_per_eval: int = int(os.getenv("MAX_BROWSERS_PER_EVAL", "1"))
        
        # Rate limiting (FR-059)
        self.rate_limit_enabled: bool = (
            os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
        )
        self.rate_limit_requests_per_minute: int = int(
            os.getenv("RATE_LIMIT_REQUESTS_PER_MINUTE", "60")
        )
        
        # === End Feature 004 Configuration ===
        
        # Efficiency targets (constitutional mandates)
        self.token_limit_per_observation: int = 5000  # Mandate C
        self.latency_target_seconds: float = 2.0     # Mandate L
        self.memory_limit_mb: int = 500               # Mandate F
        
        # Efficiency penalty coefficients (FR-017)
        self.lambda_c: float = 0.01  # Token penalty coefficient
        self.lambda_l: float = 0.1   # Latency penalty coefficient
    
    def __repr__(self) -> str:
        """String representation (excludes sensitive data)."""
        return (
            f"Settings(host={self.host}, port={self.port}, mcp_port={self.mcp_port}, "
            f"log_level={self.log_level}, verify_chromium={self.verify_chromium_processes})"
        )


# Global settings instance
settings = Settings()
