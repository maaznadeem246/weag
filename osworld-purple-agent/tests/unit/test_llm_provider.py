"""
Unit tests for LLMConfig.from_env() — all three providers, missing key validation,
and invalid provider fallback.  No real API calls — env vars are mocked only.
"""

import pytest
from unittest.mock import patch

# Import the module under test.
from src.llm_provider import LLMConfig, LLMProvider


def _env(**kwargs):
    """Return an os.environ patch dict with only the provided keys set."""
    return patch.dict("os.environ", kwargs, clear=True)


class TestLLMConfigOpenAI:
    """LLMConfig.from_env() with provider=openai."""

    def test_provider_set_correctly(self):
        with _env(OSWORLD_LLM_PROVIDER="openai", OSWORLD_OPENAI_API_KEY="sk-test"):
            cfg = LLMConfig.from_env("OSWORLD_")
        assert cfg.provider == LLMProvider.OPENAI

    def test_api_key_loaded(self):
        with _env(OSWORLD_LLM_PROVIDER="openai", OSWORLD_OPENAI_API_KEY="sk-test"):
            cfg = LLMConfig.from_env("OSWORLD_")
        assert cfg.openai_api_key == "sk-test"

    def test_model_default(self):
        with _env(OSWORLD_LLM_PROVIDER="openai", OSWORLD_OPENAI_API_KEY="sk-xyz"):
            cfg = LLMConfig.from_env("OSWORLD_")
        assert cfg.openai_model == "gpt-4o"

    def test_model_override(self):
        with _env(
            OSWORLD_LLM_PROVIDER="openai",
            OSWORLD_OPENAI_API_KEY="sk-xyz",
            OSWORLD_OPENAI_MODEL="gpt-4-turbo",
        ):
            cfg = LLMConfig.from_env("OSWORLD_")
        assert cfg.openai_model == "gpt-4-turbo"

    def test_unprefixed_key_fallback(self):
        """Unprefixed OPENAI_API_KEY used when OSWORLD_ variant absent."""
        with _env(OSWORLD_LLM_PROVIDER="openai", OPENAI_API_KEY="sk-fallback"):
            cfg = LLMConfig.from_env("OSWORLD_")
        assert cfg.openai_api_key == "sk-fallback"

    def test_prefixed_key_wins_over_unprefixed(self):
        with _env(
            OSWORLD_LLM_PROVIDER="openai",
            OSWORLD_OPENAI_API_KEY="sk-prefixed",
            OPENAI_API_KEY="sk-fallback",
        ):
            cfg = LLMConfig.from_env("OSWORLD_")
        assert cfg.openai_api_key == "sk-prefixed"


class TestLLMConfigGemini:
    """LLMConfig.from_env() with provider=gemini."""

    def test_provider_set_correctly(self):
        with _env(OSWORLD_LLM_PROVIDER="gemini", OSWORLD_GEMINI_API_KEY="g-key"):
            cfg = LLMConfig.from_env("OSWORLD_")
        assert cfg.provider == LLMProvider.GEMINI

    def test_api_key_loaded(self):
        with _env(OSWORLD_LLM_PROVIDER="gemini", OSWORLD_GEMINI_API_KEY="g-key"):
            cfg = LLMConfig.from_env("OSWORLD_")
        assert cfg.gemini_api_key == "g-key"

    def test_model_default(self):
        with _env(OSWORLD_LLM_PROVIDER="gemini", OSWORLD_GEMINI_API_KEY="g-key"):
            cfg = LLMConfig.from_env("OSWORLD_")
        assert cfg.gemini_model == "gemini-2.5-flash"

    def test_model_override(self):
        with _env(
            OSWORLD_LLM_PROVIDER="gemini",
            OSWORLD_GEMINI_API_KEY="g-key",
            OSWORLD_GEMINI_MODEL="gemini-1.5-pro",
        ):
            cfg = LLMConfig.from_env("OSWORLD_")
        assert cfg.gemini_model == "gemini-1.5-pro"


class TestLLMConfigLiteLLM:
    """LLMConfig.from_env() with provider=litellm (default)."""

    def test_default_provider_is_litellm(self):
        """No OSWORLD_LLM_PROVIDER set → defaults to litellm."""
        with _env():
            cfg = LLMConfig.from_env("OSWORLD_")
        assert cfg.provider == LLMProvider.LITELLM

    def test_explicit_litellm(self):
        with _env(OSWORLD_LLM_PROVIDER="litellm", OSWORLD_OPENROUTER_API_KEY="or-key"):
            cfg = LLMConfig.from_env("OSWORLD_")
        assert cfg.provider == LLMProvider.LITELLM

    def test_api_key_loaded(self):
        with _env(OSWORLD_LLM_PROVIDER="litellm", OSWORLD_OPENROUTER_API_KEY="or-key"):
            cfg = LLMConfig.from_env("OSWORLD_")
        assert cfg.openrouter_api_key == "or-key"

    def test_model_default(self):
        with _env(OSWORLD_OPENROUTER_API_KEY="or-key"):
            cfg = LLMConfig.from_env("OSWORLD_")
        assert cfg.litellm_model == "google/gemini-2.0-flash-exp:free"

    def test_model_override(self):
        with _env(
            OSWORLD_OPENROUTER_API_KEY="or-key",
            OSWORLD_LITELLM_MODEL="anthropic/claude-3-5-sonnet",
        ):
            cfg = LLMConfig.from_env("OSWORLD_")
        assert cfg.litellm_model == "anthropic/claude-3-5-sonnet"


class TestLLMConfigInvalidProvider:
    """Invalid or missing provider values fall back to litellm."""

    def test_invalid_string_falls_back_to_litellm(self):
        with _env(OSWORLD_LLM_PROVIDER="gpt99"):
            cfg = LLMConfig.from_env("OSWORLD_")
        assert cfg.provider == LLMProvider.LITELLM

    def test_empty_string_falls_back_to_litellm(self):
        with _env(OSWORLD_LLM_PROVIDER=""):
            cfg = LLMConfig.from_env("OSWORLD_")
        assert cfg.provider == LLMProvider.LITELLM

    def test_case_insensitive_provider(self):
        """Provider string is lowercased before parsing."""
        with _env(OSWORLD_LLM_PROVIDER="OpenAI", OSWORLD_OPENAI_API_KEY="sk-x"):
            cfg = LLMConfig.from_env("OSWORLD_")
        assert cfg.provider == LLMProvider.OPENAI


class TestMissingAPIKeyValidation:
    """Missing required API keys raise ValueError from LLMClientFactory."""

    def test_openai_missing_key_raises(self):
        from src.llm_provider import LLMClientFactory

        cfg = LLMConfig(provider=LLMProvider.OPENAI, openai_api_key=None)
        with pytest.raises(ValueError, match="OPENAI_API_KEY"):
            LLMClientFactory.create_client(cfg)

    def test_gemini_missing_key_raises(self):
        from src.llm_provider import LLMClientFactory

        cfg = LLMConfig(provider=LLMProvider.GEMINI, gemini_api_key=None)
        with pytest.raises(ValueError, match="GEMINI_API_KEY"):
            LLMClientFactory.create_client(cfg)

    def test_litellm_missing_key_raises(self):
        from src.llm_provider import LLMClientFactory

        cfg = LLMConfig(provider=LLMProvider.LITELLM, openrouter_api_key=None)
        with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
            LLMClientFactory.create_litellm_model(cfg)


class TestMaxIterations:
    """max_iterations is loaded from env."""

    def test_default(self):
        with _env():
            cfg = LLMConfig.from_env("OSWORLD_")
        assert cfg.max_iterations == 20

    def test_override(self):
        with _env(OSWORLD_LLM_MAX_ITERATIONS="10"):
            cfg = LLMConfig.from_env("OSWORLD_")
        assert cfg.max_iterations == 10
