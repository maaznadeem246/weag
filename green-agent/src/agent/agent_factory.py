"""
Agent factory for creating configured evaluation agents.

Provides:
- create_evaluation_agent(): Factory function for EvaluationAgent
"""

import os
from typing import Any

from agents import Agent, set_default_openai_client, set_default_openai_api, ModelSettings
from openai import AsyncOpenAI
from openinference.instrumentation.openai_agents import OpenAIAgentsInstrumentor
from langfuse import get_client

from src.config.settings import settings
from src.utils.llm_provider import LLMConfig, setup_llm_client
from src.agent.context import AgentContext
from src.agent.guardrails.input_guardrails import validate_evaluation_request, validate_evaluation_request_guardrail
from src.agent.guardrails.output_guardrails import validate_evaluation_artifact, validate_evaluation_artifact_guardrail
from src.agent.instructions import EVALUATION_AGENT_INSTRUCTIONS
from src.agent.tools import AGENT_TOOLS
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Best-effort: initialize Langfuse with blocked scopes before enabling OTel-based
# auto-instrumentation so noisy A2A spans are not exported.
try:
    from langfuse import Langfuse

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
except Exception:
    pass

# Initialize OpenInference instrumentation for Langfuse tracing
OpenAIAgentsInstrumentor().instrument()

# Initialize Langfuse client for tracing
try:
    langfuse = get_client()
    if langfuse.auth_check():
        logger.info("✓ Green Agent: Langfuse client is authenticated and ready!")
    else:
        logger.warning("⚠ Green Agent: Langfuse authentication failed. Check your credentials.")
except Exception as e:
    logger.warning(f"⚠ Green Agent: Failed to initialize Langfuse client: {e}")
    langfuse = None

# Get trace ID from environment for unified tracing
# This allows Green Agent to participate in the same trace started by kickstart script
ASSESSMENT_TRACE_ID = os.environ.get("ASSESSMENT_TRACE_ID")
if ASSESSMENT_TRACE_ID and langfuse:
    logger.info(f"✓ Green Agent: Using unified trace context (trace_id: {ASSESSMENT_TRACE_ID})")


def create_evaluation_agent() -> Agent[AgentContext]:
    """
    Create configured EvaluationAgent for orchestrating evaluations.
    
    Implements Agent factory with tools, model, temperature, max_iterations.
    
    Configuration:
    - Tools: 10 context-aware tools (environment, monitoring, communication, evaluation)
    - Model: Flexible LLM provider (OpenAI, Gemini, LiteLLM/OpenRouter)
    - Temperature: 0.1 (low for consistent orchestration)
    - Max iterations: 50 (prevent reasoning loops)
    
    Returns:
        Agent[AgentContext] configured for evaluation orchestration
        
    Example:
        agent = create_evaluation_agent()
        result = await Runner.run(agent, user_input, context=eval_context, session=session)
    """
    # Langfuse tracing is automatically handled by OpenInference instrumentation
    # Agent name "BrowserGymEvaluator" will be visible in Langfuse dashboard
    logger.info("OpenInference instrumentation enabled for Green Agent")
    
    # Configure to use Chat Completions API instead of Responses API
    # Gemini doesn't support Responses API, only Chat Completions
    set_default_openai_api("chat_completions")
    
    # Setup LLM client using abstraction layer (GREEN_ overrides allow per-agent config)
    llm_config = LLMConfig.from_env("GREEN_")
    client, model, _ = setup_llm_client(llm_config, "GREEN_")
    
    # For OpenAI/Gemini, set the custom client as default
    # For LiteLLM, client is None and model is LitellmModel instance
    if client is not None:
        set_default_openai_client(client)
        model_name = model  # String model name
    else:
        model_name = model  # LitellmModel instance (used directly as Agent.model)
    
    # Create agent with configuration
    agent = Agent[AgentContext](
        name="BrowserGymEvaluator",
        instructions=EVALUATION_AGENT_INSTRUCTIONS,
        tools=AGENT_TOOLS,
        model=model_name,  # String for OpenAI/Gemini, LitellmModel for LiteLLM
        # Note: temperature removed - some models (o1, o3) only support default temperature
        # Guardrails: input and output validation
        input_guardrails=[validate_evaluation_request_guardrail],
        output_guardrails=[validate_evaluation_artifact_guardrail],
    )
    
    # Get display name for logging
    display_model = model_name if isinstance(model_name, str) else llm_config.litellm_model
    
    logger.info(
        "EvaluationAgent created",
        extra={
            "model": display_model,
            "provider": llm_config.provider.value,
            "max_iterations": llm_config.max_iterations,
            "tools_count": len(AGENT_TOOLS),
        }
    )
    
    return agent


# Global agent instance (created once at startup)
_evaluation_agent: Agent[AgentContext] | None = None


def get_evaluation_agent() -> Agent[AgentContext]:
    """
    Get or create global EvaluationAgent instance.
    
    Returns:
        Singleton EvaluationAgent instance
    """
    global _evaluation_agent
    
    if _evaluation_agent is None:
        _evaluation_agent = create_evaluation_agent()
    
    return _evaluation_agent


__all__ = [
    "create_evaluation_agent",
    "get_evaluation_agent",
]
