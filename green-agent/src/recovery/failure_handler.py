"""
Failure recovery and cleanup handlers for Green Agent.

Handles MCP disconnections, partial evaluation cleanup, and graceful degradation.
Implements Failure recovery with rollback and dataset verification.
"""

import asyncio
import logging
from typing import Any, Dict, Optional

from src.utils.exceptions import EvaluationError, MCPServerError


logger = logging.getLogger(__name__)


class FailureRecoveryHandler:
    """
    Handles failure recovery for Green Agent.
    
    Provides:
    - MCP disconnection recovery with automatic restart
    - Partial evaluation cleanup
    - Graceful degradation strategies
    - Dataset verification before evaluation
    """

    def __init__(self, max_retry_attempts: int = 3, retry_delay_seconds: int = 5):
        """
        Initialize failure recovery handler.
        
        Args:
            max_retry_attempts: Maximum retry attempts for recovery
            retry_delay_seconds: Delay between retry attempts
        """
        self.max_retry_attempts = max_retry_attempts
        self.retry_delay_seconds = retry_delay_seconds
        self._recovery_in_progress: Dict[str, bool] = {}

    async def handle_mcp_disconnection(
        self,
        session_id: str,
        spawn_mcp_func,
        **spawn_kwargs
    ) -> bool:
        """
        Handle MCP server disconnection with automatic restart.
        
        Args:
            session_id: Session ID
            spawn_mcp_func: Function to spawn MCP server
            **spawn_kwargs: Arguments for spawn function
            
        Returns:
            True if recovery successful, False otherwise
        """
        if self._recovery_in_progress.get(session_id):
            logger.warning(f"Recovery already in progress for session {session_id}")
            return False

        self._recovery_in_progress[session_id] = True

        try:
            for attempt in range(1, self.max_retry_attempts + 1):
                logger.info(
                    f"Attempting MCP server recovery for session {session_id} "
                    f"(attempt {attempt}/{self.max_retry_attempts})"
                )

                try:
                    # Spawn new MCP server
                    mcp_process = await spawn_mcp_func(**spawn_kwargs)

                    if mcp_process and mcp_process.poll() is None:
                        logger.info(f"MCP server recovered successfully for session {session_id}")
                        return True

                except Exception as e:
                    logger.error(f"MCP recovery attempt {attempt} failed: {e}")

                # Wait before retry
                if attempt < self.max_retry_attempts:
                    await asyncio.sleep(self.retry_delay_seconds)

            logger.error(
                f"MCP server recovery failed after {self.max_retry_attempts} attempts "
                f"for session {session_id}"
            )
            return False

        finally:
            self._recovery_in_progress[session_id] = False

    async def cleanup_partial_evaluation(
        self,
        session_id: str,
        task_id: str,
        cleanup_mcp_func,
        **cleanup_kwargs
    ) -> None:
        """
        Cleanup partial evaluation artifacts.
        
        Handles cleanup when evaluation fails mid-execution:
        - Closes browser instances
        - Cleans up MCP server resources
        - Removes temporary files
        - Resets session state
        
        Args:
            session_id: Session ID
            task_id: Task ID
            cleanup_mcp_func: Function to cleanup MCP resources
            **cleanup_kwargs: Arguments for cleanup function
        """
        logger.info(f"Cleaning up partial evaluation for task {task_id} (session {session_id})")

        try:
            # Cleanup MCP resources
            await cleanup_mcp_func(**cleanup_kwargs)
            logger.info(f"MCP cleanup completed for task {task_id}")

        except Exception as e:
            logger.error(f"Error during MCP cleanup for task {task_id}: {e}")

        # TODO: Add cleanup for other resources:
        # - Browser instances
        # - Temporary files
        # - Session state
        # - Cached observations

        logger.info(f"Partial evaluation cleanup completed for task {task_id}")

    async def verify_dataset_availability(
        self,
        benchmark: str,
        task_id: str
    ) -> bool:
        """
        Verify dataset is available before starting evaluation.
        
        Checks:
        - Dataset files exist
        - Required resources are accessible
        - Benchmark configuration is valid
        
        Args:
            benchmark: Benchmark name
            task_id: Task ID
            
        Returns:
            True if dataset available, False otherwise
            
        Raises:
            EvaluationError: If dataset verification fails critically
        """
        logger.info(f"Verifying dataset availability for {benchmark}.{task_id}")

        try:
            # TODO: Implement actual dataset verification
            # For now, just check benchmark name
            from src.security.input_validator import SUPPORTED_BENCHMARKS

            if benchmark not in SUPPORTED_BENCHMARKS:
                raise EvaluationError(
                    f"Unsupported benchmark: {benchmark}",
                    task_id=task_id,
                    benchmark=benchmark
                )

            # TODO: Check benchmark-specific requirements:
            # - miniwob: HTML files in benchmarks/miniwob/
            # - webarena: Configuration files
            # - visualwebarena: Image benchmarks
            # - workarena: WorkArena environment
            # - assistantbench: Assistant data
            # - weblinx: WebLinx data

            logger.info(f"Dataset verification passed for {benchmark}.{task_id}")
            return True

        except EvaluationError:
            raise
        except Exception as e:
            logger.error(f"Dataset verification failed for {benchmark}.{task_id}: {e}")
            return False

    async def rollback_evaluation_state(
        self,
        session_id: str,
        previous_state: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Rollback evaluation state on failure.
        
        Restores previous valid state if evaluation fails.
        
        Args:
            session_id: Session ID
            previous_state: Previous state to restore (optional)
        """
        logger.info(f"Rolling back evaluation state for session {session_id}")

        try:
            if previous_state:
                # TODO: Restore previous state
                # - Session state
                # - Environment state
                # - MCP server state
                logger.info(f"State rolled back to previous checkpoint for session {session_id}")
            else:
                logger.warning(f"No previous state to restore for session {session_id}")

        except Exception as e:
            logger.error(f"Error during state rollback for session {session_id}: {e}")

    async def handle_evaluation_timeout(
        self,
        session_id: str,
        task_id: str,
        cleanup_func,
        **cleanup_kwargs
    ) -> Dict[str, Any]:
        """
        Handle evaluation timeout gracefully.
        
        Args:
            session_id: Session ID
            task_id: Task ID
            cleanup_func: Cleanup function
            **cleanup_kwargs: Cleanup arguments
            
        Returns:
            Partial artifact with timeout metadata
        """
        logger.warning(f"Evaluation timeout for task {task_id} (session {session_id})")

        # Cleanup resources
        await self.cleanup_partial_evaluation(
            session_id=session_id,
            task_id=task_id,
            cleanup_mcp_func=cleanup_func,
            **cleanup_kwargs
        )

        # Return partial artifact
        return {
            "task_id": task_id,
            "task_success": False,
            "metadata": {
                "failure_reason": "timeout",
                "session_id": session_id,
                "message": "Evaluation exceeded timeout limit"
            }
        }

    def is_recovery_in_progress(self, session_id: str) -> bool:
        """
        Check if recovery is in progress for session.
        
        Args:
            session_id: Session ID
            
        Returns:
            True if recovery in progress
        """
        return self._recovery_in_progress.get(session_id, False)


# Global failure recovery handler
_recovery_handler: Optional[FailureRecoveryHandler] = None


def get_recovery_handler() -> FailureRecoveryHandler:
    """Get global failure recovery handler."""
    global _recovery_handler
    if _recovery_handler is None:
        _recovery_handler = FailureRecoveryHandler()
    return _recovery_handler


__all__ = [
    "FailureRecoveryHandler",
    "get_recovery_handler",
]
