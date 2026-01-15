"""
Integration test for real BrowserGym evaluation.
Tests end-to-end evaluation flow with actual metrics collection.
"""

import asyncio
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from src.green_agent.utils.shared_state import SharedStateManager, EvaluationState
from src.green_agent.utils.models import EvalRequest, EvaluationSession, EvaluationArtifact
from src.green_agent.metrics.penalty_calculator import calculate_efficiency_penalty


class TestRealEvaluationMetrics:
    """Tests for real metrics collection during evaluation."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for state files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    @pytest.fixture
    def shared_state(self, temp_dir):
        """Create and initialize shared state manager."""
        manager = SharedStateManager("test-eval-session", state_dir=temp_dir)
        manager.initialize()
        return manager
    
    def test_metrics_accumulate_correctly(self, shared_state):
        """Test that metrics accumulate correctly during evaluation."""
        # Simulate MCP tool invocations (environment auto-initialized by Green Agent)
        
        # 1. get_observation (3 times)
        for i in range(3):
            shared_state.update_tool_invocation("get_observation")
            shared_state.add_tokens(1500)
            shared_state.add_latency(30)
        
        # 2. execute_actions (2 batches)
        shared_state.update_tool_invocation("execute_actions")
        shared_state.add_actions(3)
        shared_state.add_latency(200)
        shared_state.update_task_state(reward=0.0, done=False, truncated=False)
        
        shared_state.update_tool_invocation("execute_actions")
        shared_state.add_actions(2)
        shared_state.add_latency(180)
        shared_state.update_task_state(reward=1.0, done=True, truncated=False)
        
        # Task complete - Green Agent handles cleanup automatically
        
        # Verify accumulated metrics
        state = shared_state.read_state()
        
        assert state.mcp_tool_invocations == 5  # 3 + 2
        assert state.total_tokens == 4500  # 1500 * 3
        assert state.total_latency_ms == 90 + 200 + 180  # = 470
        assert state.action_count == 5  # 3 + 2
        assert state.observation_count == 3
        assert state.task_success is True
        assert state.final_reward == 1.0
        # cleanup_called removed - Green Agent handles cleanup automatically
        shared_state._state.final_reward = 0.0
        shared_state._state.task_completed = False
        
        # Case 2: Zero reward = failure
        shared_state.update_task_state(reward=0.0, done=True, truncated=False)
        state = shared_state.read_state()
        assert state.task_success is False
    
    def test_efficiency_penalty_calculation(self):
        """Test efficiency penalty uses real metrics."""
        # Scenario 1: Low token/latency = high efficiency
        penalty_high = calculate_efficiency_penalty(
            total_tokens=1000,
            total_latency_seconds=0.5
        )
        
        # Scenario 2: High token/latency = lower efficiency
        penalty_low = calculate_efficiency_penalty(
            total_tokens=10000,
            total_latency_seconds=5.0
        )
        
        # Higher tokens/latency should result in lower penalty (more penalty subtracted)
        assert penalty_high > penalty_low
        assert 0 <= penalty_high <= 1
        assert 0 <= penalty_low <= 1
    
    def test_final_score_calculation(self, shared_state):
        """Test final_score = task_success * efficiency_penalty."""
        # Simulate successful task with moderate efficiency
        shared_state.add_tokens(2000)
        shared_state.add_latency(500)
        shared_state.update_task_state(reward=1.0, done=True, truncated=False)
        
        state = shared_state.read_state()
        
        efficiency_penalty = calculate_efficiency_penalty(
            total_tokens=state.total_tokens,
            total_latency_seconds=state.total_latency_ms / 1000.0
        )
        
        final_score = float(state.task_success) * efficiency_penalty
        
        assert final_score > 0  # task_success=True, so score > 0
        assert final_score == efficiency_penalty  # 1.0 * efficiency_penalty
    
    def test_failed_task_has_zero_final_score(self, shared_state):
        """Test that failed tasks have zero final score regardless of efficiency."""
        # Simulate failed task with good efficiency
        shared_state.add_tokens(100)  # Very low tokens
        shared_state.add_latency(10)  # Very low latency
        shared_state.update_task_state(reward=0.0, done=True, truncated=False)
        
        state = shared_state.read_state()
        
        efficiency_penalty = calculate_efficiency_penalty(
            total_tokens=state.total_tokens,
            total_latency_seconds=state.total_latency_ms / 1000.0
        )
        
        final_score = float(state.task_success) * efficiency_penalty
        
        assert state.task_success is False
        assert final_score == 0.0  # 0.0 * efficiency_penalty = 0


class TestEventDrivenMonitoring:
    """Tests for event-driven monitoring behavior."""
    
    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    def test_completion_detected_on_cleanup(self, temp_dir):
        """Test that monitoring detects completion when cleanup_called=True."""
        manager = SharedStateManager("monitor-test", state_dir=temp_dir)
        manager.initialize()
        
        # Initially not complete
        state = manager.read_state()
        assert state.cleanup_called is False
        
        # Mark cleanup called
        manager.mark_cleanup_called()
        
        state = manager.read_state()
        assert state.cleanup_called is True
        assert state.task_completed is True
    
    def test_completion_detected_on_done(self, temp_dir):
        """Test that monitoring detects completion when done=True."""
        manager = SharedStateManager("done-test", state_dir=temp_dir)
        manager.initialize()
        
        # Initially not complete
        state = manager.read_state()
        assert state.task_completed is False
        
        # Task done via BrowserGym
        manager.update_task_state(reward=1.0, done=True, truncated=False)
        
        state = manager.read_state()
        assert state.done is True
        assert state.task_completed is True
    
    def test_completion_detected_on_truncated(self, temp_dir):
        """Test that monitoring detects completion when truncated=True."""
        manager = SharedStateManager("truncated-test", state_dir=temp_dir)
        manager.initialize()
        
        # Task truncated (max steps exceeded)
        manager.update_task_state(reward=0.0, done=False, truncated=True)
        
        state = manager.read_state()
        assert state.truncated is True
        assert state.task_completed is True
    
    def test_error_detection(self, temp_dir):
        """Test that monitoring detects errors."""
        manager = SharedStateManager("error-test", state_dir=temp_dir)
        manager.initialize()
        
        # Set error
        manager.set_error("BrowserGym environment failed to initialize")
        
        state = manager.read_state()
        assert state.error == "BrowserGym environment failed to initialize"
    
    def test_progress_tracking_via_invocation_count(self, temp_dir):
        """Test that progress can be tracked via mcp_tool_invocations."""
        manager = SharedStateManager("progress-test", state_dir=temp_dir)
        manager.initialize()
        
        last_count = 0
        
        # Simulate monitoring loop detecting new invocations (environment auto-initialized)
        manager.update_tool_invocation("get_observation")
        state = manager.read_state()
        assert state.mcp_tool_invocations > last_count
        last_count = state.mcp_tool_invocations
        
        manager.update_tool_invocation("execute_actions")
        state = manager.read_state()
        assert state.mcp_tool_invocations > last_count


class TestArtifactGeneration:
    """Tests for evaluation artifact generation with real metrics."""
    
    def test_artifact_contains_all_required_fields(self):
        """Test that EvaluationArtifact has all required fields."""
        artifact = EvaluationArtifact(
            task_success=True,
            task_id="miniwob.click-test",
            benchmark="miniwob",
            total_tokens=2500,
            total_latency_ms=450,
            peak_memory_mb=256,
            chromium_process_count=0,
            efficiency_penalty=0.85,
            final_score=0.85,
            mcp_tool_invocations=5,
            observation_count=3,
            action_count=2,
            evaluation_duration_seconds=8.5,
        )
        
        # Verify all fields are present
        assert artifact.task_success is True
        assert artifact.task_id == "miniwob.click-test"
        assert artifact.benchmark == "miniwob"
        assert artifact.total_tokens == 2500
        assert artifact.total_latency_ms == 450
        assert artifact.efficiency_penalty == 0.85
        assert artifact.final_score == 0.85
        assert artifact.mcp_tool_invocations == 5
    
    def test_artifact_from_shared_state(self):
        """Test creating artifact from shared state metrics."""
        # Create mock state as if read from shared state
        state = EvaluationState(
            session_id="artifact-test",
            task_success=True,
            final_reward=1.0,
            total_tokens=3000,
            total_latency_ms=600,
            action_count=4,
            observation_count=5,
            mcp_tool_invocations=10,
        )
        
        # Calculate efficiency penalty
        efficiency_penalty = calculate_efficiency_penalty(
            total_tokens=state.total_tokens,
            total_latency_seconds=state.total_latency_ms / 1000.0
        )
        
        # Create artifact
        artifact = EvaluationArtifact(
            task_success=state.task_success,
            task_id="miniwob.click-dialog",
            benchmark="miniwob",
            total_tokens=state.total_tokens,
            total_latency_ms=state.total_latency_ms,
            peak_memory_mb=128,
            chromium_process_count=0,
            efficiency_penalty=efficiency_penalty,
            final_score=float(state.task_success) * efficiency_penalty,
            mcp_tool_invocations=state.mcp_tool_invocations,
            observation_count=state.observation_count,
            action_count=state.action_count,
            evaluation_duration_seconds=10.0,
        )
        
        # Verify metrics came from state
        assert artifact.total_tokens == 3000
        assert artifact.total_latency_ms == 600
        assert artifact.action_count == 4
        assert artifact.observation_count == 5
        assert artifact.mcp_tool_invocations == 10
        assert artifact.final_score > 0


class TestEdgeCases:
    """Tests for edge cases and error scenarios."""
    
    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    def test_empty_evaluation_generates_valid_artifact(self):
        """Test that empty evaluation (no MCP calls) generates valid artifact."""
        artifact = EvaluationArtifact(
            task_success=False,
            task_id="miniwob.unknown-task",
            benchmark="miniwob",
            total_tokens=0,
            total_latency_ms=0,
            peak_memory_mb=0,
            chromium_process_count=0,
            efficiency_penalty=1.0,  # No penalty when no resources used
            final_score=0.0,  # task_success=False
            mcp_tool_invocations=0,
            observation_count=0,
            action_count=0,
            evaluation_duration_seconds=0.0,
            error_message="Task initialization failed",
        )
        
        assert artifact.error_message == "Task initialization failed"
        assert artifact.final_score == 0.0
    
    def test_timeout_scenario(self, temp_dir):
        """Test timeout scenario preserves partial metrics."""
        manager = SharedStateManager("timeout-test", state_dir=temp_dir)
        manager.initialize()
        
        # Simulate partial evaluation before timeout (environment auto-initialized)
        manager.update_tool_invocation("get_observation")
        manager.add_latency(100)
        manager.add_tokens(2000)
        manager.update_tool_invocation("execute_actions")
        manager.add_actions(2)
        manager.add_latency(150)
        # Green Agent handles cleanup automatically
        
        state = manager.read_state()
        
        # Partial metrics should be available
        assert state.mcp_tool_invocations == 2
        assert state.total_tokens == 2000
        assert state.total_latency_ms == 250
        assert state.action_count == 2
        # cleanup_called removed - timeout before Green Agent auto-cleanup
        manager = SharedStateManager("crash-test", state_dir=temp_dir)
        manager.initialize()
        
        # Simulate some progress before crash (environment auto-initialized)
        manager.update_tool_invocation("get_observation")
        manager.add_latency(100)
        
        # Simulate crash
        manager.set_error("Segmentation fault in BrowserGym")
        
        state = manager.read_state()
        
        assert state.error == "Segmentation fault in BrowserGym"
        assert state.mcp_tool_invocations == 1  # Partial metrics preserved
    
    def test_reward_accumulation_max(self, temp_dir):
        """Test that final_reward keeps maximum across all steps."""
        manager = SharedStateManager("reward-max-test", state_dir=temp_dir)
        manager.initialize()
        
        # Multiple rewards during episode
        manager.update_task_state(reward=0.2, done=False, truncated=False)
        manager.update_task_state(reward=0.8, done=False, truncated=False)
        manager.update_task_state(reward=0.5, done=False, truncated=False)
        manager.update_task_state(reward=0.3, done=True, truncated=False)
        
        state = manager.read_state()
        
        assert state.final_reward == 0.8  # Maximum of all rewards
        assert state.task_success is True  # max reward > 0
