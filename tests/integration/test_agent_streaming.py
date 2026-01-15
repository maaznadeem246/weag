"""
Integration test for agent streaming.

Tests SSE streaming of agent events (thinking, tool calls, guardrails).
Implements T112: Integration test for agent streaming.
"""

import asyncio
import json
import subprocess
import time

import httpx
import pytest


class TestAgentStreaming:
    """Test agent SSE streaming functionality."""

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
    async def test_sse_connection(self, green_agent_process, green_agent_url):
        """Test SSE connection establishment."""
        async with httpx.AsyncClient(timeout=30) as client:
            # Submit evaluation request
            response = await client.post(
                f"{green_agent_url}/evaluate",
                json={
                    "task_id": "miniwob.click-test",
                    "benchmark": "miniwob",
                }
            )

            assert response.status_code == 200
            interaction_id = response.json()["interaction_id"]

            # Connect to SSE stream
            async with client.stream("GET", f"{green_agent_url}/stream/{interaction_id}") as stream_response:
                assert stream_response.status_code == 200
                assert "text/event-stream" in stream_response.headers.get("content-type", "")

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_streaming_events_emitted(self, green_agent_process, green_agent_url):
        """Test that streaming events are emitted during evaluation."""
        async with httpx.AsyncClient(timeout=120) as client:
            # Submit evaluation request
            response = await client.post(
                f"{green_agent_url}/evaluate",
                json={
                    "task_id": "miniwob.click-test",
                    "benchmark": "miniwob",
                }
            )

            interaction_id = response.json()["interaction_id"]

            # Collect events from SSE stream
            events = []
            event_types = set()

            async with client.stream("GET", f"{green_agent_url}/stream/{interaction_id}") as stream_response:
                async for line in stream_response.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue

                    data = line[6:]
                    try:
                        event_data = json.loads(data)
                        events.append(event_data)

                        # Track event types
                        if "event_type" in event_data:
                            event_types.add(event_data["event_type"])

                        # Stop after reasonable number of events
                        if len(events) > 50 or event_data.get("status") == "complete":
                            break
                    except json.JSONDecodeError:
                        continue

            # Verify events were emitted
            assert len(events) > 0, "Should emit at least one event"

            # Verify expected event types present
            expected_types = ["agent_thinking", "tool_call", "tool_result"]
            found_types = [t for t in expected_types if t in event_types]
            assert len(found_types) > 0, f"Should emit at least one of {expected_types}"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_streaming_mcp_details_event(self, green_agent_process, green_agent_url):
        """Test that MCP connection details are streamed."""
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{green_agent_url}/evaluate",
                json={
                    "task_id": "miniwob.click-test",
                    "benchmark": "miniwob",
                }
            )

            interaction_id = response.json()["interaction_id"]

            mcp_details_found = False

            async with client.stream("GET", f"{green_agent_url}/stream/{interaction_id}") as stream_response:
                async for line in stream_response.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue

                    data = line[6:]
                    try:
                        event_data = json.loads(data)

                        # Check for MCP connection details
                        if "mcp_connection_details" in event_data:
                            mcp_details_found = True
                            details = event_data["mcp_connection_details"]

                            # Verify details structure
                            assert "command" in details
                            assert "args" in details
                            break

                    except json.JSONDecodeError:
                        continue

            assert mcp_details_found, "Should stream MCP connection details"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_streaming_guardrail_events(self, green_agent_process, green_agent_url):
        """Test that guardrail validation events are streamed."""
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{green_agent_url}/evaluate",
                json={
                    "task_id": "miniwob.click-test",
                    "benchmark": "miniwob",
                }
            )

            interaction_id = response.json()["interaction_id"]

            guardrail_events = []

            async with client.stream("GET", f"{green_agent_url}/stream/{interaction_id}") as stream_response:
                async for line in stream_response.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue

                    data = line[6:]
                    try:
                        event_data = json.loads(data)

                        # Collect guardrail events
                        if event_data.get("event_type") == "guardrail":
                            guardrail_events.append(event_data)

                        # Stop after collecting some events
                        if len(guardrail_events) >= 2 or event_data.get("status") == "complete":
                            break

                    except json.JSONDecodeError:
                        continue

            # Should have at least input guardrail event
            # (Output guardrail may occur later)
            assert len(guardrail_events) > 0, "Should emit guardrail events"

            # Verify guardrail event structure
            for event in guardrail_events:
                assert "guardrail_type" in event
                assert event["guardrail_type"] in ["input", "output"]
                assert "validation_result" in event

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_streaming_multiple_clients(self, green_agent_process, green_agent_url):
        """Test multiple clients can subscribe to same evaluation stream."""
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{green_agent_url}/evaluate",
                json={
                    "task_id": "miniwob.click-test",
                    "benchmark": "miniwob",
                }
            )

            interaction_id = response.json()["interaction_id"]

            # Create multiple stream connections
            async def collect_events(client_id: int):
                events = []
                async with httpx.AsyncClient(timeout=60) as c:
                    async with c.stream("GET", f"{green_agent_url}/stream/{interaction_id}") as stream_response:
                        async for line in stream_response.aiter_lines():
                            if not line or not line.startswith("data: "):
                                continue

                            data = line[6:]
                            try:
                                event_data = json.loads(data)
                                events.append(event_data)

                                if len(events) >= 10 or event_data.get("status") == "complete":
                                    break
                            except:
                                continue
                return len(events)

            # Collect events from multiple clients concurrently
            results = await asyncio.gather(
                collect_events(1),
                collect_events(2),
                collect_events(3),
            )

            # All clients should receive events
            assert all(count > 0 for count in results), "All clients should receive events"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "integration"])
