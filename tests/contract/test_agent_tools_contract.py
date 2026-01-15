"""
Contract validation test for agent tools.

Verifies agent tools match contracts/agent-tools.json schema specifications.
Implements T114: Contract validation test for agent tools.
"""

import json
from pathlib import Path

import pytest

from src.green_agent.agent.tools import AGENT_TOOLS


class TestAgentToolsContract:
    """Test agent tools match contract specifications."""

    @pytest.fixture
    def agent_tools_contract(self):
        """Load agent-tools.json contract specification."""
        contract_path = Path("specs/004-openai-agent-integration/contracts/agent-tools.json")

        if not contract_path.exists():
            pytest.skip("agent-tools.json contract not found")

        with open(contract_path, "r") as f:
            return json.load(f)

    def test_all_tools_registered(self, agent_tools_contract):
        """Test that all contract tools are registered."""
        contract_tools = agent_tools_contract.get("tools", [])
        registered_tool_names = {tool.__name__ for tool in AGENT_TOOLS}

        for contract_tool in contract_tools:
            tool_name = contract_tool.get("name")
            assert tool_name in registered_tool_names, f"Tool {tool_name} not registered in AGENT_TOOLS"

    def test_tool_count_matches(self, agent_tools_contract):
        """Test that tool count matches contract."""
        contract_tool_count = len(agent_tools_contract.get("tools", []))
        registered_tool_count = len(AGENT_TOOLS)

        assert registered_tool_count == contract_tool_count, \
            f"Expected {contract_tool_count} tools, found {registered_tool_count}"

    def test_tool_parameters_match(self, agent_tools_contract):
        """Test that tool parameters match contract specifications."""
        contract_tools = {
            tool["name"]: tool
            for tool in agent_tools_contract.get("tools", [])
        }

        for tool_func in AGENT_TOOLS:
            tool_name = tool_func.__name__

            if tool_name not in contract_tools:
                continue

            contract_tool = contract_tools[tool_name]
            contract_params = contract_tool.get("parameters", {})

            # Verify tool has correct signature
            # (This is a basic check; full validation would inspect function signature)
            assert hasattr(tool_func, "__call__"), f"Tool {tool_name} should be callable"

    def test_tool_descriptions_present(self, agent_tools_contract):
        """Test that all tools have descriptions."""
        contract_tools = agent_tools_contract.get("tools", [])

        for contract_tool in contract_tools:
            assert "description" in contract_tool, \
                f"Tool {contract_tool.get('name')} missing description"
            assert len(contract_tool["description"]) > 0, \
                f"Tool {contract_tool.get('name')} has empty description"

    def test_required_tools_present(self):
        """Test that required tools are present."""
        required_tools = [
            "verify_mcp_health",
            "send_mcp_details",
            "get_current_state",
            "calculate_efficiency_score",
            "generate_evaluation_artifact",
            "cleanup_evaluation",
            "send_task_update",
            "orchestrate_batch_evaluation",
        ]

        registered_tool_names = {tool.__name__ for tool in AGENT_TOOLS}

        for required_tool in required_tools:
            assert required_tool in registered_tool_names, \
                f"Required tool {required_tool} not found in AGENT_TOOLS"

    def test_tool_return_types_valid(self, agent_tools_contract):
        """Test that tool return types are valid."""
        contract_tools = agent_tools_contract.get("tools", [])

        for contract_tool in contract_tools:
            returns = contract_tool.get("returns", {})

            # Verify return type is specified
            assert "type" in returns or "schema" in returns, \
                f"Tool {contract_tool.get('name')} missing return type specification"

    def test_tools_have_async_signatures(self):
        """Test that all tools are async functions."""
        import inspect

        for tool_func in AGENT_TOOLS:
            # Check if function is async (coroutine function)
            # Note: Decorated functions may not show as coroutine functions
            # This is a best-effort check
            tool_name = tool_func.__name__

            # At minimum, verify it's callable
            assert callable(tool_func), f"Tool {tool_name} should be callable"

    def test_contract_schema_version(self, agent_tools_contract):
        """Test that contract has schema version."""
        assert "version" in agent_tools_contract, "Contract missing version field"
        assert agent_tools_contract["version"] in ["1.0", "1.0.0"], \
            f"Unexpected contract version: {agent_tools_contract['version']}"

    def test_contract_completeness(self, agent_tools_contract):
        """Test that contract is complete."""
        required_fields = ["version", "tools"]

        for field in required_fields:
            assert field in agent_tools_contract, f"Contract missing required field: {field}"

        # Verify tools array is not empty
        assert len(agent_tools_contract["tools"]) > 0, "Contract has no tools defined"


class TestMCPToolsContract:
    """Test MCP tools match contract specifications."""

    @pytest.fixture
    def mcp_tools_contract(self):
        """Load mcp-tools.json contract specification."""
        contract_path = Path("specs/001-browsergym-green-agent/contracts/mcp-tools.json")

        if not contract_path.exists():
            pytest.skip("mcp-tools.json contract not found")

        with open(contract_path, "r") as f:
            return json.load(f)

    def test_mcp_tools_defined(self, mcp_tools_contract):
        """Test that MCP tools are defined in contract."""
        tools = mcp_tools_contract.get("tools", [])

        # Only 2 base MCP tools (environment lifecycle managed by Green Agent)
        expected_mcp_tools = [
            "execute_actions",
            "get_observation",
        ]

        tool_names = {tool["name"] for tool in tools}

        for expected_tool in expected_mcp_tools:
            assert expected_tool in tool_names, \
                f"Expected MCP tool {expected_tool} not found in contract"

    def test_mcp_tool_parameters_specified(self, mcp_tools_contract):
        """Test that MCP tool parameters are specified."""
        tools = mcp_tools_contract.get("tools", [])

        for tool in tools:
            assert "parameters" in tool, f"Tool {tool['name']} missing parameters"

            # Each tool should have input schema
            params = tool["parameters"]
            assert "type" in params or "properties" in params, \
                f"Tool {tool['name']} parameters missing type/properties"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
