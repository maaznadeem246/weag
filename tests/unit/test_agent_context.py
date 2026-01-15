"""
Unit tests for AgentContext validation.

Tests Pydantic field validation rules for AgentContext model.
Implements T109: Unit tests for AgentContext validation.
"""

import pytest
from pydantic import ValidationError

from src.green_agent.agent.context import (
    AgentContext,
    AgentThinkingEvent,
    BatchEvaluationConfig,
    BenchmarkConfig,
    GuardrailEvent,
    StreamingEvent,
    ToolCallEvent,
    ToolResultEvent,
)


class TestAgentContextValidation:
    """Test AgentContext field validation."""

    def test_valid_context_creation(self):
        """Test creating valid AgentContext."""
        context = AgentContext(
            task_id="miniwob.click-test",
            benchmark="miniwob",
            timeout=120,
            purple_agent_url="http://localhost:8000",
        )

        assert context.task_id == "miniwob.click-test"
        assert context.benchmark == "miniwob"
        assert context.timeout == 120
        assert context.environment_initialized is False
        assert context.task_complete is False

    def test_required_field_task_id(self):
        """Test that task_id is required."""
        with pytest.raises(ValidationError) as exc_info:
            AgentContext(
                benchmark="miniwob",
                timeout=120,
                purple_agent_url="http://localhost:8000",
            )

        assert "task_id" in str(exc_info.value)

    def test_required_field_benchmark(self):
        """Test that benchmark is required."""
        with pytest.raises(ValidationError) as exc_info:
            AgentContext(
                task_id="miniwob.click-test",
                timeout=120,
                purple_agent_url="http://localhost:8000",
            )

        assert "benchmark" in str(exc_info.value)

    def test_optional_field_timeout_default(self):
        """Test that timeout has default value."""
        context = AgentContext(
            task_id="miniwob.click-test",
            benchmark="miniwob",
            purple_agent_url="http://localhost:8000",
        )

        assert context.timeout is not None  # Should have default value

    def test_optional_field_purple_agent_url_none(self):
        """Test that purple_agent_url can be None."""
        context = AgentContext(
            task_id="miniwob.click-test",
            benchmark="miniwob",
            timeout=120,
        )

        assert context.purple_agent_url is None

    def test_session_id_default_generation(self):
        """Test that session_id is generated if not provided."""
        context = AgentContext(
            task_id="miniwob.click-test",
            benchmark="miniwob",
            timeout=120,
        )

        assert context.session_id is not None
        assert len(context.session_id) > 0

    def test_mcp_connection_details_optional(self):
        """Test that mcp_connection_details is optional."""
        context = AgentContext(
            task_id="miniwob.click-test",
            benchmark="miniwob",
            timeout=120,
        )

        assert context.mcp_connection_details is None

    def test_mcp_connection_details_dict(self):
        """Test that mcp_connection_details accepts dict."""
        context = AgentContext(
            task_id="miniwob.click-test",
            benchmark="miniwob",
            timeout=120,
            mcp_connection_details={
                "command": "python",
                "args": ["-m", "server"],
                "port": 5000,
            }
        )

        assert context.mcp_connection_details["command"] == "python"
        assert context.mcp_connection_details["port"] == 5000

    def test_efficiency_metrics_default_initialization(self):
        """Test that efficiency_metrics initializes with defaults."""
        context = AgentContext(
            task_id="miniwob.click-test",
            benchmark="miniwob",
            timeout=120,
        )

        assert context.efficiency_metrics is not None
        assert "token_cost" in context.efficiency_metrics
        assert "latency_ms" in context.efficiency_metrics
        assert "step_count" in context.efficiency_metrics

    def test_lists_default_to_empty(self):
        """Test that list fields default to empty lists."""
        context = AgentContext(
            task_id="miniwob.click-test",
            benchmark="miniwob",
            timeout=120,
        )

        assert context.actions_taken == []
        assert context.observations_collected == []

    def test_boolean_fields_default_to_false(self):
        """Test that boolean fields default to False."""
        context = AgentContext(
            task_id="miniwob.click-test",
            benchmark="miniwob",
            timeout=120,
        )

        assert context.environment_initialized is False
        assert context.task_complete is False

    def test_context_allows_arbitrary_types(self):
        """Test that context allows arbitrary types (for mcp_server_process)."""
        from unittest.mock import Mock

        mock_process = Mock()
        context = AgentContext(
            task_id="miniwob.click-test",
            benchmark="miniwob",
            timeout=120,
            mcp_server_process=mock_process,
        )

        assert context.mcp_server_process is mock_process


class TestBenchmarkConfigValidation:
    """Test BenchmarkConfig field validation."""

    def test_valid_benchmark_config(self):
        """Test creating valid BenchmarkConfig."""
        config = BenchmarkConfig(
            benchmark="miniwob",
            max_tasks=5,
            task_selection_strategy="random",
        )

        assert config.benchmark == "miniwob"
        assert config.max_tasks == 5
        assert config.task_selection_strategy == "random"

    def test_benchmark_required(self):
        """Test that benchmark is required."""
        with pytest.raises(ValidationError) as exc_info:
            BenchmarkConfig(
                max_tasks=5,
            )

        assert "benchmark" in str(exc_info.value)

    def test_max_tasks_default(self):
        """Test that max_tasks has default value."""
        config = BenchmarkConfig(benchmark="miniwob")

        assert config.max_tasks is not None

    def test_task_selection_strategy_default(self):
        """Test that task_selection_strategy has default value."""
        config = BenchmarkConfig(benchmark="miniwob")

        assert config.task_selection_strategy in ["random", "sequential", "specific"]

    def test_specific_task_ids_optional(self):
        """Test that specific_task_ids is optional."""
        config = BenchmarkConfig(benchmark="miniwob")

        assert config.specific_task_ids is None

    def test_specific_task_ids_list(self):
        """Test that specific_task_ids accepts list."""
        config = BenchmarkConfig(
            benchmark="miniwob",
            task_selection_strategy="specific",
            specific_task_ids=["miniwob.click-test", "miniwob.click-button"],
        )

        assert len(config.specific_task_ids) == 2


class TestBatchEvaluationConfigValidation:
    """Test BatchEvaluationConfig field validation."""

    def test_valid_batch_config(self):
        """Test creating valid BatchEvaluationConfig."""
        config = BatchEvaluationConfig(
            benchmarks=[
                BenchmarkConfig(benchmark="miniwob", max_tasks=5),
                BenchmarkConfig(benchmark="webarena", max_tasks=3),
            ],
            stop_on_error=False,
        )

        assert len(config.benchmarks) == 2
        assert config.stop_on_error is False

    def test_benchmarks_required(self):
        """Test that benchmarks list is required."""
        with pytest.raises(ValidationError) as exc_info:
            BatchEvaluationConfig(stop_on_error=False)

        assert "benchmarks" in str(exc_info.value)

    def test_stop_on_error_default(self):
        """Test that stop_on_error has default value."""
        config = BatchEvaluationConfig(
            benchmarks=[BenchmarkConfig(benchmark="miniwob")],
        )

        assert config.stop_on_error is not None

    def test_empty_benchmarks_list_invalid(self):
        """Test that empty benchmarks list is invalid."""
        with pytest.raises(ValidationError) as exc_info:
            BatchEvaluationConfig(benchmarks=[])

        assert "benchmarks" in str(exc_info.value)


class TestStreamingEventValidation:
    """Test streaming event model validation."""

    def test_agent_thinking_event(self):
        """Test AgentThinkingEvent validation."""
        event = AgentThinkingEvent(
            session_id="test-session",
            task_id="miniwob.click-test",
            reasoning="Analyzing the page structure...",
        )

        assert event.event_type == "agent_thinking"
        assert event.reasoning == "Analyzing the page structure..."
        assert event.timestamp is not None

    def test_tool_call_event(self):
        """Test ToolCallEvent validation."""
        event = ToolCallEvent(
            session_id="test-session",
            task_id="miniwob.click-test",
            tool_name="calculate_efficiency_score",
            tool_args={"task_id": "miniwob.click-test"},
        )

        assert event.event_type == "tool_call"
        assert event.tool_name == "calculate_efficiency_score"
        assert event.tool_args["task_id"] == "miniwob.click-test"

    def test_tool_result_event(self):
        """Test ToolResultEvent validation."""
        event = ToolResultEvent(
            session_id="test-session",
            task_id="miniwob.click-test",
            tool_name="calculate_efficiency_score",
            result_status="success",
            result_data={"status": "success"},
        )

        assert event.event_type == "tool_result"
        assert event.result_status == "success"

    def test_guardrail_event(self):
        """Test GuardrailEvent validation."""
        event = GuardrailEvent(
            session_id="test-session",
            task_id="miniwob.click-test",
            guardrail_type="input",
            validation_result="passed",
            message="Request validated successfully",
        )

        assert event.event_type == "guardrail"
        assert event.guardrail_type == "input"
        assert event.validation_result == "passed"

    def test_streaming_event_base_required_fields(self):
        """Test StreamingEvent base class required fields."""
        with pytest.raises(ValidationError) as exc_info:
            StreamingEvent(
                session_id="test-session",
                # Missing task_id
            )

        assert "task_id" in str(exc_info.value)


class TestContextImmutability:
    """Test context field immutability where appropriate."""

    def test_can_update_mutable_fields(self):
        """Test that mutable fields can be updated."""
        context = AgentContext(
            task_id="miniwob.click-test",
            benchmark="miniwob",
            timeout=120,
        )

        # These should be mutable
        context.environment_initialized = True
        context.task_complete = True
        context.final_reward = 1.0
        context.actions_taken.append({"action": "click"})

        assert context.environment_initialized is True
        assert context.task_complete is True
        assert context.final_reward == 1.0
        assert len(context.actions_taken) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
