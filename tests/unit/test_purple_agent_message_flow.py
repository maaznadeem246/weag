"""
Test message-based MCP connection flow with proxy tools.

Verifies that connect_to_mcp can establish dynamic connections using A2A details.
"""

import pytest
from src.purple_agent.agent.context import TestPurpleAgentContext
from src.purple_agent.tools.mcp_proxy_tools import connect_to_mcp
from unittest.mock import Mock, AsyncMock, patch


@pytest.mark.asyncio
async def test_connect_with_mcp_details_in_context():
    """Test that connect_to_mcp uses MCP details from context."""
    
    # Create context with MCP connection details
    context = TestPurpleAgentContext(
        task_id="miniwob.click-test",
        benchmark="miniwob",
        green_agent_url="http://localhost:9009",
        mcp_connection_details={
            "url": "http://localhost:8001/mcp",
            "transport": "http",
        }
    )
    
    # Create mock RunContextWrapper
    mock_ctx = Mock()
    mock_ctx.context = context
    
    # Call connect_to_mcp_server - it should extract MCP details from messages
    # Note: This will fail at MCP connection stage (no actual MCP server running)
    # but should successfully extract details first
    result = await connect_to_mcp_server(mock_ctx)
    
    # Should have extracted and populated mcp_connection_details
    assert context.mcp_connection_details is not None
    assert context.mcp_connection_details["command"] == "python"
    
    # Mock the MCP client to avoid actual connection
    mock_ctx = Mock()
    mock_ctx.context = context
    
    # Mock streamablehttp_client to simulate successful connection
    with patch('src.purple_agent.tools.mcp_proxy_tools.streamablehttp_client') as mock_http:
        mock_session = AsyncMock()
        mock_session.initialize = AsyncMock()
        mock_tools_result = Mock()
        mock_tools_result.tools = [
            Mock(name="initialize_environment"),
            Mock(name="get_observation"),
            Mock(name="execute_actions"),
            Mock(name="cleanup_environment"),
        ]
        mock_session.list_tools = AsyncMock(return_value=mock_tools_result)
        
        # Setup context manager
        async def mock_http_cm(*args, **kwargs):
            class CM:
                async def __aenter__(self):
                    return (Mock(), Mock(), None)
                async def __aexit__(self, *args):
                    pass
            return CM()
        
        mock_http.side_effect = mock_http_cm
        
        with patch('src.purple_agent.tools.mcp_proxy_tools.ClientSession', return_value=mock_session):
            result = await connect_to_mcp(mock_ctx, "browsergym")
    
    assert result["status"] == "connected"
    assert result["server"] == "browsergym"
    assert len(result["tools"]) == 4


@pytest.mark.asyncio
async def test_connect_fails_without_details():
    """Test that connect_to_mcp fails gracefully without MCP details."""
    
    context = TestPurpleAgentContext(
        task_id="miniwob.click-test",
        benchmark="miniwob",
        green_agent_url="http://localhost:9009",
        mcp_connection_details=None,  # No details
    )
    
    mock_ctx = Mock()
    mock_ctx.context = context
    
    result = await connect_to_mcp(mock_ctx, "browsergym")
    
    assert "error" in result
    assert "No MCP connection details" in result["error"]


@pytest.mark.asyncio
async def test_already_connected():
    """Test that connect_to_mcp returns early if already connected."""
    
    mock_session = Mock()
    
    context = TestPurpleAgentContext(
        task_id="miniwob.click-test",
        benchmark="miniwob",
        green_agent_url="http://localhost:9009",
        mcp_connection_details={"url": "http://localhost:8001/mcp"},
        mcp_connected=True
    )
    context.mcp_registry["browsergym"] = mock_session
    
    mock_ctx = Mock()
    mock_ctx.context = context
    
    # Mock list_tools to avoid actual call
    mock_tools_result = Mock()
    mock_tools_result.tools = []
    mock_session.list_tools = AsyncMock(return_value=mock_tools_result)
    
    result = await connect_to_mcp(mock_ctx, "browsergym")
    
    assert result["status"] == "already_connected"
    assert result["server"] == "browsergym"


if __name__ == "__main__":
    import asyncio
    
    print("Testing MCP proxy tool connections...")
    asyncio.run(test_connect_with_mcp_details_in_context())
    print("✓ Test 1 passed: Connection with MCP details")
    
    asyncio.run(test_connect_fails_without_details())
    print("✓ Test 2 passed: Graceful failure without details")
    
    asyncio.run(test_already_connected())
    print("✓ Test 3 passed: Already connected check")
    
    print("\n✅ All tests passed!")
