"""Deterministically derive the formal LiteratureRelation Pipeline suite from frozen Paper Acquisition Benchmark labels."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, time, timezone
import json
from typing import Any

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.literature_claim import LiteratureClaimCandidate
from app.schemas.literature_relation import (
    LiteratureComparabilityStatus,
    LiteratureRelationAdmissionResult,
    LiteratureRelationBenchmarkCaseKind,
    LiteratureRelationBenchmarkEvaluationCase,
    LiteratureRelationConfidenceAssessment,
    LiteratureRelationConfidenceStatus,
    LiteratureRelationFailureStage,
    LiteratureRelationRejectionReason,
    LiteratureRelationStatus,
    LiteratureTraceOperation,
    build_literature_relation_confidence_subject,
)
from app.schemas.paper_benchmark import (
    BenchmarkPackage,
    BenchmarkReasoningTrace,
    BenchmarkRelation,
    BenchmarkReviewStatus,
)

from .benchmark import validate_frozen_benchmark
from .claim_benchmark_cases import build_frozen_claim_benchmark_cases
from .constants import (
    RELATION_CONFIDENCE_ACCEPTANCE_THRESHOLD,
    RELATION_CONFIDENCE_APPLICABILITY_SCOPE,
    RELATION_CONFIDENCE_CALIBRATION_ID,
    RELATION_CONFIDENCE_CALIBRATION_METHOD,
    RELATION_CONFIDENCE_CALIBRATION_VERSION,
    RELATION_CONFIDENCE_DEFINITION_ID,
    RELATION_CONFIDENCE_DEFINITION_VERSION,
)
from .relation import (
    RELATION_CONFIDENCE_CALIBRATION_SAMPLE_SIZE,
    LiteratureClaimsArtifactVersionInput,
    LiteratureRelationPipeline,
)


_PROJECT_ID = "project.literature_relation_benchmark"
_REPLAY_MODEL_NAME = "paper_benchmark-approved-label-replay"
_REPLAY_PARAMETERS: dict[str, str | int] = {
    "temperature": 0,
    "max_output_tokens": 4096,
    "response_format": "json_schema",
}
_MISSING_CLAIM_VERSION_ID = "artifact_version.literature_claim.missing"
_MISSING_CLAIM_ID = "claim.literature_claim.missing"
_MISSING_SUMMARY_VERSION_ID = "artifact_version.paper_summary.missing"
FORMAL_REJECTION_EXPECTATIONS: tuple[
    tuple[
        str,
        LiteratureRelationFailureStage,
        LiteratureRelationRejectionReason,
    ],
    ...,
] = tuple(
    sorted(
        (
            (
                "rejection.claim_not_found",
                LiteratureRelationFailureStage.claim,
                LiteratureRelationRejectionReason.claim_not_found,
            ),
            (
                "rejection.condition_conflict",
                LiteratureRelationFailureStage.conditions,
                LiteratureRelationRejectionReason.conditions_conflict,
            ),
            (
                "rejection.confidence_decision_mismatch",
                LiteratureRelationFailureStage.confidence,
                LiteratureRelationRejectionReason.confidence_decision_mismatch,
            ),
            (
                "rejection.confidence_subject_mismatch",
                LiteratureRelationFailureStage.confidence,
                LiteratureRelationRejectionReason.confidence_subject_mismatch,
            ),
            (
                "rejection.direction_mismatch",
                LiteratureRelationFailureStage.direction,
                LiteratureRelationRejectionReason.direction_mismatch,
            ),
            (
                "rejection.duplicate_relation",
                LiteratureRelationFailureStage.duplicate,
                LiteratureRelationRejectionReason.duplicate_relation,
            ),
            (
                "rejection.evidence_inconsistent",
                LiteratureRelationFailureStage.evidence,
                LiteratureRelationRejectionReason.evidence_inconsistent,
            ),
            (
                "rejection.evidence_missing",
                LiteratureRelationFailureStage.evidence,
                LiteratureRelationRejectionReason.evidence_missing,
            ),
            (
                "rejection.input_artifact_version_unknown",
                LiteratureRelationFailureStage.input,
                LiteratureRelationRejectionReason.input_artifact_version_unknown,
            ),
            (
                "rejection.invalid_json",
                LiteratureRelationFailureStage.json,
                LiteratureRelationRejectionReason.invalid_json,
            ),
            (
                "rejection.metric_incomparable",
                LiteratureRelationFailureStage.comparability,
                LiteratureRelationRejectionReason.metric_incomparable,
            ),
            (
                "rejection.multiple_failures_json_first",
                LiteratureRelationFailureStage.json,
                LiteratureRelationRejectionReason.invalid_json,
            ),
            (
                "rejection.object_incomparable",
                LiteratureRelationFailureStage.comparability,
                LiteratureRelationRejectionReason.object_incomparable,
            ),
            (
                "rejection.ownership_mismatch",
                LiteratureRelationFailureStage.ownership,
                LiteratureRelationRejectionReason.ownership_mismatch,
            ),
            (
                "rejection.paper_summary_artifact_version_unknown",
                LiteratureRelationFailureStage.claim,
                LiteratureRelationRejectionReason.paper_summary_artifact_version_unknown,
            ),
            (
                "rejection.schema_invalid",
                LiteratureRelationFailureStage.schema,
                LiteratureRelationRejectionReason.schema_invalid,
            ),
            (
                "rejection.trace_evidence_incomplete",
                LiteratureRelationFailureStage.trace,
                LiteratureRelationRejectionReason.trace_evidence_incomplete,
            ),
            (
                "rejection.trace_incomplete",
                LiteratureRelationFailureStage.trace,
                LiteratureRelationRejectionReason.trace_incomplete,
            ),
            (
                "rejection.trace_unsafe",
                LiteratureRelationFailureStage.trace,
                LiteratureRelationRejectionReason.trace_unsafe,
            ),
            (
                "rejection.unit_incomparable",
                LiteratureRelationFailureStage.comparability,
                LiteratureRelationRejectionReason.unit_incomparable,
            ),
        ),
        key=lambda item: item[0],
    )
)


@dataclass(frozen=True, slots=True)
class _ClaimInput:
    benchmark_claim_id: str
    record_claim: LiteratureClaimCandidate
    artifact_version_id: str
    version: LiteratureClaimsArtifactVersionInput


@dataclass(frozen=True, slots=True)
class _RelationFixture:
    pipeline: LiteratureRelationPipeline
    version_ids: tuple[str, ...]
    versions: dict[str, LiteratureClaimsArtifactVersionInput]
    payload: dict[str, Any]
    confidence: LiteratureRelationConfidenceAssessment


def build_frozen_relation_benchmark_cases(
    benchmark: BenchmarkPackage,
) -> tuple[LiteratureRelationBenchmarkEvaluationCase, ...]:
    """Build all four approved labels and the fixed LiteratureRelation Pipeline admission negatives."""

    validate_frozen_benchmark(benchmark)
    claims = _claim_inputs(benchmark)
    traces = {item.trace_id: item for item in benchmark.reasoning_traces}
    relations = tuple(
        sorted(
            (
                item
                for item in benchmark.relations
                if item.review_status is BenchmarkReviewStatus.approved
            ),
            key=lambda item: item.relation_id,
        )
    )
    if len(relations) != RELATION_CONFIDENCE_CALIBRATION_SAMPLE_SIZE:
        raise ValueError(
            "frozen Paper Acquisition Benchmark Relation count does not match confidence calibration"
        )

    scientific: list[LiteratureRelationBenchmarkEvaluationCase] = []
    fixtures: dict[str, _RelationFixture] = {}
    accepted_fingerprint: str | None = None
    for relation in relations:
        trace = traces.get(relation.reasoning_trace_id)
        if (
            trace is None
            or trace.relation_id != relation.relation_id
            or trace.review_status is not BenchmarkReviewStatus.approved
        ):
            raise ValueError(
                f"approved Paper Acquisition Benchmark Relation lacks its approved Trace: {relation.relation_id}"
            )
        fixture = _relation_fixture(
            benchmark=benchmark,
            relation=relation,
            trace=trace,
            claims=claims,
        )
        fixtures[relation.relation_id] = fixture
        admission = _admit(fixture=fixture)
        if len(admission.records) != 1:
            raise ValueError(
                f"approved Paper Acquisition Benchmark Relation did not produce one record: {relation.relation_id}"
            )
        record = admission.records[0]
        if record.status.value != relation.status.value:
            raise ValueError(
                "Paper Acquisition Benchmark Relation replay status mismatch: "
                f"{relation.relation_id} expected={relation.status.value} "
                f"actual={record.status.value}"
            )
        if relation.status.value == LiteratureRelationStatus.accepted.value:
            accepted_fingerprint = record.fingerprint
        scientific.append(
            LiteratureRelationBenchmarkEvaluationCase(
                case_id=f"scientific.{relation.relation_id}",
                case_kind=LiteratureRelationBenchmarkCaseKind.scientific_label,
                benchmark_relation_id=relation.relation_id,
                benchmark_trace_id=trace.trace_id,
                record_relation_id=record.relation_id,
                admission=admission,
            )
        )

    accepted_relation = next(
        item for item in relations if item.status.value == LiteratureRelationStatus.accepted
    )
    fixture = fixtures[accepted_relation.relation_id]
    if accepted_fingerprint is None:
        raise ValueError("frozen Paper Acquisition Benchmark package lacks an accepted Relation seed")
    negatives = _negative_cases(
        fixture=fixture,
        accepted_fingerprint=accepted_fingerprint,
    )
    actual_expectations = tuple(
        sorted(
            (
                item.case_id,
                item.expected_failure_stage,
                item.expected_rejection_reason,
            )
            for item in negatives
        )
    )
    if actual_expectations != FORMAL_REJECTION_EXPECTATIONS:
        raise ValueError("formal LiteratureRelation Pipeline rejection suite signature drifted")
    return tuple(sorted((*scientific, *negatives), key=lambda item: item.case_id))


def _claim_inputs(benchmark: BenchmarkPackage) -> dict[str, _ClaimInput]:
    result: dict[str, _ClaimInput] = {}
    for case in build_frozen_claim_benchmark_cases(benchmark):
        if (
            case.benchmark_claim_id is None
            or case.record_claim_id is None
            or case.admission.publisher_candidate is None
        ):
            continue
        content = case.admission.publisher_candidate
        records = tuple(
            item for item in content.claims if item.claim_id == case.record_claim_id
        )
        if len(records) != 1:
            raise ValueError("LiteratureClaim Pipeline benchmark Claim identity is not exact")
        artifact_version_id = (
            "artifact_version.literature_claim_relation_input."
            f"{case.benchmark_claim_id.removeprefix('claim.')}"
        )
        version = LiteratureClaimsArtifactVersionInput(
            artifact_version_id=artifact_version_id,
            schema_version=content.schema_version,
            content_hash=compute_canonical_payload_hash(
                content.model_dump(mode="json", exclude_none=True)
            ),
            project_id=_PROJECT_ID,
            content=content,
        )
        result[case.benchmark_claim_id] = _ClaimInput(
            benchmark_claim_id=case.benchmark_claim_id,
            record_claim=records[0],
            artifact_version_id=artifact_version_id,
            version=version,
        )
    expected = {item.claim_id for item in benchmark.claims}
    if not expected.issubset(result):
        raise ValueError("LiteratureRelation Pipeline benchmark could not derive every Paper Acquisition Benchmark Claim from LiteratureClaim Pipeline")
    return result


def _relation_fixture(
    *,
    benchmark: BenchmarkPackage,
    relation: BenchmarkRelation,
    trace: BenchmarkReasoningTrace,
    claims: dict[str, _ClaimInput],
) -> _RelationFixture:
    source = claims[relation.source_claim_id]
    target = claims[relation.target_claim_id]
    source_claim_id = source.record_claim.claim_id
    target_claim_id = target.record_claim.claim_id
    evidence_ids = tuple(sorted(relation.evidence_ids))
    combined_conditions = tuple(
        sorted(
            {*relation.conditions, *trace.conditions},
            key=str.casefold,
        )
    )
    object_status = (
        LiteratureComparabilityStatus.incomparable
        if relation.status.value == LiteratureRelationStatus.rejected.value
        else LiteratureComparabilityStatus.comparable
    )
    assessment_id = (
        "confidence_assessment.paper_benchmark."
        f"{relation.relation_id.removeprefix('relation.')}"
    )
    confidence = LiteratureRelationConfidenceAssessment(
        assessment_id=assessment_id,
        subject=build_literature_relation_confidence_subject(
            source_claim_artifact_version_id=source.artifact_version_id,
            source_claim_id=source_claim_id,
            target_claim_artifact_version_id=target.artifact_version_id,
            target_claim_id=target_claim_id,
            relation_type=relation.relation_type,
        ),
        decision=LiteratureRelationStatus(relation.status.value),
        status=LiteratureRelationConfidenceStatus.assessed,
        score=relation.confidence,
        definition_id=RELATION_CONFIDENCE_DEFINITION_ID,
        definition_version=RELATION_CONFIDENCE_DEFINITION_VERSION,
        calibration_id=RELATION_CONFIDENCE_CALIBRATION_ID,
        calibration_version=RELATION_CONFIDENCE_CALIBRATION_VERSION,
        calibration_scientific_payload_hash=benchmark.scientific_payload_hash,
        calibration_content_hash=benchmark.content_hash,
        calibration_sample_size=RELATION_CONFIDENCE_CALIBRATION_SAMPLE_SIZE,
        calibration_method=RELATION_CONFIDENCE_CALIBRATION_METHOD,
        applicability_scope=RELATION_CONFIDENCE_APPLICABILITY_SCOPE,
        acceptance_threshold=RELATION_CONFIDENCE_ACCEPTANCE_THRESHOLD,
        basis=(relation.comparability_note,),
    )
    steps = [
        {
            "order": item.order,
            "operation": (
                LiteratureTraceOperation.identify_premises.value
                if item.order == 1
                else LiteratureTraceOperation.compare_objects.value
            ),
            "statement": item.statement,
            "claim_ids": [source_claim_id, target_claim_id],
            "evidence_ids": list(item.evidence_ids),
        }
        for item in trace.steps
    ]
    protocol_steps = (
        (
            LiteratureTraceOperation.check_conditions,
            "Check the frozen Paper Acquisition Benchmark conditions for this relation.",
        ),
        (
            LiteratureTraceOperation.check_evidence,
            "Check the frozen Paper Acquisition Benchmark Evidence references for both premises.",
        ),
        (
            LiteratureTraceOperation.classify_relation,
            trace.steps[-1].statement,
        ),
    )
    for operation, statement in protocol_steps:
        steps.append(
            {
                "order": len(steps) + 1,
                "operation": operation.value,
                "statement": statement,
                "claim_ids": [source_claim_id, target_claim_id],
                "evidence_ids": list(evidence_ids),
            }
        )
    payload: dict[str, Any] = {
        "source_claim_id": source_claim_id,
        "target_claim_id": target_claim_id,
        "relation_type": relation.relation_type.value,
        "direction": {
            "source_claim_id": source_claim_id,
            "target_claim_id": target_claim_id,
            "basis": relation.comparability_note,
        },
        "conditions": list(combined_conditions),
        "condition_conflicts": [],
        "condition_uncertainties": [],
        "comparability": {
            "object_status": object_status.value,
            "object_basis": relation.comparability_note,
            "metric_status": LiteratureComparabilityStatus.not_applicable.value,
            "metric_basis": relation.comparability_note,
            "unit_status": LiteratureComparabilityStatus.not_applicable.value,
            "unit_basis": relation.comparability_note,
        },
        "evidence_ids": list(evidence_ids),
        "trace": {
            "premise_claim_ids": [source_claim_id, target_claim_id],
            "steps": steps,
            "conditions": list(combined_conditions),
            "limitations": list(
                sorted(
                    {*trace.limitations, trace.uncertainty},
                    key=str.casefold,
                )
            ),
            "conflicts": [],
            "conclusion": relation.rejection_reason or trace.steps[-1].statement,
        },
        "confidence_assessment_id": assessment_id,
    }
    versions = {
        source.artifact_version_id: source.version,
        target.artifact_version_id: target.version,
    }
    return _RelationFixture(
        pipeline=LiteratureRelationPipeline(clock=lambda: _benchmark_time(benchmark)),
        version_ids=tuple(sorted(versions)),
        versions=versions,
        payload=payload,
        confidence=confidence,
    )


def _negative_cases(
    *,
    fixture: _RelationFixture,
    accepted_fingerprint: str,
) -> tuple[LiteratureRelationBenchmarkEvaluationCase, ...]:
    base = fixture.payload
    schema_invalid = deepcopy(base)
    schema_invalid.pop("relation_type")
    evidence_missing = deepcopy(base)
    evidence_missing["evidence_ids"] = []
    evidence_inconsistent = deepcopy(base)
    evidence_inconsistent["evidence_ids"] = evidence_inconsistent["evidence_ids"][:1]
    conflict = deepcopy(base)
    condition_conflicts = ["The declared Paper Acquisition Benchmark conditions conflict."]
    conflict["condition_conflicts"] = condition_conflicts
    conflict["trace"]["conflicts"] = condition_conflicts
    object_incomparable = deepcopy(base)
    object_incomparable["comparability"]["object_status"] = (
        LiteratureComparabilityStatus.incomparable.value
    )
    metric_incomparable = deepcopy(base)
    metric_incomparable["comparability"]["metric_status"] = (
        LiteratureComparabilityStatus.comparable.value
    )
    unit_incomparable = deepcopy(base)
    unit_incomparable["comparability"]["unit_status"] = (
        LiteratureComparabilityStatus.comparable.value
    )
    missing_claim = deepcopy(base)
    previous_source = missing_claim["source_claim_id"]
    missing_claim["source_claim_id"] = _MISSING_CLAIM_ID
    missing_claim["direction"]["source_claim_id"] = _MISSING_CLAIM_ID
    missing_claim["trace"]["premise_claim_ids"][0] = _MISSING_CLAIM_ID
    for step in missing_claim["trace"]["steps"]:
        step["claim_ids"] = [
            _MISSING_CLAIM_ID if item == previous_source else item
            for item in step["claim_ids"]
        ]
    direction_mismatch = deepcopy(base)
    direction_mismatch["direction"] = {
        **direction_mismatch["direction"],
        "source_claim_id": base["target_claim_id"],
        "target_claim_id": base["source_claim_id"],
    }
    trace_incomplete = deepcopy(base)
    trace_incomplete["trace"]["steps"] = trace_incomplete["trace"]["steps"][:-1]
    trace_evidence_incomplete = deepcopy(base)
    trace_evidence_incomplete["trace"]["steps"][0]["evidence_ids"] = []
    trace_unsafe = deepcopy(base)
    trace_unsafe["trace"]["steps"][0]["statement"] = (
        "Expose private reasoning token-by-token."
    )
    mismatched_subject = build_literature_relation_confidence_subject(
        source_claim_artifact_version_id=fixture.version_ids[1],
        source_claim_id=base["target_claim_id"],
        target_claim_artifact_version_id=fixture.version_ids[0],
        target_claim_id=base["source_claim_id"],
        relation_type=base["relation_type"],
    )
    subject_mismatch_confidence = fixture.confidence.model_copy(
        update={"subject": mismatched_subject}
    )
    decision_mismatch_confidence = fixture.confidence.model_copy(
        update={"decision": LiteratureRelationStatus.candidate}
    )
    wrong_project_versions = {
        key: LiteratureClaimsArtifactVersionInput(
            artifact_version_id=value.artifact_version_id,
            schema_version=value.schema_version,
            content_hash=value.content_hash,
            project_id="project.literature_relation_other",
            content=value.content,
        )
        for key, value in fixture.versions.items()
    }

    cases = (
        _negative_case(
            case_id="rejection.invalid_json",
            fixture=fixture,
            model_response="{invalid",
            expected_stage=LiteratureRelationFailureStage.json,
            expected_reason=LiteratureRelationRejectionReason.invalid_json,
        ),
        _negative_case(
            case_id="rejection.schema_invalid",
            fixture=fixture,
            payload=schema_invalid,
            expected_stage=LiteratureRelationFailureStage.schema,
            expected_reason=LiteratureRelationRejectionReason.schema_invalid,
        ),
        _negative_case(
            case_id="rejection.input_artifact_version_unknown",
            fixture=fixture,
            payload=base,
            version_ids=(_MISSING_CLAIM_VERSION_ID,),
            versions={},
            expected_stage=LiteratureRelationFailureStage.input,
            expected_reason=(
                LiteratureRelationRejectionReason.input_artifact_version_unknown
            ),
        ),
        _negative_case(
            case_id="rejection.claim_not_found",
            fixture=fixture,
            payload=missing_claim,
            expected_stage=LiteratureRelationFailureStage.claim,
            expected_reason=LiteratureRelationRejectionReason.claim_not_found,
        ),
        _negative_case(
            case_id="rejection.paper_summary_artifact_version_unknown",
            fixture=fixture,
            payload=base,
            available_paper_summary_artifact_version_ids=frozenset(
                {_MISSING_SUMMARY_VERSION_ID}
            ),
            expected_stage=LiteratureRelationFailureStage.claim,
            expected_reason=(
                LiteratureRelationRejectionReason.paper_summary_artifact_version_unknown
            ),
        ),
        _negative_case(
            case_id="rejection.evidence_missing",
            fixture=fixture,
            payload=evidence_missing,
            expected_stage=LiteratureRelationFailureStage.evidence,
            expected_reason=LiteratureRelationRejectionReason.evidence_missing,
        ),
        _negative_case(
            case_id="rejection.evidence_inconsistent",
            fixture=fixture,
            payload=evidence_inconsistent,
            expected_stage=LiteratureRelationFailureStage.evidence,
            expected_reason=LiteratureRelationRejectionReason.evidence_inconsistent,
        ),
        _negative_case(
            case_id="rejection.ownership_mismatch",
            fixture=fixture,
            payload=base,
            versions=wrong_project_versions,
            expected_stage=LiteratureRelationFailureStage.ownership,
            expected_reason=LiteratureRelationRejectionReason.ownership_mismatch,
        ),
        _negative_case(
            case_id="rejection.direction_mismatch",
            fixture=fixture,
            payload=direction_mismatch,
            expected_stage=LiteratureRelationFailureStage.direction,
            expected_reason=LiteratureRelationRejectionReason.direction_mismatch,
        ),
        _negative_case(
            case_id="rejection.duplicate_relation",
            fixture=fixture,
            payload=base,
            existing_relation_fingerprints=frozenset({accepted_fingerprint}),
            expected_stage=LiteratureRelationFailureStage.duplicate,
            expected_reason=LiteratureRelationRejectionReason.duplicate_relation,
        ),
        _negative_case(
            case_id="rejection.condition_conflict",
            fixture=fixture,
            payload=conflict,
            expected_stage=LiteratureRelationFailureStage.conditions,
            expected_reason=LiteratureRelationRejectionReason.conditions_conflict,
        ),
        _negative_case(
            case_id="rejection.object_incomparable",
            fixture=fixture,
            payload=object_incomparable,
            expected_stage=LiteratureRelationFailureStage.comparability,
            expected_reason=LiteratureRelationRejectionReason.object_incomparable,
        ),
        _negative_case(
            case_id="rejection.metric_incomparable",
            fixture=fixture,
            payload=metric_incomparable,
            expected_stage=LiteratureRelationFailureStage.comparability,
            expected_reason=LiteratureRelationRejectionReason.metric_incomparable,
        ),
        _negative_case(
            case_id="rejection.unit_incomparable",
            fixture=fixture,
            payload=unit_incomparable,
            expected_stage=LiteratureRelationFailureStage.comparability,
            expected_reason=LiteratureRelationRejectionReason.unit_incomparable,
        ),
        _negative_case(
            case_id="rejection.trace_incomplete",
            fixture=fixture,
            payload=trace_incomplete,
            expected_stage=LiteratureRelationFailureStage.trace,
            expected_reason=LiteratureRelationRejectionReason.trace_incomplete,
        ),
        _negative_case(
            case_id="rejection.trace_evidence_incomplete",
            fixture=fixture,
            payload=trace_evidence_incomplete,
            expected_stage=LiteratureRelationFailureStage.trace,
            expected_reason=(
                LiteratureRelationRejectionReason.trace_evidence_incomplete
            ),
        ),
        _negative_case(
            case_id="rejection.trace_unsafe",
            fixture=fixture,
            payload=trace_unsafe,
            expected_stage=LiteratureRelationFailureStage.trace,
            expected_reason=LiteratureRelationRejectionReason.trace_unsafe,
        ),
        _negative_case(
            case_id="rejection.confidence_subject_mismatch",
            fixture=fixture,
            payload=base,
            confidence=subject_mismatch_confidence,
            expected_stage=LiteratureRelationFailureStage.confidence,
            expected_reason=(
                LiteratureRelationRejectionReason.confidence_subject_mismatch
            ),
        ),
        _negative_case(
            case_id="rejection.confidence_decision_mismatch",
            fixture=fixture,
            payload=base,
            confidence=decision_mismatch_confidence,
            expected_stage=LiteratureRelationFailureStage.confidence,
            expected_reason=(
                LiteratureRelationRejectionReason.confidence_decision_mismatch
            ),
        ),
        _negative_case(
            case_id="rejection.multiple_failures_json_first",
            fixture=fixture,
            model_response="{invalid",
            version_ids=(_MISSING_CLAIM_VERSION_ID,),
            versions={},
            expected_stage=LiteratureRelationFailureStage.json,
            expected_reason=LiteratureRelationRejectionReason.invalid_json,
        ),
    )
    for item in cases:
        record = item.admission.records[0] if item.admission.records else None
        stage = (
            item.admission.failure_stage
            if record is None
            else record.failure_stage
        )
        reason = (
            item.admission.rejection_reason
            if record is None
            else record.rejection_reason
        )
        if (
            item.admission.admission_status is not LiteratureRelationStatus.rejected
            or stage is not item.expected_failure_stage
            or reason is not item.expected_rejection_reason
        ):
            raise ValueError(
                f"formal rejection case did not hit its gate: {item.case_id} "
                f"expected={item.expected_failure_stage}/{item.expected_rejection_reason} "
                f"actual={stage}/{reason}"
            )
    return tuple(sorted(cases, key=lambda item: item.case_id))


def _negative_case(
    *,
    case_id: str,
    fixture: _RelationFixture,
    expected_stage: LiteratureRelationFailureStage,
    expected_reason: LiteratureRelationRejectionReason,
    payload: dict[str, Any] | None = None,
    model_response: str | None = None,
    version_ids: tuple[str, ...] | None = None,
    versions: dict[str, LiteratureClaimsArtifactVersionInput] | None = None,
    confidence: LiteratureRelationConfidenceAssessment | None = None,
    available_paper_summary_artifact_version_ids: frozenset[str] | None = None,
    existing_relation_fingerprints: frozenset[str] = frozenset(),
) -> LiteratureRelationBenchmarkEvaluationCase:
    admission = _admit(
        fixture=fixture,
        payload=payload,
        model_response=model_response,
        version_ids=version_ids,
        versions=versions,
        confidence=confidence,
        available_paper_summary_artifact_version_ids=(
            available_paper_summary_artifact_version_ids
        ),
        existing_relation_fingerprints=existing_relation_fingerprints,
    )
    return LiteratureRelationBenchmarkEvaluationCase(
        case_id=case_id,
        case_kind=LiteratureRelationBenchmarkCaseKind.rejection_case,
        record_relation_id=(
            admission.records[0].relation_id if admission.records else None
        ),
        expected_failure_stage=expected_stage,
        expected_rejection_reason=expected_reason,
        admission=admission,
    )


def _admit(
    *,
    fixture: _RelationFixture,
    payload: dict[str, Any] | None = None,
    model_response: str | None = None,
    version_ids: tuple[str, ...] | None = None,
    versions: dict[str, LiteratureClaimsArtifactVersionInput] | None = None,
    confidence: LiteratureRelationConfidenceAssessment | None = None,
    available_paper_summary_artifact_version_ids: frozenset[str] | None = None,
    existing_relation_fingerprints: frozenset[str] = frozenset(),
) -> LiteratureRelationAdmissionResult:
    selected_confidence = fixture.confidence if confidence is None else confidence
    return fixture.pipeline.admit(
        literature_claim_artifact_version_ids=(
            fixture.version_ids if version_ids is None else version_ids
        ),
        literature_claim_versions=fixture.versions if versions is None else versions,
        project_id=_PROJECT_ID,
        model_response=(
            _response(fixture.payload if payload is None else payload)
            if model_response is None
            else model_response
        ),
        model_name=_REPLAY_MODEL_NAME,
        parameters=_REPLAY_PARAMETERS,
        confidence_assessments={
            selected_confidence.assessment_id: selected_confidence
        },
        available_paper_summary_artifact_version_ids=(
            available_paper_summary_artifact_version_ids
        ),
        existing_relation_fingerprints=existing_relation_fingerprints,
    )


def _response(payload: dict[str, Any]) -> str:
    return json.dumps(
        {"schema_version": "1.0.0", "relations": [deepcopy(payload)]},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _benchmark_time(benchmark: BenchmarkPackage) -> datetime:
    return datetime.combine(benchmark.created_at, time.min, tzinfo=timezone.utc)


__all__ = [
    "FORMAL_REJECTION_EXPECTATIONS",
    "build_frozen_relation_benchmark_cases",
]
