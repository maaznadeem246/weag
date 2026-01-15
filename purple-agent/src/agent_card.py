"""
Purple Agent Card configuration for A2A protocol.
Defines agent capabilities, skills, and metadata.
"""

from a2a.types import AgentCapabilities, AgentCard, AgentSkill


def create_purple_agent_card(agent_url: str) -> AgentCard:
    """
    Create Purple Agent card for A2A discovery.
    
    Args:
        agent_url: Base URL where Purple Agent is hosted
        
    Returns:
        AgentCard with Purple Agent capabilities
    """
    # Define Purple Agent's skill
    evaluation_skill = AgentSkill(
        id="browser_task_evaluation",
        name="BrowserGym Task Evaluation",
        description=(
            "Evaluates web-based tasks using BrowserGym environments. "
            "Connects to MCP servers for browser control, executes actions, "
            "and completes assigned tasks."
        ),
        tags=["browsergym", "evaluation", "web-automation", "mcp"],
        examples=[
            "Complete miniwob.click-test task",
            "Execute webarena shopping task",
            "Solve visualwebarena navigation challenge"
        ],
    )
    
    # Create agent card
    agent_card = AgentCard(
        name="BrowserGym Purple Agent",
        description=(
            "Evaluation agent for BrowserGym benchmark tasks. "
            "Receives task assignments from Green Agent, connects to MCP servers "
            "for browser control, and executes web-based evaluation tasks."
        ),
        url=agent_url,
        version="1.0.0",
        default_input_modes=["text"],
        default_output_modes=["text"],
        capabilities=AgentCapabilities(
            streaming=True,
            multi_turn=True,
        ),
        skills=[evaluation_skill],
    )
    
    return agent_card


def get_agent_card_dict(agent_url: str) -> dict:
    """
    Get Purple Agent card as dict for JSON serialization.
    
    Args:
        agent_url: Base URL where Purple Agent is hosted
        
    Returns:
        Dict representation of agent card
    """
    card = create_purple_agent_card(agent_url)
    return card.model_dump(mode='json', exclude_none=True)
