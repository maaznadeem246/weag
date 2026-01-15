"""
Langfuse tracing and OpenAI client configuration.

Provides:
- get_langfuse_client(): Configured Langfuse client for tracing
- get_openai_client(): OpenAI client wrapper with Langfuse integration and Gemini support
"""

from typing import Optional
from langfuse import Langfuse
from langfuse.openai import OpenAI
from src.config.settings import settings


_langfuse_client: Optional[Langfuse] = None
_openai_client: Optional[OpenAI] = None


def get_langfuse_client() -> Optional[Langfuse]:
    """
    Get or create Langfuse client for tracing.
    
    Returns:
        Configured Langfuse client if enabled, None otherwise
    """
    global _langfuse_client
    
    if not settings.langfuse_enabled:
        return None
    
    if _langfuse_client is None:
        if not settings.langfuse_public_key or not settings.langfuse_secret_key:
            raise ValueError(
                "Langfuse enabled but missing credentials: "
                "LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY required"
            )
        
        # Pass blocked_instrumentation_scopes if configured to avoid sending
        # traces from noisy libraries (e.g., A2A SDK internals)
        kwargs = dict(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
            debug=settings.langfuse_debug,
        )
        if getattr(settings, "langfuse_blocked_instrumentation_scopes", None):
            kwargs["blocked_instrumentation_scopes"] = (
                settings.langfuse_blocked_instrumentation_scopes
            )

        _langfuse_client = Langfuse(**kwargs)
    
    return _langfuse_client


def get_openai_client() -> OpenAI:
    """
    Get or create OpenAI client with Langfuse tracing and Gemini support.
    
    This client can be used with Gemini models by configuring base_url to
    Gemini's OpenAI-compatible endpoint.
    
    Returns:
        OpenAI client wrapped with Langfuse tracing
        
    Raises:
        ValueError: If GEMINI_API_KEY is not configured
    """
    global _openai_client
    
    if _openai_client is None:
        if not settings.gemini_api_key:
            raise ValueError(
                "GEMINI_API_KEY environment variable required for agent orchestration"
            )
        
        # Create OpenAI client with Gemini configuration
        # Langfuse.openai wraps the client for automatic tracing
        _openai_client = OpenAI(
            api_key=settings.gemini_api_key,
            base_url=settings.gemini_base_url,
        )
    
    return _openai_client


def shutdown_langfuse() -> None:
    """
    Shutdown Langfuse client and flush any pending traces.
    
    Call this during application shutdown to ensure all traces are sent.
    """
    global _langfuse_client
    
    if _langfuse_client is not None:
        _langfuse_client.flush()
        _langfuse_client = None


__all__ = [
    "get_langfuse_client",
    "get_openai_client",
    "shutdown_langfuse",
]
