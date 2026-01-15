"""
Helper functions for observation filtering operations.

Extracted from observation_filter.py to reduce duplication and improve testability.
"""

from typing import Dict, Any, Optional
from src.utils.token_estimator import estimate_tokens, check_token_limit
from src.utils.logging import get_logger


logger = get_logger(__name__)


def extract_observation_metadata(observation: Dict[str, Any]) -> Dict[str, str]:
    """
    Extract common metadata from observation.
    
    Args:
        observation: Raw observation dict
        
    Returns:
        Dict with url, goal, and last_action_result
    """
    return {
        "url": observation.get("url", ""),
        "goal": observation.get("goal", observation.get("task_goal", "")),
        "last_action_result": observation.get("last_action_error", ""),
    }


def calculate_observation_tokens(filtered_obs: Dict[str, Any]) -> int:
    """
    Calculate total token count for filtered observation.
    
    Estimates tokens for all text fields in the observation.
    
    Args:
        filtered_obs: Filtered observation dict
        
    Returns:
        Total estimated token count
    """
    total = 0
    
    # Main content fields
    for key in ["axtree_txt", "dom_txt", "url", "goal", "last_action_result"]:
        if key in filtered_obs and filtered_obs[key]:
            total += estimate_tokens(str(filtered_obs[key]))
    
    return total


def add_token_metadata(
    filtered_obs: Dict[str, Any],
    token_limit: int,
    mode_name: str,
    content_key: str = "axtree_txt"
) -> Dict[str, Any]:
    """
    Add token estimates and compliance warnings to filtered observation.
    
    Args:
        filtered_obs: Filtered observation dict
        token_limit: Maximum allowed tokens
        mode_name: Observation mode name for metadata
        content_key: Key containing main content for limit check
        
    Returns:
        Updated observation dict with token metadata
    """
    # Calculate total tokens
    total_tokens = calculate_observation_tokens(filtered_obs)
    filtered_obs["token_estimate"] = total_tokens
    filtered_obs["observation_mode"] = mode_name
    
    # Check token limit compliance
    content = filtered_obs.get(content_key, "")
    if content:
        _, within_limit, warning = check_token_limit(content, token_limit)
        
        if not within_limit:
            filtered_obs["warning"] = warning
            logger.warning(
                f"Observation exceeds token limit",
                extra={
                    "mode": mode_name,
                    "tokens": total_tokens,
                    "limit": token_limit,
                    "warning": warning
                }
            )
    
    return filtered_obs


def create_screenshot_reference(
    observation: Dict[str, Any],
    include_dimensions: bool = True
) -> str:
    """
    Create a text reference to screenshot data.
    
    Args:
        observation: Raw observation with screenshot field
        include_dimensions: Include screenshot dimensions in reference
        
    Returns:
        Screenshot reference string
    """
    screenshot = observation.get("screenshot")
    if not screenshot:
        return "[No screenshot available]"
    
    ref = "[Screenshot: binary data available]"
    
    if include_dimensions and isinstance(screenshot, (bytes, bytearray)):
        ref += f" ({len(screenshot)} bytes)"
    
    return ref


def build_filtered_observation(
    content: str,
    observation: Dict[str, Any],
    content_key: str,
    token_limit: int,
    mode_name: str,
    extra_fields: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Build a complete filtered observation dict with all standard fields.
    
    Combines content, metadata, token estimates, and compliance checks.
    
    Args:
        content: Filtered main content (AXTree, DOM, etc.)
        observation: Raw observation for metadata extraction
        content_key: Key to store main content under (e.g., "axtree_txt")
        token_limit: Maximum allowed tokens
        mode_name: Observation mode name
        extra_fields: Optional additional fields to include
        
    Returns:
        Complete filtered observation dict
    """
    # Start with main content
    filtered_obs = {content_key: content}
    
    # Add standard metadata
    filtered_obs.update(extract_observation_metadata(observation))
    
    # Add extra fields if provided
    if extra_fields:
        filtered_obs.update(extra_fields)
    
    # Add token metadata and compliance checks
    add_token_metadata(filtered_obs, token_limit, mode_name, content_key)
    
    return filtered_obs


def truncate_content_to_limit(
    content: str,
    token_limit: int,
    preserve_start: int = 0,
    preserve_end: int = 0
) -> str:
    """
    Truncate content to fit within token limit.
    
    Optionally preserves content at start and end.
    
    Args:
        content: Content string to truncate
        token_limit: Maximum allowed tokens
        preserve_start: Number of tokens to preserve at start
        preserve_end: Number of tokens to preserve at end
        
    Returns:
        Truncated content string
    """
    current_tokens = estimate_tokens(content)
    
    if current_tokens <= token_limit:
        return content
    
    # Simple line-based truncation (rough estimate)
    lines = content.split("\n")
    target_lines = int(len(lines) * (token_limit / current_tokens))
    
    if preserve_start and preserve_end:
        # Preserve both ends
        start_lines = preserve_start * len(lines) // current_tokens
        end_lines = preserve_end * len(lines) // current_tokens
        mid_lines = target_lines - start_lines - end_lines
        
        if mid_lines > 0:
            return (
                "\n".join(lines[:start_lines]) +
                f"\n... ({len(lines) - target_lines} lines truncated) ...\n" +
                "\n".join(lines[-end_lines:])
            )
    
    # Simple truncation from end
    return "\n".join(lines[:target_lines]) + f"\n... (truncated {len(lines) - target_lines} lines)"
