"""
Helper functions for building task messages and formatting for Purple Agent communication.

Extracted from communication_tools.py for better modularity.
"""

from typing import Optional, List
from src.benchmarks.profiles import BenchmarkProfile
from src.mcp import ToolMetadata, format_tools_documentation
from src.utils.shared_state import DEFAULT_MAX_TOOL_CALLS


def build_profile_section(profile: Optional[BenchmarkProfile]) -> str:
    """
    Build profile information section for task message.
    
    Args:
        profile: Benchmark profile with configuration
        
    Returns:
        Formatted profile section string
    """
    if not profile:
        return ""
    
    return f"""
- **Benchmark Name**: {profile.display_name}
- **Token Limit**: {profile.token_limit} tokens
- **Observation Mode**: {profile.observation_mode.value}"""


def build_mcp_connection_section(mcp_details: dict) -> str:
    """
    Build MCP connection details section.
    
    Args:
        mcp_details: MCP connection details dict
        
    Returns:
        Formatted connection section string
    """
    session_info = f"\n- **Session ID**: `{mcp_details.get('session_id')}`" if mcp_details.get('session_id') else ""
    
    return f"""## MCP SERVER CONNECTION FOR TOOLS

- **Transport**: {mcp_details.get('transport', 'http')}
- **URL**: `{mcp_details.get('url', 'N/A')}`{session_info}"""


def build_tools_section(tools_details: List[ToolMetadata], benchmark: str) -> str:
    """
    Build tools documentation section.
    
    Args:
        tools_details: List of tool metadata
        benchmark: Benchmark name
        
    Returns:
        Formatted tools section string
    """
    if tools_details:
        return f"\n{format_tools_documentation(tools_details, benchmark)}"
    else:
        return "\n## AVAILABLE MCP TOOLS\n\nTool documentation not available. Use `tool_list_mcp_tools` after connecting."


def build_task_goal_section(task_goal: Optional[str]) -> str:
    """
    Build task goal section if available.
    
    Args:
        task_goal: Task goal text from BrowserGym
        
    Returns:
        Formatted task goal section or empty string
    """
    if not task_goal:
        return ""
    
    return f"""

## TASK GOAL

{task_goal}

"""


def build_task_message(
    task_id: str,
    benchmark: str,
    mcp_details: dict,
    tools_details: List[ToolMetadata],
    profile: Optional[BenchmarkProfile] = None,
    task_goal: Optional[str] = None,
    max_tool_calls: int = DEFAULT_MAX_TOOL_CALLS,
) -> str:
    """
    Build comprehensive task assignment message for Purple Agent.
    
    This is a TEXT-ONLY message that Purple Agent can understand without
    any structured data parsing. Tool documentation is dynamically generated
    from the actual MCP tool functions.
    
    Args:
        task_id: Full task identifier (e.g., 'miniwob.click-test')
        benchmark: Benchmark name (e.g., 'miniwob')
        mcp_details: MCP connection details dict
        tools_details: List of ToolMetadata extracted from MCP tools
        profile: Optional benchmark profile for additional context
        task_goal: Optional task goal/instruction from BrowserGym environment
        max_tool_calls: Maximum number of tool calls allowed per task
        
    Returns:
        Formatted text message with all task details
    """
    profile_info = build_profile_section(profile)
    task_goal_section = build_task_goal_section(task_goal)
    tools_section = build_tools_section(tools_details, benchmark)
    
    # Build complete message
    message = f"""{'=' * 60}
ASSESSMENT TASK
{'=' * 60}

## TASK DETAILS

- **Task ID**: `{task_id}`
- **Benchmark**: {benchmark}{profile_info}

## INSTRUCTIONS

Complete the browser-based task by interacting with web elements. The environment has been initialized. Use `get_observation` to see the current page state and task goal, then execute actions to achieve it.

**⚠️ TOOL CALL LIMIT**: You have a maximum of **{max_tool_calls} tool calls** for this task. Plan efficiently!
- If you exceed the limit, the task will be terminated and marked as incomplete.
- Use `execute_actions` with multiple actions in one call when possible.

{build_mcp_connection_section(mcp_details)}
{tools_section}

## TASK DETAILS

- **Task ID**: `{task_id}`
- **Benchmark**: {benchmark}{profile_info}

{task_goal_section}

{'=' * 60}"""
    
    return message
