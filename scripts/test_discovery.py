#!/usr/bin/env python
"""Quick test of task auto-discovery."""
import sys
sys.path.insert(0, ".")

from src.green_agent.benchmarks import discover_tasks_for_benchmark

print("=" * 50)
print("Testing MiniWoB Task Auto-Discovery")
print("=" * 50)

# Test with max_tasks = 2
tasks = discover_tasks_for_benchmark("miniwob", max_tasks=2)
print(f"\nDiscovered {len(tasks)} tasks (max_tasks=2):")
for t in tasks:
    print(f"  - {t}")

# Test with max_tasks = 5
tasks = discover_tasks_for_benchmark("miniwob", max_tasks=5)
print(f"\nDiscovered {len(tasks)} tasks (max_tasks=5):")
for t in tasks:
    print(f"  - {t}")

# Test all available tasks
tasks = discover_tasks_for_benchmark("miniwob", max_tasks=None)
print(f"\nTotal available MiniWoB tasks: {len(tasks)}")
print("First 10:")
for t in tasks[:10]:
    print(f"  - {t}")
