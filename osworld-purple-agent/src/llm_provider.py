"""
LLM Provider Abstraction Layer for OSWorld Purple Agent.

Supports multiple LLM providers:
- OpenAI Official
- Google Gemini Official (via openai-compatible API)
- LiteLLM (OpenRouter for access to multiple models including Gemini)

Configuration via environment variables with OSWORLD_ prefix.

IMPORTANT: For OpenAI Agents SDK integration:
- OpenAI/Gemini: Use set_default_openai_client() with AsyncOpenAI
- LiteLLM: Use LitellmModel class directly on Agent (avoids "/" parsing issues)
"""

import logging
import os
from enum import Enum
from typing import Any, Optional, Union

from openai import AsyncOpenAI
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class LLMProvider(str, Enum):
    """Supported LLM providers."""

    OPENAI = "openai"
    GEMINI = "gemini"
    LITELLM = "litellm"  # OpenRouter via LiteLLM


class LLMConfig(BaseModel):
    """Configuration for LLM provider."""

    provider: LLMProvider = Field(
        default=LLMProvider.LITELLM,
        description="LLM provider to use",
    )

    # API Keys
    openai_api_key: Optional[str] = Field(default=None)
    gemini_api_key: Optional[str] = Field(default=None)
    openrouter_api_key: Optional[str] = Field(default=None)

    # Model names
    openai_model: str = Field(default="gpt-4o")
    gemini_model: str = Field(default="gemini-2.5-flash")
    litellm_model: str = Field(default="google/gemini-2.0-flash-exp:free")

    # Base URLs
    gemini_base_url: str = Field(
        default="https://generativelanguage.googleapis.com/v1beta/openai/"
    )
    openrouter_base_url: str = Field(default="https://openrouter.ai/api/v1")

    max_iterations: int = Field(default=20, ge=1, le=100)

    @classmethod
    def from_env(cls, prefix: str = "OSWORLD_") -> "LLMConfig":
        """
        Create configuration from environment variables for OSWorld Purple Agent.

        OSWORLD_-prefixed values win when provided; falls back to unprefixed values.
        Invalid provider strings silently fall back to 'litellm'.

        Args:
            prefix: Environment variable prefix (default: 'OSWORLD_')

        Returns:
            Populated LLMConfig instance.
        """

        def _get(key: str, default: Optional[str] = None) -> Optional[str]:
            prefixed = os.getenv(f"{prefix}{key}") if prefix else None
            if prefixed not in (None, ""):
                return prefixed
            fallback = os.getenv(key, default)
            return default if fallback in (None, "") else fallback

        provider_str = (_get("LLM_PROVIDER", "litellm") or "litellm").lower()
        try:
            provider = LLMProvider(provider_str)
        except ValueError:
            logger.warning(
                "Unknown OSWORLD_LLM_PROVIDER=%r — falling back to 'litellm'",
                provider_str,
            )
            provider = LLMProvider.LITELLM

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

        Args:
            config: LLM configuration.

        Returns:
            Tuple of (AsyncOpenAI client, model name string).

        Raises:
            ValueError: If required API key is missing.
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

        This is the RECOMMENDED approach for OpenRouter/LiteLLM — avoids '/'
        parsing issues in the SDK.

        Args:
            config: LLM configuration (must have provider=LITELLM).

        Returns:
            LitellmModel instance for use as Agent.model.

        Raises:
            ValueError: If OPENROUTER_API_KEY is missing.
            ImportError: If openai-agents[litellm] is not installed.
        """
        if not config.openrouter_api_key:
            raise ValueError(
                "OPENROUTER_API_KEY is required for LiteLLM provider.\n"
                "Set OSWORLD_OPENROUTER_API_KEY or OPENROUTER_API_KEY in .env.\n"
                "Get a free key at: https://openrouter.ai/keys"
            )

        try:
            from agents.extensions.models.litellm_model import LitellmModel
        except ImportError as exc:
            raise ImportError(
                "LitellmModel requires openai-agents[litellm].\n"
                "Install with: pip install 'openai-agents[litellm]'"
            ) from exc

        model_name = config.litellm_model
        if model_name.startswith("litellm/"):
            model_name = model_name[len("litellm/"):]
        if not model_name.startswith("openrouter/"):
            model_name = f"openrouter/{model_name}"

        return LitellmModel(model=model_name, api_key=config.openrouter_api_key)

    @staticmethod
    def _create_openai_client(config: LLMConfig) -> tuple[AsyncOpenAI, str]:
        if not config.openai_api_key:
            raise ValueError(
                "OPENAI_API_KEY is required for OpenAI provider.\n"
                "Set OSWORLD_OPENAI_API_KEY or OPENAI_API_KEY in .env."
            )
        return AsyncOpenAI(api_key=config.openai_api_key), config.openai_model

    @staticmethod
    def _create_gemini_client(config: LLMConfig) -> tuple[AsyncOpenAI, str]:
        if not config.gemini_api_key:
            raise ValueError(
                "GEMINI_API_KEY is required for Gemini provider.\n"
                "Set OSWORLD_GEMINI_API_KEY or GEMINI_API_KEY in .env.\n"
                "Get a free key at: https://aistudio.google.com/apikey"
            )
        client = AsyncOpenAI(
            api_key=config.gemini_api_key,
            base_url=config.gemini_base_url,
        )
        return client, config.gemini_model

    @staticmethod
    def _create_litellm_client(config: LLMConfig) -> tuple[AsyncOpenAI, str]:
        """Fallback AsyncOpenAI client for LiteLLM. Prefer create_litellm_model()."""
        if not config.openrouter_api_key:
            raise ValueError(
                "OPENROUTER_API_KEY is required for LiteLLM provider.\n"
                "Set OSWORLD_OPENROUTER_API_KEY or OPENROUTER_API_KEY in .env."
            )
        client = AsyncOpenAI(
            api_key=config.openrouter_api_key,
            base_url=config.openrouter_base_url,
            default_headers={
                "HTTP-Referer": "https://github.com/weag-project",
                "X-Title": "WEAG OSWorld Purple Agent",
            },
        )
        logger.warning(
            "OSWorld LiteLLM: using fallback AsyncOpenAI client for model=%r. "
            "Prefer LLMClientFactory.create_litellm_model() for the Agents SDK.",
            config.litellm_model,
        )
        return client, config.litellm_model


def setup_llm_client(
    config: Optional[LLMConfig] = None,
    prefix: str = "OSWORLD_",
) -> tuple[Optional[AsyncOpenAI], Union[str, Any], LLMConfig]:
    """
    Set up LLM client for the OSWorld Purple Agent.

    For OpenAI/Gemini: returns (AsyncOpenAI client, model_name, config).
    For LiteLLM: returns (None, LitellmModel, config) — use the model as Agent.model.

    Args:
        config: Pre-built LLMConfig, or None to load from env.
        prefix: Environment variable prefix (default: 'OSWORLD_').

    Returns:
        Tuple of (client_or_none, model_or_litellm_model, config).
    """
    if config is None:
        config = LLMConfig.from_env(prefix)

    if config.provider == LLMProvider.LITELLM:
        litellm_model = LLMClientFactory.create_litellm_model(config)
        return None, litellm_model, config

    client, model_name = LLMClientFactory.create_client(config)
    return client, model_name, config


__all__ = [
    "LLMProvider",
    "LLMConfig",
    "LLMClientFactory",
    "setup_llm_client",
]
