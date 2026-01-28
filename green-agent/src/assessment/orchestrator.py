"""
Assessment Orchestrator - Background task execution for multi-task assessments.

Runs independently in the background while LLM handles A2A messages.
Uses existing multi_task_tools logic internally.
"""

import asyncio
import os
import time
from typing import Any, Dict, Optional
from uuid import uuid4

from src.assessment import Assessment, TaskStatus
from src.agent.context import AgentContext
from src.utils.shared_state import SharedStateManager
from src.utils.activity_watchdog import get_watchdog, create_watchdog, pulse, ActivityType
from src.environment.entities import EnvironmentConfig
from src.benchmarks.profiles import get_profile_for_task, detect_benchmark
from src.benchmarks.tool_registry import register_tools_for_benchmark
from src.mcp.server import (
    session_manager as mcp_session_manager,
    observation_filter as mcp_observation_filter,
    mcp as mcp_app,
    start_http_server,
)
from src.mcp import get_all_tools_metadata
# Import message builder directly to avoid circular imports
from src.a2a.message_builders import build_task_message
import src.mcp.server as mcp_module
from src.utils.logging import get_logger

logger = get_logger(__name__)

# MCP server state (module-level, shared across orchestrator instances)
_mcp_server_task: Optional[asyncio.Task] = None
_mcp_server_started: bool = False
_mcp_server_port: int = 8001


def _get_mcp_url() -> str:
    """Get MCP URL for Purple Agent connection.
    
    Auto-detects Docker environment and uses appropriate hostname.
    Priority: Explicit MCP_EXTERNAL_URL > Auto-detect Docker > localhost
    """
    from src.utils.docker_detection import is_running_in_docker
    
    # Priority 1: Explicit external URL from env var
    external_url = os.environ.get("MCP_EXTERNAL_URL")
    if external_url:
        return external_url
    
    # Priority 2: Auto-detect Docker and use container name
    if is_running_in_docker():
        # Purple Agent connects to Green Agent via container name (not localhost)
        mcp_url = f"http://green-agent:{_mcp_server_port}/mcp"
        logger.info(f"🐳 Docker detected - using MCP URL: {mcp_url}")
        return mcp_url
    
    # Priority 3: Default to localhost for local development
    return f"http://localhost:{_mcp_server_port}/mcp"


class AssessmentOrchestrator:
    """
    Background orchestrator for multi-task assessment execution.
    
    Runs the task loop independently:
    1. Initialize MCP server
    2. Send first task to Purple Agent
    3. Wait for completion
    4. Send next task (with environment switching)
    5. Repeat until all tasks done
    6. Finalize and store results
    
    Usage:
        orchestrator = AssessmentOrchestrator(assessment, context)
        task = asyncio.create_task(orchestrator.run())
        assessment.set_orchestrator_running(task)
    """
    
    def __init__(self, assessment: Assessment, context: AgentContext, active_sessions: Optional[Dict[str, Any]] = None):
        """
        Initialize orchestrator.
        
        Args:
            assessment: Assessment tracker with task plan
            context: Agent context with Purple Agent URL and state
            active_sessions: Optional dict for status endpoint updates (passed from main module)
        """
        self._assessment = assessment
        self._context = context
        self._timeout_per_task = assessment.timeout_seconds
        self._active_sessions = active_sessions or {}
    
    def _update_status(self, state: str, **extra_fields) -> None:
        """
        Update _active_sessions dict for /status/{run_id} endpoint polling.
        
        Args:
            state: Current state - "running", "complete", "failed"
            **extra_fields: Additional fields to include in status dict
        """
        if not self._active_sessions:
            return  # No-op if module not loaded yet
        
        run_id = self._assessment.run_id
        assessment_dict = self._assessment.to_dict()
        
        status_entry = {
            "state": state,
            "run_id": run_id,
            "task_id": assessment_dict.get("config", {}).get("task_id", "multi"),
            "progress": {
                "current_index": assessment_dict.get("current_index", 0),
                "total_tasks": assessment_dict.get("total_tasks", 0),
                "passed_count": assessment_dict.get("passed_count", 0),
                "failed_count": assessment_dict.get("failed_count", 0),
                "success_rate": assessment_dict.get("success_rate", 0.0),
            },
            **extra_fields
        }
        
        self._active_sessions[run_id] = status_entry
        logger.debug(f"Status update: {state} - {status_entry['progress']}")

    
    async def run(self) -> Dict[str, Any]:
        """
        Run the complete assessment orchestration loop.
        
        Returns:
            Final assessment results artifact
        """
        assessment = self._assessment
        context = self._context
        
        try:
            logger.info(f"🚀 Starting assessment orchestration: {assessment.total_tasks} tasks")
            self._update_status("running")
            
            # Step 1: Initialize MCP server
            await self._initialize_mcp_server()
            
            # Step 2: Send first task
            await self._send_first_task()
            self._update_status("running")  # Update after first task sent
            
            # Step 3: Main task loop
            while not assessment.is_all_complete():
                # Wait for current task completion
                await self._wait_for_completion()
                self._update_status("running")  # Update after task completion
                
                # Check if more tasks
                if assessment.advance_to_next_task():
                    # Send next task
                    await self._send_task()
                    self._update_status("running")  # Update after sending next task
                else:
                    # No more tasks
                    break
            
            # Step 4: Finalize
            artifact = self._finalize()
            assessment.set_orchestrator_complete(artifact)
            
            # Final status update
            self._update_status("complete", result=artifact)
            
            logger.info(f"✅ Assessment orchestration complete: {assessment.get_passed_count()}/{assessment.total_tasks} passed")
            logger.info("✅ About to return from run() - finally block will execute cleanup")
            return artifact
            
        except asyncio.CancelledError:
            logger.warning("⚠️ Orchestrator was cancelled - running cleanup anyway")
            assessment.set_orchestrator_error("Cancelled")
            self._update_status("failed", error="Cancelled")
            raise
        except Exception as e:
            logger.error(f"❌ Orchestrator failed: {e}", exc_info=True)
            assessment.set_orchestrator_error(str(e))
            self._update_status("failed", error=str(e))
            raise
        finally:
            # Cleanup always runs
            logger.info("🧹 Finally block reached - starting cleanup")
            await self._cleanup()
    
    async def _initialize_mcp_server(self) -> None:
        """Initialize MCP server for the assessment."""
        global _mcp_server_task, _mcp_server_started
        
        if _mcp_server_started:
            logger.debug("MCP server already running")
            return
        
        logger.info(f"Starting MCP server on port {_mcp_server_port}")
        _mcp_server_task = asyncio.create_task(start_http_server(port=_mcp_server_port))
        
        # Wait for server ready
        ready = await self._wait_for_server(_mcp_server_port)
        if not ready:
            raise RuntimeError(f"MCP server failed to start on port {_mcp_server_port}")
        
        _mcp_server_started = True
        logger.info(f"✓ MCP server ready on port {_mcp_server_port}")
    
    async def _wait_for_server(self, port: int, timeout: float = 15.0) -> bool:
        """Wait for MCP server to be ready."""
        import httpx
        start = asyncio.get_running_loop().time()
        async with httpx.AsyncClient() as client:
            while asyncio.get_running_loop().time() - start < timeout:
                try:
                    resp = await client.get(f"http://localhost:{port}/", timeout=1.0)
                    if resp.status_code < 500:
                        return True
                except Exception:
                    await asyncio.sleep(0.25)
        return False
    
    async def _send_first_task(self) -> None:
        """Initialize environment and send first task."""
        assessment = self._assessment
        context = self._context
        
        first_task = assessment.current_task_id
        benchmark_id = assessment.current_benchmark
        max_steps = assessment.max_steps
        max_tool_calls = assessment.max_tool_calls
        
        # Create shared state
        mcp_session_id = str(uuid4())
        os.environ["MCP_SESSION_ID"] = mcp_session_id
        shared_state = SharedStateManager(mcp_session_id)
        shared_state.initialize()
        
        context.shared_state_manager = shared_state
        context.mcp_session_id = mcp_session_id
        assessment.set_state_manager(shared_state)
        mcp_module.shared_state = shared_state
        
        # Setup benchmark profile
        profile = get_profile_for_task(first_task)
        if hasattr(mcp_observation_filter, "apply_profile"):
            mcp_observation_filter.apply_profile(profile)
        mcp_module.active_benchmark_profile = profile
        register_tools_for_benchmark(benchmark_id, mcp_app)
        
        # Create environment session
        env_config = EnvironmentConfig(task_id=first_task, max_steps=max_steps)
        from src.environment.thread_executor import browser_executor
        session = await browser_executor.run(mcp_session_manager.create_session, env_config)
        
        # Update shared state
        shared_state.reset_for_new_task(task_id=first_task, benchmark_id=benchmark_id)
        shared_state.update_tool_invocation("initialize_environment")
        shared_state.set_max_tool_calls(max_tool_calls)
        
        # Get task goal
        task_goal = None
        if session and session.current_observation:
            task_goal = session.current_observation.get("goal", "")
        
        # Build and send message
        await self._send_task_message(
            task_id=first_task,
            benchmark=benchmark_id,
            profile=profile,
            task_goal=task_goal,
            max_tool_calls=max_tool_calls,
            is_first=True,
        )
        
        assessment.mark_task_sent(0)
        logger.info(f"📤 First task sent: {first_task}")
    
    async def _send_task(self) -> None:
        """Send current task to Purple Agent (after advancement)."""
        assessment = self._assessment
        context = self._context
        shared_state = context.shared_state_manager
        
        current_index = assessment.current_index
        current_task = assessment.current_task_id
        current_benchmark = assessment.current_benchmark
        max_steps = assessment.max_steps
        max_tool_calls = assessment.max_tool_calls
        
        # Get previous benchmark for switch detection
        prev_task = assessment.get_task(current_index - 1)
        prev_benchmark = prev_task.benchmark if prev_task else None
        is_benchmark_switch = prev_benchmark != current_benchmark
        
        # Environment switching
        env_config = EnvironmentConfig(task_id=current_task, max_steps=max_steps)
        from src.environment.thread_executor import browser_executor
        
        pulse(ActivityType.HEARTBEAT, f"switching_to_task_{current_task}")
        
        if is_benchmark_switch:
            logger.info(f"Benchmark change ({prev_benchmark} -> {current_benchmark}): recreating environment")
        else:
            logger.info(f"Same benchmark ({current_benchmark}): using efficient task switch")
        
        await browser_executor.run(mcp_session_manager.switch_to_task, current_task, env_config)
        
        pulse(ActivityType.HEARTBEAT, f"env_switch_completed_{current_task}")
        
        # Update profile and tools
        profile = get_profile_for_task(current_task)
        if hasattr(mcp_observation_filter, "apply_profile"):
            mcp_observation_filter.apply_profile(profile)
        mcp_module.active_benchmark_profile = profile
        register_tools_for_benchmark(current_benchmark, mcp_app)
        
        # Reset shared state
        if shared_state:
            shared_state.reset_for_new_task(task_id=current_task, benchmark_id=current_benchmark)
            shared_state.update_tool_invocation("initialize_environment")
            shared_state.set_max_tool_calls(max_tool_calls)
        
        # Get task goal
        task_goal = None
        try:
            session = mcp_session_manager.get_session()
            if session and session.current_observation:
                task_goal = session.current_observation.get("goal", "")
        except Exception as e:
            logger.warning(f"Could not retrieve task goal: {e}")
        
        # Send message
        await self._send_task_message(
            task_id=current_task,
            benchmark=current_benchmark,
            profile=profile,
            task_goal=task_goal,
            max_tool_calls=max_tool_calls,
            is_first=False,
        )
        
        assessment.mark_task_sent(current_index)
        logger.info(f"📤 Task {current_index + 1}/{assessment.total_tasks} sent: {current_task}")
    
    async def _send_task_message(
        self,
        task_id: str,
        benchmark: str,
        profile: Any,
        task_goal: Optional[str],
        max_tool_calls: int,
        is_first: bool,
    ) -> None:
        """Build and send task message to Purple Agent."""
        context = self._context
        assessment = self._assessment
        
        mcp_session_id = context.mcp_session_id
        mcp_url = _get_mcp_url()
        tools_details = get_all_tools_metadata(benchmark)
        
        task_message = build_task_message(
            task_id=task_id,
            benchmark=benchmark,
            mcp_details={
                "url": mcp_url,
                "transport": "http",
                "session_id": mcp_session_id,
            },
            tools_details=tools_details,
            profile=profile,
            task_goal=task_goal,
            max_tool_calls=max_tool_calls,
        )
        
        # Add progress info
        current_index = assessment.current_index
        task_message += f"\n\nMULTI-TASK PROGRESS: Task {current_index + 1}/{assessment.total_tasks}.\n"
        
        # Send to Purple Agent
        purple_url = context.purple_agent_url
        await self._send_to_purple(purple_url, task_message)
    
    async def _send_to_purple(self, purple_url: str, text: str) -> None:
        """Send text message to Purple Agent via A2A."""
        import httpx
        from a2a.client import A2ACardResolver, ClientFactory, ClientConfig
        from a2a.types import Message, Role, Part, TextPart
        
        pulse(ActivityType.A2A_MESSAGE, f"sending_to_purple:{purple_url}")
        
        base_url = str(purple_url).rstrip("/")
        timeout = httpx.Timeout(300.0, connect=10.0, read=300.0, write=30.0)
        
        async with httpx.AsyncClient(timeout=timeout) as httpx_client:
            resolver = A2ACardResolver(httpx_client=httpx_client, base_url=base_url)
            purple_agent_card = await resolver.get_agent_card()
            client_config = ClientConfig(httpx_client=httpx_client, streaming=True)
            factory = ClientFactory(client_config)
            a2a_client = factory.create(purple_agent_card)
            
            message = Message(
                kind="message",
                role=Role.user,
                parts=[Part(root=TextPart(kind="text", text=text))],
                message_id=uuid4().hex,
            )
            
            send_result = a2a_client.send_message(message)
            if hasattr(send_result, "__aiter__"):
                async for _ in send_result:
                    pulse(ActivityType.A2A_MESSAGE, "purple_response_chunk")
            else:
                await send_result
        
        pulse(ActivityType.A2A_MESSAGE, "message_sent_complete")
    
    async def _wait_for_completion(self) -> None:
        """Wait for current task to complete."""
        assessment = self._assessment
        context = self._context
        shared_state = context.shared_state_manager
        
        # Validate shared state exists
        if not shared_state:
            logger.error("No shared state manager - cannot wait for completion")
            return
        
        current_task = assessment.current_task_id
        task_index = assessment.current_index
        
        # Check if already complete
        task_entry = assessment.get_task(task_index)
        if task_entry and task_entry.status.is_terminal():
            logger.info(f"Task {current_task} already completed")
            return
        
        logger.info(f"⏳ Waiting for task completion: {current_task}")
        
        # Snapshot for delta calculation
        assessment.snapshot_task_start(task_index)
        
        start_time = time.time()
        
        # Get or create watchdog (imported at top of module)
        watchdog = get_watchdog()
        if not watchdog:
            watchdog = create_watchdog(timeout_seconds=8.0, first_task_timeout=20.0)
        
        while time.time() - start_time < self._timeout_per_task:
            current_state = shared_state.read_state()
            
            # Check inactivity timeout
            if watchdog and watchdog.is_timed_out:
                time_since = watchdog.seconds_since_activity
                logger.warning(f"⏱️ Inactivity timeout: {current_task} ({time_since:.1f}s)")
                self._mark_task_failed(task_index, f"Inactivity timeout after {time_since:.1f}s", current_state)
                return
            
            # Check errors
            if current_state.error and not current_state.task_completed:
                logger.warning(f"Task failed: {current_task} - {current_state.error}")
                self._mark_task_failed(task_index, current_state.error, current_state)
                return
            
            # Check tool limit
            if current_state.tool_calls_exceeded:
                logger.warning(f"Tool limit exceeded: {current_task}")
                self._mark_task_failed(
                    task_index,
                    f"Tool call limit exceeded: {current_state.mcp_tool_invocations}/{current_state.max_tool_calls}",
                    current_state,
                    status=TaskStatus.TOOL_LIMIT,
                )
                return
            
            # Check completion
            if current_state.task_completed:
                success = bool(current_state.task_success)
                metrics = assessment.calculate_task_metrics(task_index)
                
                assessment.mark_task_completed(
                    index=task_index,
                    success=success,
                    reward=float(current_state.final_reward),
                    done=bool(current_state.done),
                    truncated=bool(current_state.truncated),
                    metrics=metrics,
                    status=TaskStatus.COMPLETED if success else TaskStatus.FAILED,
                    completion_time=time.time() - start_time,
                )
                
                status_emoji = "✓" if success else "✗"
                logger.info(f"{status_emoji} Task completed: {current_task}, reward={current_state.final_reward}")
                return
            
            await asyncio.sleep(0.5)
        
        # Total timeout
        logger.warning(f"Task timed out: {current_task}")
        current_state = shared_state.read_state()
        self._mark_task_failed(
            task_index,
            f"Total timeout after {self._timeout_per_task}s",
            current_state,
            status=TaskStatus.TIMEOUT,
        )
    
    def _mark_task_failed(
        self,
        task_index: int,
        error: str,
        state: Any,
        status: TaskStatus = TaskStatus.FAILED,
    ) -> None:
        """Mark task as failed with error."""
        assessment = self._assessment
        metrics = assessment.calculate_task_metrics(task_index)
        
        assessment.mark_task_completed(
            index=task_index,
            success=False,
            reward=float(state.final_reward) if state else 0.0,
            done=False,
            truncated=True,
            metrics=metrics,
            status=status,
            error=error,
        )
    
    def _finalize(self) -> Dict[str, Any]:
        """Finalize assessment and build artifact."""
        assessment = self._assessment
        context = self._context
        
        # Get results summary
        artifact = assessment.get_results_summary()
        
        # Update context
        context.evaluation_complete = True
        context.task_success = assessment.get_success_rate() > 0.5
        context.final_reward = assessment.get_success_rate()
        
        # Display summary
        assessment.display_summary()
        
        logger.info(f"📊 Assessment finalized: {assessment.get_passed_count()}/{assessment.total_tasks} passed")
        return artifact
    
    async def _cleanup(self) -> None:
        """Cleanup resources - browser sessions and MCP server."""
        global _mcp_server_task, _mcp_server_started
        
        logger.info("🧹 Starting orchestrator cleanup...")
        
        # Close browser sessions
        try:
            from src.environment.thread_executor import browser_executor
            logger.info("🧹 Closing browser sessions...")
            result = await browser_executor.run(mcp_session_manager.cleanup_all_sessions)
            logger.info(f"🧹 Browser sessions cleanup result: {result}")
        except Exception as e:
            logger.error(f"❌ Error closing browser sessions: {e}", exc_info=True)
        
        # Stop MCP server
        try:
            if _mcp_server_task and not _mcp_server_task.done():
                logger.info("🧹 Stopping MCP server...")
                _mcp_server_task.cancel()
                try:
                    await asyncio.wait_for(_mcp_server_task, timeout=2.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass
                logger.info("🧹 MCP server stopped")
            else:
                logger.info("🧹 MCP server was not running or already stopped")
        except Exception as e:
            logger.error(f"❌ Error stopping MCP server: {e}", exc_info=True)
        
        _mcp_server_started = False
        _mcp_server_task = None
        
        logger.info("✅ Orchestrator cleanup complete")


def start_orchestrator(assessment: Assessment, context: AgentContext, active_sessions: Optional[Dict[str, Any]] = None) -> asyncio.Task:
    """
    Start orchestrator in background task.
    
    Args:
        assessment: Assessment tracker
        context: Agent context
        active_sessions: Optional dict for status endpoint updates
        
    Returns:
        The asyncio.Task running the orchestrator
    """
    orchestrator = AssessmentOrchestrator(assessment, context, active_sessions)
    task = asyncio.create_task(orchestrator.run())
    assessment.set_orchestrator_running(task)
    return task


__all__ = ["AssessmentOrchestrator", "start_orchestrator"]
