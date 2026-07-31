"""Versioned C-08 cross-source entity-alignment contracts."""

from __future__ import annotations

from copy import deepcopy
from datetime import date
from enum import StrEnum
import math
from typing import Annotated, Any, Literal, Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from ._hashing import compute_canonical_payload_hash
from .enums import SourceMode
from .evidence import SourceSnapshotRecord
from .manifest import ContentHash, Identifier, ObjectType, SemanticVersion
from .source_acquisition import (
    DataSourceCompletion,
    DataSourceCompletionStatus,
    DataSourceDataLevel,
    RawDataSourceRecord,
)


MODEL_CONFIG = ConfigDict(extra="forbid", frozen=True)
NonEmptyString = Annotated[str, Field(min_length=1)]
CanonicalFieldId = Annotated[
    str,
    Field(pattern=r"^(planet|star|system)\.[a-z][a-z0-9_]*$"),
]
NormalizedScalar = str | int | float | bool


class EntityLevel(StrEnum):
    host_star = "host_star"
    planet_candidate = "planet_candidate"
    planet_assertion = "planet_assertion"


class CrossmatchMethod(StrEnum):
    exact_identifier = "exact_identifier"
    curated_entity_alias = "curated_entity_alias"
    coordinate = "coordinate"
    compound = "compound"


class MatchDecision(StrEnum):
    accepted = "accepted"
    rejected = "rejected"
    review_required = "review_required"
    conflict = "conflict"
    inconclusive = "inconclusive"
    unmatched = "unmatched"


class ConfidenceBand(StrEnum):
    high = "high"
    medium = "medium"
    low = "low"
    not_applicable = "not_applicable"


class CrossmatchRecordType(StrEnum):
    paired = "paired"
    unpaired = "unpaired"
    conflict_group = "conflict_group"


class CrossmatchSide(StrEnum):
    left = "left"
    right = "right"


class MatchTopology(StrEnum):
    one_to_one = "one_to_one"
    one_to_many = "one_to_many"
    many_to_one = "many_to_one"
    many_to_many = "many_to_many"


class AdjudicationDecision(StrEnum):
    accepted = "accepted"
    rejected = "rejected"
    keep_unresolved = "keep_unresolved"


class ReviewerKind(StrEnum):
    human = "human"
    benchmark_fixture = "benchmark_fixture"


class ConditionOperator(StrEnum):
    exact = "exact"
    curated_alias = "curated_alias"
    angular_separation_lte = "angular_separation_lte"
    angular_separation_gt = "angular_separation_gt"
    contradicts = "contradicts"
    source_scope = "source_scope"


class CrossmatchCapacityPolicy(BaseModel):
    model_config = MODEL_CONFIG

    max_left_records: int = Field(gt=0, le=100_000)
    max_right_records: int = Field(gt=0, le=100_000)
    max_candidate_pairs: int = Field(gt=0, le=10_000_000)


class CoordinatePolicy(BaseModel):
    model_config = MODEL_CONFIG

    frame: Literal["ICRS"] = "ICRS"
    unit: Literal["degree"] = "degree"
    strict_separation_arcsec: float = Field(gt=0, le=3600)
    manual_review_separation_arcsec: float = Field(gt=0, le=3600)

    @field_validator(
        "strict_separation_arcsec",
        "manual_review_separation_arcsec",
    )
    @classmethod
    def reject_non_finite_threshold(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("coordinate threshold must be finite")
        return value

    @model_validator(mode="after")
    def validate_threshold_order(self) -> Self:
        if self.strict_separation_arcsec >= self.manual_review_separation_arcsec:
            raise ValueError(
                "strict coordinate threshold must be below manual-review threshold"
            )
        return self


class ConfidencePolicy(BaseModel):
    model_config = MODEL_CONFIG

    high_minimum: float = Field(ge=0, le=1)
    medium_minimum: float = Field(ge=0, le=1)
    low_minimum: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_order(self) -> Self:
        if not (
            self.high_minimum > self.medium_minimum > self.low_minimum >= 0
        ):
            raise ValueError("confidence thresholds must be strictly descending")
        return self


class MethodConfidencePolicy(BaseModel):
    model_config = MODEL_CONFIG

    exact_identifier: float = Field(ge=0, le=1)
    curated_entity_alias: float = Field(ge=0, le=1)
    coordinate_strict: float = Field(ge=0, le=1)
    coordinate_review: float = Field(ge=0, le=1)
    compound: float = Field(ge=0, le=1)

    @field_validator(
        "exact_identifier",
        "curated_entity_alias",
        "coordinate_strict",
        "coordinate_review",
        "compound",
    )
    @classmethod
    def reject_non_finite_confidence(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("method confidence must be finite")
        return value


class EntityAliasEntry(BaseModel):
    model_config = MODEL_CONFIG

    alias_id: Identifier
    entity_level: EntityLevel
    left_source_id: Identifier
    left_field_id: CanonicalFieldId
    left_value: NonEmptyString
    right_source_id: Identifier
    right_field_id: CanonicalFieldId
    right_value: NonEmptyString
    rationale: NonEmptyString


class EntityAliasCatalog(BaseModel):
    model_config = MODEL_CONFIG

    catalog_id: Identifier
    version: SemanticVersion
    content_hash: ContentHash
    entries: tuple[EntityAliasEntry, ...]
    source: NonEmptyString
    maintainer: NonEmptyString
    created_at: date

    @model_validator(mode="after")
    def validate_catalog(self) -> Self:
        alias_ids = [entry.alias_id for entry in self.entries]
        if len(alias_ids) != len(set(alias_ids)):
            raise ValueError("entity alias catalog contains duplicate alias_id")
        _validate_content_hash(self)
        return self


class CrossmatchSourceOriginPolicy(BaseModel):
    model_config = MODEL_CONFIG

    source_mode: SourceMode
    data_levels: tuple[DataSourceDataLevel, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_data_levels(self) -> Self:
        if len(self.data_levels) != len(set(self.data_levels)):
            raise ValueError("source origin policy contains duplicate data level")
        return self


class CrossmatchSourcePolicy(BaseModel):
    model_config = MODEL_CONFIG

    policy_id: Identifier
    version: SemanticVersion
    allowed_origins: tuple[CrossmatchSourceOriginPolicy, ...] = Field(
        min_length=1
    )
    completion_statuses: tuple[DataSourceCompletionStatus, ...] = Field(
        min_length=1
    )
    content_hash: ContentHash

    @model_validator(mode="after")
    def validate_policy(self) -> Self:
        source_modes = [origin.source_mode for origin in self.allowed_origins]
        if len(source_modes) != len(set(source_modes)):
            raise ValueError("source policy contains duplicate source mode")
        if len(self.completion_statuses) != len(set(self.completion_statuses)):
            raise ValueError("source policy contains duplicate completion status")
        if set(self.completion_statuses) != set(DataSourceCompletionStatus):
            raise ValueError(
                "source policy completion statuses must cover the closed contract"
            )
        _validate_content_hash(self)
        return self


class CrossmatchRuleSet(BaseModel):
    model_config = MODEL_CONFIG

    rule_set_id: Identifier
    schema_version: SemanticVersion
    version: SemanticVersion
    content_hash: ContentHash
    producer_name: NonEmptyString
    producer_version: SemanticVersion
    case_manifest_id: Identifier
    case_manifest_version: SemanticVersion
    case_manifest_content_hash: ContentHash
    field_manifest_id: Identifier
    field_manifest_version: SemanticVersion
    field_manifest_content_hash: ContentHash
    source_policy_version: SemanticVersion
    source_policy_content_hash: ContentHash
    identifier_policy_version: SemanticVersion
    name_policy_version: SemanticVersion
    alias_policy_version: SemanticVersion
    coordinate_policy_version: SemanticVersion
    entity_alias_catalog_version: SemanticVersion
    entity_alias_catalog_content_hash: ContentHash
    capacity_policy_version: SemanticVersion
    conflict_policy_version: SemanticVersion
    supported_entity_levels: tuple[EntityLevel, ...] = Field(min_length=1)
    method_priority: tuple[CrossmatchMethod, ...] = Field(min_length=1)
    alias_requires_corroboration: bool
    capacity: CrossmatchCapacityPolicy
    coordinate: CoordinatePolicy
    confidence: ConfidencePolicy
    method_confidence: MethodConfidencePolicy
    created_at: date
    maintained_by: NonEmptyString

    @model_validator(mode="after")
    def validate_rule_set_hash(self) -> Self:
        if len(self.supported_entity_levels) != len(
            set(self.supported_entity_levels)
        ):
            raise ValueError("RuleSet supported entity levels must be unique")
        if len(self.method_priority) != len(set(self.method_priority)):
            raise ValueError("RuleSet method priority must be unique")
        if set(self.supported_entity_levels) != set(EntityLevel):
            raise ValueError(
                "RuleSet supported entity levels must cover every EntityLevel"
            )
        if set(self.method_priority) != set(CrossmatchMethod):
            raise ValueError(
                "RuleSet method priority must cover every CrossmatchMethod"
            )
        _validate_content_hash(self)
        return self


class CrossmatchSourceInput(BaseModel):
    """Typed projection of one C-02/C-07 acquisition result."""

    model_config = MODEL_CONFIG

    source_mode: SourceMode
    data_level: DataSourceDataLevel
    records: tuple[RawDataSourceRecord, ...]
    snapshot: SourceSnapshotRecord
    completion: DataSourceCompletion

    @model_validator(mode="after")
    def validate_source_identity(self) -> Self:
        if any(record.source_id != self.snapshot.source_id for record in self.records):
            raise ValueError("source input records must belong to the source snapshot")
        row_keys = [record.row_key for record in self.records]
        if len(row_keys) != len(set(row_keys)):
            raise ValueError("source input contains duplicate row key")
        record_hashes = [record.content_hash for record in self.records]
        if len(record_hashes) != len(set(record_hashes)):
            raise ValueError("source input contains duplicate record content hash")
        metadata = self.snapshot.request_metadata
        if metadata.get("source_mode") not in (None, self.source_mode.value):
            raise ValueError("source input mode disagrees with source snapshot")
        if metadata.get("data_level") not in (None, self.data_level.value):
            raise ValueError("source input data level disagrees with source snapshot")
        return self


class ManualReviewDecision(BaseModel):
    model_config = MODEL_CONFIG

    schema_version: Literal["1.0.0"] = "1.0.0"
    decision_id: Identifier
    logical_match_key: ContentHash
    adjudication: AdjudicationDecision
    adjudicated_by: NonEmptyString
    reviewer_kind: ReviewerKind
    adjudication_rule_or_actor: NonEmptyString
    adjudicated_at: AwareDatetime
    rationale: NonEmptyString
    source_input_hash: ContentHash
    rule_set_id: Identifier
    rule_set_version: SemanticVersion
    rule_set_content_hash: ContentHash
    left_candidate_ids: tuple[Identifier, ...] = Field(min_length=1)
    right_candidate_ids: tuple[Identifier, ...] = Field(min_length=1)
    evidence_ids: tuple[Identifier, ...] = Field(min_length=1)
    content_hash: ContentHash

    @model_validator(mode="after")
    def validate_decision_hash(self) -> Self:
        for values, label in (
            (self.left_candidate_ids, "left candidate"),
            (self.right_candidate_ids, "right candidate"),
            (self.evidence_ids, "Evidence"),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"manual decision contains duplicate {label} ID")
        _validate_content_hash(self)
        return self


class CrossmatchInput(BaseModel):
    model_config = MODEL_CONFIG

    case_manifest_id: Identifier
    case_manifest_version: SemanticVersion
    case_manifest_content_hash: ContentHash
    field_manifest_id: Identifier
    field_manifest_version: SemanticVersion
    field_manifest_content_hash: ContentHash
    rule_set: CrossmatchRuleSet
    alias_catalog: EntityAliasCatalog
    source_policy: CrossmatchSourcePolicy
    left: CrossmatchSourceInput
    right: CrossmatchSourceInput
    source_input_hash: ContentHash
    manual_review_decisions: tuple[ManualReviewDecision, ...] = ()
    input_hash: ContentHash

    @model_validator(mode="after")
    def validate_frozen_inputs(self) -> Self:
        rule_set = self.rule_set
        expected_manifest_pins = (
            self.case_manifest_id,
            self.case_manifest_version,
            self.case_manifest_content_hash,
            self.field_manifest_id,
            self.field_manifest_version,
            self.field_manifest_content_hash,
        )
        actual_manifest_pins = (
            rule_set.case_manifest_id,
            rule_set.case_manifest_version,
            rule_set.case_manifest_content_hash,
            rule_set.field_manifest_id,
            rule_set.field_manifest_version,
            rule_set.field_manifest_content_hash,
        )
        if actual_manifest_pins != expected_manifest_pins:
            raise ValueError("crossmatch input manifest pins disagree with RuleSet")
        if (
            self.alias_catalog.version != rule_set.entity_alias_catalog_version
            or self.alias_catalog.content_hash
            != rule_set.entity_alias_catalog_content_hash
        ):
            raise ValueError("crossmatch input alias catalog disagrees with RuleSet")
        if (
            self.source_policy.version != rule_set.source_policy_version
            or self.source_policy.content_hash
            != rule_set.source_policy_content_hash
        ):
            raise ValueError("crossmatch input SourcePolicy disagrees with RuleSet")
        allowed_origins = {
            origin.source_mode: set(origin.data_levels)
            for origin in self.source_policy.allowed_origins
        }
        for source in (self.left, self.right):
            if source.data_level not in allowed_origins.get(
                source.source_mode,
                set(),
            ):
                raise ValueError(
                    "source input origin is absent from the frozen SourcePolicy"
                )
        if self.left.snapshot.source_id == self.right.snapshot.source_id:
            raise ValueError("crossmatch input sources must be distinct")
        expected_source_hash = compute_crossmatch_source_input_hash(self)
        if self.source_input_hash != expected_source_hash:
            raise ValueError(
                f"source_input_hash does not match input: {expected_source_hash}"
            )
        decision_keys = [
            decision.logical_match_key for decision in self.manual_review_decisions
        ]
        if len(decision_keys) != len(set(decision_keys)):
            raise ValueError("manual decisions must target unique logical matches")
        for decision in self.manual_review_decisions:
            if decision.source_input_hash != self.source_input_hash:
                raise ValueError("manual decision input hash does not match")
            if (
                decision.rule_set_id != self.rule_set.rule_set_id
                or decision.rule_set_version != self.rule_set.version
                or decision.rule_set_content_hash != self.rule_set.content_hash
            ):
                raise ValueError("manual decision RuleSet hash does not match")
        expected_input_hash = compute_crossmatch_input_hash(self)
        if self.input_hash != expected_input_hash:
            raise ValueError(f"input_hash does not match input: {expected_input_hash}")
        return self


class SourceRecordReference(BaseModel):
    model_config = MODEL_CONFIG

    side: CrossmatchSide
    source_snapshot_id: Identifier
    source_snapshot_content_hash: ContentHash
    source_id: Identifier
    query_hash: ContentHash
    row_key: tuple[tuple[NonEmptyString, NonEmptyString], ...] = Field(min_length=1)
    record_content_hash: ContentHash
    object_type: ObjectType
    source_entity_key: NonEmptyString


class EvidenceLocator(BaseModel):
    model_config = MODEL_CONFIG

    side: CrossmatchSide
    source_snapshot_id: Identifier
    source_id: Identifier
    query_hash: ContentHash
    row_key: tuple[tuple[NonEmptyString, NonEmptyString], ...] = Field(min_length=1)
    raw_field: NonEmptyString


class SkyCoordinate(BaseModel):
    model_config = MODEL_CONFIG

    frame: Literal["ICRS"] = "ICRS"
    unit: Literal["degree"] = "degree"
    right_ascension: float = Field(ge=0, lt=360)
    declination: float = Field(ge=-90, le=90)

    @field_validator("right_ascension", "declination")
    @classmethod
    def reject_non_finite_coordinate(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("coordinate values must be finite")
        return value


class CanonicalIdentityValue(BaseModel):
    model_config = MODEL_CONFIG

    field_id: CanonicalFieldId
    normalized_value: NonEmptyString
    normalization_rule_version: SemanticVersion
    locator: EvidenceLocator


class EntityCandidate(BaseModel):
    model_config = MODEL_CONFIG

    candidate_id: Identifier
    side: CrossmatchSide
    entity_level: EntityLevel
    source_record: SourceRecordReference
    identity_values: tuple[CanonicalIdentityValue, ...] = Field(min_length=1)
    coordinate: SkyCoordinate | None = None
    content_hash: ContentHash

    @model_validator(mode="after")
    def validate_candidate(self) -> Self:
        if self.side is not self.source_record.side:
            raise ValueError("candidate side disagrees with source record")
        if any(value.locator.side is not self.side for value in self.identity_values):
            raise ValueError("candidate identity locator uses the wrong side")
        field_ids = [value.field_id for value in self.identity_values]
        if len(field_ids) != len(set(field_ids)):
            raise ValueError("candidate identity fields must be unique")
        _validate_content_hash(self)
        return self


class CrossmatchCondition(BaseModel):
    model_config = MODEL_CONFIG

    condition_id: Identifier
    operator: ConditionOperator
    field_id: CanonicalFieldId | None = None
    left_value: NormalizedScalar | None = None
    right_value: NormalizedScalar | None = None
    separation_arcsec: float | None = Field(default=None, ge=0)
    strict_threshold_arcsec: float | None = Field(default=None, gt=0)
    manual_review_threshold_arcsec: float | None = Field(default=None, gt=0)
    rule_reference: NonEmptyString

    @model_validator(mode="after")
    def validate_coordinate_condition(self) -> Self:
        values = (
            self.separation_arcsec,
            self.strict_threshold_arcsec,
            self.manual_review_threshold_arcsec,
        )
        if any(value is not None and not math.isfinite(value) for value in values):
            raise ValueError("condition distances must be finite")
        coordinate_condition = self.operator in {
            ConditionOperator.angular_separation_lte,
            ConditionOperator.angular_separation_gt,
        }
        value_condition = self.operator in {
            ConditionOperator.exact,
            ConditionOperator.curated_alias,
            ConditionOperator.contradicts,
        }
        if coordinate_condition != all(value is not None for value in values):
            raise ValueError(
                "coordinate condition requires separation and both thresholds"
            )
        strict_threshold = self.strict_threshold_arcsec
        manual_threshold = self.manual_review_threshold_arcsec
        if (
            coordinate_condition
            and strict_threshold is not None
            and manual_threshold is not None
            and strict_threshold >= manual_threshold
        ):
            raise ValueError("coordinate condition thresholds are out of order")
        if value_condition and (
            self.field_id is None
            or self.left_value is None
            or self.right_value is None
        ):
            raise ValueError(
                "identifier and alias conditions require field and both values"
            )
        if coordinate_condition and (
            self.field_id is not None
            or self.left_value is not None
            or self.right_value is not None
        ):
            raise ValueError(
                "coordinate conditions must not carry identifier values"
            )
        return self


class CrossmatchEvidence(BaseModel):
    model_config = MODEL_CONFIG

    evidence_id: Identifier
    entity_level: EntityLevel
    method: CrossmatchMethod
    decision: MatchDecision
    confidence: float = Field(ge=0, le=1)
    confidence_band: ConfidenceBand
    left_candidate_id: Identifier
    right_candidate_id: Identifier
    left_locators: tuple[EvidenceLocator, ...] = Field(min_length=1)
    right_locators: tuple[EvidenceLocator, ...] = Field(min_length=1)
    conditions: tuple[CrossmatchCondition, ...] = Field(min_length=1)
    rule_set_id: Identifier
    rule_set_version: SemanticVersion
    rule_set_content_hash: ContentHash
    content_hash: ContentHash

    @model_validator(mode="after")
    def validate_evidence(self) -> Self:
        if not math.isfinite(self.confidence):
            raise ValueError("Evidence confidence must be finite")
        if any(
            locator.side is not CrossmatchSide.left for locator in self.left_locators
        ):
            raise ValueError("left evidence locator uses the wrong side")
        if any(
            locator.side is not CrossmatchSide.right
            for locator in self.right_locators
        ):
            raise ValueError("right evidence locator uses the wrong side")
        condition_ids = [condition.condition_id for condition in self.conditions]
        if len(condition_ids) != len(set(condition_ids)):
            raise ValueError("Evidence contains duplicate condition_id")
        _validate_content_hash(self)
        return self


class CandidateEdge(BaseModel):
    model_config = MODEL_CONFIG

    edge_id: Identifier
    logical_match_key: ContentHash
    entity_level: EntityLevel
    left_candidate_id: Identifier
    right_candidate_id: Identifier
    method: CrossmatchMethod
    decision: MatchDecision
    confidence: float = Field(ge=0, le=1)
    confidence_band: ConfidenceBand
    condition_ids: tuple[Identifier, ...] = Field(min_length=1)
    evidence_ids: tuple[Identifier, ...] = Field(min_length=1)
    content_hash: ContentHash

    @model_validator(mode="after")
    def validate_edge(self) -> Self:
        if not math.isfinite(self.confidence):
            raise ValueError("candidate confidence must be finite")
        if (
            self.method is CrossmatchMethod.coordinate
            and self.decision is MatchDecision.accepted
        ):
            raise ValueError("coordinate-only candidate cannot be accepted")
        if len(self.condition_ids) != len(set(self.condition_ids)):
            raise ValueError("candidate edge contains duplicate condition_id")
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("candidate edge contains duplicate evidence_id")
        _validate_content_hash(self)
        return self


class _AdjudicableRecord(BaseModel):
    model_config = MODEL_CONFIG

    manual_decision_id: Identifier | None = None
    adjudication: AdjudicationDecision | None = None
    adjudicated_by: NonEmptyString | None = None
    reviewer_kind: ReviewerKind | None = None
    adjudication_rule_or_actor: NonEmptyString | None = None
    adjudicated_at: AwareDatetime | None = None
    adjudication_rationale: NonEmptyString | None = None
    manual_decision_content_hash: ContentHash | None = None

    @model_validator(mode="after")
    def validate_adjudication(self) -> Self:
        values = (
            self.manual_decision_id,
            self.adjudication,
            self.adjudicated_by,
            self.reviewer_kind,
            self.adjudication_rule_or_actor,
            self.adjudicated_at,
            self.adjudication_rationale,
            self.manual_decision_content_hash,
        )
        if any(value is not None for value in values) and not all(
            value is not None for value in values
        ):
            raise ValueError("manual adjudication fields must be recorded together")
        return self


class PairedMatch(_AdjudicableRecord):
    record_type: Literal["paired"] = "paired"
    logical_match_key: ContentHash
    entity_level: EntityLevel
    topology: MatchTopology
    left_candidate_ids: tuple[Identifier, ...] = Field(min_length=1)
    right_candidate_ids: tuple[Identifier, ...] = Field(min_length=1)
    method: CrossmatchMethod
    decision: MatchDecision
    confidence_band: ConfidenceBand
    evidence_ids: tuple[Identifier, ...] = Field(min_length=1)
    content_hash: ContentHash

    @model_validator(mode="after")
    def validate_paired_match(self) -> Self:
        if self.decision not in {
            MatchDecision.accepted,
            MatchDecision.rejected,
            MatchDecision.review_required,
        }:
            raise ValueError("paired match has an invalid decision")
        if (
            self.method is CrossmatchMethod.coordinate
            and self.decision is MatchDecision.accepted
        ):
            raise ValueError("coordinate-only match cannot be accepted")
        for values, label in (
            (self.left_candidate_ids, "left candidate"),
            (self.right_candidate_ids, "right candidate"),
            (self.evidence_ids, "Evidence"),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"paired match contains duplicate {label} ID")
        _validate_content_hash(self)
        return self


class UnpairedRecord(BaseModel):
    model_config = MODEL_CONFIG

    record_type: Literal["unpaired"] = "unpaired"
    candidate_id: Identifier
    side: CrossmatchSide
    entity_level: EntityLevel
    decision: MatchDecision
    source_completion_status: Literal["complete", "truncated", "unknown"]
    reason: NonEmptyString
    content_hash: ContentHash

    @model_validator(mode="after")
    def validate_unpaired_record(self) -> Self:
        if self.decision not in {
            MatchDecision.unmatched,
            MatchDecision.inconclusive,
        }:
            raise ValueError("unpaired record has an invalid decision")
        if (
            self.source_completion_status == "complete"
            and self.decision is not MatchDecision.unmatched
        ):
            raise ValueError("complete opposite source requires unmatched decision")
        if (
            self.source_completion_status in {"truncated", "unknown"}
            and self.decision is not MatchDecision.inconclusive
        ):
            raise ValueError(
                "incomplete opposite source requires inconclusive decision"
            )
        _validate_content_hash(self)
        return self


class ConflictGroup(_AdjudicableRecord):
    record_type: Literal["conflict_group"] = "conflict_group"
    logical_match_key: ContentHash
    entity_level: EntityLevel
    left_candidate_ids: tuple[Identifier, ...] = Field(min_length=1)
    right_candidate_ids: tuple[Identifier, ...] = Field(min_length=1)
    method: CrossmatchMethod
    decision: Literal[MatchDecision.conflict] = MatchDecision.conflict
    conflict_code: Identifier
    evidence_ids: tuple[Identifier, ...] = Field(min_length=1)
    content_hash: ContentHash

    @model_validator(mode="after")
    def validate_conflict_group(self) -> Self:
        for values, label in (
            (self.left_candidate_ids, "left candidate"),
            (self.right_candidate_ids, "right candidate"),
            (self.evidence_ids, "Evidence"),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"conflict group contains duplicate {label} ID")
        _validate_content_hash(self)
        return self


CrossmatchRecord = Annotated[
    PairedMatch | UnpairedRecord | ConflictGroup,
    Field(discriminator="record_type"),
]


class RatioMetric(BaseModel):
    model_config = MODEL_CONFIG

    numerator: int = Field(ge=0)
    denominator: int = Field(ge=0)
    value: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def validate_ratio(self) -> Self:
        if self.numerator > self.denominator:
            raise ValueError("ratio numerator must not exceed denominator")
        expected = (
            self.numerator / self.denominator if self.denominator else None
        )
        if expected is None and self.value is not None:
            raise ValueError("empty ratio must not have a value")
        if expected is not None and (
            self.value is None or not math.isclose(self.value, expected, abs_tol=1e-12)
        ):
            raise ValueError("ratio value does not match numerator and denominator")
        return self


class ConfidenceDistribution(BaseModel):
    model_config = MODEL_CONFIG

    high: int = Field(ge=0)
    medium: int = Field(ge=0)
    low: int = Field(ge=0)
    not_applicable: int = Field(ge=0)


class MethodDistribution(BaseModel):
    model_config = MODEL_CONFIG

    exact_identifier: int = Field(ge=0)
    curated_entity_alias: int = Field(ge=0)
    coordinate: int = Field(ge=0)
    compound: int = Field(ge=0)


class CrossmatchMetrics(BaseModel):
    model_config = MODEL_CONFIG

    left_record_count: int = Field(ge=0)
    right_record_count: int = Field(ge=0)
    left_candidate_count: int = Field(ge=0)
    right_candidate_count: int = Field(ge=0)
    candidate_pair_count: int = Field(
        ge=0,
        description=(
            "Materialized CandidateEdge count after matching; this is not the "
            "eligible candidate-pair count used by the capacity preflight."
        ),
    )
    paired_group_count: int = Field(ge=0)
    matched_group_count: int = Field(ge=0)
    ambiguous_group_count: int = Field(ge=0)
    conflict_group_count: int = Field(ge=0)
    unmatched_record_count: int = Field(ge=0)
    unmatched_left_record_count: int = Field(ge=0)
    unmatched_right_record_count: int = Field(ge=0)
    inconclusive_record_count: int = Field(ge=0)
    manual_review_required_count: int = Field(ge=0)
    low_confidence_count: int = Field(ge=0)
    manual_adjudication_count: int = Field(ge=0)
    one_to_one_count: int = Field(ge=0)
    one_to_many_count: int = Field(ge=0)
    many_to_one_count: int = Field(ge=0)
    many_to_many_count: int = Field(ge=0)
    confidence_distribution: ConfidenceDistribution
    method_distribution: MethodDistribution
    error_example_references: tuple[ContentHash, ...]
    match_coverage: RatioMetric
    conflict_rate: RatioMetric
    unmatched_rate: RatioMetric
    evidence_coverage: RatioMetric

    @model_validator(mode="after")
    def validate_metric_totals(self) -> Self:
        topology_count = (
            self.one_to_one_count
            + self.one_to_many_count
            + self.many_to_one_count
            + self.many_to_many_count
        )
        if topology_count != self.paired_group_count:
            raise ValueError("topology counts must equal paired_group_count")
        if (
            self.unmatched_left_record_count
            + self.unmatched_right_record_count
            != self.unmatched_record_count
        ):
            raise ValueError("side unmatched counts must equal unmatched_record_count")
        confidence_count = sum(
            (
                self.confidence_distribution.high,
                self.confidence_distribution.medium,
                self.confidence_distribution.low,
                self.confidence_distribution.not_applicable,
            )
        )
        method_count = sum(
            (
                self.method_distribution.exact_identifier,
                self.method_distribution.curated_entity_alias,
                self.method_distribution.coordinate,
                self.method_distribution.compound,
            )
        )
        if confidence_count != self.candidate_pair_count:
            raise ValueError("confidence distribution must cover candidate pairs")
        if method_count != self.candidate_pair_count:
            raise ValueError("method distribution must cover candidate pairs")
        if self.matched_group_count > self.paired_group_count:
            raise ValueError("matched_group_count exceeds paired_group_count")
        return self


class CrossmatchProducerExecution(BaseModel):
    model_config = MODEL_CONFIG

    producer_name: NonEmptyString
    producer_version: SemanticVersion
    rule_set_id: Identifier
    rule_set_version: SemanticVersion
    rule_set_content_hash: ContentHash


class CrossmatchResult(BaseModel):
    """Typed C-04 handoff; publication and ArtifactVersion identity are out of scope."""

    model_config = MODEL_CONFIG

    result_id: Identifier
    schema_version: SemanticVersion
    input_hash: ContentHash
    case_manifest_id: Identifier
    case_manifest_version: SemanticVersion
    case_manifest_content_hash: ContentHash
    field_manifest_id: Identifier
    field_manifest_version: SemanticVersion
    field_manifest_content_hash: ContentHash
    left_source_id: Identifier
    right_source_id: Identifier
    left_source_mode: SourceMode
    right_source_mode: SourceMode
    left_data_level: DataSourceDataLevel
    right_data_level: DataSourceDataLevel
    left_source_snapshot: SourceSnapshotRecord
    right_source_snapshot: SourceSnapshotRecord
    left_completion: DataSourceCompletion
    right_completion: DataSourceCompletion
    rule_set_id: Identifier
    rule_set_version: SemanticVersion
    rule_set_content_hash: ContentHash
    alias_catalog_id: Identifier
    alias_catalog_version: SemanticVersion
    alias_catalog_content_hash: ContentHash
    candidates: tuple[EntityCandidate, ...]
    candidate_edges: tuple[CandidateEdge, ...]
    evidence: tuple[CrossmatchEvidence, ...]
    records: tuple[CrossmatchRecord, ...]
    metrics: CrossmatchMetrics
    producer_execution: CrossmatchProducerExecution
    output_hash: ContentHash
    content_hash: ContentHash

    @model_validator(mode="after")
    def validate_handoff(self) -> Self:
        candidates_by_id = {
            candidate.candidate_id: candidate for candidate in self.candidates
        }
        candidate_ids = set(candidates_by_id)
        edge_ids = {edge.edge_id for edge in self.candidate_edges}
        evidence_ids = {item.evidence_id for item in self.evidence}
        if len(candidate_ids) != len(self.candidates):
            raise ValueError("crossmatch result contains duplicate candidate_id")
        if len(evidence_ids) != len(self.evidence):
            raise ValueError("crossmatch result contains duplicate evidence_id")
        if len(edge_ids) != len(self.candidate_edges):
            raise ValueError("crossmatch result contains duplicate edge_id")
        record_keys = [
            (
                record.record_type,
                (
                    record.candidate_id
                    if isinstance(record, UnpairedRecord)
                    else record.logical_match_key
                ),
            )
            for record in self.records
        ]
        if len(record_keys) != len(set(record_keys)):
            raise ValueError("crossmatch result contains duplicate record identity")
        snapshots = {
            CrossmatchSide.left: self.left_source_snapshot,
            CrossmatchSide.right: self.right_source_snapshot,
        }
        for candidate in self.candidates:
            snapshot = snapshots[candidate.side]
            reference = candidate.source_record
            if (
                reference.source_snapshot_id != snapshot.snapshot_id
                or reference.source_snapshot_content_hash != snapshot.content_hash
                or reference.source_id != snapshot.source_id
                or reference.query_hash != snapshot.query_hash
            ):
                raise ValueError(
                    "candidate source reference disagrees with SourceSnapshot"
                )
            for identity in candidate.identity_values:
                locator = identity.locator
                if (
                    locator.side is not candidate.side
                    or locator.source_snapshot_id != reference.source_snapshot_id
                    or locator.source_id != reference.source_id
                    or locator.query_hash != reference.query_hash
                    or locator.row_key != reference.row_key
                ):
                    raise ValueError(
                        "candidate identity locator disagrees with source reference"
                    )
        evidence_by_id = {
            item.evidence_id: item for item in self.evidence
        }
        for item in self.evidence:
            left_candidate = candidates_by_id.get(item.left_candidate_id)
            right_candidate = candidates_by_id.get(item.right_candidate_id)
            if (
                left_candidate is None
                or left_candidate.side is not CrossmatchSide.left
                or right_candidate is None
                or right_candidate.side is not CrossmatchSide.right
            ):
                raise ValueError("Evidence references invalid candidate sides")
            expected_right_level = (
                EntityLevel.host_star
                if item.entity_level is EntityLevel.host_star
                else EntityLevel.planet_assertion
            )
            if (
                item.entity_level is not left_candidate.entity_level
                or right_candidate.entity_level is not expected_right_level
            ):
                raise ValueError("Evidence entity level disagrees with candidates")
            if (
                item.rule_set_id != self.rule_set_id
                or item.rule_set_version != self.rule_set_version
                or item.rule_set_content_hash != self.rule_set_content_hash
            ):
                raise ValueError("Evidence disagrees with result RuleSet")
            for locator in (*item.left_locators, *item.right_locators):
                snapshot = snapshots[locator.side]
                if (
                    locator.source_snapshot_id != snapshot.snapshot_id
                    or locator.source_id != snapshot.source_id
                    or locator.query_hash != snapshot.query_hash
                ):
                    raise ValueError("Evidence locator disagrees with SourceSnapshot")
        for edge in self.candidate_edges:
            if (
                edge.left_candidate_id not in candidate_ids
                or edge.right_candidate_id not in candidate_ids
            ):
                raise ValueError("candidate edge references an unknown candidate")
            if not set(edge.evidence_ids).issubset(evidence_ids):
                raise ValueError("candidate edge references unknown Evidence")
            left_candidate = candidates_by_id[edge.left_candidate_id]
            right_candidate = candidates_by_id[edge.right_candidate_id]
            if (
                left_candidate.side is not CrossmatchSide.left
                or right_candidate.side is not CrossmatchSide.right
                or left_candidate.entity_level is not edge.entity_level
                or right_candidate.entity_level
                is not (
                    EntityLevel.host_star
                    if edge.entity_level is EntityLevel.host_star
                    else EntityLevel.planet_assertion
                )
            ):
                raise ValueError("candidate edge uses invalid candidate sides or level")
            edge_evidence = [evidence_by_id[item] for item in edge.evidence_ids]
            if any(
                item.left_candidate_id != edge.left_candidate_id
                or item.right_candidate_id != edge.right_candidate_id
                or item.method is not edge.method
                or item.decision is not edge.decision
                or item.confidence != edge.confidence
                or item.confidence_band is not edge.confidence_band
                for item in edge_evidence
            ):
                raise ValueError("candidate edge disagrees with Evidence")
            condition_ids = {
                condition.condition_id
                for item in edge_evidence
                for condition in item.conditions
            }
            if set(edge.condition_ids) != condition_ids:
                raise ValueError("candidate edge condition IDs disagree with Evidence")
        for record in self.records:
            if isinstance(record, PairedMatch | ConflictGroup):
                if not set(record.left_candidate_ids).issubset(candidate_ids):
                    raise ValueError("record references unknown left candidate")
                if not set(record.right_candidate_ids).issubset(candidate_ids):
                    raise ValueError("record references unknown right candidate")
                if not set(record.evidence_ids).issubset(evidence_ids):
                    raise ValueError("record references unknown Evidence")
                expected_right_level = (
                    EntityLevel.host_star
                    if record.entity_level is EntityLevel.host_star
                    else EntityLevel.planet_assertion
                )
                if any(
                    candidates_by_id[candidate_id].side
                    is not CrossmatchSide.left
                    or candidates_by_id[candidate_id].entity_level
                    is not record.entity_level
                    for candidate_id in record.left_candidate_ids
                ):
                    raise ValueError("record uses invalid left candidate members")
                if any(
                    candidates_by_id[candidate_id].side
                    is not CrossmatchSide.right
                    or candidates_by_id[candidate_id].entity_level
                    is not expected_right_level
                    for candidate_id in record.right_candidate_ids
                ):
                    raise ValueError("record uses invalid right candidate members")
                if any(
                    item.left_candidate_id not in record.left_candidate_ids
                    or item.right_candidate_id not in record.right_candidate_ids
                    or item.entity_level is not record.entity_level
                    for item in (
                        evidence_by_id[evidence_id]
                        for evidence_id in record.evidence_ids
                    )
                ):
                    raise ValueError("record membership disagrees with Evidence")
            else:
                candidate = candidates_by_id.get(record.candidate_id)
                if candidate is None:
                    raise ValueError(
                        "unpaired record references an unknown candidate"
                    )
                if (
                    candidate.side is not record.side
                    or candidate.entity_level is not record.entity_level
                ):
                    raise ValueError(
                        "unpaired record disagrees with candidate identity"
                    )
        if (
            self.left_source_id != self.left_source_snapshot.source_id
            or self.right_source_id != self.right_source_snapshot.source_id
        ):
            raise ValueError("result source IDs disagree with SourceSnapshot")
        if (
            self.producer_execution.rule_set_id != self.rule_set_id
            or self.producer_execution.rule_set_version != self.rule_set_version
            or self.producer_execution.rule_set_content_hash
            != self.rule_set_content_hash
        ):
            raise ValueError("producer execution disagrees with result RuleSet")
        if self.output_hash != self.content_hash:
            raise ValueError("output_hash must equal the canonical result content_hash")
        expected_result_id = (
            f"crossmatch.{self.content_hash.removeprefix('sha256:')[:24]}"
        )
        if self.result_id != expected_result_id:
            raise ValueError(
                f"result_id does not match content hash: {expected_result_id}"
            )
        _validate_content_hash(self)
        return self


class BenchmarkToiRecord(BaseModel):
    model_config = MODEL_CONFIG

    record_type: Literal["toi"] = "toi"
    toi: NonEmptyString
    tic_id: str | int | None = None
    right_ascension: str | int | float | None = None
    declination: str | int | float | None = None


class BenchmarkPsRecord(BaseModel):
    model_config = MODEL_CONFIG

    record_type: Literal["ps"] = "ps"
    planet_name: NonEmptyString
    reference: NonEmptyString
    tic_id: str | int | None = None
    gaia_dr3_id: str | int | None = None
    hostname: NonEmptyString | None = None
    right_ascension: str | int | float | None = None
    declination: str | int | float | None = None


CrossmatchBenchmarkRecord = Annotated[
    BenchmarkToiRecord | BenchmarkPsRecord,
    Field(discriminator="record_type"),
]


class CrossmatchBenchmarkExpectation(BaseModel):
    model_config = MODEL_CONFIG

    paired_count: int = Field(ge=0)
    conflict_group_count: int = Field(ge=0)
    unmatched_count: int = Field(ge=0)
    inconclusive_count: int = Field(ge=0)
    review_required_count: int = Field(ge=0)
    manual_adjudication_count: int | None = Field(default=None, ge=0)
    planet_assertion_count: int = Field(ge=0)
    methods: tuple[CrossmatchMethod, ...] = ()
    topologies: tuple[MatchTopology, ...] = ()
    conflict_codes: tuple[Identifier, ...] = ()
    expected_error_code: NonEmptyString | None = None


class CrossmatchBenchmarkScenario(BaseModel):
    model_config = MODEL_CONFIG

    scenario_id: Identifier
    description: NonEmptyString
    category: NonEmptyString
    left_completion: DataSourceCompletionStatus
    right_completion: DataSourceCompletionStatus
    left_records: tuple[BenchmarkToiRecord, ...]
    right_records: tuple[BenchmarkPsRecord, ...]
    capacity_override: CrossmatchCapacityPolicy | None = None
    input_fault: Literal[
        "duplicate_record_reference",
        "record_source_mismatch",
    ] | None = None
    manual_adjudication: AdjudicationDecision | None = None
    manual_binding: Literal["valid", "stale_input", "stale_rule"] | None = None
    expectation: CrossmatchBenchmarkExpectation

    @model_validator(mode="after")
    def validate_manual_fixture(self) -> Self:
        if (self.manual_adjudication is None) != (self.manual_binding is None):
            raise ValueError(
                "benchmark manual adjudication and binding must be provided together"
            )
        return self


class CrossmatchBenchmarkManifest(BaseModel):
    model_config = MODEL_CONFIG

    benchmark_id: Identifier
    version: SemanticVersion
    content_hash: ContentHash
    data_level: Literal["synthetic_fixture"]
    provenance_note: NonEmptyString
    rule_set_id: Identifier
    rule_set_version: SemanticVersion
    rule_set_content_hash: ContentHash
    scenarios: tuple[CrossmatchBenchmarkScenario, ...] = Field(min_length=26)
    created_at: date
    maintained_by: NonEmptyString

    @model_validator(mode="after")
    def validate_benchmark(self) -> Self:
        scenario_ids = [scenario.scenario_id for scenario in self.scenarios]
        if len(scenario_ids) != len(set(scenario_ids)):
            raise ValueError("crossmatch benchmark contains duplicate scenario_id")
        _validate_content_hash(self)
        return self


class BenchmarkScenarioStatus(StrEnum):
    passed = "passed"
    failed = "failed"


class CrossmatchBenchmarkScenarioResult(BaseModel):
    model_config = MODEL_CONFIG

    scenario_id: Identifier
    status: BenchmarkScenarioStatus
    result_content_hash: ContentHash | None = None
    observed_error_code: NonEmptyString | None = None
    failure_reason: NonEmptyString | None = None

    @model_validator(mode="after")
    def validate_result(self) -> Self:
        if self.status is BenchmarkScenarioStatus.passed and self.failure_reason:
            raise ValueError("passed benchmark scenario cannot have a failure reason")
        if self.status is BenchmarkScenarioStatus.failed and not self.failure_reason:
            raise ValueError("failed benchmark scenario requires a failure reason")
        return self


class CrossmatchBenchmarkReport(BaseModel):
    model_config = MODEL_CONFIG

    benchmark_id: Identifier
    benchmark_version: SemanticVersion
    benchmark_content_hash: ContentHash
    rule_set_content_hash: ContentHash
    scenario_count: int = Field(ge=0)
    passed_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    results: tuple[CrossmatchBenchmarkScenarioResult, ...]
    content_hash: ContentHash

    @model_validator(mode="after")
    def validate_report(self) -> Self:
        if self.scenario_count != len(self.results):
            raise ValueError("benchmark scenario_count does not match results")
        if self.passed_count + self.failed_count != self.scenario_count:
            raise ValueError("benchmark pass/fail counts do not match scenario_count")
        if self.passed_count != sum(
            result.status is BenchmarkScenarioStatus.passed
            for result in self.results
        ):
            raise ValueError("benchmark passed_count does not match results")
        _validate_content_hash(self)
        return self


def compute_crossmatch_content_hash(
    value: BaseModel | dict[str, Any],
) -> str:
    payload = (
        _drop_none(
            deepcopy(
                value.model_dump(
                    mode="json",
                    exclude_none=True,
                )
            )
        )
        if isinstance(value, BaseModel)
        else _drop_none(deepcopy(value))
    )
    payload.pop("content_hash", None)
    payload.pop("result_id", None)
    payload.pop("output_hash", None)
    return compute_canonical_payload_hash(payload)


def compute_crossmatch_source_input_hash(
    value: CrossmatchInput | dict[str, Any],
) -> str:
    payload = (
        _drop_none(value.model_dump(mode="json", exclude_none=True))
        if isinstance(value, BaseModel)
        else _drop_none(deepcopy(value))
    )
    payload.pop("source_input_hash", None)
    payload.pop("input_hash", None)
    payload.pop("manual_review_decisions", None)
    for side in ("left", "right"):
        source = payload.get(side)
        if not isinstance(source, dict):
            continue
        records = source.get("records")
        if isinstance(records, list):
            source["records"] = sorted(
                records,
                key=lambda record: (
                    record.get("source_id"),
                    record.get("row_key"),
                    record.get("content_hash"),
                ),
            )
    return compute_canonical_payload_hash(payload)


def compute_crossmatch_input_hash(
    value: CrossmatchInput | dict[str, Any],
) -> str:
    payload = (
        _drop_none(value.model_dump(mode="json", exclude_none=True))
        if isinstance(value, BaseModel)
        else _drop_none(deepcopy(value))
    )
    source_input_hash = payload.get("source_input_hash")
    if not isinstance(source_input_hash, str):
        source_input_hash = compute_crossmatch_source_input_hash(payload)
    decisions = payload.get("manual_review_decisions", [])
    decision_hashes = sorted(
        decision["content_hash"]
        for decision in decisions
        if isinstance(decision, dict) and isinstance(decision.get("content_hash"), str)
    )
    return compute_canonical_payload_hash(
        {
            "source_input_hash": source_input_hash,
            "manual_review_decision_hashes": decision_hashes,
        }
    )


def _drop_none(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _drop_none(nested)
            for key, nested in value.items()
            if nested is not None
        }
    if isinstance(value, (list, tuple)):
        return [_drop_none(nested) for nested in value]
    return value


def _validate_content_hash(value: BaseModel) -> None:
    expected = compute_crossmatch_content_hash(value)
    if getattr(value, "content_hash") != expected:
        raise ValueError(f"content_hash does not match canonical payload: {expected}")
