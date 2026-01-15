"""
Request validation helpers for Green Agent.

Extracted from main.py to improve modularity and testability.
"""

from typing import Tuple

from src.utils.models import EvalRequest
from src.benchmarks import validate_assessment_config
from src.utils.logging import get_logger


logger = get_logger(__name__)


def validate_required_roles(
    participants: dict,
    required_roles: list[str]
) -> Tuple[bool, str]:
    """
    Validate that all required participant roles are present.
    
    Args:
        participants: Dict of role -> endpoint mappings
        required_roles: List of required role names
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    missing_roles = set(required_roles) - set(participants.keys())
    if missing_roles:
        return False, f"Missing required roles: {missing_roles}"
    return True, ""


def validate_single_task_config(config: dict, required_keys: list[str]) -> Tuple[bool, str]:
    """
    Validate single-task mode configuration.
    
    Args:
        config: Configuration dict
        required_keys: Required configuration keys
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    missing_config = set(required_keys) - set(config.keys())
    if missing_config:
        return False, f"Missing required config keys: {missing_config}"
    
    task_id = config.get("task_id")
    if not task_id or "." not in str(task_id):
        return False, "task_id must be in format 'benchmark.task' (e.g., 'miniwob.click-test')"
    
    return True, ""


def validate_multi_task_config(config: dict) -> Tuple[bool, str]:
    """
    Validate multi-task mode configuration.
    
    Args:
        config: Configuration dict
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    tasks_by_benchmark = config.get("tasks_by_benchmark")
    
    # If no tasks_by_benchmark provided, will auto-discover
    if not isinstance(tasks_by_benchmark, dict) or not tasks_by_benchmark:
        return True, ""
    
    # Validate at least one valid task exists
    for _, tasks in tasks_by_benchmark.items():
        if isinstance(tasks, list):
            valid_tasks = [t for t in tasks if isinstance(t, str) and "." in t]
            if valid_tasks:
                return True, ""
    
    return False, "Multi-task mode requires at least one task_id in tasks_by_benchmark"


def determine_execution_mode(config: dict) -> str:
    """
    Determine execution mode from configuration.
    
    Args:
        config: Configuration dict
        
    Returns:
        "single" or "multi" execution mode
    """
    tasks_by_benchmark = config.get("tasks_by_benchmark")
    is_multi = config.get("mode") == "multi" or isinstance(tasks_by_benchmark, dict)
    
    return "multi" if is_multi else "single"


def validate_evaluation_request(
    request: EvalRequest,
    required_roles: list[str],
    required_config_keys: list[str]
) -> Tuple[bool, str]:
    """
    Validate complete evaluation request.
    
    Checks:
    - Required participant roles
    - Configuration via benchmark manager
    - Single-task or multi-task specific validations
    
    Args:
        request: EvalRequest with participants and config
        required_roles: List of required role names
        required_config_keys: Required config keys for single-task mode
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    # Validate required roles
    is_valid, error = validate_required_roles(request.participants, required_roles)
    if not is_valid:
        return False, error
    
    config = request.config or {}
    
    # Use benchmark manager for basic validation
    validation = validate_assessment_config(config)
    if not validation["valid"]:
        return False, f"Config validation failed: {'; '.join(validation['errors'])}"
    
    # Determine execution mode
    mode = determine_execution_mode(config)
    
    # Mode-specific validation
    if mode == "single":
        return validate_single_task_config(config, required_config_keys)
    else:
        return validate_multi_task_config(config)
