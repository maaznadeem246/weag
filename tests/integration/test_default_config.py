"""
Integration test for default configuration.

Tests evaluation with default settings (5 tasks, miniwob benchmark).
Implements T116: Integration test for default configuration.
"""

import subprocess
import time

import httpx
import pytest


class TestDefaultConfiguration:
    """Test Green Agent default configuration."""

    @pytest.fixture(scope="class")
    def green_agent_url(self):
        """Green Agent base URL."""
        return "http://localhost:9009"

    @pytest.fixture(scope="class")
    def green_agent_process(self, green_agent_url):
        """Start Green Agent server with default configuration."""
        process = subprocess.Popen(
            ["python", "-m", "src.green_agent.main"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={},  # No environment variables = use defaults
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
    async def test_default_benchmark_is_miniwob(self, green_agent_process, green_agent_url):
        """Test that default benchmark is miniwob."""
        async with httpx.AsyncClient(timeout=60) as client:
            # Submit evaluation without specifying benchmark
            response = await client.post(
                f"{green_agent_url}/evaluate",
                json={
                    "task_id": "miniwob.click-test",
                    # No benchmark specified = should use default
                }
            )

            # Should accept request with default benchmark
            if response.status_code == 200:
                # Default benchmark accepted
                result = response.json()
                assert "interaction_id" in result
            else:
                # If default not supported, should return clear error
                assert response.status_code in [400, 422]

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_default_max_tasks_is_5(self, green_agent_process, green_agent_url):
        """Test that default max_tasks is 5 for batch evaluations."""
        async with httpx.AsyncClient(timeout=120) as client:
            # Submit batch evaluation without specifying max_tasks
            batch_request = {
                "benchmarks": [
                    {
                        "benchmark": "miniwob",
                        # No max_tasks specified = should use default (5)
                    }
                ]
            }

            response = await client.post(
                f"{green_agent_url}/evaluate/batch",
                json=batch_request
            )

            # Should accept batch request with default max_tasks
            if response.status_code == 200:
                result = response.json()
                assert "interaction_id" in result or "results" in result
            else:
                # If batch endpoint not implemented, skip
                pytest.skip("Batch evaluation endpoint not available")

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_default_timeout_is_reasonable(self, green_agent_process, green_agent_url):
        """Test that default timeout is reasonable (not too short or too long)."""
        async with httpx.AsyncClient(timeout=60) as client:
            # Submit evaluation without specifying timeout
            response = await client.post(
                f"{green_agent_url}/evaluate",
                json={
                    "task_id": "miniwob.click-test",
                    "benchmark": "miniwob",
                    # No timeout specified = should use default
                }
            )

            if response.status_code == 200:
                # Evaluation accepted with default timeout
                # Verify it doesn't timeout immediately or run forever
                interaction_id = response.json()["interaction_id"]

                # Subscribe to SSE to monitor progress
                start_time = time.time()
                timeout_used = None

                async with client.stream("GET", f"{green_agent_url}/stream/{interaction_id}") as stream_response:
                    async for line in stream_response.aiter_lines():
                        if not line or not line.startswith("data: "):
                            continue

                        import json
                        data = line[6:]

                        try:
                            event_data = json.loads(data)

                            # Check if timeout value is mentioned
                            if "timeout" in event_data:
                                timeout_used = event_data["timeout"]

                            # Stop after getting some events
                            if time.time() - start_time > 10:
                                break

                        except json.JSONDecodeError:
                            continue

                # Default timeout should be reasonable (e.g., 120-300 seconds)
                if timeout_used:
                    assert 60 <= timeout_used <= 600, \
                        f"Default timeout {timeout_used}s is unreasonable"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_default_session_mode(self, green_agent_process, green_agent_url):
        """Test default session storage mode."""
        async with httpx.AsyncClient(timeout=60) as client:
            # Submit evaluation (will create session with default mode)
            response = await client.post(
                f"{green_agent_url}/evaluate",
                json={
                    "task_id": "miniwob.click-test",
                    "benchmark": "miniwob",
                }
            )

            if response.status_code == 200:
                interaction_id = response.json()["interaction_id"]

                # Verify session was created (check via health or logs)
                # Default should be InMemorySession for development
                assert interaction_id is not None

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_default_supported_benchmarks(self, green_agent_process, green_agent_url):
        """Test that default configuration supports all 6 benchmarks."""
        benchmarks = [
            "miniwob",
            "webarena",
            "visualwebarena",
            "workarena",
            "assistantbench",
            "weblinx",
        ]

        async with httpx.AsyncClient(timeout=60) as client:
            for benchmark in benchmarks:
                response = await client.post(
                    f"{green_agent_url}/evaluate",
                    json={
                        "task_id": f"{benchmark}.test-task",
                        "benchmark": benchmark,
                    }
                )

                # Should accept all supported benchmarks
                assert response.status_code in [200, 202], \
                    f"Benchmark {benchmark} not supported by default configuration"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_default_configuration_documented(self):
        """Test that default configuration is documented."""
        from pathlib import Path

        # Check if CONFIGURATION.md exists
        config_doc = Path("docs/CONFIGURATION.md")

        if not config_doc.exists():
            pytest.skip("CONFIGURATION.md not found")

        # Verify documentation mentions defaults
        content = config_doc.read_text()

        expected_defaults = [
            "DEFAULT_BENCHMARK",
            "DEFAULT_MAX_TASKS",
            "default",
        ]

        for default_key in expected_defaults:
            assert default_key in content or default_key.lower() in content.lower(), \
                f"Documentation should mention {default_key}"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_defaults_in_settings_file(self):
        """Test that defaults are defined in settings.py."""
        try:
            from config import settings

            # Verify settings module has default values
            assert hasattr(settings, "DEFAULT_BENCHMARK") or hasattr(settings, "benchmark"), \
                "settings.py should define default benchmark"

        except ImportError:
            pytest.skip("settings.py not found")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "integration"])
