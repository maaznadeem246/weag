"""
Structured logging configuration for Green Agent.

Provides centralized logging with JSON format, correlation IDs, and secrets redaction.
Implements Structured logging with correlation IDs.
"""

import json
import logging
import sys
from datetime import datetime
from typing import Any, Dict, Optional

from src.security.secrets_redactor import redact_dict


class StructuredFormatter(logging.Formatter):
    """
    JSON formatter for structured logging.
    
    Outputs logs in JSON format with standard fields:
    - timestamp: ISO 8601 timestamp
    - level: Log level (INFO, ERROR, etc.)
    - logger: Logger name
    - message: Log message
    - correlation_id: Request correlation ID
    - extra: Additional context fields
    """

    def format(self, record: logging.LogRecord) -> str:
        """
        Format log record as JSON.
        
        Args:
            record: Log record
            
        Returns:
            JSON-formatted log entry
        """
        log_data: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add correlation ID if present
        if hasattr(record, "correlation_id"):
            log_data["correlation_id"] = record.correlation_id

        # Add extra fields
        if hasattr(record, "extra"):
            log_data["extra"] = record.extra

        # Add exception info
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Redact secrets
        log_data = redact_dict(log_data)

        return json.dumps(log_data)


class CorrelationFilter(logging.Filter):
    """
    Filter that adds correlation ID to log records.
    
    Retrieves correlation ID from context (e.g., asyncio context vars).
    """

    def __init__(self, get_correlation_id_func=None):
        """
        Initialize correlation filter.
        
        Args:
            get_correlation_id_func: Function to get correlation ID (optional)
        """
        super().__init__()
        self.get_correlation_id = get_correlation_id_func

    def filter(self, record: logging.LogRecord) -> bool:
        """
        Add correlation ID to log record.
        
        Args:
            record: Log record
            
        Returns:
            True (always passes)
        """
        if self.get_correlation_id:
            try:
                correlation_id = self.get_correlation_id()
                if correlation_id:
                    record.correlation_id = correlation_id
            except Exception:
                pass  # Ignore errors getting correlation ID

        return True


def setup_logging(
    log_level: str = "INFO",
    json_format: bool = True,
    correlation_id_func=None
) -> logging.Logger:
    """
    Setup structured logging for Green Agent.
    
    Args:
        log_level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_format: Use JSON format (True) or plain text (False)
        correlation_id_func: Function to get correlation ID
        
    Returns:
        Configured root logger
    """
    # Get root logger
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, log_level.upper()))

    # Remove existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, log_level.upper()))

    # Set formatter
    if json_format:
        formatter = StructuredFormatter()
    else:
        formatter = logging.Formatter(
            fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

    console_handler.setFormatter(formatter)

    # Add correlation filter
    if correlation_id_func:
        correlation_filter = CorrelationFilter(correlation_id_func)
        console_handler.addFilter(correlation_filter)

    logger.addHandler(console_handler)

    # Add file handler to logs/green_agent.log (in green-agent/logs/)
    try:
        from pathlib import Path
        logs_dir = Path("logs")
        logs_dir.mkdir(exist_ok=True)
        
        file_handler = logging.FileHandler(logs_dir / "green_agent.log", encoding="utf-8")
        file_handler.setLevel(getattr(logging, log_level.upper()))
        file_handler.setFormatter(formatter)
        
        if correlation_id_func:
            file_handler.addFilter(correlation_filter)
        
        logger.addHandler(file_handler)
    except Exception as e:
        # Don't fail if file logging setup fails
        logger.warning(f"Failed to setup file logging: {e}")

    return logger


def log_with_context(
    logger: logging.Logger,
    level: str,
    message: str,
    correlation_id: Optional[str] = None,
    **extra_fields
) -> None:
    """
    Log message with context fields.
    
    Args:
        logger: Logger instance
        level: Log level (debug, info, warning, error, critical)
        message: Log message
        correlation_id: Correlation ID
        **extra_fields: Additional context fields
    """
    # Create log record
    log_method = getattr(logger, level.lower())

    # Add extra fields as LogRecord attributes
    extra = {}
    if correlation_id:
        extra["correlation_id"] = correlation_id
    if extra_fields:
        extra["extra"] = extra_fields

    log_method(message, extra=extra)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance with the given name.
    
    Args:
        name: Logger name (typically __name__)
        
    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)


__all__ = [
    "StructuredFormatter",
    "CorrelationFilter",
    "setup_logging",
    "log_with_context",
    "get_logger",
]
