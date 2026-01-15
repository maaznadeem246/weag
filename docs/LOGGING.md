# Logging Configuration

The Green Agent supports two logging modes for flexibility during development and production.

## Logging Modes

### 1. Pretty Console Output (Default)
**Best for:** Development, debugging, watching evaluations

Colorful formatted output with visual boxes showing BrowserGym SDK responses:

```
[INFO] 07:25:02 | +==================================================================+
                   |  >>> ACTION 1/1 COMPLETED - BrowserGym SDK Response <<<  |
                   +==================================================================+
                   |  REWARD:     1.0000   (from env.step() - authentic)        |
                   |  DONE:       True     (task goal achieved by SDK)          |
                   |  TRUNCATED:  False    (max steps reached?)               |
                   |  LATENCY:    1835.0ms                                    |
                   +==================================================================+
```

**Color Coding:**
- `REWARD:` - Bright Yellow
- `DONE:` - Bright Green
- `[SUCCESS]` - Bold Bright Green
- `BrowserGym SDK` - Bold Bright Cyan
- `ERROR` logs - Bright Red

**Enable:**
```powershell
# Default mode (no env variable needed)
E:/Maaz/Projects/weag/.venv/Scripts/python.exe scripts/kickstart_assessment.py --task miniwob.click-test

# Or explicitly set
$env:LOG_FORMAT="pretty"
E:/Maaz/Projects/weag/.venv/Scripts/python.exe scripts/kickstart_assessment.py --task miniwob.click-test
```

### 2. JSON Structured Logging
**Best for:** Production, log aggregation, automated analysis

JSON output with structured fields for observability tools:

```json
{"timestamp": "2026-01-09T07:25:02.564565Z", "level": "INFO", "logger": "src.green_agent.environment.action_executor", "message": "+==================================================================+\n|  >>> ACTION 1/1 COMPLETED - BrowserGym SDK Response <<<  |\n+==================================================================+", "latency_ms": 1835.0424766540527, "source": "BrowserGym_SDK"}
```

**Enable:**
```powershell
$env:LOG_FORMAT="json"
E:/Maaz/Projects/weag/.venv/Scripts/python.exe scripts/kickstart_assessment.py --task miniwob.click-test
```

## File Logging

Both modes automatically write JSON logs to `logs/green_agent.log` (if `logs/` directory exists).

**Benefits:**
- Persistent structured logs for analysis
- JSON format for easy parsing
- Separate from console output

## Log Levels

Control verbosity via `LOG_LEVEL` environment variable:

```powershell
# Debug mode (all logs)
$env:LOG_LEVEL="DEBUG"

# Info mode (default)
$env:LOG_LEVEL="INFO"

# Warning mode (errors + warnings only)
$env:LOG_LEVEL="WARNING"

# Error mode (errors only)
$env:LOG_LEVEL="ERROR"
```

## SDK Response Highlighting

The logger automatically highlights **BrowserGym SDK responses** to confirm authenticity:

**Keywords highlighted:**
- `BrowserGym SDK` - Indicates values come from SDK, not LLM
- `env.step()` - Direct environment call
- `REWARD:` / `DONE:` / `TRUNCATED:` - SDK return values
- `[SUCCESS]` - Task completion confirmed by SDK

This makes it easy to verify that task success is determined by the official BrowserGym benchmark, not by LLM judgement.

## Examples

### Development Workflow
```powershell
# Pretty colored output for watching agent behavior
E:/Maaz/Projects/weag/.venv/Scripts/python.exe scripts/kickstart_assessment.py --task miniwob.click-test --visible
```

### Production/CI Pipeline
```powershell
# JSON output for log aggregation
$env:LOG_FORMAT="json"
E:/Maaz/Projects/weag/.venv/Scripts/python.exe scripts/kickstart_assessment.py --task miniwob.click-test --output results.json
```

### Debugging
```powershell
# Debug logs with colors
$env:LOG_LEVEL="DEBUG"
E:/Maaz/Projects/weag/.venv/Scripts/python.exe scripts/kickstart_assessment.py --task miniwob.click-test --visible
```

## Integration with Langfuse

Structured logging complements Langfuse tracing:
- **Console/File logs**: Low-level execution details (actions, observations, SDK responses)
- **Langfuse traces**: High-level agent decisions, LLM calls, tool usage

Both are enabled by default for comprehensive observability.
