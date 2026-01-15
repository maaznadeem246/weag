"""
BROWSER VISIBILITY CONFIGURATION FLOW
======================================

This document traces how the headless/visible browser setting flows through the system.

CONFIGURATION FLOW:
==================

1. KICKSTART SCRIPT (scripts/kickstart_assessment.py)
   Line 231: env["BROWSER_HEADLESS"] = "true" if self.args.headless else "false"
   
   Default behavior (no --headless flag):
   - args.headless = False (action="store_true" defaults to False)
   - Sets: BROWSER_HEADLESS="false"
   
   With --headless flag:
   - args.headless = True
   - Sets: BROWSER_HEADLESS="true"

2. AGENT PROCESS START (scripts/kickstart_assessment.py)
   Line 73-76:
   ```python
   proc_env = os.environ.copy()  # Get parent environment
   if env:
       proc_env.update(env)  # Add BROWSER_HEADLESS="false"
   ```
   
   Result: Green Agent subprocess gets BROWSER_HEADLESS in its environment

3. GREEN AGENT SPAWNS MCP SERVER (src/green_agent/main.py)
   Line 428-434:
   ```python
   mcp_env = os.environ.copy()  # Green Agent's environment (includes BROWSER_HEADLESS)
   mcp_env["MCP_SESSION_ID"] = session_id
   mcp_env["BENCHMARK"] = benchmark
   
   if "BROWSER_HEADLESS" in os.environ:
       mcp_env["BROWSER_HEADLESS"] = os.environ["BROWSER_HEADLESS"]
   ```
   
   Result: MCP server subprocess gets BROWSER_HEADLESS="false"

4. MCP SERVER CREATES BROWSERGYM SESSION (src/green_agent/environment/session_manager.py)
   Line 117-122:
   ```python
   headless_env = os.environ.get("BROWSER_HEADLESS")  # Gets "false"
   if headless_env is None:
       headless = True  # Default if not set
   else:
       # "false" in ("0", "false", "no", "off") -> True
       # not True -> False
       headless = str(headless_env).lower() not in ("0", "false", "no", "off")
   ```
   
   When BROWSER_HEADLESS="false":
   - str("false").lower() = "false"
   - "false" not in ("0", "false", "no", "off") = False
   - headless = False ✅ (VISIBLE BROWSER)
   
   When BROWSER_HEADLESS="true":
   - str("true").lower() = "true"
   - "true" not in ("0", "false", "no", "off") = True
   - headless = True ✅ (HEADLESS BROWSER)

5. BROWSERGYM ENVIRONMENT CREATION (src/green_agent/environment/session_manager.py)
   Line 130-133:
   ```python
   env = gym.make(
       env_id,
       headless=headless,  # False for visible, True for headless
       **benchmark_config
   )
   ```
   
   Result: Browser opens in visible/headless mode based on configuration


VALIDATION VALUES:
==================

Values that make browser VISIBLE (headless=False):
- BROWSER_HEADLESS="false"
- BROWSER_HEADLESS="False"
- BROWSER_HEADLESS="no"
- BROWSER_HEADLESS="No"
- BROWSER_HEADLESS="0"
- BROWSER_HEADLESS="off"
- BROWSER_HEADLESS="Off"

Values that make browser HEADLESS (headless=True):
- BROWSER_HEADLESS="true"
- BROWSER_HEADLESS="True"
- BROWSER_HEADLESS="yes"
- BROWSER_HEADLESS="1"
- BROWSER_HEADLESS="on"
- Any other value
- Environment variable not set (defaults to True)


TROUBLESHOOTING:
===============

If browser is not visible when expected:

1. Check kickstart script logs for:
   "Setting BROWSER_HEADLESS=false (headless mode: False)"
   
2. Check Green Agent logs for:
   "Passing BROWSER_HEADLESS=false to MCP server"
   
3. Check session_manager logs for:
   "BROWSER_HEADLESS='false' -> headless=False"
   "Browser headless mode: False (BROWSER_HEADLESS=false)"

4. Common issues:
   - Gemini API rate limits (429 errors) cause quick failures
   - Browser opens but task fails immediately, so you don't see it
   - MCP server subprocess not getting environment variable


TESTING:
========

Test browser visibility without API calls:
```powershell
E:/Maaz/Projects/weag/.venv/Scripts/python.exe scripts/test_browser_visible.py
```

This will open a browser for 30 seconds without making any LLM API calls.
"""
