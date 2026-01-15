"""
Benchmark Profiles for BrowserGym Green Agent.

Defines benchmark-specific configurations for:
- Observation token limits (Mandate C)
- Extra MCP tools per benchmark
- Filtering strategies per benchmark characteristics

Per research.md Decision 4 and contracts/benchmark-profiles.json.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional


# =============================================================================
# Observation Mode Enum
# =============================================================================

class ObservationMode(str, Enum):
    """Observation format mode for benchmark filtering."""
    
    AXTREE = "axtree"
    AXTREE_COMPACT = "axtree_compact"
    AXTREE_FULL = "axtree_full"
    AXTREE_WITH_SCREENSHOT = "axtree_with_screenshot"
    DOM = "dom"
    SCREENSHOT = "screenshot"


# =============================================================================
# Filtering Strategy
# =============================================================================

@dataclass
class FilteringStrategy:
    """How observations are filtered for a benchmark."""
    
    focus_elements: list[str] = field(default_factory=list)
    exclude_elements: list[str] = field(default_factory=lambda: ["script", "style", "meta"])
    max_depth: int = 15
    include_hidden: bool = False
    form_focus: bool = False


# =============================================================================
# Tool Definition
# =============================================================================

@dataclass
class ToolDefinition:
    """Dynamic MCP tool definition for benchmark-specific tools."""
    
    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: Optional[dict[str, Any]] = None
    handler: Optional[Callable] = None


# =============================================================================
# Benchmark Profile
# =============================================================================

@dataclass
class BenchmarkProfile:
    """Configuration for benchmark-specific behavior.
    
    Each profile defines:
    - Token limit for observation filtering (Mandate C compliance)
    - Observation mode (axtree, screenshot, etc.)
    - Extra MCP tools specific to the benchmark
    - Filtering strategy for AXTree processing
    """
    
    benchmark_id: str
    display_name: str
    token_limit: int
    observation_mode: ObservationMode
    extra_tools: list[ToolDefinition] = field(default_factory=list)
    filtering_strategy: FilteringStrategy = field(default_factory=FilteringStrategy)
    
    def __post_init__(self):
        """Validate profile configuration."""
        if not 1000 <= self.token_limit <= 10000:
            raise ValueError(f"token_limit must be between 1000 and 10000, got {self.token_limit}")


# =============================================================================
# Benchmark Profile Registry
# =============================================================================

class BenchmarkProfileRegistry:
    """Registry of all supported benchmark profiles.
    
    Per research.md Decision 4, defines 6 benchmark profiles with
    appropriate token limits, extra tools, and filtering strategies.
    """
    
    _instance: Optional["BenchmarkProfileRegistry"] = None
    _profiles: dict[str, BenchmarkProfile]
    
    def __new__(cls) -> "BenchmarkProfileRegistry":
        """Singleton pattern for profile registry."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._profiles = {}
            cls._instance._initialize_profiles()
        return cls._instance
    
    def _initialize_profiles(self) -> None:
        """Initialize all 6 benchmark profiles."""
        
        # MiniWoB++ - Simple widget tasks
        self._profiles["miniwob"] = BenchmarkProfile(
            benchmark_id="miniwob",
            display_name="MiniWoB++",
            token_limit=2000,
            observation_mode=ObservationMode.AXTREE_COMPACT,
            extra_tools=[],  # Base tools only
            filtering_strategy=FilteringStrategy(
                focus_elements=["button", "input", "link", "select"],
                exclude_elements=["script", "style", "meta"],
                max_depth=10,
                include_hidden=False,
                form_focus=False,
            ),
        )
        
        # WebArena - Complex web navigation
        self._profiles["webarena"] = BenchmarkProfile(
            benchmark_id="webarena",
            display_name="WebArena",
            token_limit=5000,
            observation_mode=ObservationMode.AXTREE_FULL,
            extra_tools=[
                ToolDefinition(
                    name="navigate_tabs",
                    description="Switch between browser tabs",
                    input_schema={
                        "type": "object",
                        "properties": {
                            "tab_index": {"type": "integer", "description": "Target tab index (0-based)"}
                        },
                        "required": ["tab_index"],
                    },
                ),
                ToolDefinition(
                    name="fill_form",
                    description="Fill a form with multiple fields at once",
                    input_schema={
                        "type": "object",
                        "properties": {
                            "fields": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "selector": {"type": "string"},
                                        "value": {"type": "string"},
                                    },
                                    "required": ["selector", "value"],
                                },
                                "description": "List of field selectors and values to fill",
                            }
                        },
                        "required": ["fields"],
                    },
                ),
            ],
            filtering_strategy=FilteringStrategy(
                focus_elements=["button", "input", "link", "select", "textarea", "form"],
                exclude_elements=["script", "style", "meta", "noscript"],
                max_depth=20,
                include_hidden=False,
                form_focus=True,
            ),
        )
        
        # VisualWebArena - Visual-dependent tasks
        self._profiles["visualwebarena"] = BenchmarkProfile(
            benchmark_id="visualwebarena",
            display_name="VisualWebArena",
            token_limit=3500,
            observation_mode=ObservationMode.AXTREE_WITH_SCREENSHOT,
            extra_tools=[
                ToolDefinition(
                    name="get_screenshot",
                    description="Capture current page screenshot",
                    input_schema={
                        "type": "object",
                        "properties": {
                            "full_page": {
                                "type": "boolean",
                                "default": False,
                                "description": "Capture full page or viewport only",
                            }
                        },
                    },
                ),
                ToolDefinition(
                    name="identify_visual_element",
                    description="Identify element by visual description",
                    input_schema={
                        "type": "object",
                        "properties": {
                            "description": {
                                "type": "string",
                                "description": "Visual description of the element to find",
                            }
                        },
                        "required": ["description"],
                    },
                ),
            ],
            filtering_strategy=FilteringStrategy(
                focus_elements=["img", "button", "input", "link"],
                exclude_elements=["script", "style", "meta"],
                max_depth=15,
                include_hidden=False,
                form_focus=False,
            ),
        )
        
        # WorkArena - ServiceNow workflows
        self._profiles["workarena"] = BenchmarkProfile(
            benchmark_id="workarena",
            display_name="WorkArena",
            token_limit=4500,
            observation_mode=ObservationMode.AXTREE,
            extra_tools=[
                ToolDefinition(
                    name="fill_form",
                    description="Fill a ServiceNow form with multiple fields",
                    input_schema={
                        "type": "object",
                        "properties": {
                            "fields": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "field_name": {"type": "string"},
                                        "value": {"type": "string"},
                                    },
                                    "required": ["field_name", "value"],
                                },
                            }
                        },
                        "required": ["fields"],
                    },
                ),
                ToolDefinition(
                    name="submit_form",
                    description="Submit the current form",
                    input_schema={
                        "type": "object",
                        "properties": {
                            "confirm": {
                                "type": "boolean",
                                "default": True,
                                "description": "Whether to confirm submission dialogs",
                            }
                        },
                    },
                ),
            ],
            filtering_strategy=FilteringStrategy(
                focus_elements=["button", "input", "select", "textarea", "form", "label"],
                exclude_elements=["script", "style", "meta", "noscript"],
                max_depth=18,
                include_hidden=False,
                form_focus=True,
            ),
        )
        
        # AssistantBench - Information retrieval
        self._profiles["assistantbench"] = BenchmarkProfile(
            benchmark_id="assistantbench",
            display_name="AssistantBench",
            token_limit=3000,
            observation_mode=ObservationMode.AXTREE,
            extra_tools=[
                ToolDefinition(
                    name="submit_answer",
                    description="Submit the final answer for the task",
                    input_schema={
                        "type": "object",
                        "properties": {
                            "answer": {
                                "type": "string",
                                "description": "The answer to submit",
                            }
                        },
                        "required": ["answer"],
                    },
                ),
                ToolDefinition(
                    name="search_page",
                    description="Search for text content within the current page",
                    input_schema={
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search query text",
                            },
                            "case_sensitive": {
                                "type": "boolean",
                                "default": False,
                            },
                        },
                        "required": ["query"],
                    },
                ),
            ],
            filtering_strategy=FilteringStrategy(
                focus_elements=["article", "main", "p", "h1", "h2", "h3", "span", "div"],
                exclude_elements=["script", "style", "meta", "nav", "footer", "header"],
                max_depth=12,
                include_hidden=False,
                form_focus=False,
            ),
        )
        
        # WebLINX - Dialogue-based navigation
        self._profiles["weblinx"] = BenchmarkProfile(
            benchmark_id="weblinx",
            display_name="WebLINX",
            token_limit=4000,
            observation_mode=ObservationMode.AXTREE,
            extra_tools=[],  # Base tools only, dialogue-aware filtering
            filtering_strategy=FilteringStrategy(
                focus_elements=["button", "input", "link", "select", "textarea"],
                exclude_elements=["script", "style", "meta"],
                max_depth=15,
                include_hidden=False,
                form_focus=False,
            ),
        )
    
    def get(self, benchmark_id: str) -> Optional[BenchmarkProfile]:
        """Get profile by benchmark ID."""
        return self._profiles.get(benchmark_id.lower())
    
    def get_or_raise(self, benchmark_id: str) -> BenchmarkProfile:
        """Get profile by benchmark ID or raise ValueError."""
        profile = self.get(benchmark_id)
        if profile is None:
            supported = ", ".join(self._profiles.keys())
            raise ValueError(f"Unknown benchmark: {benchmark_id}. Supported: {supported}")
        return profile
    
    def all_profiles(self) -> list[BenchmarkProfile]:
        """Get all registered profiles."""
        return list(self._profiles.values())
    
    def supported_benchmarks(self) -> list[str]:
        """Get list of supported benchmark IDs."""
        return list(self._profiles.keys())
    
    @classmethod
    def instance(cls) -> "BenchmarkProfileRegistry":
        """Get singleton instance."""
        return cls()


# =============================================================================
# Helper Functions
# =============================================================================

def get_profile_for_task(task_id: str) -> BenchmarkProfile:
    """Get benchmark profile from task_id prefix.
    
    Task IDs follow the pattern: {benchmark}.{task_name}
    e.g., "miniwob.click-test" → miniwob profile
    
    Args:
        task_id: The task identifier with benchmark prefix
        
    Returns:
        BenchmarkProfile for the detected benchmark
        
    Raises:
        ValueError: If benchmark prefix not recognized
    """
    if not task_id or "." not in task_id:
        raise ValueError(f"Invalid task_id format: {task_id}. Expected: {{benchmark}}.{{task_name}}")
    
    benchmark_prefix = task_id.split(".")[0].lower()
    registry = BenchmarkProfileRegistry.instance()
    
    return registry.get_or_raise(benchmark_prefix)


def detect_benchmark(task_id: str) -> str:
    """Extract benchmark ID from task_id prefix.
    
    Args:
        task_id: The task identifier with benchmark prefix
        
    Returns:
        Benchmark ID string (lowercase)
        
    Raises:
        ValueError: If task_id format is invalid
    """
    if not task_id or "." not in task_id:
        raise ValueError(f"Invalid task_id format: {task_id}. Expected: {{benchmark}}.{{task_name}}")
    
    return task_id.split(".")[0].lower()
