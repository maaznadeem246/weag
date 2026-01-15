"""
Session storage implementations for agent persistence.

Implements SQLite session storage for agent state persistence.
"""

import os
from datetime import datetime, timedelta
from typing import Any

try:
    # OpenAI Agents SDK: SQLiteSession supports both in-memory and persistent storage
    from agents import SQLiteSession  # type: ignore
except Exception:  # pragma: no cover
    SQLiteSession = None  # type: ignore

from src.config.settings import settings
from src.utils.logging import get_logger

logger = get_logger(__name__)


def create_session(session_id: str, use_persistent: bool | None = None) -> Any:
    """
    Create agent session (persistent or in-memory).
    
    Implements Session factory with SQLite/InMemory support.
    
    Args:
        session_id: Unique session identifier (UUID format)
        use_persistent: Override settings to force persistent/in-memory.
                       If None, uses settings.use_persistent_sessions
                       
    Returns:
        SQLiteSession instance (with in-memory or file-based storage)
        
    Example:
        # Production: Persistent SQLite session
        session = create_session("abc-123-def", use_persistent=True)
        
        # Development: In-memory session (lost when process ends)
        session = create_session("test-session", use_persistent=False)
        
    """
    if use_persistent is None:
        use_persistent = settings.use_persistent_sessions
    
    if SQLiteSession is None:
        raise RuntimeError(
            "SQLiteSession is unavailable; ensure the OpenAI Agents SDK is installed"
        )
    
    if use_persistent:
        # SQLiteSession with file storage for production persistence
        db_path = settings.sessions_db_path
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        
        session = SQLiteSession(
            session_id=session_id,
            db_path=db_path,
        )
        
        logger.info(
            "Created persistent session",
            extra={
                "session_id": session_id,
                "db_path": db_path,
            },
        )
    else:
        # SQLiteSession with in-memory storage (default ":memory:")
        # In-memory database is lost when process ends
        session = SQLiteSession(
            session_id=session_id,
            # db_path defaults to ":memory:" if not provided
        )
        
        logger.info(
            "Created in-memory session",
            extra={"session_id": session_id},
        )
    
    return session


def cleanup_expired_sessions(max_age_hours: int = 24) -> int:
    """
    Clean up expired sessions from persistent storage.
    
    Implements Session cleanup with TTL expiration.
    
    Args:
        max_age_hours: Maximum age in hours before session is considered expired
        
    Returns:
        Number of sessions cleaned up
        
    Example:
        # Clean up sessions older than 24 hours
        count = cleanup_expired_sessions(max_age_hours=24)
        logger.info(f"Cleaned up {count} expired sessions")
    """
    if not settings.use_persistent_sessions:
        logger.debug("Session cleanup skipped (in-memory mode)")
        return 0
    
    try:
        import sqlite3
        
        db_path = settings.sessions_db_path
        
        if not os.path.exists(db_path):
            logger.debug("Session database does not exist, nothing to clean")
            return 0
        
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Delete sessions older than cutoff
        cursor.execute(
            """
            DELETE FROM sessions 
            WHERE updated_at < ?
            """,
            (cutoff_time.isoformat(),),
        )
        
        deleted_count = cursor.rowcount
        conn.commit()
        conn.close()
        
        logger.info(
            "Cleaned up expired sessions",
            extra={
                "deleted_count": deleted_count,
                "max_age_hours": max_age_hours,
            },
        )
        
        return deleted_count
        
    except Exception as e:
        logger.error(
            "Session cleanup failed",
            extra={"error": str(e)},
            exc_info=True,
        )
        return 0


def get_session_history(session_id: str) -> dict[str, Any]:
    """
    Retrieve session conversation history and artifacts.
    
    Implements Session query endpoint support.
    
    Args:
        session_id: Session identifier to query
        
    Returns:
        Dictionary with session metadata, conversation history, artifacts
        
    Example:
        history = get_session_history("abc-123-def")
        print(f"Session has {len(history['messages'])} messages")
    """
    if not settings.use_persistent_sessions:
        return {
            "error": "Session history not available in in-memory mode",
            "session_id": session_id,
        }
    
    try:
        import sqlite3
        
        db_path = settings.sessions_db_path
        
        if not os.path.exists(db_path):
            return {
                "error": "Session database not found",
                "session_id": session_id,
            }
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Query session data
        cursor.execute(
            """
            SELECT session_id, data, created_at, updated_at
            FROM sessions
            WHERE session_id = ?
            """,
            (session_id,),
        )
        
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return {
                "error": "Session not found",
                "session_id": session_id,
            }
        
        import json
        
        session_data = json.loads(row[1]) if row[1] else {}
        
        return {
            "session_id": row[0],
            "data": session_data,
            "created_at": row[2],
            "updated_at": row[3],
        }
        
    except Exception as e:
        logger.error(
            "Failed to retrieve session history",
            extra={"session_id": session_id, "error": str(e)},
            exc_info=True,
        )
        return {
            "error": f"Failed to retrieve session: {str(e)}",
            "session_id": session_id,
        }


__all__ = [
    "create_session",
    "cleanup_expired_sessions",
    "get_session_history",
]
