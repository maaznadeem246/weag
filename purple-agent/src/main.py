"""
Purple Agent - A2A Server Implementation.

Purple Agent runs as an A2A server, waiting for messages from Green Agent.
Receives task assignments and MCP connection details via A2A messages.

Usage:
    python -m src.purple_agent.main --host 127.0.0.1 --port 9010
"""

import argparse
import asyncio
import logging
import os
import sys
import signal
from pathlib import Path
from dotenv import load_dotenv
import uvicorn

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from src.executor import PurpleAgentExecutor
from src.agent_card import create_purple_agent_card, get_agent_card_dict
from src.config import PurpleAgentConfig



# Load .env from project root (works both locally and in Docker)
project_root = Path(__file__).resolve().parent.parent.parent
load_dotenv(str(project_root / ".env"))

# Ensure logs directory exists (use /home/agent/logs in Docker, local path otherwise)
logs_dir = Path("/home/agent/logs") if Path("/home/agent").exists() else project_root / "purple-agent" / "logs"
logs_dir.mkdir(parents=True, exist_ok=True)

# Initialize Langfuse with blocked instrumentation scopes
try:
    from langfuse import Langfuse
    
    # Default blocked A2A SDK scopes to reduce trace noise
    blocked_list = [
        "a2a", "a2a.server", "a2a.client",
        "a2a.server.events", "a2a.server.events.event_queue",
        "a2a.server.events.event_consumer", "a2a.server.request_handlers",
        "a2a.server.request_handlers.default_request_handler",
        "a2a.server.apps", "a2a.server.tasks",
        "a2a.client.resolver", "a2a.client.factory",
    ]
    
    langfuse_enabled = os.getenv("LANGFUSE_ENABLED", "true").lower() == "true"
    if langfuse_enabled and os.getenv("LANGFUSE_PUBLIC_KEY"):
        Langfuse(
            public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
            secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
            host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
            blocked_instrumentation_scopes=blocked_list,
            debug=(os.getenv("LANGFUSE_DEBUG", "false").lower() == "true"),
        )
except Exception:
    pass

# Suppress verbose logging
logging.getLogger("LiteLLM").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

# Global agent URL for endpoints
_agent_url = ""

logger = logging.getLogger(__name__)


logger = logging.getLogger(__name__)


async def health_check(request):
    """Health check endpoint."""
    return JSONResponse({"status": "healthy", "agent": "purple"})


async def well_known_agent_json(request):
    """Agent discovery endpoint per A2A spec."""
    return JSONResponse(get_agent_card_dict(_agent_url))


async def main():
    """Main entry point for Purple Agent A2A server."""
    global _agent_url
    
    parser = argparse.ArgumentParser(description="Purple Agent A2A Server")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host to bind")
    parser.add_argument("--port", type=int, default=9010, help="Port to bind")
    parser.add_argument("--card-url", type=str, help="External URL for agent card")
    parser.add_argument("--log-level", type=str, default="INFO",
                       choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                       help="Logging level")
    args = parser.parse_args()
    # Install custom asyncio exception handler to suppress noisy AnyIO
    # cancel-scope RuntimeError that can occur during stream shutdown on Windows.
    def _asyncio_exception_handler(loop, context):
        exc = context.get("exception")
        msg = context.get("message", "")
        if exc and isinstance(exc, RuntimeError) and "Attempted to exit cancel scope" in str(exc):
            # Suppress this specific noisy runtime error (cleanup race in AnyIO/mcp client)
            logging.getLogger(__name__).debug("Suppressed AnyIO cancel-scope RuntimeError: %s", str(exc))
            return
        # Fallback to default handler for other exceptions
        loop.default_exception_handler(context)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is not None:
        loop.set_exception_handler(_asyncio_exception_handler)
    
    # Setup logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(logs_dir / "purple_agent.log", encoding="utf-8")
        ]
    )
    
    # Priority: CLI arg > Environment variable > Default
    agent_url = args.card_url or os.environ.get("AGENT_CARD_URL") or f"http://{args.host}:{args.port}/"
    _agent_url = agent_url
    
    logger.info(f"💜 Purple Agent A2A server starting on http://{args.host}:{args.port}/")
    
    # Create Purple Agent components
    config = PurpleAgentConfig()
    config.green_agent_url = os.getenv("GREEN_AGENT_URL", "http://127.0.0.1:9009/")
    
    executor = PurpleAgentExecutor(config)
    agent_card = create_purple_agent_card(agent_url)
    
    # Create A2A request handler
    request_handler = DefaultRequestHandler(
        agent_executor=executor,
        task_store=InMemoryTaskStore(),
    )
    
    # Create A2A application
    a2a_server = A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=request_handler,
    )
    a2a_app = a2a_server.build()
    
    # Create main Starlette app with routes
    from starlette.routing import Mount
    
    main_app = Starlette(
        routes=[
            Route("/health", health_check, methods=["GET"]),
            Route("/.well-known/agent.json", well_known_agent_json, methods=["GET"]),
            Route("/.well-known/agent-card.json", well_known_agent_json, methods=["GET"]),
            Mount("/", app=a2a_app),
        ],
    )
    
    # Setup graceful shutdown
    shutdown_event = asyncio.Event()
    
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, shutting down...")
        shutdown_event.set()
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    # Run server
    uvicorn_config = uvicorn.Config(
        main_app,
        host=args.host,
        port=args.port,
        log_level=args.log_level.lower()
    )
    uvicorn_server = uvicorn.Server(uvicorn_config)
    
    try:
        server_task = asyncio.create_task(uvicorn_server.serve())
        await shutdown_event.wait()
        
        uvicorn_server.should_exit = True
        await server_task
        
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    asyncio.run(main())
