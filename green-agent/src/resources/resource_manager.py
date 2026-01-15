"""
Resource management and limits for Green Agent.

Enforces resource limits (memory, CPU, concurrency) and ensures reproducibility.
Implements Resource limits, timeout guards, thread safety, reproducibility.
"""

import asyncio
import functools
import logging
import threading
from contextlib import asynccontextmanager
from typing import Any, Callable, Dict, Optional, TypeVar

from src.utils.exceptions import ResourceLimitError, TimeoutError


logger = logging.getLogger(__name__)

T = TypeVar("T")


class ResourceLimits:
    """
    Centralized resource limits configuration.
    
    Defines limits for:
    - Concurrent evaluations
    - Memory usage
    - Timeout durations
    - MCP server instances
    """

    # Concurrency limits
    MAX_CONCURRENT_EVALUATIONS = 3
    MAX_MCP_SERVERS = 5

    # Timeout limits (seconds)
    DEFAULT_EVALUATION_TIMEOUT = 300  # 5 minutes
    MAX_EVALUATION_TIMEOUT = 3600  # 1 hour
    MIN_EVALUATION_TIMEOUT = 60  # 1 minute

    MCP_HEALTH_CHECK_TIMEOUT = 30
    MCP_SPAWN_TIMEOUT = 60
    MCP_CLEANUP_TIMEOUT = 30

    # Memory limits (MB)
    MAX_OBSERVATION_SIZE_MB = 50  # Maximum size for observation data
    MAX_ARTIFACT_SIZE_MB = 10  # Maximum size for artifact data

    # Rate limits
    MAX_ACTIONS_PER_EVALUATION = 1000  # Prevent infinite loops


class ConcurrencyLimiter:
    """
    Semaphore-based concurrency limiter.
    
    Ensures maximum number of concurrent operations doesn't exceed limit.
    """

    def __init__(self, max_concurrent: int):
        """
        Initialize concurrency limiter.
        
        Args:
            max_concurrent: Maximum concurrent operations
        """
        self.max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._active_count = 0
        self._lock = threading.Lock()

    @asynccontextmanager
    async def acquire(self, operation_id: str):
        """
        Acquire concurrency slot.
        
        Args:
            operation_id: Operation identifier for logging
            
        Yields:
            None
            
        Raises:
            ResourceLimitError: If concurrency limit reached and timeout
        """
        logger.debug(f"Acquiring concurrency slot for {operation_id}")

        try:
            async with self._semaphore:
                with self._lock:
                    self._active_count += 1

                logger.info(
                    f"Concurrency slot acquired for {operation_id} "
                    f"(active: {self._active_count}/{self.max_concurrent})"
                )

                try:
                    yield
                finally:
                    with self._lock:
                        self._active_count -= 1

                    logger.debug(
                        f"Concurrency slot released for {operation_id} "
                        f"(active: {self._active_count}/{self.max_concurrent})"
                    )

        except asyncio.TimeoutError:
            raise ResourceLimitError(
                f"Concurrency limit reached: {self.max_concurrent} concurrent operations",
                resource_type="concurrency",
                limit=self.max_concurrent,
                current=self._active_count
            )

    def get_active_count(self) -> int:
        """Get number of active operations."""
        with self._lock:
            return self._active_count


class TimeoutGuard:
    """
    Timeout guard for async operations.
    
    Ensures operations complete within timeout or raise TimeoutError.
    """

    @staticmethod
    async def with_timeout(
        coro: Callable,
        timeout_seconds: float,
        operation_name: str
    ) -> Any:
        """
        Execute coroutine with timeout.
        
        Args:
            coro: Coroutine to execute
            timeout_seconds: Timeout in seconds
            operation_name: Operation name for error message
            
        Returns:
            Coroutine result
            
        Raises:
            TimeoutError: If operation exceeds timeout
        """
        try:
            result = await asyncio.wait_for(coro, timeout=timeout_seconds)
            return result

        except asyncio.TimeoutError:
            raise TimeoutError(
                f"Operation '{operation_name}' exceeded timeout of {timeout_seconds}s",
                operation=operation_name,
                timeout_seconds=timeout_seconds
            )


class ThreadSafeState:
    """
    Thread-safe state container.
    
    Provides thread-safe access to shared state using locks.
    """

    def __init__(self):
        """Initialize thread-safe state."""
        self._state: Dict[str, Any] = {}
        self._lock = threading.RLock()  # Reentrant lock

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get state value.
        
        Args:
            key: State key
            default: Default value if key not found
            
        Returns:
            State value
        """
        with self._lock:
            return self._state.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """
        Set state value.
        
        Args:
            key: State key
            value: State value
        """
        with self._lock:
            self._state[key] = value

    def update(self, updates: Dict[str, Any]) -> None:
        """
        Update multiple state values.
        
        Args:
            updates: Dictionary of updates
        """
        with self._lock:
            self._state.update(updates)

    def delete(self, key: str) -> None:
        """
        Delete state value.
        
        Args:
            key: State key to delete
        """
        with self._lock:
            self._state.pop(key, None)

    def clear(self) -> None:
        """Clear all state."""
        with self._lock:
            self._state.clear()

    def to_dict(self) -> Dict[str, Any]:
        """
        Get state as dictionary.
        
        Returns:
            State dictionary (copy)
        """
        with self._lock:
            return self._state.copy()


class ReproducibilityManager:
    """
    Ensures reproducible evaluations.
    
    Tracks:
    - Random seeds
    - Environment configurations
    - Dependency versions
    - Evaluation parameters
    """

    def __init__(self, seed: Optional[int] = None):
        """
        Initialize reproducibility manager.
        
        Args:
            seed: Random seed (optional)
        """
        self.seed = seed
        self._config_snapshot: Dict[str, Any] = {}

    def set_seed(self, seed: int) -> None:
        """
        Set random seed for reproducibility.
        
        Args:
            seed: Random seed
        """
        self.seed = seed
        # TODO: Set seeds for random, numpy, torch, etc.

    def snapshot_config(self, config: Dict[str, Any]) -> None:
        """
        Snapshot configuration for reproducibility.
        
        Args:
            config: Configuration to snapshot
        """
        self._config_snapshot = config.copy()

    def get_reproducibility_metadata(self) -> Dict[str, Any]:
        """
        Get reproducibility metadata.
        
        Returns:
            Metadata for reproducing evaluation
        """
        return {
            "seed": self.seed,
            "config_snapshot": self._config_snapshot,
            # TODO: Add:
            # - Python version
            # - Dependency versions
            # - Environment variables
            # - System info
        }


# Global resource managers
_evaluation_limiter: Optional[ConcurrencyLimiter] = None
_mcp_limiter: Optional[ConcurrencyLimiter] = None
_global_state: Optional[ThreadSafeState] = None


def get_evaluation_limiter() -> ConcurrencyLimiter:
    """Get evaluation concurrency limiter."""
    global _evaluation_limiter
    if _evaluation_limiter is None:
        _evaluation_limiter = ConcurrencyLimiter(ResourceLimits.MAX_CONCURRENT_EVALUATIONS)
    return _evaluation_limiter


def get_mcp_limiter() -> ConcurrencyLimiter:
    """Get MCP server concurrency limiter."""
    global _mcp_limiter
    if _mcp_limiter is None:
        _mcp_limiter = ConcurrencyLimiter(ResourceLimits.MAX_MCP_SERVERS)
    return _mcp_limiter


def get_global_state() -> ThreadSafeState:
    """Get global thread-safe state."""
    global _global_state
    if _global_state is None:
        _global_state = ThreadSafeState()
    return _global_state


__all__ = [
    "ResourceLimits",
    "ConcurrencyLimiter",
    "TimeoutGuard",
    "ThreadSafeState",
    "ReproducibilityManager",
    "get_evaluation_limiter",
    "get_mcp_limiter",
    "get_global_state",
]
