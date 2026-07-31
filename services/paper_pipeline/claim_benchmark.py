"""Reproducible D-07 evaluation against the frozen D-01 Claim labels."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path

from pydantic import TypeAdapter

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.literature_claim import (
    LiteratureClaimBenchmarkCaseKind,
    LiteratureClaimBenchmarkCaseResult,
    LiteratureClaimBenchmarkEvaluationCase,
    LiteratureClaimBenchmarkReport,
    LiteratureClaimCandidate,
    LiteratureClaimRejectionCount,
    LiteratureClaimRejectionReason,
    LiteratureClaimStatus,
    LiteratureClaimStatusCounts,
    LiteratureClaimTypeCount,
    compute_literature_claim_benchmark_output_hash,
)
from app.schemas.paper_benchmark import (
    BenchmarkClaim,
    BenchmarkPackage,
    BenchmarkReviewStatus,
)

from .benchmark import load_frozen_benchmark, validate_frozen_benchmark


_CASE_ADAPTER = TypeAdapter(tuple[LiteratureClaimBenchmarkEvaluationCase, ...])


def evaluate_literature_claims(
    *,
    benchmark: BenchmarkPackage,
    cases: tuple[LiteratureClaimBenchmarkEvaluationCase, ...],
) -> LiteratureClaimBenchmarkReport:
    """Evaluate only frozen approved Claim labels; never invent scientific truth."""

    if not cases:
        raise ValueError("LiteratureClaim benchmark requires at least one case")
    validate_frozen_benchmark(benchmark)
    benchmark_claims = {item.claim_id: item for item in benchmark.claims}
    ordered_cases = tuple(sorted(cases, key=lambda item: item.case_id))
    producer = ordered_cases[0].admission.producer
    signature = _producer_signature(producer)
    results: list[LiteratureClaimBenchmarkCaseResult] = []
    claim_type_counts: Counter[object] = Counter()
    rejection_case_ids: dict[
        LiteratureClaimRejectionReason, list[str]
    ] = defaultdict(list)
    schema_valid_count = 0
    evidence_supported_count = 0
    evidence_total_count = 0
    scientific_exact_count = 0
    scientific_total_count = 0
    rejection_passed_count = 0
    rejection_total_count = 0
    status_counts: Counter[LiteratureClaimStatus] = Counter()

    for case in ordered_cases:
        expected = None
        if case.case_kind is LiteratureClaimBenchmarkCaseKind.scientific_label:
            expected = benchmark_claims.get(case.benchmark_claim_id or "")
            if (
                expected is None
                or expected.review_status is not BenchmarkReviewStatus.approved
            ):
                raise ValueError(
                    "scientific cases must reference approved D-01 Claim labels"
                )
        if _producer_signature(case.admission.producer) != signature:
            raise ValueError(
                "one Claim benchmark report requires one Prompt/model/parameter version"
            )
        record = _select_record(case)
        schema_valid = record is not None or (
            case.admission.rejection_reason
            not in {
                LiteratureClaimRejectionReason.invalid_json,
                LiteratureClaimRejectionReason.schema_invalid,
            }
        )
        schema_valid_count += int(schema_valid)
        scientific_compared = expected is not None and schema_valid and record is not None
        supported, total = (
            _evidence_counts(case, record) if scientific_compared else (0, 0)
        )
        evidence_supported_count += supported
        evidence_total_count += total
        scientific_exact = (
            _matches_approved_claim(record, expected)
            if scientific_compared and record is not None and expected is not None
            else None
        )
        scientific_total_count += int(scientific_compared)
        scientific_exact_count += int(scientific_exact is True)
        status = (
            record.status
            if record is not None
            else case.admission.admission_status
        )
        failure_stage = (
            record.failure_stage
            if record is not None
            else case.admission.failure_stage
        )
        reason = (
            record.rejection_reason
            if record is not None
            else case.admission.rejection_reason
        )
        rejection_case_pass = None
        if case.case_kind is LiteratureClaimBenchmarkCaseKind.rejection_case:
            rejection_total_count += 1
            rejection_case_pass = (
                status is LiteratureClaimStatus.rejected
                and failure_stage is case.expected_failure_stage
                and reason is case.expected_rejection_reason
            )
            rejection_passed_count += int(rejection_case_pass)
        status_counts[status] += 1
        if scientific_compared and expected is not None:
            claim_type_counts[expected.claim_type] += 1
        if reason is not None:
            rejection_case_ids[reason].append(case.case_id)
        results.append(
            LiteratureClaimBenchmarkCaseResult(
                case_id=case.case_id,
                case_kind=case.case_kind,
                benchmark_claim_id=case.benchmark_claim_id,
                claim_type=None if expected is None else expected.claim_type,
                expected_failure_stage=case.expected_failure_stage,
                expected_rejection_reason=case.expected_rejection_reason,
                schema_valid=schema_valid,
                evidence_items_supported=supported,
                evidence_items_total=total,
                scientific_label_compared=scientific_compared,
                scientific_label_exact_match=scientific_exact,
                rejection_case_pass=rejection_case_pass,
                status=status,
                failure_stage=failure_stage,
                rejection_reason=reason,
                input_hash=case.admission.producer.input_hash,
                output_hash=case.admission.output_hash,
            )
        )

    type_counts = tuple(
        LiteratureClaimTypeCount(claim_type=claim_type, count=count)
        for claim_type, count in sorted(
            claim_type_counts.items(), key=lambda item: item[0].value
        )
    )
    rejection_counts = tuple(
        LiteratureClaimRejectionCount(
            rejection_reason=reason,
            count=len(case_ids),
            sample_case_ids=tuple(sorted(case_ids)),
        )
        for reason, case_ids in sorted(
            rejection_case_ids.items(), key=lambda item: item[0].value
        )
    )
    typed_status_counts = LiteratureClaimStatusCounts(
        accepted=status_counts[LiteratureClaimStatus.accepted],
        candidate=status_counts[LiteratureClaimStatus.candidate],
        rejected=status_counts[LiteratureClaimStatus.rejected],
    )
    input_payload = {
        "benchmark_id": benchmark.benchmark_id,
        "benchmark_schema_version": benchmark.schema_version,
        "benchmark_version": benchmark.benchmark_version,
        "benchmark_scientific_payload_hash": benchmark.scientific_payload_hash,
        "benchmark_content_hash": benchmark.content_hash,
        "prompt_name": producer.prompt_name,
        "prompt_version": producer.prompt_version,
        "prompt_hash": producer.prompt_hash,
        "claim_schema_version": producer.schema_version,
        "model_name": producer.model_name,
        "parameters_version": producer.parameters_version,
        "parameters_hash": producer.parameters_hash,
        "producer_version": producer.producer_version,
        "cases": [
            item.model_dump(mode="json", exclude_none=True) for item in results
        ],
    }
    input_hash = compute_canonical_payload_hash(input_payload)
    report_payload = {
        "report_version": "1.0.0",
        **{key: value for key, value in input_payload.items() if key != "cases"},
        "sample_count": len(results),
        "claim_type_counts": [
            item.model_dump(mode="json") for item in type_counts
        ],
        "schema_items_valid": schema_valid_count,
        "schema_items_total": len(results),
        "schema_pass_rate": schema_valid_count / len(results),
        "rejection_cases_passed": rejection_passed_count,
        "rejection_cases_total": rejection_total_count,
        "rejection_case_pass_rate": (
            rejection_passed_count / rejection_total_count
            if rejection_total_count
            else None
        ),
        "evidence_items_supported": evidence_supported_count,
        "evidence_items_total": evidence_total_count,
        "evidence_coverage_rate": (
            evidence_supported_count / evidence_total_count
            if evidence_total_count
            else None
        ),
        "scientific_label_items_exact": scientific_exact_count,
        "scientific_label_items_total": scientific_total_count,
        "scientific_label_exact_match_rate": (
            scientific_exact_count / scientific_total_count
            if scientific_total_count
            else None
        ),
        "status_counts": typed_status_counts.model_dump(mode="json"),
        "rejection_counts": [
            item.model_dump(mode="json") for item in rejection_counts
        ],
        "cases": [
            item.model_dump(mode="json", exclude_none=True) for item in results
        ],
        "input_hash": input_hash,
        "output_hash": "sha256:" + "0" * 64,
    }
    output_hash = compute_literature_claim_benchmark_output_hash(report_payload)
    report_payload["output_hash"] = output_hash
    return LiteratureClaimBenchmarkReport.model_validate(report_payload)


def validate_scientific_label_coverage(
    benchmark: BenchmarkPackage,
    cases: tuple[LiteratureClaimBenchmarkEvaluationCase, ...],
) -> None:
    """Require the formal suite to cover every approved D-01 Claim exactly once."""

    validate_frozen_benchmark(benchmark)
    expected = tuple(
        sorted(
            item.claim_id
            for item in benchmark.claims
            if item.review_status is BenchmarkReviewStatus.approved
        )
    )
    actual = tuple(
        sorted(
            case.benchmark_claim_id
            for case in cases
            if case.case_kind
            is LiteratureClaimBenchmarkCaseKind.scientific_label
            and case.benchmark_claim_id is not None
        )
    )
    if actual != expected:
        raise ValueError(
            "formal D-07 benchmark must cover every approved D-01 Claim exactly once"
        )


def _select_record(
    case: LiteratureClaimBenchmarkEvaluationCase,
) -> LiteratureClaimCandidate | None:
    if case.record_claim_id is None:
        if len(case.admission.records) > 1:
            raise ValueError("multi-record benchmark case requires record_claim_id")
        return case.admission.records[0] if case.admission.records else None
    matches = tuple(
        item
        for item in case.admission.records
        if item.claim_id == case.record_claim_id
    )
    if len(matches) != 1:
        raise ValueError("record_claim_id must identify exactly one admission record")
    return matches[0]


def _evidence_counts(
    case: LiteratureClaimBenchmarkEvaluationCase,
    record: LiteratureClaimCandidate | None,
) -> tuple[int, int]:
    if record is None:
        return 0, 0
    candidate = case.admission.publisher_candidate
    references = (
        {}
        if candidate is None
        else {
            item.evidence_id: item
            for item in candidate.evidence_references
            if item.claim_id == record.claim_id
        }
    )
    supported = sum(
        evidence_id in references
        and references[evidence_id].status == "supported"
        for evidence_id in record.evidence_ids
    )
    return supported, len(record.evidence_ids)


def _matches_approved_claim(
    actual: LiteratureClaimCandidate,
    expected: BenchmarkClaim,
) -> bool:
    """Exact frozen-label comparison; no fuzzy similarity or confidence score."""

    return (
        actual.paper_id == expected.paper_id
        and actual.claim_type == expected.claim_type
        and actual.text == expected.text
        and actual.normalized_text == expected.normalized_text
        and actual.conditions
        == tuple(sorted(expected.conditions, key=str.casefold))
        and actual.evidence_ids == tuple(sorted(expected.evidence_ids))
        and actual.status.value == expected.status.value
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
        )
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate serialized D-07 admission cases against frozen D-01 Claims."
    )
    parser.add_argument(
        "--cases",
        type=Path,
        help=(
            "Optional JSON array of LiteratureClaimBenchmarkEvaluationCase values; "
            "omit to generate the formal suite deterministically from tracked D-01."
        ),
    )
    parser.add_argument(
        "--cases-output",
        type=Path,
        help="Optionally write the sorted generated/loaded case array for inspection.",
    )
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    benchmark = load_frozen_benchmark()
    if args.cases is None:
        from .claim_benchmark_cases import build_frozen_claim_benchmark_cases

        cases = build_frozen_claim_benchmark_cases(benchmark)
    else:
        cases = _CASE_ADAPTER.validate_json(args.cases.read_text(encoding="utf-8"))
    cases = tuple(sorted(cases, key=lambda item: item.case_id))
    validate_scientific_label_coverage(benchmark, cases)
    if args.cases_output is not None:
        args.cases_output.parent.mkdir(parents=True, exist_ok=True)
        args.cases_output.write_text(
            _stable_json(
                [item.model_dump(mode="json", exclude_none=True) for item in cases]
            ),
            encoding="utf-8",
            newline="\n",
        )
    report = evaluate_literature_claims(benchmark=benchmark, cases=cases)
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
