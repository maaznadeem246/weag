"""Security package for Green Agent.

Note: Imports are carefully ordered to avoid circular dependencies.
The secrets_redactor module is imported first since it has no internal deps.
Other modules with potential circular deps use lazy imports.
"""

# Import secrets_redactor first - it has no internal dependencies
from src.security.secrets_redactor import (
    RedactedFormatter,
    redact_secrets,
    setup_secure_logging,
    redact_dict,
)

# Import rate_limiter - minimal dependencies  
from src.security.rate_limiter import RateLimiter, check_rate_limit


# Lazy imports for modules that may cause circular dependencies
def __getattr__(name: str):
    """Lazy import for input_validator to avoid circular imports."""
    if name in ("sanitize_task_id", "sanitize_benchmark", "sanitize_url", 
                "sanitize_config_value", "sanitize_dict", "SUPPORTED_BENCHMARKS"):
        from src.security import input_validator
        return getattr(input_validator, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Input validation (lazy loaded)
    "sanitize_task_id",
    "sanitize_benchmark",
    "sanitize_url",
    "sanitize_config_value",
    "sanitize_dict",
    "SUPPORTED_BENCHMARKS",
    # Rate limiting
    "RateLimiter",
    "check_rate_limit",
    # Secrets redaction
    "redact_secrets",
    "redact_dict",
    "RedactedFormatter",
    "setup_secure_logging",
]
