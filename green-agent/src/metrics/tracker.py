"""
Efficiency metrics tracking for constitutional mandate compliance.

Tracks token counts (C), latency (L), and resource footprint (F).
"""

import psutil
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class EfficiencyMetrics:
    """
    Performance measurements for Mandate C/L/F tracking.
    
    Attributes:
        total_tokens: Cumulative token count across all observations (Mandate C)
        total_latency_ms: Cumulative MCP tool invocation time (Mandate L)
        peak_memory_mb: Peak memory usage during evaluation (Mandate F)
        chromium_process_count: Number of Chromium processes at cleanup (Mandate F)
        mcp_tool_invocations: Count of MCP tool calls
        observation_count: Number of observations returned
        action_count: Number of actions executed
        efficiency_penalty: Calculated penalty using formula (FR-017)
        final_score: Task success × efficiency_penalty
        session_start: Evaluation start timestamp
    """
    
    total_tokens: int = 0
    total_latency_ms: int = 0
    peak_memory_mb: int = 0
    chromium_process_count: int = 0
    mcp_tool_invocations: int = 0
    observation_count: int = 0
    action_count: int = 0
    efficiency_penalty: float = 1.0
    final_score: float = 0.0
    session_start: datetime = field(default_factory=datetime.utcnow)
    
    def add_tokens(self, tokens: int) -> None:
        """Add tokens to cumulative count."""
        self.total_tokens += tokens
        self.observation_count += 1
    
    def add_latency(self, latency_ms: int) -> None:
        """Add latency to cumulative time."""
        self.total_latency_ms += latency_ms
        self.mcp_tool_invocations += 1
    
    def update_memory(self, memory_mb: int) -> None:
        """Update peak memory if current usage is higher."""
        self.peak_memory_mb = max(self.peak_memory_mb, memory_mb)
    
    def set_chromium_processes(self, count: int) -> None:
        """Set Chromium process count (for cleanup verification)."""
        self.chromium_process_count = count
    
    def add_actions(self, count: int) -> None:
        """Add to action count."""
        self.action_count += count
    
    def get_current_memory_mb(self) -> int:
        """
        Get current process memory usage in MB.
        
        Returns:
            Memory usage in megabytes
        """
        process = psutil.Process()
        memory_info = process.memory_info()
        memory_mb = int(memory_info.rss / (1024 * 1024))  # Convert bytes to MB
        return memory_mb
    
    def update_peak_memory(self) -> int:
        """
        Update peak memory based on current usage.
        
        Returns:
            Current memory usage in MB
        """
        current_memory = self.get_current_memory_mb()
        self.update_memory(current_memory)
        return current_memory
    
    def to_dict(self) -> dict:
        """Convert metrics to dictionary for serialization."""
        return {
            "total_tokens": self.total_tokens,
            "total_latency_ms": self.total_latency_ms,
            "peak_memory_mb": self.peak_memory_mb,
            "chromium_process_count": self.chromium_process_count,
            "mcp_tool_invocations": self.mcp_tool_invocations,
            "observation_count": self.observation_count,
            "action_count": self.action_count,
            "efficiency_penalty": self.efficiency_penalty,
            "final_score": self.final_score,
            "session_duration_seconds": (
                (datetime.utcnow() - self.session_start).total_seconds()
            ),
        }
