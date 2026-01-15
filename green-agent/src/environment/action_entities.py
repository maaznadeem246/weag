"""
Action entities for BrowserGym action execution.

Supports rich BrowserGym action types: click, dblclick, hover, fill, select_option,
scroll, keyboard_type, keyboard_press, goto, tab management, drag_and_drop, and more.
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import uuid


class ActionType(Enum):
    """Supported BrowserGym action types."""
    CLICK = "click"
    DBLCLICK = "dblclick"
    HOVER = "hover"
    FILL = "fill"
    SELECT_OPTION = "select_option"
    SCROLL = "scroll"
    KEYBOARD_TYPE = "keyboard_type"
    KEYBOARD_PRESS = "keyboard_press"
    GOTO = "goto"
    TAB_FOCUS = "tab_focus"
    NEW_TAB = "new_tab"
    TAB_CLOSE = "tab_close"
    SEND_MSG_TO_USER = "send_msg_to_user"
    CLEAR = "clear"
    FOCUS = "focus"
    PRESS = "press"  # backward-compatible alias -> keyboard_press
    DRAG_AND_DROP = "drag_and_drop"
    KEYBOARD = "keyboard"  # legacy alias handled in translation


@dataclass
class ActionRequest:
    """
    Action request from purple agent.
    
    Attributes:
        action: Action type (click/fill/select_option/scroll/keyboard)
        bid: Browser element ID (for click, fill, select_option)
        text: Text input (for fill, keyboard)
        url: URL for navigation (optional)
        direction: Scroll direction (for scroll: up/down/left/right)
        key: Keyboard key (for keyboard: Enter, Tab, etc.)
    """
    action: str
    bid: Optional[str] = None
    text: Optional[str] = None
    url: Optional[str] = None
    direction: Optional[str] = None  # legacy scroll direction
    dx: Optional[int] = None  # scroll dx
    dy: Optional[int] = None  # scroll dy
    key: Optional[str] = None  # legacy single key
    key_comb: Optional[str] = None  # keyboard_press combination
    tab_index: Optional[int] = None
    options: Optional[list[str]] = None
    button: Optional[str] = None  # mouse button where applicable
    from_bid: Optional[str] = None
    to_bid: Optional[str] = None
    
    def validate(self) -> bool:
        """
        Validate action parameters.
        
        Returns:
            True if valid, raises ValueError otherwise
        """
        normalized_action = (self.action or "").lower()
        try:
            action_type = ActionType(normalized_action)
        except ValueError:
            raise ValueError(f"Invalid action type: {self.action}")

        # Validate required parameters per action type
        if action_type in (ActionType.CLICK, ActionType.DBLCLICK, ActionType.HOVER, ActionType.CLEAR, ActionType.FOCUS):
            if not self.bid:
                raise ValueError(f"{action_type.value} action requires 'bid' parameter")

        elif action_type == ActionType.FILL:
            if not self.bid or not self.text:
                raise ValueError("Fill action requires 'bid' and 'text' parameters")

        elif action_type == ActionType.SELECT_OPTION:
            if not self.bid or not (self.text or (self.options and len(self.options) > 0)):
                raise ValueError("Select_option action requires 'bid' and 'text' or 'options'")

        elif action_type == ActionType.SCROLL:
            if self.direction is None and self.dy is None and self.dx is None:
                raise ValueError("Scroll action requires 'direction' or numeric dx/dy")

        elif action_type in (ActionType.KEYBOARD_TYPE, ActionType.KEYBOARD):
            if not self.text:
                raise ValueError("keyboard_type action requires 'text' parameter")

        elif action_type in (ActionType.KEYBOARD_PRESS, ActionType.PRESS):
            if not (self.key_comb or self.key):
                raise ValueError("keyboard_press action requires 'key_comb' or 'key'")

        elif action_type == ActionType.GOTO:
            if not self.url:
                raise ValueError("goto action requires 'url'")

        elif action_type == ActionType.TAB_FOCUS:
            if self.tab_index is None:
                raise ValueError("tab_focus action requires 'tab_index'")

        elif action_type == ActionType.SEND_MSG_TO_USER:
            if not self.text:
                raise ValueError("send_msg_to_user action requires 'text'")

        elif action_type == ActionType.DRAG_AND_DROP:
            if not (self.from_bid and self.to_bid):
                raise ValueError("drag_and_drop action requires 'from_bid' and 'to_bid'")

        # new_tab / tab_close have no required params

        return True


@dataclass
class ActionResult:
    """
    Result of executing a single action.
    
    Attributes:
        observation: Filtered observation after action
        reward: BrowserGym reward (task completion signal)
        done: Task completion flag
        truncated: Episode truncation flag (max steps reached)
        error: Error message if action failed
        action_index: Index in batch (0-based)
        latency_ms: Action execution time
    """
    observation: Dict[str, Any]
    reward: float
    done: bool
    truncated: bool
    error: Optional[str] = None
    action_index: int = 0
    latency_ms: float = 0.0


@dataclass
class ActionBatch:
    """
    Batch of actions for sequential execution.
    
    Attributes:
        batch_id: Unique batch identifier
        actions: List of action requests
        results: List of action results (populated during execution)
        started_at: Batch start timestamp
        completed_at: Batch completion timestamp
        latency_ms: Total batch execution time
        early_termination: True if batch stopped early (done=True or truncated=True)
    """
    batch_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    actions: List[ActionRequest] = field(default_factory=list)
    results: List[ActionResult] = field(default_factory=list)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    latency_ms: float = 0.0
    early_termination: bool = False
    
    def add_result(self, result: ActionResult):
        """Add action result to batch."""
        self.results.append(result)
    
    def mark_started(self):
        """Mark batch as started."""
        self.started_at = datetime.utcnow()
    
    def mark_completed(self):
        """Mark batch as completed and calculate latency."""
        self.completed_at = datetime.utcnow()
        if self.started_at:
            self.latency_ms = (self.completed_at - self.started_at).total_seconds() * 1000
    
    def should_terminate_early(self) -> bool:
        """
        Check if batch should terminate early.
        
        Returns:
            True if last result indicates task completion or truncation
        """
        if not self.results:
            return False
        
        last_result = self.results[-1]
        return last_result.done or last_result.truncated
