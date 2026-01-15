"""Agent guardrails for input/output validation."""

from pydantic import BaseModel


class ValidationResult(BaseModel):
    """Validation result from guardrail agents."""
    
    is_valid: bool
    violations: list[str] = []
    message: str = ""
    # Compatibility with Agents SDK guardrail expectations
    tripwire_triggered: bool = False
    # Optional error field used by some unit tests/logging
    error: str | None = None


__all__ = ["ValidationResult"]
