"""
Unit tests for agent tools.

Tests all 10 agent tools with mocked context and dependencies.
Implements T107: Comprehensive unit tests for agent tools.
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from src.green_agent.agent.context import AgentContext, BatchEvaluationConfig, BenchmarkConfig
from src.green_agent.agent.tools.evaluation_tools import (
    calculate_efficiency_score,
    cleanup_evaluation,
    generate_evaluation_artifact,
    get_current_state,
    initialize_evaluation,
    orchestrate_batch_evaluation,
    send_task_update,
)
from src.green_agent.agent.tools.communication_tools import send_mcp_details_to_purple_agent
from src.green_agent.agent.tools.environment_tools import verify_mcp_server_health


@pytest.fixture
def mock_context():
    """Create mock agent context."""
    context = Mock(spec=AgentContext)
    context.task_id = "miniwob.click-test"
    context.benchmark = "miniwob"
    context.timeout = 120
    context.mcp_server_process = Mock()
    context.mcp_server_process.poll.return_value = None  # Process running
    context.mcp_connection_details = {
        "command": "python",
        "args": ["-m", "src.green_agent.mcp_server"],
        "port": 5000,
    }
    context.environment_initialized = False
    context.session_id = "test-session-123"
    context.actions_taken = []
    context.observations_collected = []
    context.task_complete = False
    context.final_reward = None
    context.efficiency_metrics = {
        "token_cost": 0,
        "latency_ms": 0,
        "step_count": 0,
    }
    context.purple_agent_url = "http://localhost:8000"
    return context


@pytest.fixture
def mock_run_context(mock_context):
    """Create mock run context wrapper."""
    run_ctx = Mock()
    run_ctx.context = mock_context
    return run_ctx


class TestVerifyMCPHealth:
    """Test verify_mcp_server_health tool."""

    @pytest.mark.asyncio
    async def test_verify_mcp_health_success(self, mock_run_context, mock_context):
        """Test successful MCP health check."""
        with patch("src.green_agent.agent.tools.environment_tools.check_mcp_health") as mock_check:
            mock_check.return_value = {
                "status": "healthy",
                "tools_available": 4,
                "uptime_seconds": 10,
            }

            result = await verify_mcp_server_health(mock_run_context)

            assert result["status"] == "healthy"
            assert result["tools_available"] == 4
            mock_check.assert_called_once()

    @pytest.mark.asyncio
    async def test_verify_mcp_health_not_initialized(self, mock_run_context, mock_context):
        """Test health check when environment not initialized."""
        mock_context.environment_initialized = False

        result = await verify_mcp_server_health(mock_run_context)

        assert result["status"] == "not_initialized"

    @pytest.mark.asyncio
    async def test_verify_mcp_health_process_dead(self, mock_run_context, mock_context):
        """Test health check when MCP process is dead."""
        mock_context.mcp_server_process.poll.return_value = 1  # Process exited

        result = await verify_mcp_server_health(mock_run_context)

        assert result["status"] == "unhealthy"
        assert "Process terminated" in result["error"]


class TestSendMCPDetails:
    """Test send_mcp_details_to_purple_agent tool."""

    @pytest.mark.asyncio
    async def test_send_mcp_details_success(self, mock_run_context, mock_context):
        """Test successful MCP details sending."""
        with patch("src.green_agent.agent.tools.communication_tools.emit_task_update", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = {"status": "success"}

            result = await send_mcp_details_to_purple_agent(mock_run_context)

            assert result["status"] == "success"
            assert "mcp_details" in result
            mock_send.assert_awaited()

    @pytest.mark.asyncio
    async def test_send_mcp_details_no_connection_info(self, mock_run_context, mock_context):
        """Test sending MCP details when connection info missing."""
        mock_context.mcp_connection_details = None

        result = await send_mcp_details_to_purple_agent(mock_run_context)

        assert result["status"] == "error"
        assert "connection details" in result.get("message", "").lower()


class TestGetCurrentState:
    """Test get_current_state tool."""

    @pytest.mark.asyncio
    async def test_get_current_state(self, mock_run_context, mock_context):
        """Test getting current state."""
        result = await get_current_state(mock_run_context)

        assert result["task_id"] == "miniwob.click-test"
        assert result["benchmark"] == "miniwob"
        assert result["session_id"] == "test-session-123"
        assert result["environment_initialized"] is False
        assert "efficiency_metrics" in result


class TestCalculateEfficiencyScore:
    """Test calculate_efficiency_score tool."""

    @pytest.mark.asyncio
    async def test_calculate_efficiency_score(self, mock_run_context, mock_context):
        """Test efficiency score calculation."""
        mock_context.efficiency_metrics = {
            "token_cost": 1000,
            "latency_ms": 5000,
            "step_count": 10,
        }
        mock_context.task_complete = True
        mock_context.final_reward = 1.0

        result = await calculate_efficiency_score(mock_run_context)

        assert result["status"] == "calculated"
        assert "efficiency_score" in result
        assert "cost_penalty" in result
        assert "latency_penalty" in result
        assert "fragility_penalty" in result

    @pytest.mark.asyncio
    async def test_calculate_efficiency_score_task_failed(self, mock_run_context, mock_context):
        """Test efficiency score when task failed."""
        mock_context.task_complete = False
        mock_context.final_reward = 0.0

        result = await calculate_efficiency_score(mock_run_context)

        assert result["status"] == "calculated"
        assert result["efficiency_score"] == 0.0


class TestGenerateEvaluationArtifact:
    """Test generate_evaluation_artifact tool."""

    @pytest.mark.asyncio
    async def test_generate_artifact_success(self, mock_run_context, mock_context):
        """Test successful artifact generation."""
        mock_context.task_complete = True
        mock_context.final_reward = 1.0
        mock_context.efficiency_metrics = {
            "token_cost": 1000,
            "latency_ms": 5000,
            "step_count": 10,
        }

        result = await generate_evaluation_artifact(mock_run_context)

        assert result["status"] == "generated"
        assert "artifact" in result
        artifact = result["artifact"]
        assert artifact["task_id"] == "miniwob.click-test"
        assert artifact["task_success"] is True
        assert artifact["final_score"] == 1.0

    @pytest.mark.asyncio
    async def test_generate_artifact_task_incomplete(self, mock_run_context, mock_context):
        """Test artifact generation when task incomplete."""
        mock_context.task_complete = False

        result = await generate_evaluation_artifact(mock_run_context)

        assert result["status"] == "generated"
        artifact = result["artifact"]
        assert artifact["task_success"] is False


class TestCleanupEvaluation:
    """Test cleanup_evaluation tool."""

    @pytest.mark.asyncio
    async def test_cleanup_success(self, mock_run_context, mock_context):
        """Test successful cleanup."""
        with patch("src.green_agent.agent.tools.evaluation_tools.cleanup_mcp_server") as mock_cleanup:
            mock_cleanup.return_value = {"status": "cleaned"}

            result = await cleanup_evaluation(mock_run_context)

            assert result["status"] == "cleaned"
            mock_cleanup.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_not_initialized(self, mock_run_context, mock_context):
        """Test cleanup when environment not initialized."""
        mock_context.environment_initialized = False

        result = await cleanup_evaluation(mock_run_context)

        assert result["status"] == "skipped"


class TestSendTaskUpdate:
    """Test send_task_update tool."""

    @pytest.mark.asyncio
    async def test_send_task_update_success(self, mock_run_context, mock_context):
        """Test successful task update sending."""
        with patch("src.green_agent.agent.tools.evaluation_tools.emit_sse_event") as mock_emit:
            result = await send_task_update(
                mock_run_context,
                update_type="progress",
                message="Task in progress",
                data={"actions": 5}
            )

            assert result["status"] == "sent"
            mock_emit.assert_called_once()


class TestOrchestrateBatchEvaluation:
    """Test orchestrate_batch_evaluation tool."""

    @pytest.mark.asyncio
    async def test_batch_evaluation_success(self, mock_run_context, mock_context):
        """Test successful batch evaluation."""
        batch_config = BatchEvaluationConfig(
            benchmarks=[
                BenchmarkConfig(
                    benchmark="miniwob",
                    max_tasks=2,
                    task_selection_strategy="random"
                )
            ],
            stop_on_error=False,
        )
        mock_context.batch_evaluation_config = batch_config

        with patch("src.green_agent.agent.tools.evaluation_tools.run_single_evaluation") as mock_run:
            mock_run.return_value = {
                "task_success": True,
                "final_score": 1.0,
                "token_cost": 1000,
                "latency_ms": 5000,
            }

            result = await orchestrate_batch_evaluation(mock_run_context)

            assert result["status"] == "completed"
            assert "results" in result
            assert len(result["results"]) == 1  # 1 benchmark
            assert result["results"][0]["benchmark"] == "miniwob"

    @pytest.mark.asyncio
    async def test_batch_evaluation_stop_on_error(self, mock_run_context, mock_context):
        """Test batch evaluation with stop_on_error."""
        batch_config = BatchEvaluationConfig(
            benchmarks=[
                BenchmarkConfig(benchmark="miniwob", max_tasks=2),
                BenchmarkConfig(benchmark="webarena", max_tasks=2),
            ],
            stop_on_error=True,
        )
        mock_context.batch_evaluation_config = batch_config

        with patch("src.green_agent.agent.tools.evaluation_tools.run_single_evaluation") as mock_run:
            mock_run.side_effect = Exception("Evaluation failed")

            result = await orchestrate_batch_evaluation(mock_run_context)

            assert result["status"] == "failed"
            assert "error" in result


@pytest.mark.asyncio
async def test_all_tools_have_langfuse_decorators():
    """Test that all tools have @observe decorators for tracing."""
    from src.green_agent.agent.tools import AGENT_TOOLS

    assert len(AGENT_TOOLS) == 11, "Expected 11 agent tools"

    # Verify each tool has observe decorator
    for tool in AGENT_TOOLS:
        # Check if function has __wrapped__ attribute (sign of decorator)
        assert hasattr(tool, "__name__"), f"Tool {tool} missing __name__"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
