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
from .publisher import (
    AdmittedArtifactCandidate,
    ArtifactAdmissionContext,
    ArtifactPublication,
    ArtifactPublisher,
    ProducerExecutionConflictError,
    ProducerExecutionRequest,
    ProducerExecutionSnapshot,
    ProducerExecutionStore,
    PublicationAdmissionError,
    PublicationConflictError,
    PublicationResult,
    StalePublicationError,
    admit_artifact_candidate,
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
    "AdmittedArtifactCandidate",
    "ArtifactAdmissionContext",
    "ArtifactPublication",
    "ArtifactPublisher",
    "InvalidTaskTransition",
    "AttemptHandle",
    "LeaseGrant",
    "FailureDecision",
    "PersistentWorkflowExecutionError",
    "PersistentWorkflowExecutor",
    "PersistentWorkflowStore",
    "ProducerExecutionConflictError",
    "ProducerExecutionRequest",
    "ProducerExecutionSnapshot",
    "ProducerExecutionStore",
    "PublicationAdmissionError",
    "PublicationConflictError",
    "PublicationResult",
    "RunSnapshot",
    "RunStepDefinition",
    "RetryBudgetExhaustedError",
    "StaleWorkflowWriteError",
    "StalePublicationError",
    "WorkflowContext",
    "WorkflowConflictError",
    "WorkflowExecutionError",
    "WorkflowExecutor",
    "WorkflowHooks",
    "WorkflowStep",
    "can_transition",
    "admit_artifact_candidate",
    "next_statuses",
    "require_transition",
]
