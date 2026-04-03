"""
Contract tests — validate agent card JSON schema and step response structure
against contracts/a2a-messages.md.
"""

import pytest
from a2a.types import AgentCapabilities, AgentCard, AgentSkill, DataPart, Message, Part, TextPart

from src.messenger import build_step_response


# ─── Agent Card Schema ─────────────────────────────────────────────────────────

class TestAgentCardSchema:
    """Agent card must conform exactly to the green agent's expected schema."""

    @pytest.fixture
    def agent_card(self) -> AgentCard:
        """Build the same AgentCard as server.py produces."""
        from src.server import _build_agent_card
        return _build_agent_card()

    def test_skill_id_is_osworld_task(self, agent_card: AgentCard):
        assert len(agent_card.skills) >= 1
        assert agent_card.skills[0].id == "osworld_task"

    def test_input_modes_include_text_file_data(self, agent_card: AgentCard):
        modes = agent_card.skills[0].input_modes
        assert "text" in modes
        assert "file" in modes
        assert "data" in modes

    def test_output_modes_include_text_data(self, agent_card: AgentCard):
        modes = agent_card.skills[0].output_modes
        assert "text" in modes
        assert "data" in modes

    def test_streaming_is_false(self, agent_card: AgentCard):
        assert agent_card.capabilities.streaming is False

    def test_push_notifications_is_false(self, agent_card: AgentCard):
        assert agent_card.capabilities.push_notifications is False

    def test_name_set(self, agent_card: AgentCard):
        assert agent_card.name == "OSWorld Purple Agent"

    def test_version_set(self, agent_card: AgentCard):
        assert agent_card.version is not None and agent_card.version != ""


# ─── Step Response Structure ──────────────────────────────────────────────────

class TestStepResponseStructure:
    """Step response must be exactly [TextPart(reasoning), DataPart(actions)]."""

    def test_two_parts_returned(self):
        msg = build_step_response("reasoning text", ["pyautogui.click(0, 0)"])
        assert isinstance(msg, Message)
        assert len(msg.parts) == 2

    def test_first_part_is_text_part(self):
        msg = build_step_response("my reasoning", ["DONE"])
        root = msg.parts[0].root
        assert isinstance(root, TextPart)

    def test_second_part_is_data_part(self):
        msg = build_step_response("my reasoning", ["DONE"])
        root = msg.parts[1].root
        assert isinstance(root, DataPart)

    def test_data_part_has_actions_key(self):
        msg = build_step_response("my reasoning", ["pyautogui.click(10, 20)"])
        data = msg.parts[1].root.data
        assert "actions" in data

    def test_actions_is_a_list(self):
        msg = build_step_response("reason", ["pyautogui.click(10, 20)", "DONE"])
        assert isinstance(msg.parts[1].root.data["actions"], list)

    def test_actions_are_strings(self):
        msg = build_step_response("reason", ["pyautogui.click(10, 20)", "DONE"])
        for action in msg.parts[1].root.data["actions"]:
            assert isinstance(action, str)

    def test_fail_response_structure(self):
        """Error/FAIL response must still have exactly two parts."""
        msg = build_step_response("LLM call failed: timeout", ["FAIL"])
        assert len(msg.parts) == 2
        assert msg.parts[1].root.data["actions"] == ["FAIL"]

    def test_reasoning_preserved_verbatim(self):
        reasoning = "I see the desktop. Column A has 5 values."
        msg = build_step_response(reasoning, ["DONE"])
        assert msg.parts[0].root.text == reasoning
