"""
Assessment tracking module for Green Agent.

Provides centralized state management for multi-task assessments and 
helper utilities for evaluation processing.

Usage:
    from src.assessment import Assessment, AssessmentConfig
    
    config = AssessmentConfig(
        run_id="eval_123",
        session_id="session_abc",
        benchmarks=["miniwob", "assistantbench"],
        tasks_by_benchmark={"miniwob": ["miniwob.click-test"], ...}
    )
    assessment = Assessment(config)
    
    # Associate state manager
    assessment.set_state_manager(shared_state_manager)
    
    # Track task progression
    assessment.mark_task_sent(0)
    assessment.snapshot_task_start(0)
    assessment.mark_task_completed(0, success=True, reward=1.0)
    
    # Build artifacts and display results
    artifact = assessment.build_task_artifact(0)
    assessment.display_summary()
"""

from src.assessment.models import (
    TaskStatus,
    TaskEntry,
    ParticipantInfo,
    AssessmentConfig,
)
from src.assessment.tracker import (
    Assessment,
    create_assessment,
)
from src.assessment.helpers import (
    # Assessment domain helpers
    create_task_result,
    store_task_result,
    check_activity_timeout,
)
from src.assessment.orchestrator import (
    AssessmentOrchestrator,
    start_orchestrator,
)

# Backward compatibility aliases
AssessmentTracker = Assessment
create_tracker_from_config = create_assessment

__all__ = [
    # Core assessment classes
    "Assessment",
    "AssessmentTracker",  # Backward compatibility
    "TaskStatus",
    "TaskEntry", 
    "ParticipantInfo",
    "AssessmentConfig",
    
    # Orchestrator
    "AssessmentOrchestrator",
    "start_orchestrator",
    
    # Factory functions
    "create_assessment",
    "create_tracker_from_config",  # Backward compatibility
    
    # Assessment domain helpers
    "create_task_result",
    "store_task_result",
    "check_activity_timeout",
]
