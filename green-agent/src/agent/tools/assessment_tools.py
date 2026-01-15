"""
Assessment tools for LLM-facing interaction.

These are the ONLY tools exposed to the LLM for assessment management.
All complex orchestration logic runs in the background orchestrator.

Tools:
- start_assessment(): Start background assessment (call once)
- get_assessment_status(): Check current progress
- get_assessment_result(): Get final results when complete
"""

import asyncio
from typing import Any, Dict
from agents.run_context import RunContextWrapper

from src.agent.context import AgentContext
from src.assessment import Assessment
from src.assessment.orchestrator import start_orchestrator
from src.utils.logging import get_logger

logger = get_logger(__name__)


async def start_assessment(ctx: RunContextWrapper[AgentContext]) -> Dict[str, Any]:
    """
    Start background assessment execution.
    
    Call this ONCE when Purple Agent is ready to begin.
    The orchestrator runs independently in the background.
    
    Returns:
        dict with status and initial info
    """
    context: AgentContext = ctx.context
    assessment: Assessment = context.assessment_tracker
    
    if not assessment:
        return {
            "status": "error",
            "message": "No assessment configured. Cannot start."
        }
    
    # Check if already running
    if assessment.is_orchestrator_running():
        return {
            "status": "already_running",
            "message": "Assessment is already running in the background.",
            "progress": assessment.get_orchestrator_progress()
        }
    
    # Check if already complete
    if assessment.orchestrator_status == "complete":
        return {
            "status": "already_complete",
            "message": "Assessment has already completed.",
            "progress": assessment.get_orchestrator_progress()
        }
    
    # Check if Purple Agent URL is configured
    if not context.purple_agent_url:
        return {
            "status": "error",
            "message": "Purple Agent URL not configured. Cannot start assessment."
        }
    
    try:
        # Start orchestrator as background task (don't await - let it run independently)
        task = start_orchestrator(assessment, context, context.active_sessions)
        
        logger.info(f"🚀 Assessment started: {assessment.total_tasks} tasks")
        
        return {
            "status": "started",
            "message": f"Assessment started with {assessment.total_tasks} tasks. Running in background.",
            "total_tasks": assessment.total_tasks,
            "first_task": assessment.current_task_id,
            "benchmarks": assessment.benchmarks,
        }
        
    except Exception as e:
        logger.error(f"Failed to start assessment: {e}", exc_info=True)
        return {
            "status": "error",
            "message": f"Failed to start assessment: {str(e)}"
        }


async def get_assessment_status(ctx: RunContextWrapper[AgentContext]) -> Dict[str, Any]:
    """
    Get current assessment status and progress.
    
    Use this to check how the background assessment is progressing.
    
    Returns:
        dict with status, progress, and current task info
    """
    context: AgentContext = ctx.context
    assessment: Assessment = context.assessment_tracker
    
    if not assessment:
        return {
            "status": "error",
            "message": "No assessment configured."
        }
    
    progress = assessment.get_orchestrator_progress()
    
    # Add human-readable summary
    if progress["status"] == "idle":
        progress["summary"] = "Assessment not started. Call start_assessment() to begin."
    elif progress["status"] == "running":
        progress["summary"] = (
            f"Running: Task {progress['current_task_index'] + 1}/{progress['total_tasks']} "
            f"({progress['completed_tasks']} completed, {progress['passed_tasks']} passed)"
        )
    elif progress["status"] == "complete":
        progress["summary"] = (
            f"Complete: {progress['passed_tasks']}/{progress['total_tasks']} tasks passed "
            f"({progress['success_rate']:.1%} success rate)"
        )
    elif progress["status"] == "error":
        progress["summary"] = f"Error: {progress['error']}"
    
    return progress


async def get_assessment_result(ctx: RunContextWrapper[AgentContext]) -> Dict[str, Any]:
    """
    Get final assessment results.
    
    Call this when assessment is complete to retrieve the full results artifact.
    
    Returns:
        dict with final results or status if not complete
    """
    context: AgentContext = ctx.context
    assessment: Assessment = context.assessment_tracker
    
    if not assessment:
        return {
            "status": "error",
            "message": "No assessment configured."
        }
    
    orchestrator_status = assessment.orchestrator_status
    
    if orchestrator_status == "idle":
        return {
            "status": "not_started",
            "message": "Assessment has not been started yet. Call start_assessment() first."
        }
    
    if orchestrator_status == "running":
        progress = assessment.get_orchestrator_progress()
        return {
            "status": "in_progress",
            "message": (
                f"Assessment still running. "
                f"Progress: {progress['completed_tasks']}/{progress['total_tasks']} tasks completed."
            ),
            "progress": progress
        }
    
    if orchestrator_status == "error":
        return {
            "status": "error",
            "message": f"Assessment failed: {assessment.orchestrator_error}",
            "error": assessment.orchestrator_error,
            "partial_results": assessment.get_results_summary()
        }
    
    # Status is "complete"
    artifact = assessment.result_artifact
    if artifact:
        return {
            "status": "complete",
            "message": (
                f"Assessment complete: {artifact.get('passed_tasks', 0)}/{artifact.get('total_tasks', 0)} "
                f"tasks passed ({artifact.get('success_rate', 0):.1%} success rate)"
            ),
            "results": artifact
        }
    
    # Fallback: build results from assessment
    return {
        "status": "complete",
        "message": "Assessment complete.",
        "results": assessment.get_results_summary()
    }


__all__ = [
    "start_assessment",
    "get_assessment_status",
    "get_assessment_result",
]
