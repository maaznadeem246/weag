"""
A2A server for BrowserGym Green Agent.
Implements AgentBeats GreenAgent pattern for assessment orchestration.

Based on debate_judge.py from AgentBeats tutorial.
Includes /.well-known/agent.json endpoint per A2A discovery spec.
"""

import argparse
import asyncio
import sys
import json
import logging
import time
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from pathlib import Path
from uuid import uuid4
import os
import httpx
import uvicorn
from dotenv import load_dotenv
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from a2a.client import A2ACardResolver, ClientFactory, ClientConfig
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
    TaskState,
    Part,
    TextPart,
    DataPart,
    Message,
    Role,
)
from a2a.utils import new_agent_text_message

from src.utils.models import (
    EvalRequest,
    EvaluationSession,
    EvaluationStatus,
    MCPConnectionDetails,
    EvaluationArtifact,
)
from src.mcp import get_all_tools_metadata
from src.metrics.tracker import EfficiencyMetrics
from src.metrics.penalty_calculator import calculate_efficiency_penalty
from src.utils.shared_state import SharedStateManager, EvaluationState
from src.utils.activity_watchdog import (
    create_watchdog, 
    get_watchdog,
    pulse,
    ActivityType,
)
from src.agent.agent_factory import get_evaluation_agent
from src.agent.context import AgentContext
from src.agent.monitoring import BackgroundMonitor
from agents import Runner
from agents.exceptions import MaxTurnsExceeded
from src.a2a.agent_card import (
    create_agent_card,
    get_agent_card_dict,
    get_extended_agent_card,
)
from src.benchmarks import (
    get_benchmark_manager,
    create_assessment_task_plan,
    validate_assessment_config,
    DEFAULT_EVALUATION_BENCHMARKS,
)
from src.benchmarks.profiles import detect_benchmark
from src.assessment import Assessment, AssessmentConfig
from src.a2a.artifact_helpers import (
    get_metrics_from_state,
    calculate_final_score,
    create_evaluation_artifact,
    create_error_artifact,
    log_evaluation_completion
)
from src.a2a.validation_helpers import validate_evaluation_request
from src.mcp.mcp_management import comprehensive_cleanup
from src.utils.logging import get_logger


# Load environment variables
load_dotenv()

logger = get_logger(__name__)

# Best-effort: initialize Langfuse with blocked instrumentation scopes early,
# so OpenTelemetry spans from noisy libraries (e.g., A2A) don't get exported.
try:
    from langfuse import Langfuse
    from src.config.settings import settings

    blocked_list = getattr(settings, "langfuse_blocked_instrumentation_scopes", []) or []
    if (
        settings.langfuse_enabled
        and settings.langfuse_public_key
        and settings.langfuse_secret_key
        and blocked_list
    ):
        Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
            blocked_instrumentation_scopes=blocked_list,
            debug=settings.langfuse_debug,
        )
except Exception as e:
    # Tracing is optional; never fail app startup for this.
    logger.warning(f"Failed to initialize Langfuse early: {e}")
    pass




class BrowserGymGreenAgent:
    """
    Green Agent implementation for BrowserGym environment evaluation.
    
    Responsibilities:
    1. Accept A2A assessment requests from AgentBeats platform
    2. Spawn MCP server as subprocess for purple agent tool discovery
    3. Stream A2A task updates during evaluation
    4. Generate A2A artifacts with efficiency metrics and final score
    """
    
    def __init__(self):
        self._required_roles = ["purple_agent"]
        self._required_config_keys = ["task_id"]
        self._active_session: Optional[EvaluationSession] = None
        self._metrics = EfficiencyMetrics()
        self._shared_state_manager: Optional[SharedStateManager] = None
        self._evaluation_state: Optional[EvaluationState] = None
        self._evaluation_complete_event: Optional[asyncio.Event] = None  # Signal when background eval finishes
        self._background_monitor: Optional[Any] = None  # BackgroundMonitor instance
    
    def validate_request(self, request: EvalRequest) -> tuple[bool, str]:
        """
        Validate incoming A2A assessment request.
        
        Args:
            request: EvalRequest with participants and config
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        return validate_evaluation_request(
            request,
            self._required_roles,
            self._required_config_keys
        )
    
    def setup_context(self, req: EvalRequest) -> AgentContext:
        """
        Setup AgentContext from EvalRequest.
        
        Creates Assessment and AgentContext for LLM-first architecture.
        Called by executor to initialize context before Runner.run().
        
        Args:
            req: EvalRequest with participants and task config
            
        Returns:
            Configured AgentContext
        """
        start_time = datetime.now(timezone.utc)
        cfg = req.config or {}
        
        # Extract or use defaults
        default_task_id = cfg.get("default_task_id", "miniwob.click-test")
        default_benchmark = cfg.get("default_benchmark", "miniwob")
        
        # Check for multi-task mode FIRST (before using defaults)
        tasks_by_benchmark = cfg.get("tasks_by_benchmark")
        explicit_mode = cfg.get("mode")
        explicit_task_id = cfg.get("task_id")  # Only explicit task_id, no fallback
        benchmarks_in_cfg = cfg.get("benchmarks")  # Check if benchmarks array provided
        max_tasks_per_benchmark = cfg.get("max_tasks_per_benchmark")  # Check if max_tasks is set
        
        # Determine if truly multi-task:
        # - Explicit mode="multi" (with or without tasks_by_benchmark), OR
        # - tasks_by_benchmark dict present, OR
        # - benchmarks array present without explicit task_id, OR
        # - max_tasks_per_benchmark is set WITHOUT explicit task_id (auto-discover mode)
        is_multi = (
            explicit_mode == "multi"
            or isinstance(tasks_by_benchmark, dict)
            or (isinstance(benchmarks_in_cfg, list) and benchmarks_in_cfg and not explicit_task_id)
            or (max_tasks_per_benchmark is not None and not explicit_task_id)  # NEW: Auto-discover if max_tasks is set
        )
        
        # Now apply defaults based on mode
        task_id = explicit_task_id or default_task_id
        benchmark = cfg.get("benchmark", default_benchmark)
        run_id = str(cfg.get("run_id") or task_id)
        
        # Build participants map
        participants_map = {role: str(url) for role, url in req.participants.items()}
        primary_purple_url = str(req.participants.get("purple_agent")) if "purple_agent" in req.participants else str(list(req.participants.values())[0])
        
        # Docker override: If PURPLE_AGENT_URL env var is set, use it instead of localhost
        # This is needed because inside Docker, containers use service names, not localhost
        env_purple_url = os.environ.get("PURPLE_AGENT_URL")
        if env_purple_url:
            primary_purple_url = env_purple_url
            participants_map["purple_agent"] = env_purple_url
            # Purple URL configured (verbose logging disabled)
        
        # Extract purple_agent_id
        primary_purple_parsed = httpx.URL(primary_purple_url)
        purple_agent_id = primary_purple_parsed.path.strip("/").split("/")[-1] or run_id[:8]
        
        # Context setup (verbose logging disabled)
        
        # Check if tasks_by_benchmark has actual tasks (not just empty lists)
        has_explicit_tasks = (
            isinstance(tasks_by_benchmark, dict) 
            and any(len(tasks) > 0 for tasks in tasks_by_benchmark.values())
        )
        
        # Create Assessment for multi-task or single task
        if is_multi and has_explicit_tasks:
            # Multi-task with explicit tasks from TOML
            benchmark_manager = get_benchmark_manager()
            task_plan_data = benchmark_manager.create_task_plan(specific_tasks=tasks_by_benchmark)
            benchmarks = task_plan_data["benchmarks"]
        elif is_multi:
            # Multi mode without explicit tasks - auto-discover or use defaults
            benchmarks_list = cfg.get("benchmarks") or []
            if not benchmarks_list:
                # No benchmarks specified - use defaults
                from src.benchmarks import DEFAULT_EVALUATION_BENCHMARKS
                benchmarks_list = DEFAULT_EVALUATION_BENCHMARKS
            
            # Discover tasks for each benchmark
            from src.benchmarks import discover_tasks_for_benchmark
            max_tasks_per_benchmark = cfg.get("max_tasks_per_benchmark", 5)
            tasks_by_benchmark = {}
            
            for benchmark_id in benchmarks_list:
                try:
                    discovered = discover_tasks_for_benchmark(benchmark_id, max_tasks_per_benchmark)
                    tasks_by_benchmark[benchmark_id] = discovered
                    # Discovered tasks (verbose logging disabled)
                except Exception as e:
                    logger.warning(f"Failed to discover tasks for {benchmark_id}: {e}")
                    tasks_by_benchmark[benchmark_id] = []
            
            benchmarks = benchmarks_list
        else:
            # Single task mode - create single-task assessment
            benchmarks = [benchmark]
            tasks_by_benchmark = {benchmark: [task_id]}
        
        assessment_config = AssessmentConfig(
            run_id=run_id,
            benchmarks=benchmarks,
            tasks_by_benchmark=tasks_by_benchmark,
            max_steps=cfg.get("max_steps", 10),
            max_tool_calls=cfg.get("max_tool_calls", 12),
            timeout_seconds=cfg.get("timeout_seconds", 300),
            primary_participant_url=primary_purple_url,
        )
        assessment = Assessment(assessment_config)
        
        # Create AgentContext
        context = AgentContext(
            task_id=task_id if not is_multi else "multi-task-orchestration",
            benchmark=benchmark if not is_multi else "multi",
            default_task_id=default_task_id,
            default_benchmark=default_benchmark,
            purple_agent_url=primary_purple_url,
            purple_agent_id=purple_agent_id,
            participants=participants_map,
            mcp_server_spawned=False,
            mcp_session_id=str(uuid4()),
            session_id=str(uuid4()),
            current_step=0,
            evaluation_complete=False,
            task_success=False,
            final_reward=0.0,
            error_message=None,
            shared_state_manager=None,  # Created by orchestrator
            task_updater=None,  # Not needed in new architecture
            active_sessions=_active_sessions,  # Pass for status endpoint updates
            start_time=start_time,
            timeout_seconds=cfg.get("timeout_seconds", 300),
            background_monitor_interval=3.0,
            incoming_messages=[],
            assessment_tracker=assessment,
        )
        
        # Context created (verbose logging disabled)
        return context
    
    async def run_eval(self, req: EvalRequest, updater: TaskUpdater) -> None:
        """
        Main evaluation orchestration method.
         
        Args:
            req: EvalRequest containing purple agent endpoint and task config
            updater: TaskUpdater for streaming A2A task updates
        """
        # Check if unified tracing is enabled
        assessment_trace_id = os.environ.get("ASSESSMENT_TRACE_ID")
        
        if assessment_trace_id:
            try:
                from langfuse import observe, get_client
                langfuse_client = get_client()
                
                # Wrap the actual evaluation in @observe
                @observe(name="GreenAgent-Evaluation", as_type="agent")
                async def run_evaluation_traced(request, task_updater):
                    """Run evaluation with tracing linked to parent trace."""
                    # Add time debug info to the execution span
                    from langfuse import get_client
                    lf = get_client()
                    
                    # Get unique assessment ID if available
                    assessment_id = os.environ.get("ASSESSMENT_ID")
                    
                    # Set trace-level session id and metadata, then add span metadata
                    if assessment_id:
                        try:
                            lf.update_current_trace(
                                session_id=assessment_id,
                                metadata={"assessment_id": assessment_id},
                            )
                        except Exception:
                            # Older Langfuse clients may not support update_current_trace
                            pass

                    lf.update_current_span(
                        metadata={
                            "assessment_id": assessment_id,
                            "time_debug": {
                                "iso_now": datetime.now().isoformat(),
                                "local_now": time.ctime(),
                                "tz": time.tzname[0]
                            }
                        }
                    )
                    return await self._run_eval_internal(request, task_updater)
                
                # Execute with trace linking
                await run_evaluation_traced(
                    req,
                    updater,
                    langfuse_trace_id=assessment_trace_id
                )
                return
                
            except Exception as e:
                logger.warning(f"⚠ Green Agent: Failed to run with unified tracing: {e}")
                # Fallback to running without tracing
        
        # No unified tracing or error - run directly
        await self._run_eval_internal(req, updater)
    
    async def _run_eval_internal(self, req: EvalRequest, updater: TaskUpdater) -> None:
        """
        Internal evaluation method using OpenAI Agent SDK for orchestration.
        
        Args:
            req: EvalRequest containing purple agent endpoint(s) and optional task config
            updater: TaskUpdater for streaming A2A task updates
        """
        start_time = datetime.now(timezone.utc)
        
        # Get the evaluation agent from factory
        agent = get_evaluation_agent()
        
        cfg = req.config or {}

        # Extract or use defaults for task_id and benchmark
        default_task_id = cfg.get("default_task_id", "miniwob.click-test")
        default_benchmark = cfg.get("default_benchmark", "miniwob")

        task_id = cfg.get("task_id", default_task_id)
        benchmark = cfg.get("benchmark", default_benchmark)

        # Multi-task mode: run_id identifies this assessment for polling
        run_id = str(cfg.get("run_id") or task_id)

        tasks_by_benchmark = cfg.get("tasks_by_benchmark")
        is_multi = cfg.get("mode") == "multi" or isinstance(tasks_by_benchmark, dict)
        
        context_id = str(uuid4())
        
        # Build participants map from req.participants (supports multiple purple agents)
        participants_map = {role: str(url) for role, url in req.participants.items()}
        
        # Get primary purple agent (first participant or one named "purple_agent")
        primary_purple_url = str(req.participants.get("purple_agent")) if "purple_agent" in req.participants else str(list(req.participants.values())[0])
        
        # Extract purple_agent_id from primary URL for message prefixing (A2A requirement)
        primary_purple_parsed = httpx.URL(primary_purple_url)
        purple_agent_id = primary_purple_parsed.path.strip("/").split("/")[-1] or context_id[:8]

        # Log task start
        logger.info("-" * 60)
        logger.info(f"TASK STARTED: {task_id}")
        logger.info(f"Benchmark: {benchmark}")
        logger.info(f"Max Steps: {agent_context.max_steps}")
        logger.info(f"Timeout: {agent_context.timeout_seconds}s")
        logger.info("-" * 60)
        
        # Safe update helper that ignores terminal-state race conditions
        async def safe_update_status(state, message):
            try:
                await updater.update_status(state=state, message=message)
            except Exception as re:
                # Use general Exception to catch SDK-specific errors as well
                logger.debug(f"Could not update task status (ignoring): {re}")
                
        try:
            if is_multi:
                # Use benchmark manager to create task plan
                if tasks_by_benchmark:
                    # Use provided tasks_by_benchmark
                    benchmark_manager = get_benchmark_manager()
                    task_plan_data = benchmark_manager.create_task_plan(
                        specific_tasks=tasks_by_benchmark
                    )
                    benchmarks = task_plan_data["benchmarks"]
                    task_plan = []
                    for tasks_list in task_plan_data["tasks_by_benchmark"].values():
                        task_plan.extend(tasks_list)
                else:
                    # Auto-discover tasks from available benchmarks
                    task_plan_data = create_assessment_task_plan(
                        max_tasks_per_benchmark=cfg.get("max_tasks_per_benchmark", 5)
                    )
                    benchmarks = task_plan_data["benchmarks"]
                    tasks_by_benchmark = task_plan_data["tasks_by_benchmark"]
                    task_plan = []
                    for tasks_list in task_plan_data["tasks_by_benchmark"].values():
                        task_plan.extend(tasks_list)
                
                # Register session for status queries (for kickstart script)
                _active_sessions[run_id] = {
                    "state": "submitted",
                    "task_id": task_id,
                    "run_id": run_id,
                    "result": None,
                }

                await safe_update_status(
                    state=TaskState.submitted,
                    message=new_agent_text_message(f"Assessment request received (multi-task run_id={run_id})"),
                )
                await safe_update_status(
                    state=TaskState.working,
                    message=new_agent_text_message("Initializing multi-task BrowserGym assessment"),
                )

                # Run multi-task assessment with LLM orchestration
                self._evaluation_complete_event = asyncio.Event()
                
                # Create Assessment (single source of truth for assessment state)
                assessment_config = AssessmentConfig(
                    run_id=run_id,
                    benchmarks=benchmarks,
                    tasks_by_benchmark=tasks_by_benchmark,
                    max_steps=cfg.get("max_steps", 10),
                    max_tool_calls=cfg.get("max_tool_calls", 12),
                    timeout_seconds=cfg.get("timeout_seconds", 300),
                    primary_participant_url=primary_purple_url,
                )
                assessment = Assessment(assessment_config)
                
                # Log assessment start
                logger.info("\n" + "="*70)
                logger.info("🚀 ASSESSMENT STARTED")
                logger.info(f"Run ID: {run_id}")
                logger.info(f"Total Tasks: {assessment.total_tasks}")
                logger.info(f"Benchmarks: {', '.join(benchmarks)}")
                for bench, tasks in tasks_by_benchmark.items():
                    logger.info(f"  • {bench}: {len(tasks)} tasks")
                logger.info(f"Max Steps/Task: {assessment_config.max_steps}")
                logger.info(f"Timeout: {assessment_config.timeout_seconds}s")
                logger.info(f"Purple Agent: {primary_purple_url}")
                logger.info("="*70 + "\n")
                
                # Log assessment start with details
                logger.info("=" * 60)
                logger.info("ASSESSMENT STARTED")
                logger.info(f"Run ID: {run_id}")
                logger.info(f"Total Tasks: {assessment.total_tasks}")
                logger.info(f"Benchmarks: {', '.join(benchmarks)}")
                logger.info(f"Max Steps: {assessment_config.max_steps}")
                logger.info(f"Timeout: {assessment_config.timeout_seconds}s")
                logger.info(f"Purple Agent: {primary_purple_url}")
                logger.info("=" * 60)
                
                # Create agent context for multi-task orchestration
                agent_context = AgentContext(
                    task_id="multi-task-orchestration",
                    benchmark="multi",
                    default_task_id="multi",
                    default_benchmark="multi",
                    purple_agent_url=primary_purple_url,
                    purple_agent_id=purple_agent_id,
                    participants=participants_map,
                    mcp_server_spawned=False,
                    mcp_session_id=str(uuid4()),
                    session_id=str(uuid4()),
                    current_step=0,
                    evaluation_complete=False,
                    task_success=False,
                    final_reward=0.0,
                    error_message=None,
                    shared_state_manager=None,  # Will be created in agent tools
                    task_updater=updater,
                    start_time=start_time,
                    timeout_seconds=cfg.get("timeout_seconds", 300),
                    background_monitor_interval=3.0,
                    incoming_messages=[],  # For Purple completion messages
                    # Assessment (single source of truth)
                    assessment_tracker=assessment,
                )
                
                # ================================================================
                # LLM MULTI-TASK LOOP (orchestrated with programmatic prompting)
                # ================================================================
                # The LLM orchestrates the flow, but we use a programmatic loop
                # to ensure it processes all tasks by sending internal_system
                # messages between iterations.
                # ================================================================
                
                from agents import Runner
                from src.agent.sessions.session_storage import create_session
                
                # Multi-task orchestration uses max_turns per prompt (explicit instructions)
                # Each Runner.run() call should complete the requested tool call
                max_turns_per_prompt = int(os.getenv("GREEN_MAX_TURNS_PER_PROMPT", "10"))
                
                try:
                    # Starting multi-task loop (verbose logging disabled)
                    
                    # Create activity watchdog with differentiated timeouts:
                    # - 20s initial timeout (before first interaction - browser setup)
                    # - 8s after first pulse (once Purple Agent starts interacting)
                    watchdog = create_watchdog(
                        timeout_seconds=8.0,         # Pulse timeout after first interaction
                        first_task_timeout=20.0      # Initial timeout until first real interaction
                    )
                    # ActivityWatchdog created (verbose logging disabled)
                    
                    # Create in-memory session for conversation history
                    multi_task_session_id = str(uuid4())
                    session = create_session(session_id=multi_task_session_id, use_persistent=False)
                    # Session created (verbose logging disabled)
                    
                    # Reuse agent instance already created at function start
                    
                    # Step 1: Initial prompt - send first task
                    current_task_index = 0
                    initial_prompt = (
                        f"internal_system: Starting multi-task assessment with {len(task_plan)} tasks. "
                        f"Task plan: {task_plan}. "
                        f"Purple agent ready at {agent_context.purple_agent_url}. "
                        f"CALL send_first_task_to_purple_agent() NOW to start task 1/{len(task_plan)}."
                    )
                    
                    # Task 1 flow (verbose logging disabled)
                    
                    # Use watchdog.track() context manager for clean activity tracking
                    try:
                        async with watchdog.track("runner_first_task"):
                            result = await watchdog.wait_with_timeout(
                                Runner.run(
                                    agent,
                                    initial_prompt,
                                    context=agent_context,
                                    session=session,
                                    max_turns=max_turns_per_prompt
                                )
                            )
                    except (asyncio.TimeoutError, asyncio.CancelledError) as e:
                        error_type = "cancelled" if isinstance(e, asyncio.CancelledError) else "inactivity_timeout"
                        logger.error(f"❌ [FLOW] Task 1 TIMEOUT during send_first_task: {error_type}")
                        # Mark first task as failed due to timeout
                        shared_state = agent_context.shared_state_manager
                        first_task_id = task_plan[0]
                        if shared_state:
                            shared_state.mark_task_completed(success=False, reason="inactivity_timeout")
                        # Flow logging disabled (verbose)
                        
                        # Mark task as failed in assessment
                        from src.assessment import TaskStatus
                        assessment.mark_task_completed(
                            index=0,
                            success=False,
                            reward=0.0,
                            done=False,
                            truncated=True,
                            metrics={},
                            status=TaskStatus.SEND_TIMEOUT,
                            error=f"Timeout during send_first_task: {first_task_id}",
                            completion_time=0.0,
                        )
                        
                        # Continue to next task instead of crashing
                        current_task_index = 1
                        # Flow logging disabled (verbose)
                    
                    # Step 2: Loop through remaining tasks
                    # Loop structure: For each task index, wait for completion then send next
                    # The send_first_task already sent task 0, so we start by waiting for it
                    
                    while True:
                        current_task_index = assessment.current_index
                        # Flow logging disabled (verbose)
                        
                        if current_task_index >= len(task_plan):
                            # Flow logging disabled (verbose)
                            break
                        
                        task_id_current = task_plan[current_task_index]
                        timeout_per_task = agent_context.timeout_seconds // max(1, len(task_plan))
                        # Per-task timeout is now less critical since we have 12s inactivity timeout
                        # Keep it reasonable for legitimate tasks but not excessive
                        timeout_per_task = max(30, min(timeout_per_task, 90))  # 30-90 seconds per task (safety net)
                        
                        # Check if this task was actually sent using tracker
                        task_was_sent = assessment.is_task_sent(current_task_index)
                        
                        if not task_was_sent:
                            # Task was NOT sent (e.g., timeout occurred before send completed)
                            # We need to SEND it now before waiting for it
                            # Flow logging disabled (verbose)
                            
                            send_prompt = (
                                f"internal_system: Need to send task {current_task_index + 1}/{len(task_plan)} ({task_id_current}). "
                                f"CALL send_next_task_to_purple_agent() NOW."
                            )
                            
                            try:
                                async with watchdog.track(f"send_task_{current_task_index + 1}"):
                                    result = await watchdog.wait_with_timeout(
                                        Runner.run(
                                            agent,
                                            send_prompt,
                                            context=agent_context,
                                            session=session,
                                            max_turns=max_turns_per_prompt
                                        )
                                    )
                                
                                # Verify the task was actually sent after LLM run
                                if not assessment.is_task_sent(current_task_index):
                                    logger.error(f"❌ [FLOW] LLM did not call send_next_task_to_purple_agent for task {current_task_index + 1}")
                                    # Mark task as failed
                                    from src.assessment import TaskStatus
                                    assessment.mark_task_completed(
                                        index=current_task_index,
                                        success=False,
                                        reward=0.0,
                                        done=False,
                                        truncated=True,
                                        metrics={},
                                        status=TaskStatus.SEND_TIMEOUT,
                                        error=f"LLM failed to call send tool: {task_id_current}",
                                        completion_time=0.0,
                                    )
                                    # Advance to next task - if no more tasks, break
                                    if not assessment.advance_to_next_task():
                                        # Flow logging disabled (verbose)
                                        break
                                    # Flow logging disabled (verbose)
                                    continue
                                    
                            except (asyncio.TimeoutError, asyncio.CancelledError) as e:
                                error_type = "cancelled" if isinstance(e, asyncio.CancelledError) else "inactivity_timeout"
                                logger.error(f"❌ [FLOW] Task {current_task_index + 1} TIMEOUT during send attempt: {error_type}")
                                # Mark task as failed and move to next
                                if agent_context.shared_state_manager:
                                    agent_context.shared_state_manager.mark_task_completed(success=False, reason="send_timeout")
                                # Flow logging disabled (verbose)
                                
                                # Mark task as failed in assessment
                                from src.assessment import TaskStatus
                                assessment.mark_task_completed(
                                    index=current_task_index,
                                    success=False,
                                    reward=0.0,
                                    done=False,
                                    truncated=True,
                                    metrics={},
                                    status=TaskStatus.SEND_TIMEOUT,
                                    error=f"Timeout during send attempt: {task_id_current}",
                                    completion_time=0.0,
                                )
                                
                                # Advance to next task in assessment - if no more tasks, break
                                if not assessment.advance_to_next_task():
                                    # Flow logging disabled (verbose)
                                    break
                                # Flow logging disabled (verbose)
                                continue
                        
                        # Flow logging disabled (verbose)
                        
                        # Wait prompt: Tell LLM to call wait_for_purple_completion
                        wait_prompt = (
                            f"internal_system: Task {current_task_index + 1}/{len(task_plan)} ({task_id_current}) sent. "
                            f"CALL wait_for_purple_completion(timeout_seconds={timeout_per_task}) NOW to wait for completion."
                        )
                        
                        # Use watchdog.track() context manager - auto pulses on entry/exit
                        # logger.info(f"⏳ Waiting for Purple Agent (watchdog: {watchdog.timeout_seconds}s inactivity timeout)...")
                        try:
                            async with watchdog.track(f"wait_task_{current_task_index + 1}"):
                                result = await watchdog.wait_with_timeout(
                                    Runner.run(
                                        agent,
                                        wait_prompt,
                                        context=agent_context,
                                        session=session,
                                        max_turns=max_turns_per_prompt
                                    )
                                )
                            # logger.info("✓ Runner.run completed successfully for wait prompt")
                        except (asyncio.TimeoutError, asyncio.CancelledError) as e:
                            error_type = "cancelled" if isinstance(e, asyncio.CancelledError) else "inactivity_timeout"
                            logger.error(f"❌ [FLOW] Task {current_task_index + 1} TIMEOUT during wait_for_purple_completion: {error_type}")
                            
                            # Mark first task completed for timeout adjustment (even on failure)
                            if current_task_index == 0:
                                watchdog.mark_first_task_completed()
                            
                            # Mark task as failed and continue
                            if agent_context.shared_state_manager:
                                agent_context.shared_state_manager.mark_task_completed(success=False, reason="inactivity_timeout")
                            # Flow logging disabled (verbose)
                            
                            # Mark task as failed in assessment
                            from src.assessment import TaskStatus
                            assessment.mark_task_completed(
                                index=current_task_index,
                                success=False,
                                reward=0.0,
                                done=False,
                                truncated=True,
                                metrics={},
                                status=TaskStatus.TIMEOUT,
                                error=f"Inactivity timeout during wait: {task_id_current}",
                                completion_time=0.0,
                            )
                            
                            # Advance to next task - if no more tasks, break
                            if not assessment.advance_to_next_task():
                                # Flow logging disabled (verbose)
                                break
                            # Flow logging disabled (verbose)
                            continue
                        
                        # Check task completion status from tracker
                        current_task_entry = assessment.get_task(current_task_index)
                        last_task_completed = current_task_entry and current_task_entry.status.is_terminal()
                        last_task_success = current_task_entry.success if current_task_entry else False
                        last_task_status = current_task_entry.status.value if current_task_entry else "unknown"
                        
                        # Log task completion status
                        status_emoji = "✓" if last_task_success else "✗"
                        # Flow logging disabled (verbose)
                        
                        # Mark first task completion for ActivityWatchdog timeout adjustment
                        if current_task_index == 0:  # First task (0-indexed)
                            watchdog.mark_first_task_completed()
                        
                        if not last_task_completed:
                            # Flow logging disabled (verbose)
                            # Mark as failed in assessment
                            from src.assessment import TaskStatus
                            assessment.mark_task_completed(
                                index=current_task_index,
                                success=False,
                                reward=0.0,
                                done=False,
                                truncated=True,
                                metrics={},
                                status=TaskStatus.FAILED,
                                error=f"Task completion not detected: {task_id_current}",
                                completion_time=0.0,
                            )
                        
                        # Move to next task using tracker
                        assessment.advance_to_next_task()
                        next_index = assessment.current_index
                        # Flow logging disabled (verbose)
                        
                        # Check if there are more tasks to run
                        if next_index < len(task_plan):
                            next_task_id = task_plan[next_index]
                            next_benchmark = detect_benchmark(next_task_id) or "unknown"
                            
                            # Log task change
                            logger.info("-"*70)
                            logger.info(f"🔄 SWITCHING TO NEXT TASK ({next_index + 1}/{len(task_plan)})")
                            logger.info(f"New Task: {next_task_id}")
                            logger.info(f"Benchmark: {next_benchmark}")
                            logger.info("-"*70)
                            
                            # Flow logging disabled (verbose)
                            next_prompt = (
                                f"internal_system: Task {current_task_index + 1}/{len(task_plan)} ({task_id_current}) finished with status={last_task_status}. "
                                f"CALL send_next_task_to_purple_agent() NOW to start task {next_index + 1}/{len(task_plan)} ({next_task_id})."
                            )
                            
                            # Use watchdog.track() context manager for clean activity tracking
                            try:
                                async with watchdog.track(f"send_next_task_{next_index + 1}"):
                                    result = await watchdog.wait_with_timeout(
                                        Runner.run(
                                            agent,
                                            next_prompt,
                                            context=agent_context,
                                            session=session,
                                            max_turns=max_turns_per_prompt
                                        )
                                    )
                                
                                # Verify the task was actually sent after LLM run
                                if not assessment.is_task_sent(next_index):
                                    logger.error(f"❌ [FLOW] LLM did not call send_next_task_to_purple_agent for task {next_index + 1}")
                                    # Mark task as failed
                                    assessment.mark_task_completed(
                                        index=next_index,
                                        success=False,
                                        reward=0.0,
                                        done=False,
                                        truncated=True,
                                        metrics={},
                                        status=TaskStatus.SEND_TIMEOUT,
                                        error=f"LLM failed to call send tool: {next_task_id}",
                                        completion_time=0.0,
                                    )
                                    # Advance to next task - if no more tasks, break
                                    if not assessment.advance_to_next_task():
                                        # Flow logging disabled (verbose)
                                        break
                                    # Flow logging disabled (verbose)
                                    continue
                                    
                            except (asyncio.TimeoutError, asyncio.CancelledError) as e:
                                error_type = "cancelled" if isinstance(e, asyncio.CancelledError) else "inactivity_timeout"
                                logger.error(f"❌ [FLOW] Task {next_index + 1} TIMEOUT during send_next_task: {error_type}")
                                # Mark this task as failed due to timeout
                                if agent_context.shared_state_manager:
                                    agent_context.shared_state_manager.mark_task_completed(success=False, reason="inactivity_timeout")
                                # Flow logging disabled (verbose)
                                
                                # Mark task as failed in assessment
                                assessment.mark_task_completed(
                                    index=next_index,
                                    success=False,
                                    reward=0.0,
                                    done=False,
                                    truncated=True,
                                    metrics={},
                                    status=TaskStatus.SEND_TIMEOUT,
                                    error=f"Timeout during send_next_task: {next_task_id}",
                                    completion_time=0.0,
                                )
                                
                                # Advance to next task - if no more tasks, break
                                if not assessment.advance_to_next_task():
                                    # Flow logging disabled (verbose)
                                    break
                                # Flow logging disabled (verbose)
                                continue
                        else:
                            # Flow logging disabled (verbose)
                            break
                    
                    # Step 3: Finalize assessment (programmatically, not via LLM)
                    # Finalizing assessment (verbose logging disabled)
                    
                    # Import and call finalize directly
                    from src.agent.tools.multi_task_tools import finalize_multi_task_assessment
                    from agents.run_context import RunContextWrapper
                    
                    ctx_wrapper = RunContextWrapper(context=agent_context)
                    finalization_result = await finalize_multi_task_assessment(ctx_wrapper)
                    
                    final_results = assessment.get_results_summary()
                    
                    # Log assessment completion
                    success_count = sum(1 for t in assessment.results_by_task.values() if t.get("task_success"))
                    total = len(task_plan)
                    logger.info("\n" + "="*70)
                    logger.info("✅ ASSESSMENT COMPLETED")
                    logger.info(f"Run ID: {run_id}")
                    logger.info(f"Total Tasks: {total}")
                    logger.info(f"Successful: {success_count}/{total}")
                    logger.info(f"Success Rate: {success_count/total*100:.1f}%")
                    logger.info("\nTask Results:")
                    for task_id, result in assessment.results_by_task.items():
                        status = "✓" if result.get("task_success") else "✗"
                        score = result.get("final_score", 0.0)
                        benchmark = result.get("benchmark", "unknown")
                        logger.info(f"  {status} {task_id} ({benchmark}): score={score:.2f}")
                    logger.info("="*70 + "\n")
                    
                    _active_sessions[run_id] = {
                        "state": "complete",
                        "run_id": run_id,
                        "task_id": "multi",
                        "result": {
                            "mode": "multi",
                            "run_id": run_id,
                            "participants": final_results.get("participants", {}),
                            "total_tasks": len(task_plan),
                            "success_rate": assessment.get_success_rate(),
                            "llm_orchestration": True,
                        }
                    }
                    
                    # Log assessment completion with results
                    success_count = sum(1 for t in assessment.results_by_task.values() if t.get("task_success"))
                    logger.info("=" * 60)
                    logger.info("ASSESSMENT COMPLETED")
                    logger.info(f"Run ID: {run_id}")
                    logger.info(f"Total Tasks: {len(task_plan)}")
                    logger.info(f"Successful: {success_count}/{len(task_plan)}")
                    logger.info(f"Success Rate: {success_count/len(task_plan)*100:.1f}%")
                    for task_id, result in assessment.results_by_task.items():
                        status = "✓" if result.get("task_success") else "✗"
                        score = result.get("final_score", 0.0)
                        logger.info(f"  {status} {task_id}: score={score:.2f}")
                    logger.info("=" * 60)
                    
                except Exception as e:
                    logger.error(f"Multi-task orchestration failed: {e}", exc_info=True)
                    
                    # Finalize assessment even on failure to capture partial results
                    try:
                        from src.agent.tools.multi_task_tools import finalize_multi_task_assessment
                        from agents.run_context import RunContextWrapper
                        
                        ctx_wrapper = RunContextWrapper(context=agent_context)
                        finalization_result = await finalize_multi_task_assessment(ctx_wrapper)
                        # Finalized with partial results (verbose logging disabled)
                    except Exception as fin_error:
                        logger.warning(f"Failed to finalize assessment: {fin_error}")
                    
                    final_results = assessment.get_results_summary() if assessment else {}
                    
                    _active_sessions[run_id] = {
                        "state": "failed",
                        "run_id": run_id,
                        "error": str(e),
                        "partial_results": final_results.get("participants", {}),  # Include partial results
                        "total_tasks": len(task_plan) if 'task_plan' in locals() else 0,
                    }
                
                return

            # Create evaluation session (using primary purple agent)
            self._active_session = EvaluationSession(
                task_id=task_id,
                purple_agent_endpoint=primary_purple_url,
                status=EvaluationStatus.CREATED
            )
            
            # Generate session ID for MCP and shared state
            session_id = str(uuid4())
            
            # Create shared state manager for monitoring
            self._shared_state_manager = SharedStateManager(session_id)
            
            # Create agent context for the evaluation
            agent_context = AgentContext(
                task_id=task_id,
                benchmark=benchmark,
                default_task_id=default_task_id,
                default_benchmark=default_benchmark,
                purple_agent_url=primary_purple_url,
                purple_agent_id=purple_agent_id,
                participants=participants_map,
                mcp_server_spawned=False,
                mcp_session_id=session_id,
                session_id=session_id,
                current_step=0,
                evaluation_complete=False,
                task_success=False,
                final_reward=0.0,
                error_message=None,
                shared_state_manager=self._shared_state_manager,
                task_updater=updater,
                start_time=start_time,
                timeout_seconds=req.config.get("timeout_seconds", 300),
                background_monitor_interval=3.0,  # Background monitor polls every 3 seconds
                incoming_messages=[]  # Initialize empty message queue
            )
            
            # Register session for status queries (for kickstart script)
            _active_sessions[run_id] = {
                "state": "submitted",
                "task_id": task_id,
                "run_id": run_id,
                "result": None
            }
            
            # Safe update helper that ignores terminal-state race conditions
            async def safe_update_status(state, message):
                try:
                    await updater.update_status(state=state, message=message)
                except RuntimeError as re:
                    logger.warning(f"Could not update task status (may already be terminal): {re}")

            # Stream initial "submitted" status (required by A2A protocol)
            await safe_update_status(
                state=TaskState.submitted,
                message=new_agent_text_message(f"Assessment request received for task: {task_id}")
            )

            # Stream "working" status when starting evaluation
            await safe_update_status(
                state=TaskState.working,
                message=new_agent_text_message(f"Initializing BrowserGym evaluation for task: {task_id}")
            )
            
            # Step 1: Build MCP connection details for purple agent (HTTP transport)
            # Note: MCP server will start on-demand when Purple Agent calls initialize_environment
            mcp_url = get_mcp_url()
            
            # Extract tool metadata for documentation
            benchmark = task_id.split('.')[0] if '.' in task_id else task_id
            tools_details = get_all_tools_metadata(benchmark)
            
            # Build MCPConnectionDetails for agent/context usage (HTTP transport)
            mcp_details = MCPConnectionDetails(
                url=mcp_url,
                transport="http",
                session_id=session_id,
                tools_details=tools_details,
            )

            # Update context with MCP details so agent can access them
            agent_context.mcp_connection_details = mcp_details
            agent_context.mcp_server_healthy = True
            agent_context.mcp_server_process = 0  # No subprocess PID in HTTP mode
            agent_context.mcp_tools_verified = [
                "initialize_environment",
                "execute_actions",
                "get_observation",
                "cleanup_environment",
            ]

            # Update session status
            self._active_session.status = EvaluationStatus.RUNNING
            
            # Start background monitor (runs in parallel with agent)
            self._background_monitor = BackgroundMonitor(
                agent_context=agent_context,
                interval=agent_context.background_monitor_interval,
                timeout_seconds=agent_context.timeout_seconds
            )
            await self._background_monitor.start()
            
            # Step 3: Use agent to orchestrate the entire evaluation
            # The agent will:
            # 1. Get MCP details from context
            # 2. Send MCP + task details to purple agent via A2A message
            # 3. Monitor evaluation progress
            # 4. Generate final artifact
            
            initial_message = f"internal_system: Participants ready: {{purple_agent: {agent_context.purple_agent_url}}}. Task: {task_id} (benchmark: {agent_context.benchmark}). START EVALUATION NOW by calling send_task_details_to_purple_agent() to send task assignment to purple agent. Purple agent is waiting for your A2A message!"
            
            # Get max_turns from environment (GREEN_LLM_MAX_ITERATIONS or LLM_MAX_ITERATIONS)
            max_agent_turns = int(os.getenv("GREEN_LLM_MAX_ITERATIONS") or os.getenv("LLM_MAX_ITERATIONS", "50"))
            
            try:
                # Run the agent with the evaluation context
                result = await Runner.run(
                    agent,
                    initial_message,
                    context=agent_context,
                    max_turns=max_agent_turns  # Use environment config
                )
                

                
                # Update session status based on agent result
                self._active_session.status = EvaluationStatus.COMPLETED
                self._active_session.completed_at = datetime.now(timezone.utc)
                
                # Extract final results from context (agent tools update context)
                if agent_context.evaluation_complete:
                    _active_sessions[run_id] = {
                        "state": "complete",
                        "task_id": task_id,
                        "result": {
                            "task_success": agent_context.task_success,
                            "final_score": agent_context.final_reward,
                            "task_id": task_id,
                            "benchmark": agent_context.benchmark,
                        }
                    }
                else:
                    _active_sessions[run_id] = {
                        "state": "failed",
                        "task_id": task_id,
                        "error": agent_context.error_message or "Evaluation incomplete"
                    }
                
            except MaxTurnsExceeded as mte:
                # Handle agent hitting max-turns limit gracefully: publish artifact and mark failed.
                logger.warning(f"Agent orchestration stopped: {mte}")
                try:
                    error_artifact = await self._generate_error_artifact(str(mte), start_time)
                except Exception:
                    error_artifact = None

                try:
                    if error_artifact is not None:
                        await updater.add_artifact(
                            parts=[
                                Part(root=TextPart(kind="text", text=f"Evaluation stopped: {str(mte)}")),
                                Part(root=DataPart(kind="data", data=error_artifact.model_dump() if hasattr(error_artifact, "model_dump") else {}))
                            ],
                            name="MaxTurnsExceeded"
                        )
                except Exception as e:
                    logger.warning(f"Failed to add MaxTurnsExceeded artifact: {e}")

                await safe_update_status(
                    state=TaskState.failed,
                    message=new_agent_text_message(f"Evaluation terminated: {str(mte)}")
                )

                if self._active_session:
                    self._active_session.status = EvaluationStatus.FAILED

                _active_sessions[run_id] = {
                    "state": "failed",
                    "task_id": task_id,
                    "error": str(mte),
                    "result": None
                }

                return

            except Exception as agent_error:
                logger.error(
                    f"Agent orchestration failed: {agent_error}",
                    exc_info=True
                )
                _active_sessions[run_id] = {
                    "state": "failed",
                    "task_id": task_id,
                    "error": str(agent_error)
                }
                raise
            
            # Agent orchestration completed - Runner.run() already waited for Purple Agent response
            # BackgroundMonitor already detected completion and stopped
            # No need for additional background monitoring - just do cleanup
            
            # Generate final artifact from shared state (captures real metrics from MCP)
            try:
                artifact = await self._generate_artifact(start_time)
                
                # Update session with artifact
                if self._active_session:
                    self._active_session.final_artifact = artifact.model_dump()
                
                # Update active sessions for kickstart polling
                _active_sessions[run_id] = {
                    "state": "complete",
                    "task_id": task_id,
                    "result": artifact.model_dump()
                }
                
                logger.info(f"Artifact generated: {task_id}, success={artifact.task_success}, score={artifact.final_score}")
            except Exception as artifact_error:
                logger.warning(f"Failed to generate artifact: {artifact_error}")
            
        except Exception as e:
            logger.error(
                "Evaluation failed",
                extra={"task_id": task_id, "error": str(e)},
                exc_info=True
            )
            
            # Generate error artifact
            error_artifact = await self._generate_error_artifact(str(e), start_time)
            
            await updater.add_artifact(
                parts=[
                    Part(root=TextPart(
                        kind="text",
                        text=f"Evaluation failed: {str(e)}"
                    )),
                    Part(root=DataPart(kind="data", data=error_artifact.model_dump()))
                ],
                name="Error Report"
            )
            
            # Update to failed state (A2A SDK handles this automatically)
            await updater.update_status(
                state=TaskState.failed,
                message=new_agent_text_message(f"Evaluation failed: {str(e)}")
            )
            
            if self._active_session:
                self._active_session.status = EvaluationStatus.FAILED
                self._active_session.error = str(e)
            
            # Update status for kickstart script
            _active_sessions[run_id] = {
                "state": "failed",
                "task_id": task_id,
                "error": str(e),
                "result": None
            }
            
            raise
        
        finally:
            # Cleanup after evaluation completes (no background task needed)
            # This runs after Runner.run() completes - Purple Agent already finished
            try:
                # Stop background monitor if still running
                if self._background_monitor:
                    await self._background_monitor.stop()
                
                # Cleanup browser environment and MCP server
                await self._cleanup_mcp_server()
                
                # Cleanup completed (verbose logging disabled)
            except Exception as cleanup_error:
                logger.warning(f"Cleanup error (non-fatal): {cleanup_error}")

    async def _run_multi_task_background(
        self,
        req: EvalRequest,
        config: dict,
        start_time: datetime,
        run_id: str,
    ) -> None:
        """Run a multi-task assessment across one or more benchmarks.

        Contract:
        - Do not perform per-task full cleanup.
        - Use efficient env switching: reset() for same benchmark, recreate for different benchmark.
        - Record results per task.
        - Validate at the end using environment signals (reward/done) and benchmark-specific rules.
        """
        try:
            from uuid import uuid4
            from src.environment.entities import EnvironmentConfig
            from src.benchmarks.profiles import get_profile_for_task, detect_benchmark
            from src.mcp.server import (
                session_manager as mcp_session_manager,
                observation_filter as mcp_observation_filter,
                mcp as mcp_app,
                start_http_server,
            )
            from src.benchmarks.tool_registry import register_tools_for_benchmark
            import src.mcp.server as mcp_module

            # Get task plan from config (already discovered in _create_context_from_eval_request)
            tasks_by_benchmark = config.get("tasks_by_benchmark") or {}
            benchmarks = config.get("benchmarks") or []
            timeout_seconds = int(config.get("timeout_seconds", 300))
            max_steps = int(config.get("max_steps", 10))

            task_plan: list[str] = []
            for b in benchmarks:
                tasks = tasks_by_benchmark.get(b) or []
                if isinstance(tasks, list):
                    task_plan.extend([t for t in tasks if isinstance(t, str) and "." in t])

            if not task_plan:
                raise ValueError("Multi-task plan is empty - no tasks discovered")

            # Initialize MCP server once
            global _mcp_server_task, _mcp_server_started
            if not _mcp_server_started:
                _mcp_server_task = asyncio.create_task(start_http_server(port=_mcp_server_port))
                # Best-effort: wait for server to accept connections
                async def _wait_for_server(port: int, timeout: float = 15.0) -> bool:
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
                    raise TimeoutError(f"MCP server failed to start on port {_mcp_server_port}")
                _mcp_server_started = True

            mcp_url = get_mcp_url()

            # Shared state session id stays constant for the whole multi-task run
            mcp_session_id = str(uuid4())
            os.environ["MCP_SESSION_ID"] = mcp_session_id
            self._shared_state_manager = SharedStateManager(mcp_session_id)
            self._shared_state_manager.initialize()

            # Ensure MCP tools can update shared state
            mcp_module.shared_state = self._shared_state_manager

            # Participants
            participants_map = {role: str(url) for role, url in req.participants.items()}

            results_by_participant: Dict[str, Any] = {}

            for role, purple_url in participants_map.items():
                # Store results per participant
                per_task_results: list[dict[str, Any]] = []
                results_by_participant[role] = {
                    "purple_agent_url": purple_url,
                    "tasks": per_task_results,
                }

                current_benchmark = None

                # Run all tasks sequentially (with smart env switching)
                for idx, task_id in enumerate(task_plan):
                    benchmark_id = detect_benchmark(task_id)
                    profile = get_profile_for_task(task_id)

                    # Apply observation filtering profile
                    if hasattr(mcp_observation_filter, "apply_profile"):
                        mcp_observation_filter.apply_profile(profile)
                    mcp_module.active_benchmark_profile = profile

                    # Register benchmark tools (safe to call repeatedly)
                    register_tools_for_benchmark(benchmark_id, mcp_app)

                    # Smart environment switching
                    env_config = EnvironmentConfig(task_id=task_id, max_steps=max_steps)
                    
                    from src.environment.thread_executor import browser_executor
                    
                    if current_benchmark is None:
                        # First task: create initial session
                        session = await browser_executor.run(mcp_session_manager.create_session, env_config)
                        current_benchmark = benchmark_id
                    elif current_benchmark == benchmark_id:
                        # Same benchmark: efficient task switching
                        switch_result = await browser_executor.run(
                            mcp_session_manager.switch_to_task, task_id, env_config
                        )
                        if switch_result.get("status") != "success":
                            raise RuntimeError(f"Failed to switch to task {task_id}: {switch_result.get('error')}")
                        session = mcp_session_manager.get_session()
                    else:
                        # Different benchmark: recreate environment
                        switch_result = await browser_executor.run(
                            mcp_session_manager.switch_to_task, task_id, env_config
                        )
                        if switch_result.get("status") != "success":
                            raise RuntimeError(f"Failed to switch to task {task_id}: {switch_result.get('error')}")
                        session = mcp_session_manager.get_session()
                        current_benchmark = benchmark_id

                    # Reset shared-state task fields
                    if self._shared_state_manager:
                        self._shared_state_manager.reset_for_new_task(task_id=task_id, benchmark_id=benchmark_id)
                        self._shared_state_manager.update_tool_invocation("initialize_environment")

                    # Build and send task message
                    tools_details = get_all_tools_metadata(benchmark_id)
                    from src.agent.tools.communication_tools import _build_task_message
                    task_message = _build_task_message(
                        task_id=task_id,
                        benchmark=benchmark_id,
                        mcp_details={
                            "url": mcp_url,
                            "transport": "http",
                            "session_id": mcp_session_id,
                        },
                        tools_details=tools_details,
                        profile=profile,
                    )

                    # Add explicit multi-task guidance
                    task_message += "\\n\\nNOTE: This is a MULTI-TASK assessment. Do NOT call cleanup_environment between tasks. After you see done=True or reward>0, stop acting and wait for the next task message.\\n"

                    await self._send_text_message_to_purple(purple_url, task_message)

                    # Monitor completion
                    task_start = time.time()
                    start_state = self._shared_state_manager.read_state() if self._shared_state_manager else None
                    while True:
                        if time.time() - task_start > timeout_seconds:
                            raise TimeoutError(f"Task timeout: {task_id}")

                        state = self._shared_state_manager.read_state() if self._shared_state_manager else None
                        if state and state.error:
                            raise RuntimeError(f"Task error: {state.error}")
                        if state and state.task_completed:
                            end_state = state
                            break
                        await asyncio.sleep(0.5)

                    # Record per-task result
                    delta = {}
                    if start_state is not None and end_state is not None:
                        delta = {
                            "tokens": max(0, end_state.total_tokens - start_state.total_tokens),
                            "latency_ms": max(0, end_state.total_latency_ms - start_state.total_latency_ms),
                            "actions": max(0, end_state.action_count - start_state.action_count),
                            "observations": max(0, end_state.observation_count - start_state.observation_count),
                            "mcp_calls": max(0, end_state.mcp_tool_invocations - start_state.mcp_tool_invocations),
                        }

                    per_task_results.append(
                        {
                            "task_id": task_id,
                            "benchmark": benchmark_id,
                            "task_index": idx,
                            "success": bool(end_state.task_success),
                            "final_reward": float(end_state.final_reward),
                            "done": bool(end_state.done),
                            "truncated": bool(end_state.truncated),
                            "metrics": delta,
                        }
                    )

                    # Update status payload for kickstart polling
                    _active_sessions[run_id] = {
                        "state": "running",
                        "run_id": run_id,
                        "current_task": task_id,
                        "completed_tasks": len(per_task_results),
                        "total_tasks": len(task_plan),
                        "participants": list(participants_map.keys()),
                        "result": None,
                    }

            # Validation and aggregation (end-of-run)
            all_task_rows: list[dict[str, Any]] = []
            for role, pdata in results_by_participant.items():
                for row in pdata.get("tasks", []):
                    all_task_rows.append({"participant": role, **row})

            total = len(all_task_rows)
            passed = sum(1 for r in all_task_rows if r.get("success"))
            success_rate = (passed / total) if total else 0.0

            # Aggregate metrics across tasks (simple sum)
            total_tokens = sum(int(r.get("metrics", {}).get("tokens", 0)) for r in all_task_rows)
            total_latency_ms = sum(int(r.get("metrics", {}).get("latency_ms", 0)) for r in all_task_rows)
            total_actions = sum(int(r.get("metrics", {}).get("actions", 0)) for r in all_task_rows)
            total_observations = sum(int(r.get("metrics", {}).get("observations", 0)) for r in all_task_rows)
            total_mcp_calls = sum(int(r.get("metrics", {}).get("mcp_calls", 0)) for r in all_task_rows)

            # For compatibility with existing Kickstart display
            efficiency_penalty = calculate_efficiency_penalty(total_tokens, total_latency_ms)
            final_score = success_rate * efficiency_penalty

            artifact_dict = {
                "mode": "multi",
                "run_id": run_id,
                "task_success": passed == total and total > 0,
                "final_score": final_score,
                "efficiency_penalty": efficiency_penalty,
                "benchmark": "multi",
                "task_id": "multi",
                "total_tokens": total_tokens,
                "total_latency_ms": total_latency_ms,
                "mcp_tool_invocations": total_mcp_calls,
                "observation_count": total_observations,
                "action_count": total_actions,
                "evaluation_duration_seconds": max(0.0, (datetime.now(timezone.utc) - start_time).total_seconds()),
                # A2A protocol metadata requirement
                "metadata": {
                    "session_id": run_id,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                },
                "participants": results_by_participant,
                "validation": {
                    "total_tasks": total,
                    "passed": passed,
                    "success_rate": success_rate,
                    "method": "env_reward_done",
                },
            }

            _active_sessions[run_id] = {
                "state": "complete",
                "run_id": run_id,
                "task_id": "multi",
                "result": artifact_dict,
            }
            
            # Display comprehensive results
            self._display_assessment_results(artifact_dict)

        except Exception as e:
            logger.error("Multi-task evaluation failed", extra={"run_id": run_id, "error": str(e)}, exc_info=True)
            _active_sessions[run_id] = {
                "state": "failed",
                "run_id": run_id,
                "task_id": "multi",
                "error": str(e),
                "result": None,
            }
        finally:
            # Final cleanup after all tasks
            await self._cleanup_mcp_server()
            if self._evaluation_complete_event:
                self._evaluation_complete_event.set()
    
    def _display_assessment_results(self, artifact: dict) -> None:
        """
        Display comprehensive assessment results with totals, benchmark breakdown, and participant stats.
        
        Args:
            artifact: Evaluation artifact dictionary with results
        """
        print("\n" + "="*80)
        print("🎯 ASSESSMENT RESULTS".center(80))
        print("="*80)
        
        # Overall status
        validation = artifact.get("validation", {})
        total_tasks = validation.get("total_tasks", 0)
        passed_tasks = validation.get("passed", 0)
        failed_tasks = total_tasks - passed_tasks
        success_rate = validation.get("success_rate", 0.0)
        
        status_symbol = "✓" if artifact.get("task_success") else "✗"
        status_text = "PASSED" if artifact.get("task_success") else "FAILED"
        
        print(f"\n📊 OVERALL STATUS: {status_symbol} {status_text}")
        print(f"   Total Tasks: {total_tasks}")
        print(f"   Completed: {passed_tasks} ({success_rate*100:.1f}%)")
        print(f"   Failed: {failed_tasks}")
        print(f"   Final Score: {artifact.get('final_score', 0.0):.3f}")
        print(f"   Efficiency Penalty: {artifact.get('efficiency_penalty', 0.0):.3f}")
        print(f"   Duration: {artifact.get('evaluation_duration_seconds', 0.0):.1f}s")
        
        # Metrics summary
        print(f"\n📈 METRICS SUMMARY:")
        print(f"   Tokens: {artifact.get('total_tokens', 0):,}")
        print(f"   Latency: {artifact.get('total_latency_ms', 0):,}ms")
        print(f"   Actions: {artifact.get('action_count', 0)}")
        print(f"   Observations: {artifact.get('observation_count', 0)}")
        print(f"   MCP Calls: {artifact.get('mcp_tool_invocations', 0)}")
        
        # Benchmark breakdown
        participants = artifact.get("participants", {})
        if participants:
            print(f"\n🎯 BENCHMARK BREAKDOWN:")
            
            # Collect benchmark statistics
            benchmark_stats = {}
            for participant_name, participant_data in participants.items():
                tasks = participant_data.get("tasks", [])
                for task in tasks:
                    task_id = task.get("task_id", "unknown")
                    benchmark = task_id.split(".")[0] if "." in task_id else "unknown"
                    
                    if benchmark not in benchmark_stats:
                        benchmark_stats[benchmark] = {
                            "total": 0,
                            "passed": 0,
                            "failed": 0,
                            "tokens": 0,
                            "latency_ms": 0
                        }
                    
                    benchmark_stats[benchmark]["total"] += 1
                    if task.get("success"):
                        benchmark_stats[benchmark]["passed"] += 1
                    else:
                        benchmark_stats[benchmark]["failed"] += 1
                    
                    metrics = task.get("metrics", {})
                    benchmark_stats[benchmark]["tokens"] += metrics.get("tokens", 0)
                    benchmark_stats[benchmark]["latency_ms"] += metrics.get("latency_ms", 0)
            
            # Display benchmark stats
            for benchmark, stats in sorted(benchmark_stats.items()):
                success_rate_bench = (stats["passed"] / stats["total"] * 100) if stats["total"] > 0 else 0.0
                print(f"\n   📁 {benchmark.upper()}:")
                print(f"      Total: {stats['total']} | Passed: {stats['passed']} | Failed: {stats['failed']} ({success_rate_bench:.1f}%)")
                print(f"      Tokens: {stats['tokens']:,} | Latency: {stats['latency_ms']:,}ms")
        
        # Participant breakdown
        if participants:
            print(f"\n👥 PARTICIPANT BREAKDOWN:")
            
            for participant_name, participant_data in participants.items():
                tasks = participant_data.get("tasks", [])
                total_p = len(tasks)
                passed_p = sum(1 for t in tasks if t.get("success"))
                failed_p = total_p - passed_p
                success_rate_p = (passed_p / total_p * 100) if total_p > 0 else 0.0
                
                # Aggregate metrics for this participant
                total_tokens_p = sum(t.get("metrics", {}).get("tokens", 0) for t in tasks)
                total_latency_p = sum(t.get("metrics", {}).get("latency_ms", 0) for t in tasks)
                total_actions_p = sum(t.get("metrics", {}).get("actions", 0) for t in tasks)
                
                print(f"\n   🤖 {participant_name}:")
                print(f"      Tasks: {total_p} | Passed: {passed_p} | Failed: {failed_p} ({success_rate_p:.1f}%)")
                print(f"      Tokens: {total_tokens_p:,} | Latency: {total_latency_p:,}ms | Actions: {total_actions_p}")
                
                # Show individual task results
                if tasks:
                    print(f"      Tasks:")
                    for task in tasks:
                        task_id = task.get("task_id", "unknown")
                        success_symbol = "✓" if task.get("success") else "✗"
                        reward = task.get("reward", 0.0)
                        print(f"         {success_symbol} {task_id} (reward: {reward:.2f})")
        
        print("\n" + "="*80)
        print("✨ Assessment completed successfully".center(80))
        print("="*80 + "\n")

    async def _send_text_message_to_purple(self, purple_agent_url: str, text: str) -> None:
        """Send a plain-text A2A message to the Purple Agent."""
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
                    pass
            else:
                await send_result
    
    async def _run_evaluation_background(
        self, 
        updater: TaskUpdater, 
        config: dict, 
        start_time: datetime,
        run_id: str
    ) -> None:
        """
        Run evaluation monitoring in background after MCP details are sent.
        
        This method runs as a background task to avoid blocking the A2A response.
        WARNING: updater becomes invalid once run_eval() returns and task enters terminal state.
        Do NOT use updater for final artifacts - task is already marked as completed by executor.
        
        Args:
            updater: TaskUpdater for streaming A2A task updates (only valid during run_eval)
            config: Evaluation configuration
            start_time: Evaluation start time
            task_id: Task identifier
        """
        # Extract task_id from config for logging (run_id is the fallback)
        task_id = config.get("task_id", run_id)
        
        try:
            # Wait for evaluation completion (MCP server will handle purple agent interactions)
            # Monitor shared state changes without using updater (which becomes invalid)
            await self._monitor_evaluation_passive(config)
            
            # Generate final artifact
            artifact = await self._generate_artifact(start_time)
            
            # NOTE: Cannot use updater.add_artifact() here because task is already terminal
            # The A2A executor marked task as completed when run_eval() returned
            # However, we can still store artifact in session for kickstart script
            # The A2A SDK already sent task completion via updater.update_status()
            
            # Update session
            if self._active_session:
                self._active_session.status = EvaluationStatus.COMPLETED
                self._active_session.completed_at = datetime.now(timezone.utc)
                self._active_session.final_artifact = artifact.model_dump()
            
            # Update status for kickstart script
            _active_sessions[run_id] = {
                "state": "complete",
                "task_id": run_id,
                "result": artifact.model_dump()
            }
            
            logger.info(f"Evaluation completed: {task_id}, success={artifact.task_success}, score={artifact.final_score}")
            
        except Exception as e:
            logger.error(
                "Background evaluation failed",
                extra={"task_id": task_id, "error": str(e)},
                exc_info=True
            )
            # Update session to failed state
            if self._active_session:
                self._active_session.status = EvaluationStatus.FAILED
            _active_sessions[run_id] = {
                "state": "failed",
                "task_id": run_id,
                "error": str(e)
            }
        finally:
            # Perform cleanup when background evaluation completes
            
            # Cleanup MCP subprocess
            await self._cleanup_mcp_server()
            
            # Signal completion event (if anyone is waiting)
            if self._evaluation_complete_event:
                self._evaluation_complete_event.set()

    async def _monitor_mcp_logs(self) -> None:
        """Monitor MCP server stderr/stdout and log output."""
        if not self._mcp_process:
            return
        
        try:
            # Monitor stderr in background
            while self._mcp_process.poll() is None:
                if self._mcp_process.stderr:
                    line = await asyncio.to_thread(self._mcp_process.stderr.readline)
                    if line:
                        decoded = line.decode('utf-8', errors='replace').strip()
                        # Skip logging MCP output - too verbose
                await asyncio.sleep(0.1)
        except Exception as e:
            pass  # Silently ignore MCP log monitor errors
    
    
    
    async def _monitor_evaluation_passive(self, config: dict) -> None:
        """
        Monitor evaluation progress WITHOUT using TaskUpdater (for background task).
        
        This method is called by the background task after run_eval() has returned
        and the task is already in terminal state. We can't use TaskUpdater anymore.
        
        Polls shared state file for:
        1. Task completion (done/truncated from BrowserGym)
        2. Cleanup signal (purple agent called cleanup_environment)
        3. No activity timeout (purple disconnected without cleanup)
        
        Args:
            config: Evaluation configuration
        """
        timeout_seconds = config.get("timeout_seconds", 300)
        poll_interval = 0.5  # Poll every 500ms
        no_activity_timeout = 10.0  # If no MCP activity for 10s after task completion, assume done
        
        start_time = datetime.now(timezone.utc)
        last_activity_time = datetime.now(timezone.utc)
        task_completed_time = None
        
        while True:
            # Check timeout
            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
            if elapsed > timeout_seconds:
                logger.warning(
                    "Evaluation timeout reached in background monitor",
                    extra={"timeout_seconds": timeout_seconds, "elapsed": elapsed}
                )
                break
            
            # Read shared state from MCP subprocess
            if self._shared_state_manager:
                state = self._shared_state_manager.read_state()
                self._evaluation_state = state
                
                # Track activity (any MCP tool invocation)
                if state.mcp_tool_invocations > 0:
                    last_activity_time = datetime.now(timezone.utc)
                
                # Check for completion signals
                if state.cleanup_called:
                    # Cleanup signal received (verbose logging disabled)
                    break
                
                # Check for task completion (done/truncated)
                if state.task_completed and not task_completed_time:
                    task_completed_time = datetime.now(timezone.utc)
                    # Waiting for cleanup (verbose logging disabled)
                
                # If task completed and no activity for N seconds, assume Purple disconnected
                if task_completed_time:
                    time_since_completion = (datetime.now(timezone.utc) - task_completed_time).total_seconds()
                    if time_since_completion > no_activity_timeout:
                        logger.warning(
                            f"No MCP activity for {no_activity_timeout}s after task completion. "
                            "Assuming Purple Agent disconnected without calling cleanup. Proceeding with cleanup."
                        )
                        break
                
                # Check for errors
                if state.error:
                    logger.error(f"MCP error detected: {state.error}")
                    raise RuntimeError(f"MCP error: {state.error}")
            
            await asyncio.sleep(poll_interval)
    
    async def _generate_artifact(self, start_time: datetime) -> EvaluationArtifact:
        """
        Generate final evaluation artifact with efficiency metrics.
        
        Uses real metrics from shared state (populated by MCP tool invocations).
        
        Args:
            start_time: Evaluation start timestamp
            
        Returns:
            EvaluationArtifact with results and metrics
        """
        if not self._active_session:
            raise ValueError("No active session to generate artifact from")
        
        # Calculate evaluation duration
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        
        # Get metrics from shared state or fallback to local metrics
        metrics = get_metrics_from_state(self._evaluation_state, self._metrics)
        
        # Calculate efficiency penalty and final score
        efficiency_penalty, final_score = calculate_final_score(
            metrics["task_success"],
            metrics["total_tokens"],
            metrics["total_latency_ms"]
        )
        
        # Get additional metrics
        metrics_dict = self._metrics.to_dict()
        additional_metrics = {
            "peak_memory_mb": metrics_dict.get("peak_memory_mb", 0),
            "chromium_process_count": metrics_dict.get("chromium_process_count", 0),
        }
        
        # Create artifact
        artifact = create_evaluation_artifact(
            task_id=self._active_session.task_id,
            task_success=metrics["task_success"],
            metrics=metrics,
            efficiency_penalty=efficiency_penalty,
            final_score=final_score,
            duration_seconds=duration,
            session_id=self._active_session.session_id,
            additional_metrics=additional_metrics
        )
        
        log_evaluation_completion(artifact)
        return artifact
    
    async def _generate_error_artifact(self, error: str, start_time: datetime) -> EvaluationArtifact:
        """
        Generate error artifact when evaluation fails.
        
        Args:
            error: Error description
            start_time: Evaluation start timestamp
            
        Returns:
            EvaluationArtifact with zero metrics and error details
        """
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        task_id = self._active_session.task_id if self._active_session else None
        session_id = self._active_session.session_id if self._active_session else "unknown"
        
        return create_error_artifact(error, task_id, duration, session_id)
        """
        Generate error artifact when evaluation fails.
        
        Includes partial metrics collected before failure.
        
        Args:
            error: Error message
            start_time: Evaluation start timestamp
            
        Returns:
            EvaluationArtifact with error details and partial metrics
        """
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        
        # Collect metrics from multiple sources (partial metrics)
        total_tokens = 0
        total_latency_ms = 0
        peak_memory_mb = 0
        chromium_process_count = 0
        mcp_tool_invocations = 0
        observation_count = 0
        action_count = 0
        
        # Try to get metrics from shared state first (more accurate)
        if self._evaluation_state:
            state = self._evaluation_state
            total_tokens = state.total_tokens
            total_latency_ms = state.total_latency_ms
            action_count = state.action_count
            observation_count = state.observation_count
            mcp_tool_invocations = state.mcp_tool_invocations
        
        # Fall back to local metrics for memory/process info
        metrics_dict = self._metrics.to_dict()
        peak_memory_mb = metrics_dict.get("peak_memory_mb", 0)
        chromium_process_count = metrics_dict.get("chromium_process_count", 0)
        
        # If shared state was empty, use local metrics
        if total_tokens == 0:
            total_tokens = metrics_dict.get("total_tokens", 0)
        if total_latency_ms == 0:
            total_latency_ms = metrics_dict.get("total_latency_ms", 0)
        if mcp_tool_invocations == 0:
            mcp_tool_invocations = metrics_dict.get("mcp_tool_invocations", 0)
        if observation_count == 0:
            observation_count = metrics_dict.get("observation_count", 0)
        if action_count == 0:
            action_count = metrics_dict.get("action_count", 0)
        
        task_id = self._active_session.task_id if self._active_session else "unknown"
        benchmark = task_id.split(".")[0] if "." in task_id else "unknown"
        
        return EvaluationArtifact(
            task_success=False,
            task_id=task_id,
            benchmark=benchmark,
            total_tokens=total_tokens,
            total_latency_ms=total_latency_ms,
            peak_memory_mb=peak_memory_mb,
            chromium_process_count=chromium_process_count,
            efficiency_penalty=0.0,
            final_score=0.0,
            mcp_tool_invocations=mcp_tool_invocations,
            observation_count=observation_count,
            action_count=action_count,
            evaluation_duration_seconds=duration,
            metadata={
                "session_id": self._active_session.session_id if self._active_session else "unknown",
                "timestamp": datetime.now(timezone.utc).isoformat()
            },
            error_message=error
        )
    
    async def _cleanup_mcp_server(self) -> None:
        """Cleanup MCP server subprocess, shared state, and related processes."""
        # Starting cleanup (verbose logging disabled)
        
        # Cleanup MCP subprocess if managed by green agent
        if self._active_session and self._active_session.mcp_process:
            process = self._active_session.mcp_process
            logger.info("Cleaning up MCP server subprocess", extra={"pid": process.pid})
            
            try:
                # Try graceful termination first
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=5.0)
                    # MCP terminated (verbose logging disabled)
                except asyncio.TimeoutError:
                    # Force kill if graceful termination fails
                    process.kill()
                    await process.wait()
                    logger.warning("MCP server forcefully killed")
            except Exception as e:
                logger.error(f"Error cleaning up MCP server: {e}", exc_info=True)
        
        # Kill any remaining Python MCP server processes
        try:
            import psutil
            current_pid = os.getpid()
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    # Skip current process
                    if proc.info['pid'] == current_pid:
                        continue
                    
                    # Kill Python processes running mcp_server
                    if proc.info['name'] and 'python' in proc.info['name'].lower():
                        cmdline = proc.info.get('cmdline', [])
                        if cmdline and any('mcp_server' in arg for arg in cmdline):
                            # Killing orphaned MCP process (verbose logging disabled)
                            proc.kill()
                            proc.wait(timeout=3)
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired):
                    pass
        except ImportError:
            logger.warning("psutil not available for process cleanup")
        except Exception as e:
            logger.error(f"Error cleaning up orphaned processes: {e}", exc_info=True)
        
        # NOTE: We no longer kill ALL Chrome/Chromium processes here!
        # The session_manager.cleanup_session() now tracks and kills only
        # the specific browser PIDs that were spawned for this evaluation.
        # This prevents accidentally closing the user's personal browser windows.
        # See: session_manager.py and process_monitor.py for the safe cleanup logic.
        
        # ALWAYS cleanup browser session - don't depend on _active_session state
        # This ensures browsers are closed even if session tracking failed
        try:
            from src.mcp.server import session_manager
            # Always attempt cleanup - session_manager tracks its own current_session_id
            cleanup_result = session_manager.cleanup_session()
            browser_session_id = getattr(session_manager, 'current_session_id', None) or "unknown"
            green_session_id = self._active_session.session_id if self._active_session else "unknown"
            # Browser environment cleanup (verbose logging disabled)
        except Exception as e:
            logger.error(f"Error cleaning up browser session: {e}", exc_info=True)
            # Fallback: Try to cleanup all sessions as last resort
            try:
                from src.mcp.server import session_manager
                session_manager.cleanup_all_sessions()
                # Fallback cleanup completed (verbose logging disabled)
            except Exception as fallback_error:
                logger.error(f"Fallback cleanup also failed: {fallback_error}")
        
        # Cleanup shared state file
        if self._shared_state_manager:
            try:
                self._shared_state_manager.cleanup()
            except Exception as e:
                logger.error(f"Error cleaning up shared state: {e}", exc_info=True)
            finally:
                self._shared_state_manager = None
        
        self._evaluation_state = None
        # Comprehensive cleanup completed (verbose logging disabled)


# =============================================================================
# Well-Known Endpoint
# =============================================================================

# Store agent URL globally for endpoint handlers
_agent_url: str = ""


async def well_known_agent_json(request):
    """Serve agent card at /.well-known/agent.json endpoint.
    
    Per A2A discovery spec (FR-003), returns full agent card JSON.
    """
    card_dict = get_agent_card_dict(_agent_url)
    return JSONResponse(card_dict)


async def health_check(request):
    """Health check endpoint for orchestration and monitoring.
    
    Returns:
        JSON response with status "ok" if agent is running
    """
    return JSONResponse({"status": "ok", "agent": "browsergym-green-agent"})


# Store active sessions for status queries
_active_sessions: Dict[str, Dict[str, Any]] = {}

# Global MCP server state (on-demand initialization)
_mcp_server_task: Optional[asyncio.Task] = None
_mcp_server_port: int = int(os.environ.get("MCP_SERVER_PORT", "8001"))  # Configurable via env var
_mcp_server_started: bool = False
_mcp_external_url: Optional[str] = None  # External MCP URL for Docker networking


def get_mcp_url() -> str:
    """Get MCP URL for Purple Agent connection.
    
    Auto-detects Docker environment and uses appropriate hostname.
    Priority: Explicit MCP_EXTERNAL_URL > Auto-detect Docker > localhost
    
    Returns:
        MCP URL string (e.g., "http://green-agent:8001/mcp" or "http://localhost:8001/mcp")
    """
    from src.utils.docker_detection import is_running_in_docker
    
    # Priority 1: Explicit external URL from env or CLI
    if _mcp_external_url:
        return _mcp_external_url
    
    # Priority 2: Auto-detect Docker and use container hostname
    if is_running_in_docker():
        # In Docker, Purple Agent connects to Green Agent via container name (not localhost)
        # The container name is "green-agent" in docker-compose.yml
        mcp_url = f"http://green-agent:{_mcp_server_port}/mcp"
        # Docker detected - using MCP URL (verbose logging disabled)
        return mcp_url
    
    # Priority 3: Default to localhost for local development
    return f"http://localhost:{_mcp_server_port}/mcp"


async def status_check(request):
    """Status check endpoint for assessment monitoring.
    
    Args:
        request: Request with interaction_id in path
        
    Returns:
        JSON response with assessment state and result
    """
    interaction_id = request.path_params.get("interaction_id", "")
    
    if not interaction_id:
        return JSONResponse({"error": "interaction_id required"}, status_code=400)
    
    session = _active_sessions.get(interaction_id)

    # Debug: log current active session keys to help diagnose polling mismatches
    # Commented out to reduce console noise during polling
    # try:
    #     logger.info(f"Status check for interaction_id={interaction_id}; known_sessions={list(_active_sessions.keys())}")
    # except Exception:
    #     pass

    # Fallback: if direct key not found, try to locate by matching stored 'task_id' field
    if not session:
        for key, s in _active_sessions.items():
            try:
                if isinstance(s, dict) and s.get("task_id") == interaction_id:
                    # Cache under requested interaction_id for faster subsequent lookups
                    _active_sessions[interaction_id] = s
                    session = s
                    break
            except Exception:
                continue

    if not session:
        return JSONResponse({"error": "Session not found"}, status_code=404)

    return JSONResponse(session)


async def agent_get_card_rpc(request):
    """Handle agent/getCard JSON-RPC method for extended card.
    
    Per research.md Decision 7 - returns extended info for authenticated clients.
    This is accessed via POST to /a2a with JSON-RPC payload.
    """
    try:
        body = await request.json()
        method = body.get("method", "")
        
        if method == "agent/getCard":
            # Return extended agent card
            extended_card = get_extended_agent_card(_agent_url)
            return JSONResponse({
                "jsonrpc": "2.0",
                "id": body.get("id"),
                "result": extended_card
            })
        else:
            # Pass through to A2A handler
            return None
    except Exception as e:
        logger.error(f"Error in agent/getCard: {e}", exc_info=True)
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": body.get("id") if "body" in locals() else None,
            "error": {
                "code": -32603,
                "message": str(e)
            }
        }, status_code=500)


# =============================================================================
# Main Application Entry Point
# =============================================================================

async def main():
    """Main entry point for A2A server."""
    global _agent_url
    
    parser = argparse.ArgumentParser(description="Run BrowserGym Green Agent A2A server")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host to bind server")
    parser.add_argument("--port", type=int, default=9009, help="Port to bind server")
    parser.add_argument("--mcp-port", type=int, default=int(os.environ.get("MCP_SERVER_PORT", "8001")), help="MCP server port")
    parser.add_argument("--card-url", type=str, help="External URL for agent card")
    parser.add_argument("--mcp-url", type=str, help="External MCP URL for Docker networking (e.g., http://green-agent:8001/mcp)")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    parser.add_argument("--log-level", type=str, default="INFO", 
                       choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
                       help="Logging level")
    args = parser.parse_args()
    
    # Set BROWSER_HEADLESS environment variable
    if args.headless:
        os.environ["BROWSER_HEADLESS"] = "true"
    else:
        # Default to true (headless) if not specified, but allow existing env var to take precedence
        if "BROWSER_HEADLESS" not in os.environ:
            os.environ["BROWSER_HEADLESS"] = "true"
    
    # Configure logging
    from src.utils.logging import setup_logging
    setup_logging(args.log_level)
    
    # Install custom asyncio exception handler to suppress noisy Windows
    # ConnectionResetError during MCP session cleanup
    def _asyncio_exception_handler(loop, context):
        exc = context.get("exception")
        if exc and isinstance(exc, ConnectionResetError):
            # Suppress ConnectionResetError during pipe/socket cleanup
            logger.debug("Suppressed ConnectionResetError during cleanup: %s", str(exc))
            return
        # Fallback to default handler for other exceptions
        loop.default_exception_handler(context)
    
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is not None:
        loop.set_exception_handler(_asyncio_exception_handler)
    
    agent_url = args.card_url or f"http://{args.host}:{args.port}/"
    _agent_url = agent_url  # Store globally for endpoint handlers
    
    # Set global MCP port from CLI argument
    global _mcp_server_port
    _mcp_server_port = args.mcp_port
    
    # Set global MCP URL for Docker networking support
    # Priority: CLI arg > Environment variable > Default localhost
    global _mcp_external_url
    _mcp_external_url = args.mcp_url or os.environ.get("MCP_EXTERNAL_URL")
    # Also set as environment variable for orchestrator module to use
    if _mcp_external_url:
        os.environ["MCP_EXTERNAL_URL"] = _mcp_external_url
    
    logger.info(f"🚀 Green Agent A2A server starting on http://{args.host}:{args.port}/")
    
    # Create green agent instance
    green_agent = BrowserGymGreenAgent()
    
    # Create agent card using new module
    agent_card = create_agent_card(agent_url)
    
    # Create A2A request handler
    # Note: We need to create a proper executor wrapper here
    # For now, using a simple implementation
    from src.a2a.executor import GreenExecutor
    executor = GreenExecutor(green_agent)
    
    request_handler = DefaultRequestHandler(
        agent_executor=executor,
        task_store=InMemoryTaskStore(),
    )
    
    # Create A2A application
    a2a_server = A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=request_handler,
    )
    # Build the A2A Starlette app from the server
    a2a_app = a2a_server.build()
    
    # Create combined Starlette app with A2A SDK
    # Note: A2A SDK handles its own streaming via the protocol - no custom SSE needed
    from starlette.middleware import Middleware
    from starlette.routing import Mount
    
    main_app = Starlette(
        routes=[
            Route("/health", health_check, methods=["GET"]),  # Health check endpoint
            Route("/status/{interaction_id}", status_check, methods=["GET"]),  # Status endpoint for kickstart
            Route("/.well-known/agent.json", well_known_agent_json, methods=["GET"]),  # Agent card discovery
            Route("/.well-known/agent-card.json", well_known_agent_json, methods=["GET"]),  # Agent card discovery alias
            Mount("/", app=a2a_app),  # Mount A2A app at root (handles /message and streaming)
        ],
    )
    
    # Setup graceful shutdown handler
    shutdown_event = asyncio.Event()
    
    def signal_handler(signum, frame):
        """Handle SIGTERM/SIGINT for graceful shutdown."""
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        shutdown_event.set()
    
    import signal
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    # Run main A2A server
    # Note: MCP HTTP server will be started on-demand when first evaluation begins
    uvicorn_config = uvicorn.Config(
        main_app,
        host=args.host,
        port=args.port,
        log_level=args.log_level.lower()
    )
    uvicorn_server = uvicorn.Server(uvicorn_config)
    
    try:
        # Start server in background
        server_task = asyncio.create_task(uvicorn_server.serve())
        
        # Wait for shutdown signal
        await shutdown_event.wait()
        
        # Cleanup active sessions
        if green_agent._active_session:
            await green_agent._cleanup_mcp_server()
        
        # Stop main A2A server
        uvicorn_server.should_exit = True
        await server_task
        
        # Cancel MCP server task if it was started
        if _mcp_server_task and not _mcp_server_task.done():
            _mcp_server_task.cancel()
            try:
                await _mcp_server_task
            except asyncio.CancelledError:
                pass
        
    except Exception as e:
        logger.error(f"Error during server operation: {e}", exc_info=True)
        raise
    finally:
        # Final cleanup
        if green_agent._active_session:
            await green_agent._cleanup_mcp_server()
        
        # Ensure MCP server is cancelled if it was started
        if _mcp_server_task and not _mcp_server_task.done():
            _mcp_server_task.cancel()
            try:
                await _mcp_server_task
            except asyncio.CancelledError:
                pass


if __name__ == "__main__":
    asyncio.run(main())

