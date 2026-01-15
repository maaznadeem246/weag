# LLM Provider Abstraction Layer

## Overview

The WEAG project now supports multiple LLM providers through a unified abstraction layer in `src/common/llm_provider.py`. This allows easy switching between:

- **OpenAI Official** - GPT-4o, GPT-4, etc.
- **Google Gemini Official** - gemini-2.5-flash, gemini-2.0-flash-exp, etc.
- **LiteLLM/OpenRouter** - Access to multiple models via proxy (including Gemini, Claude, Mistral, etc.)

## Quick Start

### 1. Configure Provider

Edit `.env` file:

```bash
# Use Gemini (default, free tier available)
LLM_PROVIDER=gemini
GEMINI_API_KEY=AIzaSy...

# OR use OpenRouter for more options
LLM_PROVIDER=litellm
OPENROUTER_API_KEY=sk-or-v1-...
LITELLM_MODEL=google/gemini-2.0-flash-exp:free

# OR use OpenAI (paid)
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-proj-...
```

### 2. Run Assessment

```powershell
# Uses provider from .env
.\run.ps1

# Override provider via environment variable
$env:LLM_PROVIDER="litellm"; .\run.ps1
```

## Architecture

### Abstraction Layer

```
src/common/llm_provider.py
├── LLMProvider (enum)        # openai, gemini, litellm
├── LLMConfig (pydantic)      # Configuration management
├── LLMClientFactory          # Creates AsyncOpenAI clients
└── setup_llm_client()        # Main entry point
```

### Integration Points

Both agents use the abstraction layer:

**Purple Agent** (`src/purple_agent/agent/agent_factory.py`):
```python
from src.common import LLMConfig, setup_llm_client

llm_config = LLMConfig.from_env()
client, model_name, _ = setup_llm_client(llm_config)
set_default_openai_client(client)
```

**Green Agent** (`src/green_agent/agent/agent_factory.py`):
```python
from src.common import LLMConfig, setup_llm_client

llm_config = LLMConfig.from_env()
client, model_name, _ = setup_llm_client(llm_config)
set_default_openai_client(client)
```

## Configuration Options

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `LLM_PROVIDER` | Provider to use | `gemini` |
| `OPENAI_API_KEY` | OpenAI API key | - |
| `GEMINI_API_KEY` | Gemini API key | - |
| `OPENROUTER_API_KEY` | OpenRouter API key | - |
| `OPENAI_MODEL` | OpenAI model name | `gpt-4o` |
| `GEMINI_MODEL` | Gemini model name | `gemini-2.5-flash` |
| `LITELLM_MODEL` | LiteLLM model name | `google/gemini-2.0-flash-exp:free` |
| `LLM_TEMPERATURE` | Model temperature | `0.1` |
| `LLM_MAX_ITERATIONS` | Max agent iterations | `50` |

### Programmatic Configuration

```python
from src.common import LLMConfig, LLMProvider, setup_llm_client

# Create config programmatically
config = LLMConfig(
    provider=LLMProvider.LITELLM,
    openrouter_api_key="sk-or-v1-...",
    litellm_model="google/gemini-2.0-flash-exp:free",
    temperature=0.1,
)

# Setup client
client, model_name, _ = setup_llm_client(config)
```

## Provider Details

### OpenAI Official
- **Endpoint**: `https://api.openai.com/v1`
- **Models**: `gpt-4o`, `gpt-4-turbo`, `gpt-3.5-turbo`
- **Auth**: API key (`sk-proj-...`)
- **Cost**: Paid per token
- **Pros**: Most reliable, best performance
- **Cons**: Costs money

### Google Gemini Official
- **Endpoint**: `https://generativelanguage.googleapis.com/v1beta/openai/`
- **Models**: `gemini-2.5-flash`, `gemini-2.0-flash-exp`, `gemini-2.5-pro`
- **Auth**: API key (`AIzaSy...`)
- **Cost**: Free tier available
- **Pros**: Fast, cost-effective, good performance
- **Cons**: Rate limits on free tier

### LiteLLM/OpenRouter
- **Endpoint**: `https://openrouter.ai/api/v1`
- **Models**: 100+ models from multiple providers
- **Auth**: API key (`sk-or-v1-...`)
- **Cost**: Free tier + paid models
- **Pros**: Access to many models, unified API
- **Cons**: Added latency, proxy limitations

## Popular OpenRouter Models

```bash
# Free models
google/gemini-2.0-flash-exp:free      # Fast Gemini (recommended)
google/gemini-2.0-pro:free            # More capable Gemini
mistralai/mistral-7b-instruct:free    # Mistral alternative

# Paid models (with OpenRouter credits)
openai/gpt-4o                         # GPT-4 via proxy
anthropic/claude-3-5-sonnet           # Claude 3.5
google/gemini-2.5-flash               # Paid Gemini tier
```

Full list: https://openrouter.ai/models

## Examples

### Switch to OpenRouter

```bash
# Get OpenRouter API key from https://openrouter.ai/
echo 'LLM_PROVIDER=litellm' >> .env
echo 'OPENROUTER_API_KEY=sk-or-v1-...' >> .env
echo 'LITELLM_MODEL=google/gemini-2.0-flash-exp:free' >> .env

# Run assessment
.\run.ps1
```

### Use OpenAI

```bash
# Get OpenAI API key from https://platform.openai.com/api-keys
echo 'LLM_PROVIDER=openai' >> .env
echo 'OPENAI_API_KEY=sk-proj-...' >> .env
echo 'OPENAI_MODEL=gpt-4o' >> .env

# Run assessment
.\run.ps1
```

### Test Different Providers

```powershell
# Test with Gemini (default)
$env:LLM_PROVIDER="gemini"; E:/Maaz/Projects/weag/.venv/Scripts/python.exe scripts/kickstart_assessment.py

# Test with OpenRouter
$env:LLM_PROVIDER="litellm"; $env:OPENROUTER_API_KEY="sk-or-v1-..."; E:/Maaz/Projects/weag/.venv/Scripts/python.exe scripts/kickstart_assessment.py

# Test with OpenAI
$env:LLM_PROVIDER="openai"; $env:OPENAI_API_KEY="sk-proj-..."; E:/Maaz/Projects/weag/.venv/Scripts/python.exe scripts/kickstart_assessment.py
```

## Benefits

✅ **Easy Switching** - Change provider with one environment variable
✅ **Cost Optimization** - Use free tiers during development, paid tiers for production
✅ **Redundancy** - Fallback to different provider if one has issues
✅ **Model Flexibility** - Access to 100+ models via OpenRouter
✅ **Unified Interface** - Same code works with all providers
✅ **Type Safety** - Pydantic validation for configuration

## See Also

- [Full LLM Provider Guide](docs/LLM_PROVIDERS.md)
- [OpenRouter Models](https://openrouter.ai/models)
- [Gemini API Docs](https://ai.google.dev/)
- [OpenAI API Docs](https://platform.openai.com/docs)
