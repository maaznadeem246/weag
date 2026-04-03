"""
A2A Message Parsing and Building for OSWorld Purple Agent.

Provides two public functions:
- parse_step_message(message) -> StepMessage   extract typed parts from incoming A2A Message
- build_step_response(reasoning, actions) -> list  build outgoing A2A parts list

Incoming message structure (from green agent, per contracts/a2a-messages.md):
  Part 0: TextPart        — task instruction (always present)
  Part 1: DataPart        — env_config: {action_space, observation_type}
  Part 2: FilePart        — screenshot.png base64 PNG (present when observation_type includes screenshot)
  Part 3: DataPart        — accessibility_tree string (optional)
  Part 4: DataPart        — terminal output string (optional)

Outgoing message structure (to green agent):
  Part 0: TextPart        — LLM reasoning chain-of-thought
  Part 1: DataPart        — {"actions": ["pyautogui.click(100, 200)", ...]}
"""

from dataclasses import dataclass, field
from typing import Optional

from a2a.types import DataPart, FilePart, Message, Part, Role, TextPart


@dataclass
class StepMessage:
    """Typed representation of one evaluation step received from the green agent."""

    instruction: str
    """Full task instruction (from TextPart)."""

    env_config: dict
    """Environment config dict, e.g. {"action_space": "pyautogui", "observation_type": "screenshot"}."""

    screenshot_b64: Optional[str] = None
    """Base64-encoded PNG screenshot, or None if absent."""

    accessibility_tree: Optional[str] = None
    """Desktop accessibility tree text, or None if absent."""

    terminal: Optional[str] = None
    """Terminal output text, or None if absent."""


@dataclass
class StepResponse:
    """Typed representation of one evaluation step response to the green agent."""

    reasoning: str
    """LLM chain-of-thought reasoning text."""

    actions: list[str] = field(default_factory=list)
    """Ordered list of pyautogui expressions or special values (WAIT/DONE/FAIL)."""


def _make_message_id() -> str:
    import uuid
    return str(uuid.uuid4())


def parse_step_message(message: Message) -> StepMessage:
    """
    Extract typed fields from an incoming A2A Message.

    Iterates parts in order; the first TextPart is the instruction, the first
    DataPart with key 'env_config' is the environment config, the first FilePart
    is the screenshot, etc.  Extra or missing optional parts are handled gracefully.

    Args:
        message: Raw A2A Message from the green agent.

    Returns:
        StepMessage with all available fields populated.

    Raises:
        ValueError: If the instruction TextPart is missing.
    """
    instruction: Optional[str] = None
    env_config: dict = {}
    screenshot_b64: Optional[str] = None
    accessibility_tree: Optional[str] = None
    terminal: Optional[str] = None

    for part in message.parts:
        root = part.root if hasattr(part, "root") else part

        if isinstance(root, TextPart) and instruction is None:
            instruction = root.text or ""

        elif isinstance(root, FilePart):
            file_obj = root.file
            if (
                screenshot_b64 is None
                and file_obj is not None
                and getattr(file_obj, "mime_type", None) == "image/png"
            ):
                screenshot_b64 = getattr(file_obj, "bytes", None)

        elif isinstance(root, DataPart):
            data = root.data or {}
            if "env_config" in data and not env_config:
                env_config = data["env_config"]
            elif "accessibility_tree" in data and accessibility_tree is None:
                accessibility_tree = data["accessibility_tree"]
            elif "terminal" in data and terminal is None:
                terminal = data["terminal"]

    if instruction is None:
        raise ValueError("Incoming A2A message is missing the instruction TextPart.")

    return StepMessage(
        instruction=instruction,
        env_config=env_config,
        screenshot_b64=screenshot_b64,
        accessibility_tree=accessibility_tree,
        terminal=terminal,
    )


def build_step_response(
    reasoning: str,
    actions: list[str],
    context_id: str | None = None,
    task_id: str | None = None,
) -> Message:
    """
    Build an outgoing A2A Message from LLM output.

    Produces a Message with role=agent containing exactly two parts:
      - TextPart  — LLM chain-of-thought reasoning
      - DataPart  — {"actions": [...]}

    Args:
        reasoning:  LLM chain-of-thought text.
        actions:    Ordered list of pyautogui expressions / special values.
                    If empty, ["FAIL"] is substituted.
        context_id: A2A context id to embed in the message (optional).
        task_id:    A2A task id to embed in the message (optional).

    Returns:
        A2A Message with role=agent.
    """
    if not actions:
        actions = ["FAIL"]

    parts = [
        Part(root=TextPart(text=reasoning)),
        Part(root=DataPart(data={"actions": actions})),
    ]
    return Message(
        message_id=_make_message_id(),
        role=Role.agent,
        parts=parts,
        context_id=context_id,
        task_id=task_id,
    )


__all__ = ["StepMessage", "StepResponse", "parse_step_message", "build_step_response"]
