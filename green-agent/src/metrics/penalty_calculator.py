"""
Efficiency penalty calculator for competition scoring.

Implements FR-017 formula: 1 - λ_C × log(C) - λ_L × L
"""

import math
# from typing import Optional


class PenaltyCalculator:
    """Compatibility wrapper for penalty/score calculation.

    Some parts of the codebase (and older versions) expect an OO-style
    `PenaltyCalculator` with configurable coefficients.
    """

    def __init__(self, lambda_c: float = 0.01, lambda_l: float = 0.1) -> None:
        self.lambda_c = lambda_c
        self.lambda_l = lambda_l

    def efficiency_penalty(self, total_tokens: int, total_latency_seconds: float) -> float:
        return calculate_efficiency_penalty(
            total_tokens=total_tokens,
            total_latency_seconds=total_latency_seconds,
            lambda_c=self.lambda_c,
            lambda_l=self.lambda_l,
        )

    def final_score(self, task_success: bool, total_tokens: int, total_latency_seconds: float) -> float:
        return calculate_final_score(
            task_success=task_success,
            total_tokens=total_tokens,
            total_latency_seconds=total_latency_seconds,
            lambda_c=self.lambda_c,
            lambda_l=self.lambda_l,
        )


def calculate_efficiency_penalty(
    total_tokens: int,
    total_latency_seconds: float,
    lambda_c: float = 0.01,
    lambda_l: float = 0.1
) -> float:
    """
    Calculate efficiency penalty using constitutional formula.
    
    Formula: efficiency = 1 - λ_C × log(C) - λ_L × L
    Where:
        λ_C = 0.01 (token penalty coefficient)
        λ_L = 0.1 (latency penalty coefficient)
        C = total token count
        L = total latency in seconds
    
    Args:
        total_tokens: Cumulative token count across all observations
        total_latency_seconds: Cumulative latency in seconds
        lambda_c: Token penalty coefficient (default: 0.01)
        lambda_l: Latency penalty coefficient (default: 0.1)
        
    Returns:
        Efficiency penalty in range [0, 1] (higher is better)
        
    Examples:
        >>> calculate_efficiency_penalty(2000, 1.5)
        0.774  # Efficient evaluation
        >>> calculate_efficiency_penalty(10000, 5.0)
        0.408  # Less efficient
    """
    # Handle edge case: zero tokens
    if total_tokens == 0:
        total_tokens = 1  # Use log(1) = 0
    
    # Calculate penalty components
    token_penalty = lambda_c * math.log(total_tokens)
    latency_penalty = lambda_l * total_latency_seconds
    
    # Calculate efficiency (clamp to [0, 1])
    efficiency = 1.0 - token_penalty - latency_penalty
    efficiency = max(0.0, min(1.0, efficiency))
    
    return efficiency


def calculate_final_score(
    task_success: bool,
    total_tokens: int,
    total_latency_seconds: float,
    lambda_c: float = 0.01,
    lambda_l: float = 0.1
) -> float:
    """
    Calculate final competition score.
    
    Formula: final_score = task_success × efficiency_penalty
    
    Args:
        task_success: Whether task completed successfully (1.0 or 0.0)
        total_tokens: Cumulative token count
        total_latency_seconds: Cumulative latency in seconds
        lambda_c: Token penalty coefficient
        lambda_l: Latency penalty coefficient
        
    Returns:
        Final score in range [0, 1]
    """
    success_value = 1.0 if task_success else 0.0
    efficiency = calculate_efficiency_penalty(
        total_tokens, total_latency_seconds, lambda_c, lambda_l
    )
    return success_value * efficiency
