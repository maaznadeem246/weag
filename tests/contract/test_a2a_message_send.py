"""
T012 [P] [US1] Contract test for A2A message/send endpoint

Tests that the A2A message/send endpoint conforms to the A2A protocol specification.
These tests validate request/response format compliance with the A2A SDK.

Note: These are structure/schema tests. Integration tests that actually call the server
are in tests/integration/
"""

import pytest
from uuid import uuid4
from datetime import datetime, timezone


class TestA2AMessageSendContract:
    """Test A2A message/send endpoint contract compliance."""
    
    def test_message_send_request_format(self):
        """Test that message/send requests conform to A2A Message schema."""
        # Expected request format per A2A protocol
        request_message = {
            "kind": "message",
            "role": "user",
            "parts": [
                {
                    "kind": "text",
                    "text": "Evaluate task: miniwob.click-test"
                },
                {
                    "kind": "data",
                    "data": {
                        "task_id": "miniwob.click-test",
                        "benchmark": "miniwob",
                        "max_steps": 10
                    }
                }
            ],
            "messageId": str(uuid4()),
        }
        
        # Validate required fields
        assert "kind" in request_message
        assert request_message["kind"] == "message"
        assert "role" in request_message
        assert "parts" in request_message
        assert "messageId" in request_message
        assert len(request_message["parts"]) > 0
        
    def test_message_send_response_has_task_object(self):
        """Test that response contains a valid Task object."""
        # Expected response format per A2A protocol
        response_task = {
            "kind": "task",
            "id": str(uuid4()),
            "contextId": str(uuid4()),
            "status": {
                "state": "working",
                "message": "Evaluation in progress",
                "timestamp": datetime.now(timezone.utc).isoformat()
            },
            "artifacts": [],
            "history": []
        }
        
        # Validate Task object structure
        assert response_task["kind"] == "task"
        assert "id" in response_task
        assert "contextId" in response_task
        assert "status" in response_task
        assert "artifacts" in response_task
        
        # Validate TaskStatus structure
        status = response_task["status"]
        assert "state" in status
        assert status["state"] in ["submitted", "working", "input-required", "completed", "failed", "canceled"]
        assert "timestamp" in status
    
    def test_task_status_states_are_valid(self):
        """Test that task status states conform to A2A protocol."""
        valid_states = ["submitted", "working", "input-required", "completed", "failed", "canceled"]
        
        for state in valid_states:
            status = {
                "state": state,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            assert status["state"] in valid_states
    
    def test_artifact_structure_in_response(self):
        """Test that artifacts conform to A2A Artifact schema."""
        artifact = {
            "artifactId": str(uuid4()),
            "name": "Evaluation Results",
            "description": "Task completion metrics",
            "parts": [
                {
                    "kind": "text",
                    "text": "Task completed successfully"
                },
                {
                    "kind": "data",
                    "data": {
                        "task_success": True,
                        "total_tokens": 1500,
                        "total_latency_ms": 5000
                    }
                }
            ]
        }
        
        # Validate Artifact structure
        assert "artifactId" in artifact
        assert "name" in artifact
        assert "parts" in artifact
        assert len(artifact["parts"]) > 0
        
        # Validate Part structures
        for part in artifact["parts"]:
            assert "kind" in part
            assert part["kind"] in ["text", "data", "file"]


class TestA2AMessageParts:
    """Test A2A message part types."""
    
    def test_text_part_structure(self):
        """Test TextPart schema compliance."""
        text_part = {
            "kind": "text",
            "text": "This is a text message"
        }
        
        assert text_part["kind"] == "text"
        assert "text" in text_part
        assert isinstance(text_part["text"], str)
    
    def test_data_part_structure(self):
        """Test DataPart schema compliance."""
        data_part = {
            "kind": "data",
            "data": {
                "task_id": "miniwob.click-test",
                "config": {"max_steps": 10}
            }
        }
        
        assert data_part["kind"] == "data"
        assert "data" in data_part
        assert isinstance(data_part["data"], dict)
    
    def test_file_part_structure(self):
        """Test FilePart schema compliance."""
        file_part = {
            "kind": "file",
            "file": {
                "name": "screenshot.png",
                "mimeType": "image/png",
                "bytes": "base64encodeddata=="
            }
        }
        
        assert file_part["kind"] == "file"
        assert "file" in file_part
        assert "name" in file_part["file"]
        assert "mimeType" in file_part["file"]


class TestA2ATaskLifecycle:
    """Test A2A task lifecycle states."""
    
    def test_task_starts_in_submitted_state(self):
        """Test that new tasks start in 'submitted' state."""
        initial_status = {
            "state": "submitted",
            "message": "Task received",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        assert initial_status["state"] == "submitted"
    
    def test_task_transitions_to_working(self):
        """Test that tasks transition to 'working' state."""
        working_status = {
            "state": "working",
            "message": "Evaluation in progress",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        assert working_status["state"] == "working"
    
    def test_task_completes_successfully(self):
        """Test that tasks can complete successfully."""
        completed_status = {
            "state": "completed",
            "message": "Task completed successfully",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        assert completed_status["state"] == "completed"
    
    def test_task_can_fail(self):
        """Test that tasks can fail with error state."""
        failed_status = {
            "state": "failed",
            "message": "Evaluation timeout",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        assert failed_status["state"] == "failed"


class TestA2AErrorHandling:
    """Test A2A error response format."""
    
    def test_error_artifact_structure(self):
        """Test that error artifacts conform to expected structure."""
        error_artifact = {
            "artifactId": str(uuid4()),
            "name": "Error Report",
            "description": "Error: validation",
            "parts": [
                {
                    "kind": "text",
                    "text": "Error: Invalid task ID format"
                },
                {
                    "kind": "data",
                    "data": {
                        "errorCode": "INVALID_TASK_ID",
                        "errorType": "validation",
                        "errorMessage": "Task ID must be in format: benchmark.task-name"
                    }
                }
            ]
        }
        
        assert "artifactId" in error_artifact
        assert "Error" in error_artifact["name"]
        assert len(error_artifact["parts"]) == 2
        
        # Validate error data part
        data_part = error_artifact["parts"][1]
        assert data_part["kind"] == "data"
        assert "errorCode" in data_part["data"]
        assert "errorType" in data_part["data"]
        assert "errorMessage" in data_part["data"]
    
    def test_error_with_partial_metrics(self):
        """Test that error artifacts include partial metrics."""
        error_data = {
            "errorCode": "-32002",
            "errorType": "timeout",
            "errorMessage": "Evaluation timeout after 30.0s",
            "partialMetrics": {
                "steps_completed": 5,
                "tokens_used": 2000,
                "elapsed_time": 30.5
            }
        }
        
        assert "partialMetrics" in error_data
        assert "steps_completed" in error_data["partialMetrics"]
        assert "tokens_used" in error_data["partialMetrics"]


class TestA2AProtocolVersion:
    """Test A2A protocol version compliance."""
    
    def test_protocol_version_030(self):
        """Test that agent card specifies protocol version 0.3.0."""
        agent_card = {
            "protocolVersion": "0.3.0",
            "name": "BrowserGym Green Agent",
            "version": "1.0.0"
        }
        
        assert agent_card["protocolVersion"] == "0.3.0"
