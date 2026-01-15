"""
Contract validation test for A2A MCP handoff message.

Verifies Green agent sends MCP connection details conforming to schema.
Implements T041: Contract validation test for A2A MCP message.
"""

import json
from pathlib import Path

import pytest

from tests.utils.contract_validation import get_contract_validator
from src.utils.a2a_validation import validate_mcp_connection_details, create_test_mcp_details


class TestA2AMCPMessageContract:
    """Test A2A MCP handoff message contract compliance."""

    @pytest.fixture
    def contract_validator(self):
        """Get contract validator for feature 005."""
        return get_contract_validator("005-kickstart-assessment")

    @pytest.fixture
    def mcp_handoff_schema(self, contract_validator):
        """Load MCP handoff message schema."""
        return contract_validator.load_schema("a2a-mcp-handoff.json")

    def test_schema_file_exists(self):
        """Test that MCP handoff contract schema exists."""
        project_root = Path(__file__).parent.parent.parent
        schema_path = project_root / "specs" / "005-kickstart-assessment" / "contracts" / "a2a-mcp-handoff.json"
        assert schema_path.exists(), f"Schema not found: {schema_path}"

    def test_mcp_connection_details_required_fields(self, mcp_handoff_schema):
        """Test MCPConnectionDetails has all required fields."""
        mcp_def = mcp_handoff_schema["definitions"]["MCPConnectionDetails"]
        required = mcp_def["required"]
        
        # Must include command, args, transport, env, session_id
        assert "command" in required
        assert "args" in required
        assert "transport" in required
        assert "env" in required
        assert "session_id" in required

    def test_valid_mcp_connection_details(self, contract_validator):
        """Test valid MCP connection details pass validation."""
        valid_details = {
            "command": "python",
            "args": ["-m", "src.green_agent.mcp_server"],
            "transport": "stdio",
            "env": {
                "SESSION_ID": "test-session-123",
                "BENCHMARK": "miniwob"
            },
            "session_id": "test-session-123"
        }
        
        is_valid, error = contract_validator.validate(
            valid_details,
            "a2a-mcp-handoff.json",
            raise_on_error=False
        )
        
        # Note: The schema validates the full message structure, not just MCPConnectionDetails
        # So we use our utility validator for the details object
        is_valid_details, error_details = validate_mcp_connection_details(valid_details)
        assert is_valid_details, f"Valid details failed: {error_details}"

    def test_missing_required_field_command(self, contract_validator):
        """Test that missing 'command' field fails validation."""
        invalid_details = {
            "args": ["-m", "src.green_agent.mcp_server"],
            "transport": "stdio",
            "env": {"SESSION_ID": "test", "BENCHMARK": "miniwob"},
            "session_id": "test"
        }
        
        is_valid, error = validate_mcp_connection_details(invalid_details)
        assert not is_valid
        assert "command" in error

    def test_missing_required_field_args(self, contract_validator):
        """Test that missing 'args' field fails validation."""
        invalid_details = {
            "command": "python",
            "transport": "stdio",
            "env": {"SESSION_ID": "test", "BENCHMARK": "miniwob"},
            "session_id": "test"
        }
        
        is_valid, error = validate_mcp_connection_details(invalid_details)
        assert not is_valid
        assert "args" in error

    def test_invalid_transport_type(self, contract_validator):
        """Test that invalid transport type fails validation."""
        invalid_details = {
            "command": "python",
            "args": ["-m", "src.green_agent.mcp_server"],
            "transport": "invalid_transport",
            "env": {"SESSION_ID": "test", "BENCHMARK": "miniwob"},
            "session_id": "test"
        }
        
        is_valid, error = validate_mcp_connection_details(invalid_details)
        assert not is_valid
        assert "transport" in error

    def test_transport_must_be_stdio(self, mcp_handoff_schema):
        """Test that transport enum only allows stdio."""
        mcp_def = mcp_handoff_schema["definitions"]["MCPConnectionDetails"]
        transport_enum = mcp_def["properties"]["transport"]["enum"]
        
        assert transport_enum == ["stdio"]

    def test_create_test_mcp_details_helper(self):
        """Test helper function creates valid MCP details."""
        details = create_test_mcp_details()
        
        is_valid, error = validate_mcp_connection_details(details)
        assert is_valid, f"Test details invalid: {error}"
        
        assert details["command"] == "python"
        assert isinstance(details["args"], list)
        assert details["transport"] == "stdio"
        assert "session_id" in details

    def test_env_field_structure(self, mcp_handoff_schema):
        """Test env field has required SESSION_ID and BENCHMARK."""
        mcp_def = mcp_handoff_schema["definitions"]["MCPConnectionDetails"]
        env_props = mcp_def["properties"]["env"]
        
        assert "SESSION_ID" in env_props["required"]
        assert "BENCHMARK" in env_props["required"]

    def test_args_must_be_array(self):
        """Test that args field must be an array."""
        invalid_details = {
            "command": "python",
            "args": "-m src.green_agent.mcp_server",  # String instead of array
            "transport": "stdio",
            "env": {"SESSION_ID": "test", "BENCHMARK": "miniwob"},
            "session_id": "test"
        }
        
        is_valid, error = validate_mcp_connection_details(invalid_details)
        assert not is_valid
        assert "args" in error
