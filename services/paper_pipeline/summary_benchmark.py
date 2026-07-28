"""Reproducible D-03 evaluation against the frozen D-01 package."""

from __future__ import annotations

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.paper_benchmark import BenchmarkPackage, BenchmarkReviewStatus
from app.schemas.paper_summary import (
    PaperSummaryBenchmarkCaseResult,
    PaperSummaryBenchmarkEvaluationCase,
    PaperSummaryBenchmarkReport,
    PaperSummarySupportStatus,
    compute_paper_summary_benchmark_output_hash,
)


def evaluate_paper_summaries(
    *,
    benchmark: BenchmarkPackage,
    cases: tuple[PaperSummaryBenchmarkEvaluationCase, ...],
    human_review_sample_ids: tuple[str, ...],
) -> PaperSummaryBenchmarkReport:
    """Report frozen metrics without calling a model or modifying Benchmark truth."""

    if not cases:
        raise ValueError("PaperSummary benchmark requires at least one evaluation case")
    benchmark_summaries = {
        summary.summary_id: summary for summary in benchmark.paper_summaries
    }
    for summary_id in human_review_sample_ids:
        summary = benchmark_summaries.get(summary_id)
        if summary is None or summary.review_status is not BenchmarkReviewStatus.approved:
            raise ValueError("human review samples must reference approved D-01 summaries")

    producer = cases[0].admission.producer
    producer_signature = (
        producer.prompt_name,
        producer.prompt_version,
        producer.prompt_hash,
        producer.model_name,
        producer.parameters_version,
        producer.parameters_hash,
    )
    case_results: list[PaperSummaryBenchmarkCaseResult] = []
    schema_valid_count = 0
    core_item_count = 0
    supported_core_item_count = 0
    unsupported_expected_count = 0
    unsupported_blocked_count = 0
    for case in cases:
        if case.benchmark_summary_id not in benchmark_summaries:
            raise ValueError("evaluation case must reference a D-01 PaperSummary")
        candidate_producer = case.admission.producer
        if (
            candidate_producer.prompt_name,
            candidate_producer.prompt_version,
            candidate_producer.prompt_hash,
            candidate_producer.model_name,
            candidate_producer.parameters_version,
            candidate_producer.parameters_hash,
        ) != producer_signature:
            raise ValueError("one benchmark report requires one Prompt/model/parameter version")
        summary = case.admission.summary
        schema_valid = summary is not None
        schema_valid_count += int(schema_valid)
        core_statements = () if summary is None else summary.findings + summary.limitations
        core_by_id = {item.statement_id: item for item in core_statements}
        if len(core_by_id) != len(core_statements):
            raise ValueError("benchmark Summary contains duplicate core statement ids")
        case_supported_count = sum(
            item.status is PaperSummarySupportStatus.supported
            for item in core_statements
        )
        case_core_count = len(core_statements)
        core_item_count += case_core_count
        supported_core_item_count += case_supported_count
        unsupported_expected = bool(case.unsupported_statement_ids)
        if unsupported_expected:
            unsupported_expected_count += len(case.unsupported_statement_ids)
            unknown = set(case.unsupported_statement_ids) - set(core_by_id)
            if unknown:
                raise ValueError("unsupported target must identify a finding or limitation")
            blocked_targets = tuple(
                item
                for item in case.unsupported_statement_ids
                if core_by_id[item].status is not PaperSummarySupportStatus.supported
            )
            unsupported_blocked = len(blocked_targets) == len(
                case.unsupported_statement_ids
            )
            unsupported_blocked_count += len(blocked_targets)
        else:
            unsupported_blocked = False
        case_results.append(
            PaperSummaryBenchmarkCaseResult(
                case_id=case.case_id,
                benchmark_summary_id=case.benchmark_summary_id,
                schema_valid=schema_valid,
                core_item_count=case_core_count,
                supported_core_item_count=case_supported_count,
                unsupported_expected=unsupported_expected,
                unsupported_blocked=unsupported_blocked,
                input_hash=candidate_producer.input_hash,
                model_response_hash=candidate_producer.model_response_hash,
                output_hash=None if summary is None else summary.output_hash,
            )
        )
    input_hash = compute_canonical_payload_hash(
        {
            "benchmark_id": benchmark.benchmark_id,
            "benchmark_schema_version": benchmark.schema_version,
            "benchmark_version": benchmark.benchmark_version,
            "benchmark_scientific_payload_hash": benchmark.scientific_payload_hash,
            "benchmark_content_hash": benchmark.content_hash,
            "prompt_name": producer.prompt_name,
            "prompt_version": producer.prompt_version,
            "prompt_hash": producer.prompt_hash,
            "model_name": producer.model_name,
            "parameters_version": producer.parameters_version,
            "parameters_hash": producer.parameters_hash,
            "cases": [item.model_dump(mode="json", exclude_none=True) for item in case_results],
            "human_review_sample_ids": human_review_sample_ids,
        }
    )
    payload = {
        "report_version": "1.0.0",
        "benchmark_id": benchmark.benchmark_id,
        "benchmark_schema_version": benchmark.schema_version,
        "benchmark_version": benchmark.benchmark_version,
        "benchmark_scientific_payload_hash": benchmark.scientific_payload_hash,
        "benchmark_content_hash": benchmark.content_hash,
        "prompt_name": producer.prompt_name,
        "prompt_version": producer.prompt_version,
        "prompt_hash": producer.prompt_hash,
        "model_name": producer.model_name,
        "parameters_version": producer.parameters_version,
        "parameters_hash": producer.parameters_hash,
        "cases": [item.model_dump(mode="json", exclude_none=True) for item in case_results],
        "schema_pass_rate": schema_valid_count / len(cases),
        "evidence_coverage": (
            supported_core_item_count / core_item_count if core_item_count else 0.0
        ),
        "unsupported_block_rate": (
            unsupported_blocked_count / unsupported_expected_count
            if unsupported_expected_count
            else None
        ),
        "human_review_sample_ids": human_review_sample_ids,
        "input_hash": input_hash,
        "output_hash": "sha256:" + "0" * 64,
    }
    output_hash = compute_paper_summary_benchmark_output_hash(payload)
    payload["output_hash"] = output_hash
    return PaperSummaryBenchmarkReport.model_validate(payload)
