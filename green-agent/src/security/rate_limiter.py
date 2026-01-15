"""
Rate limiting for Green Agent endpoints.

Prevents abuse and DoS attacks by limiting requests per client.
Implements Rate limiting with configurable limits per endpoint.
"""

import time
from collections import defaultdict
from typing import Dict, Optional, Tuple

from src.utils.exceptions import SecurityError


class RateLimiter:
    """
    Token bucket rate limiter for request throttling.
    
    Uses client IP or identifier to track request rates.
    Thread-safe implementation with per-client buckets.
    """

    def __init__(
        self,
        requests_per_minute: int = 60,
        burst_size: Optional[int] = None
    ):
        """
        Initialize rate limiter.
        
        Args:
            requests_per_minute: Maximum requests per minute per client
            burst_size: Maximum burst size (defaults to requests_per_minute)
        """
        self.rate = requests_per_minute / 60.0  # requests per second
        self.burst_size = burst_size or requests_per_minute
        
        # Storage: client_id -> (tokens, last_update_time)
        self._buckets: Dict[str, Tuple[float, float]] = defaultdict(
            lambda: (self.burst_size, time.time())
        )

    def check_rate_limit(self, client_id: str, cost: float = 1.0) -> None:
        """
        Check if request is within rate limit.
        
        Args:
            client_id: Client identifier (IP address, user ID, etc.)
            cost: Request cost in tokens (default: 1.0)
            
        Raises:
            SecurityError: If rate limit exceeded
        """
        current_time = time.time()
        
        # Get current bucket state
        tokens, last_update = self._buckets[client_id]
        
        # Refill tokens based on time elapsed
        time_elapsed = current_time - last_update
        tokens = min(self.burst_size, tokens + time_elapsed * self.rate)
        
        # Check if enough tokens available
        if tokens < cost:
            # Calculate wait time
            wait_time = (cost - tokens) / self.rate
            raise SecurityError(
                f"Rate limit exceeded for client {client_id}. Retry after {wait_time:.1f} seconds",
                security_issue="rate_limit_exceeded",
                client_id=client_id,
                retry_after_seconds=wait_time,
                current_tokens=tokens,
                required_tokens=cost
            )
        
        # Consume tokens
        tokens -= cost
        
        # Update bucket
        self._buckets[client_id] = (tokens, current_time)

    def reset(self, client_id: Optional[str] = None) -> None:
        """
        Reset rate limit for client(s).
        
        Args:
            client_id: Client to reset (None = reset all clients)
        """
        if client_id:
            if client_id in self._buckets:
                self._buckets[client_id] = (self.burst_size, time.time())
        else:
            self._buckets.clear()

    def get_remaining_tokens(self, client_id: str) -> float:
        """
        Get remaining tokens for client.
        
        Args:
            client_id: Client identifier
            
        Returns:
            Remaining tokens (request capacity)
        """
        if client_id not in self._buckets:
            return self.burst_size
        
        current_time = time.time()
        tokens, last_update = self._buckets[client_id]
        
        # Calculate current tokens (with refill)
        time_elapsed = current_time - last_update
        tokens = min(self.burst_size, tokens + time_elapsed * self.rate)
        
        return tokens


# Global rate limiters for different endpoints
_rate_limiters: Dict[str, RateLimiter] = {
    # Evaluation endpoint: 10 requests per minute (evaluations are expensive)
    "evaluate": RateLimiter(requests_per_minute=10, burst_size=5),
    
    # Health check: 60 requests per minute (lightweight, allow more)
    "health": RateLimiter(requests_per_minute=60, burst_size=10),
    
    # Artifact submission: 20 requests per minute
    "artifact": RateLimiter(requests_per_minute=20, burst_size=10),
    
    # Default: 30 requests per minute
    "default": RateLimiter(requests_per_minute=30, burst_size=15),
}


def check_rate_limit(endpoint: str, client_id: str, cost: float = 1.0) -> None:
    """
    Check rate limit for endpoint and client.
    
    Args:
        endpoint: Endpoint name (evaluate, health, artifact, default)
        client_id: Client identifier
        cost: Request cost in tokens
        
    Raises:
        SecurityError: If rate limit exceeded
    """
    limiter = _rate_limiters.get(endpoint, _rate_limiters["default"])
    limiter.check_rate_limit(client_id, cost)


def get_remaining_capacity(endpoint: str, client_id: str) -> float:
    """
    Get remaining request capacity for client.
    
    Args:
        endpoint: Endpoint name
        client_id: Client identifier
        
    Returns:
        Remaining tokens
    """
    limiter = _rate_limiters.get(endpoint, _rate_limiters["default"])
    return limiter.get_remaining_tokens(client_id)


def reset_rate_limit(endpoint: str, client_id: Optional[str] = None) -> None:
    """
    Reset rate limit for endpoint.
    
    Args:
        endpoint: Endpoint name
        client_id: Client to reset (None = reset all)
    """
    if endpoint in _rate_limiters:
        _rate_limiters[endpoint].reset(client_id)


__all__ = [
    "RateLimiter",
    "check_rate_limit",
    "get_remaining_capacity",
    "reset_rate_limit",
]
