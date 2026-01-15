"""
Benchmark-specific tool handler implementations for MCP tools.

These handlers are dynamically registered based on the active benchmark.
Extracted from tool_registry.py for better modularity.
"""

import asyncio
import base64
from typing import Any
from datetime import datetime

from src.environment.thread_executor import browser_executor
from src.utils.logging import get_logger

logger = get_logger(__name__)


# =============================================================================
# Session Manager Lazy Import
# =============================================================================

_session_manager = None


def get_session_manager():
    """Lazy import of session manager to avoid circular imports."""
    global _session_manager
    if _session_manager is None:
        from src.environment.session_manager import SessionManager
        _session_manager = SessionManager()
    return _session_manager


# =============================================================================
# WebArena Tool Handlers
# =============================================================================

async def navigate_tabs_handler(tab_index: int) -> dict[str, Any]:
    """Switch between browser tabs.
    
    Args:
        tab_index: Target tab index (0-based)
        
    Returns:
        dict with success status and current tab info
    """
    start_time = datetime.utcnow()
    logger.info(f"navigate_tabs invoked: tab_index={tab_index}")
    
    try:
        session_manager = get_session_manager()
        session = session_manager.get_session()
        
        if not session or not session.env:
            raise ValueError("No active session")
        
        # Get Playwright page from BrowserGym env
        page = session.env.page
        context = page.context
        pages = context.pages
        
        if tab_index < 0 or tab_index >= len(pages):
            raise ValueError(f"Tab index {tab_index} out of range (0-{len(pages)-1})")
        
        # Bring target tab to front
        await browser_executor.run(pages[tab_index].bring_to_front)
        
        latency_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
        
        return {
            "success": True,
            "current_tab": tab_index,
            "total_tabs": len(pages),
            "url": pages[tab_index].url,
            "latency_ms": latency_ms,
        }
    except Exception as e:
        logger.error(f"navigate_tabs failed: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


async def fill_form_handler(fields: list[dict[str, str]]) -> dict[str, Any]:
    """Fill a form with multiple fields at once.
    
    Args:
        fields: List of {selector: str, value: str} or {field_name: str, value: str}
        
    Returns:
        dict with success status and filled field count
    """
    start_time = datetime.utcnow()
    logger.info(f"fill_form invoked: {len(fields)} fields")
    
    try:
        session_manager = get_session_manager()
        session = session_manager.get_session()
        
        if not session or not session.env:
            raise ValueError("No active session")
        
        page = session.env.page
        filled_count = 0
        errors = []
        
        for field in fields:
            try:
                # Support both selector and field_name patterns
                selector = field.get("selector") or field.get("field_name")
                value = field.get("value", "")
                
                if not selector:
                    errors.append("Missing selector/field_name")
                    continue
                
                # Fill the field
                await browser_executor.run(page.fill, selector, value)
                filled_count += 1
            except Exception as e:
                errors.append(f"{selector}: {str(e)}")
        
        latency_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
        
        return {
            "success": filled_count == len(fields),
            "filled_count": filled_count,
            "total_fields": len(fields),
            "errors": errors if errors else None,
            "latency_ms": latency_ms,
        }
    except Exception as e:
        logger.error(f"fill_form failed: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


# =============================================================================
# VisualWebArena Tool Handlers
# =============================================================================

async def get_screenshot_handler(full_page: bool = False) -> dict[str, Any]:
    """Capture current page screenshot.
    
    Args:
        full_page: Whether to capture full page or viewport only
        
    Returns:
        dict with base64-encoded screenshot data
    """
    start_time = datetime.utcnow()
    logger.info(f"get_screenshot invoked: full_page={full_page}")
    
    try:
        session_manager = get_session_manager()
        session = session_manager.get_session()
        
        if not session or not session.env:
            raise ValueError("No active session")
        
        page = session.env.page
        
        # Capture screenshot
        screenshot_bytes = await browser_executor.run(
            page.screenshot,
            full_page=full_page,
            type="png"
        )
        
        # Encode as base64
        screenshot_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")
        
        latency_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
        
        return {
            "success": True,
            "screenshot": screenshot_b64,
            "mime_type": "image/png",
            "full_page": full_page,
            "size_bytes": len(screenshot_bytes),
            "latency_ms": latency_ms,
        }
    except Exception as e:
        logger.error(f"get_screenshot failed: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


async def identify_visual_element_handler(description: str) -> dict[str, Any]:
    """Identify element by visual description.
    
    Note: Placeholder implementation using text matching.
    Full implementation would require vision model integration.
    
    Args:
        description: Visual description of the element to find
        
    Returns:
        dict with matching element info
    """
    start_time = datetime.utcnow()
    logger.info(f"identify_visual_element invoked: description='{description[:50]}...'")
    
    try:
        session_manager = get_session_manager()
        session = session_manager.get_session()
        
        if not session or not session.env:
            raise ValueError("No active session")
        
        # Get current observation for element matching
        obs = session.current_observation or {}
        axtree = obs.get("axtree_txt", "")
        
        # Simple text matching fallback
        matches = []
        description_lower = description.lower()
        
        for line in axtree.split("\n"):
            if any(word in line.lower() for word in description_lower.split()):
                matches.append(line.strip())
        
        latency_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
        
        return {
            "success": len(matches) > 0,
            "matches": matches[:5],  # Top 5 matches
            "match_count": len(matches),
            "method": "text_matching",
            "latency_ms": latency_ms,
        }
    except Exception as e:
        logger.error(f"identify_visual_element failed: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


# =============================================================================
# WorkArena Tool Handlers
# =============================================================================

async def submit_form_handler(confirm: bool = True) -> dict[str, Any]:
    """Submit the current form.
    
    Args:
        confirm: Whether to confirm submission dialogs
        
    Returns:
        dict with success status
    """
    start_time = datetime.utcnow()
    logger.info(f"submit_form invoked: confirm={confirm}")
    
    try:
        session_manager = get_session_manager()
        session = session_manager.get_session()
        
        if not session or not session.env:
            raise ValueError("No active session")
        
        page = session.env.page
        
        # Set up dialog handler if confirm is True
        if confirm:
            async def handle_dialog(dialog):
                await dialog.accept()
            page.on("dialog", handle_dialog)
        
        # Try to find and click submit button
        submit_selectors = [
            'button[type="submit"]',
            'input[type="submit"]',
            'button:has-text("Submit")',
            'button:has-text("Save")',
            '#submit',
            '.submit-button',
        ]
        
        submitted = False
        for selector in submit_selectors:
            try:
                element = await browser_executor.run(page.query_selector, selector)
                if element:
                    await browser_executor.run(element.click)
                    submitted = True
                    break
            except Exception:
                continue
        
        # Wait for navigation/response
        if submitted:
            try:
                await browser_executor.run(page.wait_for_load_state, "networkidle", timeout=5000)
            except Exception:
                pass  # Timeout acceptable
        
        latency_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
        
        return {
            "success": submitted,
            "submitted": submitted,
            "url": page.url,
            "latency_ms": latency_ms,
        }
    except Exception as e:
        logger.error(f"submit_form failed: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


# =============================================================================
# AssistantBench Tool Handlers
# =============================================================================

async def submit_answer_handler(answer: str) -> dict[str, Any]:
    """Submit the final answer for the task.
    
    Args:
        answer: The answer to submit
        
    Returns:
        dict with submission status
    """
    start_time = datetime.utcnow()
    logger.info(f"submit_answer invoked: answer='{answer[:50]}...'")
    
    try:
        session_manager = get_session_manager()
        session = session_manager.get_session()
        
        if not session:
            raise ValueError("No active session")
        
        # Store answer in session for evaluation
        session.submitted_answer = answer
        
        latency_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
        
        return {
            "success": True,
            "answer": answer,
            "submitted": True,
            "latency_ms": latency_ms,
        }
    except Exception as e:
        logger.error(f"submit_answer failed: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


async def search_page_handler(query: str, case_sensitive: bool = False) -> dict[str, Any]:
    """Search for text content within the current page.
    
    Args:
        query: Search query text
        case_sensitive: Whether search is case-sensitive
        
    Returns:
        dict with matching text snippets
    """
    start_time = datetime.utcnow()
    logger.info(f"search_page invoked: query='{query}'")
    
    try:
        session_manager = get_session_manager()
        session = session_manager.get_session()
        
        if not session or not session.env:
            raise ValueError("No active session")
        
        page = session.env.page
        
        # Get page text content
        text_content = await browser_executor.run(
            page.evaluate,
            "() => document.body.innerText"
        )
        
        # Search for query
        if not case_sensitive:
            search_text = text_content.lower()
            search_query = query.lower()
        else:
            search_text = text_content
            search_query = query
        
        # Find all occurrences with context
        matches = []
        idx = 0
        while True:
            pos = search_text.find(search_query, idx)
            if pos == -1:
                break
            
            # Get context (50 chars before/after)
            start = max(0, pos - 50)
            end = min(len(text_content), pos + len(query) + 50)
            snippet = text_content[start:end]
            
            matches.append({
                "position": pos,
                "snippet": snippet.strip(),
            })
            
            idx = pos + 1
            if len(matches) >= 10:  # Limit to 10 matches
                break
        
        latency_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
        
        return {
            "success": len(matches) > 0,
            "matches": matches,
            "match_count": len(matches),
            "query": query,
            "latency_ms": latency_ms,
        }
    except Exception as e:
        logger.error(f"search_page failed: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


# =============================================================================
# Tool Handler Registry
# =============================================================================

def get_tool_handler_mapping() -> dict[str, Any]:
    """Get mapping of tool names to handler functions.
    
    Returns:
        Dict mapping tool names to async handler functions
    """
    return {
        # WebArena tools
        "navigate_tabs": navigate_tabs_handler,
        "fill_form": fill_form_handler,
        # VisualWebArena tools
        "get_screenshot": get_screenshot_handler,
        "identify_visual_element": identify_visual_element_handler,
        # WorkArena tools
        "submit_form": submit_form_handler,
        # AssistantBench tools
        "submit_answer": submit_answer_handler,
        "search_page": search_page_handler,
    }
