"""D-07 LiteratureClaim extraction, admission, and benchmark contracts."""

from __future__ import annotations

from copy import deepcopy
from enum import StrEnum
from typing import Any, ClassVar, Literal, Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    Field,
    PrivateAttr,
    model_validator,
)

from ._hashing import compute_canonical_payload_hash
from .enums import ClaimType
from .manifest import ContentHash, Identifier, SemanticVersion
from .paper_summary import (
    MODEL_CONFIG,
    NonEmptyString,
    PaperSummaryEvidence,
    PaperSummarySourceSnapshotReference,
    ShortString,
)


_ARTIFACT_PUBLICATION_SEAL = object()


class LiteratureClaimStatus(StrEnum):
    candidate = "candidate"
    accepted = "accepted"
    rejected = "rejected"


class LiteratureClaimFailureStage(StrEnum):
    json = "json"
    schema = "schema"
    input = "input"
    evidence = "evidence"
    ownership = "ownership"
    normalization = "normalization"
    duplicate = "duplicate"


class LiteratureClaimRejectionReason(StrEnum):
    invalid_json = "literature_claim.json_invalid"
    schema_invalid = "literature_claim.schema_invalid"
    input_artifact_version_unknown = (
        "literature_claim.input_artifact_version_unknown"
    )
    input_schema_version_unsupported = (
        "literature_claim.input_schema_version_unsupported"
    )
    evidence_missing = "literature_claim.evidence_missing"
    evidence_not_found = "literature_claim.evidence_not_found"
    source_snapshot_not_found = "literature_claim.source_snapshot_not_found"
    ownership_mismatch = "literature_claim.ownership_mismatch"
    normalization_unsafe = "literature_claim.normalization_unsafe"
    duplicate_claim = "literature_claim.duplicate"


class LiteratureClaimPolarity(StrEnum):
    positive = "positive"
    negative = "negative"
    neutral = "neutral"
    mixed = "mixed"


class LiteratureClaimBenchmarkCaseKind(StrEnum):
    scientific_label = "scientific_label"
    rejection_case = "rejection_case"


class LiteratureClaimInputVersions(BaseModel):
    """Trace retained even when the requested Summary version cannot be resolved."""

    model_config = MODEL_CONFIG

    paper_summary_artifact_version_id: Identifier
    paper_summary_schema_version: SemanticVersion | None = None
    paper_summary_output_hash: ContentHash | None = None
    summary_id: Identifier | None = None
    paper_id: Identifier
    source_snapshots: tuple[PaperSummarySourceSnapshotReference, ...]

    @model_validator(mode="after")
    def validate_references(self) -> Self:
        _require_unique(
            tuple(item.source_snapshot_id for item in self.source_snapshots),
            "input SourceSnapshot version",
        )
        resolved = (
            self.paper_summary_schema_version,
            self.paper_summary_output_hash,
            self.summary_id,
        )
        if any(item is None for item in resolved) and any(
            item is not None for item in resolved
        ):
            raise ValueError("resolved PaperSummary version fields must be all-or-none")
        if self.summary_id is None and self.source_snapshots:
            raise ValueError("unresolved PaperSummary cannot declare SourceSnapshots")
        return self


class LiteratureClaimModelCandidate(BaseModel):
    """One strict model-produced Claim before provenance admission."""

    model_config = MODEL_CONFIG
    __artifact_publication_requires_admission__: ClassVar[bool] = True

    source_statement_id: Identifier
    text: NonEmptyString
    normalized_text: NonEmptyString
    claim_type: ClaimType
    polarity: LiteratureClaimPolarity
    objects: tuple[ShortString, ...] = Field(min_length=1)
    metric: ShortString | None
    unit: ShortString | None
    conditions: tuple[NonEmptyString, ...]
    scope: tuple[NonEmptyString, ...]
    limitations: tuple[NonEmptyString, ...]
    qualifiers: tuple[NonEmptyString, ...]
    uncertainty: ShortString | None
    comparison_basis: ShortString | None
    evidence_ids: tuple[Identifier, ...]

    @model_validator(mode="after")
    def validate_structure(self) -> Self:
        for values, label in (
            (self.objects, "Claim object"),
            (self.conditions, "Claim condition"),
            (self.scope, "Claim scope"),
            (self.limitations, "Claim limitation"),
            (self.qualifiers, "Claim qualifier"),
            (self.evidence_ids, "Claim Evidence id"),
        ):
            _require_unique(values, label)
        if self.unit is not None and self.metric is None:
            raise ValueError("Claim unit requires a metric")
        return self


class LiteratureClaimExtractionOutput(BaseModel):
    """The complete JSON shape accepted before D-07 admission."""

    model_config = MODEL_CONFIG
    __artifact_publication_requires_admission__: ClassVar[bool] = True

    schema_version: Literal["1.0.0"]
    claims: tuple[LiteratureClaimModelCandidate, ...] = Field(min_length=1)


class LiteratureClaimEvidenceReference(BaseModel):
    model_config = MODEL_CONFIG

    claim_id: Identifier
    evidence_id: Identifier
    summary_statement_id: Identifier
    paper_id: Identifier
    source_snapshot_id: Identifier
    source_snapshot_version: ShortString
    source_snapshot_content_hash: ContentHash
    status: Literal["supported", "unsupported", "unverifiable"]
    validation_code: Identifier


class LiteratureClaimCandidate(BaseModel):
    """Schema-valid Claim with the outcome of deterministic D-07 admission."""

    model_config = MODEL_CONFIG
    __artifact_publication_requires_admission__: ClassVar[bool] = True

    claim_id: Identifier
    source_statement_id: Identifier
    paper_id: Identifier
    source_paper_summary_artifact_version_id: Identifier
    source_summary_id: Identifier | None = None
    text: NonEmptyString
    normalized_text: NonEmptyString
    claim_type: ClaimType
    polarity: LiteratureClaimPolarity
    objects: tuple[ShortString, ...] = Field(min_length=1)
    metric: ShortString | None = None
    unit: ShortString | None = None
    conditions: tuple[NonEmptyString, ...]
    scope: tuple[NonEmptyString, ...]
    limitations: tuple[NonEmptyString, ...]
    qualifiers: tuple[NonEmptyString, ...]
    uncertainty: ShortString | None = None
    comparison_basis: ShortString | None = None
    evidence_ids: tuple[Identifier, ...]
    source_snapshot_ids: tuple[Identifier, ...]
    normalization_version: SemanticVersion
    fingerprint: ContentHash
    status: LiteratureClaimStatus
    failure_stage: LiteratureClaimFailureStage | None = None
    rejection_reason: LiteratureClaimRejectionReason | None = None
    producer_execution_id: Identifier
    input_hash: ContentHash
    model_response_hash: ContentHash

    @model_validator(mode="after")
    def validate_admission_state(self) -> Self:
        for values, label in (
            (self.objects, "Claim object"),
            (self.conditions, "Claim condition"),
            (self.scope, "Claim scope"),
            (self.limitations, "Claim limitation"),
            (self.qualifiers, "Claim qualifier"),
            (self.evidence_ids, "Claim Evidence id"),
            (self.source_snapshot_ids, "Claim SourceSnapshot id"),
        ):
            _require_unique(values, label)
        if self.status is LiteratureClaimStatus.rejected:
            if self.failure_stage is None or self.rejection_reason is None:
                raise ValueError("rejected Claim requires stage and rejection reason")
        elif self.failure_stage is not None or self.rejection_reason is not None:
            raise ValueError("non-rejected Claim cannot declare rejection metadata")
        if self.status is LiteratureClaimStatus.accepted and (
            not self.evidence_ids
            or not self.source_snapshot_ids
            or self.source_summary_id is None
        ):
            raise ValueError(
                "accepted Claim requires Summary, Evidence, and SourceSnapshot"
            )
        if (
            self.status is LiteratureClaimStatus.candidate
            and self.source_summary_id is None
        ):
            raise ValueError("candidate Claim requires resolved PaperSummary")
        expected = compute_literature_claim_fingerprint(self)
        if self.fingerprint != expected:
            raise ValueError(f"fingerprint does not match LiteratureClaim: {expected}")
        return self


class LiteratureClaimProducerExecution(BaseModel):
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
    input_versions: LiteratureClaimInputVersions
    input_hash: ContentHash
    model_response_hash: ContentHash
    output_hash: ContentHash
    status: Literal["completed", "rejected"]
    started_at: AwareDatetime
    finished_at: AwareDatetime
    latency_ms: int = Field(ge=0)
    error_code: LiteratureClaimRejectionReason | None = None

    @model_validator(mode="after")
    def validate_terminal_state(self) -> Self:
        if self.status == "completed" and self.error_code is not None:
            raise ValueError("completed Claim execution cannot declare error_code")
        if self.status == "rejected" and self.error_code not in {
            LiteratureClaimRejectionReason.invalid_json,
            LiteratureClaimRejectionReason.schema_invalid,
        }:
            raise ValueError("rejected Claim execution requires JSON/Schema error_code")
        return self


class LiteratureClaimStatusCounts(BaseModel):
    model_config = MODEL_CONFIG

    accepted: int = Field(ge=0)
    candidate: int = Field(ge=0)
    rejected: int = Field(ge=0)


class LiteratureClaimsCandidate(BaseModel):
    """Publisher-ready typed candidate produced only by the D-07 pipeline."""

    model_config = MODEL_CONFIG
    __artifact_publication_requires_admission__: ClassVar[bool] = True
    _artifact_publication_seal: tuple[object, int] | None = PrivateAttr(default=None)

    kind: Literal["literature_claims"] = "literature_claims"
    schema_version: Literal["1.0.0"] = "1.0.0"
    input_versions: LiteratureClaimInputVersions
    claims: tuple[LiteratureClaimCandidate, ...] = Field(min_length=1)
    evidence: tuple[PaperSummaryEvidence, ...]
    evidence_references: tuple[LiteratureClaimEvidenceReference, ...]
    evidence_ids: tuple[Identifier, ...]
    source_snapshot_ids: tuple[Identifier, ...]
    status_counts: LiteratureClaimStatusCounts
    producer: LiteratureClaimProducerExecution
    input_hash: ContentHash
    output_hash: ContentHash

    @model_validator(mode="after")
    def validate_candidate_integrity(self) -> Self:
        _require_unique(
            tuple(item.claim_id for item in self.claims),
            "LiteratureClaim id",
        )
        _require_unique(
            tuple(item.evidence_id for item in self.evidence),
            "LiteratureClaim Evidence",
        )
        _require_unique(
            tuple(
                (item.claim_id, item.evidence_id)
                for item in self.evidence_references
            ),
            "LiteratureClaim Evidence reference",
        )
        expected_evidence_ids = tuple(
            sorted({item.evidence_id for item in self.evidence_references})
        )
        if self.evidence_ids != expected_evidence_ids:
            raise ValueError("evidence_ids must equal admitted Evidence references")
        expected_snapshot_ids = tuple(
            sorted({item.source_snapshot_id for item in self.evidence_references})
        )
        if self.source_snapshot_ids != expected_snapshot_ids:
            raise ValueError(
                "source_snapshot_ids must equal admitted Evidence SourceSnapshots"
            )
        claims_by_id = {item.claim_id: item for item in self.claims}
        evidence_by_id = {item.evidence_id: item for item in self.evidence}
        references_by_claim: dict[
            str, list[LiteratureClaimEvidenceReference]
        ] = {}
        for reference in self.evidence_references:
            claim = claims_by_id.get(reference.claim_id)
            evidence = evidence_by_id.get(reference.evidence_id)
            if claim is None or evidence is None:
                raise ValueError(
                    "Evidence reference must identify retained Claim and Evidence"
                )
            if (
                reference.summary_statement_id != claim.source_statement_id
                or reference.evidence_id not in claim.evidence_ids
                or reference.paper_id != claim.paper_id
                or evidence.paper_id != claim.paper_id
                or reference.source_snapshot_id != evidence.source_snapshot_id
                or reference.source_snapshot_version
                != evidence.source_snapshot_version
                or reference.source_snapshot_content_hash
                != evidence.source_snapshot_content_hash
                or reference.status != evidence.status
                or reference.validation_code != evidence.validation_code
            ):
                raise ValueError(
                    "Evidence reference provenance does not match Claim/Evidence"
                )
            references_by_claim.setdefault(reference.claim_id, []).append(reference)
        for claim in self.claims:
            if claim.status is LiteratureClaimStatus.rejected:
                continue
            claim_references = references_by_claim.get(claim.claim_id, [])
            if tuple(sorted(item.evidence_id for item in claim_references)) != (
                claim.evidence_ids
            ):
                raise ValueError(
                    "publishable Claim requires all declared Evidence references"
                )
            if tuple(
                sorted({item.source_snapshot_id for item in claim_references})
            ) != claim.source_snapshot_ids:
                raise ValueError(
                    "publishable Claim SourceSnapshots must match Evidence references"
                )
        counts = LiteratureClaimStatusCounts(
            accepted=sum(
                item.status is LiteratureClaimStatus.accepted for item in self.claims
            ),
            candidate=sum(
                item.status is LiteratureClaimStatus.candidate for item in self.claims
            ),
            rejected=sum(
                item.status is LiteratureClaimStatus.rejected for item in self.claims
            ),
        )
        if self.status_counts != counts:
            raise ValueError("status_counts do not match LiteratureClaims")
        if self.input_hash != self.producer.input_hash:
            raise ValueError("ProducerExecution input_hash does not match candidate")
        if self.input_versions != self.producer.input_versions:
            raise ValueError("ProducerExecution input versions do not match candidate")
        for claim in self.claims:
            if (
                claim.paper_id != self.input_versions.paper_id
                or claim.source_paper_summary_artifact_version_id
                != self.input_versions.paper_summary_artifact_version_id
                or claim.source_summary_id != self.input_versions.summary_id
                or claim.producer_execution_id != self.producer.execution_id
                or claim.input_hash != self.input_hash
                or claim.model_response_hash != self.producer.model_response_hash
            ):
                raise ValueError("LiteratureClaim provenance does not match candidate")
        expected_output_hash = compute_literature_claims_output_hash(self)
        if self.output_hash != expected_output_hash:
            raise ValueError(
                f"output_hash does not match LiteratureClaims: {expected_output_hash}"
            )
        if self.producer.output_hash != expected_output_hash:
            raise ValueError("ProducerExecution output_hash does not match candidate")
        return self

    def __artifact_publication_is_admitted__(self) -> bool:
        seal = self._artifact_publication_seal
        return (
            isinstance(seal, tuple)
            and len(seal) == 2
            and seal[0] is _ARTIFACT_PUBLICATION_SEAL
            and seal[1] == id(self)
        )


class LiteratureClaimAdmissionResult(BaseModel):
    model_config = MODEL_CONFIG
    __artifact_publication_requires_admission__: ClassVar[bool] = True

    admission_status: LiteratureClaimStatus
    failure_stage: LiteratureClaimFailureStage | None = None
    rejection_reason: LiteratureClaimRejectionReason | None = None
    records: tuple[LiteratureClaimCandidate, ...]
    publisher_candidate: LiteratureClaimsCandidate | None = None
    producer: LiteratureClaimProducerExecution
    output_hash: ContentHash

    @model_validator(mode="after")
    def validate_result(self) -> Self:
        if self.admission_status is LiteratureClaimStatus.rejected and not self.records:
            if self.failure_stage not in {
                LiteratureClaimFailureStage.json,
                LiteratureClaimFailureStage.schema,
            }:
                raise ValueError("empty rejected result requires JSON/Schema stage")
            if self.rejection_reason is None:
                raise ValueError("empty rejected result requires rejection reason")
        elif self.failure_stage is not None or self.rejection_reason is not None:
            raise ValueError("record-level outcomes cannot declare top-level failure")

        expected_status = _aggregate_status(self.records)
        if self.records and self.admission_status is not expected_status:
            raise ValueError("admission_status does not match Claim records")
        has_publishable = any(
            item.status is not LiteratureClaimStatus.rejected for item in self.records
        )
        if has_publishable != (self.publisher_candidate is not None):
            raise ValueError(
                "publisher candidate is required exactly when a Claim is publishable"
            )
        if self.publisher_candidate is not None:
            if (
                self.publisher_candidate.claims != self.records
                or self.publisher_candidate.producer != self.producer
                or self.publisher_candidate.output_hash != self.output_hash
            ):
                raise ValueError("publisher candidate does not match admission result")
        else:
            expected_hash = compute_literature_claim_admission_output_hash(self)
            if self.output_hash != expected_hash:
                raise ValueError(
                    f"output_hash does not match Claim admission: {expected_hash}"
                )
        if self.producer.output_hash != self.output_hash:
            raise ValueError("ProducerExecution output_hash does not match result")
        return self


class LiteratureClaimBenchmarkEvaluationCase(BaseModel):
    model_config = MODEL_CONFIG

    case_id: Identifier
    case_kind: LiteratureClaimBenchmarkCaseKind
    benchmark_claim_id: Identifier | None = None
    record_claim_id: Identifier | None = None
    expected_failure_stage: LiteratureClaimFailureStage | None = None
    expected_rejection_reason: LiteratureClaimRejectionReason | None = None
    admission: LiteratureClaimAdmissionResult

    @model_validator(mode="after")
    def validate_expectation(self) -> Self:
        if self.case_kind is LiteratureClaimBenchmarkCaseKind.scientific_label:
            if self.benchmark_claim_id is None:
                raise ValueError("scientific benchmark case requires a D-01 Claim id")
            if (
                self.expected_failure_stage is not None
                or self.expected_rejection_reason is not None
            ):
                raise ValueError(
                    "scientific benchmark case cannot declare rejection expectations"
                )
        else:
            if self.benchmark_claim_id is not None:
                raise ValueError(
                    "rejection benchmark case cannot consume a scientific label"
                )
            if (
                self.expected_failure_stage is None
                or self.expected_rejection_reason is None
            ):
                raise ValueError(
                    "rejection benchmark case requires expected stage and reason"
                )
        return self


class LiteratureClaimBenchmarkCaseResult(BaseModel):
    model_config = MODEL_CONFIG

    case_id: Identifier
    case_kind: LiteratureClaimBenchmarkCaseKind
    benchmark_claim_id: Identifier | None = None
    claim_type: ClaimType | None = None
    expected_failure_stage: LiteratureClaimFailureStage | None = None
    expected_rejection_reason: LiteratureClaimRejectionReason | None = None
    schema_valid: bool
    evidence_items_supported: int = Field(ge=0)
    evidence_items_total: int = Field(ge=0)
    scientific_label_compared: bool
    scientific_label_exact_match: bool | None = None
    rejection_case_pass: bool | None = None
    status: LiteratureClaimStatus
    failure_stage: LiteratureClaimFailureStage | None = None
    rejection_reason: LiteratureClaimRejectionReason | None = None
    input_hash: ContentHash
    output_hash: ContentHash

    @model_validator(mode="after")
    def validate_outcome(self) -> Self:
        if self.status is LiteratureClaimStatus.rejected:
            if self.failure_stage is None or self.rejection_reason is None:
                raise ValueError(
                    "rejected benchmark case requires failure stage and reason"
                )
        elif self.failure_stage is not None or self.rejection_reason is not None:
            raise ValueError(
                "non-rejected benchmark case cannot have rejection metadata"
            )
        if self.evidence_items_supported > self.evidence_items_total:
            raise ValueError("case Evidence numerator cannot exceed denominator")
        if self.case_kind is LiteratureClaimBenchmarkCaseKind.scientific_label:
            if self.benchmark_claim_id is None or self.claim_type is None:
                raise ValueError(
                    "scientific result requires a D-01 Claim id and Claim type"
                )
            if (
                self.expected_failure_stage is not None
                or self.expected_rejection_reason is not None
                or self.rejection_case_pass is not None
            ):
                raise ValueError(
                    "scientific result cannot declare rejection expectations"
                )
            if self.scientific_label_compared != (
                self.scientific_label_exact_match is not None
            ):
                raise ValueError(
                    "scientific comparison flag must match exact-match applicability"
                )
        else:
            if (
                self.benchmark_claim_id is not None
                or self.claim_type is not None
                or self.expected_failure_stage is None
                or self.expected_rejection_reason is None
                or self.rejection_case_pass is None
                or self.scientific_label_compared
                or self.scientific_label_exact_match is not None
            ):
                raise ValueError(
                    "rejection result must contain only its expected rejection outcome"
                )
        return self


class LiteratureClaimTypeCount(BaseModel):
    model_config = MODEL_CONFIG

    claim_type: ClaimType
    count: int = Field(ge=0)


class LiteratureClaimRejectionCount(BaseModel):
    model_config = MODEL_CONFIG

    rejection_reason: LiteratureClaimRejectionReason
    count: int = Field(ge=1)
    sample_case_ids: tuple[Identifier, ...] = Field(min_length=1)


class LiteratureClaimBenchmarkReport(BaseModel):
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
    claim_schema_version: Literal["1.0.0"]
    model_name: ShortString
    parameters_version: SemanticVersion
    parameters_hash: ContentHash
    producer_version: SemanticVersion
    sample_count: int = Field(ge=0)
    claim_type_counts: tuple[LiteratureClaimTypeCount, ...]
    schema_items_valid: int = Field(ge=0)
    schema_items_total: int = Field(ge=0)
    schema_pass_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    rejection_cases_passed: int = Field(ge=0)
    rejection_cases_total: int = Field(ge=0)
    rejection_case_pass_rate: float | None = Field(
        default=None, ge=0.0, le=1.0
    )
    evidence_items_supported: int = Field(ge=0)
    evidence_items_total: int = Field(ge=0)
    evidence_coverage_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    scientific_label_items_exact: int = Field(ge=0)
    scientific_label_items_total: int = Field(ge=0)
    scientific_label_exact_match_rate: float | None = Field(
        default=None, ge=0.0, le=1.0
    )
    status_counts: LiteratureClaimStatusCounts
    rejection_counts: tuple[LiteratureClaimRejectionCount, ...]
    cases: tuple[LiteratureClaimBenchmarkCaseResult, ...]
    input_hash: ContentHash
    output_hash: ContentHash

    @model_validator(mode="after")
    def validate_report(self) -> Self:
        _require_unique(tuple(item.case_id for item in self.cases), "benchmark case id")
        _require_unique(
            tuple(item.claim_type for item in self.claim_type_counts),
            "benchmark Claim type count",
        )
        _require_unique(
            tuple(item.rejection_reason for item in self.rejection_counts),
            "benchmark rejection count",
        )
        if self.sample_count != len(self.cases):
            raise ValueError("sample_count must equal benchmark case count")
        if self.schema_items_valid > self.schema_items_total:
            raise ValueError("schema numerator cannot exceed denominator")
        if self.evidence_items_supported > self.evidence_items_total:
            raise ValueError("Evidence numerator cannot exceed denominator")
        if self.rejection_cases_passed > self.rejection_cases_total:
            raise ValueError("rejection numerator cannot exceed denominator")
        if self.scientific_label_items_exact > self.scientific_label_items_total:
            raise ValueError("scientific label numerator cannot exceed denominator")
        if tuple(item.case_id for item in self.cases) != tuple(
            sorted(item.case_id for item in self.cases)
        ):
            raise ValueError("benchmark cases must use stable case_id order")
        if tuple(item.claim_type.value for item in self.claim_type_counts) != tuple(
            sorted(item.claim_type.value for item in self.claim_type_counts)
        ):
            raise ValueError("Claim type counts must use stable enum order")
        if tuple(
            item.rejection_reason.value for item in self.rejection_counts
        ) != tuple(
            sorted(item.rejection_reason.value for item in self.rejection_counts)
        ):
            raise ValueError("rejection counts must use stable enum order")
        if (
            sum(item.count for item in self.claim_type_counts)
            != self.scientific_label_items_total
        ):
            raise ValueError(
                "Claim type counts must equal compared scientific label count"
            )
        if (
            self.status_counts.accepted
            + self.status_counts.candidate
            + self.status_counts.rejected
            != self.sample_count
        ):
            raise ValueError("status_counts must equal sample_count")
        if self.schema_items_total != self.sample_count:
            raise ValueError("schema denominator must equal sample_count")
        expected_schema_rate = (
            self.schema_items_valid / self.schema_items_total
            if self.schema_items_total
            else None
        )
        if self.schema_pass_rate != expected_schema_rate:
            raise ValueError("schema_pass_rate does not match counts")
        expected_rejection_rate = (
            self.rejection_cases_passed / self.rejection_cases_total
            if self.rejection_cases_total
            else None
        )
        if self.rejection_case_pass_rate != expected_rejection_rate:
            raise ValueError("rejection_case_pass_rate does not match counts")
        expected_evidence_coverage_rate = (
            self.evidence_items_supported / self.evidence_items_total
            if self.evidence_items_total
            else None
        )
        if self.evidence_coverage_rate != expected_evidence_coverage_rate:
            raise ValueError("evidence_coverage_rate does not match counts")
        expected_scientific_rate = (
            self.scientific_label_items_exact / self.scientific_label_items_total
            if self.scientific_label_items_total
            else None
        )
        if self.scientific_label_exact_match_rate != expected_scientific_rate:
            raise ValueError(
                "scientific_label_exact_match_rate does not match counts"
            )
        expected_schema_valid = sum(item.schema_valid for item in self.cases)
        expected_rejection_total = sum(
            item.case_kind is LiteratureClaimBenchmarkCaseKind.rejection_case
            for item in self.cases
        )
        expected_rejection_passed = sum(
            item.rejection_case_pass is True for item in self.cases
        )
        expected_scientific_total = sum(
            item.scientific_label_compared for item in self.cases
        )
        expected_scientific_exact = sum(
            item.scientific_label_exact_match is True for item in self.cases
        )
        expected_evidence_supported = sum(
            item.evidence_items_supported for item in self.cases
        )
        expected_evidence_total = sum(item.evidence_items_total for item in self.cases)
        if (
            self.schema_items_valid != expected_schema_valid
            or self.rejection_cases_total != expected_rejection_total
            or self.rejection_cases_passed != expected_rejection_passed
            or self.scientific_label_items_total != expected_scientific_total
            or self.scientific_label_items_exact != expected_scientific_exact
            or self.evidence_items_supported != expected_evidence_supported
            or self.evidence_items_total != expected_evidence_total
        ):
            raise ValueError("benchmark metric counts do not match case results")
        expected_status_counts = LiteratureClaimStatusCounts(
            accepted=sum(
                item.status is LiteratureClaimStatus.accepted for item in self.cases
            ),
            candidate=sum(
                item.status is LiteratureClaimStatus.candidate for item in self.cases
            ),
            rejected=sum(
                item.status is LiteratureClaimStatus.rejected for item in self.cases
            ),
        )
        if self.status_counts != expected_status_counts:
            raise ValueError("status_counts do not match case results")
        expected_type_counts: dict[ClaimType, int] = {}
        for item in self.cases:
            if not item.scientific_label_compared or item.claim_type is None:
                continue
            expected_type_counts[item.claim_type] = (
                expected_type_counts.get(item.claim_type, 0) + 1
            )
        if {
            item.claim_type: item.count for item in self.claim_type_counts
        } != expected_type_counts:
            raise ValueError("Claim type counts do not match scientific cases")
        for item in self.rejection_counts:
            if (
                item.count != len(item.sample_case_ids)
                or item.sample_case_ids != tuple(sorted(item.sample_case_ids))
                or len(item.sample_case_ids) != len(set(item.sample_case_ids))
            ):
                raise ValueError(
                    "rejection samples must be unique, sorted, and match count"
                )
        expected_rejection_samples: dict[
            LiteratureClaimRejectionReason, tuple[str, ...]
        ] = {}
        for reason in LiteratureClaimRejectionReason:
            case_ids = tuple(
                sorted(
                    item.case_id
                    for item in self.cases
                    if item.rejection_reason is reason
                )
            )
            if case_ids:
                expected_rejection_samples[reason] = case_ids
        actual_rejection_samples = {
            item.rejection_reason: item.sample_case_ids
            for item in self.rejection_counts
        }
        if actual_rejection_samples != expected_rejection_samples:
            raise ValueError("rejection counts do not match case results")
        expected_hash = compute_literature_claim_benchmark_output_hash(self)
        if self.output_hash != expected_hash:
            raise ValueError(
                f"output_hash does not match Claim benchmark: {expected_hash}"
            )
        return self


def compute_literature_claim_fingerprint(
    value: LiteratureClaimCandidate | dict[str, Any],
) -> str:
    payload = _model_or_dict(value)
    fields = {
        key: payload.get(key)
        for key in (
            "text",
            "normalized_text",
            "claim_type",
            "polarity",
            "objects",
            "metric",
            "unit",
            "conditions",
            "scope",
            "limitations",
            "qualifiers",
            "uncertainty",
            "comparison_basis",
        )
    }
    for field in ("objects", "conditions", "scope", "limitations", "qualifiers"):
        values = fields.get(field)
        if isinstance(values, list):
            fields[field] = sorted(values, key=str.casefold)
    return compute_canonical_payload_hash(fields)


def compute_literature_claims_output_hash(
    value: LiteratureClaimsCandidate | dict[str, Any],
) -> str:
    payload = _model_or_dict(value)
    payload.pop("output_hash", None)
    _drop_execution_runtime(payload.get("producer"))
    _drop_claim_execution_runtime(payload)
    return compute_canonical_payload_hash(payload)


def compute_literature_claim_admission_output_hash(
    value: LiteratureClaimAdmissionResult | dict[str, Any],
) -> str:
    payload = _model_or_dict(value)
    payload.pop("output_hash", None)
    _drop_execution_runtime(payload.get("producer"))
    _drop_claim_execution_runtime(payload)
    return compute_canonical_payload_hash(payload)


def compute_literature_claim_benchmark_output_hash(
    value: LiteratureClaimBenchmarkReport | dict[str, Any],
) -> str:
    payload = _model_or_dict(value)
    payload.pop("output_hash", None)
    return compute_canonical_payload_hash(payload)


def _seal_literature_claims_for_publication(
    value: LiteratureClaimsCandidate,
) -> LiteratureClaimsCandidate:
    object.__setattr__(
        value,
        "_artifact_publication_seal",
        (_ARTIFACT_PUBLICATION_SEAL, id(value)),
    )
    return value


def _aggregate_status(
    records: tuple[LiteratureClaimCandidate, ...],
) -> LiteratureClaimStatus:
    if any(item.status is LiteratureClaimStatus.accepted for item in records):
        return LiteratureClaimStatus.accepted
    if any(item.status is LiteratureClaimStatus.candidate for item in records):
        return LiteratureClaimStatus.candidate
    return LiteratureClaimStatus.rejected


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
    if isinstance(value, list):
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


def _drop_claim_execution_runtime(payload: dict[str, Any]) -> None:
    for field in ("claims", "records"):
        records = payload.get(field)
        if not isinstance(records, list):
            continue
        for record in records:
            if isinstance(record, dict):
                record.pop("producer_execution_id", None)
    publisher_candidate = payload.get("publisher_candidate")
    if isinstance(publisher_candidate, dict):
        _drop_execution_runtime(publisher_candidate.get("producer"))
        _drop_claim_execution_runtime(publisher_candidate)


def _require_unique(values: tuple[Any, ...], label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"duplicate {label}")
