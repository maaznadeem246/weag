"""
OsworldAgent — core LLM logic for the OSWorld Purple Agent.

Receives a parsed StepMessage (instruction + optional screenshot + env config),
runs one step of the OpenAI Agents SDK using output_type=StepResponse for
structured outputs, and returns a (StepResponse, updated_history) tuple.

LLM provider and model are configured entirely via environment variables
(OSWORLD_ prefix) through setup_llm_client().
"""

import logging
from typing import Any, Optional

from agents import Agent, Runner, set_default_openai_api, set_default_openai_client

from .llm_provider import LLMConfig, LLMProvider, setup_llm_client
from .messenger import StepMessage, StepResponse

logger = logging.getLogger(__name__)

# OSWorld-specific system prompt.
# No JSON format instructions needed — output_type=StepResponse enforces the
# schema automatically via the SDK's structured-outputs mechanism.
_SYSTEM_PROMPT = """\
You are a computer-use agent controlling an Ubuntu 22.04 desktop (1920×1080 resolution).

At each step you receive:
  - A task instruction describing what to accomplish
  - A screenshot of the current desktop state
  - Optionally: an accessibility tree and/or terminal output for additional context

## Available pyautogui Actions

Mouse:
  pyautogui.click(x, y)                   # left-click at pixel (x, y)
  pyautogui.doubleClick(x, y)             # double-click
  pyautogui.rightClick(x, y)              # right-click (context menu)
  pyautogui.moveTo(x, y)                  # move cursor without clicking
  pyautogui.dragTo(x, y, duration=0.5)    # drag from current position to (x, y)

Keyboard:
  pyautogui.typewrite("text", interval=0.05)  # type a string character by character
  pyautogui.hotkey("ctrl", "c")               # key combination (copy)
  pyautogui.hotkey("alt", "F4")              # close window
  pyautogui.press("enter")                    # single key press
  pyautogui.press("tab")                      # Tab key
  pyautogui.keyDown("shift"); pyautogui.keyUp("shift")  # hold/release key

Scroll:
  pyautogui.scroll(3)   # scroll up 3 clicks at current cursor position
  pyautogui.scroll(-3)  # scroll down 3 clicks

Wait:
  import time; time.sleep(1.0)  # pause for 1 second

## Special Commands
Use ONE of these as the sole element in actions when appropriate:
  WAIT  — more time is needed (loading, animation); wait for the next screenshot
  DONE  — the task is fully and successfully completed (confirm visually)
  FAIL  — the task cannot be completed (impossible request or unrecoverable error)

## Strategy
1. Study the screenshot carefully — identify the target element and its pixel coordinates.
2. Prefer clicking visible UI elements over keyboard shortcuts when both work.
3. Issue ONE action per step — you will see the result before deciding the next action.
4. Use WAIT when a spinner, loading bar, or animation is visible.
5. Use DONE only after visually confirming the task outcome in the screenshot.
6. Use FAIL only as a last resort after exhausting all reasonable approaches.

## Output Fields
- reasoning: Your chain-of-thought — what you see, where the target is, why this action.
- actions: A non-empty list of pyautogui expression strings (or WAIT/DONE/FAIL).
"""


def _build_input(step: StepMessage, history: list[dict]) -> list[dict]:
    """
    Build the message list for Runner.run(), including full conversation history.

    Args:
        step: Parsed step message from the green agent.
        history: Prior turns as returned by result.to_input_list() from the SDK.

    Returns:
        Full message list: history + new user message with screenshot.
    """
    content: list[Any] = [{"type": "text", "text": step.instruction}]

    if step.accessibility_tree:
        content.append(
            {"type": "text", "text": f"Accessibility tree:\n{step.accessibility_tree}"}
        )

    if step.terminal:
        content.append(
            {"type": "text", "text": f"Terminal output:\n{step.terminal}"}
        )

    if step.screenshot_b64:
        content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{step.screenshot_b64}",
                    "detail": "high",
                },
            }
        )

    return list(history) + [{"role": "user", "content": content}]


class OsworldAgent:
    """
    Agent wrapper around the OpenAI Agents SDK using structured outputs.

    Uses output_type=StepResponse so the SDK enforces the JSON schema via
    structured outputs — no manual JSON parsing or regex fallback needed.

    run() returns (StepResponse, updated_history) where updated_history is
    result.to_input_list() — the caller should store this and pass it back
    on the next invocation to maintain the full conversation trajectory.
    """

    def __init__(self, llm_config: Optional[LLMConfig] = None) -> None:
        """
        Initialise the agent and wire up the LLM provider.

        Args:
            llm_config: Pre-built config, or None to load from OSWORLD_ env vars.
        """
        client, model, cfg = setup_llm_client(llm_config, prefix="OSWORLD_")

        agent_kwargs: dict[str, Any] = dict(
            name="OsworldPurpleAgent",
            instructions=_SYSTEM_PROMPT,
            output_type=StepResponse,
        )

        if cfg.provider == LLMProvider.LITELLM:
            # LitellmModel instance is passed directly as Agent.model.
            self._sdk_agent: Agent = Agent(model=model, **agent_kwargs)
        else:
            # OpenAI / Gemini: configure the global default client.
            set_default_openai_api("chat_completions")
            set_default_openai_client(client)
            self._sdk_agent = Agent(model=str(model), **agent_kwargs)

        self._max_iterations: int = cfg.max_iterations
        logger.info(
            "OsworldAgent initialised — provider=%s model=%s",
            cfg.provider.value,
            getattr(model, "model", model),
        )

    async def run(
        self, step: StepMessage, history: list[dict]
    ) -> tuple[StepResponse, list[dict]]:
        """
        Execute one evaluation step.

        Args:
            step: Parsed step message (instruction, screenshot, env_config, …).
            history: Conversation history from the previous result.to_input_list()
                     call, or [] for the first step.

        Returns:
            (response, updated_history) where:
              - response is a StepResponse with typed reasoning + actions.
              - updated_history is result.to_input_list() — pass this back on
                the next call to maintain the full trajectory.
            On LLM error, returns a FAIL StepResponse and the input messages
            list (so history is still usable on the next step).
        """
        messages = _build_input(step, history)

        try:
            result = await Runner.run(
                self._sdk_agent,
                input=messages,
                max_turns=self._max_iterations,
            )
            response: StepResponse = result.final_output
            # Guard: SDK structured output should always return actions, but
            # if the model returns an empty list, default to FAIL.
            if not response.actions:
                response = StepResponse(reasoning=response.reasoning, actions=["FAIL"])
            return response, result.to_input_list()

        except Exception as exc:
            error_msg = f"LLM call failed: {type(exc).__name__}: {exc}"
            logger.error("OsworldAgent.run error: %s", error_msg, exc_info=True)
            return StepResponse(reasoning=error_msg, actions=["FAIL"]), messages


__all__ = ["OsworldAgent"]
