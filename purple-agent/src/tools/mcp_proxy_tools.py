"""
MCP proxy tools for dynamic MCP server connections.

These generic tools allow the agent to connect to ANY MCP server at runtime
without needing to reload or reconfigure the agent. The agent starts with
these 4 proxy tools, and uses them to bridge to MCP servers discovered via A2A.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, TYPE_CHECKING
from agents import RunContextWrapper

from src.utils.logging import get_logger

# Use TYPE_CHECKING to avoid circular import
if TYPE_CHECKING:
    from src.agent.context import TestPurpleAgentContext

logger = get_logger(__name__)


def _log_observation_result(server_name: str, payload: Dict[str, Any]) -> None:
    """Log a concise summary of the observation result for debugging."""
    result = payload.get("result")
    summary = {"server": server_name}

    if isinstance(result, dict):
        summary.update({
            "url": result.get("url"),
            "goal_present": bool(result.get("goal")),
            "token_estimate": result.get("token_estimate"),
            "axtree_chars": len(result.get("axtree_txt", "")),
            "key_count": len(result.keys()),
        })
    else:
        summary["result_preview"] = str(result)[:200]

    # Observation received (verbose logging disabled)


async def connect_to_mcp(
    ctx: RunContextWrapper[TestPurpleAgentContext],
    server_name: str,
    url: str,
    transport: str = "http"
) -> Dict[str, Any]:
    """
    Connect to an MCP server at the specified URL.
    
    Extract the connection details from the task message you received:
    - Look for "MCP SERVER CONNECTION" section
    - Extract the URL (e.g., "http://127.0.0.1:8001/mcp")
    - Transport is usually "http" or "streamable-http"
    
    Args:
        server_name: Friendly name for the server (use "browsergym")
        url: Full HTTP URL to the MCP server (e.g., "http://127.0.0.1:8001/mcp")
        transport: Transport protocol - use "http" (default: "http")
        
    Returns:
        Connection status with available tools list
        
    Example:
        # Extract URL from message, then call:
        result = await connect_to_mcp(ctx, "browsergym", "http://127.0.0.1:8001/mcp", "http")
        # Returns: {"status": "connected", "server": "browsergym", "tools": ["execute_actions", ...]}
    """
    context = ctx.context
    
    # Check if already connected
    if context.mcp_connected and server_name in context.mcp_registry:
        conn_info = context.mcp_registry[server_name]
        session = conn_info["session"] if isinstance(conn_info, dict) else conn_info
        
        # List available tools
        tools_result = await session.list_tools()
        tool_names = [tool.name for tool in tools_result.tools]
        
        return {
            "status": "already_connected",
            "server": server_name,
            "tools": tool_names
        }
    
    # Connect to MCP server
    try:
        from mcp import ClientSession
        
        # Normalize transport name
        transport = transport.lower().replace("-", "")
        
        if transport in ["http", "streamablehttp"] and url:
            # HTTP transport (recommended)
            from mcp.client.streamable_http import streamablehttp_client
            
            # Per official MCP Python SDK docs, use nested async with pattern:
            # async with streamablehttp_client(...) as (read, write, _):
            #     async with ClientSession(read, write) as session:
            #         await session.initialize()
            #
            # However, we need to keep the connection open across tool calls,
            # so we manually enter the context managers and store them.
            
            logger.info(f"🔌 Connecting to MCP server: {url}")
            http_cm = streamablehttp_client(url)
            try:
                logger.info("  • Establishing HTTP transport...")
                read, write, _ = await asyncio.wait_for(http_cm.__aenter__(), timeout=30.0)
                logger.info("  ✓ HTTP transport established")
            except asyncio.TimeoutError:
                logger.error("❌ HTTP transport connection timed out")
                return {"error": "HTTP transport connection timed out"}
            except Exception as e:
                logger.error(f"❌ Failed to establish HTTP transport: {e}", exc_info=True)
                return {"error": f"HTTP transport failed: {e}"}
            
            # Now create and enter ClientSession context manager
            logger.info("  • Creating MCP client session...")
            session_cm = ClientSession(read, write)
            try:
                session = await asyncio.wait_for(session_cm.__aenter__(), timeout=30.0)
                logger.info("  ✓ MCP client session created")
                
                # Initialize the MCP protocol
                logger.info("  • Initializing MCP protocol handshake...")
                await asyncio.wait_for(session.initialize(), timeout=30.0)
                logger.info("✅ MCP connection successful!")
            except asyncio.TimeoutError:
                # Cleanup HTTP transport
                try:
                    await http_cm.__aexit__(None, None, None)
                except Exception:
                    pass
                return {"error": "MCP session initialization timed out"}
            except Exception as e:
                logger.error(f"Failed to initialize MCP session: {e}", exc_info=True)
                # Cleanup HTTP transport
                try:
                    await http_cm.__aexit__(None, None, None)
                except Exception:
                    pass
                return {"error": f"MCP session init failed: {e}"}
            
            # Store both context managers for proper cleanup later
            context.mcp_registry[server_name] = {
                "session": session,
                "session_cm": session_cm,
                "http_cm": http_cm,
                "transport": "http"
            }
            context.mcp_connected = True
            
            # List available tools
            tools_result = await session.list_tools()
            tool_names = [tool.name for tool in tools_result.tools]
            
            return {
                "status": "connected",
                "server": server_name,
                "url": url,
                "transport": transport,
                "tools": tool_names,
                "tool_count": len(tool_names)
            }
        
        else:
            return {
                "error": f"Unsupported transport '{transport}' or missing URL. Use transport='http' with a valid URL."
            }
            
    except Exception as e:
        logger.error(f"Failed to connect to MCP server: {e}", exc_info=True)
        return {
            "error": f"Connection failed: {str(e)}"
        }


async def list_mcp_tools(ctx: RunContextWrapper[TestPurpleAgentContext], server_name: str) -> Dict[str, Any]:
    """
    List all available tools from a connected MCP server.
    
    Args:
        server_name: Name of the connected MCP server
        
    Returns:
        List of available tools with descriptions
        
    Example:
        result = await list_mcp_tools(ctx, "browsergym")
        # Returns: {"server": "browsergym", "tools": [{"name": "get_observation", "description": "..."}]}
    """
    context = ctx.context
    
    # Check if connected
    if server_name not in context.mcp_registry:
        return {
            "error": f"Not connected to MCP server '{server_name}'. Call connect_to_mcp first."
        }
    
    try:
        conn_info = context.mcp_registry[server_name]
        session = conn_info["session"] if isinstance(conn_info, dict) else conn_info
        tools_result = await session.list_tools()
        
        tools_info = []
        for tool in tools_result.tools:
            tools_info.append({
                "name": tool.name,
                "description": tool.description or "No description",
                "input_schema": tool.inputSchema
            })
        return {
            "server": server_name,
            "tools": tools_info,
            "tool_count": len(tools_info)
        }
        
    except Exception as e:
        logger.error(f"Failed to list MCP tools: {e}", exc_info=True)
        return {
            "error": f"Failed to list tools: {str(e)}"
        }


async def call_mcp_tool(
    ctx: RunContextWrapper[TestPurpleAgentContext],
    server_name: str,
    tool_name: str,
    arguments: Dict[str, Any] | None = None
) -> Dict[str, Any]:
    """
    Call a tool on a connected MCP server.
    
    Args:
        server_name: Name of the connected MCP server
        tool_name: Name of the tool to call
        arguments: Tool arguments as a dictionary
        
    Returns:
        Tool execution result
        
    Example:
        # Get observation
        result = await call_mcp_tool(ctx, "browsergym", "get_observation", {})
        
        # Execute action
        result = await call_mcp_tool(ctx, "browsergym", "execute_actions", {
            "actions": [{"action": "click", "bid": "12"}]
        })
    """
    context = ctx.context
    
    # Check if connected
    if server_name not in context.mcp_registry:
        return {
            "error": f"Not connected to MCP server '{server_name}'. Call connect_to_mcp first."
        }
    
    try:
        conn_info = context.mcp_registry[server_name]
        session = conn_info["session"] if isinstance(conn_info, dict) else conn_info
        
        # Ensure arguments is a dict (LLM may pass as JSON string)
        if arguments is None:
            arguments = {}
        elif isinstance(arguments, str):
            try:
                import json
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                arguments = {}
        
        # Call the tool
        result = await session.call_tool(tool_name, arguments=arguments)
        
        # Parse result content
        response_payload: Dict[str, Any]
        if hasattr(result, 'content') and result.content:
            # Extract text from content parts
            if isinstance(result.content, list):
                response_data: Dict[str, Any] = {}
                for part in result.content:
                    if hasattr(part, 'text'):
                        try:
                            import json
                            parsed = json.loads(part.text)
                            response_data.update(parsed)
                        except Exception:
                            response_data['text'] = part.text
                response_payload = {
                    "status": "success",
                    "tool": tool_name,
                    "server": server_name,
                    "result": response_data
                }
            else:
                response_payload = {
                    "status": "success",
                    "tool": tool_name,
                    "server": server_name,
                    "result": str(result.content)
                }
        else:
            response_payload = {
                "status": "success",
                "tool": tool_name,
                "server": server_name,
                "result": str(result)
            }

        if tool_name == "get_observation":
            _log_observation_result(server_name, response_payload)
        
        # Update context when execute_actions indicates task completion
        if tool_name == "execute_actions":
            result_data = response_payload.get("result", {})
            results_list = result_data.get("results", [])
            
            # Check all action results for task completion
            for action_result in results_list:
                if isinstance(action_result, dict):
                    reward = action_result.get("reward", 0.0)
                    done = action_result.get("done", False)
                    
                    # Update context with highest reward seen
                    if reward > context.final_reward:
                        context.final_reward = reward
                    
                    # Mark task complete if done
                    if done or reward >= 1.0:
                        context.task_complete = True
                        context.final_reward = max(context.final_reward, reward)
                        logger.info(f"Task completed: reward={context.final_reward}")
            
            # Increment actions taken
            context.actions_taken += len(results_list)

        return response_payload
        
    except Exception as e:
        logger.error(f"Failed to call MCP tool {tool_name}: {e}", exc_info=True)
        return {
            "error": f"Tool call failed: {str(e)}",
            "tool": tool_name,
            "server": server_name
        }


async def disconnect_mcp(ctx: RunContextWrapper[TestPurpleAgentContext], server_name: str) -> Dict[str, Any]:
    """
    Disconnect from an MCP server and cleanup resources.
    
    Args:
        server_name: Name of the connected MCP server
        
    Returns:
        Disconnection status
        
    Example:
        result = await disconnect_mcp(ctx, "browsergym")
        # Returns: {"status": "disconnected", "server": "browsergym"}
    """
    context = ctx.context
    
    # Check if connected
    if server_name not in context.mcp_registry:
        return {
            "status": "not_connected",
            "server": server_name,
            "message": "Already disconnected or never connected"
        }
    
    try:
        conn_info = context.mcp_registry[server_name]
        
        # Handle dict format with session_cm and http_cm
        if isinstance(conn_info, dict):
            session_cm = conn_info.get("session_cm")
            http_cm = conn_info.get("http_cm") or conn_info.get("context_manager")
            
            # Exit session context manager first (this closes the MCP session)
            if session_cm:
                try:
                    await session_cm.__aexit__(None, None, None)
                except Exception:
                    pass
            
            # Then exit HTTP transport context manager
            if http_cm:
                try:
                    await http_cm.__aexit__(None, None, None)
                except Exception:
                    pass
        else:
            # Old format - just close the session
            session = conn_info
            if hasattr(session, 'close'):
                await session.close()
        
        # Remove from registry
        del context.mcp_registry[server_name]
        
        # Update connection status
        if not context.mcp_registry:
            context.mcp_connected = False
        
        return {
            "status": "disconnected",
            "server": server_name
        }
        
    except Exception as e:
        logger.error(f"Failed to disconnect from MCP server: {e}", exc_info=True)
        return {
            "error": f"Disconnect failed: {str(e)}",
            "server": server_name
        }


__all__ = [
    "connect_to_mcp",
    "list_mcp_tools",
    "call_mcp_tool",
    "disconnect_mcp",
]
