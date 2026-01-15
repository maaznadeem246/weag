#!/usr/bin/env python
"""Test task plan resolution."""
import sys
sys.path.insert(0, ".")

import tomllib
from pathlib import Path

# Load TOML directly
toml_data = tomllib.loads(Path("config/assessment.toml").read_text())

# Import the resolve function
from scripts.kickstart_assessment import _kickstart_resolve_task_plan

project_root = Path(".")
result = _kickstart_resolve_task_plan(project_root, toml_data)

print("=" * 50)
print("Task Plan Resolution Test")
print("=" * 50)
print(f"\nBenchmarks: {result['benchmarks']}")
print(f"\nTasks by benchmark:")
for bench, tasks in result['tasks_by_benchmark'].items():
    print(f"  {bench}: {len(tasks)} tasks")
    for t in tasks:
        print(f"    - {t}")
print(f"\nTotal tasks: {sum(len(v) for v in result['tasks_by_benchmark'].values())}")
print(f"Max tasks per benchmark: {result.get('max_tasks_per_benchmark', 'not set')}")
