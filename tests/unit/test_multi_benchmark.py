"""
Unit tests for multi-benchmark support (T055-T060).

Tests environment initialization for all six BrowserGym benchmarks:
- MiniWoB (T055)
- WebArena (T056)
- VisualWebArena (T057)
- WorkArena (T058)
- AssistantBench (T059)
- WebLINX (T060)
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from src.green_agent.environment.entities import EnvironmentConfig, EnvironmentSession
from src.green_agent.environment.session_manager import SessionManager


class TestMultiBenchmarkSupport:
    """Test multi-benchmark support for all six BrowserGym benchmarks."""
    
    @pytest.fixture
    def session_manager(self):
        """Create session manager instance."""
        return SessionManager()
    
    @pytest.fixture
    def mock_gym_env(self):
        """Create mock gymnasium environment."""
        env = Mock()
        env.reset = Mock(return_value=({"obs": "initial"}, {"info": "data"}))
        env.step = Mock(return_value=({"obs": "next"}, 1.0, False, False, {"info": "data"}))
        env.close = Mock()
        return env
    
    # T055: Test MiniWoB benchmark integration
    def test_miniwob_benchmark_integration(self, session_manager, mock_gym_env):
        """Test MiniWoB benchmark with sample task (click-test)."""
        config = EnvironmentConfig(
            task_id="miniwob.click-test",
            max_steps=50,
            seed=42
        )
        
        # Validate task_id
        is_valid, error_msg = config.validate_task_id()
        assert is_valid, f"MiniWoB task_id validation failed: {error_msg}"
        
        # Check benchmark extraction
        assert config.get_benchmark() == "miniwob"
        
        # Check that config has task-specific parameters
        assert config.max_steps == 50
        assert config.seed == 42
        assert config.task_id == "miniwob.click-test"
        
        # Check benchmark-specific config (should be empty for BrowserGym)
        benchmark_config = config.get_benchmark_specific_config()
        assert isinstance(benchmark_config, dict)
        
        # Test environment creation
        with patch("gymnasium.make", return_value=mock_gym_env):
            session = session_manager.create_session(config)
            assert session.benchmark == "miniwob"
            assert session.task_id == "miniwob.click-test"
            mock_gym_env.reset.assert_called_once()
    
    # T056: Test WebArena benchmark integration
    def test_webarena_benchmark_integration(self, session_manager, mock_gym_env):
        """Test WebArena benchmark with sample task."""
        config = EnvironmentConfig(
            task_id="webarena.shopping-search",
            start_url="https://www.example.com",
            max_steps=100
        )
        
        # Validate task_id
        is_valid, error_msg = config.validate_task_id()
        assert is_valid, f"WebArena task_id validation failed: {error_msg}"
        
        # Check benchmark extraction
        assert config.get_benchmark() == "webarena"
        
        # Check that config has task-specific parameters
        assert config.max_steps == 100
        assert config.start_url == "https://www.example.com"
        assert config.task_id == "webarena.shopping-search"
        
        # Check benchmark-specific config (should be empty for BrowserGym)
        benchmark_config = config.get_benchmark_specific_config()
        assert isinstance(benchmark_config, dict)
        
        # Test environment creation
        with patch("gymnasium.make", return_value=mock_gym_env):
            session = session_manager.create_session(config)
            assert session.benchmark == "webarena"
            assert session.task_id == "webarena.shopping-search"
    
    # T057: Test VisualWebArena benchmark integration
    def test_visualwebarena_benchmark_integration(self, session_manager, mock_gym_env):
        """Test VisualWebArena benchmark with sample task."""
        config = EnvironmentConfig(
            task_id="visualwebarena.image-search",
            start_url="https://www.example.com/images",
            max_steps=75
        )
        
        # Validate task_id
        is_valid, error_msg = config.validate_task_id()
        assert is_valid, f"VisualWebArena task_id validation failed: {error_msg}"
        
        # Check benchmark extraction
        assert config.get_benchmark() == "visualwebarena"
        
        # Check that config has task-specific parameters
        assert config.start_url == "https://www.example.com/images"
        assert config.max_steps == 75
        
        # Check benchmark-specific config (should be empty for BrowserGym)
        benchmark_config = config.get_benchmark_specific_config()
        assert isinstance(benchmark_config, dict)
        
        # Test environment creation
        with patch("gymnasium.make", return_value=mock_gym_env):
            session = session_manager.create_session(config)
            assert session.benchmark == "visualwebarena"
            assert session.task_id == "visualwebarena.image-search"
    
    # T058: Test WorkArena benchmark integration
    def test_workarena_benchmark_integration(self, session_manager, mock_gym_env):
        """Test WorkArena benchmark with sample task."""
        config = EnvironmentConfig(
            task_id="workarena.servicenow-task",
            max_steps=100,
            seed=123
        )
        
        # Validate task_id
        is_valid, error_msg = config.validate_task_id()
        assert is_valid, f"WorkArena task_id validation failed: {error_msg}"
        
        # Check benchmark extraction
        assert config.get_benchmark() == "workarena"
        
        # Check that config has task-specific parameters
        assert config.max_steps == 100
        assert config.seed == 123
        
        # Check benchmark-specific config (should be empty for BrowserGym)
        benchmark_config = config.get_benchmark_specific_config()
        assert isinstance(benchmark_config, dict)
        
        # Test environment creation
        with patch("gymnasium.make", return_value=mock_gym_env):
            session = session_manager.create_session(config)
            assert session.benchmark == "workarena"
            assert session.task_id == "workarena.servicenow-task"
    
    # T059: Test AssistantBench benchmark integration
    def test_assistantbench_benchmark_integration(self, session_manager, mock_gym_env):
        """Test AssistantBench benchmark with sample task."""
        config = EnvironmentConfig(
            task_id="assistantbench.email-task",
            max_steps=60
        )
        
        # Validate task_id
        is_valid, error_msg = config.validate_task_id()
        assert is_valid, f"AssistantBench task_id validation failed: {error_msg}"
        
        # Check benchmark extraction
        assert config.get_benchmark() == "assistantbench"
        
        # Check that config has task-specific parameters
        assert config.max_steps == 60
        assert config.task_id == "assistantbench.email-task"
        
        # Check benchmark-specific config (should be empty for BrowserGym)
        benchmark_config = config.get_benchmark_specific_config()
        assert isinstance(benchmark_config, dict)
        
        # Test environment creation
        with patch("gymnasium.make", return_value=mock_gym_env):
            session = session_manager.create_session(config)
            assert session.benchmark == "assistantbench"
            assert session.task_id == "assistantbench.email-task"
    
    # T060: Test WebLINX benchmark integration
    def test_weblinx_benchmark_integration(self, session_manager, mock_gym_env):
        """Test WebLINX benchmark with sample task."""
        config = EnvironmentConfig(
            task_id="weblinx.navigation-task",
            start_url="https://www.example.com",
            max_steps=80,
            seed=456
        )
        
        # Validate task_id
        is_valid, error_msg = config.validate_task_id()
        assert is_valid, f"WebLINX task_id validation failed: {error_msg}"
        
        # Check benchmark extraction
        assert config.get_benchmark() == "weblinx"
        
        # Check that config has task-specific parameters
        assert config.start_url == "https://www.example.com"
        assert config.max_steps == 80
        assert config.seed == 456
        
        # Check benchmark-specific config (should be empty for BrowserGym)
        benchmark_config = config.get_benchmark_specific_config()
        assert isinstance(benchmark_config, dict)
        
        # Test environment creation
        with patch("gymnasium.make", return_value=mock_gym_env):
            session = session_manager.create_session(config)
            assert session.benchmark == "weblinx"
            assert session.task_id == "weblinx.navigation-task"
    
    def test_invalid_benchmark_validation(self):
        """Test validation rejects invalid benchmarks."""
        config = EnvironmentConfig(task_id="invalid-benchmark.task")
        is_valid, error_msg = config.validate_task_id()
        assert not is_valid
        assert "Unsupported benchmark" in error_msg
    
    def test_empty_task_id_validation(self):
        """Test validation rejects empty task_id."""
        config = EnvironmentConfig(task_id="")
        is_valid, error_msg = config.validate_task_id()
        assert not is_valid
        assert "cannot be empty" in error_msg
    
    def test_missing_task_name_validation(self):
        """Test validation rejects task_id without task name."""
        config = EnvironmentConfig(task_id="miniwob.")
        is_valid, error_msg = config.validate_task_id()
        assert not is_valid
        assert "task name" in error_msg
    
    def test_no_dot_in_task_id_validation(self):
        """Test validation rejects task_id without dot separator."""
        config = EnvironmentConfig(task_id="miniwobclicktest")
        is_valid, error_msg = config.validate_task_id()
        assert not is_valid
        assert "benchmark.task-name" in error_msg
    
    def test_all_benchmarks_supported(self):
        """Test all six benchmarks are in supported list."""
        expected_benchmarks = [
            "miniwob",
            "webarena",
            "visualwebarena",
            "workarena",
            "assistantbench",
            "weblinx"
        ]
        config = EnvironmentConfig(task_id="miniwob.test")
        assert config.SUPPORTED_BENCHMARKS == expected_benchmarks
    
    def test_case_insensitive_benchmark_extraction(self):
        """Test benchmark extraction is case-insensitive."""
        config = EnvironmentConfig(task_id="MiniWoB.Click-Test")
        assert config.get_benchmark() == "miniwob"
        
        is_valid, _ = config.validate_task_id()
        assert is_valid
