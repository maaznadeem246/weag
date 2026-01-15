"""
Standalone MCP Server Runner for BrowserGym Green Agent.

Run this to test the MCP server independently without the full Green Agent.
Usage:
    python scripts/run_mcp_server_standalone.py
    
Then test with MCP Inspector:
    npx -y @modelcontextprotocol/inspector
    Connect to: http://localhost:8001
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Import after path setup
from src.green_agent.mcp.server import mcp
from src.utils.logging import get_logger

logger = get_logger(__name__)


def main():
    """Run MCP server standalone on port 8001."""
    
    logger.info("=" * 60)
    logger.info("🚀 Starting MCP Server in Standalone Mode")
    logger.info("=" * 60)
    logger.info("")
    logger.info("Server will run at: http://localhost:8001")
    logger.info("Available endpoints:")
    logger.info("  - POST http://localhost:8001/mcp/messages")
    logger.info("  - GET  http://localhost:8001/mcp/sse")
    logger.info("")
    logger.info("To test with MCP Inspector:")
    logger.info("  1. Run: npx -y @modelcontextprotocol/inspector")
    logger.info("  2. Open: http://localhost:5173 (Inspector UI)")
    logger.info("  3. Connect to: http://localhost:8001")
    logger.info("")
    logger.info("Tools available:")
    logger.info("  - initialize_environment")
    logger.info("  - execute_actions")
    logger.info("  - get_observation")
    logger.info("  - cleanup_environment")
    logger.info("")
    logger.info("Press Ctrl+C to stop the server")
    logger.info("=" * 60)
    logger.info("")
    
    # Explicitly configure FastMCP streamable HTTP path and mount under /mcp
    # This ensures endpoints are available at /mcp and /mcp/sse as clients expect.
    from starlette.applications import Starlette
    from starlette.routing import Mount
    import uvicorn

    # Place endpoints at the root of the mount point so mounting at '/mcp'
    # will expose '/mcp' and '/mcp/sse'. This avoids redirect/404 issues.
    try:
        mcp.settings.streamable_http_path = "/"
    except Exception:
        # If settings object differs across SDK versions, ignore and continue
        pass

    # Ensure MCP session manager is started during ASGI lifespan so
    # streamable-http handlers have an initialized task group.
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def lifespan(app):
        # Initialize FastMCP's internal session manager/task group
        async with mcp.session_manager.run():
            yield

    app = Starlette(
        routes=[
            Mount("/mcp", app=mcp.streamable_http_app()),
        ],
        lifespan=lifespan,
    )

    config = uvicorn.Config(
        app=app,
        host="0.0.0.0",
        port=8001,
        log_level="info",
    )
    server = uvicorn.Server(config)
    server.run()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("\n✓ MCP Server stopped")
        sys.exit(0)
