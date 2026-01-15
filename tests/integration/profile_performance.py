"""
Performance profiling script for BrowserGym Green Agent (T090).

Identifies bottlenecks in:
- Observation filtering
- Action execution
- Token estimation
- Memory usage

Run: .\.venv\Scripts\python.exe tests\integration\profile_performance.py
"""

import asyncio
import time
import cProfile
import pstats
import io
from pathlib import Path
import sys

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.green_agent.environment.entities import EnvironmentConfig
from src.green_agent.environment.session_manager import SessionManager
from src.green_agent.environment.observation_filter import filter_observation
from src.green_agent.environment.action_executor import ActionExecutor
from src.green_agent.utils.token_estimator import estimate_tokens
from src.green_agent.metrics.tracker import EfficiencyMetrics


def profile_observation_filtering():
    """Profile observation filtering performance."""
    print("\n" + "="*60)
    print("PROFILING: Observation Filtering")
    print("="*60)
    
    # Create dummy observation
    dummy_obs = {
        "axtree": {
            "text": "A" * 10000,  # Large text
            "nodes": [{"id": i, "name": f"element-{i}"} for i in range(100)]
        },
        "screenshot": "base64_data_here" * 100,
        "focused_element_bid": "5",
        "last_action": "click('5')",
        "last_action_error": ""
    }
    
    # Profile AXTree filtering
    profiler = cProfile.Profile()
    profiler.enable()
    
    start_time = time.perf_counter()
    for _ in range(100):
        filtered = filter_observation(dummy_obs, mode="axtree")
        tokens = estimate_tokens(str(filtered))
    elapsed = time.perf_counter() - start_time
    
    profiler.disable()
    
    # Print stats
    s = io.StringIO()
    ps = pstats.Stats(profiler, stream=s).sort_stats('cumulative')
    ps.print_stats(10)
    
    print(f"\nPerformance Metrics:")
    print(f"  Total time (100 iterations): {elapsed:.3f}s")
    print(f"  Average per iteration: {(elapsed/100)*1000:.2f}ms")
    print(f"  Tokens in filtered observation: {tokens}")
    
    print("\nTop 10 Functions by Cumulative Time:")
    print(s.getvalue())
    
    # Recommendations
    if (elapsed/100)*1000 > 100:
        print("\n⚠️  WARNING: Observation filtering exceeds 100ms target")
        print("   Recommendations:")
        print("   - Optimize filter_observation() logic")
        print("   - Consider caching token estimations")
        print("   - Profile estimate_tokens() separately")
    else:
        print("\n✅ Observation filtering performance acceptable")


def profile_action_execution():
    """Profile action execution performance."""
    print("\n" + "="*60)
    print("PROFILING: Action Execution")
    print("="*60)
    
    # Create mock environment
    from unittest.mock import Mock
    env = Mock()
    env.step = Mock(return_value=({"obs": "test"}, 0.0, False, False, {"info": "test"}))
    
    executor = ActionExecutor(env)
    
    # Profile batch execution
    actions = [
        {"action": "click", "bid": str(i)} for i in range(50)
    ]
    
    profiler = cProfile.Profile()
    profiler.enable()
    
    start_time = time.perf_counter()
    for _ in range(10):
        results = executor.execute_action_batch(actions)
    elapsed = time.perf_counter() - start_time
    
    profiler.disable()
    
    # Print stats
    s = io.StringIO()
    ps = pstats.Stats(profiler, stream=s).sort_stats('cumulative')
    ps.print_stats(10)
    
    print(f"\nPerformance Metrics:")
    print(f"  Total time (10 iterations × 50 actions): {elapsed:.3f}s")
    print(f"  Average per batch: {(elapsed/10)*1000:.2f}ms")
    print(f"  Average per action: {(elapsed/10/50)*1000:.2f}ms")
    
    print("\nTop 10 Functions by Cumulative Time:")
    print(s.getvalue())
    
    # Recommendations
    if (elapsed/10)*1000 > 2000:
        print("\n⚠️  WARNING: Action batch exceeds 2s target")
        print("   Recommendations:")
        print("   - Optimize action translation logic")
        print("   - Consider async action execution")
        print("   - Profile gymnasium step() overhead")
    else:
        print("\n✅ Action execution performance acceptable")


def profile_token_estimation():
    """Profile token estimation performance."""
    print("\n" + "="*60)
    print("PROFILING: Token Estimation")
    print("="*60)
    
    test_strings = [
        "A" * 1000,   # Small
        "B" * 5000,   # Medium
        "C" * 10000,  # Large
    ]
    
    for size_label, test_str in zip(["Small (1K chars)", "Medium (5K chars)", "Large (10K chars)"], test_strings):
        profiler = cProfile.Profile()
        profiler.enable()
        
        start_time = time.perf_counter()
        for _ in range(1000):
            tokens = estimate_tokens(test_str)
        elapsed = time.perf_counter() - start_time
        
        profiler.disable()
        
        print(f"\n{size_label}:")
        print(f"  Total time (1000 iterations): {elapsed:.3f}s")
        print(f"  Average per call: {(elapsed/1000)*1000:.3f}ms")
        print(f"  Estimated tokens: {tokens}")


def profile_memory_usage():
    """Profile memory usage during evaluation."""
    print("\n" + "="*60)
    print("PROFILING: Memory Usage")
    print("="*60)
    
    metrics = EfficiencyMetrics()
    
    # Measure baseline
    baseline_memory = metrics.get_current_memory_mb()
    print(f"Baseline memory: {baseline_memory} MB")
    
    # Simulate memory-intensive operations
    large_data = []
    memory_samples = []
    
    for i in range(10):
        # Allocate data
        large_data.append("x" * 1_000_000)  # 1MB chunks
        
        # Measure memory
        current_memory = metrics.update_peak_memory()
        memory_samples.append(current_memory)
        
        print(f"  Iteration {i+1}: {current_memory} MB")
    
    # Clean up
    large_data.clear()
    
    print(f"\nMemory Statistics:")
    print(f"  Baseline: {baseline_memory} MB")
    print(f"  Peak: {metrics.peak_memory_mb} MB")
    print(f"  Delta: {metrics.peak_memory_mb - baseline_memory} MB")
    
    if metrics.peak_memory_mb > 500:
        print("\n⚠️  WARNING: Peak memory exceeds 500MB limit")
        print("   Recommendations:")
        print("   - Review large data structures")
        print("   - Implement streaming for observations")
        print("   - Clear caches more aggressively")
    else:
        print("\n✅ Memory usage within acceptable limits")


def main():
    """Run all profiling tests."""
    print("\n" + "="*60)
    print("BROWSERGYM GREEN AGENT - PERFORMANCE PROFILING")
    print("="*60)
    
    try:
        # Profile each component
        profile_observation_filtering()
        profile_action_execution()
        profile_token_estimation()
        profile_memory_usage()
        
        # Summary
        print("\n" + "="*60)
        print("PROFILING COMPLETE")
        print("="*60)
        print("\nKey Findings:")
        print("1. Check warnings above for components exceeding targets")
        print("2. Review cumulative time stats for bottlenecks")
        print("3. Consider optimizing top functions in profiles")
        
        print("\nNext Steps:")
        print("- Run with actual BrowserGym environment for realistic profiling")
        print("- Use memory_profiler for detailed memory analysis:")
        print("  python -m memory_profiler script.py")
        print("- Use line_profiler for line-by-line profiling:")
        print("  kernprof -l -v script.py")
        
    except Exception as e:
        print(f"\n❌ PROFILING FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
