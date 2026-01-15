"""
Benchmark Constants - Dependency-Free Module.

This module contains only constant definitions with zero imports
to avoid circular dependency issues.
"""

# =============================================================================
# BENCHMARK CONFIGURATION - CENTRAL CONTROL PANEL
# =============================================================================
# Uncomment/comment benchmarks here to control which ones are evaluated by default
# when no TOML configuration is provided.

# All supported benchmarks (validation whitelist)
SUPPORTED_BENCHMARKS = [
    "miniwob",
    "webarena",
    "visualwebarena",
    "workarena",
    "assistantbench",
    "weblinx",
]

# Default benchmarks for evaluation (when TOML has no [[benchmarks]] sections)
# Uncomment/comment lines below to enable/disable benchmarks for evaluation
DEFAULT_EVALUATION_BENCHMARKS = [
    "miniwob",           # ✅ Local HTML tasks - ready to use
    "assistantbench",    # ✅ local sdk install required
    # "webarena",        # ⚠️ Docker containers required
    # "visualwebarena",  # ⚠️ Docker containers required
    # "workarena",       # ⚠️ ServiceNow instance required
    # "weblinx",         # ⚠️ Dataset download required
]

# Default maximum tasks per benchmark (when not specified in config)
DEFAULT_MAX_TASKS_PER_BENCHMARK = 2
