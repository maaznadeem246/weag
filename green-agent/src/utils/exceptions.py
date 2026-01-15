"""
Structured exception classes for Green Agent.

Provides domain-specific exceptions with proper error codes and context.
Implements Structured exception classes.
"""

from typing import Any, Dict, Optional


class GreenAgentError(Exception):
    """Base exception for all Green Agent errors."""

    def __init__(self, message: str, error_code: str, details: Optional[Dict[str, Any]] = None):
        """
        Initialize error with message, code, and optional details.
        
        Args:
            message: Human-readable error message
            error_code: Machine-readable error code
            details: Optional dictionary with additional context
        """
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.details = details or {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for serialization."""
        return {
            "error": self.__class__.__name__,
            "message": self.message,
            "error_code": self.error_code,
            "details": self.details,
        }


class ConfigurationError(GreenAgentError):
    """Configuration-related errors."""

    def __init__(self, message: str, config_key: Optional[str] = None, **kwargs):
        """
        Initialize configuration error.
        
        Args:
            message: Error message
            config_key: Configuration key that caused the error
            **kwargs: Additional details
        """
        details = kwargs
        if config_key:
            details["config_key"] = config_key

        super().__init__(
            message=message,
            error_code="CONFIGURATION_ERROR",
            details=details
        )


class EvaluationError(GreenAgentError):
    """Evaluation execution errors."""

    def __init__(
        self,
        message: str,
        task_id: Optional[str] = None,
        benchmark: Optional[str] = None,
        **kwargs
    ):
        """
        Initialize evaluation error.
        
        Args:
            message: Error message
            task_id: Task ID that failed
            benchmark: Benchmark name
            **kwargs: Additional details
        """
        details = kwargs
        if task_id:
            details["task_id"] = task_id
        if benchmark:
            details["benchmark"] = benchmark

        super().__init__(
            message=message,
            error_code="EVALUATION_ERROR",
            details=details
        )


class MCPServerError(GreenAgentError):
    """MCP server lifecycle and communication errors."""

    def __init__(
        self,
        message: str,
        operation: Optional[str] = None,
        process_id: Optional[int] = None,
        **kwargs
    ):
        """
        Initialize MCP server error.
        
        Args:
            message: Error message
            operation: MCP operation that failed (spawn, health_check, etc.)
            process_id: Process ID if applicable
            **kwargs: Additional details
        """
        details = kwargs
        if operation:
            details["operation"] = operation
        if process_id:
            details["process_id"] = process_id

        super().__init__(
            message=message,
            error_code="MCP_SERVER_ERROR",
            details=details
        )


class GuardrailError(GreenAgentError):
    """Guardrail validation errors."""

    def __init__(
        self,
        message: str,
        guardrail_type: str,
        validation_result: Optional[str] = None,
        **kwargs
    ):
        """
        Initialize guardrail error.
        
        Args:
            message: Error message
            guardrail_type: Type of guardrail (input/output)
            validation_result: Validation result if available
            **kwargs: Additional details
        """
        details = kwargs
        details["guardrail_type"] = guardrail_type
        if validation_result:
            details["validation_result"] = validation_result

        super().__init__(
            message=message,
            error_code="GUARDRAIL_ERROR",
            details=details
        )


class SessionError(GreenAgentError):
    """Session management errors."""

    def __init__(
        self,
        message: str,
        session_id: Optional[str] = None,
        operation: Optional[str] = None,
        **kwargs
    ):
        """
        Initialize session error.
        
        Args:
            message: Error message
            session_id: Session ID that failed
            operation: Session operation (create, load, cleanup)
            **kwargs: Additional details
        """
        details = kwargs
        if session_id:
            details["session_id"] = session_id
        if operation:
            details["operation"] = operation

        super().__init__(
            message=message,
            error_code="SESSION_ERROR",
            details=details
        )


class A2AProtocolError(GreenAgentError):
    """A2A protocol communication errors."""

    def __init__(
        self,
        message: str,
        interaction_id: Optional[str] = None,
        message_type: Optional[str] = None,
        **kwargs
    ):
        """
        Initialize A2A protocol error.
        
        Args:
            message: Error message
            interaction_id: Interaction ID
            message_type: A2A message type
            **kwargs: Additional details
        """
        details = kwargs
        if interaction_id:
            details["interaction_id"] = interaction_id
        if message_type:
            details["message_type"] = message_type

        super().__init__(
            message=message,
            error_code="A2A_PROTOCOL_ERROR",
            details=details
        )


class BenchmarkError(GreenAgentError):
    """Benchmark-specific errors."""

    def __init__(
        self,
        message: str,
        benchmark: str,
        issue_type: Optional[str] = None,
        **kwargs
    ):
        """
        Initialize benchmark error.
        
        Args:
            message: Error message
            benchmark: Benchmark name
            issue_type: Type of issue (unsupported, dataset_missing, etc.)
            **kwargs: Additional details
        """
        details = kwargs
        details["benchmark"] = benchmark
        if issue_type:
            details["issue_type"] = issue_type

        super().__init__(
            message=message,
            error_code="BENCHMARK_ERROR",
            details=details
        )


class ResourceLimitError(GreenAgentError):
    """Resource limit exceeded errors."""

    def __init__(
        self,
        message: str,
        resource_type: str,
        limit: Optional[Any] = None,
        current: Optional[Any] = None,
        **kwargs
    ):
        """
        Initialize resource limit error.
        
        Args:
            message: Error message
            resource_type: Type of resource (memory, cpu, timeout)
            limit: Resource limit
            current: Current resource usage
            **kwargs: Additional details
        """
        details = kwargs
        details["resource_type"] = resource_type
        if limit is not None:
            details["limit"] = limit
        if current is not None:
            details["current"] = current

        super().__init__(
            message=message,
            error_code="RESOURCE_LIMIT_ERROR",
            details=details
        )


class SecurityError(GreenAgentError):
    """Security-related errors."""

    def __init__(
        self,
        message: str,
        security_issue: str,
        **kwargs
    ):
        """
        Initialize security error.
        
        Args:
            message: Error message
            security_issue: Type of security issue (rate_limit, invalid_url, etc.)
            **kwargs: Additional details
        """
        details = kwargs
        details["security_issue"] = security_issue

        super().__init__(
            message=message,
            error_code="SECURITY_ERROR",
            details=details
        )


class TimeoutError(GreenAgentError):
    """Timeout errors for async operations."""

    def __init__(
        self,
        message: str,
        operation: str,
        timeout_seconds: Optional[float] = None,
        **kwargs
    ):
        """
        Initialize timeout error.
        
        Args:
            message: Error message
            operation: Operation that timed out
            timeout_seconds: Timeout duration
            **kwargs: Additional details
        """
        details = kwargs
        details["operation"] = operation
        if timeout_seconds is not None:
            details["timeout_seconds"] = timeout_seconds

        super().__init__(
            message=message,
            error_code="TIMEOUT_ERROR",
            details=details
        )


__all__ = [
    "GreenAgentError",
    "ConfigurationError",
    "EvaluationError",
    "MCPServerError",
    "GuardrailError",
    "SessionError",
    "A2AProtocolError",
    "BenchmarkError",
    "ResourceLimitError",
    "SecurityError",
    "TimeoutError",
]
