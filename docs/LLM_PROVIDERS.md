# LLM Provider Configuration Guide

This project supports multiple LLM providers through a unified abstraction layer.

## Supported Providers

1. **Google Gemini** (default) - Direct API
2. **OpenAI** - Official API
3. **LiteLLM/OpenRouter** - Access to multiple models via OpenRouter

## Configuration

Set environment variables in `.env` file or export them in your shell.

### Provider Selection

```bash
# Choose provider (default: gemini)
LLM_PROVIDER=gemini  # Options: openai, gemini, litellm
```

### API Keys

```bash
# Google Gemini (required if LLM_PROVIDER=gemini - DEFAULT)
# Get free API key at: https://aistudio.google.com/apikey
GEMINI_API_KEY=AIzaSy...

# OpenAI (required if LLM_PROVIDER=openai)
# Get API key at: https://platform.openai.com/api-keys
OPENAI_API_KEY=sk-...

# OpenRouter (required if LLM_PROVIDER=litellm)
# Get free API key at: https://openrouter.ai/keys
OPENROUTER_API_KEY=sk-or-v1-...
```

### Model Configuration

```bash
# Model names (per provider)
OPENAI_MODEL=gpt-4o                              # OpenAI model
GEMINI_MODEL=gemini-2.5-flash                    # Gemini model
LITELLM_MODEL=google/gemini-2.0-flash-exp:free   # LiteLLM model (provider/model format)

# Model settings
LLM_TEMPERATURE=0.1                              # 0.0 to 2.0
LLM_MAX_ITERATIONS=50                            # Max agent iterations
```

## Provider Examples

### 1. Google Gemini (Default)

```bash
LLM_PROVIDER=gemini
GEMINI_API_KEY=AIzaSyCKH8hihbwuEJ546zCBBW_Xzp4Ca05zz2o
GEMINI_MODEL=gemini-2.5-flash
LLM_TEMPERATURE=0.1
```

**Pros:**
- Free tier available
- Fast inference
- Good performance
- Cost-effective

**Cons:**
- Rate limits on free tier
- Limited quota per day

### 2. OpenAI Official

```bash
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-proj-...
OPENAI_MODEL=gpt-4o
LLM_TEMPERATURE=0.1
```

**Pros:**
- Most reliable
- Best performance
- Higher rate limits

**Cons:**
- Costs money ($)
- Requires paid account

### 3. LiteLLM via OpenRouter

```bash
LLM_PROVIDER=litellm
OPENROUTER_API_KEY=sk-or-v1-...
LITELLM_MODEL=google/gemini-2.0-flash-exp:free
LLM_TEMPERATURE=0.1
```

**Pros:**
- Access to multiple providers
- Some free models available
- Unified API
- No direct API keys needed

**Cons:**
- Adds latency (proxy layer)
- OpenRouter-specific rate limits
- Model availability varies

## OpenRouter Models

Popular models available via OpenRouter:

### Free Models
```bash
# Gemini Flash (fastest, free)
LITELLM_MODEL=google/gemini-2.0-flash-exp:free

# Gemini Pro (more capable, free)
LITELLM_MODEL=google/gemini-2.0-pro:free

# Mistral (free)
LITELLM_MODEL=mistralai/mistral-7b-instruct:free
```

### Paid Models (with OpenRouter credits)
```bash
# GPT-4 via OpenRouter
LITELLM_MODEL=openai/gpt-4o

# Claude via OpenRouter  
LITELLM_MODEL=anthropic/claude-3-5-sonnet

# Gemini (paid tier)
LITELLM_MODEL=google/gemini-2.5-flash
```

Full model list: https://openrouter.ai/models

## Getting API Keys

### Gemini API Key
1. Go to https://ai.google.dev/
2. Click "Get API Key"
3. Create API key in Google AI Studio
4. Copy key starting with `AIzaSy...`

### OpenAI API Key
1. Go to https://platform.openai.com/api-keys
2. Create new secret key
3. Copy key starting with `sk-proj-...`
4. Add payment method (paid service)

### OpenRouter API Key
1. Go to https://openrouter.ai/
2. Sign in with Google/GitHub
3. Go to Keys section
4. Create new API key
5. Copy key starting with `sk-or-v1-...`
6. Optionally add credits for paid models

## Quick Setup

### Default (Gemini Free)
```bash
# .env file
LLM_PROVIDER=gemini
GEMINI_API_KEY=AIzaSy...
```

### OpenRouter (Gemini via Proxy)
```bash
# .env file
LLM_PROVIDER=litellm
OPENROUTER_API_KEY=sk-or-v1-...
LITELLM_MODEL=google/gemini-2.0-flash-exp:free
```

### OpenAI (Paid, Most Reliable)
```bash
# .env file
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-proj-...
OPENAI_MODEL=gpt-4o
```

## Switching Providers

To switch providers, just change the `LLM_PROVIDER` environment variable and restart:

```bash
# Use Gemini
LLM_PROVIDER=gemini .\run.ps1

# Use OpenAI
LLM_PROVIDER=openai .\run.ps1

# Use OpenRouter
LLM_PROVIDER=litellm .\run.ps1
```

## Troubleshooting

### Rate Limit Errors (429)
- **Gemini**: Wait 1 minute or upgrade to paid tier
- **OpenRouter**: Check free tier limits, add credits
- **OpenAI**: Check billing, increase limits

### Authentication Errors (401)
- Verify API key is correct
- Check key hasn't expired
- Ensure key has proper permissions

### Model Not Found (404)
- Verify model name spelling
- Check model is available for your provider
- For OpenRouter: check https://openrouter.ai/models

### Connection Errors
- Check internet connection
- Verify base_url is correct
- Check firewall/proxy settings
