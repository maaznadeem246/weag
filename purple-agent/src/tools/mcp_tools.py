"""
MCP client tools for Test Purple Agent.

⚠️ DEPRECATED: This module is kept for reference only.
Use mcp_proxy_tools.py instead for dynamic MCP server connections.

The new proxy tools approach allows connecting to ANY MCP server at runtime
without hardcoding specific tools. See mcp_proxy_tools.py for the new implementation.

Legacy tools for connecting to Green Agent's MCP server and executing BrowserGym actions.
"""

import asyncio
import json
import time
from typing import Any, Dict

from src.agent.context import TestPurpleAgentContext


async def connect_to_mcp_server(ctx: Any) -> Dict[str, Any]:
    """
    Connect to Green Agent's MCP server using connection details from A2A messages.
    
    Extracts MCP connection details from incoming A2A messages and establishes connection.
    Implements Establish stdio MCP client connection.
    
    Args:
        ctx: RunContextWrapper[TestPurpleAgentContext]
        
    Returns:
        Connection result with status and details
    """
    context: TestPurpleAgentContext = ctx.context
    
    print(f"[PURPLE] connect_to_mcp_server called, incoming_messages count: {len(context.incoming_messages)}")
    
    # Early return if already connected
    if context.mcp_connected and context.mcp_client:
        print("[PURPLE] Already connected to MCP server, skipping reconnection")
        return {
            "status": "success",
            "message": "Already connected to MCP server",
            "tools_available": 0
        }
    
    # Check connection attempt limit (max 2 attempts)
    if context.mcp_connection_attempts >= 2:
        print(f"[PURPLE] Maximum connection attempts (2) reached, aborting")
        return {
            "status": "failed",
            "error": "Maximum connection attempts exceeded",
            "message": "Failed to connect to MCP server after 2 attempts. Please check MCP server logs.",
            "attempts": context.mcp_connection_attempts
        }
    
    # Increment attempt counter
    context.mcp_connection_attempts += 1
    print(f"[PURPLE] Connection attempt {context.mcp_connection_attempts}/2")
    
    # Try to extract MCP details from incoming messages if not already present
    if not context.mcp_connection_details and context.incoming_messages:
        for msg in context.incoming_messages:
            # Check for MCP details in message data
            if isinstance(msg, dict):
                # Direct MCP details at message level
                # Check for either HTTP (url) or stdio (command) fields
                if ("url" in msg or "command" in msg) and "transport" in msg:
                    context.mcp_connection_details = msg
                    break
                
                # Check message parts array
                if "parts" in msg and isinstance(msg["parts"], list):
                    for part in msg["parts"]:
                        if not isinstance(part, dict):
                            continue
                        
                        # Check for mcp_connection_details field in part
                        if "mcp_connection_details" in part:
                            context.mcp_connection_details = part["mcp_connection_details"]
                            break
                        
                        # Check data field in part
                        if "data" in part and isinstance(part["data"], dict):
                            data = part["data"]
                            # Direct MCP details in data (http or stdio)
                            if ("url" in data or "command" in data) and "transport" in data:
                                context.mcp_connection_details = data
                                break
                            # MCP details nested in data.mcp_connection_details
                            if "mcp_connection_details" in data:
                                context.mcp_connection_details = data["mcp_connection_details"]
                                break
                    
                    # Break outer loop if found
                    if context.mcp_connection_details:
                        break
                
                # Fallback: check top-level data field
                if "data" in msg and isinstance(msg["data"], dict):
                    data = msg["data"]
                    if ("url" in data or "command" in data) and "transport" in data:
                        context.mcp_connection_details = data
                        break
                
                # Check mcp_connection_details field at message level
                if "mcp_connection_details" in msg:
                    context.mcp_connection_details = msg["mcp_connection_details"]
                    break
    
    if not context.mcp_connection_details:
        print(f"[PURPLE] No MCP connection details found in {len(context.incoming_messages)} messages")
        return {
            "status": "failed",
            "error": "No MCP connection details received from Green Agent",
            "message": "Waiting for Green Agent to send MCP details via A2A message. Check incoming_messages.",
            "incoming_messages_count": len(context.incoming_messages)
        }
    
    print(f"[PURPLE] Found MCP connection details: transport={context.mcp_connection_details.get('transport', 'unknown')}, url={context.mcp_connection_details.get('url', context.mcp_connection_details.get('command', 'N/A'))}")
    conn_details = context.mcp_connection_details
    
    try:
        # Import MCP client SDK
        from mcp import ClientSession
        
        # Check transport type
        transport = conn_details.get("transport", "http")  # Default to http
        
        if transport == "http":
            # HTTP transport (new default)
            from mcp.client.streamable_http import streamablehttp_client
            
            url = conn_details.get("url")
            if not url:
                return {
                    "status": "failed",
                    "error": "No URL provided in MCP connection details",
                    "message": "HTTP transport requires 'url' field"
                }
            
            print(f"[PURPLE] Connecting to MCP HTTP server: {url}")
            
            # Establish connection with streamable HTTP transport
            print("[PURPLE] Starting MCP streamable HTTP transport...")
            try:
                # Create streamable HTTP client connection
                transport_cm = streamablehttp_client(url)
                
                # Enter the context manager and wait for connection
                read, write, _ = await asyncio.wait_for(
                    transport_cm.__aenter__(),
                    timeout=30.0  # 30 second timeout
                )
                print("[PURPLE] MCP streamable HTTP transport established")
                
            except asyncio.TimeoutError:
                return {
                    "status": "failed",
                    "error": "Timeout connecting to MCP HTTP server",
                    "message": f"MCP server at {url} took longer than 30 seconds to respond"
                }
            except Exception as e:
                return {
                    "status": "failed",
                    "error": f"Failed to establish MCP HTTP connection: {str(e)}",
                    "message": f"Failed to connect to MCP HTTP server at {url}: {str(e)}"
                }
        
        elif transport == "stdio":
            # stdio transport (legacy/deprecated)
            from mcp import StdioServerParameters
            from mcp.client.stdio import stdio_client
            
            command = conn_details.get("command", "python")
            args = conn_details.get("args", [])
            
            print(f"[PURPLE] Connecting to MCP stdio server: {command} {' '.join(args)}")
            
            # Create MCP client
            server_params = StdioServerParameters(
                command=command,
                args=args,
                env=conn_details.get("env")
            )
            
            # Establish connection with timeout
            transport_cm = stdio_client(server_params)
            
            print("[PURPLE] Starting MCP stdio transport...")
            try:
                # Enter the context manager and wait for transport with timeout
                read, write = await asyncio.wait_for(
                    transport_cm.__aenter__(),
                    timeout=30.0  # 30 second timeout
                )
                print("[PURPLE] MCP stdio transport established")
            except asyncio.TimeoutError:
                # On timeout, we need to clean up the transport that may have partially started
                # Use shield to ensure cleanup completes even if we're in a cancelled context
                try:
                    await asyncio.shield(transport_cm.__aexit__(None, None, None))
                except Exception:
                    pass  # Cleanup failed, but we're already returning an error
                return {
                    "status": "failed",
                    "error": "Timeout waiting for MCP stdio server to start",
                    "message": "MCP stdio server took longer than 30 seconds to respond"
                }
            except Exception as e:
                # On other errors during transport setup, try to clean up
                try:
                    await asyncio.shield(transport_cm.__aexit__(None, None, None))
                except Exception:
                    pass
                return {
                    "status": "failed",
                    "error": f"Failed to establish MCP stdio transport: {str(e)}",
                    "message": f"Failed to connect to MCP stdio server: {str(e)}"
                }
        
        else:
            return {
                "status": "failed",
                "error": f"Unsupported transport: {transport}",
                "message": f"Only 'http' and 'stdio' transports are supported, got: {transport}"
            }
        
        # Create session
        print("[PURPLE] Initializing MCP session...")
        session = ClientSession(read, write)
        try:
            await asyncio.wait_for(
                session.initialize(),
                timeout=30.0  # 30 second timeout (increased from 10s)
            )
            print("[PURPLE] MCP session initialized")
        except asyncio.TimeoutError:
            # Cleanup transport on session init timeout
            try:
                await asyncio.shield(transport_cm.__aexit__(None, None, None))
            except Exception:
                pass
            return {
                "status": "failed",
                "error": "Timeout initializing MCP session",
                "message": "MCP session initialization took longer than 30 seconds. MCP server may not be responding."
            }
        except Exception as e:
            # Cleanup transport on session init error
            try:
                await asyncio.shield(transport_cm.__aexit__(None, None, None))
            except Exception:
                pass
            return {
                "status": "failed",
                "error": f"Failed to initialize MCP session: {str(e)}",
                "message": f"Failed to connect to MCP server: {str(e)}"
            }
        
        # List available tools
        print("[PURPLE] Listing MCP tools...")
        try:
            tools_response = await asyncio.wait_for(
                session.list_tools(),
                timeout=5.0
            )
            tools_count = len(tools_response.tools) if hasattr(tools_response, 'tools') else 0
            print(f"[PURPLE] Found {tools_count} MCP tools")
        except asyncio.TimeoutError:
            tools_count = 0
            print("[PURPLE] Warning: Timeout listing tools")
        except Exception as e:
            tools_count = 0
            print(f"[PURPLE] Warning: Failed to list tools: {e}")
        
        # Store client and transport context manager in context
        context.mcp_client = session
        context.mcp_transport_cm = transport_cm
        context.mcp_connected = True
        
        return {
            "status": "success",
            "message": f"Connected to MCP server via {command}",
            "tools_available": tools_count
        }
        
    except ImportError as e:
        return {
            "status": "failed",
            "error": f"MCP SDK not installed: {str(e)}",
            "message": "Install with: pip install mcp"
        }
    except Exception as e:
        return {
            "status": "failed",
            "error": str(e),
            "message": f"Failed to connect to MCP server: {str(e)}"
        }


async def mcp_get_observation(ctx: Any) -> Dict[str, Any]:
    """
    Get current observation from BrowserGym environment via MCP.
    
    Implements Call MCP get_observation tool.
    
    Args:
        ctx: RunContextWrapper[TestPurpleAgentContext]
        
    Returns:
        Observation with done/reward status and parsed elements
    """
    context: TestPurpleAgentContext = ctx.context
    
    if not context.environment_initialized:
        return {
            "status": "failed",
            "error": "Environment not initialized",
            "message": "Call mcp_initialize_environment first"
        }
    
    try:
        session = context.mcp_client
        
        # Call MCP get_observation tool
        result = await session.call_tool(
            "get_observation",
            arguments={}
        )
        
        # Parse observation
        obs_data = json.loads(result.content[0].text) if result.content else {}
        
        # Extract key information
        done = obs_data.get("done", False)
        reward = obs_data.get("reward", 0.0)
        axtree = obs_data.get("axtree", "")
        
        # Update context if task is complete
        if done:
            context.task_complete = True
            context.final_reward = reward
        
        return {
            "status": "success",
            "done": done,
            "reward": reward,
            "axtree_snippet": axtree[:500] if axtree else "",  # First 500 chars for agent analysis
            "full_axtree": axtree,
            "message": f"Observation retrieved (done={done}, reward={reward})"
        }
        
    except Exception as e:
        return {
            "status": "failed",
            "error": str(e),
            "message": f"Failed to get observation: {str(e)}"
        }


async def mcp_execute_action(ctx: Any, action: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute action in BrowserGym environment via MCP.
    
    Implements Call MCP execute_actions tool.
    
    Args:
        ctx: RunContextWrapper[TestPurpleAgentContext]
        action: Action dict with action_type and parameters
        
    Returns:
        Execution result
    """
    context: TestPurpleAgentContext = ctx.context
    
    if not context.mcp_connected or not context.mcp_client:
        return {
            "status": "failed",
            "error": "Not connected to MCP server",
            "message": "Call connect_to_mcp_server first"
        }
    
    try:
        session = context.mcp_client
        
        # Call MCP execute_actions tool
        result = await session.call_tool(
            "execute_actions",
            arguments={
                "actions": [action]
            }
        )
        
        # Parse result
        result_data = json.loads(result.content[0].text) if result.content else {}
        
        # Update action count
        context.actions_taken += 1
        
        return {
            "status": "success",
            "action": action,
            "result": result_data,
            "actions_taken": context.actions_taken,
            "message": f"Action executed: {action.get('action_type', 'unknown')}"
        }
        
    except Exception as e:
        return {
            "status": "failed",
            "error": str(e),
            "action": action,
            "message": f"Failed to execute action: {str(e)}"
        }


__all__ = [
    "connect_to_mcp_server",
    "mcp_get_observation",
    "mcp_execute_action",
]
