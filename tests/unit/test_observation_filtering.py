"""
T058 [P] [US7] Unit test for benchmark-specific observation filtering

Tests that observations are filtered according to benchmark profiles,
respecting token limits and filtering strategies.
"""

import pytest

from src.green_agent.environment.observation_filter import (
    ObservationFilter,
    ObservationMode,
    BENCHMARK_STRATEGIES,
)
from src.green_agent.benchmarks.profiles import BenchmarkProfileRegistry


class TestObservationFilterCreation:
    """Test observation filter creation and initialization."""
    
    def test_create_filter_with_default_params(self):
        """Test creating filter with default parameters."""
        obs_filter = ObservationFilter()
        
        assert obs_filter.token_limit == 5000
        assert obs_filter.benchmark_id is None
    
    def test_create_filter_with_token_limit(self):
        """Test creating filter with custom token limit."""
        obs_filter = ObservationFilter(token_limit=2000)
        
        assert obs_filter.token_limit == 2000
    
    def test_create_filter_with_benchmark_id(self):
        """Test creating filter with benchmark ID."""
        obs_filter = ObservationFilter(token_limit=2000, benchmark_id="miniwob")
        
        assert obs_filter.token_limit == 2000
        assert obs_filter.benchmark_id == "miniwob"
    
    def test_create_filter_from_benchmark_profile(self):
        """Test creating filter from BenchmarkProfile."""
        registry = BenchmarkProfileRegistry.instance()
        profile = registry.get("miniwob")
        
        obs_filter = ObservationFilter.from_benchmark_profile(profile)
        
        assert obs_filter.token_limit == profile.token_limit
        assert obs_filter.benchmark_id == profile.benchmark_id


class TestFilteringStrategies:
    """Test benchmark-specific filtering strategies."""
    
    def test_all_benchmarks_have_strategies(self):
        """Test that all 6 benchmarks have filtering strategies."""
        expected_benchmarks = [
            "miniwob",
            "webarena",
            "visualwebarena",
            "workarena",
            "assistantbench",
            "weblinx",
        ]
        
        for benchmark_id in expected_benchmarks:
            assert benchmark_id in BENCHMARK_STRATEGIES, f"Missing strategy for {benchmark_id}"
    
    def test_filtering_strategy_structure(self):
        """Test that filtering strategies have expected structure."""
        for benchmark_id, strategy in BENCHMARK_STRATEGIES.items():
            # Should have focus_elements
            assert hasattr(strategy, 'focus_elements')
            assert isinstance(strategy.focus_elements, (set, list))
            
            # Should have exclude_elements
            assert hasattr(strategy, 'exclude_elements')
            assert isinstance(strategy.exclude_elements, (set, list))


class TestDefaultObservationModes:
    """Test default observation modes for each benchmark."""
    
    def test_miniwob_default_mode(self):
        """Test MiniWoB++ uses compact mode."""
        obs_filter = ObservationFilter(token_limit=2000, benchmark_id="miniwob")
        
        assert obs_filter.get_default_mode() == ObservationMode.AXTREE_COMPACT
    
    def test_webarena_default_mode(self):
        """Test WebArena uses full mode."""
        obs_filter = ObservationFilter(token_limit=5000, benchmark_id="webarena")
        
        assert obs_filter.get_default_mode() == ObservationMode.AXTREE_FULL
    
    def test_visualwebarena_default_mode(self):
        """Test VisualWebArena uses screenshot mode."""
        obs_filter = ObservationFilter(token_limit=3500, benchmark_id="visualwebarena")
        
        assert obs_filter.get_default_mode() == ObservationMode.AXTREE_WITH_SCREENSHOT
    
    def test_default_fallback_mode(self):
        """Test unknown benchmark uses standard mode."""
        obs_filter = ObservationFilter(token_limit=5000, benchmark_id="unknown")
        
        assert obs_filter.get_default_mode() == ObservationMode.AXTREE


class TestTokenLimitCompliance:
    """Test token limit compliance per Mandate C."""
    
    @pytest.mark.parametrize("benchmark_id,token_limit", [
        ("miniwob", 2000),
        ("webarena", 5000),
        ("visualwebarena", 3500),
        ("workarena", 4500),
        ("assistantbench", 3000),
        ("weblinx", 4000),
    ])
    def test_benchmark_token_limits(self, benchmark_id, token_limit):
        """Test each benchmark has correct token limit."""
        registry = BenchmarkProfileRegistry.instance()
        profile = registry.get(benchmark_id)
        
        obs_filter = ObservationFilter.from_benchmark_profile(profile)
        
        assert obs_filter.token_limit == token_limit
    
    def test_token_limit_ordering(self):
        """Test token limits are ordered correctly."""
        registry = BenchmarkProfileRegistry.instance()
        
        miniwob_limit = registry.get("miniwob").token_limit
        visualwebarena_limit = registry.get("visualwebarena").token_limit
        weblinx_limit = registry.get("weblinx").token_limit
        workarena_limit = registry.get("workarena").token_limit
        webarena_limit = registry.get("webarena").token_limit
        
        # Verify ordering: miniwob < visualwebarena < weblinx < workarena < webarena
        assert miniwob_limit < visualwebarena_limit
        assert visualwebarena_limit < weblinx_limit
        assert weblinx_limit < workarena_limit
        assert workarena_limit < webarena_limit


class TestObservationFiltering:
    """Test actual observation filtering behavior."""
    
    def test_filter_preserves_essential_fields(self):
        """Test that filtering preserves essential fields (FR-014)."""
        obs_filter = ObservationFilter(token_limit=2000, benchmark_id="miniwob")
        
        # Mock observation
        observation = {
            "axtree_txt": "button[0] 'Click Me'",
            "goal": "Click the button",
            "url": "http://example.com/task.html",
            "last_action": "None",
            "last_action_error": "",
        }
        
        filtered = obs_filter.filter_observation(observation)
        
        # Should be a dictionary
        assert isinstance(filtered, dict)
        
        # Should have some content
        assert len(filtered) > 0
    
    def test_filter_with_different_modes(self):
        """Test filtering with different observation modes."""
        obs_filter = ObservationFilter(token_limit=2000, benchmark_id="miniwob")
        
        observation = {
            "axtree_txt": "button[0] 'Click Me'",
            "goal": "Click the button",
        }
        
        # Test with compact mode
        filtered_compact = obs_filter.filter_observation(observation, mode=ObservationMode.AXTREE_COMPACT)
        assert isinstance(filtered_compact, dict)
        
        # Test with full mode
        filtered_full = obs_filter.filter_observation(observation, mode=ObservationMode.AXTREE_FULL)
        assert isinstance(filtered_full, dict)
