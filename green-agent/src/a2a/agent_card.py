"""
A2A Agent Card Generator for BrowserGym Green Agent.

Provides A2A-compliant agent card generation using the official A2A SDK.
Per research.md Decision 1 and contracts/agent-card.json schema.
"""

import json
from pathlib import Path
from typing import Optional

from a2a.types import (
    AgentCard,
    AgentCapabilities,
    AgentSkill,
)

from src.benchmarks.profiles import BenchmarkProfileRegistry
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Protocol version per A2A spec
A2A_PROTOCOL_VERSION = "0.3.0"

# Agent metadata
AGENT_VERSION = "1.0.0"
AGENT_NAME = "BrowserGym Green Agent"

# Provider info
PROVIDER_ORG = "WEAG"
PROVIDER_URL = "https://github.com/weag-project"


def get_supported_benchmarks() -> list[str]:
    """Get list of supported benchmark IDs."""
    registry = BenchmarkProfileRegistry.instance()
    return registry.supported_benchmarks()


def get_benchmark_display_names() -> str:
    """Get formatted display names of supported benchmarks.
    
    Returns:
        Comma-separated string of benchmark display names
    """
    registry = BenchmarkProfileRegistry.instance()
    display_names = [profile.display_name for profile in registry.all_profiles()]
    return ", ".join(display_names)


def get_agent_description() -> str:
    """Generate dynamic agent description with current benchmark support.
    
    Returns:
        Agent description string with up-to-date benchmark list
    """
    benchmark_names = get_benchmark_display_names()
    return (
        "Evaluation harness for web automation benchmarks using BrowserGym. "
        f"Supports {benchmark_names}."
    )


def create_evaluation_skill() -> AgentSkill:
    """Create the BrowserGym evaluation skill definition.
    
    Returns:
        AgentSkill for browsergym-evaluation
    """
    benchmarks = get_supported_benchmarks()
    benchmark_list = ", ".join(benchmarks)
    
    return AgentSkill(
        id="browsergym-evaluation",
        name="BrowserGym Evaluation",
        description=(
            f"Evaluate purple agents on web automation benchmarks ({benchmark_list}). "
            "Uses Dynamic MCP Server for tool delivery."
        ),
        tags=["evaluation", "benchmark", "web-automation", "browsergym", "mcp"],
        examples=[
            json.dumps({
                "participants": {
                    "purple_agent": "https://purple-agent.example.com:443"
                },
                "config": {
                    "task_id": "miniwob.click-test",
                    "max_steps": 50,
                    "seed": 42
                }
            }, indent=2)
        ],
        input_modes=["application/json", "text/plain"],
        output_modes=["application/json", "text/plain"],
    )


def create_agent_card(
    agent_url: str,
    *,
    streaming: bool = True,
    push_notifications: bool = False,
    state_transition_history: bool = True,
    version: Optional[str] = None,
) -> AgentCard:
    """Create A2A-compliant agent card for BrowserGym Green Agent.
    
    Per research.md Decision 1 - uses A2A SDK's AgentCard class for compliance.
    
    Args:
        agent_url: Public URL for this agent's A2A endpoint
        streaming: Whether agent supports SSE streaming (default: True)
        push_notifications: Whether agent supports push notifications (default: False)
        state_transition_history: Whether agent tracks state history (default: True)
        version: Override agent version (default: AGENT_VERSION)
        
    Returns:
        AgentCard with full A2A-compliant structure
    """
    skill = create_evaluation_skill()
    
    capabilities = AgentCapabilities(
        streaming=streaming,
        push_notifications=push_notifications,
        state_transition_history=state_transition_history,
    )
    
    return AgentCard(
        name=AGENT_NAME,
        description=get_agent_description(),
        url=agent_url,
        version=version or AGENT_VERSION,
        default_input_modes=["application/json", "text/plain"],
        default_output_modes=["application/json", "text/plain"],
        capabilities=capabilities,
        skills=[skill],
    )


def get_agent_card_dict(agent_url: str) -> dict:
    """Get agent card as dictionary for JSON serialization.
    
    Adds protocolVersion and provider fields not directly supported by SDK.
    
    Args:
        agent_url: Public URL for this agent
        
    Returns:
        Dictionary suitable for JSON serialization
    """
    card = create_agent_card(agent_url)
    
    # Convert to dict and add extra fields
    card_dict = {
        "protocolVersion": A2A_PROTOCOL_VERSION,
        "name": card.name,
        "description": card.description,
        "version": card.version,
        "url": card.url,
        "provider": {
            "organization": PROVIDER_ORG,
            "url": PROVIDER_URL,
        },
        "capabilities": {
            "streaming": card.capabilities.streaming if card.capabilities else True,
            "pushNotifications": card.capabilities.push_notifications if card.capabilities else False,
            "stateTransitionHistory": card.capabilities.state_transition_history if card.capabilities else True,
        },
        "defaultInputModes": card.default_input_modes or ["application/json"],
        "defaultOutputModes": card.default_output_modes or ["application/json"],
        "skills": [],
    }
    
    # Add skills
    for skill in card.skills or []:
        skill_dict = {
            "id": skill.id,
            "name": skill.name,
            "description": skill.description,
            "tags": skill.tags or [],
            "examples": skill.examples or [],
            "inputModes": skill.input_modes or ["application/json"],
            "outputModes": skill.output_modes or ["application/json"],
        }
        card_dict["skills"].append(skill_dict)
    
    return card_dict


def get_extended_agent_card(agent_url: str) -> dict:
    """Get extended agent card for authenticated requests.
    
    Includes additional internal information not in public well-known endpoint.
    Per research.md Decision 7 - agent/getCard JSON-RPC method.
    
    Args:
        agent_url: Public URL for this agent
        
    Returns:
        Extended agent card dictionary
    """
    card_dict = get_agent_card_dict(agent_url)
    
    # Add extended info for authenticated clients
    registry = BenchmarkProfileRegistry.instance()
    
    card_dict["extended"] = {
        "benchmarks": {},
        "efficiency_mandates": {
            "token_limit_per_observation": 5000,  # Default, varies by benchmark
            "latency_target_seconds": 2.0,
            "memory_limit_mb": 500,
            "zero_orphaned_processes": True,
        },
        "scoring_formula": {
            "formula": "final_score = task_success × (1 - λ_C × log(C) - λ_L × L)",
            "lambda_c": 0.01,
            "lambda_l": 0.1,
        },
    }
    
    # Add benchmark-specific details
    for profile in registry.all_profiles():
        card_dict["extended"]["benchmarks"][profile.benchmark_id] = {
            "display_name": profile.display_name,
            "token_limit": profile.token_limit,
            "observation_mode": profile.observation_mode.value,
            "extra_tools": [tool.name for tool in profile.extra_tools],
        }
    
    return card_dict


# Convenience function for import
def get_agent_card(agent_url: str) -> AgentCard:
    """Alias for create_agent_card for backward compatibility."""
    return create_agent_card(agent_url)
