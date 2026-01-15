"""
Input guardrails for evaluation request validation.

Implements Request validation guardrail with benchmark validation,
format checking, and resource availability verification.
"""

from typing import Any

from langfuse import observe
from agents import Agent, input_guardrail
from agents.guardrail import GuardrailFunctionOutput

from src.agent.guardrails import ValidationResult
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Supported BrowserGym benchmarks (FR-024)
SUPPORTED_BENCHMARKS = [
    "miniwob",
    "webarena",
    "visualwebarena",
    "workarena",
    "assistantbench",
    "weblinx",
]

# Request validation instructions for guardrail agent
REQUEST_VALIDATION_INSTRUCTIONS = """You are a request validation agent for BrowserGym evaluations.

Your role is to validate evaluation requests and ensure they meet all requirements before processing.

Validation Checks:
1. **Benchmark Validation**: Check benchmark name is in supported list: {supported_benchmarks}
2. **Task ID Format**: Verify task_id follows format: {{benchmark}}.{{task_name}} (lowercase, hyphen-separated)
3. **Timeout Range**: Ensure timeout is positive integer (recommended: 60-1800 seconds)
4. **Resource Availability**: Check if max_tasks is reasonable (1-100 recommended)
5. **Configuration Completeness**: Verify all required fields are present

If validation passes, return:
- is_valid: true
- violations: []
- message: "Request validation passed"

If validation fails, return:
- is_valid: false
- violations: ["specific issue 1", "specific issue 2", ...]
- message: "Request validation failed: <summary>"

Be specific about violations. Include the actual value and expected format/range.
"""


def create_request_validation_agent() -> Agent[Any]:
    """
    Create guardrail agent for request validation.
    
    Implements Request validation agent with validation instructions.
    
    Returns:
        Agent configured for request validation with ValidationResult output
    """
    return Agent[Any](
        name="RequestValidator",
        instructions=REQUEST_VALIDATION_INSTRUCTIONS.format(
            supported_benchmarks=", ".join(SUPPORTED_BENCHMARKS)
        ),
        model="gemini-2.5-flash",
        temperature=0.0,  # Deterministic validation
        max_iterations=5,  # Simple validation task
    )


# Global validation agent instance
_validation_agent: Agent[Any] | None = None


def get_validation_agent() -> Agent[Any]:
    """Get or create request validation agent."""
    global _validation_agent
    if _validation_agent is None:
        _validation_agent = create_request_validation_agent()
    return _validation_agent

    # """
    # Input guardrail that validates evaluation requests before processing.
    
    # Implements Input guardrail with validation logic and Langfuse tracing.
    
    # Validation Rules (CHK001-CHK006):
    # - Benchmark must be in SUPPORTED_BENCHMARKS
    # - task_id must follow {benchmark}.{task_name} format
    # - timeout must be positive integer
    # - max_tasks must be reasonable (1-100)
    # - All required configuration fields present
    
    # Args:
    #     user_input: Evaluation request as string (JSON or natural language)
        
    # Returns:
    #     ValidationResult with is_valid flag and violations list
        
    # Raises:
    #     Exception: If validation fails (tripwire pattern per FR-006)
        
    # Example:
    #     # Valid request passes through
    #     result = await validate_evaluation_request('{"benchmark": "miniwob", "task_id": "miniwob.click-test"}')
        
    #     # Invalid request raises exception
    #     result = await validate_evaluation_request('{"benchmark": "invalid", ...}')
    #     # Raises: Exception("Request validation failed: Invalid benchmark name")
    # """


def _validate_request_inner(context_data: dict) -> ValidationResult:
    """
    Inner validation function (testable without decorators).
    
    Args:
        context_data: Dict with benchmark, task_id, timeout, etc.
        
    Returns:
        ValidationResult with validation outcome
    """
    violations: list[str] = []

    benchmark = context_data.get("benchmark")
    task_id = context_data.get("task_id")
    timeout = context_data.get("timeout")
    batch_cfg = context_data.get("batch_evaluation_config") or context_data.get("batch_config")

    logger.info("Validating request", extra={"benchmark": benchmark, "task_id": task_id})

    # Normalize placeholder values used for initial readiness messages
    if isinstance(benchmark, str) and benchmark.strip().lower() == "unknown":
        benchmark = None

    # If both benchmark and task_id are missing, treat this as a lightweight
    # readiness / handshake message and skip strict validation to avoid
    # triggering the tripwire on initial contact.
    if not benchmark and not task_id:
        return ValidationResult(is_valid=True, violations=[], message="Readiness message: validation bypassed", error=None)

    # Multi-task orchestration mode: allow "multi" as benchmark
    if benchmark == "multi" or task_id == "multi-task-orchestration":
        return ValidationResult(is_valid=True, violations=[], message="Multi-task orchestration: validation bypassed", error=None)

    # If benchmark is missing but task_id is present as a plain UUID (no dot),
    # treat this as a lightweight readiness/handshake message from Purple
    # (some purple clients send a UUID-only temporary id). Bypass strict
    # validation in that case to avoid false-positive tripwires.
    if not benchmark and task_id and "." not in task_id:
        try:
            from uuid import UUID

            UUID(task_id)
            return ValidationResult(is_valid=True, violations=[], message="Readiness message (UUID task_id): validation bypassed", error=None)
        except Exception:
            # Not a UUID - fall through to normal validation
            pass

    # Benchmark supported
    if benchmark and benchmark not in SUPPORTED_BENCHMARKS:
        violations.append(f"Benchmark '{benchmark}' not supported; expected one of: {', '.join(SUPPORTED_BENCHMARKS)}")

    # task_id format and prefix
    if task_id:
        if "." not in task_id:
            violations.append("task_id format invalid: expected '{benchmark}.{task_name}'")
        else:
            prefix = task_id.split(".", 1)[0]
            if benchmark and prefix != benchmark:
                violations.append("task_id benchmark mismatch with provided benchmark")

    # Timeout checks (None means default -> OK)
    if timeout is not None:
        try:
            t = int(timeout)
            if t < 1 or t > 3600:
                violations.append("timeout must be between 1 and 3600 seconds")
        except Exception:
            violations.append("timeout must be an integer number of seconds")

    # Batch config validation
    if batch_cfg:
        try:
            benchmarks = getattr(batch_cfg, "benchmarks", None) or batch_cfg.get("benchmarks")
            if benchmarks:
                for b in benchmarks:
                    # b may be a pydantic model or dict
                    name = getattr(b, "benchmark", None) or getattr(b, "benchmark_name", None) or (b.get("benchmark") if isinstance(b, dict) else None)
                    max_tasks = getattr(b, "max_tasks", None) or (b.get("max_tasks") if isinstance(b, dict) else None)
                    if name and name not in SUPPORTED_BENCHMARKS:
                        violations.append(f"Batch config contains unsupported benchmark: {name}")
                    if max_tasks is not None and int(max_tasks) > 100:
                        violations.append("max_tasks exceeds limit of 100")
        except Exception:
            violations.append("Invalid batch_evaluation_config format")

    if violations:
        return ValidationResult(is_valid=False, violations=violations, message=f"Request validation failed: {'; '.join(violations[:3])}", error='; '.join(violations))

    return ValidationResult(is_valid=True, violations=[], message="Request validation passed", error=None)


def validate_evaluation_request(run_ctx) -> ValidationResult:
    """Plain callable validation for tests and direct invocation.

    Expects a RunContextWrapper-like object with `.context` property (the
    `AgentContext`), or a dict-like object. Returns a `ValidationResult`.
    """
    try:
        # Extract context data
        if hasattr(run_ctx, "context"):
            ctx = run_ctx.context
        elif isinstance(run_ctx, dict) and "context" in run_ctx:
            ctx = run_ctx["context"]
        else:
            ctx = run_ctx

        context_data = {
            "benchmark": getattr(ctx, "benchmark", None),
            "task_id": getattr(ctx, "task_id", None),
            "timeout": getattr(ctx, "timeout", None),
            "batch_evaluation_config": getattr(ctx, "batch_evaluation_config", None) or getattr(ctx, "batch_config", None),
        }

        return _validate_request_inner(context_data)
    except Exception as e:
        logger.exception("validate_evaluation_request failed")
        return ValidationResult(is_valid=False, violations=[str(e)], message=f"Guardrail error: {e}", error=str(e))


@input_guardrail
@observe(as_type="guardrail")
def validate_evaluation_request_guardrail(*args, **kwargs) -> GuardrailFunctionOutput:
    """Decorated guardrail wrapper used by the Agents SDK at runtime.

    This adapts runtime calling conventions and returns a GuardrailFunctionOutput.
    """
    logger.info("Input guardrail invoked")
    try:
        # Attempt to extract context from args/kwargs similar to tests adaptation
        run_ctx = None
        if args:
            run_ctx = args[0]
        elif "context" in kwargs:
            run_ctx = kwargs.get("context")

        result = validate_evaluation_request(run_ctx)
        return GuardrailFunctionOutput(output_info=result, tripwire_triggered=not result.is_valid)
    except Exception as e:
        logger.exception("Input guardrail failed")
        return GuardrailFunctionOutput(output_info=ValidationResult(is_valid=False, violations=[str(e)], message=f"Guardrail error: {e}"), tripwire_triggered=True)


__all__ = [
    "validate_evaluation_request",
    "SUPPORTED_BENCHMARKS",
    "create_request_validation_agent",
]
__all__.extend(["validate_evaluation_request_guardrail"])
