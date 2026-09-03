"""Public contracts for immutable feedback and revision orchestration."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StringConstraints,
    model_validator,
)

from app.schemas.core import ArtifactKind, ContentHash, Identifier, UtcDateTime

MODEL_CONFIG = ConfigDict(extra="forbid", frozen=True)
FeedbackText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)
]


class FeedbackTargetType(StrEnum):
    artifact = "artifact"
    artifact_version = "artifact_version"
    dataset_field = "dataset_field"
    dataset_row = "dataset_row"
    paper = "paper"
    paper_summary = "paper_summary"
    claim = "claim"
    relation = "relation"
    trace = "trace"
    graph_node = "graph_node"
    graph_edge = "graph_edge"


class FeedbackCategory(StrEnum):
    correction = "correction"
    omission = "omission"
    evidence = "evidence"
    quality = "quality"
    interpretation = "interpretation"
    adjudication = "adjudication"


class RelationAdjudicationDecision(StrEnum):
    accepted = "accepted"
    rejected = "rejected"


class RevisionPlanStatus(StrEnum):
    proposed = "proposed"
    confirmed = "confirmed"


class RevisionDecision(StrEnum):
    recompute = "recompute"
    reuse = "reuse"


class CreateUserFeedbackRequest(BaseModel):
    model_config = MODEL_CONFIG

    expected_version_number: int = Field(ge=1)
    target_type: FeedbackTargetType
    target_id: Identifier
    target_locator: dict[str, JsonValue] = Field(default_factory=dict)
    category: FeedbackCategory
    adjudication_decision: RelationAdjudicationDecision | None = None
    summary: FeedbackText
    requested_change: FeedbackText

    @model_validator(mode="after")
    def validate_adjudication(self) -> CreateUserFeedbackRequest:
        if self.category is FeedbackCategory.adjudication:
            if (
                self.target_type is not FeedbackTargetType.relation
                or self.adjudication_decision is None
            ):
                raise ValueError(
                    "relation adjudication requires a relation target and decision"
                )
        elif self.adjudication_decision is not None:
            raise ValueError("adjudication_decision requires adjudication category")
        return self


class UserFeedback(BaseModel):
    model_config = MODEL_CONFIG

    id: Identifier
    project_id: Identifier
    artifact_id: Identifier
    baseline_artifact_version_id: Identifier
    baseline_version_number: int = Field(ge=1)
    baseline_content_hash: ContentHash
    target_type: FeedbackTargetType
    target_id: Identifier
    target_locator: dict[str, JsonValue]
    category: FeedbackCategory
    adjudication_decision: RelationAdjudicationDecision | None = None
    summary: FeedbackText
    requested_change: FeedbackText
    feedback_hash: ContentHash
    created_at: UtcDateTime

    @model_validator(mode="after")
    def validate_adjudication(self) -> UserFeedback:
        if self.category is FeedbackCategory.adjudication:
            if (
                self.target_type is not FeedbackTargetType.relation
                or self.adjudication_decision is None
            ):
                raise ValueError(
                    "relation adjudication requires a relation target and decision"
                )
        elif self.adjudication_decision is not None:
            raise ValueError("adjudication_decision requires adjudication category")
        return self


class CreateRevisionPlanRequest(BaseModel):
    model_config = MODEL_CONFIG

    feedback_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=100)
    expected_parent_run_revision: int = Field(ge=1)

    @model_validator(mode="after")
    def require_unique_feedback(self) -> CreateRevisionPlanRequest:
        if len(self.feedback_ids) != len(set(self.feedback_ids)):
            raise ValueError("feedback_ids must not contain duplicates")
        return self


class RevisionVersionDecision(BaseModel):
    model_config = MODEL_CONFIG

    artifact_version_id: Identifier
    artifact_id: Identifier
    artifact_kind: ArtifactKind
    version_number: int = Field(ge=1)
    decision: RevisionDecision
    step_key: Identifier | None = None

    @model_validator(mode="after")
    def validate_decision_shape(self) -> RevisionVersionDecision:
        if self.decision is RevisionDecision.recompute and self.step_key is None:
            raise ValueError("recompute decision requires step_key")
        if self.decision is RevisionDecision.reuse and self.step_key is not None:
            raise ValueError("reuse decision must not declare step_key")
        return self


class RevisionConflict(BaseModel):
    model_config = MODEL_CONFIG

    code: Identifier
    artifact_version_id: Identifier | None = None
    detail: FeedbackText


class RevisionPlan(BaseModel):
    model_config = MODEL_CONFIG

    id: Identifier
    project_id: Identifier
    parent_run_id: Identifier
    parent_run_revision: int = Field(ge=1)
    contract_id: Identifier
    version: int = Field(ge=1)
    status: RevisionPlanStatus
    feedback_ids: tuple[Identifier, ...]
    baseline_artifact_version_ids: tuple[Identifier, ...]
    affected_artifact_version_ids: tuple[Identifier, ...]
    reusable_artifact_version_ids: tuple[Identifier, ...]
    recompute_steps: tuple[Identifier, ...]
    version_decisions: tuple[RevisionVersionDecision, ...]
    conflicts: tuple[RevisionConflict, ...]
    confirmed_run_id: Identifier | None = None
    plan_hash: ContentHash
    created_at: UtcDateTime


class ConfirmRevisionPlanRequest(BaseModel):
    model_config = MODEL_CONFIG

    expected_plan_version: int = Field(ge=1)


__all__ = [
    "ConfirmRevisionPlanRequest",
    "CreateRevisionPlanRequest",
    "CreateUserFeedbackRequest",
    "FeedbackCategory",
    "FeedbackTargetType",
    "RevisionConflict",
    "RevisionDecision",
    "RevisionPlan",
    "RevisionPlanStatus",
    "RevisionVersionDecision",
    "UserFeedback",
]
