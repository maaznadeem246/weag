"""
T021 [P] [US2] Unit test for MCP connection message format

Tests that MCP connection details are properly formatted for purple agent communication.
"""

import json
import pytest
from uuid import uuid4

from src.green_agent.utils.models import MCPConnectionDetails


def test_mcp_connection_details_model():
    """Test MCPConnectionDetails dataclass structure."""
    session_id = uuid4().hex
    
    mcp_details = MCPConnectionDetails(
        command="python",
        args=["-m", "src.green_agent.mcp_server"],
        transport="stdio",
        env={"MINIWOB_URL": "file:///path/to/miniwob", "MCP_SESSION_ID": session_id}
    )
    
    assert mcp_details.command == "python"
    assert mcp_details.args == ["-m", "src.green_agent.mcp_server"]
    assert mcp_details.transport == "stdio"
    assert mcp_details.env["MINIWOB_URL"] == "file:///path/to/miniwob"
    assert mcp_details.env["MCP_SESSION_ID"] == session_id


def test_mcp_connection_details_serialization():
    """Test that MCPConnectionDetails serializes to proper JSON."""
    session_id = uuid4().hex
    
    mcp_details = MCPConnectionDetails(
        command="python",
        args=["-m", "src.green_agent.mcp_server"],
        transport="stdio",
        env={"WEBARENA_URL": "http://localhost:8000", "MCP_SESSION_ID": session_id}
    )
    
    # Convert to dict
    data = mcp_details.model_dump()
    
    # Verify structure
    assert "command" in data
    assert "args" in data
    assert "transport" in data
    assert "env" in data
    
    # Verify JSON serialization works
    json_str = json.dumps(data)
    parsed = json.loads(json_str)
    
    assert parsed["command"] == "python"
    assert parsed["transport"] == "stdio"
    assert parsed["env"]["MCP_SESSION_ID"] == session_id


def test_mcp_connection_message_with_task_config():
    """Test that MCP details combine with task config properly."""
    session_id = uuid4().hex
    
    mcp_details = MCPConnectionDetails(
        command="python",
        args=["-m", "src.green_agent.mcp_server"],
        transport="stdio",
        env={"MCP_SESSION_ID": session_id}
    )
    
    task_config = {
        "task_id": "miniwob.click-test",
        "benchmark_id": "miniwob",
        "max_steps": 10,
        "timeout": 30
    }
    
    # Simulate message data structure used in _send_mcp_details_to_purple
    message_data = {
        **mcp_details.model_dump(),
        "task_config": task_config
    }
    
    # Verify combined structure
    assert message_data["command"] == "python"
    assert message_data["transport"] == "stdio"
    assert message_data["env"]["MCP_SESSION_ID"] == session_id
    assert message_data["task_config"]["task_id"] == "miniwob.click-test"
    assert message_data["task_config"]["benchmark_id"] == "miniwob"
    
    # Verify JSON serialization
    json_str = json.dumps(message_data)
    parsed = json.loads(json_str)
    
    assert parsed["task_config"]["task_id"] == "miniwob.click-test"


def test_mcp_connection_details_with_empty_env():
    """Test that empty env dict is valid."""
    mcp_details = MCPConnectionDetails(
        command="python",
        args=["-m", "src.green_agent.mcp_server"],
        transport="stdio",
        env=None  # None is the default for optional env
    )
    
    data = mcp_details.model_dump()
    # env can be None (optional field)
    assert data["env"] is None or data["env"] == {}


def test_mcp_connection_details_with_multiple_env_vars():
    """Test multiple environment variables."""
    session_id = uuid4().hex
    mcp_details = MCPConnectionDetails(
        command="python",
        args=["-m", "src.green_agent.mcp_server"],
        transport="stdio",
        env={
            "MINIWOB_URL": "file:///path/to/miniwob",
            "WEBARENA_URL": "http://localhost:8000",
            "DEBUG": "1",
            "MCP_SESSION_ID": session_id
        }
    )
    
    data = mcp_details.model_dump()
    assert len(data["env"]) == 4
    assert data["env"]["MINIWOB_URL"] == "file:///path/to/miniwob"
    assert data["env"]["WEBARENA_URL"] == "http://localhost:8000"
    assert data["env"]["DEBUG"] == "1"
    assert data["env"]["MCP_SESSION_ID"] == session_id


@pytest.mark.parametrize("benchmark_id,expected_env_var", [
    ("miniwob", "MINIWOB_URL"),
    ("webarena", "WEBARENA_URL"),
    ("visualwebarena", "VISUALWEBARENA_URL"),
    ("workarena", "WORKARENA_URL"),
])
def test_mcp_connection_details_benchmark_env_vars(benchmark_id, expected_env_var):
    """Test that different benchmarks can have appropriate env vars."""
    session_id = uuid4().hex
    env = {
        expected_env_var: f"http://localhost:8000/{benchmark_id}",
        "MCP_SESSION_ID": session_id
    }
    
    mcp_details = MCPConnectionDetails(
        command="python",
        args=["-m", "src.green_agent.mcp_server"],
        transport="stdio",
        env=env
    )
    
    data = mcp_details.model_dump()
    assert expected_env_var in data["env"]
    assert data["env"]["MCP_SESSION_ID"] == session_id
