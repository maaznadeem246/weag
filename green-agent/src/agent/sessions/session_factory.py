"""
Session factory for creating agent sessions (SQLite or in-memory).

Sessions store agent conversation history and state for resumption.
"""

from src.agent.sessions.session_storage import (
    cleanup_expired_sessions,
    create_session,
    get_session_history,
)

__all__ = [
    "create_session",
    "cleanup_expired_sessions",
    "get_session_history",
]
