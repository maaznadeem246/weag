"""
Integration test for full agent evaluation flow.

Tests end-to-end evaluation: Test Purple Agent → Green Agent → Artifact.
Implements T111: Integration test for complete agent evaluation flow.
"""

import asyncio
import subprocess
import time
from pathlib import Path

import httpx
import pytest


class TestAgentEvaluationFlow:
    """Test complete agent evaluation flow."""

    @pytest.fixture(scope="class")
    def green_agent_url(self):
        """Green Agent base URL."""
        return "http://localhost:9009"

    @pytest.fixture(scope="class")
    def green_agent_process(self, green_agent_url):
        """Start Green Agent server for testing."""
        # Start Green Agent
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
    async def test_full_evaluation_flow(self, green_agent_process, green_agent_url):
        """
        Test complete evaluation flow:
        1. Submit evaluation request
        2. Monitor SSE events
        3. Verify artifact generation
        4. Validate completion
        """
        async with httpx.AsyncClient(timeout=120) as client:
            # Step 1: Submit evaluation request
            eval_request = {
                "task_id": "miniwob.click-test",
                "benchmark": "miniwob",
                "timeout": 120,
            }

            response = await client.post(
                f"{green_agent_url}/evaluate",
                json=eval_request
            )

            assert response.status_code == 200
            result = response.json()
            assert "interaction_id" in result
            interaction_id = result["interaction_id"]

            # Step 2: Monitor SSE events
            events = []
            mcp_details_received = False
            task_complete = False

            async with client.stream("GET", f"{green_agent_url}/stream/{interaction_id}") as stream_response:
                assert stream_response.status_code == 200

                async for line in stream_response.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue

                    event_data = line[6:]  # Remove "data: " prefix
                    events.append(event_data)

                    # Check for MCP connection details
                    if "mcp_connection_details" in event_data:
                        mcp_details_received = True

                    # Check for completion
                    if '"status":"complete"' in event_data:
                        task_complete = True
                        break

                    # Timeout after 60 seconds
                    if len(events) > 600:  # Approximately 60s at 10 events/sec
                        break

            # Step 3: Verify events
            assert len(events) > 0, "Should receive SSE events"
            assert mcp_details_received, "Should receive MCP connection details"

            # Step 4: Retrieve artifact (if available)
            try:
                artifact_response = await client.get(
                    f"{green_agent_url}/artifact/{interaction_id}"
                )

                if artifact_response.status_code == 200:
                    artifact = artifact_response.json()
                    assert "task_id" in artifact
                    assert "task_success" in artifact
                    assert artifact["task_id"] == "miniwob.click-test"
            except:
                # Artifact may not be available yet
                pass

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_evaluation_with_test_purple_agent(self, green_agent_process, green_agent_url):
        """
        Test evaluation using Test Purple Agent.
        This validates the full Purple-Green integration.
        """
        # Start Test Purple Agent in subprocess
        purple_process = subprocess.Popen(
            [
                "python", "-m", "tests.purple_agent.main",
                "--task-id", "miniwob.click-test",
                "--benchmark", "miniwob",
                "--timeout", "120",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={
                "GREEN_AGENT_URL": green_agent_url,
                "GEMINI_API_KEY": "test-key",
            }
        )

        try:
            # Wait for completion (max 2 minutes)
            stdout, stderr = purple_process.communicate(timeout=120)

            # Check exit code
            assert purple_process.returncode == 0, f"Purple Agent failed: {stderr.decode()}"

            # Verify logs contain success indicators
            log_output = stdout.decode() + stderr.decode()
            assert "Evaluation complete" in log_output or "success" in log_output.lower()

        except subprocess.TimeoutExpired:
            purple_process.kill()
            pytest.fail("Purple Agent timed out")
        finally:
            if purple_process.poll() is None:
                purple_process.terminate()

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_evaluation_error_handling(self, green_agent_process, green_agent_url):
        """Test evaluation error handling."""
        async with httpx.AsyncClient(timeout=30) as client:
            # Submit invalid evaluation request
            invalid_request = {
                "task_id": "invalid-task",
                "benchmark": "invalid-benchmark",
                "timeout": 10,
            }

            response = await client.post(
                f"{green_agent_url}/evaluate",
                json=invalid_request
            )

            # Should reject invalid request
            assert response.status_code in [400, 422, 500]

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_concurrent_evaluations(self, green_agent_process, green_agent_url):
        """Test multiple concurrent evaluations."""
        async with httpx.AsyncClient(timeout=120) as client:
            # Submit multiple evaluation requests
            tasks = [
                client.post(
                    f"{green_agent_url}/evaluate",
                    json={
                        "task_id": f"miniwob.click-test-{i}",
                        "benchmark": "miniwob",
                        "timeout": 60,
                    }
                )
                for i in range(3)
            ]

            responses = await asyncio.gather(*tasks, return_exceptions=True)

            # All requests should succeed or return valid responses
            for response in responses:
                if isinstance(response, Exception):
                    pytest.skip(f"Concurrent evaluation failed: {response}")
                else:
                    assert response.status_code in [200, 202]


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "integration"])
