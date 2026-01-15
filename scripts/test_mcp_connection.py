"""
Simple MCP client to test connection to standalone server.

Usage:
    1. Start server: python scripts/run_mcp_server_standalone.py
    2. Run this test: python scripts/test_mcp_connection.py
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from mcp.client.streamable_http import streamablehttp_client
from src.green_agent.utils.logging import get_logger

logger = get_logger(__name__)


async def test_connection():
    """Test connection to MCP server."""
    
    server_url = "http://localhost:8001"
    
    logger.info("=" * 60)
    logger.info("🔍 Testing MCP Server Connection")
    logger.info("=" * 60)
    logger.info(f"Server URL: {server_url}")
    logger.info("")
    
    try:
        logger.info("Step 1: Connecting to MCP server...")
        async with streamablehttp_client(server_url) as (read, write, _):
            logger.info("✓ Connection established successfully!")
            logger.info("")
            
            logger.info("Step 2: Initializing MCP session...")
            # Send initialize request
            init_request = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {
                        "name": "test-client",
                        "version": "1.0.0"
                    }
                }
            }
            
            await write.send(init_request)
            response = await read.recv()
            logger.info(f"✓ Initialize response: {response}")
            logger.info("")
            
            logger.info("Step 3: Listing available tools...")
            # List tools
            list_tools_request = {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list",
                "params": {}
            }
            
            await write.send(list_tools_request)
            response = await read.recv()
            
            if "result" in response and "tools" in response["result"]:
                tools = response["result"]["tools"]
                logger.info(f"✓ Found {len(tools)} tools:")
                for tool in tools:
                    logger.info(f"  - {tool['name']}: {tool.get('description', 'No description')}")
            else:
                logger.warning(f"Unexpected response: {response}")
            
            logger.info("")
            logger.info("=" * 60)
            logger.info("✓ All tests passed! MCP server is working correctly.")
            logger.info("=" * 60)
            
    except ConnectionError as e:
        logger.error("=" * 60)
        logger.error("❌ Connection failed!")
        logger.error("=" * 60)
        logger.error(f"Error: {e}")
        logger.error("")
        logger.error("Make sure the MCP server is running:")
        logger.error("  python scripts/run_mcp_server_standalone.py")
        logger.error("=" * 60)
        sys.exit(1)
        
    except Exception as e:
        logger.error("=" * 60)
        logger.error("❌ Test failed!")
        logger.error("=" * 60)
        logger.error(f"Error: {e}", exc_info=True)
        logger.error("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(test_connection())
