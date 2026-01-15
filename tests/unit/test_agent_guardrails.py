"""
Unit tests for agent guardrails.

Tests input and output guardrails with various validation scenarios.
Implements T108: Unit tests for guardrails validation logic.
"""

from unittest.mock import Mock

import pytest

from src.green_agent.agent.context import AgentContext
from src.green_agent.agent.guardrails.input_guardrails import validate_evaluation_request
from src.green_agent.agent.guardrails.output_guardrails import validate_evaluation_artifact


@pytest.fixture
def mock_context():
    """Create mock agent context for guardrail testing."""
    context = Mock(spec=AgentContext)
    context.task_id = "miniwob.click-test"
    context.benchmark = "miniwob"
    context.timeout = 120
    return context


@pytest.fixture
def mock_run_context(mock_context):
    """Create mock run context wrapper."""
    run_ctx = Mock()
    run_ctx.context = mock_context
    return run_ctx


class TestInputGuardrails:
    """Test validate_evaluation_request input guardrail."""

    def test_valid_request(self, mock_run_context):
        """Test validation of valid evaluation request."""
        result = validate_evaluation_request(mock_run_context)

        assert result.is_valid is True
        assert result.error is None

    def test_invalid_benchmark(self, mock_run_context, mock_context):
        """Test validation with invalid benchmark."""
        mock_context.benchmark = "invalid-benchmark"

        result = validate_evaluation_request(mock_run_context)

        assert result.is_valid is False
        assert "not supported" in result.error.lower()
        assert "miniwob" in result.error  # Should suggest valid benchmarks

    def test_invalid_task_id_format(self, mock_run_context, mock_context):
        """Test validation with invalid task_id format."""
        mock_context.task_id = "invalid_task_id"  # Missing dot separator

        result = validate_evaluation_request(mock_run_context)

        assert result.is_valid is False
        assert "task_id" in result.error.lower()
        assert "format" in result.error.lower()

    def test_task_id_benchmark_mismatch(self, mock_run_context, mock_context):
        """Test validation when task_id prefix doesn't match benchmark."""
        mock_context.task_id = "webarena.some-task"
        mock_context.benchmark = "miniwob"

        result = validate_evaluation_request(mock_run_context)

        assert result.is_valid is False
        assert "mismatch" in result.error.lower()

    def test_timeout_too_low(self, mock_run_context, mock_context):
        """Test validation with timeout below minimum."""
        mock_context.timeout = 0  # Below minimum of 1

        result = validate_evaluation_request(mock_run_context)

        assert result.is_valid is False
        assert "timeout" in result.error.lower()

    def test_timeout_too_high(self, mock_run_context, mock_context):
        """Test validation with timeout above maximum."""
        mock_context.timeout = 4000  # Above maximum of 3600

        result = validate_evaluation_request(mock_run_context)

        assert result.is_valid is False
        assert "timeout" in result.error.lower()

    def test_timeout_none_uses_default(self, mock_run_context, mock_context):
        """Test validation when timeout is None (should use default)."""
        mock_context.timeout = None

        result = validate_evaluation_request(mock_run_context)

        assert result.is_valid is True

    @pytest.mark.parametrize("benchmark", [
        "miniwob",
        "webarena",
        "visualwebarena",
        "workarena",
        "assistantbench",
        "weblinx",
    ])
    def test_all_supported_benchmarks(self, mock_run_context, mock_context, benchmark):
        """Test validation accepts all 6 supported benchmarks."""
        mock_context.benchmark = benchmark
        mock_context.task_id = f"{benchmark}.test-task"

        result = validate_evaluation_request(mock_run_context)

        assert result.is_valid is True

    def test_batch_config_max_tasks_validation(self, mock_run_context, mock_context):
        """Test validation of batch config max_tasks."""
        from src.green_agent.agent.context import BatchEvaluationConfig, BenchmarkConfig

        mock_context.batch_evaluation_config = BatchEvaluationConfig(
            benchmarks=[
                BenchmarkConfig(benchmark="miniwob", max_tasks=101)  # Above max of 100
            ]
        )

        result = validate_evaluation_request(mock_run_context)

        assert result.is_valid is False
        assert "max_tasks" in result.error.lower()

    def test_batch_config_invalid_benchmark(self, mock_run_context, mock_context):
        """Test validation of batch config with invalid benchmark."""
        from src.green_agent.agent.context import BatchEvaluationConfig, BenchmarkConfig

        mock_context.batch_evaluation_config = BatchEvaluationConfig(
            benchmarks=[
                BenchmarkConfig(benchmark="invalid-benchmark", max_tasks=5)
            ]
        )

        result = validate_evaluation_request(mock_run_context)

        assert result.is_valid is False
        assert "benchmark" in result.error.lower()


class TestOutputGuardrails:
    """Test validate_evaluation_artifact output guardrail."""

    @pytest.fixture
    def valid_artifact(self):
        """Create valid evaluation artifact."""
        return {
            "task_id": "miniwob.click-test",
            "benchmark": "miniwob",
            "task_success": True,
            "final_score": 1.0,
            "token_cost": 1000,
            "latency_ms": 5000,
            "step_count": 10,
            "metadata": {
                "session_id": "test-session-123",
                "timestamp": "2025-12-25T10:00:00Z",
            }
        }

    def test_valid_artifact(self, mock_run_context, valid_artifact):
        """Test validation of valid artifact."""
        result = validate_evaluation_artifact(mock_run_context, valid_artifact)

        assert result.is_valid is True
        assert result.error is None

    def test_missing_required_field_task_id(self, mock_run_context, valid_artifact):
        """Test validation with missing task_id."""
        del valid_artifact["task_id"]

        result = validate_evaluation_artifact(mock_run_context, valid_artifact)

        assert result.is_valid is False
        assert "task_id" in result.error.lower()

    def test_missing_required_field_task_success(self, mock_run_context, valid_artifact):
        """Test validation with missing task_success."""
        del valid_artifact["task_success"]

        result = validate_evaluation_artifact(mock_run_context, valid_artifact)

        assert result.is_valid is False
        assert "task_success" in result.error.lower()

    def test_missing_metadata_session_id(self, mock_run_context, valid_artifact):
        """Test validation with missing metadata.session_id."""
        del valid_artifact["metadata"]["session_id"]

        result = validate_evaluation_artifact(mock_run_context, valid_artifact)

        assert result.is_valid is False
        assert "session_id" in result.error.lower()

    def test_missing_metadata_timestamp(self, mock_run_context, valid_artifact):
        """Test validation with missing metadata.timestamp."""
        del valid_artifact["metadata"]["timestamp"]

        result = validate_evaluation_artifact(mock_run_context, valid_artifact)

        assert result.is_valid is False
        assert "timestamp" in result.error.lower()

    def test_negative_token_cost(self, mock_run_context, valid_artifact):
        """Test validation with negative token_cost."""
        valid_artifact["token_cost"] = -100

        result = validate_evaluation_artifact(mock_run_context, valid_artifact)

        assert result.is_valid is False
        assert "token_cost" in result.error.lower()

    def test_negative_latency(self, mock_run_context, valid_artifact):
        """Test validation with negative latency_ms."""
        valid_artifact["latency_ms"] = -5000

        result = validate_evaluation_artifact(mock_run_context, valid_artifact)

        assert result.is_valid is False
        assert "latency_ms" in result.error.lower()

    def test_negative_step_count(self, mock_run_context, valid_artifact):
        """Test validation with negative step_count."""
        valid_artifact["step_count"] = -10

        result = validate_evaluation_artifact(mock_run_context, valid_artifact)

        assert result.is_valid is False
        assert "step_count" in result.error.lower()

    def test_final_score_out_of_range_high(self, mock_run_context, valid_artifact):
        """Test validation with final_score above 1.0."""
        valid_artifact["final_score"] = 1.5

        result = validate_evaluation_artifact(mock_run_context, valid_artifact)

        assert result.is_valid is False
        assert "final_score" in result.error.lower()

    def test_final_score_out_of_range_low(self, mock_run_context, valid_artifact):
        """Test validation with final_score below 0.0."""
        valid_artifact["final_score"] = -0.5

        result = validate_evaluation_artifact(mock_run_context, valid_artifact)

        assert result.is_valid is False
        assert "final_score" in result.error.lower()

    def test_invalid_task_success_type(self, mock_run_context, valid_artifact):
        """Test validation with non-boolean task_success."""
        valid_artifact["task_success"] = "true"  # String instead of boolean

        result = validate_evaluation_artifact(mock_run_context, valid_artifact)

        assert result.is_valid is False
        assert "task_success" in result.error.lower()

    def test_artifact_with_optional_fields(self, mock_run_context, valid_artifact):
        """Test validation with optional fields included."""
        valid_artifact["additional_metrics"] = {"custom": "value"}
        valid_artifact["error_message"] = None

        result = validate_evaluation_artifact(mock_run_context, valid_artifact)

        assert result.is_valid is True

    def test_empty_metadata(self, mock_run_context, valid_artifact):
        """Test validation with empty metadata."""
        valid_artifact["metadata"] = {}

        result = validate_evaluation_artifact(mock_run_context, valid_artifact)

        assert result.is_valid is False
        assert "metadata" in result.error.lower()


class TestGuardrailIntegration:
    """Test guardrail integration with agent execution."""

    def test_input_guardrail_blocks_invalid_request(self, mock_run_context, mock_context):
        """Test that input guardrail blocks invalid requests."""
        mock_context.benchmark = "invalid-benchmark"

        result = validate_evaluation_request(mock_run_context)

        assert result.is_valid is False
        # In actual agent execution, this would raise an exception

    def test_output_guardrail_blocks_invalid_artifact(self, mock_run_context):
        """Test that output guardrail blocks invalid artifacts."""
        invalid_artifact = {
            "task_id": "miniwob.click-test",
            # Missing required fields
        }

        result = validate_evaluation_artifact(mock_run_context, invalid_artifact)

        assert result.is_valid is False
        # In actual agent execution, this would raise an exception


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
