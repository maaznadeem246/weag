"""
Action executor for BrowserGym environment.

Translates JSON action requests to BrowserGym string format and executes batches.
"""

import asyncio
from textwrap import dedent
from typing import Dict, Any, List
from datetime import datetime
import time
from src.environment.action_entities import ActionRequest, ActionResult, ActionBatch
from src.environment.entities import EnvironmentSession
from src.environment.observation_filter import ObservationFilter
from src.utils.logging import get_logger


logger = get_logger(__name__)


class ActionExecutor:
    """
    Executes action batches on BrowserGym environments.
    
    Handles:
    - JSON to BrowserGym action translation
    - Sequential batch execution
    - Early termination on task completion
    - Per-action error handling
    """
    
    def __init__(self, observation_filter: ObservationFilter):
        """
        Initialize action executor.
        
        Args:
            observation_filter: Observation filter for result observations
        """
        self.observation_filter = observation_filter
    
    def translate_action(self, action_request: ActionRequest) -> str:
        """
        Translate structured action request to BrowserGym string format.
        """
        action_request.validate()  # Raises ValueError if invalid

        action = action_request.action.lower()

        def _esc(val: str) -> str:
            return val.replace("'", "\\'")

        if action == "click":
            button = f", '{action_request.button}'" if action_request.button else ""
            return f"click('{action_request.bid}'{button})"

        if action == "dblclick":
            button = f", '{action_request.button}'" if action_request.button else ""
            return f"dblclick('{action_request.bid}'{button})"

        if action == "hover":
            return f"hover('{action_request.bid}')"

        if action == "fill":
            text = _esc(action_request.text)
            return f"fill('{action_request.bid}', '{text}')"

        if action == "select_option":
            value = action_request.text or (action_request.options[0] if action_request.options else "")
            value = _esc(value)
            return f"select_option('{action_request.bid}', '{value}')"

        if action == "clear":
            return f"clear('{action_request.bid}')"

        if action == "focus":
            return f"focus('{action_request.bid}')"

        if action == "scroll":
            # Prefer explicit dx/dy, else map direction to dy
            dx = action_request.dx if action_request.dx is not None else 0
            if action_request.dy is not None:
                dy = action_request.dy
            else:
                dir_lower = (action_request.direction or "down").lower()
                dy_map = {"down": 100, "up": -100, "left": 0, "right": 0}
                dx_map = {"left": -100, "right": 100}
                dy = dy_map.get(dir_lower, 100)
                dx = dx_map.get(dir_lower, dx)
            return f"scroll({dx}, {dy})"

        if action in ("keyboard_type", "keyboard"):
            text = _esc(action_request.text)
            return f"keyboard_type('{text}')"

        if action in ("keyboard_press", "press"):
            key = action_request.key_comb or action_request.key
            return f"keyboard_press('{key}')"

        if action == "goto":
            return f"goto('{_esc(action_request.url)}')"

        if action == "tab_focus":
            return f"tab_focus({action_request.tab_index})"

        if action == "new_tab":
            return "new_tab()"

        if action == "tab_close":
            return "tab_close()"

        if action == "send_msg_to_user":
            return f"send_msg_to_user('{_esc(action_request.text)}')"

        if action == "drag_and_drop":
            return f"drag_and_drop('{action_request.from_bid}', '{action_request.to_bid}')"

        raise ValueError(f"Unknown action type: {action}")
    
    def execute_batch(
        self,
        session: EnvironmentSession,
        action_batch: ActionBatch
    ) -> ActionBatch:
        """
        Execute action batch sequentially with early termination.
        
        Args:
            session: Active environment session
            action_batch: Batch of actions to execute
            
        Returns:
            Completed action batch with results
        """
        action_batch.mark_started()
        
        logger.info(
            "Starting action batch execution",
            extra={
                "batch_id": action_batch.batch_id,
                "action_count": len(action_batch.actions),
                "session_id": session.session_id
            }
        )
        
        for i, action_request in enumerate(action_batch.actions):
            action_start = time.time()
            
            try:
                # Translate action
                browsergym_action = self.translate_action(action_request)
                
                logger.debug(
                    f"Executing action {i+1}/{len(action_batch.actions)}",
                    extra={
                        "action_index": i,
                        "action_type": action_request.action,
                        "browsergym_action": browsergym_action
                    }
                )
                
                # Execute action on environment
                observation, reward, done, truncated, info = session.env_instance.step(browsergym_action)
                
                # Update session observation
                session.update_observation(observation)
                session.add_action(browsergym_action)
                
                # Filter observation for response
                filtered_obs = self.observation_filter.filter_observation(observation)
                
                # Calculate action latency
                action_latency = (time.time() - action_start) * 1000
                
                # Create result
                result = ActionResult(
                    observation=filtered_obs,
                    reward=reward,
                    done=done,
                    truncated=truncated,
                    error=None,
                    action_index=i,
                    latency_ms=action_latency
                )
                
                action_batch.add_result(result)
                
                # Log with clear formatting for SDK-provided values
                logger.info(
                    dedent(f"""
                        +==================================================================+
                        |  >>> ACTION {i+1}/{len(action_batch.actions)} COMPLETED - BrowserGym SDK Response <<<  |
                        +==================================================================+
                        |  REWARD:     {reward:.4f}   (from env.step() - authentic)        |
                        |  DONE:       {done!s:<6}   (task goal achieved by SDK)          |
                        |  TRUNCATED:  {truncated!s:<6}   (max steps reached?)               |
                        |  LATENCY:    {action_latency:.1f}ms                                    |
                        +==================================================================+
                    """).strip(),
                    extra={
                        "action_index": i,
                        "reward": reward,
                        "done": done,
                        "truncated": truncated,
                        "latency_ms": action_latency,
                        "source": "BrowserGym_SDK"
                    }
                )
                
                # Early termination check
                if action_batch.should_terminate_early():
                    action_batch.early_termination = True
                    logger.info(
                        dedent(f"""
                            ************************************************************
                            *   [SUCCESS] TASK COMPLETED - BrowserGym SDK confirmed!  *
                            ************************************************************
                            *   Final Reward:  {reward:.4f}                              *
                            *   Done:          {done!s:<5}                               *
                            *   Truncated:     {truncated!s:<5}                               *
                            *   Actions:       {i + 1}/{len(action_batch.actions)}                                 *
                            *   Source:        env.step() -> BrowserGym SDK (NOT LLM) *
                            ************************************************************
                        """).strip(),
                        extra={
                            "batch_id": action_batch.batch_id,
                            "completed_actions": i + 1,
                            "total_actions": len(action_batch.actions),
                            "final_reward": reward,
                            "source": "BrowserGym_SDK"
                        }
                    )
                    break
                    
            except Exception as e:
                action_latency = (time.time() - action_start) * 1000
                
                logger.error(
                    f"Action {i+1} failed",
                    extra={
                        "action_index": i,
                        "action_type": action_request.action,
                        "error": str(e)
                    },
                    exc_info=True
                )
                
                # Create error result with current observation
                filtered_obs = self.observation_filter.filter_observation(
                    session.current_observation or {}
                )
                
                result = ActionResult(
                    observation=filtered_obs,
                    reward=0.0,
                    done=False,
                    truncated=False,
                    error=str(e),
                    action_index=i,
                    latency_ms=action_latency
                )
                
                action_batch.add_result(result)
                
                # Continue with next action (don't fail entire batch)
        
        action_batch.mark_completed()
        
        logger.info(
            "Action batch completed",
            extra={
                "batch_id": action_batch.batch_id,
                "total_actions": len(action_batch.actions),
                "completed_actions": len(action_batch.results),
                "early_termination": action_batch.early_termination,
                "latency_ms": action_batch.latency_ms
            }
        )
        
        return action_batch
