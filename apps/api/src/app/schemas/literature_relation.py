"""D-08 LiteratureRelation and auditable ReasoningTrace contracts."""

from __future__ import annotations

from copy import deepcopy
from enum import StrEnum
from typing import Any, ClassVar, Literal, Self

from pydantic import AwareDatetime, BaseModel, Field, PrivateAttr, model_validator

from ._hashing import compute_canonical_payload_hash
from .enums import LiteratureRelationType
from .literature_claim import (
    LiteratureClaimCandidate,
    LiteratureClaimStatus,
    LiteratureClaimsCandidate,
)
from .manifest import ContentHash, Identifier, SemanticVersion
from .paper_summary import MODEL_CONFIG, NonEmptyString, PaperSummaryEvidence, ShortString


class LiteratureRelationStatus(StrEnum):
    candidate = "candidate"
    accepted = "accepted"
    rejected = "rejected"


class LiteratureRelationFailureStage(StrEnum):
    json = "json"
    schema = "schema"
    input = "input"
    claim = "claim"
    evidence = "evidence"
    ownership = "ownership"
    pairing = "pairing"
    direction = "direction"
    duplicate = "duplicate"
    conditions = "conditions"
    comparability = "comparability"
    trace = "trace"
    confidence = "confidence"


class LiteratureRelationRejectionReason(StrEnum):
    invalid_json = "literature_relation.json_invalid"
    schema_invalid = "literature_relation.schema_invalid"
    input_artifact_version_unknown = (
        "literature_relation.input_artifact_version_unknown"
    )
    input_schema_version_unsupported = (
        "literature_relation.input_schema_version_unsupported"
    )
    input_content_hash_mismatch = "literature_relation.input_content_hash_mismatch"
    claim_not_found = "literature_relation.claim_not_found"
    paper_summary_artifact_version_unknown = (
        "literature_relation.paper_summary_artifact_version_unknown"
    )
    claim_status_invalid = "literature_relation.claim_status_invalid"
    evidence_missing = "literature_relation.evidence_missing"
    evidence_not_found = "literature_relation.evidence_not_found"
    source_snapshot_not_found = "literature_relation.source_snapshot_not_found"
    evidence_inconsistent = "literature_relation.evidence_inconsistent"
    ownership_mismatch = "literature_relation.ownership_mismatch"
    self_pair = "literature_relation.self_pair"
    direction_mismatch = "literature_relation.direction_mismatch"
    duplicate_relation = "literature_relation.duplicate"
    conditions_missing = "literature_relation.conditions_missing"
    conditions_conflict = "literature_relation.conditions_conflict"
    object_incomparable = "literature_relation.object_incomparable"
    metric_incomparable = "literature_relation.metric_incomparable"
    unit_incomparable = "literature_relation.unit_incomparable"
    trace_missing = "literature_relation.trace_missing"
    trace_incomplete = "literature_relation.trace_incomplete"
    trace_unsafe = "literature_relation.trace_unsafe"
    trace_direction_mismatch = "literature_relation.trace_direction_mismatch"
    trace_evidence_incomplete = "literature_relation.trace_evidence_incomplete"
    confidence_undefined = "literature_relation.confidence_undefined"
    confidence_definition_unsupported = (
        "literature_relation.confidence_definition_unsupported"
    )
    confidence_subject_mismatch = "literature_relation.confidence_subject_mismatch"
    confidence_decision_mismatch = "literature_relation.confidence_decision_mismatch"
    confidence_calibration_missing = (
        "literature_relation.confidence_calibration_missing"
    )


class LiteratureRelationReviewReason(StrEnum):
    claim_not_accepted = "literature_relation.review.claim_not_accepted"
    conditions_unresolved = "literature_relation.review.conditions_unresolved"
    confidence_not_evaluable = (
        "literature_relation.review.confidence_not_evaluable"
    )
    confidence_below_threshold = (
        "literature_relation.review.confidence_below_threshold"
    )


class LiteratureComparabilityStatus(StrEnum):
    comparable = "comparable"
    not_applicable = "not_applicable"
    incomparable = "incomparable"


class LiteratureRelationConfidenceStatus(StrEnum):
    assessed = "assessed"
    not_evaluable = "not_evaluable"


class LiteratureTraceOperation(StrEnum):
    identify_premises = "identify_premises"
    compare_objects = "compare_objects"
    compare_metric = "compare_metric"
    compare_unit = "compare_unit"
    check_conditions = "check_conditions"
    check_evidence = "check_evidence"
    classify_relation = "classify_relation"
    record_limitation = "record_limitation"


class LiteratureRelationDirectionCandidate(BaseModel):
    model_config = MODEL_CONFIG
    __artifact_publication_requires_admission__: ClassVar[bool] = True

    source_claim_id: Identifier
    target_claim_id: Identifier
    basis: ShortString


class LiteratureRelationComparabilityCandidate(BaseModel):
    model_config = MODEL_CONFIG
    __artifact_publication_requires_admission__: ClassVar[bool] = True

    object_status: LiteratureComparabilityStatus
    object_basis: ShortString
    metric_status: LiteratureComparabilityStatus
    metric_basis: ShortString
    unit_status: LiteratureComparabilityStatus
    unit_basis: ShortString


class LiteratureReasoningTraceStepCandidate(BaseModel):
    """One public, verifiable operation; never a private reasoning token log."""

    model_config = MODEL_CONFIG
    __artifact_publication_requires_admission__: ClassVar[bool] = True

    order: int = Field(ge=1, le=32)
    operation: LiteratureTraceOperation
    statement: ShortString
    claim_ids: tuple[Identifier, ...]
    evidence_ids: tuple[Identifier, ...]

class LiteratureReasoningTraceModelCandidate(BaseModel):
    model_config = MODEL_CONFIG
    __artifact_publication_requires_admission__: ClassVar[bool] = True

    premise_claim_ids: tuple[Identifier, ...]
    steps: tuple[LiteratureReasoningTraceStepCandidate, ...]
    conditions: tuple[NonEmptyString, ...]
    limitations: tuple[NonEmptyString, ...]
    conflicts: tuple[NonEmptyString, ...]
    conclusion: ShortString | None = None

class LiteratureRelationModelCandidate(BaseModel):
    """Strict JSON model output before any provenance or domain admission."""

    model_config = MODEL_CONFIG
    __artifact_publication_requires_admission__: ClassVar[bool] = True

    source_claim_id: Identifier
    target_claim_id: Identifier
    relation_type: LiteratureRelationType
    direction: LiteratureRelationDirectionCandidate
    conditions: tuple[NonEmptyString, ...]
    condition_conflicts: tuple[NonEmptyString, ...]
    condition_uncertainties: tuple[NonEmptyString, ...]
    comparability: LiteratureRelationComparabilityCandidate
    evidence_ids: tuple[Identifier, ...]
    trace: LiteratureReasoningTraceModelCandidate | None = None
    confidence_assessment_id: Identifier | None = None

    @model_validator(mode="after")
    def validate_sets(self) -> Self:
        for values, label in (
            (self.conditions, "Relation condition"),
            (self.condition_conflicts, "Relation condition conflict"),
            (self.condition_uncertainties, "Relation condition uncertainty"),
            (self.evidence_ids, "Relation Evidence"),
        ):
            _require_unique(values, label)
        return self


class LiteratureRelationExtractionOutput(BaseModel):
    model_config = MODEL_CONFIG
    __artifact_publication_requires_admission__: ClassVar[bool] = True

    schema_version: Literal["1.0.0"]
    relations: tuple[LiteratureRelationModelCandidate, ...] = Field(min_length=1)


class LiteratureRelationConfidenceSubject(BaseModel):
    model_config = MODEL_CONFIG

    source_claim_artifact_version_id: Identifier
    source_claim_id: Identifier
    target_claim_artifact_version_id: Identifier
    target_claim_id: Identifier
    relation_type: LiteratureRelationType
    fingerprint: ContentHash

    @model_validator(mode="after")
    def validate_fingerprint(self) -> Self:
        expected = compute_literature_relation_confidence_subject_fingerprint(self)
        if self.fingerprint != expected:
            raise ValueError(f"confidence subject fingerprint mismatch: {expected}")
        return self


class LiteratureRelationConfidenceAssessment(BaseModel):
    """Trusted, versioned calibration input referenced by model output by id."""

    model_config = MODEL_CONFIG
    __artifact_publication_requires_admission__: ClassVar[bool] = True

    assessment_id: Identifier
    subject: LiteratureRelationConfidenceSubject
    decision: LiteratureRelationStatus
    status: LiteratureRelationConfidenceStatus
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    definition_id: Identifier
    definition_version: SemanticVersion
    calibration_id: Identifier
    calibration_version: SemanticVersion
    calibration_scientific_payload_hash: ContentHash
    calibration_content_hash: ContentHash
    calibration_sample_size: int = Field(ge=1)
    calibration_method: Identifier
    applicability_scope: Identifier
    score_interpretation: Literal[
        "confidence_in_relation_type_and_admission_decision"
    ] = "confidence_in_relation_type_and_admission_decision"
    acceptance_threshold: float = Field(ge=0.0, le=1.0)
    basis: tuple[ShortString, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_status(self) -> Self:
        if self.status is LiteratureRelationConfidenceStatus.assessed:
            if self.score is None:
                raise ValueError("assessed confidence requires a calibrated score")
        elif self.score is not None:
            raise ValueError("not_evaluable confidence cannot contain a score")
        return self


class LiteratureClaimArtifactVersionReference(BaseModel):
    model_config = MODEL_CONFIG

    artifact_version_id: Identifier
    schema_version: SemanticVersion | None = None
    content_hash: ContentHash | None = None
    output_hash: ContentHash | None = None
    project_id: Identifier | None = None
    claim_ids: tuple[Identifier, ...] = ()
    paper_summary_artifact_version_ids: tuple[Identifier, ...] = ()
    source_snapshot_ids: tuple[Identifier, ...] = ()

    @model_validator(mode="after")
    def validate_stable_sets(self) -> Self:
        for values, label in (
            (self.claim_ids, "Claim"),
            (self.paper_summary_artifact_version_ids, "PaperSummary version"),
            (self.source_snapshot_ids, "SourceSnapshot"),
        ):
            _require_sorted_unique(values, label)
        resolved = (
            self.schema_version,
            self.content_hash,
            self.output_hash,
            self.project_id,
        )
        if any(item is None for item in resolved) and any(
            item is not None for item in resolved
        ):
            raise ValueError("resolved LiteratureClaims version fields are all-or-none")
        if self.schema_version is None:
            if any(
                (
                    self.claim_ids,
                    self.paper_summary_artifact_version_ids,
                    self.source_snapshot_ids,
                )
            ):
                raise ValueError("unresolved LiteratureClaims version has no contents")
        elif not all(
            (
                self.claim_ids,
                self.paper_summary_artifact_version_ids,
                self.source_snapshot_ids,
            )
        ):
            raise ValueError("resolved LiteratureClaims version requires provenance")
        return self


class LiteratureRelationInputVersions(BaseModel):
    model_config = MODEL_CONFIG

    project_id: Identifier
    claim_artifact_versions: tuple[LiteratureClaimArtifactVersionReference, ...] = (
        Field(min_length=1)
    )

    @model_validator(mode="after")
    def validate_versions(self) -> Self:
        ids = tuple(item.artifact_version_id for item in self.claim_artifact_versions)
        _require_sorted_unique(ids, "LiteratureClaims ArtifactVersion")
        return self


class LiteratureRelationEvidenceReference(BaseModel):
    model_config = MODEL_CONFIG

    relation_id: Identifier
    side: Literal["source", "target"]
    claim_id: Identifier
    claim_artifact_version_id: Identifier
    paper_summary_artifact_version_id: Identifier
    evidence_id: Identifier
    paper_id: Identifier
    source_snapshot_id: Identifier
    source_snapshot_version: ShortString
    source_snapshot_content_hash: ContentHash
    status: Literal["supported", "unsupported", "unverifiable"]
    validation_code: Identifier


class LiteratureReasoningTraceCandidate(BaseModel):
    model_config = MODEL_CONFIG
    __artifact_publication_requires_admission__: ClassVar[bool] = True

    trace_id: Identifier
    relation_id: Identifier
    premise_claim_ids: tuple[Identifier, Identifier]
    steps: tuple[LiteratureReasoningTraceStepCandidate, ...] = Field(min_length=1)
    conditions: tuple[NonEmptyString, ...] = Field(min_length=1)
    limitations: tuple[NonEmptyString, ...]
    conflicts: tuple[NonEmptyString, ...]
    conclusion: ShortString
    evidence_ids: tuple[Identifier, ...] = Field(min_length=1)
    trace_protocol_version: SemanticVersion
    relation_status: LiteratureRelationStatus
    scientific_review_status: Literal["pending_scientific_review"] = (
        "pending_scientific_review"
    )
    producer_execution_id: Identifier
    input_hash: ContentHash
    model_response_hash: ContentHash

    @model_validator(mode="after")
    def validate_trace(self) -> Self:
        if self.premise_claim_ids[0] == self.premise_claim_ids[1]:
            raise ValueError("ReasoningTrace premises must differ")
        orders = tuple(item.order for item in self.steps)
        if orders != tuple(range(1, len(self.steps) + 1)):
            raise ValueError("ReasoningTrace step order must be contiguous from 1")
        _require_sorted_unique(self.evidence_ids, "ReasoningTrace Evidence")
        for item in self.steps:
            _require_unique(item.claim_ids, "ReasoningTrace step Claim")
            _require_unique(item.evidence_ids, "ReasoningTrace step Evidence")
        return self


class LiteratureRelationCandidate(BaseModel):
    model_config = MODEL_CONFIG
    __artifact_publication_requires_admission__: ClassVar[bool] = True

    relation_id: Identifier
    pair_id: Identifier
    source_claim_id: Identifier
    target_claim_id: Identifier
    source_claim_artifact_version_id: Identifier | None = None
    target_claim_artifact_version_id: Identifier | None = None
    source_paper_summary_artifact_version_id: Identifier | None = None
    target_paper_summary_artifact_version_id: Identifier | None = None
    relation_type: LiteratureRelationType
    direction: LiteratureRelationDirectionCandidate
    conditions: tuple[NonEmptyString, ...]
    condition_conflicts: tuple[NonEmptyString, ...]
    condition_uncertainties: tuple[NonEmptyString, ...]
    comparability: LiteratureRelationComparabilityCandidate
    evidence_ids: tuple[Identifier, ...]
    source_snapshot_ids: tuple[Identifier, ...]
    reasoning_trace_id: Identifier | None = None
    confidence: LiteratureRelationConfidenceAssessment | None = None
    fingerprint: ContentHash
    status: LiteratureRelationStatus
    failure_stage: LiteratureRelationFailureStage | None = None
    rejection_reason: LiteratureRelationRejectionReason | None = None
    review_reason: LiteratureRelationReviewReason | None = None
    scientific_review_status: Literal["pending_scientific_review"] = (
        "pending_scientific_review"
    )
    producer_execution_id: Identifier
    input_hash: ContentHash
    model_response_hash: ContentHash

    @model_validator(mode="after")
    def validate_admission_state(self) -> Self:
        _require_unique(self.evidence_ids, "LiteratureRelation Evidence")
        _require_unique(self.source_snapshot_ids, "LiteratureRelation SourceSnapshot")
        if self.status is LiteratureRelationStatus.rejected:
            if self.failure_stage is None or self.rejection_reason is None:
                raise ValueError("rejected Relation requires stage and reason")
            if self.review_reason is not None:
                raise ValueError("rejected Relation cannot contain review_reason")
        else:
            if self.failure_stage is not None or self.rejection_reason is not None:
                raise ValueError("non-rejected Relation cannot contain rejection metadata")
            required = (
                self.source_claim_artifact_version_id,
                self.target_claim_artifact_version_id,
                self.source_paper_summary_artifact_version_id,
                self.target_paper_summary_artifact_version_id,
                self.reasoning_trace_id,
                self.confidence,
            )
            if any(item is None for item in required):
                raise ValueError("publishable Relation requires complete provenance")
            if not self.evidence_ids or not self.source_snapshot_ids:
                raise ValueError("publishable Relation requires Evidence and SourceSnapshots")
        if self.status is LiteratureRelationStatus.accepted:
            if self.review_reason is not None:
                raise ValueError("accepted Relation cannot contain review_reason")
            if (
                self.confidence is None
                or self.confidence.status
                is not LiteratureRelationConfidenceStatus.assessed
                or self.confidence.score is None
                or self.confidence.score < self.confidence.acceptance_threshold
            ):
                raise ValueError("accepted Relation requires threshold-passing confidence")
        if (
            self.status is LiteratureRelationStatus.candidate
            and self.review_reason is None
        ):
            raise ValueError("candidate Relation requires review_reason")
        expected = compute_literature_relation_fingerprint(self)
        if self.fingerprint != expected:
            raise ValueError(f"fingerprint does not match LiteratureRelation: {expected}")
        if self.confidence is not None:
            if (
                self.source_claim_artifact_version_id is None
                or self.target_claim_artifact_version_id is None
            ):
                raise ValueError("confidence requires resolved Relation endpoints")
            expected_subject = build_literature_relation_confidence_subject(
                source_claim_artifact_version_id=(
                    self.source_claim_artifact_version_id
                ),
                source_claim_id=self.source_claim_id,
                target_claim_artifact_version_id=(
                    self.target_claim_artifact_version_id
                ),
                target_claim_id=self.target_claim_id,
                relation_type=self.relation_type,
            )
            if (
                self.confidence.subject != expected_subject
                or self.confidence.decision is not self.status
            ):
                raise ValueError("confidence subject/decision does not match Relation")
        return self


class LiteratureRelationProducerExecution(BaseModel):
    model_config = MODEL_CONFIG

    execution_id: Identifier
    run_id: Identifier | None = None
    step_key: Literal["reasoning_literature"] = "reasoning_literature"
    producer_type: Literal["model"] = "model"
    producer_name: NonEmptyString
    producer_version: SemanticVersion
    model_name: ShortString
    prompt_name: Identifier
    prompt_version: ShortString
    prompt_hash: ContentHash
    schema_version: Literal["1.0.0"]
    parameters_version: SemanticVersion
    parameters_hash: ContentHash
    pairing_version: SemanticVersion
    comparison_policy_version: SemanticVersion
    trace_protocol_version: SemanticVersion
    confidence_definition_id: Identifier
    confidence_definition_version: SemanticVersion
    confidence_calibration_id: Identifier
    confidence_calibration_version: SemanticVersion
    confidence_calibration_scientific_payload_hash: ContentHash
    confidence_calibration_content_hash: ContentHash
    confidence_calibration_sample_size: int = Field(ge=1)
    confidence_calibration_method: Identifier
    confidence_applicability_scope: Identifier
    confidence_acceptance_threshold: float = Field(ge=0.0, le=1.0)
    input_versions: LiteratureRelationInputVersions
    input_hash: ContentHash
    model_response_hash: ContentHash
    output_hash: ContentHash
    status: Literal["completed", "rejected"]
    started_at: AwareDatetime
    finished_at: AwareDatetime
    latency_ms: int = Field(ge=0)
    error_code: LiteratureRelationRejectionReason | None = None

    @model_validator(mode="after")
    def validate_terminal_state(self) -> Self:
        if self.status == "completed" and self.error_code is not None:
            raise ValueError("completed Relation execution cannot declare error_code")
        if self.status == "rejected" and self.error_code not in {
            LiteratureRelationRejectionReason.invalid_json,
            LiteratureRelationRejectionReason.schema_invalid,
        }:
            raise ValueError("rejected execution requires JSON/Schema error_code")
        return self


class LiteratureRelationStatusCounts(BaseModel):
    model_config = MODEL_CONFIG

    accepted: int = Field(ge=0)
    candidate: int = Field(ge=0)
    rejected: int = Field(ge=0)


class LiteratureRelationsCandidate(BaseModel):
    """The only D-08 typed candidate accepted by the generic Publisher port."""

    model_config = MODEL_CONFIG
    __artifact_publication_requires_admission__: ClassVar[bool] = True
    _artifact_publication_seal: Any = PrivateAttr(default=None)
    _artifact_publication_context: Any = PrivateAttr(default=None)

    kind: Literal["literature_relations"] = "literature_relations"
    schema_version: Literal["1.0.0"] = "1.0.0"
    input_versions: LiteratureRelationInputVersions
    claims: tuple[LiteratureClaimCandidate, ...] = Field(min_length=2)
    relations: tuple[LiteratureRelationCandidate, ...] = Field(min_length=1)
    reasoning_traces: tuple[LiteratureReasoningTraceCandidate, ...] = Field(
        min_length=1
    )
    evidence: tuple[PaperSummaryEvidence, ...] = Field(min_length=1)
    evidence_references: tuple[LiteratureRelationEvidenceReference, ...] = Field(
        min_length=1
    )
    evidence_ids: tuple[Identifier, ...] = Field(min_length=1)
    source_snapshot_ids: tuple[Identifier, ...] = Field(min_length=1)
    status_counts: LiteratureRelationStatusCounts
    producer: LiteratureRelationProducerExecution
    input_hash: ContentHash
    output_hash: ContentHash

    @model_validator(mode="after")
    def validate_candidate(self) -> Self:
        for values, attribute, label in (
            (self.claims, "claim_id", "Claim"),
            (self.relations, "relation_id", "Relation"),
            (self.reasoning_traces, "trace_id", "ReasoningTrace"),
            (self.evidence, "evidence_id", "Evidence"),
        ):
            _require_unique(
                tuple(getattr(item, attribute) for item in values),
                label,
            )
        _require_sorted_unique(self.evidence_ids, "candidate Evidence")
        _require_sorted_unique(
            self.source_snapshot_ids, "candidate SourceSnapshot"
        )
        if not any(
            item.status is not LiteratureRelationStatus.rejected
            for item in self.relations
        ):
            raise ValueError("publisher candidate requires a publishable Relation")
        claims = {item.claim_id: item for item in self.claims}
        traces = {item.trace_id: item for item in self.reasoning_traces}
        evidence = {item.evidence_id: item for item in self.evidence}
        relations = {item.relation_id: item for item in self.relations}
        _require_unique(
            tuple(
                (item.relation_id, item.side, item.claim_id, item.evidence_id)
                for item in self.evidence_references
            ),
            "Relation Evidence reference",
        )
        references_by_relation: dict[str, list[LiteratureRelationEvidenceReference]] = {}
        for reference in self.evidence_references:
            relation = relations.get(reference.relation_id)
            if relation is None:
                raise ValueError("Evidence reference identifies unknown Relation")
            if reference.claim_id not in claims or reference.evidence_id not in evidence:
                raise ValueError("Evidence reference identifies unknown Claim/Evidence")
            expected_claim_id = (
                relation.source_claim_id
                if reference.side == "source"
                else relation.target_claim_id
            )
            expected_claim_version_id = (
                relation.source_claim_artifact_version_id
                if reference.side == "source"
                else relation.target_claim_artifact_version_id
            )
            expected_summary_version_id = (
                relation.source_paper_summary_artifact_version_id
                if reference.side == "source"
                else relation.target_paper_summary_artifact_version_id
            )
            if (
                reference.claim_id != expected_claim_id
                or reference.claim_artifact_version_id
                != expected_claim_version_id
                or reference.paper_summary_artifact_version_id
                != expected_summary_version_id
                or reference.evidence_id not in claims[reference.claim_id].evidence_ids
            ):
                raise ValueError("Relation Evidence reference endpoint mismatch")
            item = evidence[reference.evidence_id]
            if (
                reference.paper_id != item.paper_id
                or reference.source_snapshot_id != item.source_snapshot_id
                or reference.source_snapshot_version != item.source_snapshot_version
                or reference.source_snapshot_content_hash
                != item.source_snapshot_content_hash
                or reference.status != item.status
                or reference.validation_code != item.validation_code
            ):
                raise ValueError("Relation Evidence reference provenance mismatch")
            references_by_relation.setdefault(reference.relation_id, []).append(reference)

        def validate_relation_evidence_closure(
            relation: LiteratureRelationCandidate,
            *,
            scope: str,
        ) -> None:
            if (
                relation.source_claim_id not in claims
                or relation.target_claim_id not in claims
            ):
                raise ValueError(f"{scope} Relation endpoints require retained Claims")
            references = references_by_relation.get(relation.relation_id, [])
            if tuple(sorted({item.evidence_id for item in references})) != (
                relation.evidence_ids
            ):
                raise ValueError(f"{scope} Relation Evidence closure mismatch")
            if tuple(sorted({item.source_snapshot_id for item in references})) != (
                relation.source_snapshot_ids
            ):
                raise ValueError(f"{scope} Relation SourceSnapshot closure mismatch")
            for side, claim_id in (
                ("source", relation.source_claim_id),
                ("target", relation.target_claim_id),
            ):
                if tuple(
                    sorted(
                        item.evidence_id
                        for item in references
                        if item.side == side
                    )
                ) != claims[claim_id].evidence_ids:
                    raise ValueError(
                        f"{scope} Relation endpoint Evidence closure mismatch"
                    )

        for relation in self.relations:
            if relation.reasoning_trace_id is not None:
                trace = traces.get(relation.reasoning_trace_id)
                if trace is None or trace.relation_id != relation.relation_id:
                    raise ValueError("Relation/ReasoningTrace binding mismatch")
                if trace.premise_claim_ids != (
                    relation.source_claim_id,
                    relation.target_claim_id,
                ):
                    raise ValueError("ReasoningTrace direction must match Relation")
                if (
                    trace.relation_status is not relation.status
                    or trace.evidence_ids != relation.evidence_ids
                ):
                    raise ValueError("ReasoningTrace outcome/Evidence mismatch")
                validate_relation_evidence_closure(
                    relation,
                    scope="ReasoningTrace",
                )
            if relation.status is LiteratureRelationStatus.rejected:
                continue
            validate_relation_evidence_closure(relation, scope="publishable")
        if any(item.relation_id not in relations for item in self.reasoning_traces):
            raise ValueError("ReasoningTrace identifies unknown Relation")
        expected_evidence_ids = tuple(
            sorted({item.evidence_id for item in self.evidence_references})
        )
        if self.evidence_ids != expected_evidence_ids:
            raise ValueError("evidence_ids must equal Evidence references")
        expected_snapshot_ids = tuple(
            sorted({item.source_snapshot_id for item in self.evidence_references})
        )
        if self.source_snapshot_ids != expected_snapshot_ids:
            raise ValueError("source_snapshot_ids must equal Evidence references")
        expected_counts = _status_counts(self.relations)
        if self.status_counts != expected_counts:
            raise ValueError("status_counts do not match Relations")
        if self.input_hash != self.producer.input_hash:
            raise ValueError("ProducerExecution input_hash mismatch")
        if self.input_versions != self.producer.input_versions:
            raise ValueError("ProducerExecution input versions mismatch")
        for relation in self.relations:
            if (
                relation.producer_execution_id != self.producer.execution_id
                or relation.input_hash != self.input_hash
                or relation.model_response_hash != self.producer.model_response_hash
            ):
                raise ValueError("Relation producer provenance mismatch")
        for trace in self.reasoning_traces:
            if (
                trace.producer_execution_id != self.producer.execution_id
                or trace.input_hash != self.input_hash
                or trace.model_response_hash != self.producer.model_response_hash
            ):
                raise ValueError("Trace producer provenance mismatch")
        expected_hash = compute_literature_relations_output_hash(self)
        if self.output_hash != expected_hash:
            raise ValueError(f"output_hash does not match Relations: {expected_hash}")
        if self.producer.output_hash != expected_hash:
            raise ValueError("ProducerExecution output_hash mismatch")
        return self

    def __artifact_publication_is_admitted__(self) -> bool:
        from ._literature_relation_seal import (
            literature_relations_candidate_is_sealed,
        )

        return literature_relations_candidate_is_sealed(
            self,
            self._artifact_publication_seal,
            self._artifact_publication_context,
            public_payload_hash=compute_literature_relations_public_payload_hash(self),
        )


class LiteratureRelationAdmissionResult(BaseModel):
    model_config = MODEL_CONFIG
    __artifact_publication_requires_admission__: ClassVar[bool] = True

    admission_status: LiteratureRelationStatus
    failure_stage: LiteratureRelationFailureStage | None = None
    rejection_reason: LiteratureRelationRejectionReason | None = None
    records: tuple[LiteratureRelationCandidate, ...]
    reasoning_traces: tuple[LiteratureReasoningTraceCandidate, ...]
    publisher_candidate: LiteratureRelationsCandidate | None = None
    producer: LiteratureRelationProducerExecution
    output_hash: ContentHash

    @model_validator(mode="after")
    def validate_result(self) -> Self:
        if self.admission_status is LiteratureRelationStatus.rejected and not self.records:
            if self.failure_stage not in {
                LiteratureRelationFailureStage.json,
                LiteratureRelationFailureStage.schema,
            } or self.rejection_reason is None:
                raise ValueError("empty rejection requires JSON/Schema metadata")
        elif self.failure_stage is not None or self.rejection_reason is not None:
            raise ValueError("record-level result cannot declare top-level failure")
        if self.records and self.admission_status is not _aggregate_status(self.records):
            raise ValueError("admission_status does not match Relation records")
        publishable = any(
            item.status is not LiteratureRelationStatus.rejected for item in self.records
        )
        if publishable != (self.publisher_candidate is not None):
            raise ValueError("publisher candidate presence does not match records")
        if self.publisher_candidate is not None:
            if (
                self.publisher_candidate.relations != self.records
                or self.publisher_candidate.reasoning_traces != self.reasoning_traces
                or self.publisher_candidate.producer != self.producer
                or self.publisher_candidate.output_hash != self.output_hash
            ):
                raise ValueError("publisher candidate does not match admission result")
        else:
            expected = compute_literature_relation_admission_output_hash(self)
            if self.output_hash != expected:
                raise ValueError(f"output_hash does not match admission: {expected}")
        if self.producer.output_hash != self.output_hash:
            raise ValueError("ProducerExecution output_hash mismatch")
        return self


class LiteratureRelationBenchmarkCaseKind(StrEnum):
    scientific_label = "scientific_label"
    rejection_case = "rejection_case"


class LiteratureRelationBenchmarkEvaluationCase(BaseModel):
    model_config = MODEL_CONFIG

    case_id: Identifier
    case_kind: LiteratureRelationBenchmarkCaseKind
    benchmark_relation_id: Identifier | None = None
    benchmark_trace_id: Identifier | None = None
    record_relation_id: Identifier | None = None
    expected_failure_stage: LiteratureRelationFailureStage | None = None
    expected_rejection_reason: LiteratureRelationRejectionReason | None = None
    admission: LiteratureRelationAdmissionResult

    @model_validator(mode="after")
    def validate_expectation(self) -> Self:
        if self.case_kind is LiteratureRelationBenchmarkCaseKind.scientific_label:
            if self.benchmark_relation_id is None or self.benchmark_trace_id is None:
                raise ValueError("scientific case requires D-01 Relation and Trace ids")
            if (
                self.expected_failure_stage is not None
                or self.expected_rejection_reason is not None
            ):
                raise ValueError("scientific case cannot declare rejection expectation")
        elif (
            self.benchmark_relation_id is not None
            or self.benchmark_trace_id is not None
            or self.expected_failure_stage is None
            or self.expected_rejection_reason is None
        ):
            raise ValueError("rejection case requires only stage/reason expectation")
        return self


class LiteratureRelationBenchmarkCaseResult(BaseModel):
    model_config = MODEL_CONFIG

    case_id: Identifier
    case_kind: LiteratureRelationBenchmarkCaseKind
    benchmark_relation_id: Identifier | None = None
    benchmark_trace_id: Identifier | None = None
    record_relation_id: Identifier | None = None
    relation_type: LiteratureRelationType | None = None
    expected_failure_stage: LiteratureRelationFailureStage | None = None
    expected_rejection_reason: LiteratureRelationRejectionReason | None = None
    schema_valid: bool
    candidate_pair_matched: bool | None = None
    scientific_label_compared: bool
    scientific_label_exact_match: bool | None = None
    relation_evidence_items_supported: int = Field(ge=0)
    relation_evidence_items_total: int = Field(ge=0)
    trace_step_evidence_items_supported: int = Field(ge=0)
    trace_step_evidence_items_total: int = Field(ge=0)
    evidence_less_case: bool
    evidence_less_blocked: bool | None = None
    rejection_case_pass: bool | None = None
    confidence_status: LiteratureRelationConfidenceStatus | None = None
    confidence_score: float | None = Field(default=None, ge=0.0, le=1.0)
    confidence_calibrated: bool | None = None
    status: LiteratureRelationStatus
    failure_stage: LiteratureRelationFailureStage | None = None
    rejection_reason: LiteratureRelationRejectionReason | None = None
    input_hash: ContentHash
    output_hash: ContentHash

    @model_validator(mode="after")
    def validate_result(self) -> Self:
        if self.relation_evidence_items_supported > self.relation_evidence_items_total:
            raise ValueError("Relation Evidence numerator exceeds denominator")
        if self.trace_step_evidence_items_supported > self.trace_step_evidence_items_total:
            raise ValueError("Trace Evidence numerator exceeds denominator")
        if self.status is LiteratureRelationStatus.rejected:
            if self.failure_stage is None or self.rejection_reason is None:
                raise ValueError("rejected case result requires stage/reason")
        elif self.failure_stage is not None or self.rejection_reason is not None:
            raise ValueError("non-rejected case result cannot declare rejection")
        if self.case_kind is LiteratureRelationBenchmarkCaseKind.scientific_label:
            if (
                self.benchmark_relation_id is None
                or self.benchmark_trace_id is None
                or self.relation_type is None
                or self.candidate_pair_matched is None
                or self.rejection_case_pass is not None
            ):
                raise ValueError("scientific result fields are incomplete")
            if self.scientific_label_compared != (
                self.scientific_label_exact_match is not None
            ):
                raise ValueError("scientific comparison applicability mismatch")
        else:
            if (
                self.benchmark_relation_id is not None
                or self.benchmark_trace_id is not None
                or self.relation_type is not None
                or self.candidate_pair_matched is not None
                or self.expected_failure_stage is None
                or self.expected_rejection_reason is None
                or self.rejection_case_pass is None
                or self.scientific_label_compared
                or self.scientific_label_exact_match is not None
            ):
                raise ValueError("rejection result fields are inconsistent")
        if self.evidence_less_case != (self.evidence_less_blocked is not None):
            raise ValueError("evidence-less applicability mismatch")
        if self.confidence_status is LiteratureRelationConfidenceStatus.assessed:
            if self.confidence_score is None or self.confidence_calibrated is None:
                raise ValueError("assessed confidence result is incomplete")
        elif self.confidence_status is LiteratureRelationConfidenceStatus.not_evaluable:
            if self.confidence_score is not None or self.confidence_calibrated is None:
                raise ValueError("not-evaluable confidence result is inconsistent")
        elif self.confidence_score is not None or self.confidence_calibrated is not None:
            raise ValueError("confidence values require confidence_status")
        return self


class LiteratureRelationConfidenceBin(BaseModel):
    model_config = MODEL_CONFIG

    label: Literal["[0.0,0.5)", "[0.5,0.9)", "[0.9,1.0]"]
    lower_bound: float = Field(ge=0.0, le=1.0)
    upper_bound: float = Field(ge=0.0, le=1.0)
    upper_inclusive: bool
    count: int = Field(ge=0)


class LiteratureRelationRejectionCount(BaseModel):
    model_config = MODEL_CONFIG

    rejection_reason: LiteratureRelationRejectionReason
    count: int = Field(ge=1)
    sample_case_ids: tuple[Identifier, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_samples(self) -> Self:
        _require_sorted_unique(self.sample_case_ids, "rejection sample case")
        return self


class LiteratureRelationTypeCount(BaseModel):
    model_config = MODEL_CONFIG

    relation_type: LiteratureRelationType
    count: int = Field(ge=1)


class LiteratureRelationBenchmarkReport(BaseModel):
    model_config = MODEL_CONFIG

    report_version: Literal["1.0.0"] = "1.0.0"
    benchmark_id: Identifier
    benchmark_schema_version: SemanticVersion
    benchmark_version: SemanticVersion
    benchmark_scientific_payload_hash: ContentHash
    benchmark_content_hash: ContentHash
    prompt_name: Identifier
    prompt_version: ShortString
    prompt_hash: ContentHash
    relation_schema_version: Literal["1.0.0"]
    model_name: ShortString
    parameters_version: SemanticVersion
    parameters_hash: ContentHash
    producer_version: SemanticVersion
    sample_count: int = Field(ge=0)
    schema_items_valid: int = Field(ge=0)
    schema_items_total: int = Field(ge=0)
    schema_pass_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    scientific_pair_items_matched: int = Field(ge=0)
    scientific_pair_items_total: int = Field(ge=0)
    scientific_pair_coverage_rate: float | None = Field(
        default=None, ge=0.0, le=1.0
    )
    scientific_relation_items_exact: int = Field(ge=0)
    scientific_relation_items_total: int = Field(ge=0)
    scientific_relation_exact_match_rate: float | None = Field(
        default=None, ge=0.0, le=1.0
    )
    relation_evidence_items_supported: int = Field(ge=0)
    relation_evidence_items_total: int = Field(ge=0)
    relation_evidence_coverage_rate: float | None = Field(
        default=None, ge=0.0, le=1.0
    )
    trace_step_evidence_items_supported: int = Field(ge=0)
    trace_step_evidence_items_total: int = Field(ge=0)
    trace_step_evidence_coverage_rate: float | None = Field(
        default=None, ge=0.0, le=1.0
    )
    evidence_less_cases_blocked: int = Field(ge=0)
    evidence_less_cases_total: int = Field(ge=0)
    evidence_less_block_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    rejection_cases_passed: int = Field(ge=0)
    rejection_cases_total: int = Field(ge=0)
    rejection_case_pass_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    confidence_items_total: int = Field(ge=0)
    confidence_assessed_count: int = Field(ge=0)
    confidence_not_evaluable_count: int = Field(ge=0)
    confidence_calibrated_count: int = Field(ge=0)
    confidence_distribution: tuple[LiteratureRelationConfidenceBin, ...]
    scientific_status_counts: LiteratureRelationStatusCounts
    status_counts: LiteratureRelationStatusCounts
    relation_type_counts: tuple[LiteratureRelationTypeCount, ...]
    rejection_counts: tuple[LiteratureRelationRejectionCount, ...]
    cases: tuple[LiteratureRelationBenchmarkCaseResult, ...]
    input_hash: ContentHash
    output_hash: ContentHash

    @model_validator(mode="after")
    def validate_report(self) -> Self:
        if self.sample_count != len(self.cases):
            raise ValueError("sample_count must equal case count")
        if tuple(item.case_id for item in self.cases) != tuple(
            sorted(item.case_id for item in self.cases)
        ):
            raise ValueError("benchmark cases must use stable case_id order")
        for numerator, denominator, rate, label in (
            (
                self.schema_items_valid,
                self.schema_items_total,
                self.schema_pass_rate,
                "schema",
            ),
            (
                self.scientific_pair_items_matched,
                self.scientific_pair_items_total,
                self.scientific_pair_coverage_rate,
                "scientific candidate-pair",
            ),
            (
                self.scientific_relation_items_exact,
                self.scientific_relation_items_total,
                self.scientific_relation_exact_match_rate,
                "scientific Relation",
            ),
            (
                self.relation_evidence_items_supported,
                self.relation_evidence_items_total,
                self.relation_evidence_coverage_rate,
                "Relation Evidence",
            ),
            (
                self.trace_step_evidence_items_supported,
                self.trace_step_evidence_items_total,
                self.trace_step_evidence_coverage_rate,
                "Trace Evidence",
            ),
            (
                self.evidence_less_cases_blocked,
                self.evidence_less_cases_total,
                self.evidence_less_block_rate,
                "evidence-less block",
            ),
            (
                self.rejection_cases_passed,
                self.rejection_cases_total,
                self.rejection_case_pass_rate,
                "rejection",
            ),
        ):
            if numerator > denominator:
                raise ValueError(f"{label} numerator exceeds denominator")
            expected = numerator / denominator if denominator else None
            if rate != expected:
                raise ValueError(f"{label} rate does not match counts")
        if (
            self.confidence_assessed_count + self.confidence_not_evaluable_count
            != self.confidence_items_total
            or self.confidence_calibrated_count > self.confidence_assessed_count
            or sum(item.count for item in self.confidence_distribution)
            != self.confidence_assessed_count
        ):
            raise ValueError("confidence distribution does not match counts")
        scientific_cases = tuple(
            item
            for item in self.cases
            if item.case_kind is LiteratureRelationBenchmarkCaseKind.scientific_label
        )
        rejection_cases = tuple(
            item
            for item in self.cases
            if item.case_kind is LiteratureRelationBenchmarkCaseKind.rejection_case
        )
        if (
            self.schema_items_valid != sum(item.schema_valid for item in self.cases)
            or self.schema_items_total != len(self.cases)
            or self.scientific_pair_items_matched
            != sum(item.candidate_pair_matched is True for item in scientific_cases)
            or self.scientific_pair_items_total != len(scientific_cases)
            or self.scientific_relation_items_exact
            != sum(item.scientific_label_exact_match is True for item in scientific_cases)
            or self.scientific_relation_items_total
            != sum(item.scientific_label_compared for item in scientific_cases)
            or self.relation_evidence_items_supported
            != sum(item.relation_evidence_items_supported for item in scientific_cases)
            or self.relation_evidence_items_total
            != sum(item.relation_evidence_items_total for item in scientific_cases)
            or self.trace_step_evidence_items_supported
            != sum(item.trace_step_evidence_items_supported for item in scientific_cases)
            or self.trace_step_evidence_items_total
            != sum(item.trace_step_evidence_items_total for item in scientific_cases)
            or self.evidence_less_cases_blocked
            != sum(item.evidence_less_blocked is True for item in self.cases)
            or self.evidence_less_cases_total
            != sum(item.evidence_less_case for item in self.cases)
            or self.rejection_cases_passed
            != sum(item.rejection_case_pass is True for item in rejection_cases)
            or self.rejection_cases_total != len(rejection_cases)
        ):
            raise ValueError("benchmark aggregate counts do not match cases")
        scientific_confidence = tuple(
            item for item in scientific_cases if item.confidence_status is not None
        )
        if (
            self.confidence_items_total != len(scientific_confidence)
            or self.confidence_assessed_count
            != sum(
                item.confidence_status is LiteratureRelationConfidenceStatus.assessed
                for item in scientific_confidence
            )
            or self.confidence_not_evaluable_count
            != sum(
                item.confidence_status
                is LiteratureRelationConfidenceStatus.not_evaluable
                for item in scientific_confidence
            )
            or self.confidence_calibrated_count
            != sum(item.confidence_calibrated is True for item in scientific_confidence)
        ):
            raise ValueError("confidence counts must cover scientific cases only")
        expected_distribution = _confidence_distribution(scientific_confidence)
        if self.confidence_distribution != expected_distribution:
            raise ValueError("confidence distribution does not match scientific cases")
        if self.status_counts != LiteratureRelationStatusCounts(
            accepted=sum(
                item.status is LiteratureRelationStatus.accepted for item in self.cases
            ),
            candidate=sum(
                item.status is LiteratureRelationStatus.candidate for item in self.cases
            ),
            rejected=sum(
                item.status is LiteratureRelationStatus.rejected for item in self.cases
            ),
        ):
            raise ValueError("status_counts do not match cases")
        if self.scientific_status_counts != LiteratureRelationStatusCounts(
            accepted=sum(
                item.status is LiteratureRelationStatus.accepted
                for item in scientific_cases
            ),
            candidate=sum(
                item.status is LiteratureRelationStatus.candidate
                for item in scientific_cases
            ),
            rejected=sum(
                item.status is LiteratureRelationStatus.rejected
                for item in scientific_cases
            ),
        ):
            raise ValueError("scientific_status_counts do not match scientific cases")
        expected_types = tuple(
            LiteratureRelationTypeCount(relation_type=relation_type, count=count)
            for relation_type, count in sorted(
                {
                    item.relation_type: sum(
                        other.relation_type is item.relation_type
                        for other in scientific_cases
                    )
                    for item in scientific_cases
                    if item.relation_type is not None
                }.items(),
                key=lambda pair: pair[0].value,
            )
        )
        if self.relation_type_counts != expected_types:
            raise ValueError("relation_type_counts do not match scientific cases")
        expected_rejections = tuple(
            LiteratureRelationRejectionCount(
                rejection_reason=reason,
                count=len(items),
                sample_case_ids=tuple(sorted(item.case_id for item in items)),
            )
            for reason, items in sorted(
                {
                    item.rejection_reason: tuple(
                        other
                        for other in rejection_cases
                        if other.rejection_reason is item.rejection_reason
                    )
                    for item in rejection_cases
                    if item.rejection_reason is not None
                }.items(),
                key=lambda pair: pair[0].value,
            )
        )
        if self.rejection_counts != expected_rejections:
            raise ValueError("rejection_counts do not match rejection cases")
        expected_hash = compute_literature_relation_benchmark_output_hash(self)
        if self.output_hash != expected_hash:
            raise ValueError(f"output_hash does not match benchmark: {expected_hash}")
        return self


def compute_literature_relation_fingerprint(
    value: LiteratureRelationCandidate | dict[str, Any],
) -> str:
    payload = _model_or_dict(value)
    return compute_canonical_payload_hash(
        {
            "source_claim_artifact_version_id": payload.get(
                "source_claim_artifact_version_id"
            ),
            "source_claim_id": payload.get("source_claim_id"),
            "relation_type": payload.get("relation_type"),
            "target_claim_artifact_version_id": payload.get(
                "target_claim_artifact_version_id"
            ),
            "target_claim_id": payload.get("target_claim_id"),
        }
    )


def compute_literature_relation_confidence_subject_fingerprint(
    value: LiteratureRelationConfidenceSubject | dict[str, Any],
) -> str:
    payload = _model_or_dict(value)
    return compute_canonical_payload_hash(
        {
            "source_claim_artifact_version_id": payload.get(
                "source_claim_artifact_version_id"
            ),
            "source_claim_id": payload.get("source_claim_id"),
            "target_claim_artifact_version_id": payload.get(
                "target_claim_artifact_version_id"
            ),
            "target_claim_id": payload.get("target_claim_id"),
            "relation_type": payload.get("relation_type"),
        }
    )


def build_literature_relation_confidence_subject(
    *,
    source_claim_artifact_version_id: str,
    source_claim_id: str,
    target_claim_artifact_version_id: str,
    target_claim_id: str,
    relation_type: LiteratureRelationType | str,
) -> LiteratureRelationConfidenceSubject:
    payload = {
        "source_claim_artifact_version_id": source_claim_artifact_version_id,
        "source_claim_id": source_claim_id,
        "target_claim_artifact_version_id": target_claim_artifact_version_id,
        "target_claim_id": target_claim_id,
        "relation_type": relation_type,
    }
    return LiteratureRelationConfidenceSubject(
        **payload,
        fingerprint=compute_literature_relation_confidence_subject_fingerprint(payload),
    )


def compute_literature_relations_output_hash(
    value: LiteratureRelationsCandidate | dict[str, Any],
) -> str:
    payload = _model_or_dict(value)
    payload.pop("output_hash", None)
    _drop_execution_runtime(payload.get("producer"))
    _drop_relation_execution_runtime(payload)
    return compute_canonical_payload_hash(payload)


def compute_literature_relation_admission_output_hash(
    value: LiteratureRelationAdmissionResult | dict[str, Any],
) -> str:
    payload = _model_or_dict(value)
    payload.pop("output_hash", None)
    _drop_execution_runtime(payload.get("producer"))
    _drop_relation_execution_runtime(payload)
    return compute_canonical_payload_hash(payload)


def compute_literature_relations_public_payload_hash(
    value: LiteratureRelationsCandidate | dict[str, Any],
) -> str:
    return compute_canonical_payload_hash(_model_or_dict(value))


def compute_literature_relation_benchmark_output_hash(
    value: LiteratureRelationBenchmarkReport | dict[str, Any],
) -> str:
    payload = _model_or_dict(value)
    payload.pop("output_hash", None)
    return compute_canonical_payload_hash(payload)


def _confidence_distribution(
    cases: tuple[LiteratureRelationBenchmarkCaseResult, ...],
) -> tuple[LiteratureRelationConfidenceBin, ...]:
    scores = tuple(
        item.confidence_score
        for item in cases
        if item.confidence_status is LiteratureRelationConfidenceStatus.assessed
        and item.confidence_score is not None
    )
    return (
        LiteratureRelationConfidenceBin(
            label="[0.0,0.5)",
            lower_bound=0.0,
            upper_bound=0.5,
            upper_inclusive=False,
            count=sum(score < 0.5 for score in scores),
        ),
        LiteratureRelationConfidenceBin(
            label="[0.5,0.9)",
            lower_bound=0.5,
            upper_bound=0.9,
            upper_inclusive=False,
            count=sum(0.5 <= score < 0.9 for score in scores),
        ),
        LiteratureRelationConfidenceBin(
            label="[0.9,1.0]",
            lower_bound=0.9,
            upper_bound=1.0,
            upper_inclusive=True,
            count=sum(score >= 0.9 for score in scores),
        ),
    )


def _aggregate_status(
    records: tuple[LiteratureRelationCandidate, ...],
) -> LiteratureRelationStatus:
    if any(item.status is LiteratureRelationStatus.accepted for item in records):
        return LiteratureRelationStatus.accepted
    if any(item.status is LiteratureRelationStatus.candidate for item in records):
        return LiteratureRelationStatus.candidate
    return LiteratureRelationStatus.rejected


def _status_counts(
    records: tuple[LiteratureRelationCandidate, ...],
) -> LiteratureRelationStatusCounts:
    return LiteratureRelationStatusCounts(
        accepted=sum(item.status is LiteratureRelationStatus.accepted for item in records),
        candidate=sum(
            item.status is LiteratureRelationStatus.candidate for item in records
        ),
        rejected=sum(item.status is LiteratureRelationStatus.rejected for item in records),
    )


def _model_or_dict(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    if isinstance(value, BaseModel):
        return deepcopy(value.model_dump(mode="json", exclude_none=True))
    return _drop_none(deepcopy(value))


def _drop_none(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _drop_none(value.model_dump(mode="json", exclude_none=True))
    if isinstance(value, dict):
        return {
            key: _drop_none(item)
            for key, item in value.items()
            if item is not None
        }
    if isinstance(value, (list, tuple)):
        return [_drop_none(item) for item in value]
    return value


def _drop_execution_runtime(value: Any) -> None:
    if not isinstance(value, dict):
        return
    for field in (
        "execution_id",
        "run_id",
        "output_hash",
        "started_at",
        "finished_at",
        "latency_ms",
    ):
        value.pop(field, None)


def _drop_relation_execution_runtime(payload: dict[str, Any]) -> None:
    for field in ("claims", "relations", "records", "reasoning_traces"):
        records = payload.get(field)
        if not isinstance(records, list):
            continue
        for record in records:
            if isinstance(record, dict):
                record.pop("producer_execution_id", None)
    publisher_candidate = payload.get("publisher_candidate")
    if isinstance(publisher_candidate, dict):
        _drop_execution_runtime(publisher_candidate.get("producer"))
        _drop_relation_execution_runtime(publisher_candidate)


def _require_unique(values: tuple[Any, ...], label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"duplicate {label}")


def _require_sorted_unique(values: tuple[Any, ...], label: str) -> None:
    _require_unique(values, label)
    if values != tuple(sorted(values)):
        raise ValueError(f"{label} values must use stable order")


__all__ = [
    "LiteratureClaimArtifactVersionReference",
    "LiteratureComparabilityStatus",
    "LiteratureReasoningTraceCandidate",
    "LiteratureReasoningTraceModelCandidate",
    "LiteratureReasoningTraceStepCandidate",
    "LiteratureRelationAdmissionResult",
    "LiteratureRelationBenchmarkCaseKind",
    "LiteratureRelationBenchmarkCaseResult",
    "LiteratureRelationBenchmarkEvaluationCase",
    "LiteratureRelationBenchmarkReport",
    "LiteratureRelationCandidate",
    "LiteratureRelationComparabilityCandidate",
    "LiteratureRelationConfidenceAssessment",
    "LiteratureRelationConfidenceSubject",
    "LiteratureRelationConfidenceStatus",
    "LiteratureRelationDirectionCandidate",
    "LiteratureRelationEvidenceReference",
    "LiteratureRelationExtractionOutput",
    "LiteratureRelationFailureStage",
    "LiteratureRelationInputVersions",
    "LiteratureRelationModelCandidate",
    "LiteratureRelationProducerExecution",
    "LiteratureRelationRejectionReason",
    "LiteratureRelationReviewReason",
    "LiteratureRelationsCandidate",
    "LiteratureRelationStatus",
    "LiteratureRelationStatusCounts",
    "LiteratureRelationTypeCount",
    "LiteratureTraceOperation",
    "compute_literature_relation_admission_output_hash",
    "compute_literature_relation_benchmark_output_hash",
    "compute_literature_relation_fingerprint",
    "compute_literature_relation_confidence_subject_fingerprint",
    "compute_literature_relations_output_hash",
    "compute_literature_relations_public_payload_hash",
    "build_literature_relation_confidence_subject",
]
