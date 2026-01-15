"""
Secrets redaction for logging.

Prevents sensitive data (API keys, tokens, credentials) from appearing in logs.
Implements Redact secrets in logs and error messages.
"""

import logging
import re
from typing import Any, Dict, Optional


# Patterns for sensitive data
SECRET_PATTERNS = [
    # API keys and tokens
    (r"(api[_-]?key|apikey)[\"']?\s*[:=]\s*[\"']?([a-zA-Z0-9_\-]{20,})", "API_KEY"),
    (r"(token|bearer)[\"']?\s*[:=]\s*[\"']?([a-zA-Z0-9_\-\.]{20,})", "TOKEN"),
    (r"(secret|password|passwd|pwd)[\"']?\s*[:=]\s*[\"']?([^\s\"']{8,})", "SECRET"),
    
    # Authorization headers
    (r"Authorization:\s*(Bearer\s+)?([a-zA-Z0-9_\-\.]{20,})", "AUTH_TOKEN"),
    
    # Connection strings
    (r"(mysql|postgresql|mongodb|redis)://[^:]+:([^@]+)@", "DB_PASSWORD"),
    
    # AWS credentials
    (r"(aws_access_key_id|AWS_ACCESS_KEY_ID)[\"']?\s*[:=]\s*[\"']?(AKIA[A-Z0-9]{16})", "AWS_KEY"),
    (r"(aws_secret_access_key|AWS_SECRET_ACCESS_KEY)[\"']?\s*[:=]\s*[\"']?([a-zA-Z0-9/+=]{40})", "AWS_SECRET"),
    
    # Private keys
    (r"-----BEGIN (RSA |EC )?PRIVATE KEY-----[^-]+-----END", "PRIVATE_KEY"),
]


def redact_secrets(text: str) -> str:
    """
    Redact sensitive data from text.
    
    Args:
        text: Text to redact
        
    Returns:
        Redacted text with secrets replaced by placeholders
    """
    if not isinstance(text, str):
        return text
    
    redacted = text
    
    for pattern, placeholder in SECRET_PATTERNS:
        # Replace matches with placeholder
        redacted = re.sub(
            pattern,
            lambda m: m.group(0).replace(m.group(m.lastindex), f"[REDACTED_{placeholder}]"),
            redacted,
            flags=re.IGNORECASE
        )
    
    return redacted


def redact_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Redact secrets from dictionary.
    
    Args:
        data: Dictionary to redact
        
    Returns:
        Dictionary with secrets redacted
    """
    if not isinstance(data, dict):
        return data
    
    redacted = {}
    
    sensitive_keys = {
        "api_key", "apikey", "token", "bearer", "secret", "password", 
        "passwd", "pwd", "authorization", "credentials", "private_key",
        "aws_access_key_id", "aws_secret_access_key"
    }
    
    for key, value in data.items():
        # Check if key is sensitive
        if any(sensitive in key.lower() for sensitive in sensitive_keys):
            redacted[key] = "[REDACTED]"
        elif isinstance(value, str):
            redacted[key] = redact_secrets(value)
        elif isinstance(value, dict):
            redacted[key] = redact_dict(value)
        elif isinstance(value, list):
            redacted[key] = [
                redact_dict(item) if isinstance(item, dict) else redact_secrets(item) if isinstance(item, str) else item
                for item in value
            ]
        else:
            redacted[key] = value
    
    return redacted


class RedactedFormatter(logging.Formatter):
    """
    Logging formatter that redacts sensitive data.
    
    Automatically redacts secrets from log messages before output.
    """

    def format(self, record: logging.LogRecord) -> str:
        """
        Format log record with redaction.
        
        Args:
            record: Log record to format
            
        Returns:
            Formatted log message with secrets redacted
        """
        # Redact message
        if isinstance(record.msg, str):
            record.msg = redact_secrets(record.msg)
        
        # Redact args
        if record.args:
            redacted_args = tuple(
                redact_secrets(arg) if isinstance(arg, str) else arg
                for arg in record.args
            )
            record.args = redacted_args
        
        # Format with parent formatter
        formatted = super().format(record)
        
        # Final redaction pass (in case secrets in exception info)
        formatted = redact_secrets(formatted)
        
        return formatted


def setup_secure_logging(
    logger: Optional[logging.Logger] = None,
    log_level: int = logging.INFO
) -> logging.Logger:
    """
    Setup secure logging with secrets redaction.
    
    Args:
        logger: Logger to configure (None = root logger)
        log_level: Log level
        
    Returns:
        Configured logger
    """
    if logger is None:
        logger = logging.getLogger()
    
    logger.setLevel(log_level)
    
    # Remove existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # Create handler with redacted formatter
    handler = logging.StreamHandler()
    handler.setLevel(log_level)
    
    formatter = RedactedFormatter(
        fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    handler.setFormatter(formatter)
    
    logger.addHandler(handler)
    
    return logger


__all__ = [
    "redact_secrets",
    "redact_dict",
    "RedactedFormatter",
    "setup_secure_logging",
]
