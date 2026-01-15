"""
MCP server for BrowserGym Green Agent.
Official SDK implementation with FastMCP.

Exposes environment lifecycle tools for purple agent tool discovery and invocation.
Implements the "traced environment" pattern per AgentBeats best practices.
Supports dynamic benchmark-specific tool registration per Approach III.
"""

import asyncio
import os
from typing import Optional, Literal
from typing_extensions import TypedDict
from datetime import datetime
import json
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from src.environment.session_manager import SessionManager
from src.environment.entities import EnvironmentConfig
from src.environment.observation_filter import ObservationFilter, ObservationMode
from src.environment.action_entities import ActionRequest, ActionBatch
from src.environment.action_executor import ActionExecutor
from src.metrics.tracker import EfficiencyMetrics
from src.utils.shared_state import SharedStateManager, create_state_manager, get_state_manager
from src.utils.activity_watchdog import pulse, ActivityType
from src.benchmarks.profiles import get_profile_for_task, detect_benchmark
from src.benchmarks.tool_registry import (
    get_tool_registry,
    register_tools_for_benchmark,
    cleanup_benchmark_tools,
)
from src.environment.thread_executor import browser_executor
from src.mcp.helpers import (
    parse_action_batch,
    format_action_result,
    format_batch_result,
    create_tool_limit_response,
    should_terminate_batch,
    log_action_payload,
)
from src.utils.logging import get_logger

logger = get_logger(__name__)


def _purple(text: str) -> str:
    """Wrap text in ANSI magenta for terminal highlighting."""
    return f"\x1b[35m{text}\x1b[0m"


# Type definitions for MCP tool parameters
class ActionDict(TypedDict, total=False):
    """Type definition for action dictionary passed to execute_actions tool.
    
    All fields are optional at TypedDict level, but validation occurs at runtime
    based on the action type. See execute_actions docstring for requirements.
    """
    # Action identifier (at least one of these must be present)
    action: str
    action_type: str
    name: str
    
    # Element targeting
    bid: str
    from_bid: str
    to_bid: str
    
    # Text/content
    text: str
    url: str
    
    # Keyboard
    key: str
    key_comb: str
    
    # Scrolling
    direction: Literal["up", "down", "left", "right"]
    dx: int
    dy: int
    
    # Navigation
    tab_index: int
    
    # Selection
    options: list[str]
    
    # Mouse
    button: Literal["left", "right", "middle"]

# Initialize FastMCP server with disabled DNS rebinding protection for Docker
# Docker internal hostnames (green-agent:8001, purple-agent:9010) would be blocked otherwise
mcp = FastMCP(
    "green_agent_mcp_server",
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False)
)

# Initialize tool registry with MCP server
_tool_registry = get_tool_registry()
_tool_registry.set_mcp(mcp)

# Global instances (managed per server lifecycle)
session_manager = SessionManager()
observation_filter = ObservationFilter(token_limit=5000)
action_executor = ActionExecutor(observation_filter)
metrics = EfficiencyMetrics()
shared_state: Optional[SharedStateManager] = None
active_benchmark_profile = None  # Track active benchmark for observation filtering


@mcp.tool()
async def execute_actions(actions: list[ActionDict]) -> dict:
    """
    Execute a batch of browser actions sequentially.
    
    Takes an array of action objects and executes them in order against the
    BrowserGym environment. Each action interacts with page elements identified
    by their browser ID (bid) from the accessibility tree observation.
    
    Target latency: <2s for batch execution.
    
    Args:
        actions: Array of action objects (1-50 actions max). Each action must be a dict with:
        
            REQUIRED for all actions:
            - action (str): Action type. Supported values:
                * Element interactions: "click", "dblclick", "hover", "fill", "clear", "focus", "select_option"
                * Keyboard: "keyboard_type", "keyboard_press"  
                * Scrolling: "scroll"
                * Navigation: "goto", "new_tab", "tab_close", "tab_focus"
                * Communication: "send_msg_to_user"
                * Advanced: "drag_and_drop"
              Note: Also accepts "action_type" or "name" as field names for compatibility.
            
            CONDITIONAL (depending on action type):
            - bid (str): Browser element ID from AXTree - REQUIRED for: click, dblclick, hover, fill, 
                        clear, focus, select_option, drag_and_drop (as from_bid)
            - text (str): Text input - REQUIRED for: fill, keyboard_type, send_msg_to_user
            - url (str): Target URL - REQUIRED for: goto
            - direction (str): Scroll direction "up"/"down"/"left"/"right" - for: scroll (legacy)
            - dx (int): Horizontal scroll pixels - for: scroll (preferred over direction)
            - dy (int): Vertical scroll pixels - for: scroll (preferred over direction)
            - key (str): Single key name - for: keyboard_press (e.g., "Enter", "Tab", "Escape")
            - key_comb (str): Key combination - for: keyboard_press (e.g., "Control+C")
            - tab_index (int): Zero-based tab index - REQUIRED for: tab_focus
            - options (list[str]): Option values - for: select_option (alternative to text)
            - button (str): Mouse button "left"/"right"/"middle" - for: click, dblclick (optional)
            - from_bid (str): Source element ID - REQUIRED for: drag_and_drop
            - to_bid (str): Target element ID - REQUIRED for: drag_and_drop
    
    Returns:
        dict with:
            - results (list[dict]): Per-action results, each containing:
                * observation (dict): Filtered observation after action execution
                * reward (float): BrowserGym reward (1.0 = task complete)
                * done (bool): True if task is complete
                * truncated (bool): True if max steps reached
                * error (str|None): Error message if action failed
                * action_index (int): Zero-based index in batch
            - batch_id (str): Unique batch identifier for tracking
            - latency_ms (float): Total batch execution time in milliseconds
            - early_termination (bool): True if batch stopped early (done=True or error)
    
    Examples:
        Simple click:
        {"actions": [{"action": "click", "bid": "12"}]}
        
        Fill text input:
        {"actions": [{"action": "fill", "bid": "5", "text": "hello world"}]}
        
        Scroll down:
        {"actions": [{"action": "scroll", "dy": 100}]}
        
        Navigate to URL:
        {"actions": [{"action": "goto", "url": "https://example.com"}]}
        
        Multiple actions:
        {"actions": [
            {"action": "click", "bid": "3"},
            {"action": "fill", "bid": "7", "text": "search query"},
            {"action": "keyboard_press", "key": "Enter"}
        ]}
    """
    global shared_state
    start_time = datetime.utcnow()
    
    if shared_state:
        # Check task completion status FIRST - reject if already complete
        current_state = shared_state.read_state()
        if current_state.task_completed:
            logger.warning(f"⚠️ Rejecting execute_actions: Task already completed (done={current_state.done})")
            return {
                "success": False,
                "error": "Task already completed. Cannot execute more actions.",
                "done": True,
                "reward": current_state.final_reward,
                "actions_executed": 0
            }
        
        shared_state.update_tool_invocation("execute_actions")
        # Pulse watchdog - Purple Agent is active
        pulse(ActivityType.MCP_TOOL_CALL, f"execute_actions:{len(actions)}_actions")
        # Log invocation summary in purple so it's easy to spot in terminal
        tool_count = shared_state.get_state().mcp_tool_invocations
        max_calls = shared_state.get_state().max_tool_calls
        logger.info(_purple(f"MCP tool called: execute_actions, actions_count={len(actions)}, tool_call={tool_count}/{max_calls}"))
        
        # Log action payload for debugging
        log_action_payload(actions, lambda msg: logger.info(_purple(msg)))
        
        # Check tool call limit BEFORE executing
        if shared_state.check_tool_limit():
            logger.warning(_purple(f"⚠️ TOOL LIMIT EXCEEDED: {tool_count}/{max_calls} calls. Task terminated."))
            return create_tool_limit_response(tool_count, max_calls)
    
    try:
        # Validate and parse action batch
        session = session_manager.get_session()
        if not session:
            raise ValueError("No active session - environment must be initialized by Green Agent first")
        
        # Parse and validate all actions
        action_requests = parse_action_batch(actions)
        
        # Execute batch on dedicated browser thread (Playwright requires same-thread operations)
        batch = ActionBatch(actions=action_requests)
        completed_batch = await browser_executor.run(action_executor.execute_batch, session, batch)
        
        # Track metrics
        metrics.add_latency(completed_batch.latency_ms)
        metrics.action_count += len(completed_batch.results)
        
        # Update shared state with action results
        if shared_state:
            shared_state.add_latency(int(completed_batch.latency_ms))
            shared_state.add_actions(len(completed_batch.results))
            
            # Check for task completion in results
            for result in completed_batch.results:
                if result.done or result.truncated:
                    shared_state.update_task_state(
                        reward=result.reward,
                        done=result.done,
                        truncated=result.truncated
                    )
                elif result.reward > 0:
                    # Track positive reward even if not done
                    shared_state.update_task_state(
                        reward=result.reward,
                        done=False,
                        truncated=False
                    )
        
        # Format results
        results = [
            format_action_result(
                observation=result.observation,
                reward=result.reward,
                done=result.done,
                truncated=result.truncated,
                action_index=result.action_index,
                error=result.error
            )
            for result in completed_batch.results
        ]
        
        return format_batch_result(
            results=results,
            batch_id=completed_batch.batch_id,
            start_time=start_time,
            early_termination=completed_batch.early_termination
        )
    
    except ValueError as e:
        # Action validation error - return clear error with helpful hint
        error_msg = str(e)
        logger.error("Action validation failed", extra={"error": error_msg}, exc_info=True)
        
        # Add helpful hint based on error type
        if "requires 'bid' parameter" in error_msg:
            error_msg += "\\n\\nHint: Click actions need 'bid' parameter. Example: {'action_type': 'click', 'bid': '13'}\\nExtract bid from observation's axtree_txt like: [13] button 'Submit'"
        elif "requires 'bid' and 'text'" in error_msg:
            error_msg += "\\n\\nHint: Type actions need both 'bid' and 'text'. Example: {'action_type': 'type', 'bid': '5', 'text': 'hello'}"
        
        if shared_state:
            shared_state.set_error(error_msg)
        
        return {
            "success": False,
            "error": error_msg,
            "actions_executed": 0
        }
    
    except Exception as e:
        logger.error(
            "MCP tool failed: execute_actions",
            extra={"tool_name": "execute_actions", "error": str(e)},
            exc_info=True
        )
        if shared_state:
            shared_state.set_error(str(e))
        raise


@mcp.tool()
def get_observation(observation_mode: str = "axtree") -> dict:
    """
    Get filtered observation of current browser page state.
    
    Returns the current state of the browser environment including the
    accessibility tree (axtree), page URL, task goal, and token estimate.
    The observation is filtered to stay within token limits.
    
    Target: <5K tokens for efficient LLM processing.
    
    Args:
        observation_mode: Format mode for observation output.
            - 'axtree' (default): Accessibility tree with element IDs (bid) for interaction
            - 'dom': Raw DOM structure (larger, more detailed)
            - 'screenshot': Base64-encoded PNG screenshot of current viewport
    
    Returns:
        dict with:
            - axtree_txt (str): Accessibility tree text showing interactive elements with bid values
            - goal (str): The task goal/objective to accomplish
            - url (str): Current page URL
            - token_estimate (int): Estimated token count for the observation
            - open_pages (list): List of open browser tabs/pages
    
    Examples:
        {"observation_mode": "axtree"}
        {}
    """
    global shared_state
    start_time = datetime.utcnow()
    
    if shared_state:
        shared_state.update_tool_invocation("get_observation")
        # Pulse watchdog - Purple Agent is active
        pulse(ActivityType.MCP_TOOL_CALL, f"get_observation:{observation_mode}")
        # Log invocation summary in purple for easy visibility
        tool_count = shared_state.get_state().mcp_tool_invocations
        max_calls = shared_state.get_state().max_tool_calls
        logger.info(_purple(f"MCP tool called: get_observation, mode={observation_mode}, tool_call={tool_count}/{max_calls}"))
        
        # Check tool call limit BEFORE executing
        if shared_state.check_tool_limit():
            logger.warning(_purple(f"⚠️ TOOL LIMIT EXCEEDED: {tool_count}/{max_calls} calls. Task terminated."))
            return {
                "axtree_txt": "",
                "goal": "TASK TERMINATED: Tool call limit exceeded",
                "url": "",
                "token_estimate": 0,
                "error": f"Tool call limit exceeded ({max_calls} calls). Task terminated. Green Agent will send next task.",
                "task_terminated": True,
                "tool_calls_used": tool_count,
                "max_tool_calls": max_calls,
            }
    
    try:
        session = session_manager.get_session()
        if not session:
            raise ValueError("No active session - environment must be initialized by Green Agent first")
        
        raw_observation = session.current_observation or {}
        
        # Log observation summary instead of printing raw dict
        logger.debug(
            f"Retrieved raw observation: keys={list(raw_observation.keys())}, "
            f"has_axtree={'axtree_object' in raw_observation}, "
            f"url={raw_observation.get('url')}"
        )
        
        try:
            mode = ObservationMode(observation_mode.lower())
        except ValueError:
            mode = ObservationMode.AXTREE
            logger.warning(f"Invalid observation mode '\''{observation_mode}'\'', using default '\''axtree'\''")
        
        filtered_observation = observation_filter.filter_observation(raw_observation, mode=mode)
        
        # Track metrics
        token_count = filtered_observation.get("token_estimate", 0)
        metrics.add_tokens(token_count)
        metrics.observation_count += 1
        
        # Update shared state
        if shared_state:
            shared_state.add_tokens(token_count)
        
        latency_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
        metrics.add_latency(latency_ms)
        
        if shared_state:
            shared_state.add_latency(latency_ms)

        observation_summary = {
            "url": filtered_observation.get("url"),
            "goal": filtered_observation.get("goal"),
            "token_estimate": filtered_observation.get("token_estimate"),
            "axtree_len": len(filtered_observation.get("axtree_txt", "")),
            "keys": list(filtered_observation.keys()),
            "latency_ms": latency_ms,
        }
        logger.info(
            _purple("Observation snapshot"),
            extra={
                "tool_name": "get_observation",
                # "summary": filtered_observation
            }
        )
        
        summary_json = json.dumps(filtered_observation, ensure_ascii=False)
        print(_purple(f"Observation summary: {summary_json}"))

        sanitized_observation = {
            key: value
            for key, value in filtered_observation.items()
            if key != "url"
        }

        logger.info(
            _purple("Filtered observation payload sent to Purple Agent"),
            extra={
                "tool_name": "get_observation",
                "payload": sanitized_observation
            }
        )

        return sanitized_observation
    except Exception as e:
        logger.error(
            "MCP tool failed: get_observation",
            extra={"tool_name": "get_observation", "error": str(e)},
            exc_info=True
        )
        if shared_state:
            shared_state.set_error(str(e))
        raise


# cleanup_environment removed - Green Agent handles cleanup after Purple Agent completes
# Purple Agent signals completion via A2A message, then Green Agent cleans up the environment


# List of base MCP tools exposed to Purple Agent
# Add/remove tools here to change what's advertised in task messages
BASE_MCP_TOOLS = [
    execute_actions,
    get_observation,
]


def main():
    """CLI entry point for MCP server - starts HTTP server on port 8001."""
    import sys
    import argparse
    
    parser = argparse.ArgumentParser(description="Run BrowserGym MCP server")
    parser.add_argument("port", type=int, nargs="?", default=8001, help="Port to bind server")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    args = parser.parse_args()
    
    port = args.port
    
    # Set BROWSER_HEADLESS environment variable
    if args.headless:
        os.environ["BROWSER_HEADLESS"] = "true"
    else:
        # Default to false (visible) if not specified, but allow existing env var to take precedence
        if "BROWSER_HEADLESS" not in os.environ:
            os.environ["BROWSER_HEADLESS"] = "false"
    
    logger.info(f"Starting MCP server with HTTP transport on port {port}")
    
    # Run MCP server with HTTP transport (streamable-http)
    # Note: Agent must initialize environment before starting this server
    # This will start uvicorn server at http://localhost:{port}/mcp
    logger.info("Starting MCP server in CLI mode (ensure environment is initialized first)")
    mcp.run(transport="streamable-http", port=port)


async def start_http_server(port: int = 8001) -> None:
    """
    Start MCP server as HTTP server in the background.
    
    This function is used when MCP server is started from Green Agent main.py
    rather than as a standalone CLI process.
    
    Note: Agent must initialize the BrowserGym environment BEFORE calling this.
    This server is a pure tool provider - it assumes the session already exists.
    
    Args:
        port: Port to run MCP server on (default: 8001)
    """
    import uvicorn
    from starlette.applications import Starlette
    from starlette.routing import Mount
    from contextlib import asynccontextmanager
    
    logger.info(f"Starting MCP HTTP server on port {port} (tool provider mode)")
    
    # Ensure MCP session manager is started during ASGI lifespan so
    # streamable-http handlers have an initialized task group.
    @asynccontextmanager
    async def lifespan(app):
        # Initialize FastMCP's internal session manager/task group
        async with mcp.session_manager.run():
            yield
    
    # Configure streamable_http_path to /mcp endpoint
    try:
        mcp.settings.streamable_http_path = "/mcp"
    except Exception:
        # If settings object differs across SDK versions, ignore and continue
        pass
    
    # Mount MCP at root (streamable_http_path already sets the /mcp endpoint)
    # This avoids HTTP 307 redirects from /mcp to /mcp/
    app = Starlette(
        routes=[
            Mount("/", app=mcp.streamable_http_app()),
        ],
        lifespan=lifespan,
    )
    
    # Run uvicorn server
    config = uvicorn.Config(
        app=app,
        host="0.0.0.0",
        port=port,
        log_level="info",
    )
    server = uvicorn.Server(config)
    
    # Run in background
    await server.serve()


if __name__ == "__main__":
    main()
