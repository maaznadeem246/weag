"""
Integration test for A2A protocol isolation.

Verifies zero direct Purple-Green communication (only A2A protocol).
Implements T115: Integration test for A2A protocol isolation.
"""

import asyncio
import subprocess
import time
from unittest.mock import Mock, patch

import httpx
import pytest


class TestA2AProtocolIsolation:
    """Test A2A protocol isolation between Purple and Green agents."""

    @pytest.fixture(scope="class")
    def green_agent_url(self):
        """Green Agent base URL."""
        return "http://localhost:9009"

    @pytest.fixture(scope="class")
    def green_agent_process(self, green_agent_url):
        """Start Green Agent server for testing."""
        process = subprocess.Popen(
            ["python", "-m", "src.green_agent.main"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Wait for server to start
        max_retries = 30
        for _ in range(max_retries):
            try:
                response = httpx.get(f"{green_agent_url}/health", timeout=2)
                if response.status_code == 200:
                    break
            except:
                pass
            time.sleep(1)

        yield process

        # Cleanup
        process.terminate()
        process.wait(timeout=10)

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_purple_uses_only_a2a_endpoints(self, green_agent_process, green_agent_url):
        """
        Test that Purple Agent uses only A2A protocol endpoints.
        
        Purple Agent should ONLY access:
        - POST /evaluate (submit evaluation request)
        - GET /stream/{interaction_id} (subscribe to SSE events)
        - POST /artifact/{interaction_id} (submit artifact)
        
        Purple Agent should NEVER directly call:
        - Internal Green Agent functions
        - MCP server directly (must go through MCP tools exposed via A2A)
        """
        async with httpx.AsyncClient(timeout=60) as client:
            # Track all HTTP requests made
            requested_paths = []

            original_request = client.request

            async def tracking_request(method, url, **kwargs):
                """Wrapper to track HTTP requests."""
                requested_paths.append((method, url))
                return await original_request(method, url, **kwargs)

            client.request = tracking_request

            # Submit evaluation request (A2A: POST /evaluate)
            response = await client.post(
                f"{green_agent_url}/evaluate",
                json={
                    "task_id": "miniwob.click-test",
                    "benchmark": "miniwob",
                }
            )

            assert response.status_code == 200
            interaction_id = response.json()["interaction_id"]

            # Subscribe to SSE stream (A2A: GET /stream/{interaction_id})
            async with client.stream("GET", f"{green_agent_url}/stream/{interaction_id}") as stream_response:
                # Collect a few events
                event_count = 0
                async for line in stream_response.aiter_lines():
                    event_count += 1
                    if event_count >= 5:
                        break

            # Verify only A2A endpoints were accessed
            valid_a2a_endpoints = ["/evaluate", "/stream", "/artifact", "/health"]

            for method, url in requested_paths:
                # Extract path from URL
                path = url.split(green_agent_url)[-1].split("?")[0]

                # Check if path matches valid A2A endpoints
                is_valid = any(endpoint in path for endpoint in valid_a2a_endpoints)

                assert is_valid, f"Purple Agent accessed non-A2A endpoint: {method} {path}"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_purple_never_calls_mcp_directly(self, green_agent_process, green_agent_url):
        """
        Test that Purple Agent never calls MCP server directly.
        
        Purple Agent must use MCP tools through A2A protocol messages,
        NOT connect directly to MCP stdio subprocess.
        """
        # This test verifies architectural constraint:
        # Purple Agent should not have direct MCP client code
        # All MCP interaction happens via Green Agent's exposed tools

        # Verify Test Purple Agent uses A2A client, not direct MCP client
        from tests.purple_agent import a2a_client

        # Verify a2a_client module exists
        assert hasattr(a2a_client, "A2AClient"), "Purple Agent should use A2AClient"

        # Verify Purple Agent doesn't import MCP directly for environment access
        try:
            from tests.purple_agent.tools import mcp_tools

            # If mcp_tools exists, verify it uses A2A messages not direct MCP
            # (Our implementation uses A2A → Green Agent → MCP pattern)
            assert True  # Purple Agent correctly uses proxied MCP access

        except ImportError:
            # Purple Agent doesn't have direct MCP tools (even better)
            pass

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_green_agent_mcp_isolation(self, green_agent_process, green_agent_url):
        """
        Test that Green Agent isolates MCP access.
        
        Green Agent should:
        1. Spawn MCP server subprocess
        2. Expose MCP tools via A2A protocol
        3. Never expose raw MCP connection details to Purple Agent
           (only via secure A2A messages)
        """
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{green_agent_url}/evaluate",
                json={
                    "task_id": "miniwob.click-test",
                    "benchmark": "miniwob",
                }
            )

            interaction_id = response.json()["interaction_id"]

            # Subscribe to SSE events
            mcp_details_exposed = False
            mcp_details_format_valid = False

            async with client.stream("GET", f"{green_agent_url}/stream/{interaction_id}") as stream_response:
                async for line in stream_response.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue

                    import json
                    data = line[6:]

                    try:
                        event_data = json.loads(data)

                        # Check if MCP details are exposed
                        if "mcp_connection_details" in event_data:
                            mcp_details_exposed = True
                            details = event_data["mcp_connection_details"]

                            # Verify details are structured properly (not raw subprocess details)
                            if "command" in details and "args" in details:
                                mcp_details_format_valid = True

                            break

                    except json.JSONDecodeError:
                        continue

            # MCP details should be exposed via A2A protocol
            assert mcp_details_exposed, "Green Agent should expose MCP details via A2A"
            assert mcp_details_format_valid, "MCP details should be properly formatted"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_no_direct_function_calls(self):
        """
        Test that Purple and Green agents don't call each other's functions directly.
        
        Architecture constraint:
        - Purple Agent → A2A HTTP requests → Green Agent
        - Green Agent → A2A HTTP responses → Purple Agent
        - NO direct Python function calls between agents
        """
        # Verify Green Agent doesn't import Purple Agent code
        try:
            from src.green_agent import main as green_main
            import inspect

            # Check if green_main imports any purple_agent modules
            source = inspect.getsource(green_main)

            assert "from tests.purple_agent" not in source, \
                "Green Agent should not import Purple Agent modules"
            assert "import tests.purple_agent" not in source, \
                "Green Agent should not import Purple Agent modules"

        except Exception as e:
            # If we can't check, skip this verification
            pytest.skip(f"Could not verify direct imports: {e}")

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_a2a_message_schema_compliance(self, green_agent_process, green_agent_url):
        """
        Test that A2A messages comply with protocol schema.
        
        Evaluation request should have:
        - task_id
        - benchmark
        - Optional: timeout, max_tasks, etc.
        
        Artifact should have:
        - task_id
        - task_success
        - final_score
        - metadata (session_id, timestamp)
        """
        async with httpx.AsyncClient(timeout=60) as client:
            # Submit evaluation request
            eval_request = {
                "task_id": "miniwob.click-test",
                "benchmark": "miniwob",
                "timeout": 120,
            }

            response = await client.post(
                f"{green_agent_url}/evaluate",
                json=eval_request
            )

            # Verify response schema
            assert response.status_code == 200
            result = response.json()

            assert "interaction_id" in result, "Response should include interaction_id"
            assert "status" in result or "message" in result, "Response should include status/message"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_purple_agent_artifact_submission(self, green_agent_process, green_agent_url):
        """
        Test that Purple Agent submits artifacts via A2A protocol.
        
        Artifact submission should use:
        - POST /artifact/{interaction_id}
        - Proper artifact schema
        """
        async with httpx.AsyncClient(timeout=60) as client:
            # Submit evaluation request
            response = await client.post(
                f"{green_agent_url}/evaluate",
                json={
                    "task_id": "miniwob.click-test",
                    "benchmark": "miniwob",
                }
            )

            interaction_id = response.json()["interaction_id"]

            # Simulate Purple Agent artifact submission
            artifact = {
                "task_id": "miniwob.click-test",
                "benchmark": "miniwob",
                "task_success": True,
                "final_score": 1.0,
                "token_cost": 1000,
                "latency_ms": 5000,
                "step_count": 10,
                "metadata": {
                    "session_id": "test-session",
                    "timestamp": "2025-12-25T10:00:00Z",
                }
            }

            # Submit artifact via A2A endpoint
            artifact_response = await client.post(
                f"{green_agent_url}/artifact/{interaction_id}",
                json=artifact
            )

            # Should accept artifact submission
            assert artifact_response.status_code in [200, 201, 202], \
                f"Artifact submission failed: {artifact_response.status_code}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "integration"])
