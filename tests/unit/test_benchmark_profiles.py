"""
T028 [P] [US3] Unit test for benchmark profile selection

Tests that benchmark profiles are correctly selected based on task_id prefix
and that each profile has appropriate configuration.
"""

import pytest

from src.green_agent.benchmarks.profiles import (
    BenchmarkProfile,
    BenchmarkProfileRegistry,
    ObservationMode,
    detect_benchmark,
)


class TestBenchmarkProfileRegistry:
    """Test BenchmarkProfileRegistry functionality."""
    
    def test_registry_singleton(self):
        """Test that registry is a singleton."""
        registry1 = BenchmarkProfileRegistry()
        registry2 = BenchmarkProfileRegistry()
        
        assert registry1 is registry2
    
    def test_all_benchmarks_registered(self):
        """Test that all 6 benchmarks are registered."""
        registry = BenchmarkProfileRegistry()
        
        expected_benchmarks = [
            "miniwob",
            "webarena",
            "visualwebarena",
            "workarena",
            "assistantbench",
            "weblinx",
        ]
        
        supported = registry.supported_benchmarks()
        for benchmark_id in expected_benchmarks:
            assert benchmark_id in supported, f"Missing profile: {benchmark_id}"
    
    def test_get_profile_valid(self):
        """Test getting valid profiles."""
        registry = BenchmarkProfileRegistry()
        
        profile = registry.get("miniwob")
        assert profile is not None
        assert profile.benchmark_id == "miniwob"
        assert profile.display_name == "MiniWoB++"
        assert profile.token_limit == 2000
        assert profile.observation_mode == ObservationMode.AXTREE_COMPACT
    
    def test_get_or_raise_valid(self):
        """Test get_or_raise with valid benchmark."""
        registry = BenchmarkProfileRegistry()
        
        profile = registry.get_or_raise("miniwob")
        assert profile.benchmark_id == "miniwob"
    
    def test_get_profile_invalid(self):
        """Test getting invalid profile returns None."""
        registry = BenchmarkProfileRegistry()
        
        profile = registry.get("invalid_benchmark")
        assert profile is None
    
    def test_get_or_raise_invalid(self):
        """Test get_or_raise with invalid benchmark raises error."""
        registry = BenchmarkProfileRegistry()
        
        with pytest.raises(ValueError, match="Unknown benchmark"):
            registry.get_or_raise("invalid_benchmark")
    
    def test_get_all_profiles(self):
        """Test getting all profiles."""
        registry = BenchmarkProfileRegistry()
        
        profiles = registry.all_profiles()
        assert len(profiles) == 6
        
        # Check all expected benchmarks are present
        benchmark_ids = [p.benchmark_id for p in profiles]
        assert "miniwob" in benchmark_ids
        assert "webarena" in benchmark_ids


class TestBenchmarkProfiles:
    """Test individual benchmark profile configurations."""
    
    def test_miniwob_profile(self):
        """Test MiniWoB++ profile configuration."""
        registry = BenchmarkProfileRegistry()
        profile = registry.get_or_raise("miniwob")
        
        assert profile.benchmark_id == "miniwob"
        assert profile.token_limit == 2000
        assert profile.observation_mode == ObservationMode.AXTREE_COMPACT
        assert len(profile.extra_tools) == 0  # No extra tools
        assert profile.filtering_strategy.max_depth == 10
        assert "button" in profile.filtering_strategy.focus_elements
    
    def test_webarena_profile(self):
        """Test WebArena profile configuration."""
        registry = BenchmarkProfileRegistry()
        profile = registry.get_or_raise("webarena")
        
        assert profile.benchmark_id == "webarena"
        assert profile.token_limit == 5000
        assert profile.observation_mode == ObservationMode.AXTREE_FULL
        assert len(profile.extra_tools) == 2  # navigate_tabs, fill_form
        
        tool_names = [tool.name for tool in profile.extra_tools]
        assert "navigate_tabs" in tool_names
        assert "fill_form" in tool_names
        
        assert profile.filtering_strategy.form_focus is True
        assert profile.filtering_strategy.max_depth == 20
    
    def test_visualwebarena_profile(self):
        """Test VisualWebArena profile configuration."""
        registry = BenchmarkProfileRegistry()
        profile = registry.get_or_raise("visualwebarena")
        
        assert profile.benchmark_id == "visualwebarena"
        assert profile.token_limit == 3500
        assert profile.observation_mode == ObservationMode.AXTREE_WITH_SCREENSHOT
        assert len(profile.extra_tools) == 2  # get_screenshot, identify_visual_element
        
        tool_names = [tool.name for tool in profile.extra_tools]
        assert "get_screenshot" in tool_names
        assert "identify_visual_element" in tool_names
        
        assert "img" in profile.filtering_strategy.focus_elements
    
    def test_workarena_profile(self):
        """Test WorkArena profile configuration."""
        registry = BenchmarkProfileRegistry()
        profile = registry.get_or_raise("workarena")
        
        assert profile.benchmark_id == "workarena"
        assert profile.token_limit == 4500
        assert profile.observation_mode == ObservationMode.AXTREE
        assert len(profile.extra_tools) == 2  # fill_form, submit_form
        
        tool_names = [tool.name for tool in profile.extra_tools]
        assert "fill_form" in tool_names
        assert "submit_form" in tool_names
    
    def test_assistantbench_profile(self):
        """Test AssistantBench profile configuration."""
        registry = BenchmarkProfileRegistry()
        profile = registry.get_or_raise("assistantbench")
        
        assert profile.benchmark_id == "assistantbench"
        assert profile.token_limit == 3000
        assert profile.observation_mode == ObservationMode.AXTREE
        assert len(profile.extra_tools) == 2  # submit_answer, search_page
        
        tool_names = [tool.name for tool in profile.extra_tools]
        assert "submit_answer" in tool_names
        assert "search_page" in tool_names
    
    def test_weblinx_profile(self):
        """Test WebLinx profile configuration."""
        registry = BenchmarkProfileRegistry()
        profile = registry.get_or_raise("weblinx")
        
        assert profile.benchmark_id == "weblinx"
        assert profile.token_limit == 4000
        assert profile.observation_mode == ObservationMode.AXTREE
        # WebLinx uses base tools only
        assert len(profile.extra_tools) == 0


class TestBenchmarkDetection:
    """Test benchmark detection from task_id prefix."""
    
    @pytest.mark.parametrize("task_id,expected_benchmark", [
        ("miniwob.click-test", "miniwob"),
        ("miniwob.click-button", "miniwob"),
        ("webarena.navigate-github", "webarena"),
        ("webarena.shopping-cart", "webarena"),
        ("visualwebarena.identify-logo", "visualwebarena"),
        ("workarena.create-ticket", "workarena"),
        ("assistantbench.email-task", "assistantbench"),
        ("weblinx.demo-task", "weblinx"),
    ])
    def test_detect_benchmark_from_task_id(self, task_id, expected_benchmark):
        """Test benchmark detection from task_id prefix."""
        benchmark_id = detect_benchmark(task_id)
        assert benchmark_id == expected_benchmark
    
    def test_detect_benchmark_invalid_task_id(self):
        """Test detection with invalid task_id raises error."""
        with pytest.raises(ValueError, match="Invalid task_id format"):
            detect_benchmark("invalid-task-id")
    
    def test_detect_benchmark_unknown_prefix(self):
        """Test detection with unknown benchmark prefix returns prefix."""
        # The function just extracts the prefix, doesn't validate
        result = detect_benchmark("unknown.task-id")
        assert result == "unknown"


class TestTokenLimits:
    """Test token limits for Mandate C compliance."""
    
    def test_all_profiles_have_valid_token_limits(self):
        """Test that all profiles have token limits between 1000-10000."""
        registry = BenchmarkProfileRegistry()
        
        for profile in registry.all_profiles():
            assert 1000 <= profile.token_limit <= 10000, (
                f"{profile.benchmark_id} token_limit {profile.token_limit} "
                f"not in valid range [1000, 10000]"
            )
    
    def test_token_limit_ordering(self):
        """Test that token limits follow expected pattern."""
        registry = BenchmarkProfileRegistry()
        
        # MiniWoB should have smallest limit (simple tasks)
        miniwob = registry.get_or_raise("miniwob")
        assert miniwob.token_limit == 2000
        
        # WebArena should have largest limit (complex navigation)
        webarena = registry.get_or_raise("webarena")
        assert webarena.token_limit == 5000
        
        # WebLinx should have 4000
        weblinx = registry.get_or_raise("weblinx")
        assert weblinx.token_limit == 4000
        
        # VisualWebArena should be 3500 (AXTree + screenshot ref)
        visualwebarena = registry.get_or_raise("visualwebarena")
        assert visualwebarena.token_limit == 3500


class TestExtraTools:
    """Test extra tools configuration per benchmark."""
    
    def test_extra_tools_have_valid_schemas(self):
        """Test that all extra tools have valid input schemas."""
        registry = BenchmarkProfileRegistry()
        
        for profile in registry.all_profiles():
            for tool in profile.extra_tools:
                assert tool.name is not None
                assert tool.description is not None
                assert tool.input_schema is not None
                assert "type" in tool.input_schema
                assert tool.input_schema["type"] == "object"
    
    def test_no_duplicate_tool_names_per_benchmark(self):
        """Test that each benchmark has unique tool names."""
        registry = BenchmarkProfileRegistry()
        
        for profile in registry.all_profiles():
            tool_names = [tool.name for tool in profile.extra_tools]
            assert len(tool_names) == len(set(tool_names)), (
                f"{profile.benchmark_id} has duplicate tool names: {tool_names}"
            )
    
    def test_benchmarks_with_no_extra_tools(self):
        """Test benchmarks that should have no extra tools."""
        registry = BenchmarkProfileRegistry()
        
        # MiniWoB and WebLinx use base tools only
        miniwob = registry.get_or_raise("miniwob")
        weblinx = registry.get_or_raise("weblinx")
        
        assert len(miniwob.extra_tools) == 0
        assert len(weblinx.extra_tools) == 0


class TestFilteringStrategies:
    """Test filtering strategy configurations."""
    
    def test_all_profiles_have_filtering_strategy(self):
        """Test that all profiles have a filtering strategy."""
        registry = BenchmarkProfileRegistry()
        
        for profile in registry.all_profiles():
            assert profile.filtering_strategy is not None
            assert profile.filtering_strategy.max_depth is not None or profile.filtering_strategy.max_depth == 0
            assert len(profile.filtering_strategy.focus_elements) > 0
    
    def test_webarena_form_focus(self):
        """Test that WebArena has form_focus enabled."""
        registry = BenchmarkProfileRegistry()
        webarena = registry.get_or_raise("webarena")
        
        assert webarena.filtering_strategy.form_focus is True
    
    def test_visualwebarena_includes_images(self):
        """Test that VisualWebArena focuses on images."""
        registry = BenchmarkProfileRegistry()
        visualwebarena = registry.get_or_raise("visualwebarena")
        
        assert "img" in visualwebarena.filtering_strategy.focus_elements
