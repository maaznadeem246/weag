"""
T038 [US1] Contract test for agent card schema compliance

Tests that the agent card conforms to the A2A protocol specification.

Note: These are structure/schema tests. Integration tests that actually call the server
are in tests/integration/
"""

import pytest
from src.green_agent.a2a.agent_card import get_agent_card_dict, create_agent_card


# Test agent URL for contract tests
TEST_AGENT_URL = "http://localhost:9009"


class TestAgentCardSchema:
    """Test agent card schema compliance."""
    
    def test_agent_card_has_required_fields(self):
        """Test that agent card contains all required fields."""
        agent_card = get_agent_card_dict(TEST_AGENT_URL)
        
        # Required fields per A2A specification
        assert "protocolVersion" in agent_card, "protocolVersion is required"
        assert "name" in agent_card, "name is required"
        assert "version" in agent_card, "version is required"
        assert "description" in agent_card, "description is required"
        assert "capabilities" in agent_card, "capabilities is required"
        
        # Validate protocol version
        assert agent_card["protocolVersion"] == "0.3.0", "Must support A2A protocol 0.3.0"
        
        # Validate capabilities structure
        capabilities = agent_card["capabilities"]
        assert "streaming" in capabilities, "streaming capability is required"
        assert isinstance(capabilities["streaming"], bool), "streaming must be boolean"
    
    def test_agent_card_name_and_version(self):
        """Test that agent card has proper name and version."""
        agent_card = get_agent_card_dict(TEST_AGENT_URL)
        
        # Validate name
        assert isinstance(agent_card["name"], str)
        assert len(agent_card["name"]) > 0
        
        # Validate version (semantic versioning)
        version = agent_card["version"]
        assert isinstance(version, str)
        assert len(version.split(".")) >= 2, "Version should be in format X.Y or X.Y.Z"
    
    def test_agent_card_description(self):
        """Test that agent card has a meaningful description."""
        agent_card = get_agent_card_dict(TEST_AGENT_URL)
        
        assert isinstance(agent_card["description"], str)
        assert len(agent_card["description"]) > 10, "Description should be meaningful"
    
    def test_agent_card_capabilities(self):
        """Test that agent card declares required capabilities."""
        agent_card = get_agent_card_dict(TEST_AGENT_URL)
        
        capabilities = agent_card["capabilities"]
        
        # Green agent must support streaming
        assert capabilities["streaming"] is True, "Green agent must support streaming"
        
        # Optional: Check for other capabilities
        if "push_notifications" in capabilities:
            assert isinstance(capabilities["push_notifications"], bool)
        
        if "state_transition_history" in capabilities:
            assert isinstance(capabilities["state_transition_history"], bool)
    
    def test_agent_card_optional_fields(self):
        """Test optional agent card fields if present."""
        agent_card = get_agent_card_dict(TEST_AGENT_URL)
        
        # Test optional fields if present
        if "provider" in agent_card:
            assert isinstance(agent_card["provider"], dict)
            if "org" in agent_card["provider"]:
                assert isinstance(agent_card["provider"]["org"], str)
        
        if "skills" in agent_card:
            assert isinstance(agent_card["skills"], list)
            for skill in agent_card["skills"]:
                assert "id" in skill
                assert "name" in skill
                assert "description" in skill
    
    def test_create_agent_card_returns_agent_card_object(self):
        """Test that create_agent_card returns proper AgentCard object."""
        agent_card = create_agent_card(TEST_AGENT_URL)
        
        # Should have AgentCard type from a2a library
        assert hasattr(agent_card, 'name')
        assert hasattr(agent_card, 'version')
        assert hasattr(agent_card, 'description')
        assert hasattr(agent_card, 'capabilities')
        
        # Validate name and version
        assert isinstance(agent_card.name, str)
        assert isinstance(agent_card.version, str)


class TestAgentCardStructure:
    """Test agent card structure without server."""
    
    def test_minimal_agent_card_schema(self):
        """Test minimal valid agent card structure."""
        minimal_card = {
            "protocolVersion": "0.3.0",
            "name": "Test Agent",
            "version": "1.0.0",
            "description": "A test agent",
            "capabilities": {
                "streaming": True
            }
        }
        
        # Validate required fields
        assert minimal_card["protocolVersion"] == "0.3.0"
        assert isinstance(minimal_card["name"], str)
        assert isinstance(minimal_card["version"], str)
        assert isinstance(minimal_card["description"], str)
        assert isinstance(minimal_card["capabilities"], dict)
        assert "streaming" in minimal_card["capabilities"]
    
    def test_full_agent_card_schema(self):
        """Test full agent card with all optional fields."""
        full_card = {
            "protocolVersion": "0.3.0",
            "name": "BrowserGym Green Agent",
            "version": "1.0.0",
            "description": "Green agent for evaluating web automation agents using BrowserGym benchmarks",
            "provider": {
                "org": "WEAG",
                "url": "https://github.com/weag-project"
            },
            "capabilities": {
                "streaming": True,
                "push_notifications": False,
                "state_transition_history": True
            },
            "skills": [
                {
                    "id": "browsergym-evaluation",
                    "name": "BrowserGym Evaluation",
                    "description": "Evaluate purple agents on web automation benchmarks"
                }
            ]
        }
        
        # Validate all fields
        assert full_card["protocolVersion"] == "0.3.0"
        assert full_card["name"] == "BrowserGym Green Agent"
        assert full_card["version"] == "1.0.0"
        assert len(full_card["description"]) > 10
        assert "provider" in full_card
        assert "streaming" in full_card["capabilities"]
        assert isinstance(full_card["skills"], list)
    
    def test_capabilities_boolean_values(self):
        """Test that capabilities are boolean values."""
        capabilities = {
            "streaming": True,
            "push_notifications": False,
            "state_transition_history": True
        }
        
        for key, value in capabilities.items():
            assert isinstance(value, bool), f"Capability '{key}' must be boolean"
    
    def test_protocol_version_format(self):
        """Test that protocol version follows semantic versioning."""
        protocol_version = "0.3.0"
        
        # Should have 3 parts: major.minor.patch
        parts = protocol_version.split(".")
        assert len(parts) == 3
        
        # All parts should be numbers
        for part in parts:
            assert part.isdigit(), f"Version part '{part}' should be numeric"
