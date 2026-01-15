"""Agent tools for BrowserGym evaluation orchestration."""

# New simplified LLM-facing tools (3 tools only)
from src.agent.tools.assessment_tools import (
    start_assessment,
    get_assessment_status,
    get_assessment_result,
)

# Wrap with Agents SDK function_tool
from agents import function_tool

start_assessment = function_tool(start_assessment)
get_assessment_status = function_tool(get_assessment_status)
get_assessment_result = function_tool(get_assessment_result)


# Tool registry - ONLY these 3 tools are exposed to the LLM
AGENT_TOOLS = [
    start_assessment,
    get_assessment_status,
    get_assessment_result,
]


# Legacy imports for internal/orchestrator use (not exposed to LLM)
# These are used by AssessmentOrchestrator internally
from src.agent.tools.environment_tools import (
    initialize_evaluation,
    cleanup_evaluation,
    verify_mcp_server_health,
)
from src.agent.tools.monitoring_tools import (
    get_context_details,
)
from src.agent.tools.communication_tools import (
    send_task_details_to_purple_agent,
    send_task_update,
)
from src.agent.tools.evaluation_tools import (
    calculate_efficiency_score,
    generate_evaluation_artifact,
    orchestrate_batch_evaluation,
)
from src.agent.tools.multi_task_tools import (
    send_first_task_to_purple_agent,
    wait_for_purple_completion,
    send_next_task_to_purple_agent,
    finalize_multi_task_assessment,
)


__all__ = [
    # LLM-facing tools (exposed to agent)
    "AGENT_TOOLS",
    "start_assessment",
    "get_assessment_status",
    "get_assessment_result",
    
    # Internal tools (for orchestrator and programmatic use)
    "initialize_evaluation",
    "cleanup_evaluation",
    "verify_mcp_server_health",
    "get_context_details",
    "send_task_details_to_purple_agent",
    "send_task_update",
    "calculate_efficiency_score",
    "generate_evaluation_artifact",
    "orchestrate_batch_evaluation",
    "send_first_task_to_purple_agent",
    "wait_for_purple_completion",
    "send_next_task_to_purple_agent",
    "finalize_multi_task_assessment",
]
