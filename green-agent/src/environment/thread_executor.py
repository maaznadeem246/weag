"""
Dedicated thread executor for Playwright/BrowserGym operations.

From official Playwright documentation (https://playwright.dev/python/docs/library):
    "Playwright's API is not thread-safe. If you are using Playwright in a 
    multi-threaded environment, you should create a playwright instance per thread."
    
    "All its methods, as well as methods on objects created by it (such as 
    BrowserContext, Browser, Page, etc.), are expected to be called on the 
    same thread where the Playwright object was created."

This module provides a single-thread executor to ensure all BrowserGym/Playwright
operations run on a dedicated thread, preventing the "greenlet.error: cannot 
switch to a different thread" error that occurs when using asyncio.to_thread()
with Playwright's sync API.

Usage:
    from src.environment.thread_executor import browser_executor
    
    # Run sync operation on the browser thread (async context)
    result = await browser_executor.run(sync_function, arg1, arg2)
    
    # Run sync operation on the browser thread (sync context)
    result = browser_executor.run_sync(sync_function, arg1, arg2)
"""

import asyncio
import atexit
import threading
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Any, Callable, TypeVar, Optional
import logging

logger = logging.getLogger(__name__)

T = TypeVar('T')


class SingleThreadExecutor:
    """
    A single-thread executor that ensures all operations run on the same thread.
    
    This is critical for Playwright's sync API which uses greenlets that
    cannot switch between threads.
    """
    
    _instance: Optional['SingleThreadExecutor'] = None
    _lock = threading.Lock()
    
    def __new__(cls) -> 'SingleThreadExecutor':
        """Singleton pattern to ensure single executor instance."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance
    
    def __init__(self):
        """Initialize the single-thread executor."""
        if self._initialized:
            return
            
        # Create a single-thread executor
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="playwright_browser")
        self._thread_id: Optional[int] = None
        self._initialized = True
        
        # Register cleanup on exit
        atexit.register(self.shutdown)
        
        logger.info("SingleThreadExecutor initialized for Playwright operations")
    
    def _capture_thread_id(self) -> int:
        """Capture the thread ID on first execution."""
        self._thread_id = threading.current_thread().ident
        return self._thread_id
    
    def run_sync(self, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """
        Run a synchronous function on the dedicated browser thread.
        
        This is a blocking call - use run() for async contexts.
        
        Args:
            func: Function to execute
            *args: Positional arguments
            **kwargs: Keyword arguments
            
        Returns:
            Result of the function
        """
        # Capture thread ID on first call
        if self._thread_id is None:
            self._executor.submit(self._capture_thread_id).result()
        
        future: Future = self._executor.submit(func, *args, **kwargs)
        return future.result()
    
    async def run(self, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """
        Run a synchronous function on the dedicated browser thread (async version).
        
        This is the primary method for async contexts (MCP tools, etc.)
        
        Args:
            func: Synchronous function to execute
            *args: Positional arguments
            **kwargs: Keyword arguments
            
        Returns:
            Result of the function
        """
        loop = asyncio.get_event_loop()
        
        # Capture thread ID on first call
        if self._thread_id is None:
            await loop.run_in_executor(self._executor, self._capture_thread_id)
        
        # Run the function on the dedicated thread
        return await loop.run_in_executor(
            self._executor,
            lambda: func(*args, **kwargs)
        )
    
    def get_thread_id(self) -> Optional[int]:
        """Get the thread ID used by this executor."""
        return self._thread_id
    
    def is_browser_thread(self) -> bool:
        """Check if current thread is the browser thread."""
        return threading.current_thread().ident == self._thread_id
    
    def shutdown(self) -> None:
        """Shutdown the executor."""
        if hasattr(self, '_executor') and self._executor:
            try:
                self._executor.shutdown(wait=True, cancel_futures=False)
                logger.info("SingleThreadExecutor shut down")
            except Exception as e:
                logger.warning(f"Error shutting down executor: {e}")


# Global singleton instance
browser_executor = SingleThreadExecutor()


def run_on_browser_thread(func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """
    Convenience function to run a sync function on the browser thread.
    
    For sync contexts only. Use browser_executor.run() in async contexts.
    """
    return browser_executor.run_sync(func, *args, **kwargs)


async def run_on_browser_thread_async(func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """
    Convenience function to run a sync function on the browser thread (async).
    
    Args:
        func: Synchronous function to execute
        *args: Positional arguments  
        **kwargs: Keyword arguments
        
    Returns:
        Result of the function
    """
    return await browser_executor.run(func, *args, **kwargs)
