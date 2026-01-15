"""
Integration test for kickstart assessment flow.

Tests end-to-end orchestration: Kickstart script → Green Agent → Purple Agent → Result
Implements T021: Integration test for complete kickstart assessment flow.
"""

import asyncio
import os
import subprocess
import sys
from pathlib import Path

import pytest

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


@pytest.mark.integration
@pytest.mark.asyncio
async def test_kickstart_script_help():
    """
    Test that kickstart script loads and shows help.
    
    This is a minimal smoke test to verify:
    1. Script file exists
    2. Python can parse the script
    3. argparse help works
    """
    script_path = project_root / "scripts" / "kickstart_assessment.py"
    assert script_path.exists(), "Kickstart script not found"
    
    # Use sys.executable to ensure we use the same Python interpreter
    # Run with --help flag
    result = subprocess.run(
        [sys.executable, str(script_path), "--help"],
        capture_output=True,
        text=True,
        timeout=5
    )
    
    # Verify help output contains key arguments
    assert result.returncode == 0, f"Script failed with: {result.stderr}"
    assert "--task" in result.stdout
    assert "--benchmark" in result.stdout
    assert "--visible" in result.stdout
    assert "--output" in result.stdout
    assert "--timeout" in result.stdout


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.skipif(
    not os.getenv("GEMINI_API_KEY"),
    reason="Requires GEMINI_API_KEY for Purple Agent"
)
async def test_kickstart_full_assessment():
    """
    Test complete kickstart assessment flow (end-to-end).
    
    WARNING: This test is slow (~60-120s) and requires:
    - GEMINI_API_KEY environment variable
    - MiniWoB dataset downloaded
    - Available ports 9009, 9010
    
    Flow:
    1. Kickstart script starts Green Agent
    2. Green Agent spawns MCP server
    3. Green Agent sends MCP details to Purple Agent via A2A
    4. Purple Agent connects to MCP and executes task
    5. Kickstart script polls for completion
    6. Results returned and validated
    """
    script_path = project_root / "scripts" / "kickstart_assessment.py"
    
    # Ensure MiniWoB dataset path is set
    datasets_path = project_root / "datasets" / "miniwob" / "html" / "miniwob"
    if datasets_path.exists():
        os.environ["MINIWOB_URL"] = f"file:///{datasets_path.resolve().as_posix()}/"
    
    # Run kickstart script with simple task
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        str(script_path),
        "--task", "miniwob.click-test",
        "--timeout", "120",
        "--log-level", "INFO",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(project_root)
    )
    
    try:
        # Wait for completion (with timeout)
        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=150  # 120s task timeout + 30s buffer
        )
        
        # Check exit code
        assert process.returncode == 0, (
            f"Kickstart script failed with exit code {process.returncode}\n"
            f"STDOUT: {stdout.decode()}\n"
            f"STDERR: {stderr.decode()}"
        )
        
        # Verify success message in output
        output = stdout.decode()
        assert "ASSESSMENT COMPLETED SUCCESSFULLY" in output or "✓" in output, (
            f"Expected success message in output, got:\n{output}"
        )
        
    except asyncio.TimeoutError:
        # Kill process if timeout
        process.kill()
        await process.wait()
        pytest.fail("Kickstart script timed out after 150s")


@pytest.mark.integration
def test_kickstart_script_cli_validation():
    """
    Test kickstart script CLI argument validation.
    
    Verifies that:
    1. Script fails without required --task argument
    2. Script validates benchmark choices
    3. Script accepts valid timeout ranges
    """
    script_path = project_root / "scripts" / "kickstart_assessment.py"
    
    # Test 1: Missing required --task
    result = subprocess.run(
        [sys.executable, str(script_path)],
        capture_output=True,
        text=True,
        timeout=5
    )
    assert result.returncode != 0, "Should fail without --task"
    assert "required" in result.stderr.lower() or "error" in result.stderr.lower()
    
    # Test 2: Invalid benchmark (if provided)
    result = subprocess.run(
        [sys.executable, str(script_path), "--task", "test.task", "--benchmark", "invalid"],
        capture_output=True,
        text=True,
        timeout=5
    )
    assert result.returncode != 0, "Should fail with invalid benchmark"
    
    # Test 3: Valid arguments (but will fail at runtime without running agents)
    # Just verify parsing works
    result = subprocess.run(
        [sys.executable, str(script_path), 
         "--task", "miniwob.click-test",
         "--timeout", "60",
         "--visible",
         "--help"],  # Add --help to prevent actual execution
        capture_output=True,
        text=True,
        timeout=5
    )
    # With --help, it should show help and exit 0
    assert result.returncode == 0, "Should parse valid arguments"


if __name__ == "__main__":
    # Run tests directly for debugging
    import logging
    logging.basicConfig(level=logging.INFO)
    
    print("Running kickstart flow tests...")
    print("\n1. Testing help output...")
    asyncio.run(test_kickstart_script_help())
    print("✓ Help test passed")
    
    print("\n2. Testing CLI validation...")
    test_kickstart_script_cli_validation()
    print("✓ CLI validation test passed")
    
    if os.getenv("GEMINI_API_KEY"):
        print("\n3. Testing full assessment (requires ~120s)...")
        asyncio.run(test_kickstart_full_assessment())
        print("✓ Full assessment test passed")
    else:
        print("\n3. Skipping full assessment test (requires GEMINI_API_KEY)")
    
    print("\n✅ All kickstart tests passed!")
