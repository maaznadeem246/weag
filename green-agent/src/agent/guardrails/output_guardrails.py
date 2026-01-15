"""
Output guardrails for evaluation artifact validation.

Implements Artifact validation guardrail ensuring quality standards
and required metrics before emission.
"""

from typing import Any

from langfuse import observe
from agents import Agent, output_guardrail
from agents.guardrail import GuardrailFunctionOutput

from src.agent.guardrails import ValidationResult
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Artifact validation instructions for guardrail agent
ARTIFACT_VALIDATION_INSTRUCTIONS = """You are an artifact validation agent for BrowserGym evaluations.

Your role is to validate evaluation artifacts before emission and ensure they meet quality standards.

Required Fields (CHK005, CHK042):
1. **task_success**: Boolean indicating task completion
2. **final_score**: Numeric score (0.0-1.0 typical range)
3. **token_cost**: Total token count for evaluation
4. **latency**: Total evaluation time in seconds
5. **step_count**: Number of steps/actions taken
6. **task_id**: Original task identifier
7. **benchmark**: Benchmark name

A2A Schema Compliance (CHK004, CHK005):
- Must be valid JSON structure
- Must include metadata section with session_id, timestamp
- Can include freeform result data

Quality Checks:
- Numeric fields must be valid numbers (not NaN, not negative)
- Boolean fields must be true/false
- String fields must not be empty
- Efficiency metrics must be reasonable (token_cost < 1M, latency < 1 hour)

If validation passes, return:
- is_valid: true
- violations: []
- message: "Artifact validation passed"

If validation fails, return:
- is_valid: false
- violations: ["specific issue 1", "specific issue 2", ...]
- message: "Artifact validation failed: <summary>"

Be specific about violations. Include the field name and issue.
"""


def create_artifact_validation_agent() -> Agent[Any]:
    """
    Create guardrail agent for artifact validation.
    
    Implements Artifact validation agent with validation instructions.
    
    Returns:
        Agent configured for artifact validation with ValidationResult output
    """
    return Agent[Any](
        name="ArtifactValidator",
        instructions=ARTIFACT_VALIDATION_INSTRUCTIONS,
        model="gemini-2.5-flash",
        temperature=0.0,  # Deterministic validation
        max_iterations=5,  # Simple validation task
    )


# Global validation agent instance
_artifact_validation_agent: Agent[Any] | None = None


def get_artifact_validation_agent() -> Agent[Any]:
    """Get or create artifact validation agent."""
    global _artifact_validation_agent
    if _artifact_validation_agent is None:
        _artifact_validation_agent = create_artifact_validation_agent()
    return _artifact_validation_agent


def _validate_artifact_inner(artifact: dict) -> ValidationResult:
    """
    Simplified artifact validation for A2A protocol compliance.
    
    WHY THIS EXISTS:
    - AgentBeats A2A protocol requires specific fields in evaluation artifacts
    - OpenAI Agents SDK output guardrails catch errors BEFORE emission
    - Ensures evaluation results are properly structured for scoring
    
    WHAT IT CHECKS:
    - Basic required fields: task_id, task_success, final_score
    - A2A compliance: metadata with session_id and timestamp
    
    This is a WARNING-ONLY guardrail (non-blocking) to help debug issues.
    
    Args:
        artifact: Parsed artifact dict
        
    Returns:
        ValidationResult with validation outcome
    """
    violations: list[str] = []

    # Only check absolutely required fields for A2A protocol
    if "task_id" not in artifact:
        violations.append("Missing required field: 'task_id'")
    
    if "task_success" not in artifact:
        violations.append("Missing required field: 'task_success'")
    
    if "final_score" not in artifact:
        violations.append("Missing required field: 'final_score'")
    
    # A2A metadata requirement (simplified check)
    metadata = artifact.get("metadata")
    if not metadata or not isinstance(metadata, dict):
        violations.append("Missing required field: 'metadata'")
    elif "session_id" not in metadata or "timestamp" not in metadata:
        violations.append("metadata must have 'session_id' and 'timestamp'")

    if violations:
        return ValidationResult(
            is_valid=False, 
            violations=violations, 
            message=f"Artifact validation failed: {'; '.join(violations[:2])}", 
            error='; '.join(violations)
        )

    return ValidationResult(is_valid=True, violations=[], message="Artifact validation passed", error=None)


def validate_evaluation_artifact(run_ctx, artifact: dict) -> ValidationResult:
    """Plain callable artifact validation for tests and direct invocation.

    Expects the artifact as a dict. Returns a `ValidationResult`.
    """
    try:
        # If a run_ctx wrapper is provided but artifact is None, support signature
        # where caller passes (run_ctx, artifact)
        return _validate_artifact_inner(artifact)
    except Exception as e:
        logger.exception("validate_evaluation_artifact failed")
        return ValidationResult(is_valid=False, violations=[str(e)], message=f"Guardrail error: {e}", error=str(e))


@output_guardrail
@observe(as_type="guardrail")
async def validate_evaluation_artifact_guardrail(*args, **kwargs) -> GuardrailFunctionOutput:
    """Decorated guardrail wrapper used by the Agents SDK at runtime.

    Accepts runtime calling conventions and returns a GuardrailFunctionOutput.
    """
    import json

    # Attempt to extract the artifact from kwargs or positional args
    artifact_obj = None
    if "artifact" in kwargs:
        artifact_obj = kwargs.get("artifact")
    elif "agent_output" in kwargs:
        artifact_obj = kwargs.get("agent_output")
    elif len(args) >= 2:
        # common runtime pattern: (agent, agent_output, context)
        artifact_obj = args[1]
    elif len(args) == 1:
        artifact_obj = args[0]

    try:
        if isinstance(artifact_obj, str):
            artifact = json.loads(artifact_obj)
        elif isinstance(artifact_obj, dict):
            artifact = artifact_obj
        else:
            # try to coerce from several common shapes:
            # 1) JSON string via str()
            # 2) pydantic / model_dump/dict
            # 3) object's __dict__
            # 4) Agent-like wrappers (try common attributes)
            artifact = None
            try:
                artifact = json.loads(str(artifact_obj))
            except Exception:
                pass

            if artifact is None:
                # pydantic-style
                try:
                    if hasattr(artifact_obj, "model_dump"):
                        artifact = artifact_obj.model_dump()
                    elif hasattr(artifact_obj, "dict") and callable(getattr(artifact_obj, "dict")):
                        artifact = artifact_obj.dict()
                except Exception:
                    artifact = None

            if artifact is None:
                # Attempt Agent-like extraction: common attributes that may carry the artifact
                try:
                    # prefer explicit 'output' or 'agent_output' or 'last_output' if present
                    for candidate in ("output", "agent_output", "last_output", "last_response", "result"):
                        if hasattr(artifact_obj, candidate):
                            candidate_val = getattr(artifact_obj, candidate)
                            try:
                                artifact = json.loads(str(candidate_val)) if isinstance(candidate_val, str) else (candidate_val if isinstance(candidate_val, dict) else None)
                                if artifact is not None:
                                    break
                            except Exception:
                                try:
                                    if hasattr(candidate_val, "model_dump"):
                                        artifact = candidate_val.model_dump()
                                        break
                                    if hasattr(candidate_val, "dict"):
                                        artifact = candidate_val.dict()
                                        break
                                except Exception:
                                    pass
                except Exception:
                    artifact = None

            if artifact is None:
                # Fallback to object's __dict__ if available
                try:
                    obj_dict = getattr(artifact_obj, "__dict__", None)
                    if isinstance(obj_dict, dict) and obj_dict:
                        artifact = dict(obj_dict)
                    else:
                        artifact = {}
                except Exception:
                    artifact = {}

        validation = _validate_artifact_inner(artifact)
        # Log at DEBUG level for intermediate outputs, only warn on final artifact emission
        # This prevents log spam from non-artifact agent outputs
        if not validation.is_valid:
            logger.debug("Artifact validation check (non-tripwire): %s", validation.violations)
        return GuardrailFunctionOutput(output_info=validation, tripwire_triggered=False)
    except json.JSONDecodeError as e:
        logger.error("Artifact JSON parse failed", exc_info=True)
        return GuardrailFunctionOutput(output_info=ValidationResult(is_valid=False, violations=[f"Invalid JSON: {e}"], message="Artifact validation failed: Invalid JSON"), tripwire_triggered=False)
    except Exception as e:
        logger.exception("Output guardrail failed")
        return GuardrailFunctionOutput(output_info=ValidationResult(is_valid=False, violations=[str(e)], message=f"Guardrail error: {e}"), tripwire_triggered=False)


__all__ = [
    "validate_evaluation_artifact",
    "create_artifact_validation_agent",
]

# Also expose the decorated guardrail object separately for runtime use
__all__.extend(["validate_evaluation_artifact_guardrail"])
