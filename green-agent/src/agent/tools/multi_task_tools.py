"""
Multi-task orchestration tools for Green Agent LLM.

These tools allow the Green Agent to manage task progression:
- Send first task to Purple Agent
- Wait for Purple completion
- Send next task after completion (handles environment switching)
- Handle environment switching between benchmarks

Uses Assessment as the single source of truth for assessment state.
"""

import asyncio
import os
import time
from typing import Any, Dict
from agents.run_context import RunContextWrapper
from uuid import uuid4

from src.agent.context import AgentContext
from src.assessment import Assessment, TaskStatus
from src.utils.shared_state import DEFAULT_MAX_TOOL_CALLS, SharedStateManager
from src.utils.activity_watchdog import get_watchdog, pulse, ActivityType
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
from src.agent.tools.communication_tools import _build_task_message
import src.mcp.server as mcp_module
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Global state for multi-task orchestration
_mcp_server_task = None
_mcp_server_started = False
_mcp_server_port = 8001


async def send_first_task_to_purple_agent(ctx: RunContextWrapper[AgentContext]) -> dict:
    """
    Initialize multi-task assessment and send the first task to Purple Agent.
    
    This tool:
    1. Sets up MCP server for the multi-task run
    2. Creates initial environment session
    3. Sends first task message to Purple Agent
    4. Sets up monitoring for completion
    
    Returns:
        dict with status and first task details
    """
    context: AgentContext = ctx.context
    assessment: Assessment = context.assessment_tracker
    
    if not assessment:
        return {"status": "error", "message": "No Assessment in context"}
    
    if assessment.total_tasks == 0:
        return {"status": "error", "message": "No tasks in plan"}
    
    # Get first task from assessment
    first_task = assessment.current_task_id
    benchmark_id = assessment.current_benchmark
    max_steps = assessment.max_steps
    max_tool_calls = assessment.max_tool_calls
    
    try:
        # Initialize MCP server once for the whole multi-task run
        global _mcp_server_task, _mcp_server_started
        if not _mcp_server_started:
            _mcp_server_task = asyncio.create_task(start_http_server(port=_mcp_server_port))
            
            # Wait for server to be ready
            async def _wait_for_server(port: int, timeout: float = 15.0) -> bool:
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
            
            ready = await _wait_for_server(_mcp_server_port)
            if not ready:
                return {"status": "error", "message": f"MCP server failed to start on port {_mcp_server_port}"}
            _mcp_server_started = True
        
        mcp_url = f"http://localhost:{_mcp_server_port}/mcp"
        
        # Create shared state for MCP communication
        mcp_session_id = str(uuid4())
        os.environ["MCP_SESSION_ID"] = mcp_session_id
        shared_state = SharedStateManager(mcp_session_id)
        shared_state.initialize()
        context.shared_state_manager = shared_state
        context.mcp_session_id = mcp_session_id
        
        # Associate state manager with assessment for real-time state access
        assessment.set_state_manager(shared_state)
        
        # Set global MCP state
        mcp_module.shared_state = shared_state
        
        # Create initial environment session for first task
        profile = get_profile_for_task(first_task)
        if hasattr(mcp_observation_filter, "apply_profile"):
            mcp_observation_filter.apply_profile(profile)
        mcp_module.active_benchmark_profile = profile
        
        # Register benchmark tools
        register_tools_for_benchmark(benchmark_id, mcp_app)
        
        # Create environment session on dedicated browser thread
        env_config = EnvironmentConfig(task_id=first_task, max_steps=max_steps)
        
        from src.environment.thread_executor import browser_executor
        session = await browser_executor.run(mcp_session_manager.create_session, env_config)
        
        # Update shared state for first task
        shared_state.reset_for_new_task(task_id=first_task, benchmark_id=benchmark_id)
        shared_state.update_tool_invocation("initialize_environment")
        shared_state.set_max_tool_calls(max_tool_calls)
        
        # Get task goal from session observation
        task_goal = None
        if session and session.current_observation:
            task_goal = session.current_observation.get("goal", "")
        
        # Build task message
        tools_details = get_all_tools_metadata(benchmark_id)
        task_message = _build_task_message(
            task_id=first_task,
            benchmark=benchmark_id,
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
        
        # Add multi-task progress info
        task_message += assessment.format_progress("initialized")
        
        # Send task to Purple Agent
        purple_url = context.purple_agent_url
        await _send_text_message_to_purple(purple_url, task_message)
        
        # Mark task as sent in tracker
        assessment.mark_task_sent(0)
        
        logger.info(f"📤 Sent first task to Purple Agent: {first_task}")
        
        return {
            "status": "success",
            "message": f"First task sent: {first_task}",
            "task_id": first_task,
            "benchmark": benchmark_id,
            "task_index": 0,
            "total_tasks": assessment.total_tasks,
            "next_action": "wait_for_purple_completion"
        }
        
    except Exception as e:
        logger.error(f"Failed to send first task: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


async def wait_for_purple_completion(ctx: RunContextWrapper[AgentContext], timeout_seconds: int = 120) -> dict:
    """
    Wait for Purple Agent to complete the current task.
    
    Monitors shared state for task completion signals from Purple Agent.
    
    Args:
        timeout_seconds: Maximum total time to wait for completion
        
    Returns:
        dict with completion status and task results
    """
    context: AgentContext = ctx.context
    assessment: Assessment = context.assessment_tracker
    shared_state = context.shared_state_manager
    
    if not assessment:
        return {"status": "error", "message": "No Assessment in context"}
    
    if not shared_state:
        return {"status": "error", "message": "No shared state available"}
    
    current_task = assessment.current_task_id
    task_index = assessment.current_index
    current_benchmark = assessment.current_benchmark
    
    # Check if task already completed
    task_entry = assessment.get_task(task_index)
    if task_entry and task_entry.status.is_terminal():
        logger.info(f"Task {current_task} already completed with status: {task_entry.status.value}")
        return {
            "status": "already_completed",
            "message": f"Task {current_task} already completed (status: {task_entry.status.value})",
            "task_id": current_task,
            "task_index": task_index,
            "next_action": "send_next_task_or_finish"
        }
    
    logger.info(f"⏳ Waiting for Purple Agent to complete task: {current_task}")
    
    # Snapshot state at task start for delta calculation
    assessment.snapshot_task_start(task_index)
    
    start_time = time.time()
    start_state = shared_state.read_state()
    
    # Use centralized ActivityWatchdog for inactivity tracking
    watchdog = get_watchdog()
    inactivity_timeout = watchdog.timeout_seconds if watchdog else 10.0
    
    while time.time() - start_time < timeout_seconds:
        current_state = shared_state.read_state()
        
        # Check for inactivity timeout
        if watchdog and watchdog.is_timed_out:
            time_since_activity = watchdog.seconds_since_activity
            logger.warning(f"⏱️ Purple Agent inactivity timeout: {current_task} ({time_since_activity:.1f}s)")
            
            shared_state.mark_task_completed(success=False, reason="inactivity_timeout")
            
            metrics = assessment.calculate_task_metrics(task_index)
            assessment.mark_task_completed(
                index=task_index,
                success=False,
                reward=float(current_state.final_reward) if current_state else 0.0,
                done=False,
                truncated=True,
                metrics=metrics,
                status=TaskStatus.TIMEOUT,
                error=f"Inactivity timeout after {time_since_activity:.1f}s",
                completion_time=time.time() - start_time,
            )
            
            return {
                "status": "inactivity_timeout",
                "message": f"Purple Agent inactive for {time_since_activity:.1f}s: {current_task}",
                "task_id": current_task,
                "task_index": task_index,
                "next_action": "send_next_task_or_finish"
            }
        
        # Check for errors
        if current_state.error and not current_state.task_completed:
            logger.warning(f"Task failed with error: {current_task} - {current_state.error}")
            
            shared_state.mark_task_completed(success=False, reason="error")
            
            metrics = assessment.calculate_task_metrics(task_index)
            assessment.mark_task_completed(
                index=task_index,
                success=False,
                reward=float(current_state.final_reward),
                done=False,
                truncated=True,
                metrics=metrics,
                status=TaskStatus.FAILED,
                error=current_state.error,
                completion_time=time.time() - start_time,
            )
            
            return {
                "status": "error",
                "message": f"Task failed: {current_state.error}",
                "task_id": current_task,
                "task_index": task_index,
                "next_action": "send_next_task_or_finish"
            }
        
        # Check for tool call limit exceeded
        if current_state.tool_calls_exceeded:
            logger.warning(f"Task terminated due to tool call limit: {current_task}")
            
            assessment.mark_task_completed(
                index=task_index,
                success=False,
                reward=float(current_state.final_reward),
                done=False,
                truncated=True,
                metrics={},
                status=TaskStatus.TOOL_LIMIT,
                error=f"Tool call limit exceeded: {current_state.mcp_tool_invocations}/{current_state.max_tool_calls}",
                completion_time=time.time() - start_time,
            )
            
            return {
                "status": "tool_limit_exceeded",
                "message": f"Tool call limit exceeded ({current_state.mcp_tool_invocations}/{current_state.max_tool_calls}): {current_task}",
                "task_id": current_task,
                "task_index": task_index,
                "next_action": "send_next_task_or_finish"
            }
        
        # Check for completion
        if current_state.task_completed:
            metrics = assessment.calculate_task_metrics(task_index)
            success = bool(current_state.task_success)
            
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
            
            context.final_reward = float(current_state.final_reward)
            context.error_message = None
            
            status_emoji = "✓" if success else "✗"
            logger.info(f"{status_emoji} Task completed: {current_task}, success={success}, reward={current_state.final_reward}")
            
            return {
                "status": "completed",
                "message": f"Task completed: {current_task}",
                "task_id": current_task,
                "task_index": task_index,
                "success": success,
                "reward": float(current_state.final_reward),
                "next_action": "send_next_task_or_finish"
            }
        
        await asyncio.sleep(0.5)
    
    # Total timeout
    logger.warning(f"Task timed out after {timeout_seconds}s: {current_task}")
    
    shared_state.mark_task_completed(success=False, reason="timeout")
    
    current_state = shared_state.read_state()
    metrics = assessment.calculate_task_metrics(task_index)
    
    assessment.mark_task_completed(
        index=task_index,
        success=False,
        reward=float(current_state.final_reward) if current_state else 0.0,
        done=False,
        truncated=True,
        metrics=metrics,
        status=TaskStatus.TIMEOUT,
        error=f"Total timeout after {timeout_seconds}s",
        completion_time=timeout_seconds,
    )
    
    return {
        "status": "timeout",
        "message": f"Task timed out after {timeout_seconds}s: {current_task}",
        "task_id": current_task,
        "task_index": task_index,
        "next_action": "send_next_task_or_finish"
    }


async def send_next_task_to_purple_agent(ctx: RunContextWrapper[AgentContext]) -> dict:
    """
    Send the CURRENT task (as set by Assessment.current_index) to Purple Agent.
    
    NOTE: This function does NOT advance to the next task - the main orchestration
    loop in main.py is responsible for calling assessment.advance_to_next_task()
    before calling this function. This tool just sends whatever task is current.
    
    Handles environment switching (reset for same benchmark, recreate for different).
    
    Returns:
        dict with task details or completion status
    """
    context: AgentContext = ctx.context
    assessment: Assessment = context.assessment_tracker
    shared_state = context.shared_state_manager
    
    if not assessment:
        return {"status": "error", "message": "No Assessment in context"}
    
    # Get CURRENT task (main.py already advanced the index)
    # DO NOT call advance_to_next_task() here - main loop handles that!
    current_index = assessment.current_index
    current_task = assessment.current_task_id
    current_benchmark = assessment.current_benchmark
    
    # Check if we're past the end of tasks
    if current_index >= assessment.total_tasks:
        return {
            "status": "all_tasks_completed",
            "message": f"All {assessment.total_tasks} tasks completed",
            "next_action": "finalize_multi_task_assessment"
        }
    
    # Check if already sent
    if assessment.is_task_sent(current_index):
        return {
            "status": "already_sent",
            "message": f"Task {current_index} already sent. Use wait_for_purple_completion.",
            "task_id": current_task,
            "next_action": "wait_for_purple_completion"
        }
    
    # Get previous benchmark to check for switch
    prev_task = assessment.get_task(current_index - 1)
    prev_benchmark = prev_task.benchmark if prev_task else None
    is_benchmark_switch = prev_benchmark != current_benchmark
    
    try:
        max_steps = assessment.max_steps
        max_tool_calls = assessment.max_tool_calls
        env_config = EnvironmentConfig(task_id=current_task, max_steps=max_steps)
        
        from src.environment.thread_executor import browser_executor
        
        pulse(ActivityType.HEARTBEAT, f"switching_to_task_{current_task}")
        
        if not is_benchmark_switch:
            logger.info(f"Same benchmark ({current_benchmark}): using efficient task switch")
            switch_result = await browser_executor.run(
                mcp_session_manager.switch_to_task, current_task, env_config
            )
        else:
            logger.info(f"Benchmark change ({prev_benchmark} -> {current_benchmark}): recreating environment")
            pulse(ActivityType.HEARTBEAT, f"creating_env_{current_benchmark}")
            switch_result = await browser_executor.run(
                mcp_session_manager.switch_to_task, current_task, env_config
            )
        
        if switch_result.get("status") != "success":
            return {"status": "error", "message": f"Failed to switch task: {switch_result.get('error')}"}
        
        pulse(ActivityType.HEARTBEAT, f"env_switch_completed_{current_task}")
        
        # Update benchmark-specific settings
        profile = get_profile_for_task(current_task)
        if hasattr(mcp_observation_filter, "apply_profile"):
            mcp_observation_filter.apply_profile(profile)
        mcp_module.active_benchmark_profile = profile
        
        register_tools_for_benchmark(current_benchmark, mcp_app)
        
        # Reset shared state for new task
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
        
        # Build task message
        mcp_session_id = context.mcp_session_id
        mcp_url = f"http://localhost:{_mcp_server_port}/mcp"
        tools_details = get_all_tools_metadata(current_benchmark)
        
        task_message = _build_task_message(
            task_id=current_task,
            benchmark=current_benchmark,
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
        
        env_action = "reset" if not is_benchmark_switch else "recreated"
        task_message += f"\n\nMULTI-TASK PROGRESS: Task {current_index + 1}/{assessment.total_tasks}. Environment {env_action}.\n"
        
        # Send to Purple Agent
        purple_url = context.purple_agent_url
        await _send_text_message_to_purple(purple_url, task_message)
        
        # Mark as sent
        assessment.mark_task_sent(current_index)
        
        logger.info(f"📤 Sent task {current_index + 1}/{assessment.total_tasks} to Purple Agent: {current_task}")
        
        return {
            "status": "success",
            "message": f"Task sent: {current_task}",
            "task_id": current_task,
            "benchmark": current_benchmark,
            "task_index": current_index,
            "total_tasks": assessment.total_tasks,
            "next_action": "wait_for_purple_completion"
        }
        
    except Exception as e:
        logger.error(f"Failed to send next task: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


async def finalize_multi_task_assessment(ctx: RunContextWrapper[AgentContext]) -> dict:
    """
    Finalize the multi-task assessment with validation and metrics.
    
    Returns:
        dict with final assessment results
    """
    context: AgentContext = ctx.context
    assessment: Assessment = context.assessment_tracker
    
    if not assessment:
        return {"status": "error", "message": "No Assessment in context"}
    
    # Get results summary from tracker
    final_results = assessment.get_results_summary()
    
    # Mark evaluation as complete
    context.evaluation_complete = True
    context.task_success = assessment.get_success_rate() > 0.5
    context.final_reward = assessment.get_success_rate()
    
    # Display summary
    assessment.display_summary()
    
    passed = assessment.get_passed_count()
    total = assessment.total_tasks
    
    logger.info(f"✅ Multi-task assessment finalized: {passed}/{total} tasks passed")
    
    return {
        "status": "finalized",
        "message": f"Assessment completed: {passed}/{total} tasks passed",
        "final_results": final_results,
        "success_rate": assessment.get_success_rate()
    }


async def _send_text_message_to_purple(purple_agent_url: str, text: str) -> None:
    """Send a plain-text A2A message to the Purple Agent."""
    import httpx
    from a2a.client import A2ACardResolver, ClientFactory, ClientConfig
    from a2a.types import Message, Role, Part, TextPart
    
    pulse(ActivityType.A2A_MESSAGE, f"sending_to_purple:{purple_agent_url}")
    
    base_url = str(purple_agent_url).rstrip("/")
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


__all__ = [
    "send_first_task_to_purple_agent",
    "wait_for_purple_completion", 
    "send_next_task_to_purple_agent",
    "finalize_multi_task_assessment"
]
