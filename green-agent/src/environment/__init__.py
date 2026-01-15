"""Environment management for BrowserGym.

This module provides:
- Session management for BrowserGym environments
- Action execution and translation
- Observation utilities for processing AXTree, DOM, etc.
- Entity definitions (EnvironmentConfig, EnvironmentSession)
"""

from src.environment.entities import (
    EnvironmentConfig,
    EnvironmentSession,
    CleanupStatus,
)
from src.environment.session_manager import SessionManager
from src.environment.action_executor import ActionExecutor
from src.environment.observation_utils import (
    format_axtree,
    format_html,
    get_goal,
    get_url,
    get_last_action_error,
    find_elements_by_role,
    find_element_by_text,
    find_clickable_element,
    find_input_element,
    map_dom_id_to_bid,
)

__all__ = [
    # Entities
    "EnvironmentConfig",
    "EnvironmentSession",
    "CleanupStatus",
    # Managers
    "SessionManager",
    "ActionExecutor",
    # Observation utilities
    "format_axtree",
    "format_html",
    "get_goal",
    "get_url",
    "get_last_action_error",
    "find_elements_by_role",
    "find_element_by_text",
    "find_clickable_element",
    "find_input_element",
    "map_dom_id_to_bid",
]
