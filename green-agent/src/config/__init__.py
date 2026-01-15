"""
Configuration management for Green Agent.

Provides centralized configuration with validation, defaults, and environment overrides.
Implements Configuration management with validation and documentation.
"""

import os
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, validator

from src.utils.exceptions import ConfigurationError
from src.security.input_validator import SUPPORTED_BENCHMARKS


class BrowserGymConfig(BaseModel):
    """BrowserGym environment configuration."""

    headless: bool = Field(default=True, description="Run browser in headless mode")
    viewport_width: int = Field(default=1280, ge=800, le=3840, description="Browser viewport width")
    viewport_height: int = Field(default=720, ge=600, le=2160, description="Browser viewport height")
    slow_mo: int = Field(default=0, ge=0, le=5000, description="Slow motion delay in milliseconds")
    timeout: int = Field(default=30000, ge=5000, le=300000, description="Default timeout in milliseconds")


class MCPConfig(BaseModel):
    """MCP server configuration."""

    health_check_timeout: int = Field(default=30, ge=5, le=120, description="Health check timeout in seconds")
    health_check_interval: int = Field(default=60, ge=10, le=300, description="Health check interval in seconds")
    restart_on_failure: bool = Field(default=True, description="Restart MCP server on failure")
    max_restart_attempts: int = Field(default=3, ge=1, le=10, description="Maximum restart attempts")


class SessionConfig(BaseModel):
    """Session management configuration."""

    use_persistent_sessions: bool = Field(default=False, description="Use SQLite for session persistence")
    sessions_db_path: str = Field(default="sessions.db", description="SQLite database path")
    session_ttl_hours: int = Field(default=24, ge=1, le=168, description="Session TTL in hours")
    cleanup_interval_hours: int = Field(default=6, ge=1, le=24, description="Cleanup interval in hours")


class EvaluationConfig(BaseModel):
    """Evaluation execution configuration."""

    default_benchmark: str = Field(default="miniwob", description="Default benchmark if not specified")
    default_max_tasks: int = Field(default=5, ge=1, le=100, description="Default max tasks for batch evaluation")
    default_timeout: int = Field(default=300, ge=60, le=3600, description="Default evaluation timeout in seconds")
    max_concurrent_evaluations: int = Field(default=3, ge=1, le=10, description="Maximum concurrent evaluations")
    
    @validator("default_benchmark")
    def validate_benchmark(cls, v):
        """Validate benchmark is supported."""
        if v not in SUPPORTED_BENCHMARKS:
            raise ValueError(f"Unsupported benchmark: {v}. Supported: {', '.join(SUPPORTED_BENCHMARKS)}")
        return v


class ObservabilityConfig(BaseModel):
    """Observability and monitoring configuration."""

    enable_langfuse: bool = Field(default=True, description="Enable Langfuse tracing")
    langfuse_public_key: Optional[str] = Field(default=None, description="Langfuse public key")
    langfuse_secret_key: Optional[str] = Field(default=None, description="Langfuse secret key")
    langfuse_host: str = Field(default="https://cloud.langfuse.com", description="Langfuse host URL")
    
    log_level: str = Field(default="INFO", description="Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)")
    json_logs: bool = Field(default=True, description="Use JSON-formatted logs")
    
    enable_metrics: bool = Field(default=True, description="Enable Prometheus metrics")
    metrics_port: int = Field(default=9090, ge=1024, le=65535, description="Metrics server port")


class SecurityConfig(BaseModel):
    """Security configuration."""

    enable_rate_limiting: bool = Field(default=True, description="Enable rate limiting")
    rate_limit_requests_per_minute: int = Field(default=60, ge=1, le=1000, description="Rate limit per minute")
    
    enable_input_validation: bool = Field(default=True, description="Enable input validation")
    allow_private_urls: bool = Field(default=False, description="Allow private IP addresses in URLs")
    
    enable_secrets_redaction: bool = Field(default=True, description="Enable secrets redaction in logs")


class GreenAgentConfig(BaseModel):
    """
    Complete Green Agent configuration.
    
    Centralizes all configuration with validation, defaults, and environment overrides.
    """

    # Server configuration
    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=9009, ge=1024, le=65535, description="Server port")
    
    # Component configurations
    browsergym: BrowserGymConfig = Field(default_factory=BrowserGymConfig)
    mcp: MCPConfig = Field(default_factory=MCPConfig)
    session: SessionConfig = Field(default_factory=SessionConfig)
    evaluation: EvaluationConfig = Field(default_factory=EvaluationConfig)
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    
    # Agent identity
    agent_name: str = Field(default="BrowserGym Green Agent", description="Agent name")
    agent_version: str = Field(default="1.0.0", description="Agent version")
    
    # Supported benchmarks
    supported_benchmarks: List[str] = Field(default_factory=lambda: list(SUPPORTED_BENCHMARKS))

    class Config:
        """Pydantic configuration."""
        validate_assignment = True

    @classmethod
    def from_env(cls, env_prefix: str = "GREEN_AGENT_") -> "GreenAgentConfig":
        """
        Load configuration from environment variables.
        
        Environment variables:
        - GREEN_AGENT_HOST: Server host (default: 0.0.0.0)
        - GREEN_AGENT_PORT: Server port (default: 9009)
        - GREEN_AGENT_LOG_LEVEL: Log level (default: INFO)
        - GREEN_AGENT_DEFAULT_BENCHMARK: Default benchmark (default: miniwob)
        - GREEN_AGENT_DEFAULT_MAX_TASKS: Default max tasks (default: 5)
        - GREEN_AGENT_DEFAULT_TIMEOUT: Default timeout (default: 300)
        - GREEN_AGENT_ENABLE_LANGFUSE: Enable Langfuse (default: true)
        - GREEN_AGENT_LANGFUSE_PUBLIC_KEY: Langfuse public key
        - GREEN_AGENT_LANGFUSE_SECRET_KEY: Langfuse secret key
        - GREEN_AGENT_USE_PERSISTENT_SESSIONS: Use persistent sessions (default: false)
        - GREEN_AGENT_SESSIONS_DB_PATH: Sessions DB path (default: sessions.db)
        
        Args:
            env_prefix: Environment variable prefix
            
        Returns:
            Configuration instance
        """
        config_dict: Dict[str, Any] = {}
        
        # Server configuration
        if host := os.getenv(f"{env_prefix}HOST"):
            config_dict["host"] = host
        if port := os.getenv(f"{env_prefix}PORT"):
            config_dict["port"] = int(port)
        
        # Agent identity
        if name := os.getenv(f"{env_prefix}AGENT_NAME"):
            config_dict["agent_name"] = name
        if version := os.getenv(f"{env_prefix}AGENT_VERSION"):
            config_dict["agent_version"] = version
        
        # Evaluation configuration
        evaluation_dict = {}
        if benchmark := os.getenv(f"{env_prefix}DEFAULT_BENCHMARK"):
            evaluation_dict["default_benchmark"] = benchmark
        if max_tasks := os.getenv(f"{env_prefix}DEFAULT_MAX_TASKS"):
            evaluation_dict["default_max_tasks"] = int(max_tasks)
        if timeout := os.getenv(f"{env_prefix}DEFAULT_TIMEOUT"):
            evaluation_dict["default_timeout"] = int(timeout)
        if evaluation_dict:
            config_dict["evaluation"] = evaluation_dict
        
        # Observability configuration
        observability_dict = {}
        if log_level := os.getenv(f"{env_prefix}LOG_LEVEL"):
            observability_dict["log_level"] = log_level
        if enable_langfuse := os.getenv(f"{env_prefix}ENABLE_LANGFUSE"):
            observability_dict["enable_langfuse"] = enable_langfuse.lower() == "true"
        if langfuse_key := os.getenv(f"{env_prefix}LANGFUSE_PUBLIC_KEY"):
            observability_dict["langfuse_public_key"] = langfuse_key
        if langfuse_secret := os.getenv(f"{env_prefix}LANGFUSE_SECRET_KEY"):
            observability_dict["langfuse_secret_key"] = langfuse_secret
        if observability_dict:
            config_dict["observability"] = observability_dict
        
        # Session configuration
        session_dict = {}
        if use_persistent := os.getenv(f"{env_prefix}USE_PERSISTENT_SESSIONS"):
            session_dict["use_persistent_sessions"] = use_persistent.lower() == "true"
        if db_path := os.getenv(f"{env_prefix}SESSIONS_DB_PATH"):
            session_dict["sessions_db_path"] = db_path
        if session_dict:
            config_dict["session"] = session_dict
        
        # Security configuration
        security_dict = {}
        if enable_rate_limit := os.getenv(f"{env_prefix}ENABLE_RATE_LIMITING"):
            security_dict["enable_rate_limiting"] = enable_rate_limit.lower() == "true"
        if allow_private_urls := os.getenv(f"{env_prefix}ALLOW_PRIVATE_URLS"):
            security_dict["allow_private_urls"] = allow_private_urls.lower() == "true"
        if security_dict:
            config_dict["security"] = security_dict
        
        try:
            return cls(**config_dict)
        except Exception as e:
            raise ConfigurationError(
                f"Failed to load configuration from environment: {e}",
                config_key="environment"
            )

    def validate_config(self) -> None:
        """
        Validate configuration consistency.
        
        Raises:
            ConfigurationError: If configuration is invalid
        """
        # Validate Langfuse configuration
        if self.observability.enable_langfuse:
            if not self.observability.langfuse_public_key:
                raise ConfigurationError(
                    "Langfuse enabled but LANGFUSE_PUBLIC_KEY not set",
                    config_key="observability.langfuse_public_key"
                )
            if not self.observability.langfuse_secret_key:
                raise ConfigurationError(
                    "Langfuse enabled but LANGFUSE_SECRET_KEY not set",
                    config_key="observability.langfuse_secret_key"
                )
        
        # Validate persistent sessions
        if self.session.use_persistent_sessions:
            if not self.session.sessions_db_path:
                raise ConfigurationError(
                    "Persistent sessions enabled but sessions_db_path not set",
                    config_key="session.sessions_db_path"
                )

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert configuration to dictionary.
        
        Returns:
            Configuration as dictionary
        """
        return self.dict()


# Global configuration instance
_config: Optional[GreenAgentConfig] = None


def get_config() -> GreenAgentConfig:
    """
    Get global configuration instance.
    
    Returns:
        Configuration instance
    """
    global _config
    if _config is None:
        _config = GreenAgentConfig.from_env()
        _config.validate_config()
    return _config


def set_config(config: GreenAgentConfig) -> None:
    """
    Set global configuration instance.
    
    Args:
        config: Configuration to set
    """
    global _config
    config.validate_config()
    _config = config


def reset_config() -> None:
    """Reset global configuration to None."""
    global _config
    _config = None


__all__ = [
    "GreenAgentConfig",
    "BrowserGymConfig",
    "MCPConfig",
    "SessionConfig",
    "EvaluationConfig",
    "ObservabilityConfig",
    "SecurityConfig",
    "get_config",
    "set_config",
    "reset_config",
]
