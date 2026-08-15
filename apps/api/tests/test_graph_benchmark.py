from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest
from pydantic import TypeAdapter, ValidationError

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.enums import GraphEdgeType, GraphNodeType
from app.schemas.graph_artifact import (
    GRAPH_BENCHMARK_DISCLAIMER,
    GraphBenchmarkCaseKind,
    GraphBenchmarkDenominatorScope,
    GraphBenchmarkEvaluationCase,
    GraphBenchmarkReport,
    GraphIntegrityStatus,
    GraphRejectionReason,
    compute_graph_benchmark_output_hash,
)
from app.schemas.paper_benchmark import (
    BenchmarkAdmissionStatus,
    BenchmarkPackage,
    BenchmarkReviewStatus,
)
from services.graph_pipeline.benchmark import (
    FORMAL_REJECTION_EXPECTATIONS,
    FORMAL_SIZE_EXPECTATIONS,
    build_frozen_graph_benchmark_cases,
    evaluate_graph_benchmark,
    main as graph_benchmark_main,
    validate_formal_case_coverage,
    validate_frozen_graph_label,
)
from services.paper_pipeline.benchmark import load_frozen_benchmark
from services.paper_pipeline.constants import (
    FROZEN_BENCHMARK_CONTENT_HASH,
    FROZEN_BENCHMARK_SCHEMA_VERSION,
    FROZEN_BENCHMARK_VERSION,
    FROZEN_SCIENTIFIC_PAYLOAD_HASH,
)


_CASE_ADAPTER = TypeAdapter(tuple[GraphBenchmarkEvaluationCase, ...])


@pytest.fixture(scope="module")
def benchmark() -> BenchmarkPackage:
    return load_frozen_benchmark()


@pytest.fixture(scope="module")
def cases(
    benchmark: BenchmarkPackage,
) -> tuple[GraphBenchmarkEvaluationCase, ...]:
    return build_frozen_graph_benchmark_cases(benchmark)


def test_frozen_paper_benchmark_graph_label_is_exact_and_directional(
    benchmark: BenchmarkPackage,
) -> None:
    validate_frozen_graph_label(benchmark)

    assert benchmark.schema_version == FROZEN_BENCHMARK_SCHEMA_VERSION == "2.0.0"
    assert benchmark.benchmark_version == FROZEN_BENCHMARK_VERSION == "2.0.0"
    assert benchmark.scientific_payload_hash == FROZEN_SCIENTIFIC_PAYLOAD_HASH
    assert benchmark.content_hash == FROZEN_BENCHMARK_CONTENT_HASH
    assert len(benchmark.graph.nodes) == 6
    assert len(benchmark.graph.edges) == 2
    assert sum(
        item.node_type is GraphNodeType.paper for item in benchmark.graph.nodes
    ) == 3
    assert sum(
        item.node_type is GraphNodeType.claim for item in benchmark.graph.nodes
    ) == 3
    assert set(benchmark.graph_taxonomy.allowed_node_types) == {
        GraphNodeType.paper,
        GraphNodeType.claim,
    }
    assert set(benchmark.graph_taxonomy.allowed_edge_types) == {
        GraphEdgeType.supports_finding,
        GraphEdgeType.extends,
        GraphEdgeType.derived_from,
    }

    cross = next(item for item in benchmark.graph.edges if item.cross_document)
    structural = next(item for item in benchmark.graph.edges if not item.cross_document)
    relation = next(
        item for item in benchmark.relations if item.relation_id == cross.relation_id
    )
    trace = next(
        item
        for item in benchmark.reasoning_traces
        if item.trace_id == cross.reasoning_trace_id
    )
    nodes = {item.node_id: item for item in benchmark.graph.nodes}
    assert structural.edge_type is GraphEdgeType.supports_finding
    assert nodes[structural.source].node_type is GraphNodeType.paper
    assert nodes[structural.target].node_type is GraphNodeType.claim
    assert cross.edge_type is GraphEdgeType.extends
    assert relation.status is BenchmarkAdmissionStatus.accepted
    assert relation.review_status is BenchmarkReviewStatus.approved
    assert nodes[cross.source].ref_id == relation.source_claim_id
    assert nodes[cross.target].ref_id == relation.target_claim_id
    assert trace.relation_id == relation.relation_id
    assert trace.premise_claim_ids == (
        relation.source_claim_id,
        relation.target_claim_id,
    )
    assert sum(len(item.evidence_ids) for item in benchmark.graph.edges) == 3


def test_formal_graph_benchmark_is_complete_reproducible_and_exact(
    benchmark: BenchmarkPackage,
    cases: tuple[GraphBenchmarkEvaluationCase, ...],
) -> None:
    validate_formal_case_coverage(benchmark, cases)
    first = evaluate_graph_benchmark(benchmark=benchmark, cases=cases)
    second = evaluate_graph_benchmark(
        benchmark=benchmark,
        cases=tuple(reversed(cases)),
    )

    assert first == second
    assert len(cases) == (
        2 + len(FORMAL_REJECTION_EXPECTATIONS) + len(FORMAL_SIZE_EXPECTATIONS)
    )
    assert first.expected_scientific_node_count == 6
    assert first.expected_scientific_edge_count == 2
    assert first.disclaimer == GRAPH_BENCHMARK_DISCLAIMER
    assert first.full_graph_exact_match_rate.numerator == 1
    assert first.full_graph_exact_match_rate.denominator == 1
    assert first.full_graph_exact_match_rate.rate == 1.0
    assert (
        first.full_graph_exact_match_rate.denominator_scope
        is GraphBenchmarkDenominatorScope.paper_benchmark_scientific_graph_cases
    )
    assert first.node_exact_match_rate.numerator == 6
    assert first.node_exact_match_rate.denominator == 6
    assert first.node_exact_match_rate.rate == 1.0
    assert first.edge_exact_match_rate.numerator == 2
    assert first.edge_exact_match_rate.denominator == 2
    assert first.edge_exact_match_rate.rate == 1.0
    assert first.evidence_coverage_rate.numerator == 3
    assert first.evidence_coverage_rate.denominator == 3
    assert first.evidence_coverage_rate.rate == 1.0
    assert first.accepted_relation_coverage_rate.numerator == 1
    assert first.accepted_relation_coverage_rate.denominator == 1
    assert first.reasoning_trace_coverage_rate.numerator == 1
    assert first.reasoning_trace_coverage_rate.denominator == 1
    assert first.nonaccepted_relation_exclusion_rate.numerator == 3
    assert first.nonaccepted_relation_exclusion_rate.denominator == 3
    assert first.nonaccepted_relation_exclusion_rate.rate == 1.0
    assert first.stable_identity_order_rate.numerator == 3
    assert first.stable_identity_order_rate.denominator == 3
    assert first.data_mapping_fixture_pass_rate.numerator == 1
    assert first.data_mapping_fixture_pass_rate.denominator == 1
    assert first.data_mapping_fixture_pass_rate.rate == 1.0
    assert first.rejection_case_pass_rate.numerator == len(
        FORMAL_REJECTION_EXPECTATIONS
    )
    assert first.rejection_case_pass_rate.denominator == len(
        FORMAL_REJECTION_EXPECTATIONS
    )
    assert first.rejection_case_pass_rate.rate == 1.0
    assert first.size_boundary_pass_rate.numerator == len(FORMAL_SIZE_EXPECTATIONS)
    assert first.size_boundary_pass_rate.denominator == len(FORMAL_SIZE_EXPECTATIONS)
    assert first.size_boundary_pass_rate.rate == 1.0
    assert first.schema_pass_rate.numerator == len(cases) - 2
    assert first.schema_pass_rate.denominator == len(cases)
    assert first.integrity_pass_count == 3
    assert first.integrity_fail_count == len(cases) - 3
    assert first.unexpected_node_count == 0
    assert first.unexpected_edge_count == 0
    assert first.input_hash.startswith("sha256:")
    assert first.output_hash.startswith("sha256:")


def test_fixed_negative_suite_hits_its_exact_first_gate(
    benchmark: BenchmarkPackage,
    cases: tuple[GraphBenchmarkEvaluationCase, ...],
) -> None:
    report = evaluate_graph_benchmark(benchmark=benchmark, cases=cases)
    results = {item.case_id: item for item in report.cases}

    for case_id, stage, reason in FORMAL_REJECTION_EXPECTATIONS:
        result = results[case_id]
        assert result.kind is GraphBenchmarkCaseKind.rejection_case
        assert result.status is GraphIntegrityStatus.failed
        assert result.failure_stage is stage
        assert result.rejection_reason is reason
        assert result.expected_result_pass is True
    assert {
        results[case_id].rejection_reason
        for case_id in (
            "rejection.nonaccepted_candidate_relation",
            "rejection.nonaccepted_limits_relation",
            "rejection.nonaccepted_contradicts_relation",
        )
    } == {GraphRejectionReason.relation_not_accepted}
    assert all(item.input_hash.startswith("sha256:") for item in report.cases)
    assert all(item.output_hash.startswith("sha256:") for item in report.cases)


def test_data_mapping_fixture_keeps_the_complete_evidence_union_separate(
    cases: tuple[GraphBenchmarkEvaluationCase, ...],
) -> None:
    case = next(
        item
        for item in cases
        if item.kind is GraphBenchmarkCaseKind.data_mapping_fixture
    )
    payload = json.loads(case.input_json)
    nodes = {item["node_id"]: item for item in payload["nodes"]}
    edge = payload["edges"][0]
    closure = payload["data_field_closures"][0]
    categories = (
        closure["mapped_selected_evidence_ids"],
        closure["mapped_unselected_evidence_ids"],
        closure["declared_null_evidence_ids"],
        closure["unresolved_evidence_ids"],
        closure["conflict_evidence_ids"],
    )

    assert case.data_level == "fixture"
    assert {item["node_type"] for item in payload["nodes"]} == {
        GraphNodeType.dataset.value,
        GraphNodeType.field.value,
    }
    assert edge["edge_type"] == GraphEdgeType.provides_field.value
    assert nodes[edge["source"]]["node_type"] == GraphNodeType.dataset.value
    assert nodes[edge["target"]]["node_type"] == GraphNodeType.field.value
    assert all(categories)
    assert set(edge["evidence_ids"]) == set().union(
        *(set(category) for category in categories)
    )
    assert not {
        GraphNodeType.research_goal.value,
        GraphNodeType.source.value,
        "row",
        "value",
    } & {item["node_type"] for item in payload["nodes"]}


def test_graph_benchmark_empty_denominators_are_null(
    benchmark: BenchmarkPackage,
    cases: tuple[GraphBenchmarkEvaluationCase, ...],
) -> None:
    scientific = tuple(
        item
        for item in cases
        if item.kind is GraphBenchmarkCaseKind.scientific_graph
    )
    rejections = tuple(
        item for item in cases if item.kind is GraphBenchmarkCaseKind.rejection_case
    )

    scientific_report = evaluate_graph_benchmark(
        benchmark=benchmark,
        cases=scientific,
    )
    rejection_report = evaluate_graph_benchmark(
        benchmark=benchmark,
        cases=rejections,
    )

    assert scientific_report.rejection_case_pass_rate.denominator == 0
    assert scientific_report.rejection_case_pass_rate.rate is None
    assert scientific_report.size_boundary_pass_rate.denominator == 0
    assert scientific_report.size_boundary_pass_rate.rate is None
    assert rejection_report.full_graph_exact_match_rate.denominator == 0
    assert rejection_report.full_graph_exact_match_rate.rate is None
    assert rejection_report.node_exact_match_rate.denominator == 0
    assert rejection_report.node_exact_match_rate.rate is None
    assert rejection_report.edge_exact_match_rate.denominator == 0
    assert rejection_report.edge_exact_match_rate.rate is None
    assert rejection_report.evidence_coverage_rate.denominator == 0
    assert rejection_report.evidence_coverage_rate.rate is None
    assert rejection_report.accepted_relation_coverage_rate.denominator == 0
    assert rejection_report.accepted_relation_coverage_rate.rate is None
    assert rejection_report.reasoning_trace_coverage_rate.denominator == 0
    assert rejection_report.reasoning_trace_coverage_rate.rate is None
    assert rejection_report.nonaccepted_relation_exclusion_rate.denominator == 0
    assert rejection_report.nonaccepted_relation_exclusion_rate.rate is None
    assert rejection_report.size_boundary_pass_rate.denominator == 0
    assert rejection_report.size_boundary_pass_rate.rate is None
    for metric in (
        scientific_report.rejection_case_pass_rate,
        scientific_report.size_boundary_pass_rate,
        rejection_report.full_graph_exact_match_rate,
        rejection_report.node_exact_match_rate,
        rejection_report.edge_exact_match_rate,
        rejection_report.evidence_coverage_rate,
        rejection_report.accepted_relation_coverage_rate,
        rejection_report.reasoning_trace_coverage_rate,
        rejection_report.nonaccepted_relation_exclusion_rate,
        rejection_report.size_boundary_pass_rate,
    ):
        assert metric.empty_set_semantics == "null"
    with pytest.raises(ValueError, match="at least one case"):
        evaluate_graph_benchmark(benchmark=benchmark, cases=())


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("schema_version", "1.3.1"),
        ("benchmark_version", "1.3.1"),
        ("scientific_payload_hash", "sha256:" + "1" * 64),
        ("content_hash", "sha256:" + "2" * 64),
    ),
)
def test_graph_benchmark_rejects_paper_benchmark_identity_drift(
    benchmark: BenchmarkPackage,
    cases: tuple[GraphBenchmarkEvaluationCase, ...],
    field: str,
    value: str,
) -> None:
    changed = benchmark.model_copy(update={field: value})

    with pytest.raises(ValueError, match="frozen paper acquisition benchmark identity mismatch"):
        evaluate_graph_benchmark(benchmark=changed, cases=cases)


def test_formal_gate_rejects_favorable_subset_and_payload_drift(
    benchmark: BenchmarkPackage,
    cases: tuple[GraphBenchmarkEvaluationCase, ...],
) -> None:
    subset = tuple(
        item for item in cases if item.case_id != "rejection.wrong_direction"
    )
    scientific = next(
        item
        for item in cases
        if item.kind is GraphBenchmarkCaseKind.scientific_graph
    )
    changed = scientific.model_copy(update={"input_json": scientific.input_json + " "})
    drifted = tuple(changed if item is scientific else item for item in cases)

    with pytest.raises(ValueError, match="fixed rejection and size suite exactly"):
        validate_formal_case_coverage(benchmark, subset)
    with pytest.raises(ValueError, match="case payload drifted"):
        validate_formal_case_coverage(benchmark, drifted)
    with pytest.raises(ValueError, match="case ids must be unique"):
        evaluate_graph_benchmark(benchmark=benchmark, cases=(cases[0], cases[0]))


def test_graph_benchmark_report_rejects_hash_stale_aggregate(
    benchmark: BenchmarkPackage,
    cases: tuple[GraphBenchmarkEvaluationCase, ...],
) -> None:
    report = evaluate_graph_benchmark(benchmark=benchmark, cases=cases)
    payload = report.model_dump(mode="json")
    payload["unexpected_node_count"] += 1

    with pytest.raises(ValidationError, match="does not match case facts"):
        GraphBenchmarkReport.model_validate_json(json.dumps(payload))

    payload = report.model_dump(mode="json")
    payload["full_graph_exact_match_rate"]["numerator"] = 0
    payload["full_graph_exact_match_rate"]["rate"] = 0.0
    payload["output_hash"] = compute_graph_benchmark_output_hash(payload)
    with pytest.raises(ValidationError, match="does not match case facts"):
        GraphBenchmarkReport.model_validate_json(json.dumps(payload))

    payload = report.model_dump(mode="json")
    payload["input_hash"] = "sha256:" + "f" * 64
    payload["output_hash"] = compute_graph_benchmark_output_hash(payload)
    with pytest.raises(ValidationError, match="input_hash mismatch"):
        GraphBenchmarkReport.model_validate_json(json.dumps(payload))


def test_graph_benchmark_report_output_hash_mismatch_is_rejected(
    benchmark: BenchmarkPackage,
    cases: tuple[GraphBenchmarkEvaluationCase, ...],
) -> None:
    payload = evaluate_graph_benchmark(benchmark=benchmark, cases=cases).model_dump(
        mode="json"
    )
    payload["output_hash"] = "sha256:" + "f" * 64

    # The terminal report is validated directly and has no admission-result
    # envelope in which to fabricate a GraphRejectionReason finding.
    with pytest.raises(ValidationError, match="benchmark output_hash mismatch"):
        GraphBenchmarkReport.model_validate_json(json.dumps(payload))


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("paper_benchmark_schema_version", "9.9.9"),
        ("paper_benchmark_version", "9.9.9"),
        ("paper_benchmark_scientific_payload_hash", "sha256:" + "1" * 64),
        ("paper_benchmark_content_hash", "sha256:" + "2" * 64),
    ),
)
def test_graph_benchmark_report_rejects_rehashed_paper_benchmark_identity_drift(
    benchmark: BenchmarkPackage,
    cases: tuple[GraphBenchmarkEvaluationCase, ...],
    field: str,
    value: str,
) -> None:
    payload = evaluate_graph_benchmark(benchmark=benchmark, cases=cases).model_dump(
        mode="json"
    )
    payload[field] = value
    payload["input_hash"] = compute_canonical_payload_hash(
        {
            "paper_benchmark_schema_version": payload["paper_benchmark_schema_version"],
            "paper_benchmark_version": payload["paper_benchmark_version"],
            "paper_benchmark_scientific_payload_hash": payload["paper_benchmark_scientific_payload_hash"],
            "paper_benchmark_content_hash": payload["paper_benchmark_content_hash"],
            "graph_versions": payload["graph_versions"],
            "taxonomy_node_types": payload["taxonomy_node_types"],
            "taxonomy_edge_types": payload["taxonomy_edge_types"],
            "case_content_hashes": [
                item["case_content_hash"] for item in payload["cases"]
            ],
        }
    )
    payload["output_hash"] = compute_graph_benchmark_output_hash(payload)

    with pytest.raises(ValidationError, match="frozen Paper Acquisition Benchmark identity mismatch"):
        GraphBenchmarkReport.model_validate_json(json.dumps(payload))


@pytest.mark.parametrize(
    ("case_field", "case_value", "metric_field", "metric_numerator"),
    (
        (
            "matched_accepted_relation_count",
            0,
            "accepted_relation_coverage_rate",
            0,
        ),
        (
            "matched_reasoning_trace_count",
            0,
            "reasoning_trace_coverage_rate",
            0,
        ),
        (
            "excluded_nonaccepted_relation_count",
            2,
            "nonaccepted_relation_exclusion_rate",
            2,
        ),
    ),
)
def test_graph_benchmark_passing_result_requires_complete_relation_trace_closure(
    benchmark: BenchmarkPackage,
    cases: tuple[GraphBenchmarkEvaluationCase, ...],
    case_field: str,
    case_value: int,
    metric_field: str,
    metric_numerator: int,
) -> None:
    payload = evaluate_graph_benchmark(benchmark=benchmark, cases=cases).model_dump(
        mode="json"
    )
    scientific = next(
        item for item in payload["cases"] if item["kind"] == "scientific_graph"
    )
    scientific[case_field] = case_value
    metric = payload[metric_field]
    metric["numerator"] = metric_numerator
    metric["rate"] = metric_numerator / metric["denominator"]
    payload["output_hash"] = compute_graph_benchmark_output_hash(payload)

    with pytest.raises(ValidationError, match="expected-result flag disagrees"):
        GraphBenchmarkReport.model_validate_json(json.dumps(payload))


def test_graph_benchmark_cli_double_run_and_replay_are_byte_identical(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    first_report = tmp_path / "report-first.json"
    second_report = tmp_path / "report-second.json"
    replay_report = tmp_path / "report-replay.json"
    first_cases = tmp_path / "cases-first.json"
    second_cases = tmp_path / "cases-second.json"

    for report_path, cases_path in (
        (first_report, first_cases),
        (second_report, second_cases),
    ):
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "graph_benchmark",
                "--output",
                str(report_path),
                "--cases-output",
                str(cases_path),
            ],
        )
        assert graph_benchmark_main() == 0

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "graph_benchmark",
            "--cases",
            str(first_cases),
            "--output",
            str(replay_report),
        ],
    )
    assert graph_benchmark_main() == 0

    report = GraphBenchmarkReport.model_validate_json(
        first_report.read_text(encoding="utf-8")
    )
    serialized_cases = _CASE_ADAPTER.validate_json(
        first_cases.read_text(encoding="utf-8")
    )
    assert len(serialized_cases) == (
        2 + len(FORMAL_REJECTION_EXPECTATIONS) + len(FORMAL_SIZE_EXPECTATIONS)
    )
    assert report.full_graph_exact_match_rate.rate == 1.0
    assert report.data_mapping_fixture_pass_rate.rate == 1.0
    assert report.rejection_case_pass_rate.rate == 1.0
    assert first_report.read_bytes() == second_report.read_bytes()
    assert first_report.read_bytes() == replay_report.read_bytes()
    assert first_cases.read_bytes() == second_cases.read_bytes()
    assert b"\r" not in first_report.read_bytes()
    assert b"\r" not in first_cases.read_bytes()

    favorable_path = tmp_path / "favorable-subset.json"
    favorable = [
        item
        for item in json.loads(first_cases.read_text(encoding="utf-8"))
        if item["case_id"] != "rejection.wrong_direction"
    ]
    favorable_path.write_text(
        json.dumps(favorable, ensure_ascii=False),
        encoding="utf-8",
        newline="\n",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "graph_benchmark",
            "--cases",
            str(favorable_path),
            "--output",
            str(tmp_path / "subset-report.json"),
        ],
    )
    with pytest.raises(ValueError, match="fixed rejection and size suite exactly"):
        graph_benchmark_main()
