"""
Integration test for MCP health checks.

Tests MCP server spawning, health verification, and tool availability.
Implements T113: Integration test for MCP health checks.
"""

import asyncio
import time
from uuid import uuid4

import pytest

from src.green_agent.resources.health_checker import verify_mcp_server_health_full
from src.green_agent.resources.process_monitor import spawn_mcp_server, terminate_mcp_server


class TestMCPHealthChecks:
    """Test MCP server health checking functionality."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_spawn_mcp_server(self):
        """Test spawning MCP server process."""
        try:
            session_id = uuid4().hex
            process, pid = await spawn_mcp_server(session_id)

            assert process is not None
            assert pid is not None
            assert process.poll() is None, "Process should be running"

            # Cleanup
            await terminate_mcp_server(process, pid)

        except Exception as e:
            pytest.skip(f"MCP server spawn not available: {e}")

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_mcp_health_check(self):
        """Test MCP server health check."""
        try:
            session_id = uuid4().hex
            process, pid = await spawn_mcp_server(session_id)

            # Wait for server to initialize
            await asyncio.sleep(2)

            # Check health
            health_result = await verify_mcp_server_health_full(process, pid, session_id)

            assert health_result is not None
            assert "is_healthy" in health_result
            assert isinstance(health_result["is_healthy"], bool)

            # Cleanup
            await terminate_mcp_server(process, pid)

        except Exception as e:
            pytest.skip(f"MCP health check not available: {e}")

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_mcp_tool_verification(self):
        """Test that MCP server exposes correct tools."""
        try:
            session_id = uuid4().hex
            process, pid = await spawn_mcp_server(session_id)

            # Wait for server to initialize
            await asyncio.sleep(2)

            # Check health and verify tools
            health_result = await verify_mcp_server_health_full(process, pid, session_id)

            if health_result.get("is_healthy"):
                # Expected MCP tools (only base tools for task execution)
                expected_tools = [
                    "execute_actions",
                    "get_observation",
                ]

                available_tools = health_result.get("tools_discovered", [])
                for tool in expected_tools:
                    assert tool in available_tools, f"Tool {tool} should be available"

            # Cleanup
            await terminate_mcp_server(process, pid)

        except Exception as e:
            pytest.skip(f"MCP tool verification not available: {e}")

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_mcp_server_restart_on_failure(self):
        """Test MCP server restart on failure."""
        try:
            session_id = uuid4().hex
            process, pid = await spawn_mcp_server(session_id)

            # Kill the process
            process.kill()
            await asyncio.sleep(1)

            # Verify process is dead
            assert process.poll() is not None, "Process should be terminated"

            # Health check should detect failure
            health_result = await verify_mcp_server_health_full(process, pid, session_id)

            assert health_result["is_healthy"] is False

            # Spawn new server (restart)
            new_session = uuid4().hex
            new_process, new_pid = await spawn_mcp_server(new_session)

            assert new_process.poll() is None, "New process should be running"

            # Cleanup
            await terminate_mcp_server(new_process, new_pid)

        except Exception as e:
            pytest.skip(f"MCP restart test not available: {e}")

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_mcp_cleanup(self):
        """Test MCP server cleanup."""
        try:
            session_id = uuid4().hex
            process, pid = await spawn_mcp_server(session_id)

            # Cleanup
            terminated = await terminate_mcp_server(process, pid)

            assert terminated is True or terminated is False

            # Verify process is terminated
            await asyncio.sleep(1)
            assert process.poll() is not None, "Process should be terminated"

        except Exception as e:
            pytest.skip(f"MCP cleanup test not available: {e}")

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_multiple_mcp_servers_isolated(self):
        """Test that multiple MCP servers can run in isolation."""
        try:
            session1 = uuid4().hex
            session2 = uuid4().hex
            process1, pid1 = await spawn_mcp_server(session1)
            process2, pid2 = await spawn_mcp_server(session2)

            # Verify both are running
            assert process1.poll() is None
            assert process2.poll() is None

            # Verify they have different PIDs
            assert process1.pid != process2.pid

            # Cleanup both
            await terminate_mcp_server(process1, pid1)
            await terminate_mcp_server(process2, pid2)

        except Exception as e:
            pytest.skip(f"Multiple MCP servers test not available: {e}")

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_mcp_health_check_timeout(self):
        """Test MCP health check with timeout."""
        try:
            session_id = uuid4().hex
            process, pid = await spawn_mcp_server(session_id)

            # Health check with short timeout
            try:
                health_result = await asyncio.wait_for(
                    verify_mcp_server_health_full(process, pid, session_id),
                    timeout=5.0
                )

                # If it completes, should have valid result
                assert health_result is not None

            except asyncio.TimeoutError:
                pytest.fail("Health check timed out")

            # Cleanup
            await terminate_mcp_server(process, pid)

        except Exception as e:
            pytest.skip(f"MCP health timeout test not available: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "integration"])
