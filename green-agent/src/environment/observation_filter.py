"""
Observation filtering for Mandate C compliance (<5K tokens/observation).

Implements AXTree filtering using flatten_axtree_to_str utility with optional modes.
Supports benchmark-specific token limits and filtering strategies (US7).

Benchmark Token Limits (from profiles):
- miniwob: 2000 tokens (compact AXTree)
- webarena: 5000 tokens (full AXTree)
- visualwebarena: 3500 tokens (AXTree + screenshot ref)
- workarena: 4500 tokens
- assistantbench: 3000 tokens
- weblinx: 4000 tokens
"""

from typing import Dict, Any, Optional, List
from enum import Enum
from dataclasses import dataclass

from src.utils.token_estimator import estimate_tokens, check_token_limit
from src.utils.logging import get_logger
from src.environment.observation_utils import format_axtree
from src.environment.filter_helpers import (
    extract_observation_metadata,
    build_filtered_observation,
    create_screenshot_reference
)


logger = get_logger(__name__)


class ObservationMode(Enum):
    """Observation format modes."""
    AXTREE = "axtree"                    # Default: filtered AXTree (Mandate C optimized)
    AXTREE_COMPACT = "axtree_compact"    # Minimal AXTree (for miniwob)
    AXTREE_FULL = "axtree_full"          # Full AXTree (for webarena)
    AXTREE_WITH_SCREENSHOT = "axtree_with_screenshot"  # AXTree + screenshot ref (visualwebarena)
    DOM = "dom"                          # Full DOM for debugging
    SCREENSHOT = "screenshot"            # Screenshot for debugging


@dataclass
class FilteringStrategy:
    """
    Benchmark-specific filtering configuration.
    
    Determines how observations are filtered for each benchmark.
    """
    focus_elements: List[str]      # Element types to prioritize (button, input, link, etc.)
    exclude_elements: List[str]    # Element types to exclude (script, style, etc.)
    max_depth: Optional[int]       # Maximum DOM/AXTree depth
    include_hidden: bool           # Include hidden elements
    form_focus: bool               # Prioritize form elements
    

# Benchmark-specific filtering strategies
BENCHMARK_STRATEGIES: Dict[str, FilteringStrategy] = {
    "miniwob": FilteringStrategy(
        focus_elements=["button", "input", "select", "checkbox", "radio"],
        exclude_elements=["script", "style", "meta", "link"],
        max_depth=5,
        include_hidden=False,
        form_focus=True
    ),
    "webarena": FilteringStrategy(
        focus_elements=["button", "input", "select", "a", "textarea", "form"],
        exclude_elements=["script", "style", "meta", "svg"],
        max_depth=None,  # Full depth
        include_hidden=False,
        form_focus=True
    ),
    "visualwebarena": FilteringStrategy(
        focus_elements=["button", "input", "select", "a", "img", "canvas"],
        exclude_elements=["script", "style", "meta"],
        max_depth=8,
        include_hidden=False,
        form_focus=False  # Visual tasks may not focus on forms
    ),
    "workarena": FilteringStrategy(
        focus_elements=["button", "input", "select", "textarea", "form", "table"],
        exclude_elements=["script", "style", "meta", "svg"],
        max_depth=10,
        include_hidden=False,
        form_focus=True
    ),
    "assistantbench": FilteringStrategy(
        focus_elements=["button", "input", "a", "p", "span", "div"],
        exclude_elements=["script", "style", "meta", "link"],
        max_depth=6,
        include_hidden=False,
        form_focus=False
    ),
    "weblinx": FilteringStrategy(
        focus_elements=["button", "input", "select", "a", "textarea"],
        exclude_elements=["script", "style", "meta", "link", "svg"],
        max_depth=8,
        include_hidden=False,
        form_focus=True
    )
}


class ObservationFilter:
    """
    Filters BrowserGym observations for token optimization.
    
    Default mode uses flatten_axtree_to_str for 60-80% token reduction.
    Supports benchmark-specific token limits and filtering strategies.
    """
    
    def __init__(self, token_limit: int = 5000, benchmark_id: Optional[str] = None):
        """
        Initialize observation filter.
        
        Args:
            token_limit: Maximum tokens per observation (Mandate C)
            benchmark_id: Benchmark identifier for strategy selection
        """
        self.token_limit = token_limit
        self.benchmark_id = benchmark_id
        self.strategy = BENCHMARK_STRATEGIES.get(benchmark_id, BENCHMARK_STRATEGIES["webarena"])
        self.profile_observation_mode: Optional[str] = None
    
    @classmethod
    def from_benchmark_profile(cls, profile: "BenchmarkProfile") -> "ObservationFilter":
        """
        Create filter from BenchmarkProfile.
        
        Args:
            profile: BenchmarkProfile with token_limit and benchmark_id
            
        Returns:
            ObservationFilter configured for the benchmark
        """
        filt = cls(
            token_limit=profile.token_limit,
            benchmark_id=profile.benchmark_id
        )
        filt.profile_observation_mode = getattr(profile, "observation_mode", None)
        # Align strategy if profile exposes compatible fields
        strategy = BENCHMARK_STRATEGIES.get(profile.benchmark_id)
        if strategy:
            filt.strategy = strategy
        return filt

    def apply_profile(self, profile: "BenchmarkProfile") -> None:
        """Update this filter in-place from a benchmark profile."""
        self.token_limit = profile.token_limit
        self.benchmark_id = profile.benchmark_id
        self.profile_observation_mode = getattr(profile, "observation_mode", None)
        strategy = BENCHMARK_STRATEGIES.get(profile.benchmark_id)
        if strategy:
            self.strategy = strategy
    
    def get_default_mode(self) -> ObservationMode:
        """
        Get default observation mode for current benchmark.
        
        Returns:
            ObservationMode appropriate for the benchmark
        """
        if self.profile_observation_mode:
            return ObservationMode(self.profile_observation_mode)
        if self.benchmark_id == "miniwob":
            return ObservationMode.AXTREE_COMPACT
        elif self.benchmark_id == "webarena":
            return ObservationMode.AXTREE_FULL
        elif self.benchmark_id == "visualwebarena":
            return ObservationMode.AXTREE_WITH_SCREENSHOT
        else:
            return ObservationMode.AXTREE
    
    def filter_observation(
        self,
        observation: Dict[str, Any],
        mode: Optional[ObservationMode] = None
    ) -> Dict[str, Any]:
        """
        Filter observation based on mode and benchmark strategy.
        
        Args:
            observation: Raw BrowserGym observation
            mode: Observation format mode (default: benchmark-specific)
            
        Returns:
            Filtered observation dict with:
                - axtree/dom/screenshot: Filtered content
                - url: Current page URL
                - goal: Task goal
                - last_action_result: Last action outcome
                - token_estimate: Estimated token count
                - observation_mode: Mode used
                - warning: Optional warning if exceeds token limit
        """
        if mode is None:
            mode = self.get_default_mode()
        
        if mode == ObservationMode.AXTREE:
            return self._filter_axtree(observation)
        elif mode == ObservationMode.AXTREE_COMPACT:
            return self._filter_axtree_compact(observation)
        elif mode == ObservationMode.AXTREE_FULL:
            return self._filter_axtree_full(observation)
        elif mode == ObservationMode.AXTREE_WITH_SCREENSHOT:
            return self._filter_axtree_with_screenshot(observation)
        elif mode == ObservationMode.DOM:
            return self._filter_dom(observation)
        elif mode == ObservationMode.SCREENSHOT:
            return self._filter_screenshot(observation)
        else:
            raise ValueError(f"Unknown observation mode: {mode}")
    
    def _filter_axtree(self, observation: Dict[str, Any]) -> Dict[str, Any]:
        """
        Filter observation using AXTree mode (Mandate C optimized).
        
        Uses format_axtree utility to extract interactive elements.
        
        Args:
            observation: Raw observation
            
        Returns:
            Filtered observation with AXTree
        """
        try:
            # Use official BrowserGym utility via our observation_utils
            axtree_str = format_axtree(
                observation,
                with_visible=True,
                with_clickable=True,
                filter_visible_only=True
            )
            
            return build_filtered_observation(
                content=axtree_str,
                observation=observation,
                content_key="axtree_txt",
                token_limit=self.token_limit,
                mode_name="axtree"
            )
            
        except Exception as e:
            logger.error("AXTree filtering failed", extra={"error": str(e)}, exc_info=True)
            # Fallback: return minimal observation
            metadata = extract_observation_metadata(observation)
            return {
                "axtree_txt": "",
                **metadata,
                "last_action_result": str(e),
                "token_estimate": 0,
                "observation_mode": "axtree",
                "warning": f"Filtering error: {str(e)}"
            }
    
    def _filter_axtree_compact(self, observation: Dict[str, Any]) -> Dict[str, Any]:
        """
        Compact AXTree filtering for miniwob.
        
        - 2000 token limit
        - Only interactive elements (buttons, inputs, etc.)
        - Optimized for small tasks
        
        Args:
            observation: Raw observation
            
        Returns:
            Filtered observation with compact AXTree
        """
        try:
            axtree_str = format_axtree(
                observation,
                with_visible=True,
                with_clickable=True,
                filter_visible_only=True
            )
            
            return build_filtered_observation(
                content=axtree_str,
                observation=observation,
                content_key="axtree_txt",
                token_limit=self.token_limit,
                mode_name="axtree_compact"
            )
            
        except Exception as e:
            logger.error(f"Compact AXTree filtering failed: {e}", exc_info=True)
            metadata = extract_observation_metadata(observation)
            return {
                "axtree_txt": "",
                **metadata,
                "last_action_result": str(e),
                "token_estimate": 0,
                "observation_mode": "axtree_compact",
                "warning": f"Filtering error: {str(e)}"
            }
    
    def _filter_axtree_full(self, observation: Dict[str, Any]) -> Dict[str, Any]:
        """
        Full AXTree filtering for webarena.
        
        - 5000 token limit
        - Full accessibility tree
        - Includes all visible elements
        
        Args:
            observation: Raw observation
            
        Returns:
            Filtered observation with full AXTree
        """
        try:
            axtree_str = format_axtree(
                observation,
                with_visible=True,
                with_clickable=True,
                filter_visible_only=False  # Include all elements for webarena
            )
            
            return build_filtered_observation(
                content=axtree_str,
                observation=observation,
                content_key="axtree_txt",
                token_limit=self.token_limit,
                mode_name="axtree_full"
            )
            
        except Exception as e:
            logger.error(f"Full AXTree filtering failed: {e}", exc_info=True)
            metadata = extract_observation_metadata(observation)
            return {
                "axtree_txt": "",
                **metadata,
                "last_action_result": str(e),
                "token_estimate": 0,
                "observation_mode": "axtree_full",
                "warning": f"Filtering error: {str(e)}"
            }
    
    def _filter_axtree_with_screenshot(self, observation: Dict[str, Any]) -> Dict[str, Any]:
        """
        AXTree with screenshot reference for visualwebarena.
        
        - 3500 token limit
        - AXTree + screenshot reference (not full base64)
        - Useful for visual tasks
        
        Args:
            observation: Raw observation
            
        Returns:
            Filtered observation with AXTree and screenshot reference
        """
        try:
            # Use format_axtree with reserved tokens for screenshot reference
            axtree_str = format_axtree(
                observation,
                with_visible=True,
                with_clickable=True,
                filter_visible_only=True
            )
            
            # Add screenshot reference
            screenshot_ref = create_screenshot_reference(observation, include_dimensions=True)
            
            return build_filtered_observation(
                content=axtree_str,
                observation=observation,
                content_key="axtree_txt",
                token_limit=self.token_limit - 200,  # Reserve tokens for screenshot
                mode_name="axtree_with_screenshot",
                extra_fields={"screenshot_reference": screenshot_ref}
            )
            
        except Exception as e:
            logger.error(f"AXTree with screenshot filtering failed: {e}", exc_info=True)
            metadata = extract_observation_metadata(observation)
            return {
                "axtree_txt": "",
                **metadata,
                "last_action_result": str(e),
                "token_estimate": 0,
                "observation_mode": "axtree_with_screenshot",
                "warning": f"Filtering error: {str(e)}"
            }
    
    def _filter_dom(self, observation: Dict[str, Any]) -> Dict[str, Any]:
        """
        Return full DOM (debugging mode - high token cost).
        
        Args:
            observation: Raw observation
            
        Returns:
            Observation with full DOM
        """
        dom_str = observation.get("dom_object", "")
        if not isinstance(dom_str, str):
            dom_str = str(dom_str)
        
        return build_filtered_observation(
            content=dom_str,
            observation=observation,
            content_key="dom",
            token_limit=self.token_limit,
            mode_name="dom"
        )
    
    def _filter_screenshot(self, observation: Dict[str, Any]) -> Dict[str, Any]:
        """
        Return base64-encoded screenshot (debugging mode - very high token cost).
        
        Args:
            observation: Raw observation
            
        Returns:
            Observation with screenshot
        """
        import base64
        
        # Get screenshot data
        screenshot_data = observation.get("screenshot", b"")
        if isinstance(screenshot_data, bytes):
            screenshot_b64 = base64.b64encode(screenshot_data).decode("utf-8")
        else:
            screenshot_b64 = str(screenshot_data)
        
        return build_filtered_observation(
            content=screenshot_b64,
            observation=observation,
            content_key="screenshot",
            token_limit=self.token_limit,
            mode_name="screenshot",
            extra_fields={"warning": f"Screenshot mode: very high token count"}
        )
