"""Research task workflow primitives.

Phase 0 exposes only orchestration contracts and transition validation.
Pipeline implementations remain in services/* and are wired in later phases.
"""

from .executor import WorkflowExecutionError, WorkflowExecutor
from .state_machine import (
    ALLOWED_TRANSITIONS,
    InvalidTaskTransition,
    can_transition,
    next_statuses,
    require_transition,
)
from .types import WorkflowContext, WorkflowHooks, WorkflowStep

__all__ = [
    "ALLOWED_TRANSITIONS",
    "InvalidTaskTransition",
    "WorkflowContext",
    "WorkflowExecutionError",
    "WorkflowExecutor",
    "WorkflowHooks",
    "WorkflowStep",
    "can_transition",
    "next_statuses",
    "require_transition",
]
