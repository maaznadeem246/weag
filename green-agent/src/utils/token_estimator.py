"""
Token estimation utility for Mandate C compliance (Green Agent).

Uses tiktoken library with cl100k_base encoding for accurate token counting.
"""

import tiktoken
from typing import Dict, Any, Union


# Initialize encoder (cl100k_base is used by GPT-4 and similar models)
_encoder = tiktoken.get_encoding("cl100k_base")


def estimate_tokens(text: str) -> int:
    """
    Estimate token count for given text.
    
    Args:
        text: Text to count tokens for
        
    Returns:
        Estimated token count
    """
    if not text:
        return 0
    return len(_encoder.encode(text))


def estimate_tokens_dict(data: Dict[str, Any]) -> int:
    """
    Estimate tokens for a dictionary (e.g., observation object).
    
    Converts dict to JSON-like string and counts tokens.
    
    Args:
        data: Dictionary to estimate tokens for
        
    Returns:
        Estimated token count
    """
    import json
    text = json.dumps(data, default=str, ensure_ascii=False)
    return estimate_tokens(text)


def check_token_limit(text: str, limit: int = 5000) -> tuple[int, bool, str | None]:
    """
    Check if text exceeds token limit (Mandate C: <5K tokens).
    
    Args:
        text: Text to check
        limit: Token limit (default: 5000)
        
    Returns:
        Tuple of (token_count, within_limit, warning_message)
    """
    token_count = estimate_tokens(text)
    within_limit = token_count <= limit
    warning = None if within_limit else f"Token count {token_count} exceeds limit {limit}"
    return token_count, within_limit, warning


def estimate_observation_tokens(observation: Dict[str, Any]) -> int:
    """
    Estimate tokens for a BrowserGym observation.
    
    Args:
        observation: Observation dictionary from environment
        
    Returns:
        Estimated token count
    """
    # Count tokens for key fields
    total_tokens = 0
    
    if "axtree" in observation:
        total_tokens += estimate_tokens(str(observation["axtree"]))
    if "dom" in observation:
        total_tokens += estimate_tokens(str(observation["dom"]))
    if "url" in observation:
        total_tokens += estimate_tokens(str(observation["url"]))
    if "goal" in observation:
        total_tokens += estimate_tokens(str(observation["goal"]))
    if "last_action_result" in observation:
        total_tokens += estimate_tokens(str(observation["last_action_result"]))
        
    return total_tokens
