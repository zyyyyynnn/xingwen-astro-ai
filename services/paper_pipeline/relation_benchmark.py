"""Reproducible LiteratureRelation Pipeline evaluation against the frozen Paper Acquisition Benchmark Relation labels."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path

from pydantic import TypeAdapter

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.literature_relation import (
    LiteratureRelationBenchmarkCaseKind,
    LiteratureRelationBenchmarkCaseResult,
    LiteratureRelationBenchmarkEvaluationCase,
    LiteratureRelationBenchmarkReport,
    LiteratureRelationCandidate,
    LiteratureRelationConfidenceAssessment,
    LiteratureRelationConfidenceBin,
    LiteratureRelationConfidenceStatus,
    LiteratureRelationRejectionCount,
    LiteratureRelationRejectionReason,
    LiteratureRelationStatus,
    LiteratureRelationStatusCounts,
    LiteratureRelationTypeCount,
    LiteratureReasoningTraceCandidate,
    build_literature_relation_confidence_subject,
    compute_literature_relation_benchmark_output_hash,
)
from app.schemas.paper_benchmark import (
    BenchmarkPackage,
    BenchmarkReasoningTrace,
    BenchmarkRelation,
    BenchmarkReviewStatus,
)

from .benchmark import load_frozen_benchmark, validate_frozen_benchmark
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


_CASE_ADAPTER = TypeAdapter(tuple[LiteratureRelationBenchmarkEvaluationCase, ...])
_CONFIDENCE_BINS = (
    ("[0.0,0.5)", 0.0, 0.5, False),
    ("[0.5,0.9)", 0.5, 0.9, False),
    ("[0.9,1.0]", 0.9, 1.0, True),
)


def evaluate_literature_relations(
    *,
    benchmark: BenchmarkPackage,
    cases: tuple[LiteratureRelationBenchmarkEvaluationCase, ...],
) -> LiteratureRelationBenchmarkReport:
    """Evaluate LiteratureRelation Pipeline admission without inventing labels beyond frozen Paper Acquisition Benchmark."""

    if not cases:
        raise ValueError("LiteratureRelation benchmark requires at least one case")
    validate_frozen_benchmark(benchmark)
    ordered_cases = tuple(sorted(cases, key=lambda item: item.case_id))
    if len({item.case_id for item in ordered_cases}) != len(ordered_cases):
        raise ValueError("LiteratureRelation benchmark case ids must be unique")

    benchmark_relations = {item.relation_id: item for item in benchmark.relations}
    benchmark_traces = {item.trace_id: item for item in benchmark.reasoning_traces}
    claim_ids = _benchmark_claim_record_ids(benchmark)
    producer = ordered_cases[0].admission.producer
    signature = _producer_signature(producer)
    results: list[LiteratureRelationBenchmarkCaseResult] = []

    for case in ordered_cases:
        if _producer_signature(case.admission.producer) != signature:
            raise ValueError(
                "one Relation benchmark report requires one Prompt/model/parameter policy"
            )
        expected_relation = None
        expected_trace = None
        if case.case_kind is LiteratureRelationBenchmarkCaseKind.scientific_label:
            expected_relation = benchmark_relations.get(case.benchmark_relation_id or "")
            expected_trace = benchmark_traces.get(case.benchmark_trace_id or "")
            if (
                expected_relation is None
                or expected_trace is None
                or expected_relation.review_status is not BenchmarkReviewStatus.approved
                or expected_trace.review_status is not BenchmarkReviewStatus.approved
                or expected_relation.reasoning_trace_id != expected_trace.trace_id
                or expected_trace.relation_id != expected_relation.relation_id
            ):
                raise ValueError(
                    "scientific cases must reference matching approved Paper Acquisition Benchmark Relation/Trace labels"
                )

        record = _select_record(case)
        trace = _select_trace(case, record)
        status = (
            record.status if record is not None else case.admission.admission_status
        )
        failure_stage = (
            record.failure_stage
            if record is not None
            else case.admission.failure_stage
        )
        rejection_reason = (
            record.rejection_reason
            if record is not None
            else case.admission.rejection_reason
        )
        schema_valid = record is not None or rejection_reason not in {
            LiteratureRelationRejectionReason.invalid_json,
            LiteratureRelationRejectionReason.schema_invalid,
        }

        scientific = expected_relation is not None and expected_trace is not None
        expected_source = (
            None
            if expected_relation is None
            else claim_ids[expected_relation.source_claim_id]
        )
        expected_target = (
            None
            if expected_relation is None
            else claim_ids[expected_relation.target_claim_id]
        )
        pair_matched = (
            None
            if not scientific
            else record is not None
            and {record.source_claim_id, record.target_claim_id}
            == {expected_source, expected_target}
        )
        scientific_compared = scientific
        scientific_exact = None
        if scientific:
            scientific_exact = (
                record is not None
                and trace is not None
                and expected_relation is not None
                and expected_trace is not None
                and expected_source is not None
                and expected_target is not None
                and _matches_approved_label(
                    record=record,
                    trace=trace,
                    expected_relation=expected_relation,
                    expected_trace=expected_trace,
                    expected_source_claim_id=expected_source,
                    expected_target_claim_id=expected_target,
                )
            )
        relation_supported, relation_total = _relation_evidence_counts(
            record, expected_relation
        )
        trace_supported, trace_total = _trace_evidence_counts(trace, expected_trace)
        evidence_less_case = (
            case.case_kind is LiteratureRelationBenchmarkCaseKind.rejection_case
            and case.expected_rejection_reason
            is LiteratureRelationRejectionReason.evidence_missing
        )
        evidence_less_blocked = (
            status is LiteratureRelationStatus.rejected
            and rejection_reason is LiteratureRelationRejectionReason.evidence_missing
            if evidence_less_case
            else None
        )
        rejection_case_pass = None
        if case.case_kind is LiteratureRelationBenchmarkCaseKind.rejection_case:
            rejection_case_pass = (
                status is LiteratureRelationStatus.rejected
                and failure_stage is case.expected_failure_stage
                and rejection_reason is case.expected_rejection_reason
            )

        confidence = None if record is None else record.confidence
        results.append(
            LiteratureRelationBenchmarkCaseResult(
                case_id=case.case_id,
                case_kind=case.case_kind,
                benchmark_relation_id=case.benchmark_relation_id,
                benchmark_trace_id=case.benchmark_trace_id,
                record_relation_id=None if record is None else record.relation_id,
                relation_type=(
                    None if expected_relation is None else expected_relation.relation_type
                ),
                expected_failure_stage=case.expected_failure_stage,
                expected_rejection_reason=case.expected_rejection_reason,
                schema_valid=schema_valid,
                candidate_pair_matched=pair_matched,
                scientific_label_compared=scientific_compared,
                scientific_label_exact_match=scientific_exact,
                relation_evidence_items_supported=relation_supported,
                relation_evidence_items_total=relation_total,
                trace_step_evidence_items_supported=trace_supported,
                trace_step_evidence_items_total=trace_total,
                evidence_less_case=evidence_less_case,
                evidence_less_blocked=evidence_less_blocked,
                rejection_case_pass=rejection_case_pass,
                confidence_status=None if confidence is None else confidence.status,
                confidence_score=None if confidence is None else confidence.score,
                confidence_calibrated=(
                    None
                    if confidence is None or record is None
                    else _confidence_is_calibrated(
                        confidence,
                        benchmark,
                        record,
                    )
                ),
                status=status,
                failure_stage=failure_stage,
                rejection_reason=rejection_reason,
                input_hash=case.admission.producer.input_hash,
                output_hash=case.admission.output_hash,
            )
        )

    typed_results = tuple(results)
    scientific_results = tuple(
        item
        for item in typed_results
        if item.case_kind is LiteratureRelationBenchmarkCaseKind.scientific_label
    )
    rejection_results = tuple(
        item
        for item in typed_results
        if item.case_kind is LiteratureRelationBenchmarkCaseKind.rejection_case
    )
    scientific_confidence = tuple(
        item for item in scientific_results if item.confidence_status is not None
    )
    type_counts = Counter(
        item.relation_type
        for item in scientific_results
        if item.relation_type is not None
    )
    rejection_case_ids: dict[LiteratureRelationRejectionReason, list[str]] = (
        defaultdict(list)
    )
    for item in rejection_results:
        if item.rejection_reason is not None:
            rejection_case_ids[item.rejection_reason].append(item.case_id)

    input_payload = {
        "benchmark_id": benchmark.benchmark_id,
        "benchmark_schema_version": benchmark.schema_version,
        "benchmark_version": benchmark.benchmark_version,
        "benchmark_scientific_payload_hash": benchmark.scientific_payload_hash,
        "benchmark_content_hash": benchmark.content_hash,
        "prompt_name": producer.prompt_name,
        "prompt_version": producer.prompt_version,
        "prompt_hash": producer.prompt_hash,
        "relation_schema_version": producer.schema_version,
        "model_name": producer.model_name,
        "parameters_version": producer.parameters_version,
        "parameters_hash": producer.parameters_hash,
        "producer_version": producer.producer_version,
        "producer_policy_signature": list(signature),
        "cases": [
            item.model_dump(mode="json", exclude_none=True) for item in typed_results
        ],
    }
    input_hash = compute_canonical_payload_hash(input_payload)
    report_payload = {
        "report_version": "1.0.0",
        **{
            key: value
            for key, value in input_payload.items()
            if key not in {"cases", "producer_policy_signature"}
        },
        "sample_count": len(typed_results),
        "schema_items_valid": sum(item.schema_valid for item in typed_results),
        "schema_items_total": len(typed_results),
        "schema_pass_rate": _rate(
            sum(item.schema_valid for item in typed_results), len(typed_results)
        ),
        "scientific_pair_items_matched": sum(
            item.candidate_pair_matched is True for item in scientific_results
        ),
        "scientific_pair_items_total": len(scientific_results),
        "scientific_pair_coverage_rate": _rate(
            sum(item.candidate_pair_matched is True for item in scientific_results),
            len(scientific_results),
        ),
        "scientific_relation_items_exact": sum(
            item.scientific_label_exact_match is True for item in scientific_results
        ),
        "scientific_relation_items_total": sum(
            item.scientific_label_compared for item in scientific_results
        ),
        "scientific_relation_exact_match_rate": _rate(
            sum(
                item.scientific_label_exact_match is True
                for item in scientific_results
            ),
            sum(item.scientific_label_compared for item in scientific_results),
        ),
        "relation_evidence_items_supported": sum(
            item.relation_evidence_items_supported for item in scientific_results
        ),
        "relation_evidence_items_total": sum(
            item.relation_evidence_items_total for item in scientific_results
        ),
        "relation_evidence_coverage_rate": _rate(
            sum(item.relation_evidence_items_supported for item in scientific_results),
            sum(item.relation_evidence_items_total for item in scientific_results),
        ),
        "trace_step_evidence_items_supported": sum(
            item.trace_step_evidence_items_supported for item in scientific_results
        ),
        "trace_step_evidence_items_total": sum(
            item.trace_step_evidence_items_total for item in scientific_results
        ),
        "trace_step_evidence_coverage_rate": _rate(
            sum(
                item.trace_step_evidence_items_supported for item in scientific_results
            ),
            sum(item.trace_step_evidence_items_total for item in scientific_results),
        ),
        "evidence_less_cases_blocked": sum(
            item.evidence_less_blocked is True for item in typed_results
        ),
        "evidence_less_cases_total": sum(
            item.evidence_less_case for item in typed_results
        ),
        "evidence_less_block_rate": _rate(
            sum(item.evidence_less_blocked is True for item in typed_results),
            sum(item.evidence_less_case for item in typed_results),
        ),
        "rejection_cases_passed": sum(
            item.rejection_case_pass is True for item in rejection_results
        ),
        "rejection_cases_total": len(rejection_results),
        "rejection_case_pass_rate": _rate(
            sum(item.rejection_case_pass is True for item in rejection_results),
            len(rejection_results),
        ),
        "confidence_items_total": len(scientific_confidence),
        "confidence_assessed_count": sum(
            item.confidence_status is LiteratureRelationConfidenceStatus.assessed
            for item in scientific_confidence
        ),
        "confidence_not_evaluable_count": sum(
            item.confidence_status is LiteratureRelationConfidenceStatus.not_evaluable
            for item in scientific_confidence
        ),
        "confidence_calibrated_count": sum(
            item.confidence_calibrated is True for item in scientific_confidence
        ),
        "confidence_distribution": [
            item.model_dump(mode="json")
            for item in _confidence_distribution(scientific_confidence)
        ],
        "scientific_status_counts": _status_counts(scientific_results).model_dump(
            mode="json"
        ),
        "status_counts": _status_counts(typed_results).model_dump(mode="json"),
        "relation_type_counts": [
            LiteratureRelationTypeCount(
                relation_type=relation_type,
                count=count,
            ).model_dump(mode="json")
            for relation_type, count in sorted(
                type_counts.items(), key=lambda pair: pair[0].value
            )
        ],
        "rejection_counts": [
            LiteratureRelationRejectionCount(
                rejection_reason=reason,
                count=len(case_ids),
                sample_case_ids=tuple(sorted(case_ids)),
            ).model_dump(mode="json")
            for reason, case_ids in sorted(
                rejection_case_ids.items(), key=lambda pair: pair[0].value
            )
        ],
        "cases": [
            item.model_dump(mode="json", exclude_none=True) for item in typed_results
        ],
        "input_hash": input_hash,
        "output_hash": "sha256:" + "0" * 64,
    }
    report_payload["output_hash"] = compute_literature_relation_benchmark_output_hash(
        report_payload
    )
    return LiteratureRelationBenchmarkReport.model_validate(report_payload)


def validate_scientific_label_coverage(
    benchmark: BenchmarkPackage,
    cases: tuple[LiteratureRelationBenchmarkEvaluationCase, ...],
) -> None:
    """Require every approved Paper Acquisition Benchmark Relation and matching Trace exactly once."""

    validate_frozen_benchmark(benchmark)
    traces = {item.relation_id: item for item in benchmark.reasoning_traces}
    expected = tuple(
        sorted(
            (relation.relation_id, traces[relation.relation_id].trace_id)
            for relation in benchmark.relations
            if relation.review_status is BenchmarkReviewStatus.approved
            and traces[relation.relation_id].review_status
            is BenchmarkReviewStatus.approved
        )
    )
    actual = tuple(
        sorted(
            (case.benchmark_relation_id, case.benchmark_trace_id)
            for case in cases
            if case.case_kind is LiteratureRelationBenchmarkCaseKind.scientific_label
            and case.benchmark_relation_id is not None
            and case.benchmark_trace_id is not None
        )
    )
    if actual != expected:
        raise ValueError(
            "formal LiteratureRelation Pipeline benchmark must cover every approved Paper Acquisition Benchmark Relation/Trace exactly once"
        )


def validate_formal_case_coverage(
    benchmark: BenchmarkPackage,
    cases: tuple[LiteratureRelationBenchmarkEvaluationCase, ...],
) -> None:
    """Reject favorable subsets and drifted negative expectations at the CLI gate."""

    from .relation_benchmark_cases import FORMAL_REJECTION_EXPECTATIONS

    validate_scientific_label_coverage(benchmark, cases)
    if len({item.case_id for item in cases}) != len(cases):
        raise ValueError("formal LiteratureRelation Pipeline benchmark case ids must be unique")
    trace_ids = {item.relation_id: item.trace_id for item in benchmark.reasoning_traces}
    expected_scientific = tuple(
        sorted(
            (
                f"scientific.{relation.relation_id}",
                relation.relation_id,
                trace_ids[relation.relation_id],
            )
            for relation in benchmark.relations
            if relation.review_status is BenchmarkReviewStatus.approved
        )
    )
    actual_scientific = tuple(
        sorted(
            (
                case.case_id,
                case.benchmark_relation_id,
                case.benchmark_trace_id,
            )
            for case in cases
            if case.case_kind is LiteratureRelationBenchmarkCaseKind.scientific_label
        )
    )
    if actual_scientific != expected_scientific:
        raise ValueError("formal LiteratureRelation Pipeline benchmark scientific case identity drifted")
    actual = tuple(
        sorted(
            (
                case.case_id,
                case.expected_failure_stage,
                case.expected_rejection_reason,
            )
            for case in cases
            if case.case_kind is LiteratureRelationBenchmarkCaseKind.rejection_case
        )
    )
    if actual != FORMAL_REJECTION_EXPECTATIONS:
        raise ValueError(
            "formal LiteratureRelation Pipeline benchmark must contain the fixed rejection suite exactly"
        )


def _benchmark_claim_record_ids(benchmark: BenchmarkPackage) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for case in build_frozen_claim_benchmark_cases(benchmark):
        if case.benchmark_claim_id is None or case.record_claim_id is None:
            continue
        mapping[case.benchmark_claim_id] = case.record_claim_id
    return mapping


def _select_record(
    case: LiteratureRelationBenchmarkEvaluationCase,
) -> LiteratureRelationCandidate | None:
    if case.record_relation_id is None:
        if len(case.admission.records) > 1:
            raise ValueError("multi-record benchmark case requires record_relation_id")
        return case.admission.records[0] if case.admission.records else None
    matches = tuple(
        item
        for item in case.admission.records
        if item.relation_id == case.record_relation_id
    )
    if len(matches) != 1:
        raise ValueError("record_relation_id must identify exactly one Relation")
    return matches[0]


def _select_trace(
    case: LiteratureRelationBenchmarkEvaluationCase,
    record: LiteratureRelationCandidate | None,
) -> LiteratureReasoningTraceCandidate | None:
    if record is None or record.reasoning_trace_id is None:
        return None
    matches = tuple(
        item
        for item in case.admission.reasoning_traces
        if item.trace_id == record.reasoning_trace_id
        and item.relation_id == record.relation_id
    )
    if len(matches) > 1:
        raise ValueError("Relation benchmark admission contains duplicate Trace ids")
    return matches[0] if matches else None


def _matches_approved_label(
    *,
    record: LiteratureRelationCandidate,
    trace: LiteratureReasoningTraceCandidate,
    expected_relation: BenchmarkRelation,
    expected_trace: BenchmarkReasoningTrace,
    expected_source_claim_id: str,
    expected_target_claim_id: str,
) -> bool:
    """Compare the frozen Paper Acquisition Benchmark fields representable in the LiteratureRelation Pipeline domain model.

    LiteratureRelation Pipeline requires protocol bookkeeping beyond the two frozen Trace steps.  Those
    extra public operations are excluded here; every frozen step and condition is
    still compared exactly as a projection of the admitted Trace.
    """

    expected_steps = tuple(
        (item.order, item.statement, tuple(sorted(item.evidence_ids)))
        for item in expected_trace.steps
    )
    actual_steps = tuple(
        (item.order, item.statement, tuple(sorted(item.evidence_ids)))
        for item in trace.steps
    )
    expected_conditions = tuple(
        sorted(
            {*expected_relation.conditions, *expected_trace.conditions},
            key=str.casefold,
        )
    )
    expected_limitations = tuple(
        sorted(
            {*expected_trace.limitations, expected_trace.uncertainty},
            key=str.casefold,
        )
    )
    return (
        record.source_claim_id == expected_source_claim_id
        and record.target_claim_id == expected_target_claim_id
        and record.direction.source_claim_id == expected_source_claim_id
        and record.direction.target_claim_id == expected_target_claim_id
        and record.relation_type is expected_relation.relation_type
        and record.status.value == expected_relation.status.value
        and record.conditions == expected_conditions
        and record.direction.basis == expected_relation.comparability_note
        and record.comparability.object_basis
        == expected_relation.comparability_note
        and record.evidence_ids == tuple(sorted(expected_relation.evidence_ids))
        and record.confidence is not None
        and record.confidence.score == expected_relation.confidence
        and record.confidence.decision is record.status
        and record.source_claim_artifact_version_id is not None
        and record.target_claim_artifact_version_id is not None
        and record.confidence.subject
        == build_literature_relation_confidence_subject(
            source_claim_artifact_version_id=(
                record.source_claim_artifact_version_id
            ),
            source_claim_id=record.source_claim_id,
            target_claim_artifact_version_id=(
                record.target_claim_artifact_version_id
            ),
            target_claim_id=record.target_claim_id,
            relation_type=record.relation_type,
        )
        and (
            (
                expected_relation.rejection_reason is None
                and record.rejection_reason is None
            )
            or (
                expected_relation.rejection_reason is not None
                and record.rejection_reason
                is LiteratureRelationRejectionReason.object_incomparable
                and trace.conclusion == expected_relation.rejection_reason
            )
        )
        and trace.premise_claim_ids
        == (expected_source_claim_id, expected_target_claim_id)
        and actual_steps[: len(expected_steps)] == expected_steps
        and trace.conditions == expected_conditions
        and trace.limitations == expected_limitations
    )


def _relation_evidence_counts(
    record: LiteratureRelationCandidate | None,
    expected: BenchmarkRelation | None,
) -> tuple[int, int]:
    if expected is None:
        return 0, 0
    actual = set() if record is None else set(record.evidence_ids)
    return sum(item in actual for item in expected.evidence_ids), len(
        expected.evidence_ids
    )


def _trace_evidence_counts(
    trace: LiteratureReasoningTraceCandidate | None,
    expected: BenchmarkReasoningTrace | None,
) -> tuple[int, int]:
    if expected is None:
        return 0, 0
    actual_steps = (
        {} if trace is None else {item.order: set(item.evidence_ids) for item in trace.steps}
    )
    supported = sum(
        evidence_id in actual_steps.get(step.order, set())
        for step in expected.steps
        for evidence_id in step.evidence_ids
    )
    total = sum(len(step.evidence_ids) for step in expected.steps)
    return supported, total


def _confidence_is_calibrated(
    confidence: LiteratureRelationConfidenceAssessment,
    benchmark: BenchmarkPackage,
    record: LiteratureRelationCandidate,
) -> bool:
    return (
        confidence.status is LiteratureRelationConfidenceStatus.assessed
        and confidence.score is not None
        and confidence.decision is record.status
        and record.source_claim_artifact_version_id is not None
        and record.target_claim_artifact_version_id is not None
        and confidence.subject
        == build_literature_relation_confidence_subject(
            source_claim_artifact_version_id=(
                record.source_claim_artifact_version_id
            ),
            source_claim_id=record.source_claim_id,
            target_claim_artifact_version_id=(
                record.target_claim_artifact_version_id
            ),
            target_claim_id=record.target_claim_id,
            relation_type=record.relation_type,
        )
        and confidence.definition_id == RELATION_CONFIDENCE_DEFINITION_ID
        and confidence.definition_version == RELATION_CONFIDENCE_DEFINITION_VERSION
        and confidence.calibration_id == RELATION_CONFIDENCE_CALIBRATION_ID
        and confidence.calibration_version == RELATION_CONFIDENCE_CALIBRATION_VERSION
        and confidence.calibration_scientific_payload_hash
        == benchmark.scientific_payload_hash
        and confidence.calibration_content_hash == benchmark.content_hash
        and confidence.calibration_sample_size == len(benchmark.relations)
        and confidence.calibration_method == RELATION_CONFIDENCE_CALIBRATION_METHOD
        and confidence.applicability_scope == RELATION_CONFIDENCE_APPLICABILITY_SCOPE
        and confidence.acceptance_threshold
        == RELATION_CONFIDENCE_ACCEPTANCE_THRESHOLD
        and confidence.score_interpretation
        == "confidence_in_relation_type_and_admission_decision"
    )


def _producer_signature(producer: object) -> tuple[object, ...]:
    return tuple(
        getattr(producer, field)
        for field in (
            "prompt_name",
            "prompt_version",
            "prompt_hash",
            "schema_version",
            "model_name",
            "parameters_version",
            "parameters_hash",
            "producer_version",
            "pairing_version",
            "comparison_policy_version",
            "trace_protocol_version",
            "confidence_definition_id",
            "confidence_definition_version",
            "confidence_calibration_id",
            "confidence_calibration_version",
            "confidence_calibration_scientific_payload_hash",
            "confidence_calibration_content_hash",
            "confidence_calibration_sample_size",
            "confidence_calibration_method",
            "confidence_applicability_scope",
            "confidence_acceptance_threshold",
        )
    )


def _status_counts(
    cases: tuple[LiteratureRelationBenchmarkCaseResult, ...],
) -> LiteratureRelationStatusCounts:
    return LiteratureRelationStatusCounts(
        accepted=sum(item.status is LiteratureRelationStatus.accepted for item in cases),
        candidate=sum(
            item.status is LiteratureRelationStatus.candidate for item in cases
        ),
        rejected=sum(item.status is LiteratureRelationStatus.rejected for item in cases),
    )


def _confidence_distribution(
    cases: tuple[LiteratureRelationBenchmarkCaseResult, ...],
) -> tuple[LiteratureRelationConfidenceBin, ...]:
    scores = tuple(
        item.confidence_score
        for item in cases
        if item.confidence_status is LiteratureRelationConfidenceStatus.assessed
        and item.confidence_score is not None
    )
    return tuple(
        LiteratureRelationConfidenceBin(
            label=label,
            lower_bound=lower,
            upper_bound=upper,
            upper_inclusive=inclusive,
            count=sum(
                score >= lower
                and (score <= upper if inclusive else score < upper)
                for score in scores
            ),
        )
        for label, lower, upper, inclusive in _CONFIDENCE_BINS
    )


def _rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate serialized LiteratureRelation Pipeline admission cases against frozen Paper Acquisition Benchmark Relations."
    )
    parser.add_argument(
        "--cases",
        type=Path,
        help=(
            "Optional JSON array of LiteratureRelationBenchmarkEvaluationCase values; "
            "omit to generate the formal suite deterministically from tracked Paper Acquisition Benchmark."
        ),
    )
    parser.add_argument("--cases-output", type=Path)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    benchmark = load_frozen_benchmark()
    if args.cases is None:
        from .relation_benchmark_cases import build_frozen_relation_benchmark_cases

        cases = build_frozen_relation_benchmark_cases(benchmark)
    else:
        cases = _CASE_ADAPTER.validate_json(args.cases.read_text(encoding="utf-8"))
    cases = tuple(sorted(cases, key=lambda item: item.case_id))
    validate_formal_case_coverage(benchmark, cases)
    if args.cases_output is not None:
        args.cases_output.parent.mkdir(parents=True, exist_ok=True)
        args.cases_output.write_text(
            _stable_json(
                [item.model_dump(mode="json", exclude_none=True) for item in cases]
            ),
            encoding="utf-8",
            newline="\n",
        )
    report = evaluate_literature_relations(benchmark=benchmark, cases=cases)
    content = _stable_json(report.model_dump(mode="json", exclude_none=True))
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content, encoding="utf-8", newline="\n")
    else:
        print(content, end="")
    return 0


def _stable_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        allow_nan=False,
    ) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
