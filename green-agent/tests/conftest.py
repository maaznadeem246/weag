"""Test configuration and fixtures for green-agent A2A conformance tests."""
import httpx
import pytest


def pytest_addoption(parser):
    """Add command line options for agent testing."""
    parser.addoption(
        "--agent-url",
        default="http://localhost:9009",
        help="Green Agent URL (default: http://localhost:9009)",
    )


@pytest.fixture(scope="session")
def agent(request):
    """Agent URL fixture. Agent must be running before tests start."""
    url = request.config.getoption("--agent-url")

    try:
        response = httpx.get(f"{url}/.well-known/agent-card.json", timeout=5)
        if response.status_code != 200:
            pytest.exit(f"Agent at {url} returned status {response.status_code}", returncode=1)
    except Exception as e:
        pytest.exit(f"Could not connect to agent at {url}: {e}", returncode=1)

    return url
