# AGENTS.md

This document provides guidance for AI coding agents working on the **WEAG (Web Environment Agent Green)** project - a Green Agent implementation for the AgentBeats platform.

## ⚠️ CRITICAL: Context7 MCP Server Usage

**AI Agents: You MUST use the Context7 MCP server before implementing any code!**

- **Always** search official documentation via Context7 (`mcp_upstash_conte_query-docs`) before writing code for libraries or frameworks.
- **Do not** rely solely on your training data; libraries change, and Context7 provides the most up-to-date API references.
- **Workflow:**
  1.  Identify the library or framework you need to use (e.g., Langfuse, OpenAI Agents SDK, BrowserGym).
  2.  Use `mcp_upstash_conte_resolve-library-id` to find the correct library ID.
  3.  Use `mcp_upstash_conte_query-docs` to fetch relevant documentation and code examples.
  4.  **Only then** proceed with implementation based on the retrieved docs.

## 🎯 Code Quality Philosophy

**This project is built for competition submission AND learning - deliver production-grade, competition-winning code!**

### Core Principles:
1. **Simple & Concise**: Write minimal, elegant code that solves problems correctly - complexity is not sophistication
2. **Industry Standard**: Follow official documentation patterns and idiomatic code style used in production systems
3. **Production-Ready**: Code must be reliable, maintainable, and performant enough for real-world deployment
4. **Well-Documented**: Clear docstrings, inline comments for complex logic, comprehensive README files
5. **Context7 First**: Always verify implementation against latest official documentation - avoid outdated patterns
6. **Competition-Grade**: Code quality, architecture, and documentation should demonstrate professional engineering standards
7. **Reuse Before Creating**: Always check if existing code can be reused before writing new implementations - confirm with user when unsure

### What to AVOID:
- ❌ Over-engineering with unnecessary design patterns and abstractions
- ❌ Complex inheritance hierarchies when composition or simple functions suffice
- ❌ Custom implementations when battle-tested standard library methods exist
- ❌ Clever one-liners that sacrifice readability for brevity
- ❌ Premature optimization without profiling or benchmarking
- ❌ Incomplete error handling or missing edge case coverage
- ❌ Poor naming conventions (use descriptive names, not abbreviations)

### What to DO:
- ✅ Use official SDK patterns from Context7 documentation (latest stable versions)
- ✅ Prefer built-in methods and standard library functions (proven reliability)
- ✅ Write clear, linear code flow with minimal nesting (easy to debug)
- ✅ Add comprehensive docstrings with args, returns, raises, and examples
- ✅ Keep functions small and focused (single responsibility principle)
- ✅ Use type hints everywhere for IDE support, static analysis, and clarity
- ✅ Handle errors gracefully with specific exception types and meaningful messages
- ✅ Include logging at appropriate levels (debug, info, warning, error)
- ✅ Write testable code with dependency injection where appropriate
- ✅ Follow PEP 8 style guide and use consistent formatting
- ✅ **Reuse existing code**: Search codebase for similar functionality before implementing new code
- ✅ **Ask before duplicating**: If unsure whether to reuse or create new code, confirm with user first

### Code Quality Standards:
1. **Correctness**: Code must work reliably under all expected conditions
2. **Clarity**: Anyone reading the code should understand it quickly
3. **Efficiency**: Use appropriate algorithms and data structures (no premature optimization)
4. **Robustness**: Handle edge cases, validate inputs, provide useful error messages
5. **Maintainability**: Code should be easy to modify and extend
6. **Testability**: Write code that can be easily unit tested and integration tested

### Example - Simple vs Over-engineered:

**❌ Over-engineered (unnecessarily complex):**
```python
class ObservationProcessorFactory:
    @staticmethod
    def create_processor(strategy: str) -> AbstractProcessor:
        return ProcessorRegistry.get(strategy)()

class ObservationProcessor(ABC):
    @abstractmethod
    def process(self, obs: dict) -> dict:
        pass
```

**✅ Simple & Production-Ready (clear, tested, documented):**
```python
def parse_observation(obs: dict) -> dict:
    """
    Extract clickable elements and text from BrowserGym observation.
    
    Args:
        obs: Raw observation dict with 'axtree_txt' and 'text' fields
        
    Returns:
        Parsed observation with clickable elements and page text
        
    Raises:
        ValueError: If observation format is invalid
        
    Example:
        >>> obs = {"axtree_txt": "[1] button 'Click'\n[2] link 'Home'", "text": "Welcome"}
        >>> result = parse_observation(obs)
        >>> result['clickable']
        ['[1] button \'Click\'', '[2] link \'Home\'']
    """
    if not isinstance(obs, dict):
        raise ValueError(f"Expected dict, got {type(obs)}")
    
    return {
        "clickable": obs.get("axtree_txt", "").split("\n"),
        "text": obs.get("text", "")
    }
```

### Competition Submission Guidelines:
- **Code Quality**: Judges will evaluate code readability, structure, and best practices
- **Documentation**: README, inline comments, and docstrings should be comprehensive
- **Testing**: Include unit tests and integration tests where appropriate
- **Performance**: Optimize critical paths, but avoid premature optimization
- **Innovation**: Use modern patterns and tools appropriately (don't overdo it)
- **Reproducibility**: Clear setup instructions, dependency management, environment files

## ⚠️ CRITICAL: Environment Variables and Secrets Management

**AI Agents: DO NOT read, write, or modify `.env` files!**

- `.env` files contain sensitive credentials (API keys, secrets)
- User manages their own `.env` file configuration
- **Never** use tools to read `.env` file contents
- **Never** create or modify `.env` files
- **Never** display API keys or secrets in responses
- If you need to know what environment variables are available, refer to `.env.example` file instead
- The user will set their own environment variables - assume they are configured correctly

**What you CAN do:**
- ✅ Read `.env.example` to understand what variables are needed
- ✅ Reference environment variable names in code (e.g., `os.environ.get("LANGFUSE_PUBLIC_KEY")`)
- ✅ Update documentation about environment variables
- ✅ Modify code that uses `os.environ` to read environment variables

**What you MUST NOT do:**
- ❌ Read or display contents of `.env` files
- ❌ Create or modify `.env` files
- ❌ Ask user for API keys or secrets
- ❌ Display API keys or secrets in console output or logs

## Project Overview

This project contains a **complete A2A assessment system** with both Green and Purple agents:

**Green Agent** (Evaluator/Orchestrator):
- Manages and orchestrates evaluations of purple agents (participants)
- Provides an evaluation harness for benchmarking
- Spawns MCP server for BrowserGym environment access
- Communicates via the A2A protocol (Agent-to-Agent)

**Purple Agent** (Test Participant):
- Minimal reference implementation using OpenAI Agents SDK
- Connects to Green Agent via A2A protocol
- Executes tasks using MCP tools from Green Agent
- Submits evaluation artifacts back to Green Agent


#### Key Technologies
- **OpenAI Agents SDK** (v0.2.9+): Agent orchestration with tools (@function_tool), guardrails (@input_guardrail/@output_guardrail), sessions (SQLiteSession/InMemorySession), RunContextWrapper[T] for context
- **Langfuse**: Tracing via @observe decorator, OpenAI wrapper, update_current_span/trace APIs
- **Gemini 2.5 Flash**: Cost-effective LLM ($0.001-0.05/eval) via OpenAI-compatible API (base_url config)
- **Architecture**: Single-agent (no handoffs), context-aware tools, agent-based guardrails, SQLAlchemy sessions, SSE streaming integration

## Resources Folder

The `resources/` folder contains critical reference documentation:

### Available Documentation
1. **`agentbeats-tutorial-github.txt`** - Complete AgentBeats tutorial including:
   - Core concepts (Green agents, Purple agents, A2A protocol)
   - Debate example implementation (DebateJudge green agent + Debater purple agents)
   - Green agent development patterns (artifact submission, traced environment, message-based, multi-agent games)
   - Best practices for API key management, efficient communication, and reproducibility
   - Dockerization guide for agents
   - Full code examples from the official tutorial repository

2. **`browsergym-demoagent.txt`** - Example from the official BrowserGym benchmark:
   - Demonstrates how a demo agent interacts with web browsers
   - Useful for understanding observation preprocessing (HTML, AXTree, screenshots)
   - Shows integration with Playwright for browser automation
   - Note: This is a benchmark example, not our Purple Agent implementation

3. **`RESEARCH_AND_PLAN.md`** - Extended research notes and planning decisions
4. **`RESOURCES.md`** - Commands, dependencies, and benchmarks reference

## Architecture Summary

**Complete A2A System**:
- **Green Agent (A2A Server)** - Port 9009: Handles Agent-to-Agent protocol orchestration, manages evaluation lifecycle
- **Green Agent (MCP Server)** - Subprocess: Exposes 4 environment tools via stdio for BrowserGym interaction
- **Purple Agent (A2A Client)** - One-shot executor: Connects to Green Agent, receives MCP details, executes tasks

**A2A Communication Flow**:
1. Kickstart script starts both Green and Purple agents
2. Purple Agent sends evaluation request to Green Agent via A2A
3. Green Agent spawns MCP server and sends connection details back via A2A
4. Purple Agent connects to MCP server and executes task
5. Purple Agent submits evaluation artifact to Green Agent via A2A
6. Kickstart script monitors completion and exports results

**Key Components**:
- `src/green_agent/main.py` - A2A server and orchestration
    - **Multi-Task Mode**: LLM-orchestrated with programmatic prompting
    - LLM calls tools via `Runner.run()` in a loop with session continuity
    - Programmatic `internal_system` messages ensure all tasks are processed
- `src/green_agent/mcp_server.py` - MCP server with FastMCP (4 tools)
- `src/green_agent/environment/` - BrowserGym environment management (6 benchmarks)
- `src/green_agent/metrics/` - Efficiency tracking (C/L/F mandates)
- `src/purple_agent/main.py` - Purple agent entry point with A2A client
- `src/purple_agent/agent/` - OpenAI Agents SDK implementation (7 agent tools)
- `scripts/kickstart_assessment.py` - Complete assessment orchestration
- `src/green_agent/agent/tools/multi_task_tools.py` - 4 multi-task orchestration tools called by LLM

**Supported Benchmarks**: miniwob, webarena, visualwebarena, workarena, assistantbench, weblinx


### Quick Start

**Virtual Environment Setup**:
```powershell
# Windows PowerShell - Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Linux/macOS - Activate virtual environment
source .venv/bin/activate
```



## AI Agent Terminal Usage Guidelines

**CRITICAL**: This project uses a Python virtual environment (`.venv`). 

### ⚠️ MANDATORY: Always Activate Environment First!

**AI Agents MUST activate the virtual environment before running ANY Python command.**

```powershell
# Windows PowerShell - ALWAYS run this first in each terminal session
.\.venv\Scripts\Activate.ps1

# Then run your commands
python kickstart_assessment.py --task miniwob.click-test
python -m src.green_agent.main
pytest tests/unit/ -v
```

**Why activation is required:**
- ✅ Ensures correct Python interpreter is used
- ✅ All installed packages are available
- ✅ Environment variables from .env are loaded correctly
- ✅ Consistent behavior across all commands

### Method 1: Activate + Run (REQUIRED for AI Agents)
```powershell
# Step 1: ALWAYS activate first
.\.venv\Scripts\Activate.ps1

# Step 2: Verify activation (prompt shows "(.venv)" or "(weag)")
# ✅ Activated prompt: (.venv) PS E:\Maaz\Projects\weag>

# Step 3: Run commands
python kickstart_assessment.py --task miniwob.click-test --headless
python -m pytest tests/unit/ -v
```

### Method 2: Full Python Path (Alternative - NO activation needed)
Use when activation is not possible:
```powershell
# Windows - Use full path (NO activation needed)
E:/Maaz/Projects/weag/.venv/Scripts/python.exe kickstart_assessment.py --task miniwob.click-test
E:/Maaz/Projects/weag/.venv/Scripts/python.exe -m src.green_agent.main
E:/Maaz/Projects/weag/.venv/Scripts/python.exe -m pytest tests/unit/ -v
```

### Quick Reference Commands

**Important**: All examples below assume the user has configured their `.env` file with necessary credentials (GEMINI_API_KEY, LANGFUSE_PUBLIC_KEY, etc.). AI agents should NOT set these variables manually.

**Run Complete Assessment (Kickstart Script - Both Agents):**
```powershell
# Complete A2A assessment with Green + Purple agents
# Purple Agent connects to Green Agent via A2A automatically

# Headless mode (default)
E:/Maaz/Projects/weag/.venv/Scripts/python.exe scripts/kickstart_assessment.py --task miniwob.click-test --output results.json

# Visible browser mode (for debugging)
E:/Maaz/Projects/weag/.venv/Scripts/python.exe scripts/kickstart_assessment.py --task miniwob.click-test --visible

# With custom timeout
E:/Maaz/Projects/weag/.venv/Scripts/python.exe scripts/kickstart_assessment.py --task miniwob.click-test --timeout 120
```

**Run Green Agent Server Only:**
```powershell
# Green agent auto-configures MINIWOB_URL from green-agent/datasets/miniwob/
# No manual setup needed - just run:
E:/Maaz/Projects/weag/.venv/Scripts/python.exe -m src.green_agent.main
```

