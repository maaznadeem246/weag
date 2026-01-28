"""Session manager for BrowserGym environment lifecycle.

Handles environment creation, tracking, and cleanup with Mandate F compliance.
"""

import asyncio
import os
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import unquote, urlparse

import gymnasium as gym
from src.environment.entities import (
    EnvironmentConfig,
    EnvironmentSession,
    CleanupStatus
)
from src.environment.helpers import (
    ensure_benchmark_registered,
    normalize_benchmark_environment_vars,
    get_browser_headless_mode,
    create_env_id,
    validate_task_id_format,
    extract_benchmark_from_task,
    log_session_creation
)
from src.resources.process_monitor import (
    verify_no_chromium_processes,
    get_current_chromium_pids,
    kill_specific_browser_pids
)
from src.utils.logging import get_logger
from src.utils.activity_watchdog import pulse, ActivityType
from src.config.settings import settings


logger = get_logger(__name__)


class SessionManager:
    """Manages BrowserGym environment sessions."""
    
    def __init__(self):
        """Initialize session manager."""
        self.sessions: Dict[str, EnvironmentSession] = {}
        self.current_session_id: Optional[str] = None
    
    def create_session(self, config: EnvironmentConfig) -> EnvironmentSession:
        """
        Create new BrowserGym environment session.
        
        Args:
            config: Environment configuration
            
        Returns:
            Created environment session
            
        Raises:
            ValueError: If task_id is invalid
            RuntimeError: If environment creation fails
        """
        # Guard: Return existing session if one already exists for this task
        for session_id, session in self.sessions.items():
            if session.task_id == config.task_id and session.is_active:
                logger.warning(
                    f"Session already exists for task {config.task_id}, returning existing session",
                    extra={"existing_session_id": session_id, "task_id": config.task_id}
                )
                self.current_session_id = session_id
                return session
        
        # Validate task_id format
        is_valid, error_msg = validate_task_id_format(config.task_id)
        if not is_valid:
            logger.error("Invalid task_id", extra={"task_id": config.task_id, "error": error_msg})
            raise ValueError(f"Invalid task_id: {error_msg}")
        
        benchmark = extract_benchmark_from_task(config.task_id)
        log_session_creation(
            config.task_id,
            benchmark,
            config.start_url,
            config.max_steps,
            config.seed,
            False  # headless determined later
        )
        
        # Create session object
        session = EnvironmentSession(
            task_id=config.task_id,
            benchmark=config.get_benchmark(),
            config=config
        )
        
        try:
            # Pulse watchdog - starting environment creation
            pulse(ActivityType.HEARTBEAT, f"creating_env_{config.task_id}")
            
            # Ensure benchmark environments are registered with Gymnasium
            ensure_benchmark_registered(benchmark)

            # Normalize benchmark-specific environment variables/paths
            normalize_benchmark_environment_vars(benchmark)

            # Create BrowserGym environment
            # Note: BrowserGym requires "browsergym/" prefix for gym.make()
            # Apply benchmark-specific configuration
            benchmark_config = config.get_benchmark_specific_config()
            
            # Add browsergym prefix if not present
            env_id = create_env_id(config.task_id)
            
            # Allow overriding headless via env var BROWSER_HEADLESS (default: false)
            headless = get_browser_headless_mode()

            # Capture browser PIDs before creating environment
            pids_before = set(get_current_chromium_pids())

            make_kwargs = {"headless": headless}
            make_kwargs.update(benchmark_config)

            # Optional benchmark/task-specific kwargs
            if config.task_kwargs:
                make_kwargs["task_kwargs"] = config.task_kwargs
            if config.wait_for_user_message is not None:
                make_kwargs["wait_for_user_message"] = config.wait_for_user_message
            if config.viewport:
                make_kwargs["viewport"] = config.viewport
            # Note: max_steps is NOT passed to gym.make() - BrowserEnv doesn't accept it
            # max_steps is managed by the agent/wrapper, not the environment constructor

            # Pulse before gym.make - can take several seconds
            pulse(ActivityType.HEARTBEAT, f"gym_make_{env_id}")
            
            env = gym.make(
                env_id,
                **make_kwargs
            )
            
            # Pulse before reset - the long operation (browser launch + page load)
            pulse(ActivityType.HEARTBEAT, f"env_reset_{config.task_id}")
            
            # Reset environment to get initial observation
            initial_obs, info = env.reset(seed=config.seed)
            
            # Pulse after reset completed
            pulse(ActivityType.HEARTBEAT, f"env_ready_{config.task_id}")
            
            # Capture browser PIDs after creating environment
            # The difference is the PIDs we spawned (for safe cleanup later)
            pids_after = set(get_current_chromium_pids())
            spawned_pids = list(pids_after - pids_before)
            session.browser_pids = spawned_pids
            
            logger.info(
                f"Captured {len(spawned_pids)} spawned browser PIDs",
                extra={"browser_pids": spawned_pids}
            )
            
            # Store environment and observation
            session.env_instance = env
            session.update_observation(initial_obs)
            
            # Register session
            self.sessions[session.session_id] = session
            self.current_session_id = session.session_id
            
            # Log environment initialization success
            logger.info("=" * 60)
            logger.info("✅ ENVIRONMENT INITIALIZED SUCCESSFULLY")
            logger.info(f"Task: {config.task_id}")
            logger.info(f"Benchmark: {session.benchmark}")
            logger.info(f"Session ID: {session.session_id}")
            logger.info(f"Browser PIDs: {len(spawned_pids)} processes")
            logger.info(f"Headless Mode: {headless}")
            logger.info("=" * 60)
            
            return session
            
        except Exception as e:
            # Log environment initialization error
            logger.error("=" * 60)
            logger.error("❌ ENVIRONMENT INITIALIZATION FAILED")
            logger.error(f"Task: {config.task_id}")
            logger.error(f"Error: {str(e)}")
            logger.error("=" * 60)
            logger.error(f"Full error details:", exc_info=True)
            raise RuntimeError(f"Environment creation failed: {str(e)}") from e
    
    def get_session(self, session_id: Optional[str] = None) -> Optional[EnvironmentSession]:
        """
        Get environment session by ID.
        
        Args:
            session_id: Session ID (uses current if None)
            
        Returns:
            Environment session or None if not found
        """
        sid = session_id or self.current_session_id
        return self.sessions.get(sid) if sid else None
    
    def cleanup_session(
        self,
        session_id: Optional[str] = None,
        verify_processes: bool = None
    ) -> Dict[str, Any]:
        """
        Clean up environment session (Mandate F).
        
        Guarantees cleanup using try-finally blocks (FR-010).
        Optionally verifies zero orphaned Chromium processes (FR-011).
        Only kills browser processes that this session spawned (not user's browsers).
        
        Args:
            session_id: Session ID to cleanup (uses current if None)
            verify_processes: Whether to verify Chromium cleanup
                             (defaults to settings.verify_chromium_processes)
            
        Returns:
            Cleanup status dict with metrics
        """
        sid = session_id or self.current_session_id
        session = self.get_session(sid)
        
        if not session:
            logger.warning("Cleanup requested for non-existent session", extra={"session_id": sid})
            return {
                "cleanup_status": "error",
                "error": "Session not found",
                "orphaned_processes": 0
            }
        
        session.request_cleanup()
        verify = verify_processes if verify_processes is not None else settings.verify_chromium_processes
        
        cleanup_result = {
            "cleanup_status": "success",
            "orphaned_processes": 0,
            "process_verification_enabled": verify,
            "killed_browser_pids": []
        }
        
        try:
            # Close environment (Mandate F: guaranteed cleanup)
            if session.env_instance:
                try:
                    # Direct call - this method is already called on the browser thread
                    # via browser_executor.run() from orchestrator._cleanup()
                    # Using run_sync here would cause deadlock (single-thread executor)
                    session.env_instance.close()
                    logger.info(
                        "Environment closed successfully",
                        extra={"session_id": session.session_id}
                    )
                except Exception as e:
                    logger.error(
                        "Error during environment close",
                        extra={"session_id": session.session_id, "error": str(e)},
                        exc_info=True
                    )
                    cleanup_result["cleanup_status"] = "error"
                    cleanup_result["error"] = str(e)
        finally:
            # Kill any browser processes that this session spawned (safe cleanup)
            # This only kills the specific PIDs we tracked, not user's browsers
            if session.browser_pids:
                try:
                    logger.info(
                        f"Attempting to kill browser processes for session",
                        extra={
                            "session_id": session.session_id,
                            "browser_pids": session.browser_pids,
                            "pid_count": len(session.browser_pids)
                        }
                    )
                    killed = kill_specific_browser_pids(session.browser_pids)
                    cleanup_result["killed_browser_pids"] = session.browser_pids
                    logger.info(
                        f"✓ Killed {killed} processes from session's browser PIDs",
                        extra={
                            "session_id": session.session_id,
                            "browser_pids": session.browser_pids,
                            "killed_count": killed
                        }
                    )
                except Exception as e:
                    logger.warning(f"Error killing session browser PIDs: {e}", exc_info=True)
            else:
                logger.warning(
                    f"No browser PIDs tracked for session {session.session_id} - cannot kill browsers!",
                    extra={"session_id": session.session_id}
                )
            
            # Verify cleanup if requested (check for any remaining orphans)
            if verify:
                is_clean, process_count, processes = verify_no_chromium_processes()
                cleanup_result["orphaned_processes"] = process_count
                cleanup_result["is_clean"] = is_clean
                cleanup_result["process_list"] = [
                    {"pid": p["pid"], "name": p["name"]} for p in processes
                ]
                
                if not is_clean:
                    logger.warning(
                        "Chromium processes detected after cleanup",
                        extra={
                            "session_id": session.session_id,
                            "process_count": process_count,
                        }
                    )
            
            # Mark session as cleaned
            session.mark_cleaned()
            
            # Remove from current session if it's the active one
            if self.current_session_id == session.session_id:
                self.current_session_id = None
        
        logger.info(
            "Session cleanup completed",
            extra={
                "session_id": session.session_id,
                "cleanup_status": cleanup_result["cleanup_status"],
                "orphaned_processes": cleanup_result["orphaned_processes"],
            }
        )
        
        return cleanup_result

    def switch_to_task(self, task_id: str, config: EnvironmentConfig, session_id: Optional[str] = None) -> Dict[str, Any]:
        """Switch to a new task by creating a new environment.
        
        Note: BrowserGym's design requires browser recreation for each task.
        The reset() method always closes the browser and creates a new one.
        This is by design in BrowserGym - see browsergym.core.env.BrowserEnv.reset()
        
        Args:
            task_id: New task identifier (e.g., miniwob.click-test)
            config: Environment config for the new task
            session_id: Session to modify (uses current if None)
            
        Returns:
            Status dict with 'action' field indicating what was done
        """
        sid = session_id or self.current_session_id
        session = self.get_session(sid)

        if not session:
            return {"status": "error", "error": "Session not found", "session_id": sid}
            
        new_benchmark = config.get_benchmark()
        current_benchmark = session.benchmark
        
        logger.info(
            f"Switching from {current_benchmark}/{session.task_id} to {new_benchmark}/{task_id}",
            extra={
                "session_id": session.session_id,
                "old_task": session.task_id,
                "new_task": task_id,
                "old_benchmark": current_benchmark,
                "new_benchmark": new_benchmark,
            }
        )
        
        # BrowserGym requires full environment recreation for each task
        # This is because reset() in BrowserGym always closes and recreates the browser
        try:
            # Close existing environment
            if session.env_instance:
                session.env_instance.close()
                session.env_instance = None
                
            # Create new environment (reuse create_session logic)
            new_session = self.create_session(config)
            
            # Replace the session data but keep the same session_id
            session.task_id = new_session.task_id
            session.benchmark = new_session.benchmark
            session.config = new_session.config
            session.env_instance = new_session.env_instance
            session.current_observation = new_session.current_observation
            # Keep existing browser_pids and add any new ones
            session.browser_pids.extend(new_session.browser_pids)
            
            # Remove the temporary session from registry
            del self.sessions[new_session.session_id]
            
            # CRITICAL: Reset current_session_id to the original session
            # (create_session sets it to new_session.session_id which we just deleted)
            self.current_session_id = session.session_id
            
            logger.info(
                f"✓ Switched to task {task_id} (browser recreated - BrowserGym design)",
                extra={
                    "session_id": session.session_id,
                    "current_session_id": self.current_session_id,
                    "new_task": task_id,
                    "old_benchmark": current_benchmark,
                    "new_benchmark": new_benchmark,
                    "new_observation_goal": session.current_observation.get("goal", "")[:100] if session.current_observation else None,
                    "note": "BrowserGym reset() always recreates browser"
                }
            )
            return {
                "status": "success", 
                "action": "recreate", 
                "session_id": session.session_id,
                "task_id": task_id,
                "benchmark": new_benchmark,
                "reused_browser": False
            }
        except Exception as e:
            logger.error(f"Failed to switch task: {e}", extra={"session_id": session.session_id})
            return {"status": "error", "error": str(e), "session_id": session.session_id}
    
    def cleanup_all_sessions(self) -> Dict[str, int]:
        """
        Clean up all active sessions.
        
        Returns:
            Summary with success/failure counts
        """
        logger.info("🧹 cleanup_all_sessions called", extra={"session_count": len(self.sessions)})
        
        success_count = 0
        error_count = 0
        
        session_ids = list(self.sessions.keys())
        for sid in session_ids:
            logger.info(f"🧹 Cleaning up session: {sid}")
            try:
                result = self.cleanup_session(sid)
                if result["cleanup_status"] == "success":
                    success_count += 1
                    logger.info(f"✅ Session {sid} cleaned up successfully")
                else:
                    error_count += 1
                    logger.warning(f"⚠️ Session {sid} cleanup failed: {result.get('error', 'unknown')}")
            except Exception as e:
                error_count += 1
                logger.error(f"❌ Exception during session {sid} cleanup: {e}", exc_info=True)
        
        logger.info(f"🧹 cleanup_all_sessions complete: {success_count} success, {error_count} errors")
        
        return {
            "success_count": success_count,
            "error_count": error_count,
            "total": len(session_ids)
        }
