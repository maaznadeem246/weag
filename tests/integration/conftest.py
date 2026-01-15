"""
Pytest configuration for integration tests.

Implements T010: Integration test framework setup.
"""

import os
import pytest
from pathlib import Path


@pytest.fixture(scope="session")
def project_root():
    """Get project root directory."""
    return Path(__file__).parent.parent.parent


@pytest.fixture(scope="session")
def datasets_dir(project_root):
    """Get datasets directory."""
    return project_root / "datasets"


@pytest.fixture(scope="session")
def miniwob_dataset_path(datasets_dir):
    """Get MiniWoB dataset path."""
    miniwob_path = datasets_dir / "miniwob" / "html" / "miniwob"
    if miniwob_path.exists():
        return miniwob_path
    return None


@pytest.fixture(scope="function")
def set_miniwob_env(miniwob_dataset_path):
    """Set MINIWOB_URL environment variable for tests."""
    if miniwob_dataset_path:
        original = os.environ.get("MINIWOB_URL")
        os.environ["MINIWOB_URL"] = f"file:///{miniwob_dataset_path.resolve().as_posix()}/"
        yield
        # Restore original
        if original:
            os.environ["MINIWOB_URL"] = original
        else:
            os.environ.pop("MINIWOB_URL", None)
    else:
        yield


@pytest.fixture(scope="function")
def temp_output_dir(tmp_path):
    """Create temporary output directory for test artifacts."""
    output_dir = tmp_path / "test_output"
    output_dir.mkdir(exist_ok=True)
    return output_dir


@pytest.fixture(scope="function")
def mock_env_vars():
    """Fixture for setting temporary environment variables."""
    original_env = os.environ.copy()
    
    def _set_env(**kwargs):
        for key, value in kwargs.items():
            os.environ[key] = str(value)
    
    yield _set_env
    
    # Restore original environment
    os.environ.clear()
    os.environ.update(original_env)


# Mark slow tests
def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )
    config.addinivalue_line(
        "markers", "requires_api_key: marks tests that require API keys"
    )
