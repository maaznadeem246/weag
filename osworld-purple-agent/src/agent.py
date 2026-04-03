"""
OsworldAgent — core LLM logic for the OSWorld Purple Agent.

Receives a parsed StepMessage (instruction + optional screenshot + env config),
runs one step of the OpenAI Agents SDK, and returns a StepResponse with
reasoning text and a list of pyautogui action strings.

LLM provider and model are configured entirely via environment variables
(OSWORLD_ prefix) through setup_llm_client().
"""

import json
import logging
import re
from typing import Any, Optional

from agents import Agent, Runner, set_default_openai_api, set_default_openai_client

from .llm_provider import LLMConfig, LLMProvider, setup_llm_client
from .messenger import StepMessage, StepResponse

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a computer-use agent operating an Ubuntu desktop remotely via pyautogui.
At each step you receive:
  - A task instruction
  - A screenshot of the current desktop (when available)
  - Optional accessibility tree and terminal output

Your job is to decide the next action(s) and explain your reasoning.

Return your response as JSON with exactly two fields:
{
  "reasoning": "<chain-of-thought explaining what you see and what you intend to do>",
  "actions": ["<pyautogui expression>", ...]
}

Rules:
- actions must be a non-empty JSON array of strings.
- Each string is either a valid pyautogui Python expression (e.g. "pyautogui.click(150, 200)")
  or one of the special strings: "WAIT", "DONE", "FAIL".
- Use "DONE" when the task is fully completed.
- Use "FAIL" if the task cannot be completed.
- Use "WAIT" to pause and observe the next screenshot before acting.
- Do NOT include markdown fences — output raw JSON only.
"""


def _build_input(step: StepMessage, history: list[dict]) -> list[dict]:
    """
    Build the message list for Runner.run().

    Args:
        step: Parsed step message from the green agent.
        history: Conversation history (list of {role, content} dicts).

    Returns:
        Message list including all history plus current step.
    """
    content: list[Any] = [{"type": "text", "text": step.instruction}]

    if step.accessibility_tree:
        content.append(
            {
                "type": "text",
                "text": f"Accessibility tree:\n{step.accessibility_tree}",
            }
        )

    if step.terminal:
        content.append(
            {"type": "text", "text": f"Terminal output:\n{step.terminal}"}
        )

    if step.screenshot_b64:
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{step.screenshot_b64}"},
            }
        )

    # Combined history messages (already formatted) + new user message.
    messages = list(history)
    messages.append({"role": "user", "content": content})
    return messages


def _parse_actions(raw_output: str) -> tuple[str, list[str]]:
    """
    Extract reasoning and actions from raw LLM text output.

    Tries to parse JSON from the output. Falls back to returning FAIL.

    Args:
        raw_output: Raw string returned by Runner.run().

    Returns:
        Tuple of (reasoning_text, actions_list).
    """
    # Strip markdown code fences if present.
    cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", raw_output).strip()

    try:
        data = json.loads(cleaned)
        reasoning = str(data.get("reasoning", ""))
        actions = data.get("actions", [])
        if not isinstance(actions, list) or not actions:
            actions = ["FAIL"]
        return reasoning, [str(a) for a in actions]
    except (json.JSONDecodeError, ValueError):
        # Try to extract an actions array by regex as last resort.
        match = re.search(r'"actions"\s*:\s*(\[.*?\])', cleaned, re.DOTALL)
        if match:
            try:
                actions = json.loads(match.group(1))
                return cleaned, [str(a) for a in actions]
            except (json.JSONDecodeError, ValueError):
                pass
        return cleaned, ["FAIL"]


class OsworldAgent:
    """
    Stateless agent wrapper around the OpenAI Agents SDK.

    Each call to run() performs one step: builds the SDK input, calls Runner.run(),
    parses the JSON response, and returns a StepResponse.
    History management is the caller's responsibility (executor.py).
    """

    def __init__(self, llm_config: Optional[LLMConfig] = None) -> None:
        """
        Initialise the agent and wire up the LLM client.

        Args:
            llm_config: Pre-built config, or None to load from OSWORLD_ env vars.
        """
        client, model, cfg = setup_llm_client(llm_config, prefix="OSWORLD_")

        if cfg.provider == LLMProvider.LITELLM:
            # model is a LitellmModel instance — pass directly to Agent.model.
            self._sdk_agent: Agent = Agent(
                name="OsworldPurpleAgent",
                instructions=_SYSTEM_PROMPT,
                model=model,
            )
        else:
            # OpenAI / Gemini: configure the global default client.
            set_default_openai_api("chat_completions")
            set_default_openai_client(client)
            self._sdk_agent = Agent(
                name="OsworldPurpleAgent",
                instructions=_SYSTEM_PROMPT,
                model=str(model),
            )

        self._max_iterations: int = cfg.max_iterations
        logger.info(
            "OsworldAgent initialised — provider=%s model=%s",
            cfg.provider.value,
            getattr(model, "model", model),
        )

    async def run(self, step: StepMessage, history: list[dict]) -> StepResponse:
        """
        Execute one evaluation step.

        Args:
            step: Parsed step message (instruction, screenshot, env_config, …).
            history: Conversation history as a list of {role, content} dicts.
                     Will NOT be mutated by this method.

        Returns:
            StepResponse with reasoning text and actions list.
            On any LLM error, returns a FAIL response with the error description.
        """
        messages = _build_input(step, history)

        try:
            result = await Runner.run(
                self._sdk_agent,
                input=messages,
                max_turns=self._max_iterations,
            )
            raw_output = result.final_output or ""
            reasoning, actions = _parse_actions(str(raw_output))
            return StepResponse(reasoning=reasoning, actions=actions)

        except Exception as exc:
            error_msg = f"LLM call failed: {type(exc).__name__}: {exc}"
            logger.error("OsworldAgent.run error: %s", error_msg, exc_info=True)
            return StepResponse(reasoning=error_msg, actions=["FAIL"])


__all__ = ["OsworldAgent"]
