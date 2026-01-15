"""
Agent factory for Test Purple Agent.

Creates test purple agent using OpenAI Agents SDK with dynamic MCP proxy tools.
Uses generic proxy tools to connect to ANY MCP server at runtime.
"""

import os
import logging
from typing import Any

from langfuse import observe
from agents import Agent, function_tool, set_default_openai_client, set_default_openai_api
from openinference.instrumentation.openai_agents import OpenAIAgentsInstrumentor
from langfuse import get_client

from src.llm_provider import LLMConfig, LLMProvider, setup_llm_client
from src.agent.context import TestPurpleAgentContext
from src.agent.instructions import TEST_PURPLE_AGENT_INSTRUCTIONS
from src.config import PurpleAgentConfig
from src.tools.mcp_proxy_tools import (
    connect_to_mcp,
    list_mcp_tools,
    call_mcp_tool,
    disconnect_mcp,
)

logger = logging.getLogger(__name__)

# Best-effort: initialize Langfuse with blocked scopes before enabling OTel-based
# auto-instrumentation so noisy A2A spans are not exported.
try:
    from langfuse import Langfuse
    
    # Default blocked A2A SDK scopes
    blocked_list = [
        "a2a", "a2a.server", "a2a.client",
        "a2a.server.events", "a2a.server.events.event_queue",
        "a2a.server.events.event_consumer", "a2a.server.request_handlers",
        "a2a.server.request_handlers.default_request_handler",
        "a2a.server.apps", "a2a.server.tasks",
        "a2a.client.resolver", "a2a.client.factory",
    ]
    
    langfuse_enabled = os.getenv("LANGFUSE_ENABLED", "true").lower() == "true"
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")
    
    if langfuse_enabled and public_key and secret_key:
        Langfuse(
            public_key=public_key,
            secret_key=secret_key,
            host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
            blocked_instrumentation_scopes=blocked_list,
            debug=(os.getenv("LANGFUSE_DEBUG", "false").lower() == "true"),
        )
except Exception:
    pass

# Initialize OpenInference instrumentation for Langfuse tracing
OpenAIAgentsInstrumentor().instrument()

# Initialize Langfuse client for tracing
try:
    langfuse = get_client()
    if not langfuse.auth_check():
        logger.warning("⚠ Langfuse authentication failed")
except Exception:
    langfuse = None

# Get trace ID from environment for unified tracing
# This allows Purple Agent to participate in the same trace started by kickstart script
ASSESSMENT_TRACE_ID = os.environ.get("ASSESSMENT_TRACE_ID")


# Wrap MCP proxy tools with @function_tool decorator for OpenAI Agents SDK
from agents import RunContextWrapper

@function_tool
@observe()
async def tool_connect_to_mcp(
    ctx: RunContextWrapper,
    server_name: str,
    url: str,
    transport: str = "http"
) -> Any:
    """
    Connect to an MCP server at the specified URL.
    
    Read the task message to find the MCP connection details:
    - Look for "MCP SERVER CONNECTION" section
    - Extract the URL (format: http://host:port/path)
    - Use transport="http" (or whatever is specified)
    
    Args:
        server_name: Server name to use (use "browsergym" for this task)
        url: Full HTTP URL to MCP server (e.g., "http://127.0.0.1:8001/mcp")
        transport: Transport protocol, typically "http" (default: "http")
        
    Returns:
        Connection status with list of available tools
        
    Example:
        tool_connect_to_mcp("browsergym", "http://127.0.0.1:8001/mcp", "http")
    """
    return await connect_to_mcp(ctx, server_name, url, transport)


@function_tool
@observe()
async def tool_list_mcp_tools(ctx: RunContextWrapper, server_name: str) -> Any:
    """
    List all available tools from a connected MCP server.
    
    Args:
        server_name: Name of the connected MCP server
        
    Returns:
        List of tools with descriptions and schemas
    """
    return await list_mcp_tools(ctx, server_name)


@function_tool(strict_mode=False)
@observe()
async def tool_call_mcp_tool(
    ctx: RunContextWrapper,
    server_name: str,
    tool_name: str,
    arguments: dict[str, Any] | None = None
) -> Any:
    """
    Call a tool on a connected MCP server.
    
    Args:
        server_name: Name of the connected MCP server
        tool_name: Name of the tool to call (e.g., "get_observation", "execute_actions")
        arguments: Tool arguments as a dictionary
        
    Returns:
        Tool execution result
    """
    return await call_mcp_tool(ctx, server_name, tool_name, arguments or {})


@function_tool
@observe()
async def tool_disconnect_mcp(ctx: RunContextWrapper, server_name: str) -> Any:
    """
    Disconnect from an MCP server and cleanup resources.
    
    Args:
        server_name: Name of the connected MCP server
        
    Returns:
        Disconnection status
    """
    return await disconnect_mcp(ctx, server_name)


# Agent tools: 4 generic MCP proxy tools
PURPLE_AGENT_TOOLS = [
    tool_connect_to_mcp,
    tool_list_mcp_tools,
    tool_call_mcp_tool,
    tool_disconnect_mcp,
]


def create_test_purple_agent(config: PurpleAgentConfig) -> Agent[TestPurpleAgentContext]:
    """
    Create test purple agent with dynamic MCP proxy tools.
    
    The agent starts with 4 generic proxy tools that can connect to ANY MCP server
    at runtime. When Green Agent sends MCP connection details via A2A, the agent
    uses these tools to establish connection and execute MCP tools dynamically.
    
    Configures agent with:
    - Flexible LLM provider (OpenAI, Gemini, LiteLLM/OpenRouter)
    - 4 MCP proxy tools (connect, list, call, disconnect)
    - Dynamic MCP server connection (no hardcoded tools)
    - Langfuse tracing via OpenInference (automatic)
    
    Args:
        config: Purple agent configuration
        
    Returns:
        Configured Agent[TestPurpleAgentContext]
    """
    # Configure to use Chat Completions API instead of Responses API
    # Gemini doesn't support Responses API, only Chat Completions
    set_default_openai_api("chat_completions")
    
    # Setup LLM client using abstraction layer (PURPLE_ overrides allow per-agent config)
    llm_config = LLMConfig.from_env("PURPLE_")
    client, model, _ = setup_llm_client(llm_config, "PURPLE_")
    
    # For OpenAI/Gemini, set the custom client as default
    # For LiteLLM, client is None and model is LitellmModel instance
    if client is not None:
        set_default_openai_client(client, use_for_tracing=True)
        model_name = model  # String model name
    else:
        model_name = model  # LitellmModel instance (used directly as Agent.model)
    
    # Create agent
    agent = Agent[TestPurpleAgentContext](
        name="TestPurpleAgent",
        instructions=TEST_PURPLE_AGENT_INSTRUCTIONS,
        tools=PURPLE_AGENT_TOOLS,
        model=model_name,  # String for OpenAI/Gemini, LitellmModel for LiteLLM
    )
    
    # Get display name for logging
    display_model = model_name if isinstance(model_name, str) else llm_config.litellm_model
    
    logger.info(f"Created Purple Agent with model: {display_model}, provider: {llm_config.provider.value}")
    
    return agent


__all__ = ["create_test_purple_agent", "PURPLE_AGENT_TOOLS"]
