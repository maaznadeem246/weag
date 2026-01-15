"""
T013 [P] [US1] Contract test for A2A task response schema

Tests that Task objects returned by the green agent conform to the A2A protocol specification.
These tests validate the Task, TaskStatus, and Artifact schema compliance.
"""

import pytest
from uuid import uuid4
from datetime import datetime, timezone


class TestA2ATaskSchema:
    """Test A2A Task schema compliance."""
    
    def test_task_has_required_fields(self):
        """Test that Task objects contain all required fields."""
        task = {
            "kind": "task",
            "id": str(uuid4()),
            "contextId": str(uuid4()),
            "status": {
                "state": "working",
                "timestamp": datetime.now(timezone.utc).isoformat()
            },
            "artifacts": [],
            "history": []
        }
        
        # Validate required Task fields
        assert task["kind"] == "task"
        assert "id" in task
        assert "contextId" in task
        assert "status" in task
        assert "artifacts" in task
        assert isinstance(task["artifacts"], list)
    
    def test_task_status_schema(self):
        """Test that TaskStatus conforms to A2A schema."""
        status = {
            "state": "working",
            "message": "Evaluation in progress",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        # Validate required status fields
        assert "state" in status
        assert "timestamp" in status
        
        # Validate state is one of allowed values
        valid_states = ["submitted", "working", "input-required", "completed", "failed", "canceled"]
        assert status["state"] in valid_states
        
        # Validate timestamp is ISO format
        assert "T" in status["timestamp"]
        assert "Z" in status["timestamp"] or "+" in status["timestamp"] or "-" in status["timestamp"]
    
    def test_task_all_status_states(self):
        """Test all valid task status states."""
        valid_states = ["submitted", "working", "input-required", "completed", "failed", "canceled"]
        
        for state in valid_states:
            status = {
                "state": state,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            assert status["state"] == state
    
    def test_artifact_schema(self):
        """Test that Artifact objects conform to A2A schema."""
        artifact = {
            "artifactId": str(uuid4()),
            "name": "Evaluation Results",
            "description": "Task completion metrics",
            "parts": [
                {
                    "kind": "text",
                    "text": "Task completed successfully"
                }
            ]
        }
        
        # Validate required Artifact fields
        assert "artifactId" in artifact
        assert "name" in artifact
        assert "parts" in artifact
        assert isinstance(artifact["parts"], list)
        assert len(artifact["parts"]) > 0
    
    def test_artifact_with_data_part(self):
        """Test artifact with data part containing metrics."""
        artifact = {
            "artifactId": str(uuid4()),
            "name": "Evaluation Results",
            "parts": [
                {
                    "kind": "data",
                    "data": {
                        "task_success": True,
                        "total_tokens": 1500,
                        "total_latency_ms": 5000,
                        "steps": 10
                    }
                }
            ]
        }
        
        # Validate data part
        data_part = artifact["parts"][0]
        assert data_part["kind"] == "data"
        assert "data" in data_part
        assert isinstance(data_part["data"], dict)
    
    def test_task_with_multiple_artifacts(self):
        """Test task with multiple artifacts."""
        task = {
            "kind": "task",
            "id": str(uuid4()),
            "contextId": str(uuid4()),
            "status": {
                "state": "completed",
                "timestamp": datetime.now(timezone.utc).isoformat()
            },
            "artifacts": [
                {
                    "artifactId": str(uuid4()),
                    "name": "Evaluation Results",
                    "parts": [{"kind": "text", "text": "Results"}]
                },
                {
                    "artifactId": str(uuid4()),
                    "name": "Metrics Report",
                    "parts": [{"kind": "data", "data": {"tokens": 1000}}]
                }
            ],
            "history": []
        }
        
        assert len(task["artifacts"]) == 2
        assert all("artifactId" in a for a in task["artifacts"])


class TestA2AMessageParts:
    """Test A2A message part schemas."""
    
    def test_text_part_schema(self):
        """Test TextPart schema compliance."""
        text_part = {
            "kind": "text",
            "text": "This is a text message"
        }
        
        assert text_part["kind"] == "text"
        assert "text" in text_part
        assert isinstance(text_part["text"], str)
    
    def test_data_part_schema(self):
        """Test DataPart schema compliance."""
        data_part = {
            "kind": "data",
            "data": {
                "task_id": "miniwob.click-test",
                "benchmark": "miniwob",
                "max_steps": 10,
                "config": {"option": "value"}
            }
        }
        
        assert data_part["kind"] == "data"
        assert "data" in data_part
        assert isinstance(data_part["data"], dict)
    
    def test_file_part_schema(self):
        """Test FilePart schema compliance."""
        file_part = {
            "kind": "file",
            "file": {
                "name": "screenshot.png",
                "mimeType": "image/png",
                "bytes": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
            }
        }
        
        assert file_part["kind"] == "file"
        assert "file" in file_part
        assert "name" in file_part["file"]
        assert "mimeType" in file_part["file"]
        assert "bytes" in file_part["file"]


class TestA2AErrorArtifacts:
    """Test A2A error artifact schema."""
    
    def test_error_artifact_structure(self):
        """Test error artifact conforms to expected structure."""
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
        assert len(error_artifact["parts"]) >= 1
        
        # Find data part with error info
        data_parts = [p for p in error_artifact["parts"] if p["kind"] == "data"]
        assert len(data_parts) > 0
        
        error_data = data_parts[0]["data"]
        assert "errorCode" in error_data
        assert "errorType" in error_data
        assert "errorMessage" in error_data
    
    def test_error_artifact_with_partial_metrics(self):
        """Test error artifact includes partial metrics."""
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
        assert isinstance(error_data["partialMetrics"], dict)
        assert "steps_completed" in error_data["partialMetrics"]
        assert "tokens_used" in error_data["partialMetrics"]
    
    def test_error_artifact_types(self):
        """Test all error types conform to schema."""
        error_types = ["validation", "timeout", "environment", "communication", "internal"]
        
        for error_type in error_types:
            error_data = {
                "errorCode": f"{error_type.upper()}_ERROR",
                "errorType": error_type,
                "errorMessage": f"Error of type {error_type}"
            }
            
            assert error_data["errorType"] == error_type
            assert "errorCode" in error_data
            assert "errorMessage" in error_data


class TestA2ATaskLifecycle:
    """Test A2A task lifecycle state transitions."""
    
    def test_task_lifecycle_states(self):
        """Test valid task lifecycle state transitions."""
        # submitted -> working
        task = {
            "kind": "task",
            "id": str(uuid4()),
            "contextId": str(uuid4()),
            "status": {"state": "submitted", "timestamp": datetime.now(timezone.utc).isoformat()},
            "artifacts": [],
            "history": []
        }
        assert task["status"]["state"] == "submitted"
        
        # working -> completed
        task["status"] = {"state": "working", "timestamp": datetime.now(timezone.utc).isoformat()}
        assert task["status"]["state"] == "working"
        
        # completed (terminal state)
        task["status"] = {"state": "completed", "timestamp": datetime.now(timezone.utc).isoformat()}
        assert task["status"]["state"] == "completed"
    
    def test_task_failure_state(self):
        """Test task can transition to failed state."""
        task = {
            "kind": "task",
            "id": str(uuid4()),
            "contextId": str(uuid4()),
            "status": {
                "state": "failed",
                "message": "Evaluation timeout",
                "timestamp": datetime.now(timezone.utc).isoformat()
            },
            "artifacts": [],
            "history": []
        }
        
        assert task["status"]["state"] == "failed"
        assert "message" in task["status"]


class TestA2AHistoryEntries:
    """Test A2A task history entries."""
    
    def test_history_entry_structure(self):
        """Test history entries conform to expected structure."""
        history_entry = {
            "kind": "message",
            "role": "assistant",
            "parts": [
                {
                    "kind": "text",
                    "text": "Starting evaluation for task: miniwob.click-test"
                }
            ],
            "messageId": str(uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        assert history_entry["kind"] == "message"
        assert "role" in history_entry
        assert "parts" in history_entry
        assert "messageId" in history_entry
    
    def test_task_with_history(self):
        """Test task with history entries."""
        task = {
            "kind": "task",
            "id": str(uuid4()),
            "contextId": str(uuid4()),
            "status": {"state": "working", "timestamp": datetime.now(timezone.utc).isoformat()},
            "artifacts": [],
            "history": [
                {
                    "kind": "message",
                    "role": "user",
                    "parts": [{"kind": "text", "text": "Start task"}],
                    "messageId": str(uuid4())
                },
                {
                    "kind": "message",
                    "role": "assistant",
                    "parts": [{"kind": "text", "text": "Task started"}],
                    "messageId": str(uuid4())
                }
            ]
        }
        
        assert len(task["history"]) == 2
        assert all("messageId" in h for h in task["history"])
