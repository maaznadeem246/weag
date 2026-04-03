"""
Unit tests for messenger.py — parse_step_message() and build_step_response().
All tests are pure Python, no network calls, no LLM calls.
"""

import base64

import pytest
from a2a.types import DataPart, FilePart, FileWithBytes, Message, Part, TextPart

from src.messenger import StepMessage, StepResponse, build_step_response, parse_step_message

def _make_message(*parts: Part) -> Message:
    """Wrap parts in a minimal A2A Message."""
    return Message(role="user", parts=list(parts), messageId="test-msg")


def _text(text: str) -> Part:
    return Part(root=TextPart(text=text))


def _data(data: dict) -> Part:
    return Part(root=DataPart(data=data))


def _file(b64: str, mime: str = "image/png", name: str = "screenshot.png") -> Part:
    return Part(root=FilePart(file=FileWithBytes(bytes=b64, mime_type=mime, name=name)))


_ENV_CONFIG = {"action_space": "pyautogui", "observation_type": "screenshot"}
_SCREENSHOT_B64 = base64.b64encode(b"fake-png-bytes").decode()


# ─── parse_step_message ────────────────────────────────────────────────────────

class TestParseStepMessage:
    def test_valid_5_part_message(self):
        msg = _make_message(
            _text("Click the OK button"),
            _data({"env_config": _ENV_CONFIG}),
            _file(_SCREENSHOT_B64),
            _data({"accessibility_tree": "Name\tRole\nOK\tbutton"}),
            _data({"terminal": "$ ls"}),
        )
        step = parse_step_message(msg)
        assert step.instruction == "Click the OK button"
        assert step.env_config == _ENV_CONFIG
        assert step.screenshot_b64 == _SCREENSHOT_B64
        assert "OK" in step.accessibility_tree
        assert step.terminal == "$ ls"

    def test_text_only_message(self):
        """Screenshot and optional parts absent → None fields."""
        msg = _make_message(
            _text("Just text"),
            _data({"env_config": _ENV_CONFIG}),
        )
        step = parse_step_message(msg)
        assert step.instruction == "Just text"
        assert step.screenshot_b64 is None
        assert step.accessibility_tree is None
        assert step.terminal is None

    def test_missing_screenshot_is_none(self):
        msg = _make_message(_text("Go"), _data({"env_config": _ENV_CONFIG}))
        step = parse_step_message(msg)
        assert step.screenshot_b64 is None

    def test_empty_instruction_allowed(self):
        msg = _make_message(
            _text(""),
            _data({"env_config": _ENV_CONFIG}),
        )
        step = parse_step_message(msg)
        assert step.instruction == ""

    def test_missing_instruction_raises(self):
        """No TextPart → ValueError."""
        msg = _make_message(_data({"env_config": _ENV_CONFIG}))
        with pytest.raises(ValueError, match="instruction"):
            parse_step_message(msg)

    def test_env_config_absent_defaults_to_empty_dict(self):
        msg = _make_message(_text("Do something"))
        step = parse_step_message(msg)
        assert step.env_config == {}

    def test_non_png_file_ignored(self):
        """A FilePart with mime_type != image/png should not populate screenshot_b64."""
        msg = _make_message(
            _text("Go"),
            _data({"env_config": _ENV_CONFIG}),
            _file("abc", mime="text/plain", name="log.txt"),
        )
        step = parse_step_message(msg)
        assert step.screenshot_b64 is None

    def test_multiple_data_parts_each_key_extracted_once(self):
        msg = _make_message(
            _text("Do"),
            _data({"env_config": _ENV_CONFIG}),
            _data({"accessibility_tree": "tree1"}),
            _data({"accessibility_tree": "tree2"}),  # second should be ignored
        )
        step = parse_step_message(msg)
        assert step.accessibility_tree == "tree1"


# ─── build_step_response ──────────────────────────────────────────────────────

class TestBuildStepResponse:
    def test_valid_actions(self):
        msg = build_step_response("I will click OK", ["pyautogui.click(100, 200)"])
        assert isinstance(msg, Message)
        assert len(msg.parts) == 2
        text_part = msg.parts[0].root
        data_part = msg.parts[1].root
        assert isinstance(text_part, TextPart)
        assert text_part.text == "I will click OK"
        assert isinstance(data_part, DataPart)
        assert data_part.data["actions"] == ["pyautogui.click(100, 200)"]

    def test_empty_actions_substituted_with_fail(self):
        msg = build_step_response("No actions", [])
        data_part = msg.parts[1].root
        assert data_part.data["actions"] == ["FAIL"]

    def test_multiple_actions_preserved(self):
        actions = ["pyautogui.click(10, 20)", "import time; time.sleep(0.5)", "DONE"]
        msg = build_step_response("Three steps", actions)
        assert msg.parts[1].root.data["actions"] == actions

    def test_fail_action_passthrough(self):
        msg = build_step_response("LLM error", ["FAIL"])
        assert msg.parts[1].root.data["actions"] == ["FAIL"]
