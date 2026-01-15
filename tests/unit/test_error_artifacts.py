"""
T050 [P] [US6] Unit test for error artifact generation

Tests that error artifacts are properly generated for different error scenarios
with appropriate error types, codes, and partial metrics.
"""

import pytest
from a2a.types import Artifact

from src.green_agent.a2a.message_handler import (
    create_error_artifact,
    create_validation_error_artifact,
    create_timeout_error_artifact,
    create_environment_error_artifact,
    create_communication_error_artifact,
)
from src.green_agent.a2a.models import ErrorType


class TestErrorArtifactCreation:
    """Test basic error artifact creation."""
    
    def test_create_error_artifact_basic(self):
        """Test creating basic error artifact."""
        artifact = create_error_artifact(
            error_type=ErrorType.VALIDATION,
            error_message="Invalid task ID format",
            error_code="INVALID_TASK_ID",
        )
        
        assert isinstance(artifact, Artifact)
        assert artifact.artifact_id is not None
        assert artifact.name == "Error Report"
        assert "Error: validation" in artifact.description
        assert len(artifact.parts) == 2  # TextPart + DataPart
    
    def test_error_artifact_has_text_part(self):
        """Test that error artifact has text part with error message."""
        artifact = create_error_artifact(
            error_type=ErrorType.TIMEOUT,
            error_message="Evaluation timeout",
            error_code="TIMEOUT",
        )
        
        # First part should be TextPart with error message
        text_part = artifact.parts[0].root
        assert text_part.kind == "text"
        assert "Error: Evaluation timeout" in text_part.text
    
    def test_error_artifact_has_data_part(self):
        """Test that error artifact has data part with error details."""
        artifact = create_error_artifact(
            error_type=ErrorType.ENVIRONMENT,
            error_message="Browser crashed",
            error_code="ENV_CRASH",
        )
        
        # Second part should be DataPart with error data
        data_part = artifact.parts[1].root
        assert data_part.kind == "data"
        assert "errorCode" in data_part.data
        assert "errorType" in data_part.data
        assert "errorMessage" in data_part.data
        assert data_part.data["errorType"] == "environment"
        assert data_part.data["errorCode"] == "ENV_CRASH"


class TestValidationErrorArtifact:
    """Test validation error artifact generation."""
    
    def test_create_validation_error_artifact(self):
        """Test creating validation error artifact."""
        artifact = create_validation_error_artifact(
            error_code="INVALID_TASK_ID",
            error_message="Task ID must be in format: benchmark.task-name",
        )
        
        assert artifact.artifact_id is not None
        data_part = artifact.parts[1].root
        assert data_part.data["errorType"] == "validation"
        assert data_part.data["errorCode"] == "INVALID_TASK_ID"
    
    def test_validation_error_with_task_id(self):
        """Test validation error includes task_id in partial metrics."""
        artifact = create_validation_error_artifact(
            error_code="INVALID_TASK_ID",
            error_message="Invalid task ID",
            task_id="invalid.task",
        )
        
        data_part = artifact.parts[1].root
        assert "partialMetrics" in data_part.data
        assert data_part.data["partialMetrics"]["task_id"] == "invalid.task"
    
    def test_validation_error_without_task_id(self):
        """Test validation error without task_id."""
        artifact = create_validation_error_artifact(
            error_code="MISSING_FIELD",
            error_message="Required field missing",
        )
        
        data_part = artifact.parts[1].root
        # partial_metrics should be None if no task_id
        assert data_part.data.get("partialMetrics") is None


class TestTimeoutErrorArtifact:
    """Test timeout error artifact generation."""
    
    def test_create_timeout_error_artifact(self):
        """Test creating timeout error artifact with partial metrics."""
        partial_metrics = {
            "elapsed_time": 30.5,
            "steps_completed": 12,
            "tokens_used": 5000,
        }
        
        artifact = create_timeout_error_artifact(
            timeout_seconds=30.0,
            partial_metrics=partial_metrics,
        )
        
        assert artifact.artifact_id is not None
        data_part = artifact.parts[1].root
        assert data_part.data["errorType"] == "timeout"
        assert data_part.data["errorCode"] == "-32002"  # JSON-RPC timeout code
        assert "30" in data_part.data["errorMessage"]
    
    def test_timeout_error_includes_partial_metrics(self):
        """Test that timeout error includes partial metrics."""
        partial_metrics = {
            "steps_completed": 8,
            "tokens_used": 3500,
            "latency_ms": 28000,
        }
        
        artifact = create_timeout_error_artifact(
            timeout_seconds=30.0,
            partial_metrics=partial_metrics,
        )
        
        data_part = artifact.parts[1].root
        assert data_part.data["partialMetrics"] == partial_metrics
        assert data_part.data["partialMetrics"]["steps_completed"] == 8
        assert data_part.data["partialMetrics"]["tokens_used"] == 3500


class TestEnvironmentErrorArtifact:
    """Test environment error artifact generation."""
    
    def test_create_environment_error_artifact(self):
        """Test creating environment error artifact."""
        artifact = create_environment_error_artifact(
            error_message="Browser process crashed",
        )
        
        assert artifact.artifact_id is not None
        data_part = artifact.parts[1].root
        assert data_part.data["errorType"] == "environment"
        assert data_part.data["errorCode"] == "-32000"  # JSON-RPC internal error code
    
    def test_environment_error_with_partial_metrics(self):
        """Test environment error with partial metrics."""
        partial_metrics = {
            "steps_before_crash": 5,
            "last_action": "click",
        }
        
        artifact = create_environment_error_artifact(
            error_message="Environment crashed during action",
            partial_metrics=partial_metrics,
        )
        
        data_part = artifact.parts[1].root
        assert data_part.data["partialMetrics"] == partial_metrics
    
    def test_environment_error_with_stack_trace(self):
        """Test environment error with stack trace."""
        stack_trace = "Traceback (most recent call last):\n  File...\nError: Browser crashed"
        
        artifact = create_environment_error_artifact(
            error_message="Browser crashed",
            stack_trace=stack_trace,
        )
        
        data_part = artifact.parts[1].root
        assert data_part.data["stackTrace"] == stack_trace


class TestCommunicationErrorArtifact:
    """Test communication error artifact generation."""
    
    def test_create_communication_error_artifact(self):
        """Test creating communication error artifact."""
        artifact = create_communication_error_artifact(
            error_message="Purple agent unreachable",
        )
        
        assert artifact.artifact_id is not None
        data_part = artifact.parts[1].root
        assert data_part.data["errorType"] == "communication"
        assert data_part.data["errorCode"] == "-32000"  # JSON-RPC internal error code
    
    def test_communication_error_with_purple_url(self):
        """Test communication error includes purple agent URL."""
        purple_url = "http://localhost:8001"
        
        artifact = create_communication_error_artifact(
            error_message="Connection timeout",
            purple_agent_url=purple_url,
        )
        
        data_part = artifact.parts[1].root
        assert "partialMetrics" in data_part.data
        assert data_part.data["partialMetrics"]["purple_agent_url"] == purple_url


class TestErrorArtifactPartialMetrics:
    """Test partial metrics in error artifacts."""
    
    def test_partial_metrics_preserved_in_error(self):
        """Test that partial metrics are preserved in error artifacts."""
        metrics = {
            "tokens_input": 1000,
            "tokens_output": 500,
            "latency_ms": 5000,
            "steps_completed": 3,
        }
        
        artifact = create_error_artifact(
            error_type=ErrorType.TIMEOUT,
            error_message="Timeout",
            error_code="TIMEOUT",
            partial_metrics=metrics,
        )
        
        data_part = artifact.parts[1].root
        assert data_part.data["partialMetrics"] == metrics
    
    def test_empty_partial_metrics(self):
        """Test error artifact with empty partial metrics dict."""
        artifact = create_error_artifact(
            error_type=ErrorType.VALIDATION,
            error_message="Validation failed",
            error_code="VALIDATION_ERROR",
            partial_metrics={},
        )
        
        data_part = artifact.parts[1].root
        # Empty dict should be preserved (not None)
        assert data_part.data["partialMetrics"] == {}
    
    def test_none_partial_metrics(self):
        """Test error artifact with None partial metrics."""
        artifact = create_error_artifact(
            error_type=ErrorType.VALIDATION,
            error_message="Validation failed",
            error_code="VALIDATION_ERROR",
            partial_metrics=None,
        )
        
        data_part = artifact.parts[1].root
        # None should not appear in serialized data (exclude_none=True)
        assert data_part.data.get("partialMetrics") is None


class TestErrorTypes:
    """Test all error types."""
    
    @pytest.mark.parametrize("error_type", [
        ErrorType.VALIDATION,
        ErrorType.TIMEOUT,
        ErrorType.ENVIRONMENT,
        ErrorType.COMMUNICATION,
    ])
    def test_all_error_types_produce_valid_artifacts(self, error_type):
        """Test that all error types produce valid artifacts."""
        artifact = create_error_artifact(
            error_type=error_type,
            error_message=f"Test {error_type.value} error",
            error_code="TEST_ERROR",
        )
        
        assert isinstance(artifact, Artifact)
        assert artifact.artifact_id is not None
        assert len(artifact.parts) == 2
        
        data_part = artifact.parts[1].root
        assert data_part.data["errorType"] == error_type.value


class TestErrorArtifactStructure:
    """Test error artifact structure compliance."""
    
    def test_error_artifact_has_unique_id(self):
        """Test that each error artifact has unique ID."""
        artifact1 = create_error_artifact(
            ErrorType.VALIDATION, "Error 1", "E1"
        )
        artifact2 = create_error_artifact(
            ErrorType.VALIDATION, "Error 2", "E2"
        )
        
        assert artifact1.artifact_id != artifact2.artifact_id
    
    def test_error_artifact_parts_structure(self):
        """Test error artifact parts structure."""
        artifact = create_error_artifact(
            ErrorType.ENVIRONMENT,
            "Test error",
            "TEST",
            partial_metrics={"test": "value"},
        )
        
        # Should have exactly 2 parts
        assert len(artifact.parts) == 2
        
        # First part: TextPart
        assert artifact.parts[0].root.kind == "text"
        
        # Second part: DataPart with error details
        assert artifact.parts[1].root.kind == "data"
        data = artifact.parts[1].root.data
        assert "errorType" in data
        assert "errorMessage" in data
        assert "errorCode" in data
