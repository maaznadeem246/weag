"""
MCP server for BrowserGym Green Agent.
Official SDK implementation with FastMCP.

Exposes environment lifecycle tools for purple agent tool discovery and invocation.
Implements the "traced environment" pattern per AgentBeats best practices.
Supports dynamic benchmark-specific tool registration per Approach III.
"""

import asyncio
import os
from typing import Optional, Any
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


# Type definition for MCP tool parameters
# Using dict[str, Any] for flexibility - validation happens at runtime based on action type
# The dynamic documentation tells Purple Agent which actions and parameters are valid per benchmark

# Configure transport security to allow Docker service names
# Use wildcards to support dynamic port configuration
transport_security = TransportSecuritySettings(
    enable_dns_rebinding_protection=True,
    allowed_hosts=[
        "localhost:*",       # Any port on localhost
        "127.0.0.1:*",       # Any port on 127.0.0.1
        "0.0.0.0:*",         # Any port on 0.0.0.0
        "green-agent:*",     # Any port on Docker service name
    ],
)

# Initialize FastMCP server with security settings
mcp = FastMCP("green_agent_mcp_server", transport_security=transport_security)

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
async def execute_actions(actions: list[dict[str, Any]]) -> dict:
    """
    Execute a batch of browser actions sequentially on the current page.

    Use this to interact with web elements identified by their bid (browser ID) from the
    accessibility tree. See the "Allowed actions" section below for supported action types
    and their required parameters.

    Args:
        actions: Array of 1-50 action dicts. Each has "action" field plus action-specific params.

    Returns:
        dict with results (list), batch_id (str), latency_ms (float), early_termination (bool)

    Examples:
        {"actions": [{"action": "click", "bid": "12"}]}
        {"actions": [{"action": "fill", "bid": "5", "text": "hello"}]}
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
        # Tool call logging disabled (verbose)
        
        # Log action payload for debugging
        # Action payload logging disabled (verbose)
        
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

        # ANSI color codes for console output
        _ANSI_GREEN = "\x1b[32m"
        _ANSI_BLUE = "\x1b[34m"
        _ANSI_CYAN = "\x1b[36m"
        _ANSI_RESET = "\x1b[0m"

        # Extract done flags and check for task completion
        done_flags = [bool(r.get("done", False)) if isinstance(r, dict) else False for r in results]
        done_count = sum(done_flags)
        print(results)
        # Print to console with colors (bypasses JSON formatter)
        print(f"\n{_ANSI_GREEN}{'='*60}")
        print(f"📊 MCP Action Results: {len(results)} action(s) executed")
        print(f"{'='*60}{_ANSI_RESET}\n")

        # Show each result with its key information
        for idx, result in enumerate(results):
            reward = result.get("reward", 0.0)
            done = result.get("done", False)
            error = result.get("error", None)

            status_color = _ANSI_BLUE if done else _ANSI_CYAN
            status_icon = "✅" if not error else "❌"

            print(f"{status_color}{status_icon} Action {idx+1}:")
            print(f"   - done: {done}")
            print(f"   - reward: {reward:.2f}")
            if error:
                print(f"   - error: {error}")
            print(f"{_ANSI_RESET}")

        # Highlight task completion if detected
        if done_count > 0:
            print(f"{_ANSI_BLUE}{'='*60}")
            print(f"🎯 TASK COMPLETION DETECTED!")
            print(f"   {done_count}/{len(done_flags)} action(s) marked done=True")
            print(f"{'='*60}{_ANSI_RESET}\n")
        else:
            print(f"{_ANSI_CYAN}⏳ Task in progress: all actions returned done=False{_ANSI_RESET}\n")

        # Also log to JSON logger for records
        logger.info(f"MCP action results: {len(results)} actions, done_count={done_count}")

        # Log MCP tool execution results
        logger.info(f"🛠️  MCP: execute_actions completed ({len(results)} actions)")
        for idx, res in enumerate(completed_batch.results):
            status_icon = "✅" if not res.error else "❌"
            logger.info(f"  {status_icon} Action {idx+1}: done={res.done}, reward={res.reward:.2f}")
            if res.error:
                logger.error(f"    ⚠️ Error: {res.error}")
        
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
    Get current browser page state including task goal and interactive elements.

    Returns the accessibility tree showing elements you can interact with, along with
    the task goal, current URL, and open tabs. Use the bid (browser ID) values from
    the axtree to target elements in your actions.

    Args:
        observation_mode: Format for observation (default: "axtree")
            - "axtree": Accessibility tree with element IDs (recommended)
            - "dom": Raw DOM structure (more detailed)
            - "screenshot": Base64-encoded PNG image

    Returns:
        dict with:
            - axtree_txt (str): Tree of interactive elements with bid values
            - goal (str): Task objective to accomplish
            - url (str): Current page URL
            - open_pages (list): Open browser tabs

    Examples:
        {"observation_mode": "axtree"} or just {}
    """
    global shared_state
    start_time = datetime.utcnow()
    
    if shared_state:
        # Check if task is already completed - warn Purple Agent to stop
        current_state = shared_state.get_state()
        if current_state.task_completed:
            logger.warning(_purple(f"⚠️ Task already completed (done={current_state.done}). Purple Agent should stop calling tools."))
            return {
                "axtree_txt": "",
                "goal": "✅ TASK ALREADY COMPLETED - Stop calling tools and return your final answer.",
                "url": "",
                "token_estimate": 0,
                "task_completed": True,
                "final_reward": current_state.reward,
                "message": "Task was completed in previous action. No more observations needed. Report success to orchestrator.",
            }
        
        shared_state.update_tool_invocation("get_observation")
        # Pulse watchdog - Purple Agent is active
        pulse(ActivityType.MCP_TOOL_CALL, f"get_observation:{observation_mode}")
        # Log invocation summary in purple for easy visibility
        tool_count = shared_state.get_state().mcp_tool_invocations
        max_calls = shared_state.get_state().max_tool_calls
        # Tool call logging disabled (verbose)
        
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
        # Default to true (headless) if not specified, but allow existing env var to take precedence
        if "BROWSER_HEADLESS" not in os.environ:
            os.environ["BROWSER_HEADLESS"] = "true"
    
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
    
    # Log MCP server startup
    logger.info("=" * 60)
    logger.info("✅ MCP SERVER STARTED SUCCESSFULLY")
    logger.info(f"Transport: HTTP (Streamable)")
    logger.info(f"Endpoint: http://0.0.0.0:{port}/mcp")
    logger.info(f"Allowed Hosts: localhost:*, 127.0.0.1:*, green-agent:* (any port)")
    logger.info(f"DNS Rebinding Protection: Enabled")
    logger.info(f"Status: Ready to accept connections")
    logger.info("=" * 60)
    
    # Run in background
    await server.serve()


if __name__ == "__main__":
    main()
