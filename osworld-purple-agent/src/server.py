"""
OSWorld Purple Agent — A2A HTTP Server.

Builds the A2A Starlette application with AgentCard, DefaultRequestHandler,
and InMemoryTaskStore.  Exposes a `main()` entry point for both the
`osworld-agent` CLI script and `python -m src.server`.

Usage:
    osworld-agent
    python -m uvicorn src.server:app --host 0.0.0.0 --port 8000
"""

import logging
import sys

import uvicorn
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill

from .config import config as agent_config
from .executor import OsworldAgentExecutor


logger = logging.getLogger(__name__)


def _build_agent_card() -> AgentCard:
    """Build the A2A AgentCard for OSWorld Purple Agent."""
    skill = AgentSkill(
        id="osworld_task",
        name="OSWorld Task Execution",
        description="Executes computer use tasks on Ubuntu desktop via pyautogui actions",
        tags=["computer-use", "pyautogui"],
        input_modes=["text", "file", "data"],
        output_modes=["text", "data"],
    )

    return AgentCard(
        name=agent_config.agent_name,
        description="A2A purple agent for OSWorld computer use benchmark",
        url=f"http://{agent_config.host}:{agent_config.port}/",
        version=agent_config.agent_version,
        capabilities=AgentCapabilities(streaming=False, push_notifications=False),
        skills=[skill],
        default_input_modes=["text", "file", "data"],
        default_output_modes=["text", "data"],
    )


def _build_app() -> "A2AStarletteApplication":
    """Assemble the A2A Starlette application."""
    executor = OsworldAgentExecutor()
    agent_card = _build_agent_card()

    request_handler = DefaultRequestHandler(
        agent_executor=executor,
        task_store=InMemoryTaskStore(),
    )

    return A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=request_handler,
    )


# ASGI app — imported by uvicorn or used in tests.
app = _build_app().build()


def main() -> None:
    """Entry point — configure logging and start uvicorn."""
    logging.basicConfig(
        level=getattr(logging, agent_config.log_level, logging.INFO),
        format=agent_config.log_format,
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    logger.info(
        "Starting %s v%s on http://%s:%d/",
        agent_config.agent_name,
        agent_config.agent_version,
        agent_config.host,
        agent_config.port,
    )

    uvicorn.run(
        "src.server:app",
        host=agent_config.host,
        port=agent_config.port,
        log_level=agent_config.log_level.lower(),
    )


if __name__ == "__main__":
    main()
