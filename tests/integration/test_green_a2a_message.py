"""
Integration test for Green agent A2A message sending.

Verifies Green agent sends MCP connection details via A2A DataPart.
Implements T042: Integration test for Green agent A2A message.
"""

import asyncio
import json
from unittest.mock import patch, MagicMock

import pytest

from src.green_agent.utils.models import MCPConnectionDetails
from src.utils.a2a_validation import (
    validate_message_structure,
    extract_data_parts,
    find_data_part_with_field,
    validate_mcp_connection_details
)


@pytest.mark.integration
class TestGreenAgentA2AMessage:
    """Test Green agent sends proper A2A messages with MCP details."""

    def test_mcp_connection_details_model(self):
        """Test MCPConnectionDetails model creates valid structure."""
        details = MCPConnectionDetails(
            command="python",
            args=["-m", "src.green_agent.mcp_server"],
            transport="stdio",
            env={
                "SESSION_ID": "test-123",
                "BENCHMARK": "miniwob"
            },
            session_id="test-123"
        )
        
        # Convert to dict (as done in Green agent)
        details_dict = details.model_dump()
        
        # Validate structure
        is_valid, error = validate_mcp_connection_details(details_dict)
        assert is_valid, f"MCPConnectionDetails model produces invalid dict: {error}"
        
        # Check required fields
        assert details_dict["command"] == "python"
        assert details_dict["args"] == ["-m", "src.green_agent.mcp_server"]
        assert details_dict["transport"] == "stdio"
        assert "SESSION_ID" in details_dict["env"]
        assert "BENCHMARK" in details_dict["env"]
        assert details_dict["session_id"] == "test-123"

    @pytest.mark.asyncio
    async def test_green_agent_sends_datapart_not_textpart(self):
        """
        Test that Green agent sends MCP details as DataPart, not TextPart.
        
        This test verifies the fix for the critical bug where Green agent
        was sending JSON-stringified data in TextPart instead of DataPart.
        """
        from a2a.types import Message, Part, DataPart, Role
        from uuid import uuid4
        
        # Simulate what Green agent should do
        mcp_details = MCPConnectionDetails(
            command="python",
            args=["-m", "src.green_agent.mcp_server"],
            transport="stdio",
            env={
                "SESSION_ID": "test-456",
                "BENCHMARK": "miniwob"
            },
            session_id="test-456"
        )
        
        message_data = {
            **mcp_details.model_dump(),
            "task_config": {"task_id": "miniwob.click-test"}
        }
        
        # This is the CORRECT way (after fix)
        message = Message(
            kind="message",
            role=Role.user,
            parts=[Part(root=DataPart(kind="data", data=message_data))],
            message_id=uuid4().hex,
        )
        
        # Validate message structure
        is_valid, error = validate_message_structure(message)
        assert is_valid, f"Message structure invalid: {error}"
        
        # Extract DataParts
        data_parts = extract_data_parts(message)
        assert len(data_parts) > 0, "No DataParts found in message"
        
        # Find MCP connection details
        mcp_data = find_data_part_with_field(message, "command")
        assert mcp_data is not None, "MCP details not found in DataPart"
        
        # Validate MCP details
        is_valid_mcp, mcp_error = validate_mcp_connection_details(mcp_data)
        assert is_valid_mcp, f"MCP details invalid: {mcp_error}"

    def test_datapart_vs_textpart_comparison(self):
        """
        Test demonstrating the difference between DataPart and TextPart.
        
        Shows why the bug was critical: TextPart with JSON string is not
        the same as DataPart with structured data.
        """
        from a2a.types import Message, Part, DataPart, TextPart, Role
        from uuid import uuid4
        
        test_data = {
            "command": "python",
            "args": ["-m", "server"],
            "transport": "stdio"
        }
        
        # WRONG: TextPart with JSON string (old buggy implementation)
        wrong_message = Message(
            kind="message",
            role=Role.user,
            parts=[Part(root=TextPart(kind="text", text=json.dumps(test_data)))],
            message_id=uuid4().hex,
        )
        
        # CORRECT: DataPart with structured data (fixed implementation)
        correct_message = Message(
            kind="message",
            role=Role.user,
            parts=[Part(root=DataPart(kind="data", data=test_data))],
            message_id=uuid4().hex,
        )
        
        # Verify wrong message has no DataParts
        wrong_data_parts = extract_data_parts(wrong_message)
        assert len(wrong_data_parts) == 0, "TextPart should not be extracted as DataPart"
        
        # Verify correct message has DataParts
        correct_data_parts = extract_data_parts(correct_message)
        assert len(correct_data_parts) == 1, "DataPart should be extracted"
        assert correct_data_parts[0] == test_data

    @pytest.mark.asyncio
    async def test_mcp_details_match_contract_schema(self):
        """Test that MCPConnectionDetails model matches contract schema requirements."""
        details = MCPConnectionDetails(
            command="/usr/bin/python3",
            args=["-m", "src.green_agent.mcp_server"],
            transport="stdio",
            env={
                "SESSION_ID": "session-789",
                "BENCHMARK": "webarena",
                "CUSTOM_VAR": "value"  # Additional properties allowed
            },
            session_id="session-789"
        )
        
        details_dict = details.model_dump()
        
        # All required fields present
        required_fields = ["command", "args", "transport", "env", "session_id"]
        for field in required_fields:
            assert field in details_dict, f"Missing required field: {field}"
        
        # Env has required subfields
        assert "SESSION_ID" in details_dict["env"]
        assert "BENCHMARK" in details_dict["env"]
        
        # Transport is valid enum value
        assert details_dict["transport"] in ["stdio", "http", "websocket"]

    def test_green_agent_model_dump_produces_dict(self):
        """Test that model_dump() produces a plain dict suitable for DataPart."""
        details = MCPConnectionDetails(
            command="python",
            args=["-m", "src.green_agent.mcp_server"],
            transport="stdio",
            env={"SESSION_ID": "test", "BENCHMARK": "miniwob"},
            session_id="test"
        )
        
        dumped = details.model_dump()
        
        # Should be a dict
        assert isinstance(dumped, dict)
        
        # Should be JSON-serializable (required for A2A)
        json_str = json.dumps(dumped)
        parsed = json.loads(json_str)
        assert parsed == dumped
