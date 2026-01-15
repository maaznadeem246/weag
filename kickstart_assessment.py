"""
Kickstart Assessment Script - Complete A2A Assessment Flow Orchestration.

Implements User Story 1: Single command assessment execution.
Orchestrates Green and Purple agents for end-to-end evaluation flow.

Flow:
1. Start Green Agent server (port 9009)
2. Start Purple Agent server (port 9010)
3. Send assessment request to Green Agent with:
   - Participants map (Purple Agent endpoints)
   - Config (default_task_id, default_benchmark, timeout, etc.)
4. Green Agent orchestrates evaluation (sends task to Purple, monitors progress)
5. Poll for results and display

Config: scenarios/browsergym/scenario-local.toml (default)

Usage:
    python kickstart_assessment.py                              # Uses scenario-local.toml
    python kickstart_assessment.py --task miniwob.click-test    # Single task override
    python kickstart_assessment.py --visible                    # Visible browser mode (headless by default)
    python kickstart_assessment.py --output my_results.json     # Custom output path
"""

import argparse
import asyncio
import json
import logging
import os
import platform
import signal
import subprocess
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
import httpx
from dotenv import load_dotenv
from langfuse import get_client

try:
    import tomllib  # Python 3.11+
except Exception:  # pragma: no cover
    tomllib = None

# Optional: use psutil to detect running processes (best-effort)
try:
    import psutil
except Exception:
    psutil = None


# Add project root to path (kickstart_assessment.py is in root folder)
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Add green-agent to path for imports (benchmarks, etc.)
sys.path.insert(0, str(project_root / "green-agent"))

# Import shared constants (for validation only)
from src.benchmarks import SUPPORTED_BENCHMARKS

# Load environment variables from .env file
load_dotenv(project_root / ".env")

# Best-effort: initialize Langfuse with blocked instrumentation scopes early.
# This keeps A2A SDK internal spans from being exported to Langfuse.
# Kickstart script uses inline config to remain independent from agent configs.
try:
    from langfuse import Langfuse
    import os

    public_key = os.environ.get("LANGFUSE_PUBLIC_KEY")
    secret_key = os.environ.get("LANGFUSE_SECRET_KEY")
    host = os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com")
    blocked_list = ["a2a.sdk"]  # Block A2A SDK internal spans

    if public_key and secret_key:
        Langfuse(
            public_key=public_key,
            secret_key=secret_key,
            host=host,
            blocked_instrumentation_scopes=blocked_list,
            debug=os.environ.get("LANGFUSE_DEBUG", "false").lower() == "true",
        )
except Exception:
    pass

# Initialize Langfuse client for unified tracing
langfuse: Any = None
try:
    langfuse = get_client()
    if langfuse.auth_check():
        print("[OK] Kickstart: Langfuse client is authenticated and ready!")
    else:
        print("[WARN] Kickstart: Langfuse authentication failed. Tracing disabled.")
        langfuse = None
except Exception as e:
    print(f"[WARN] Kickstart: Failed to initialize Langfuse client: {e}")
    langfuse = None


logger = logging.getLogger(__name__)


# Default ports for local development.
# Keep these in sync with src.purple_agent.main defaults.
DEFAULT_GREEN_PORT = 9009
DEFAULT_PURPLE_PORT = 9010

# Default maximum tasks per benchmark (matches Green Agent's default)
# When TOML config doesn't specify max_tasks_per_benchmark, this value is used
DEFAULT_MAX_TASKS_PER_BENCHMARK = 2


class AgentProcess:
    """
    Manages agent subprocess lifecycle.
    
    Attributes:
        name: Agent name (for logging)
        process: Subprocess handle
        port: Port the agent listens on
        health_url: Health check endpoint URL
    """
    
    def __init__(self, name: str, port: int):
        """
        Initialize agent process manager.
        
        Args:
            name: Agent name (e.g., "Green Agent", "Purple Agent")
            port: Port the agent will listen on
        """
        self.name = name
        self.port = port
        self.health_url = f"http://localhost:{port}/health"
        self.process: Optional[subprocess.Popen] = None
    
    def start(self, command: list[str], env: Optional[Dict[str, str]] = None, cwd: Optional[Path] = None) -> None:
        """
        Start agent subprocess in a separate visible terminal window.
        
        Args:
            command: Command to execute (e.g., ["python", "-m", "src.main"])
            env: Environment variables to pass to subprocess
            cwd: Working directory for the process (defaults to project_root)
        """
        logger.info(f"Starting {self.name} in separate terminal...")
        
        # Merge environment with parent
        proc_env = os.environ.copy()
        if env:
            proc_env.update(env)
        
        # Build command string for terminal
        cmd_str = " ".join(command)
        
        # Use specified working directory or default to project root
        work_dir = cwd if cwd else project_root
        
        # Platform-specific terminal launch
        system = platform.system()
        
        if system == "Windows":
            # Build environment variable setup commands
            env_setup = ""
            if env:
                for key, value in env.items():
                    # Escape for command line
                    escaped_value = value.replace('"', '\\"')
                    env_setup += f'set "{key}={escaped_value}" && '
            
            # Activate venv if it exists
            venv_activate = ""
            venv_path = Path(work_dir) / ".venv" / "Scripts" / "activate.bat"
            if not venv_path.exists():
                # Try parent directory venv (for green-agent/purple-agent subdirs)
                venv_path = Path(work_dir).parent / ".venv" / "Scripts" / "activate.bat"
            if venv_path.exists():
                venv_activate = f'call "{venv_path}" && '
            
            # Build command to run agent
            full_command = f'{env_setup}{venv_activate}cd /d "{work_dir}" && {cmd_str} && echo. && echo Agent terminated. Press any key to close... && pause >nul'
            
            # Try Windows Terminal first (opens new tab in same window)
            try:
                self.process = subprocess.Popen(
                    [
                        "wt.exe",
                        "-w", "0",  # Use current window
                        "new-tab",
                        "--title", f"{self.name}",
                        "cmd.exe", "/k", full_command
                    ],
                    cwd=str(work_dir)
                )
            except FileNotFoundError:
                # Fallback to cmd.exe in new window
                self.process = subprocess.Popen(
                    ["cmd.exe", "/c", f'start "{self.name}" cmd.exe /k "{full_command}"'],
                    cwd=str(work_dir),
                    shell=True
                )
        else:
            # Linux/Mac: use gnome-terminal, xterm, or osascript
            env_setup = ""
            if env:
                for key, value in env.items():
                    escaped_value = value.replace("'", "'\\''")
                    env_setup += f"export {key}='{escaped_value}'; "
            
            bash_command = f"{env_setup}cd '{work_dir}'; {cmd_str}; echo ''; echo 'Agent terminated. Press enter to close...'; read"
            
            # Try gnome-terminal first, fallback to xterm
            try:
                self.process = subprocess.Popen(
                    ["gnome-terminal", "--", "bash", "-c", bash_command],
                    cwd=str(work_dir)
                )
            except FileNotFoundError:
                try:
                    self.process = subprocess.Popen(
                        ["xterm", "-e", "bash", "-c", bash_command],
                        cwd=str(work_dir)
                    )
                except FileNotFoundError:
                    # macOS: use osascript to open Terminal
                    self.process = subprocess.Popen(
                        ["osascript", "-e", f'tell app "Terminal" to do script "{bash_command}"'],
                        cwd=str(work_dir)
                    )
        
        # Give terminal time to spawn
        time.sleep(0.5)
        
        logger.info(f"✓ {self.name} launched in new terminal window")
    
    async def wait_until_healthy(self, timeout: int = 30) -> bool:
        """
        Poll health endpoint until agent is ready.
        
        Args:
            timeout: Maximum time to wait in seconds
            
        Returns:
            True if agent becomes healthy, False if timeout
        """
        logger.info(f"Waiting for {self.name} to become healthy...")
        
        start_time = time.time()
        async with httpx.AsyncClient() as client:
            while time.time() - start_time < timeout:
                try:
                    response = await client.get(self.health_url, timeout=2.0)
                    if response.status_code == 200:
                        logger.info(f"✓ {self.name} is healthy")
                        return True
                except (httpx.RequestError, httpx.HTTPStatusError):
                    pass
                
                await asyncio.sleep(0.5)
        
        logger.error(f"✗ {self.name} failed to become healthy within {timeout}s")
        return False
    
    def terminate(self) -> None:
        """Terminate agent subprocess gracefully (terminal launcher process only)."""
        if self.process:
            try:
                # For terminal-spawned processes, we're terminating the launcher
                # The actual agent may continue running in its terminal
                self.process.terminate()
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait()
                logger.info(f"✓ {self.name} terminal launcher stopped (agent may still be running in terminal)")
            except Exception as e:
                logger.error(f"Error terminating {self.name} launcher: {e}")


class KickstartOrchestrator:
    """
    Orchestrates complete assessment flow between Green and Purple agents.
    """
    
    def __init__(self, args: argparse.Namespace):
        """
        Initialize orchestrator with CLI arguments.
        
        Args:
            args: Parsed command-line arguments
        """
        self.args = args
        self.green_agent: Optional[AgentProcess] = None
        self.purple_agent: Optional[AgentProcess] = None

        # Load assessment config defaults (TOML) if CLI did not provide explicit task.
        self._assessment_config: Dict[str, Any] = {}
        if getattr(self.args, "config", None):
            self._assessment_config = self._load_assessment_toml(Path(self.args.config))

        # Apply TOML headless setting (default: True, user can set false in TOML)
        # CLI --visible flag overrides TOML to show browser
        # Read from [config] section first (new format), fallback to [assessment] (old format)
        config_section = self._assessment_config.get("config", {})
        assessment_cfg = self._assessment_config.get("assessment", {})
        toml_headless = config_section.get("headless", assessment_cfg.get("headless", True))  # Default headless=True
        # --visible CLI flag forces visible mode, otherwise use TOML setting
        self.args.headless = not self.args.visible and toml_headless

        # Derive benchmark from task if provided
        if self.args.task and (not self.args.benchmark):
            self.args.benchmark = self.args.task.split(".", 1)[0] if "." in self.args.task else "miniwob"

    def _load_assessment_toml(self, path: Path) -> Dict[str, Any]:
        return _kickstart_load_assessment_toml(path)

    def _resolve_participants(self) -> Dict[str, str]:
        return _kickstart_resolve_participants(project_root, self._assessment_config)

    def _resolve_task_plan(self) -> Dict[str, Any]:
        return _kickstart_resolve_task_plan(project_root, self._assessment_config)
    
    async def run(self) -> bool:
        """
        Execute complete assessment flow.
        
        Returns:
            True if assessment completed successfully, False otherwise
        """
        # Generate a unique assessment ID for this specific run
        self.assessment_id = f"eval_{uuid.uuid4().hex[:8]}_{int(time.time())}"
        logger.info(f"🚀 Starting new assessment: {self.assessment_id}")

        # Filled in if tracing is enabled.
        self.assessment_trace_id: Optional[str] = None

        # Create unified Langfuse trace for entire assessment
        if langfuse:
            with langfuse.start_as_current_span(
                name="BrowserGym-Assessment"
            ) as span:
                # Update trace with assessment metadata and time debug info
                span.update_trace(
                    name=f"Assessment: {self.args.task} ({self.assessment_id})",
                    tags=["assessment", "browsergym", self.args.benchmark],
                    metadata={
                        "assessment_id": self.assessment_id,
                        "task_id": self.args.task,
                        "benchmark": self.args.benchmark,
                        "timeout": self.args.timeout,
                        "headless": self.args.headless,
                        "time_debug": {
                            "iso_now": datetime.now().isoformat(),
                            "local_now": time.ctime(),
                            "tz": time.tzname[0]
                        }
                    },
                    session_id=self.assessment_id,  # Use unique assessment_id as session_id
                    user_id="kickstart-orchestrator",
                    version="1.0.0",
                )
                
                # Store trace_id for passing to child agents
                self.assessment_trace_id = span.trace_id
                logger.info(f"✓ Created unified trace: {self.assessment_trace_id}")
                
                return await self._run_assessment_flow(span)
        else:
            # No tracing - run without span
            self.assessment_trace_id = None
            return await self._run_assessment_flow(None)
    
    async def _run_assessment_flow(self, trace_span) -> bool:
        """
        Internal method to execute assessment flow (with or without tracing).
        
        Args:
            trace_span: Langfuse span for tracing (or None if tracing disabled)
            
        Returns:
            True if assessment completed successfully, False otherwise
        """
        try:
            # Step 1 & 2: Start Green Agent and Purple Agent in parallel
            logger.info("Starting both agents in parallel...")
            green_task = asyncio.create_task(self._start_green_agent())
            purple_task = asyncio.create_task(self._start_purple_agent())
            
            # Wait for both to complete
            green_ok, purple_ok = await asyncio.gather(green_task, purple_task)
            
            if not green_ok:
                if trace_span:
                    trace_span.update_trace(
                        output={"success": False, "error": "Failed to start Green Agent"},
                    )
                return False
            
            if not purple_ok:
                if trace_span:
                    trace_span.update_trace(
                        output={"success": False, "error": "Failed to start Purple Agent"},
                    )
                return False
            
            logger.info("✓ Both agents started successfully")
            
            # Step 3: Send assessment request to Green Agent
            # Green Agent will send task details to Purple Agent via A2A
            result = await self._send_assessment_request()
            
            if result:
                logger.info("\n" + "="*60)
                logger.info("✓ ASSESSMENT COMPLETED SUCCESSFULLY")
                logger.info("="*60 + "\n")
                
                # Display metrics in console
                self._display_results(result)
                
                # Export results (always enabled with default output/results.json)
                if self.args.output:
                    self._export_results(result)
                
                # Update trace with final results
                if trace_span:
                    trace_span.update_trace(
                        output=result,
                    )
                
                return True
            else:
                logger.error("\n" + "="*60)
                logger.error("✗ ASSESSMENT FAILED")
                logger.error("="*60 + "\n")
                
                if trace_span:
                    trace_span.update_trace(
                        output={"success": False, "error": "Assessment failed or timed out"},
                    )
                
                return False
        
        finally:
            # Cleanup: Terminate all agents
            await self._cleanup()
            
            # Flush Langfuse events before exit
            if langfuse:
                langfuse.flush()
    
    async def _start_green_agent(self) -> bool:
        """
        Start Green Agent server.
        
        Returns:
            True if started successfully, False otherwise
        
        Handles:
            - Port conflicts (T059)
            - MCP server startup failure (T057)
            - Process spawn failures with logging (T062)
        """
        try:
            port = int(self.args.green_agent_url.split(":")[-1])
            self.green_agent = AgentProcess("Green Agent", port)
            # Quick check: if Green Agent already running, skip starting a new one
            try:
                async with httpx.AsyncClient() as client:
                    health_url = f"{self.args.green_agent_url.rstrip('/')}" + "/health"
                    resp = await client.get(health_url, timeout=2.0)
                    if resp.status_code == 200:
                        logger.info(f"✓ Detected existing Green Agent at {self.args.green_agent_url}; skipping start")
                        # Do not set self.green_agent.process so cleanup won't kill external process
                        self.green_agent = None
                        return True
            except Exception:
                # Not running or unreachable; continue to start
                pass
            
            # Environment variables for Green Agent
            env = {}
            
            # Pass Langfuse credentials for tracing
            if os.environ.get("LANGFUSE_PUBLIC_KEY"):
                env["LANGFUSE_PUBLIC_KEY"] = os.environ["LANGFUSE_PUBLIC_KEY"]
                env["LANGFUSE_SECRET_KEY"] = os.environ.get("LANGFUSE_SECRET_KEY", "")
                env["LANGFUSE_HOST"] = os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com")
                env["LANGFUSE_ENABLED"] = "true"
                # Pass trace context for unified tracing (actual trace_id from kickstart span)
                if hasattr(self, 'assessment_trace_id') and self.assessment_trace_id:
                    env["ASSESSMENT_TRACE_ID"] = self.assessment_trace_id
                    env["ASSESSMENT_ID"] = self.assessment_id
                    logger.info(f"✓ Passing trace_id to Green Agent: {self.assessment_trace_id}")
                    logger.info(f"✓ Passing assessment_id to Green Agent: {self.assessment_id}")
                    # Ensure blocked instrumentation scopes are passed to child process
                    blocked = os.environ.get(
                        "LANGFUSE_BLOCKED_INSTRUMENTATION_SCOPES",
                        "a2a,a2a.server,a2a.client,a2a.server.events,a2a.server.events.event_queue,a2a.server.events.event_consumer,a2a.server.request_handlers,a2a.server.request_handlers.default_request_handler"
                    )
                    env["LANGFUSE_BLOCKED_INSTRUMENTATION_SCOPES"] = blocked
                
                miniwob_path = project_root / "benchmarks" / "miniwob" / "html" / "miniwob"
                if miniwob_path.exists():
                    env["MINIWOB_URL"] = f"file:///{miniwob_path.resolve().as_posix().rstrip('/')}/"
                else:
                    logger.warning(f"⚠ MiniWoB dataset not found at {miniwob_path}")
            
            # Set headless/visible mode (BrowserGym uses BROWSER_HEADLESS env var)
            env["BROWSER_HEADLESS"] = "true" if self.args.headless else "false"
            logger.info(f"Setting BROWSER_HEADLESS={env['BROWSER_HEADLESS']} (headless mode: {self.args.headless})")

            # Per-agent env overrides from assessment config
            env.update(_extract_agent_env(self._assessment_config, "green_agent"))
            
            # Start subprocess (may fail if port in use - T059)
            try:
                assert self.green_agent is not None
                # Use green-agent's venv python (per-agent venv)
                green_python = project_root / "green-agent" / ".venv" / "Scripts" / "python.exe"
                if not green_python.exists():
                    green_python = project_root / "green-agent" / ".venv" / "bin" / "python"
                if not green_python.exists():
                    # Fallback to system python if venv not found
                    green_python = Path("python")
                self.green_agent.start(
                    command=[str(green_python), "-m", "src.main", "--host", "127.0.0.1", "--port", str(port)],
                    env=env,
                    cwd=project_root / "green-agent"
                )
            except OSError as e:
                logger.error(f"✗ Failed to start Green Agent: {e}")
                if "address already in use" in str(e).lower() or "port" in str(e).lower():
                    logger.error(f"✗ Port {port} appears to be already in use")
                    logger.error(f"  Try: lsof -ti :{port} | xargs kill -9  (Linux/macOS)")
                    logger.error(f"  Or: netstat -ano | findstr :{port}  (Windows)")
                return False
            
            # Wait for health check (may fail if MCP server doesn't start - T057)
            assert self.green_agent is not None
            is_healthy = await self.green_agent.wait_until_healthy(timeout=30)
            
            if not is_healthy:
                logger.error("✗ Green Agent failed health check - possible MCP server startup failure")
                logger.error("  Check logs/green_agent.err for details")
                
                # Try to get process output for diagnostics
                assert self.green_agent is not None
                if self.green_agent.process:
                    try:
                        stdout, stderr = self.green_agent.process.communicate(timeout=1)
                        if stderr:
                            logger.error(f"  Green Agent stderr: {stderr.decode()[:500]}")
                        if stdout:
                            logger.error(f"  Green Agent stdout: {stdout.decode()[:500]}")
                    except:
                        pass
                
                # Attempt cleanup
                if self.green_agent:
                    self.green_agent.terminate()
                return False
            
            return True
        
        except Exception as e:
            logger.error(f"✗ Unexpected error starting Green Agent: {e}")
            logger.exception("Full traceback:")
            return False
    
    async def _start_purple_agent(self) -> bool:
        """
        Start Purple Agent server that will wait for Green Agent to send task details.
        
        Returns:
            True if started successfully, False otherwise
        """
        try:
            # Purple Agent runs as A2A server on port 9010 (default)
            purple_port = DEFAULT_PURPLE_PORT
            self.purple_agent = AgentProcess("Purple Agent", purple_port)
            
            # Quick check: if Purple Agent already running (e.g., Docker container), skip starting
            try:
                async with httpx.AsyncClient() as client:
                    # Try agent card endpoint (standard A2A discovery)
                    health_url = f"http://localhost:{purple_port}/.well-known/agent-card.json"
                    resp = await client.get(health_url, timeout=2.0)
                    if resp.status_code == 200:
                        logger.info(f"✓ Detected existing Purple Agent at http://localhost:{purple_port}; skipping start")
                        # Do not set self.purple_agent.process so cleanup won't kill external process
                        self.purple_agent = None
                        return True
            except Exception:
                # Not running or unreachable; continue to start
                pass
            
            # Environment variables for Purple Agent
            env = {
                "GEMINI_API_KEY": os.environ.get("GEMINI_API_KEY", ""),
            }

            # Per-agent env overrides from assessment config
            env.update(_extract_agent_env(self._assessment_config, "purple_agent"))
            
            # Add Langfuse credentials and trace context for unified tracing
            if os.environ.get("LANGFUSE_PUBLIC_KEY"):
                env["LANGFUSE_PUBLIC_KEY"] = os.environ["LANGFUSE_PUBLIC_KEY"]
                env["LANGFUSE_SECRET_KEY"] = os.environ.get("LANGFUSE_SECRET_KEY", "")
                env["LANGFUSE_HOST"] = os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com")
                env["LANGFUSE_ENABLED"] = "true"
                # Pass trace context for unified tracing (actual trace_id from kickstart span)
                if hasattr(self, 'assessment_trace_id') and self.assessment_trace_id:
                    env["ASSESSMENT_TRACE_ID"] = self.assessment_trace_id
                    env["ASSESSMENT_ID"] = self.assessment_id
                    logger.info(f"✓ Passing trace_id to Purple Agent: {self.assessment_trace_id}")
                    logger.info(f"✓ Passing assessment_id to Purple Agent: {self.assessment_id}")
                # Ensure blocked instrumentation scopes are passed to child process
                blocked = os.environ.get(
                    "LANGFUSE_BLOCKED_INSTRUMENTATION_SCOPES",
                    "a2a,a2a.server,a2a.client,a2a.server.events,a2a.server.events.event_queue,a2a.server.events.event_consumer,a2a.server.request_handlers,a2a.server.request_handlers.default_request_handler"
                )
                env["LANGFUSE_BLOCKED_INSTRUMENTATION_SCOPES"] = blocked
            
            # Purple Agent runs as A2A server
            # Use purple-agent's venv python (per-agent venv)
            purple_python = project_root / "purple-agent" / ".venv" / "Scripts" / "python.exe"
            if not purple_python.exists():
                purple_python = project_root / "purple-agent" / ".venv" / "bin" / "python"
            if not purple_python.exists():
                # Fallback to system python if venv not found
                purple_python = Path("python")
            command = [str(purple_python), "-m", "src.main", "--port", str(purple_port)]
            
            # Start the purple agent process
            assert self.purple_agent is not None
            self.purple_agent.start(command=command, env=env, cwd=project_root / "purple-agent")
            logger.info("✓ Purple Agent server started")
            
            # Wait for Purple agent to become healthy
            assert self.purple_agent is not None
            is_healthy = await self.purple_agent.wait_until_healthy(timeout=30)
            if not is_healthy:
                logger.error("✗ Purple Agent failed health check")
                return False
            
            return True
                
        except OSError as e:
                logger.error(f"✗ Failed to start Purple Agent: {e}")
                return False
        
        except Exception as e:
            logger.error(f"✗ Failed to start Purple Agent: {e}")
            logger.exception("Full traceback:")
            return False
        
        return True
    
    
    async def _send_assessment_request(self) -> Optional[Dict[str, Any]]:
        """
        Send assessment request to Green Agent using A2A JSON-RPC protocol.
        
        Returns:
            Assessment result if successful, or None if request failed
        """
        logger.info("\n" + "="*60)
        logger.info("SENDING A2A MESSAGE TO GREEN AGENT")
        logger.info("="*60)
        
        # Resolve participants + task plan.
        run_id = getattr(self, "assessment_id", None) or f"eval_{uuid.uuid4().hex[:8]}"
        participants = self._resolve_participants()
        plan = self._resolve_task_plan()

        # Build config for Green Agent.
        # Back-compat: if a single explicit --task is provided, still pass task_id.
        config: Dict[str, Any] = {
            "run_id": run_id,
            "timeout_seconds": int(self.args.timeout),
            "max_steps": int(getattr(self.args, "max_steps", 10) or 10),
        }

        if self.args.task:
            config.update({
                "task_id": self.args.task,
                "benchmark": self.args.benchmark or (self.args.task.split(".", 1)[0] if "." in self.args.task else "miniwob"),
            })
        else:
            # Multi-task mode: pass benchmarks/tasks to Green Agent
            # If empty, Green Agent will use its DEFAULT_EVALUATION_BENCHMARKS
            benchmarks = plan.get("benchmarks", [])
            tasks_by_benchmark = plan.get("tasks_by_benchmark", {})
            
            # Check if tasks_by_benchmark has any actual tasks
            has_explicit_tasks = any(len(tasks) > 0 for tasks in tasks_by_benchmark.values())
            
            config.update({
                "mode": "multi",
                "benchmarks": benchmarks,  # Can be empty - Green Agent will use defaults
            })
            
            # Only pass tasks_by_benchmark if there are explicit tasks
            # Otherwise, Green Agent will auto-discover tasks
            if has_explicit_tasks:
                config["tasks_by_benchmark"] = tasks_by_benchmark
            
            # Only include max_tasks_per_benchmark if explicitly set in TOML
            # Otherwise, Green Agent will use its DEFAULT_MAX_TASKS_PER_BENCHMARK
            if "max_tasks_per_benchmark" in plan:
                config["max_tasks_per_benchmark"] = plan["max_tasks_per_benchmark"]
        
        # Build evaluation request payload
        eval_request = {
            "participants": participants,
            "config": config
        }
        
        # Build A2A JSON-RPC message/send request
        message_id = uuid.uuid4().hex
        
        # Build user message based on mode
        if self.args.task:
            user_text = f"Start the evaluation for task: {self.args.task}"
        else:
            task_count = sum(len(tasks) for tasks in config.get("tasks_by_benchmark", {}).values())
            benchmark_count = len(config.get("benchmarks", []))
            
            # If no tasks discovered here, Green Agent will use its defaults
            if task_count == 0:
                user_text = "Start the multi-task evaluation (use default benchmarks)"
            else:
                user_text = f"Start the multi-task evaluation ({task_count} tasks across {benchmark_count} benchmarks)"
        
        a2a_request = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "message/send",
            "params": {
                "message": {
                    "kind": "message",
                    "role": "user",
                    "parts": [
                        {
                            "kind": "text",
                            "text": user_text
                        },
                        {
                            "kind": "data",
                            "data": eval_request
                        }
                    ],
                    "messageId": message_id
                }
            }
        }
        
        logger.info(f"Participants: {json.dumps(participants, indent=2)}")
        logger.info(f"Config: {json.dumps(config, indent=2)}")
        logger.info(f"Message ID: {message_id}")
        logger.info("="*60 + "\n")
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                # Send A2A JSON-RPC message to Green Agent root endpoint
                response = await client.post(
                    self.args.green_agent_url.rstrip('/'),
                    json=a2a_request,
                    headers={"Content-Type": "application/json"},
                    timeout=60.0
                )
                
                logger.info(f"Response status: {response.status_code}")
                
                if response.status_code == 200:
                    result = response.json()
                    logger.info(f"✓ A2A message sent successfully")
                    logger.info(f"Response: {json.dumps(result, indent=2)[:500]}")
                    
                    # Check if task was created
                    if "result" in result:
                        result_data = result["result"]
                        if isinstance(result_data, dict) and result_data.get("type") == "task":
                            task_id = result_data.get("id")
                            status = result_data.get("status", {}).get("state", "unknown")
                            logger.info(f"✅ Task Created: {task_id}")
                            logger.info(f"   Status: {status}")
                    
                    # Start polling for completion (multi-task uses run_id)
                    return await self._poll_for_completion_direct(run_id)
                else:
                    logger.error(f"✗ A2A message failed: {response.status_code}")
                    logger.error(f"Response: {response.text}")
                    return None
                    
        except httpx.TimeoutException:
            logger.error(f"✗ A2A message timed out after 60s")
            return None
        except Exception as e:
            logger.error(f"✗ A2A message failed: {e}")
            logger.exception("Full traceback:")
            return None
    
    async def _poll_for_completion_direct(self, interaction_id: str) -> Optional[Dict[str, Any]]:
        """
        Poll Green Agent for assessment completion.
        Purple Agent communicates with Green Agent via A2A automatically.
        
        Returns:
            Assessment result dict if successful, None otherwise
        """
        logger.info("\n" + "="*60)
        logger.info("MONITORING ASSESSMENT")
        logger.info("="*60)
        logger.info(f"Interaction ID: {interaction_id}")
        if self.args.task:
            logger.info(f"Task: {self.args.task}")
            logger.info(f"Benchmark: {self.args.benchmark}")
        logger.info(f"Timeout: {self.args.timeout}s")
        logger.info(f"Mode: {'HEADLESS' if self.args.headless else 'VISIBLE'}")
        logger.info("="*60 + "\n")
        
        logger.info("Purple Agent → Green Agent A2A handshake in progress...")
        logger.info("Waiting for evaluation to complete...")
        
        try:
            async with httpx.AsyncClient(timeout=self.args.timeout) as client:
                assessment_result = await self._poll_for_completion(client, interaction_id)
                
                # Check for MCP connection timeout (T058)
                if assessment_result is None:
                    # Could be timeout or Purple agent crash
                    logger.error("✗ Assessment failed - possible causes:")
                    logger.error("  - Purple Agent failed to connect via A2A")
                    logger.error("  - MCP connection timeout from Purple Agent")
                    logger.error("  - Purple Agent crash")
                    logger.error("  - Assessment exceeded timeout")
                    logger.error("  Check Green Agent and Purple Agent logs for details")
                
                return assessment_result
        
        except httpx.TimeoutException:
            logger.error(f"✗ Assessment timed out after {self.args.timeout}s")
            return None
        except Exception as e:
            logger.error(f"✗ Assessment failed: {e}")
            logger.exception("Full traceback:")
            return None
    
    async def _poll_for_completion(
        self, 
        client: httpx.AsyncClient, 
        interaction_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Poll Green Agent for assessment completion.
        
        Handles:
            - T056: Purple agent crash detection
            - T060: Assessment timeout (terminate hung agents)
        
        Args:
            client: HTTP client
            interaction_id: Interaction ID from initial request
            
        Returns:
            Final result or None if timeout/failure
        """
        logger.info("Polling for assessment completion...")
        
        poll_interval = 2.0  # Poll every 2 seconds
        max_polls = self.args.timeout // poll_interval
        start_time = time.time()
        
        for i in range(int(max_polls)):
            await asyncio.sleep(poll_interval)
            
            try:
                # Check Green Agent status endpoint first (primary source of truth)
                response = await client.get(
                    f"{self.args.green_agent_url}/status/{interaction_id}",
                    timeout=5.0
                )
                
                if response.status_code == 200:
                    status = response.json()
                    state = status.get("state", "unknown")
                    
                    elapsed = time.time() - start_time
                    logger.info(f"Status: {state} ({elapsed:.0f}s elapsed)")
                    
                    if state == "complete":
                        logger.info("✓ Assessment completed")
                        return status.get("result", {})
                    elif state == "failed":
                        logger.error("✗ Assessment failed")
                        error_msg = status.get("error", "No error details provided")
                        logger.error(f"  Error: {error_msg}")
                        return None
                    
                    # If still running, check if Purple agent crashed prematurely (T056)
                    if state == "running" and self.purple_agent and self.purple_agent.process:
                        if self.purple_agent.process.poll() is not None:
                            # Purple agent terminated while evaluation still running = crash
                            logger.error("✗ Purple Agent crashed during assessment (evaluation still running)")
                            logger.error("  Check logs/purple_agent.log for details")
                            
                            # Try to get stderr output for diagnostics
                            try:
                                _, stderr = self.purple_agent.process.communicate(timeout=1)
                                if stderr:
                                    stderr_text = stderr.decode()[:1000]
                                    logger.error(f"  Purple Agent stderr: {stderr_text}")
                            except:
                                pass
                            
                            return None
                
            except Exception as e:
                logger.warning(f"Poll error (retry): {type(e).__name__}: {e}")
                # Don't fail immediately, keep trying
        
        # T060: Assessment timeout - terminate hung agents
        logger.error(f"✗ Assessment timed out after {self.args.timeout}s")
        logger.warning("⚠ Terminating hung agents...")
        
        # Cleanup will be called in finally block
        return None    
    
    def _display_results(self, result: Dict[str, Any]) -> None:
        """
        Display assessment results in console.
        
        Args:
            result: Assessment result dictionary from Green Agent
        """
        logger.info("EVALUATION RESULTS")
        logger.info("="*60)
        
        # Task outcome
        task_success = result.get("task_success", False)
        task_id = result.get("task_id", "unknown")
        benchmark = result.get("benchmark", "unknown")
        
        logger.info(f"Task ID: {task_id}")
        logger.info(f"Benchmark: {benchmark}")
        logger.info(f"Success: {'✓ YES' if task_success else '✗ NO'}")
        logger.info("")
        
        # Scores
        final_score = result.get("final_score", 0.0)
        efficiency_penalty = result.get("efficiency_penalty", 0.0)
        
        logger.info("SCORES")
        logger.info(f"  Final Score: {final_score:.4f}")
        logger.info(f"  Efficiency Penalty: {efficiency_penalty:.4f}")
        logger.info("")
        
        # Efficiency Metrics (Constitutional Mandates C/L/F)
        logger.info("EFFICIENCY METRICS (C/L/F Mandates)")
        total_tokens = result.get("total_tokens", 0)
        total_latency_ms = result.get("total_latency_ms", 0)
        peak_memory_mb = result.get("peak_memory_mb", 0)
        chromium_count = result.get("chromium_process_count", 0)
        
        logger.info(f"  Total Tokens (C): {total_tokens:,}")
        logger.info(f"  Total Latency (L): {total_latency_ms:,} ms ({total_latency_ms/1000:.2f}s)")
        logger.info(f"  Peak Memory (F): {peak_memory_mb} MB")
        logger.info(f"  Chromium Processes: {chromium_count}")
        logger.info("")
        
        # Activity Stats
        logger.info("ACTIVITY STATISTICS")
        mcp_calls = result.get("mcp_tool_invocations", 0)
        observations = result.get("observation_count", 0)
        actions = result.get("action_count", 0)
        duration = result.get("evaluation_duration_seconds", 0.0)
        
        logger.info(f"  MCP Tool Calls: {mcp_calls}")
        logger.info(f"  Observations: {observations}")
        logger.info(f"  Actions: {actions}")
        logger.info(f"  Duration: {duration:.2f}s")
        
        # Error message if present
        error_msg = result.get("error_message")
        if error_msg:
            logger.info("")
            logger.error(f"ERROR: {error_msg}")
        
        logger.info("="*60)
    
    def _export_results(self, result: Dict[str, Any]) -> None:
        """
        Export assessment results to JSON file in AgentBeats-compatible format.
        
        AgentBeats expects results.json with:
        - participants: mapping of role to agent ID/endpoint
        - results: array of task results with pass_rate, time_used, max_score
        
        Args:
            result: Assessment result dictionary from Green Agent
        """
        try:
            output_path = Path(self.args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Transform to AgentBeats format
            agentbeats_result = self._to_agentbeats_format(result)
            
            with open(output_path, "w") as f:
                json.dump(agentbeats_result, f, indent=2)
            
            logger.info(f"✓ Results exported to: {output_path}")
            logger.info(f"  Format: AgentBeats-compatible (participants + results)")
        
        except Exception as e:
            logger.error(f"✗ Failed to export results: {e}")
    
    def _to_agentbeats_format(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform internal result format to AgentBeats leaderboard-compatible format.
        
        AgentBeats format:
        {
            "participants": { "agent": "<endpoint_or_id>" },
            "results": [
                { "pass_rate": 0.85, "time_used": 45.5, "max_score": 1 }
            ]
        }
        
        Args:
            result: Internal assessment result dictionary
            
        Returns:
            AgentBeats-compatible result dictionary
        """
        # Handle both single-task and multi-task modes
        mode = result.get("mode", "single")
        
        # Build participants map
        participants_internal = result.get("participants", {})
        participants = {}
        
        if participants_internal:
            # Multi-task mode: participants is already populated
            for role, data in participants_internal.items():
                if isinstance(data, dict):
                    participants[role] = data.get("endpoint", str(data))
                else:
                    participants[role] = str(data)
        else:
            # Single-task mode: use default
            participants["agent"] = "purple_agent"
        
        # Build results array
        results = []
        
        if mode == "multi":
            # Multi-task: aggregate from participants
            validation = result.get("validation", {})
            total_tasks = validation.get("total_tasks", 1)
            passed = validation.get("passed", 0)
            
            for role, data in participants_internal.items():
                if isinstance(data, dict):
                    task_results = data.get("task_results", [])
                    for task_result in task_results:
                        results.append({
                            "pass_rate": 1.0 if task_result.get("success", False) else 0.0,
                            "time_used": task_result.get("duration_seconds", 0.0),
                            "max_score": 1,
                            "task_id": task_result.get("task_id", "unknown"),
                        })
                    
                    # If no individual results, add aggregate
                    if not task_results:
                        results.append({
                            "pass_rate": passed / max(total_tasks, 1),
                            "time_used": result.get("evaluation_duration_seconds", 0.0),
                            "max_score": total_tasks,
                        })
        else:
            # Single-task: one result entry
            results.append({
                "pass_rate": 1.0 if result.get("task_success", False) else 0.0,
                "time_used": result.get("evaluation_duration_seconds", 0.0),
                "max_score": 1,
                "task_id": result.get("task_id", "unknown"),
                "benchmark": result.get("benchmark", "unknown"),
            })
        
        # Build final AgentBeats-compatible output
        return {
            "participants": participants,
            "results": results,
            # Include full internal result for debugging (can be removed for production)
            "_internal": result,
        }
    
    async def _cleanup(self) -> None:
        """
        Clean up agent terminal launchers.
        
        Note: Agents running in separate terminals will continue until manually closed.
        Handles T061: MCP subprocess cleanup failure (log warning, forceful kill).
        """
        logger.info("\nCleaning up agent launchers...")
        logger.info("Note: Agents are running in separate terminals. Close terminal windows manually if needed.")
        cleanup_errors = []
        
        # Cleanup Green Agent (includes MCP subprocess)
        if self.green_agent:
            try:
                self.green_agent.terminate()
                logger.info("✓ Green Agent terminated")
            except Exception as e:
                error_msg = f"Failed to terminate Green Agent: {e}"
                logger.warning(f"⚠ {error_msg}")
                cleanup_errors.append(error_msg)
                
                # Attempt forceful kill if termination failed
                try:
                    if self.green_agent.process and self.green_agent.process.poll() is None:
                        logger.warning("⚠ Attempting forceful kill of Green Agent...")
                        self.green_agent.process.kill()
                        self.green_agent.process.wait(timeout=5)
                        logger.info("✓ Green Agent forcefully killed")
                except Exception as kill_error:
                    error_msg = f"Forceful kill also failed: {kill_error}"
                    logger.error(f"✗ {error_msg}")
                    cleanup_errors.append(error_msg)
        
        # Cleanup Purple Agent
        if self.purple_agent:
            try:
                self.purple_agent.terminate()
                logger.info("✓ Purple Agent terminated")
            except Exception as e:
                error_msg = f"Failed to terminate Purple Agent: {e}"
                logger.warning(f"⚠ {error_msg}")
                cleanup_errors.append(error_msg)
                
                # Attempt forceful kill
                try:
                    if self.purple_agent.process and self.purple_agent.process.poll() is None:
                        logger.warning("⚠ Attempting forceful kill of Purple Agent...")
                        self.purple_agent.process.kill()
                        self.purple_agent.process.wait(timeout=5)
                        logger.info("✓ Purple Agent forcefully killed")
                except Exception as kill_error:
                    error_msg = f"Forceful kill also failed: {kill_error}"
                    logger.error(f"✗ {error_msg}")
                    cleanup_errors.append(error_msg)
        
        if cleanup_errors:
            logger.warning(f"⚠ Cleanup completed with {len(cleanup_errors)} error(s)")
            logger.warning("  Some processes may still be running. Check manually if needed.")
        else:
            logger.info("✓ Cleanup complete")


def parse_arguments() -> argparse.Namespace:
    """
    Parse command-line arguments.
    
    Returns:
        Parsed arguments
    """
    parser = argparse.ArgumentParser(
        description="Kickstart assessment orchestration for Green and Purple agents",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    parser.add_argument(
        "--task",
        type=str,
        default=None,
        help="Single task identifier (e.g., miniwob.click-test). If omitted, uses TOML config."
    )
    
    parser.add_argument(
        "--benchmark",
        type=str,
        choices=SUPPORTED_BENCHMARKS,
        help="Benchmark suite name (auto-derived from task if not provided)"
    )

    parser.add_argument(
        "--config",
        type=str,
        default=str(project_root / "scenarios" / "browsergym" / "scenario-local.toml"),
        help="Path to scenario TOML config (default: scenarios/browsergym/scenario-local.toml)"
    )

    parser.add_argument(
        "--max-steps",
        type=int,
        default=10,
        help="Max steps per task (sent to Green Agent)"
    )
    
    parser.add_argument(
        "--visible",
        action="store_true",
        help="Run browser in visible mode (headless by default)"
    )
    
    parser.add_argument(
        "--output",
        type=str,
        default="output/results.json",
        help="File path for exporting assessment results as JSON (AgentBeats-compatible)"
    )
    
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="Maximum time allowed for assessment completion in seconds"
    )
    
    parser.add_argument(
        "--green-agent-url",
        type=str,
        default="http://localhost:9009",
        help="URL of the Green agent A2A server"
    )
    
    parser.add_argument(
        "--log-level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging verbosity level"
    )
    
    return parser.parse_args()


def _safe_read_toml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    if tomllib is None:
        raise RuntimeError("tomllib not available (requires Python 3.11+)")
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


# Task discovery is now handled by src.green_agent.benchmarks.task_discovery


def _normalize_task_list(benchmark_id: str, raw_tasks: Any) -> list[str]:
    if raw_tasks is None:
        return []
    if not isinstance(raw_tasks, list):
        raise ValueError(f"Expected list of tasks for benchmark '{benchmark_id}', got {type(raw_tasks)}")
    tasks: list[str] = []
    for t in raw_tasks:
        if not isinstance(t, str):
            continue
        t = t.strip()
        if not t:
            continue
        # allow full task_id (miniwob.click-test) or short name (click-test)
        if "." in t:
            tasks.append(t)
        else:
            tasks.append(f"{benchmark_id}.{t}")
    return tasks


def _ensure_http_url(s: str) -> str:
    s = s.strip()
    if not s:
        raise ValueError("Empty participant URL")
    # Accept http(s) only; Green uses HttpUrl model
    if not (s.startswith("http://") or s.startswith("https://")):
        raise ValueError(f"Participant URL must start with http:// or https://, got: {s}")
    if not s.endswith("/"):
        s += "/"
    return s


def _coalesce_int(value: Any, default: int) -> int:
    try:
        if value is None:
            return int(default)
        return int(value)
    except Exception:
        return int(default)


def _coalesce_str(value: Any, default: str) -> str:
    return str(value).strip() if value is not None and str(value).strip() else default


def _listify(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _dictify(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _default_benchmarks() -> list[str]:
    """
    Get default benchmarks for evaluation when TOML config has no [[benchmarks]] sections.
    
    Returns empty list - Green Agent will apply DEFAULT_EVALUATION_BENCHMARKS from
    src.benchmarks.task_discovery. This ensures a single source of truth.
    
    To control which benchmarks are evaluated by default, edit DEFAULT_EVALUATION_BENCHMARKS
    in green-agent/src/benchmarks/task_discovery.py.
    """
    return []


def _extract_benchmarks(toml_data: Dict[str, Any]) -> list[Dict[str, Any]]:
    raw = toml_data.get("benchmarks")
    return _listify(raw)


def _extract_agent_env(toml_data: Dict[str, Any], agent_key: str) -> Dict[str, str]:
    agent_cfg = _dictify(toml_data.get(agent_key))
    env_cfg = _dictify(agent_cfg.get("env"))
    result: Dict[str, str] = {}
    for key, value in env_cfg.items():
        if value is None:
            continue
        result[str(key)] = str(value)
    return result


# Add these as methods to keep orchestrator state minimal
def _kickstart_load_assessment_toml(path: Path) -> Dict[str, Any]:
    try:
        return _safe_read_toml(path)
    except Exception as e:
        logger.warning(f"Failed to load assessment TOML at {path}: {e}")
        return {}


def _kickstart_resolve_participants(project_root: Path, toml_data: Dict[str, Any]) -> Dict[str, str]:
    # New structure: participants is a list of {role, endpoint, cmd}
    participants_cfg = _listify(toml_data.get("participants"))
    if not participants_cfg:
        return {"purple_agent": f"http://127.0.0.1:{DEFAULT_PURPLE_PORT}/"}

    participants: Dict[str, str] = {}
    for entry in participants_cfg:
        if not isinstance(entry, dict):
            continue
        role = _coalesce_str(entry.get("role"), "purple_agent")
        url = _coalesce_str(entry.get("endpoint"), "")
        if role and url:
            participants[role] = _ensure_http_url(url)
    
    if not participants:
        participants = {"purple_agent": f"http://127.0.0.1:{DEFAULT_PURPLE_PORT}/"}
    return participants


def _kickstart_resolve_task_plan(project_root: Path, toml_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Resolve task plan from TOML config.
    
    When no [[benchmarks]] sections are defined in TOML, returns empty benchmarks list.
    The Green Agent will then use its DEFAULT_EVALUATION_BENCHMARKS.
    """
    # Read from [config] section first (new format), fallback to [assessment] (old format)
    config_section = _dictify(toml_data.get("config"))
    assessment_cfg = _dictify(toml_data.get("assessment"))
    # Try config section first, then assessment section, finally use DEFAULT_MAX_TASKS_PER_BENCHMARK
    default_max = _coalesce_int(
        config_section.get("max_tasks_per_benchmark") or assessment_cfg.get("max_tasks_per_benchmark"),
        DEFAULT_MAX_TASKS_PER_BENCHMARK
    )

    benchmarks_cfg = _extract_benchmarks(toml_data)
    
    # If no benchmarks configured, let Green Agent handle defaults
    if not benchmarks_cfg:
        return {
            "benchmarks": [],  # Empty - Green Agent will use DEFAULT_EVALUATION_BENCHMARKS
            "tasks_by_benchmark": {},
            "max_tasks_per_benchmark": default_max,
        }

    benchmarks: list[str] = []
    tasks_by_benchmark: Dict[str, list[str]] = {}

    for entry in benchmarks_cfg:
        if not isinstance(entry, dict):
            continue
        benchmark_id = _coalesce_str(entry.get("id"), "miniwob")
        benchmarks.append(benchmark_id)

        max_tasks = _coalesce_int(entry.get("max_tasks"), default_max)
        tasks = _normalize_task_list(benchmark_id, entry.get("tasks"))

        # Only use explicit tasks from TOML (limit by max_tasks)
        # If no tasks specified, Green Agent will discover them
        if tasks and max_tasks > 0:
            tasks = tasks[:max_tasks]

        tasks_by_benchmark[benchmark_id] = tasks

    return {
        "benchmarks": benchmarks,
        "tasks_by_benchmark": tasks_by_benchmark,
        "max_tasks_per_benchmark": default_max,
    }



def setup_logging(level: str) -> None:
    """
    Configure logging for the orchestrator.
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR)
    """
    # Determine log file path (can be overridden with LOG_PATH env var)
    log_path = os.environ.get("LOG_PATH", os.path.join("logs", "full_assessment.log"))
    log_dir = os.path.dirname(log_path) or "logs"
    os.makedirs(log_dir, exist_ok=True)

    # Remove existing handlers to avoid duplicate logs when re-initializing
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)

    root.setLevel(getattr(logging, level, logging.INFO))

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(getattr(logging, level, logging.INFO))
    ch.setFormatter(fmt)
    root.addHandler(ch)

    # Rotating file handler
    fh: logging.Handler
    try:
        from logging.handlers import RotatingFileHandler

        fh = RotatingFileHandler(log_path, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8")
        fh.setLevel(getattr(logging, level, logging.INFO))
        fh.setFormatter(fmt)
        root.addHandler(fh)
    except Exception:
        # Fallback: if rotating handler not available, use basicFileHandler
        fh = logging.FileHandler(log_path, encoding="utf-8")
        fh.setLevel(getattr(logging, level, logging.INFO))
        fh.setFormatter(fmt)
        root.addHandler(fh)

    root.info("Logging initialized, file=%s", os.path.abspath(log_path))


async def main() -> int:
    """
    Main entry point.
    
    Returns:
        Exit code (0 for success, 1 for failure)
    """
    args = parse_arguments()
    setup_logging(args.log_level)
    
    logger.info("="*60)
    logger.info("KICKSTART ASSESSMENT ORCHESTRATOR")
    logger.info("="*60)
    
    orchestrator = KickstartOrchestrator(args)
    
    # Handle Ctrl+C gracefully
    def signal_handler(signum, frame):
        logger.info("\nReceived interrupt signal, cleaning up...")
        asyncio.create_task(orchestrator._cleanup())
        sys.exit(1)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    success = await orchestrator.run()
    
    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
