"""
LLM Provider Abstraction Layer for Purple Agent.

Supports multiple LLM providers:
- OpenAI Official (default)
- Google Gemini Official (via openai-compatible API)
- LiteLLM (OpenRouter for access to multiple models including Gemini)

Configuration via environment variables or direct instantiation.

IMPORTANT: For OpenAI Agents SDK integration:
- OpenAI/Gemini: Use set_default_openai_client() with AsyncOpenAI
- LiteLLM: Use LitellmModel class directly on Agent (avoids "/" parsing issues)
"""

import os
from enum import Enum
from typing import Optional, Union, Any
from openai import AsyncOpenAI
from pydantic import BaseModel, Field


class LLMProvider(str, Enum):
    """Supported LLM providers."""
    OPENAI = "openai"
    GEMINI = "gemini"
    LITELLM = "litellm"  # OpenRouter via LiteLLM


class LLMConfig(BaseModel):
    """Configuration for LLM provider."""
    
    provider: LLMProvider = Field(
        default=LLMProvider.GEMINI,
        description="LLM provider to use"
    )
    
    # API Keys
    openai_api_key: Optional[str] = Field(
        default=None,
        description="OpenAI API key (if using OpenAI)"
    )
    gemini_api_key: Optional[str] = Field(
        default=None,
        description="Google Gemini API key (if using Gemini)"
    )
    openrouter_api_key: Optional[str] = Field(
        default=None,
        description="OpenRouter API key (if using LiteLLM/OpenRouter)"
    )
    
    # Model names
    openai_model: str = Field(
        default="gpt-4o",
        description="OpenAI model name"
    )
    gemini_model: str = Field(
        default="gemini-2.5-flash",
        description="Gemini model name"
    )
    litellm_model: str = Field(
        default="google/gemini-2.0-flash-exp:free",
        description="Full OpenRouter model identifier (e.g., google/gemini-2.0-flash-exp:free)"
    )
    
    # Base URLs
    gemini_base_url: str = Field(
        default="https://generativelanguage.googleapis.com/v1beta/openai/",
        description="Gemini OpenAI-compatible API base URL"
    )
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1",
        description="OpenRouter API base URL"
    )
    
    # Model settings
    max_iterations: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Maximum agent iterations"
    )
    
    @classmethod
    def from_env(cls, prefix: str = "PURPLE_") -> "LLMConfig":
        """
        Create configuration from environment variables for Purple Agent.
        
        Environment variables (PURPLE_ prefixed values win when provided):
        - PURPLE_LLM_PROVIDER or LLM_PROVIDER: openai|gemini|litellm (default: gemini)
        - PURPLE_OPENAI_API_KEY or OPENAI_API_KEY: OpenAI API key
        - PURPLE_GEMINI_API_KEY or GEMINI_API_KEY: Gemini API key
        - PURPLE_OPENROUTER_API_KEY or OPENROUTER_API_KEY: OpenRouter API key
        - PURPLE_OPENAI_MODEL or OPENAI_MODEL: OpenAI model name
        - PURPLE_GEMINI_MODEL or GEMINI_MODEL: Gemini model name
        - PURPLE_LITELLM_MODEL or LITELLM_MODEL: LiteLLM model name
        - PURPLE_LLM_MAX_ITERATIONS or LLM_MAX_ITERATIONS: Maximum iterations (default: 20)
        """

        def _get(key: str, default: Optional[str] = None) -> Optional[str]:
            prefixed_value = os.getenv(f"{prefix}{key}") if prefix else None
            if prefixed_value not in (None, ""):
                return prefixed_value
            fallback = os.getenv(key, default)
            if fallback in (None, ""):
                return default
            return fallback

        provider_str = (_get("LLM_PROVIDER", "gemini") or "gemini").lower()

        try:
            provider = LLMProvider(provider_str)
        except ValueError:
            provider = LLMProvider.GEMINI

        return cls(
            provider=provider,
            openai_api_key=_get("OPENAI_API_KEY"),
            gemini_api_key=_get("GEMINI_API_KEY"),
            openrouter_api_key=_get("OPENROUTER_API_KEY"),
            openai_model=_get("OPENAI_MODEL", "gpt-4o"),
            gemini_model=_get("GEMINI_MODEL", "gemini-2.5-flash"),
            litellm_model=_get("LITELLM_MODEL", "google/gemini-2.0-flash-exp:free"),
            max_iterations=int(_get("LLM_MAX_ITERATIONS", "20")),
        )


class LLMClientFactory:
    """Factory for creating configured LLM clients."""
    
    @staticmethod
    def create_client(config: LLMConfig) -> tuple[AsyncOpenAI, str]:
        """
        Create AsyncOpenAI client based on configuration.
        
        For OpenAI and Gemini providers, returns (client, model_name).
        For LiteLLM provider, also returns (client, model_name) but the client
        may not be used - use create_litellm_model() instead for Agent.model.
        
        Args:
            config: LLM configuration
            
        Returns:
            Tuple of (client, model_name)
            
        Raises:
            ValueError: If required API key is missing
        """
        if config.provider == LLMProvider.OPENAI:
            return LLMClientFactory._create_openai_client(config)
        elif config.provider == LLMProvider.GEMINI:
            return LLMClientFactory._create_gemini_client(config)
        elif config.provider == LLMProvider.LITELLM:
            return LLMClientFactory._create_litellm_client(config)
        else:
            raise ValueError(f"Unknown provider: {config.provider}")
    
    @staticmethod
    def create_litellm_model(config: LLMConfig) -> Any:
        """
        Create LitellmModel for use with OpenAI Agents SDK.
        
        This is the RECOMMENDED way to use OpenRouter/LiteLLM with the SDK.
        The LitellmModel handles provider routing correctly without "/" parsing issues.
        
        Args:
            config: LLM configuration (must have provider=LITELLM)
            
        Returns:
            LitellmModel instance for use as Agent.model
            
        Raises:
            ValueError: If API key is missing
            ImportError: If openai-agents[litellm] not installed
        """
        if not config.openrouter_api_key:
            raise ValueError(
                "OPENROUTER_API_KEY is required for LiteLLM provider. \n"
                "Please set it in your .env file: PURPLE_OPENROUTER_API_KEY or OPENROUTER_API_KEY=your-key-here\n"
                "Get a free API key at: https://openrouter.ai/keys"
            )
        
        try:
            from agents.extensions.models.litellm_model import LitellmModel
        except ImportError:
            raise ImportError(
                "LitellmModel requires openai-agents[litellm] extension.\n"
                "Install with: pip install 'openai-agents[litellm]'"
            )
        
        # LiteLLM model format for OpenRouter: "openrouter/provider/model"
        model_name = config.litellm_model
        
        # Normalize model name for LiteLLM
        if model_name.startswith("litellm/"):
            model_name = model_name[len("litellm/"):]
        if not model_name.startswith("openrouter/"):
            model_name = f"openrouter/{model_name}"
        
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"✓ Purple Agent LiteLLM: Creating LitellmModel with model='{model_name}'")
        
        return LitellmModel(
            model=model_name,
            api_key=config.openrouter_api_key,
        )
    
    @staticmethod
    def _create_openai_client(config: LLMConfig) -> tuple[AsyncOpenAI, str]:
        """Create OpenAI official client."""
        if not config.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required for OpenAI provider")
        
        client = AsyncOpenAI(api_key=config.openai_api_key)
        return client, config.openai_model
    
    @staticmethod
    def _create_gemini_client(config: LLMConfig) -> tuple[AsyncOpenAI, str]:
        """Create Gemini client via OpenAI-compatible API."""
        if not config.gemini_api_key:
            raise ValueError(
                "GEMINI_API_KEY is required for Gemini provider. \n"
                "Please set it in your .env file: PURPLE_GEMINI_API_KEY or GEMINI_API_KEY=your-key-here\n"
                "Get a free API key at: https://aistudio.google.com/apikey"
            )
        
        client = AsyncOpenAI(
            api_key=config.gemini_api_key,
            base_url=config.gemini_base_url,
        )
        return client, config.gemini_model
    
    @staticmethod
    def _create_litellm_client(config: LLMConfig) -> tuple[AsyncOpenAI, str]:
        """
        Create LiteLLM client (OpenRouter) - FALLBACK method.
        
        NOTE: For OpenAI Agents SDK, prefer using create_litellm_model() instead.
        """
        if not config.openrouter_api_key:
            raise ValueError(
                "OPENROUTER_API_KEY is required for LiteLLM provider. \n"
                "Please set it in your .env file: PURPLE_OPENROUTER_API_KEY or OPENROUTER_API_KEY=your-key-here\n"
                "Get a free API key at: https://openrouter.ai/keys"
            )
        
        client = AsyncOpenAI(
            api_key=config.openrouter_api_key,
            base_url=config.openrouter_base_url,
            default_headers={
                "HTTP-Referer": "https://github.com/weag-project",
                "X-Title": "WEAG Purple Agent"
            }
        )
        
        model_name = config.litellm_model
        
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(
            f"⚠ Purple Agent LiteLLM: Using fallback AsyncOpenAI client with model='{model_name}'. "
            "For OpenAI Agents SDK, use LLMClientFactory.create_litellm_model() instead."
        )
        
        return client, model_name


def setup_llm_client(config: Optional[LLMConfig] = None, prefix: str = "PURPLE_") -> tuple[Optional[AsyncOpenAI], Union[str, Any], LLMConfig]:
    """
    Setup LLM client with configuration for Purple Agent.
    
    For OpenAI and Gemini: Returns (client, model_name, config)
    For LiteLLM: Returns (None, LitellmModel, config) - use LitellmModel as Agent.model
    
    Args:
        config: LLM configuration (if None, loads from environment with PURPLE_ prefix)
        prefix: Environment variable prefix (default: "PURPLE_")
        
    Returns:
        Tuple of (client_or_none, model_name_or_litellm_model, config)
    """
    if config is None:
        config = LLMConfig.from_env(prefix)
    
    # For LiteLLM, use LitellmModel which handles routing correctly
    if config.provider == LLMProvider.LITELLM:
        litellm_model = LLMClientFactory.create_litellm_model(config)
        return None, litellm_model, config
    
    # For OpenAI/Gemini, use standard AsyncOpenAI client
    client, model_name = LLMClientFactory.create_client(config)
    return client, model_name, config


__all__ = [
    "LLMProvider",
    "LLMConfig",
    "LLMClientFactory",
    "setup_llm_client",
]
