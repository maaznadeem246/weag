"""
Unit tests for SharedStateManager and EvaluationState.
Tests IPC mechanism between green agent and MCP subprocess.
"""

import json
import tempfile
from pathlib import Path
import pytest

from src.green_agent.utils.shared_state import (
    SharedStateManager,
    EvaluationState,
    create_state_manager,
    get_state_manager,
    set_state_manager,
)


class TestEvaluationState:
    """Tests for EvaluationState dataclass."""
    
    def test_default_values(self):
        """Test default values are properly initialized."""
        state = EvaluationState()
        
        assert state.session_id == ""
        assert state.task_completed is False
        assert state.task_success is False
        assert state.final_reward == 0.0
        assert state.done is False
        assert state.truncated is False
        assert state.total_tokens == 0
        assert state.total_latency_ms == 0
        assert state.action_count == 0
        assert state.observation_count == 0
        assert state.mcp_tool_invocations == 0
        assert state.last_tool == ""
        assert state.error is None
        assert state.initialized is False
        assert state.cleanup_called is False
    
    def test_to_dict(self):
        """Test conversion to dictionary."""
        state = EvaluationState(
            session_id="test-123",
            task_success=True,
            final_reward=1.0,
            total_tokens=500,
        )
        
        data = state.to_dict()
        
        assert data["session_id"] == "test-123"
        assert data["task_success"] is True
        assert data["final_reward"] == 1.0
        assert data["total_tokens"] == 500
    
    def test_from_dict(self):
        """Test creation from dictionary."""
        data = {
            "session_id": "test-456",
            "task_completed": True,
            "task_success": True,
            "final_reward": 0.75,
            "total_tokens": 1000,
            "action_count": 5,
        }
        
        state = EvaluationState.from_dict(data)
        
        assert state.session_id == "test-456"
        assert state.task_completed is True
        assert state.task_success is True
        assert state.final_reward == 0.75
        assert state.total_tokens == 1000
        assert state.action_count == 5
    
    def test_from_dict_ignores_unknown_keys(self):
        """Test that unknown keys are ignored."""
        data = {
            "session_id": "test-789",
            "unknown_field": "should be ignored",
            "another_unknown": 12345,
        }
        
        state = EvaluationState.from_dict(data)
        
        assert state.session_id == "test-789"
        assert not hasattr(state, "unknown_field")


class TestSharedStateManager:
    """Tests for SharedStateManager class."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for state files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    @pytest.fixture
    def manager(self, temp_dir):
        """Create SharedStateManager with temp directory."""
        return SharedStateManager("test-session", state_dir=temp_dir)
    
    def test_initialization(self, manager, temp_dir):
        """Test manager initializes with correct paths."""
        assert manager.session_id == "test-session"
        assert manager.state_dir == Path(temp_dir)
        assert "browsergym_eval_test-session.json" in str(manager.state_file)
    
    def test_initialize_creates_file(self, manager):
        """Test initialize() creates state file."""
        manager.initialize()
        
        assert manager.state_file.exists()
        
        with open(manager.state_file) as f:
            data = json.load(f)
        
        assert data["session_id"] == "test-session"
        assert data["initialized"] is True
    
    def test_read_state_returns_empty_if_no_file(self, temp_dir):
        """Test read_state returns empty state if file doesn't exist."""
        manager = SharedStateManager("nonexistent", state_dir=temp_dir)
        
        state = manager.read_state()
        
        assert state.session_id == "nonexistent"
        assert state.initialized is False
    
    def test_read_state_returns_written_data(self, manager):
        """Test read_state returns previously written data."""
        manager.initialize()
        manager.add_tokens(100)
        manager.add_latency(50)
        manager.add_actions(3)
        
        state = manager.read_state()
        
        assert state.total_tokens == 100
        assert state.total_latency_ms == 50
        assert state.action_count == 3
    
    def test_update_tool_invocation(self, manager):
        """Test recording tool invocations."""
        manager.initialize()
        
        manager.update_tool_invocation("get_observation")
        state = manager.read_state()
        assert state.mcp_tool_invocations == 1
        assert state.last_tool == "get_observation"
        
        manager.update_tool_invocation("execute_actions")
        state = manager.read_state()
        assert state.mcp_tool_invocations == 2
        assert state.last_tool == "execute_actions"
    
    def test_add_tokens_accumulates(self, manager):
        """Test tokens accumulate correctly."""
        manager.initialize()
        
        manager.add_tokens(100)
        manager.add_tokens(200)
        manager.add_tokens(300)
        
        state = manager.read_state()
        assert state.total_tokens == 600
        assert state.observation_count == 3  # Each add_tokens increments observation count
    
    def test_add_latency_accumulates(self, manager):
        """Test latency accumulates correctly."""
        manager.initialize()
        
        manager.add_latency(10)
        manager.add_latency(20)
        manager.add_latency(30)
        
        state = manager.read_state()
        assert state.total_latency_ms == 60
    
    def test_add_actions_accumulates(self, manager):
        """Test action count accumulates correctly."""
        manager.initialize()
        
        manager.add_actions(2)
        manager.add_actions(3)
        
        state = manager.read_state()
        assert state.action_count == 5
    
    def test_update_task_state_positive_reward(self, manager):
        """Test task state update with positive reward."""
        manager.initialize()
        
        manager.update_task_state(reward=1.0, done=True, truncated=False)
        
        state = manager.read_state()
        assert state.final_reward == 1.0
        assert state.done is True
        assert state.truncated is False
        assert state.task_completed is True
        assert state.task_success is True  # reward > 0
    
    def test_update_task_state_zero_reward(self, manager):
        """Test task state update with zero reward (failure)."""
        manager.initialize()
        
        manager.update_task_state(reward=0.0, done=True, truncated=False)
        
        state = manager.read_state()
        assert state.final_reward == 0.0
        assert state.task_completed is True
        assert state.task_success is False  # reward == 0
    
    def test_update_task_state_truncated(self, manager):
        """Test task state update when truncated."""
        manager.initialize()
        
        manager.update_task_state(reward=0.0, done=False, truncated=True)
        
        state = manager.read_state()
        assert state.truncated is True
        assert state.task_completed is True
        assert state.task_success is False
    
    def test_update_task_state_keeps_max_reward(self, manager):
        """Test that final_reward keeps maximum value."""
        manager.initialize()
        
        manager.update_task_state(reward=0.5, done=False, truncated=False)
        manager.update_task_state(reward=0.8, done=False, truncated=False)
        manager.update_task_state(reward=0.3, done=True, truncated=False)
        
        state = manager.read_state()
        assert state.final_reward == 0.8  # Max of 0.5, 0.8, 0.3
    
    def test_mark_cleanup_called(self, manager):
        """Test marking cleanup as called."""
        manager.initialize()
        manager.update_task_state(reward=1.0, done=True, truncated=False)
        
        manager.mark_cleanup_called()
        
        state = manager.read_state()
        assert state.cleanup_called is True
        assert state.task_completed is True
        assert state.task_success is True
    
    def test_set_error(self, manager):
        """Test setting error state."""
        manager.initialize()
        
        manager.set_error("Something went wrong")
        
        state = manager.read_state()
        assert state.error == "Something went wrong"
    
    def test_cleanup_removes_file(self, manager):
        """Test cleanup removes state file."""
        manager.initialize()
        assert manager.state_file.exists()
        
        manager.cleanup()
        
        assert not manager.state_file.exists()
    
    def test_cleanup_handles_missing_file(self, manager):
        """Test cleanup handles case where file doesn't exist."""
        # Should not raise exception
        manager.cleanup()
    
    def test_get_state_returns_in_memory(self, manager):
        """Test get_state returns in-memory state (for MCP)."""
        manager.initialize()
        manager.add_tokens(500)
        
        state = manager.get_state()
        
        assert state.total_tokens == 500
        assert state.session_id == "test-session"


class TestGlobalStateManager:
    """Tests for global state manager functions."""
    
    def test_create_and_get_state_manager(self):
        """Test creating and retrieving global state manager."""
        manager = create_state_manager("global-test-session")
        
        retrieved = get_state_manager()
        
        assert retrieved is manager
        assert retrieved.session_id == "global-test-session"
        
        # Cleanup
        manager.cleanup()
        set_state_manager(None)
    
    def test_set_state_manager(self):
        """Test setting global state manager."""
        manager = SharedStateManager("manual-session")
        set_state_manager(manager)
        
        retrieved = get_state_manager()
        
        assert retrieved is manager
        
        # Cleanup
        set_state_manager(None)
    
    def test_get_state_manager_returns_none_initially(self):
        """Test get_state_manager returns None when not set."""
        set_state_manager(None)
        
        result = get_state_manager()
        
        assert result is None


class TestConcurrencyScenarios:
    """Tests for concurrent access scenarios."""
    
    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    def test_separate_sessions_isolated(self, temp_dir):
        """Test that separate sessions have isolated state."""
        manager1 = SharedStateManager("session-1", state_dir=temp_dir)
        manager2 = SharedStateManager("session-2", state_dir=temp_dir)
        
        manager1.initialize()
        manager2.initialize()
        
        manager1.add_tokens(100)
        manager2.add_tokens(500)
        
        state1 = manager1.read_state()
        state2 = manager2.read_state()
        
        assert state1.total_tokens == 100
        assert state2.total_tokens == 500
        
        # Cleanup
        manager1.cleanup()
        manager2.cleanup()
    
    def test_reader_writer_scenario(self, temp_dir):
        """Test reader and writer can share state (simulates MCP↔GreenAgent)."""
        session_id = "shared-session"
        
        # Writer (MCP subprocess)
        writer = SharedStateManager(session_id, state_dir=temp_dir)
        writer.initialize()
        writer.update_tool_invocation("execute_actions")
        writer.add_tokens(1000)
        writer.add_latency(50)
        
        # Reader (Green Agent) - new instance reading same file
        reader = SharedStateManager(session_id, state_dir=temp_dir)
        state = reader.read_state()
        
        assert state.initialized is True
        assert state.mcp_tool_invocations == 1
        assert state.total_tokens == 1000
        assert state.total_latency_ms == 50
        
        # Writer continues
        writer.update_tool_invocation("execute_actions")
        writer.add_actions(3)
        
        # Reader sees updates
        state = reader.read_state()
        assert state.mcp_tool_invocations == 2
        assert state.action_count == 3
        
        # Cleanup
        writer.cleanup()
