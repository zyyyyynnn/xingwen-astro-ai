from __future__ import annotations

from datetime import timedelta
import json
from pathlib import Path
import sys

import pytest
from pydantic import TypeAdapter, ValidationError

from app.schemas.literature_relation import (
    LiteratureRelationBenchmarkCaseKind,
    LiteratureRelationBenchmarkEvaluationCase,
    LiteratureRelationBenchmarkReport,
    LiteratureRelationStatusCounts,
)
from app.schemas.paper_benchmark import BenchmarkPackage, BenchmarkReviewStatus
from services.paper_pipeline.benchmark import load_frozen_benchmark
from services.paper_pipeline.constants import (
    FROZEN_BENCHMARK_CONTENT_HASH,
    FROZEN_BENCHMARK_SCHEMA_VERSION,
    FROZEN_BENCHMARK_VERSION,
    FROZEN_SCIENTIFIC_PAYLOAD_HASH,
)
from services.paper_pipeline.relation_benchmark import (
    evaluate_literature_relations,
    main as relation_benchmark_main,
    validate_formal_case_coverage,
)
from services.paper_pipeline.relation_benchmark_cases import (
    FORMAL_REJECTION_EXPECTATIONS,
    build_frozen_relation_benchmark_cases,
)


_CASE_ADAPTER = TypeAdapter(tuple[LiteratureRelationBenchmarkEvaluationCase, ...])


@pytest.fixture(scope="module")
def benchmark() -> BenchmarkPackage:
    return load_frozen_benchmark()


@pytest.fixture(scope="module")
def cases(
    benchmark: BenchmarkPackage,
) -> tuple[LiteratureRelationBenchmarkEvaluationCase, ...]:
    return build_frozen_relation_benchmark_cases(benchmark)


def test_formal_paper_benchmark_relation_benchmark_is_reproducible_and_exact(
    benchmark: BenchmarkPackage,
    cases: tuple[LiteratureRelationBenchmarkEvaluationCase, ...],
) -> None:
    approved_relations = {
        item.relation_id
        for item in benchmark.relations
        if item.review_status is BenchmarkReviewStatus.approved
    }
    approved_traces = {
        item.trace_id
        for item in benchmark.reasoning_traces
        if item.review_status is BenchmarkReviewStatus.approved
    }
    scientific = tuple(
        item
        for item in cases
        if item.case_kind is LiteratureRelationBenchmarkCaseKind.scientific_label
    )

    validate_formal_case_coverage(benchmark, cases)
    first = evaluate_literature_relations(benchmark=benchmark, cases=cases)
    second = evaluate_literature_relations(
        benchmark=benchmark,
        cases=tuple(reversed(cases)),
    )

    assert first == second
    assert {item.benchmark_relation_id for item in scientific} == approved_relations
    assert {item.benchmark_trace_id for item in scientific} == approved_traces
    frozen_traces = {item.trace_id: item for item in benchmark.reasoning_traces}
    for case in scientific:
        expected_trace = frozen_traces[case.benchmark_trace_id or ""]
        admitted_trace = case.admission.reasoning_traces[0]
        assert expected_trace.uncertainty in admitted_trace.limitations
    assert first.benchmark_schema_version == FROZEN_BENCHMARK_SCHEMA_VERSION
    assert first.benchmark_version == FROZEN_BENCHMARK_VERSION
    assert first.benchmark_scientific_payload_hash == FROZEN_SCIENTIFIC_PAYLOAD_HASH
    assert first.benchmark_content_hash == FROZEN_BENCHMARK_CONTENT_HASH
    assert first.sample_count == 24
    assert first.schema_items_valid == 21
    assert first.schema_items_total == 24
    assert first.schema_pass_rate == 21 / 24
    assert first.scientific_pair_items_matched == 4
    assert first.scientific_pair_items_total == 4
    assert first.scientific_pair_coverage_rate == 1.0
    assert first.scientific_relation_items_exact == 4
    assert first.scientific_relation_items_total == 4
    assert first.scientific_relation_exact_match_rate == 1.0
    assert first.relation_evidence_items_supported == 8
    assert first.relation_evidence_items_total == 8
    assert first.relation_evidence_coverage_rate == 1.0
    assert first.trace_step_evidence_items_supported == 13
    assert first.trace_step_evidence_items_total == 13
    assert first.trace_step_evidence_coverage_rate == 1.0
    assert first.evidence_less_cases_blocked == 1
    assert first.evidence_less_cases_total == 1
    assert first.evidence_less_block_rate == 1.0
    assert first.rejection_cases_passed == len(FORMAL_REJECTION_EXPECTATIONS)
    assert first.rejection_cases_total == len(FORMAL_REJECTION_EXPECTATIONS)
    assert first.rejection_case_pass_rate == 1.0
    assert first.scientific_status_counts == LiteratureRelationStatusCounts(
        accepted=1,
        candidate=1,
        rejected=2,
    )
    assert {
        item.relation_type.value: item.count for item in first.relation_type_counts
    } == {
        "contradicts": 1,
        "derived_from": 1,
        "extends": 1,
        "limits": 1,
    }
    assert first.confidence_items_total == 4
    assert first.confidence_assessed_count == 4
    assert first.confidence_not_evaluable_count == 0
    assert first.confidence_calibrated_count == 4
    assert [item.count for item in first.confidence_distribution] == [0, 1, 3]
    assert first.input_hash.startswith("sha256:")
    assert first.output_hash.startswith("sha256:")


def test_formal_cases_consume_resolved_literature_claim_artifact_versions(
    cases: tuple[LiteratureRelationBenchmarkEvaluationCase, ...],
) -> None:
    scientific = tuple(
        item
        for item in cases
        if item.case_kind is LiteratureRelationBenchmarkCaseKind.scientific_label
    )

    for case in scientific:
        record = case.admission.records[0]
        references = case.admission.producer.input_versions.claim_artifact_versions
        claim_ids = {
            claim_id for reference in references for claim_id in reference.claim_ids
        }
        summary_version_ids = {
            version_id
            for reference in references
            for version_id in reference.paper_summary_artifact_version_ids
        }
        assert len(references) == 2
        assert all(reference.schema_version == "1.0.0" for reference in references)
        assert all(reference.content_hash is not None for reference in references)
        assert all(reference.output_hash is not None for reference in references)
        assert all(reference.project_id == "project.literature_relation_benchmark" for reference in references)
        assert {record.source_claim_id, record.target_claim_id}.issubset(claim_ids)
        assert record.source_claim_artifact_version_id in {
            item.artifact_version_id for item in references
        }
        assert record.target_claim_artifact_version_id in {
            item.artifact_version_id for item in references
        }
        assert record.source_paper_summary_artifact_version_id in summary_version_ids
        assert record.target_paper_summary_artifact_version_id in summary_version_ids
        assert record.confidence is not None
        assert record.confidence.decision is record.status
        assert record.confidence.subject.source_claim_artifact_version_id == (
            record.source_claim_artifact_version_id
        )
        assert record.confidence.subject.source_claim_id == record.source_claim_id
        assert record.confidence.subject.target_claim_artifact_version_id == (
            record.target_claim_artifact_version_id
        )
        assert record.confidence.subject.target_claim_id == record.target_claim_id
        assert record.confidence.subject.relation_type is record.relation_type


def test_relation_benchmark_metric_denominators_and_empty_subsets(
    benchmark: BenchmarkPackage,
    cases: tuple[LiteratureRelationBenchmarkEvaluationCase, ...],
) -> None:
    scientific = tuple(
        item
        for item in cases
        if item.case_kind is LiteratureRelationBenchmarkCaseKind.scientific_label
    )
    rejections = tuple(
        item
        for item in cases
        if item.case_kind is LiteratureRelationBenchmarkCaseKind.rejection_case
    )

    scientific_report = evaluate_literature_relations(
        benchmark=benchmark,
        cases=scientific,
    )
    rejection_report = evaluate_literature_relations(
        benchmark=benchmark,
        cases=rejections,
    )

    assert scientific_report.schema_pass_rate == 1.0
    assert scientific_report.scientific_pair_coverage_rate == 1.0
    assert scientific_report.scientific_relation_exact_match_rate == 1.0
    assert scientific_report.relation_evidence_coverage_rate == 1.0
    assert scientific_report.trace_step_evidence_coverage_rate == 1.0
    assert scientific_report.evidence_less_cases_total == 0
    assert scientific_report.evidence_less_block_rate is None
    assert scientific_report.rejection_cases_total == 0
    assert scientific_report.rejection_case_pass_rate is None
    assert rejection_report.schema_items_valid == 17
    assert rejection_report.schema_items_total == 20
    assert rejection_report.schema_pass_rate == 17 / 20
    assert rejection_report.rejection_case_pass_rate == 1.0
    assert rejection_report.scientific_pair_items_total == 0
    assert rejection_report.scientific_pair_coverage_rate is None
    assert rejection_report.scientific_relation_items_total == 0
    assert rejection_report.scientific_relation_exact_match_rate is None
    assert rejection_report.relation_evidence_items_total == 0
    assert rejection_report.relation_evidence_coverage_rate is None
    assert rejection_report.trace_step_evidence_items_total == 0
    assert rejection_report.trace_step_evidence_coverage_rate is None
    assert rejection_report.confidence_items_total == 0
    assert [item.count for item in rejection_report.confidence_distribution] == [0, 0, 0]
    assert rejection_report.scientific_status_counts == LiteratureRelationStatusCounts(
        accepted=0,
        candidate=0,
        rejected=0,
    )
    assert rejection_report.relation_type_counts == ()
    with pytest.raises(ValueError, match="at least one case"):
        evaluate_literature_relations(benchmark=benchmark, cases=())


def test_candidate_pair_coverage_is_separate_from_scientific_exact_match(
    benchmark: BenchmarkPackage,
    cases: tuple[LiteratureRelationBenchmarkEvaluationCase, ...],
) -> None:
    scientific = tuple(
        item
        for item in cases
        if item.case_kind is LiteratureRelationBenchmarkCaseKind.scientific_label
    )
    case = scientific[0]
    changed_case = case.model_copy(
        update={
            "admission": case.admission.model_copy(
                update={"reasoning_traces": ()}
            )
        }
    )
    changed_cases = (changed_case, *scientific[1:])

    report = evaluate_literature_relations(
        benchmark=benchmark,
        cases=changed_cases,
    )

    assert report.scientific_pair_items_matched == 4
    assert report.scientific_pair_items_total == 4
    assert report.scientific_pair_coverage_rate == 1.0
    assert report.scientific_relation_items_exact == 3
    assert report.scientific_relation_items_total == 4
    assert report.scientific_relation_exact_match_rate == 0.75
    changed_result = next(item for item in report.cases if item.case_id == case.case_id)
    assert changed_result.scientific_label_compared is True
    assert changed_result.scientific_label_exact_match is False


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("schema_version", "1.3.1"),
        ("benchmark_version", "1.3.1"),
        ("scientific_payload_hash", "sha256:" + "1" * 64),
        ("content_hash", "sha256:" + "2" * 64),
    ),
)
def test_relation_benchmark_rejects_paper_benchmark_identity_mismatch(
    benchmark: BenchmarkPackage,
    cases: tuple[LiteratureRelationBenchmarkEvaluationCase, ...],
    field: str,
    value: str,
) -> None:
    changed = benchmark.model_copy(update={field: value})

    with pytest.raises(ValueError, match="frozen paper acquisition benchmark identity mismatch"):
        evaluate_literature_relations(benchmark=changed, cases=cases)


def test_formal_relation_benchmark_rejects_incomplete_coverage(
    benchmark: BenchmarkPackage,
    cases: tuple[LiteratureRelationBenchmarkEvaluationCase, ...],
) -> None:
    without_scientific = tuple(
        item
        for item in cases
        if item.case_id
        != "scientific.relation.revised_tic_extends_initial_tic"
    )
    without_rejection = tuple(
        item for item in cases if item.case_id != "rejection.trace_unsafe"
    )

    with pytest.raises(ValueError, match="every approved Paper Acquisition Benchmark Relation/Trace"):
        validate_formal_case_coverage(benchmark, without_scientific)
    with pytest.raises(ValueError, match="fixed rejection suite exactly"):
        validate_formal_case_coverage(benchmark, without_rejection)


def test_relation_benchmark_rejects_mixed_producer_signatures(
    benchmark: BenchmarkPackage,
    cases: tuple[LiteratureRelationBenchmarkEvaluationCase, ...],
) -> None:
    selected = tuple(
        item
        for item in cases
        if item.case_kind is LiteratureRelationBenchmarkCaseKind.scientific_label
    )[:2]
    changed_producer = selected[1].admission.producer.model_copy(
        update={"model_name": "different-model-policy"}
    )
    changed = selected[1].model_copy(
        update={
            "admission": selected[1].admission.model_copy(
                update={"producer": changed_producer}
            )
        }
    )

    with pytest.raises(ValueError, match="one Prompt/model/parameter policy"):
        evaluate_literature_relations(
            benchmark=benchmark,
            cases=(selected[0], changed),
        )

def test_relation_benchmark_ignores_execution_runtime_in_report_hash(
    benchmark: BenchmarkPackage,
    cases: tuple[LiteratureRelationBenchmarkEvaluationCase, ...],
) -> None:
    case = next(
        item
        for item in cases
        if item.case_id
        == "scientific.relation.revised_tic_extends_initial_tic"
    )
    execution_id = "execution.literature_relation.runtime_variant"
    producer = case.admission.producer.model_copy(
        update={
            "execution_id": execution_id,
            "run_id": "run.literature_relation.runtime_variant",
            "started_at": case.admission.producer.started_at + timedelta(minutes=5),
            "finished_at": case.admission.producer.finished_at + timedelta(minutes=5),
            "latency_ms": 987,
        }
    )
    records = tuple(
        item.model_copy(update={"producer_execution_id": execution_id})
        for item in case.admission.records
    )
    traces = tuple(
        item.model_copy(update={"producer_execution_id": execution_id})
        for item in case.admission.reasoning_traces
    )
    changed_case = case.model_copy(
        update={
            "admission": case.admission.model_copy(
                update={
                    "producer": producer,
                    "records": records,
                    "reasoning_traces": traces,
                }
            )
        }
    )

    first = evaluate_literature_relations(benchmark=benchmark, cases=(case,))
    second = evaluate_literature_relations(
        benchmark=benchmark,
        cases=(changed_case,),
    )

    assert case.admission.producer.execution_id != producer.execution_id
    assert first == second
    assert first.input_hash == second.input_hash
    assert first.output_hash == second.output_hash


def test_relation_benchmark_report_recomputes_aggregate_counts(
    benchmark: BenchmarkPackage,
    cases: tuple[LiteratureRelationBenchmarkEvaluationCase, ...],
) -> None:
    report = evaluate_literature_relations(benchmark=benchmark, cases=cases)
    payload = report.model_dump(mode="json")
    payload["sample_count"] += 1

    with pytest.raises(ValidationError, match="sample_count must equal case count"):
        LiteratureRelationBenchmarkReport.model_validate(payload)


def test_relation_benchmark_cli_generates_and_replays_only_the_full_stable_suite(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    first_report_path = tmp_path / "report-first.json"
    second_report_path = tmp_path / "report-second.json"
    replay_report_path = tmp_path / "report-replay.json"
    first_cases_path = tmp_path / "cases-first.json"
    second_cases_path = tmp_path / "cases-second.json"
    for report_path, cases_path in (
        (first_report_path, first_cases_path),
        (second_report_path, second_cases_path),
    ):
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "relation_benchmark",
                "--output",
                str(report_path),
                "--cases-output",
                str(cases_path),
            ],
        )
        assert relation_benchmark_main() == 0

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "relation_benchmark",
            "--cases",
            str(first_cases_path),
            "--output",
            str(replay_report_path),
        ],
    )
    assert relation_benchmark_main() == 0

    report = LiteratureRelationBenchmarkReport.model_validate_json(
        first_report_path.read_text(encoding="utf-8")
    )
    serialized_cases = _CASE_ADAPTER.validate_json(
        first_cases_path.read_text(encoding="utf-8")
    )
    assert report.sample_count == 24
    assert report.scientific_relation_items_exact == 4
    assert report.scientific_relation_items_total == 4
    assert report.relation_evidence_items_total == 8
    assert report.trace_step_evidence_items_total == 13
    assert len(serialized_cases) == 24
    assert first_report_path.read_bytes() == second_report_path.read_bytes()
    assert first_report_path.read_bytes() == replay_report_path.read_bytes()
    assert first_cases_path.read_bytes() == second_cases_path.read_bytes()
    assert b"\r" not in first_report_path.read_bytes()
    assert b"\r" not in first_cases_path.read_bytes()

    favorable_subset_path = tmp_path / "favorable-subset.json"
    favorable_subset = [
        item
        for item in json.loads(first_cases_path.read_text(encoding="utf-8"))
        if item["case_id"] != "rejection.trace_unsafe"
    ]
    favorable_subset_path.write_text(
        json.dumps(favorable_subset, ensure_ascii=False),
        encoding="utf-8",
        newline="\n",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "relation_benchmark",
            "--cases",
            str(favorable_subset_path),
            "--output",
            str(tmp_path / "subset-report.json"),
        ],
    )
    with pytest.raises(ValueError, match="fixed rejection suite exactly"):
        relation_benchmark_main()
