"""Research task workflow primitives.

Phase 0 keeps its original executor. The opt-in persistent v2 executor uses
PostgreSQL lifecycle transactions while pipeline implementations remain ports.
"""

from .executor import WorkflowExecutionError, WorkflowExecutor
from .persistent_executor import (
    FailureDecision,
    PersistentWorkflowExecutionError,
    PersistentWorkflowExecutor,
)
from .state_machine import (
    ALLOWED_TRANSITIONS,
    InvalidTaskTransition,
    can_transition,
    next_statuses,
    require_transition,
)
from .store import (
    AttemptHandle,
    LeaseGrant,
    PersistentWorkflowStore,
    RunSnapshot,
    RunStepDefinition,
    RetryBudgetExhaustedError,
    StaleWorkflowWriteError,
    WorkflowConflictError,
)
from .types import WorkflowContext, WorkflowHooks, WorkflowStep

__all__ = [
    "ALLOWED_TRANSITIONS",
    "InvalidTaskTransition",
    "AttemptHandle",
    "LeaseGrant",
    "FailureDecision",
    "PersistentWorkflowExecutionError",
    "PersistentWorkflowExecutor",
    "PersistentWorkflowStore",
    "RunSnapshot",
    "RunStepDefinition",
    "RetryBudgetExhaustedError",
    "StaleWorkflowWriteError",
    "WorkflowContext",
    "WorkflowConflictError",
    "WorkflowExecutionError",
    "WorkflowExecutor",
    "WorkflowHooks",
    "WorkflowStep",
    "can_transition",
    "next_statuses",
    "require_transition",
]
