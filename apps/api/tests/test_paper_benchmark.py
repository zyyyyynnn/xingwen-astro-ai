from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.schemas.paper_benchmark import (
    BenchmarkAdmissionStatus,
    BenchmarkEvaluationInput,
    BenchmarkMetricId,
    BenchmarkPackage,
    BenchmarkPackagePayload,
    BenchmarkReviewStatus,
    compute_benchmark_content_hash,
    evaluate_benchmark,
    load_benchmark_package,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
BENCHMARK_PATH = (
    REPOSITORY_ROOT
    / "services"
    / "paper_pipeline"
    / "benchmarks"
    / "exoplanet_host_star"
    / "paper-reasoning-benchmark.v1.json"
)


def _read_payload() -> dict[str, Any]:
    return json.loads(BENCHMARK_PATH.read_text(encoding="utf-8"))


def test_benchmark_package_is_machine_readable_and_versioned() -> None:
    package = load_benchmark_package(BENCHMARK_PATH)

    assert package.benchmark_id == "exoplanet_host_star.paper_reasoning"
    assert package.schema_version == "1.0.0"
    assert package.benchmark_version == "1.0.0"
    assert package.case_id == "exoplanet_host_star"
    assert len(package.seed_papers) == 6
    assert len(package.claims) >= 5
    assert len(package.relations) >= 3
    assert package.review_status is BenchmarkReviewStatus.pending_human_review


def test_content_hash_uses_the_c01_canonical_rules() -> None:
    payload = _read_payload()
    package = BenchmarkPackage.model_validate(payload)

    assert compute_benchmark_content_hash(payload) == package.content_hash
    assert compute_benchmark_content_hash(package) == package.content_hash
    assert (
        compute_benchmark_content_hash(package.model_dump(mode="json"))
        == package.content_hash
    )


def test_hash_is_stable_after_json_round_trip() -> None:
    payload = _read_payload()
    round_tripped = json.loads(
        json.dumps(payload, ensure_ascii=False, sort_keys=False)
    )

    assert compute_benchmark_content_hash(round_tripped) == payload["content_hash"]


def test_hash_sorts_object_keys_but_preserves_array_order() -> None:
    payload = _read_payload()
    reordered_keys = {key: payload[key] for key in reversed(tuple(payload))}
    assert compute_benchmark_content_hash(reordered_keys) == payload["content_hash"]

    reordered_array = deepcopy(payload)
    reordered_array["seed_papers"].reverse()
    assert compute_benchmark_content_hash(reordered_array) != payload["content_hash"]


@pytest.mark.parametrize(
    "field",
    ["created_at", "review_records", "change_records"],
)
def test_audit_and_review_metadata_are_hash_bound(field: str) -> None:
    payload = _read_payload()
    if field == "created_at":
        payload[field] = "2026-07-20"
    else:
        payload[field][0]["notes" if field == "review_records" else "summary"] += " changed"

    assert compute_benchmark_content_hash(payload) != _read_payload()["content_hash"]


def test_wrong_content_hash_is_rejected() -> None:
    payload = _read_payload()
    payload["content_hash"] = f"sha256:{'0' * 64}"

    with pytest.raises(ValidationError, match="content_hash does not match"):
        BenchmarkPackage.model_validate(payload)


@pytest.mark.parametrize("field", ["schema_version", "benchmark_version"])
def test_invalid_semantic_version_is_rejected(field: str) -> None:
    payload = _read_payload()
    payload[field] = "v1"

    with pytest.raises(ValidationError, match=field):
        BenchmarkPackage.model_validate(payload)


def test_seed_papers_have_verified_identifiers_and_data_boundaries() -> None:
    package = load_benchmark_package(BENCHMARK_PATH)

    for paper in package.seed_papers:
        assert paper.doi or paper.arxiv_id or paper.official_url
        assert paper.verification_sources
        assert all(source.verified_at for source in paper.verification_sources)
        assert all(author.casefold().rstrip(".") != "et al" for author in paper.authors)
        assert paper.metadata_public is True
        assert paper.abstract_public is True
        assert paper.license_or_usage_boundary
        assert paper.rate_limit_or_runtime_risk
        assert set(paper.intended_uses) <= {"benchmark", "manual_review", "fixture"}


def test_claims_cover_required_types_and_bind_evidence() -> None:
    package = load_benchmark_package(BENCHMARK_PATH)
    claim_types = {claim.claim_type.value for claim in package.claims}

    assert len(claim_types & {"finding", "method", "dataset", "limitation"}) >= 3
    assert all(claim.evidence_ids for claim in package.claims)


def test_claim_without_evidence_is_rejected() -> None:
    payload = _read_payload()
    payload["claims"][0]["evidence_ids"] = []

    with pytest.raises(ValidationError):
        BenchmarkPackage.model_validate(payload)


def test_relations_cover_types_and_all_admission_states() -> None:
    package = load_benchmark_package(BENCHMARK_PATH)

    relation_types = {relation.relation_type.value for relation in package.relations}
    statuses = {relation.status for relation in package.relations}
    assert len(
        relation_types
        & {"supports", "extends", "derived_from", "limits", "contradicts"}
    ) >= 3
    assert statuses == set(BenchmarkAdmissionStatus)


def test_accepted_relation_requires_trace_and_both_claims_evidence() -> None:
    payload = _read_payload()
    accepted = next(
        relation for relation in payload["relations"] if relation["status"] == "accepted"
    )
    accepted["evidence_ids"] = [accepted["evidence_ids"][0]]

    with pytest.raises(ValidationError, match="lacks target evidence"):
        BenchmarkPackage.model_validate(payload)


def test_accepted_relation_without_trace_is_rejected() -> None:
    payload = _read_payload()
    accepted = next(
        relation for relation in payload["relations"] if relation["status"] == "accepted"
    )
    accepted["reasoning_trace_id"] = None

    with pytest.raises(ValidationError, match="accepted relation requires"):
        BenchmarkPackage.model_validate(payload)


def test_evidence_less_relation_is_rejected() -> None:
    payload = _read_payload()
    payload["relations"][0]["evidence_ids"] = []

    with pytest.raises(ValidationError):
        BenchmarkPackage.model_validate(payload)


def test_evidence_must_be_bound_by_its_declared_target() -> None:
    payload = _read_payload()
    evidence_id = payload["claims"][0]["evidence_ids"][0]
    payload["claims"][0]["evidence_ids"] = [payload["claims"][1]["evidence_ids"][0]]

    with pytest.raises(ValidationError, match="is not bound by its declared target"):
        BenchmarkPackage.model_validate(payload)


def test_candidate_relation_cannot_reference_a_dangling_trace() -> None:
    payload = _read_payload()
    candidate = next(
        relation for relation in payload["relations"] if relation["status"] == "candidate"
    )
    candidate["reasoning_trace_id"] = "trace.missing"

    with pytest.raises(ValidationError, match="unknown relation trace"):
        BenchmarkPackage.model_validate(payload)


def test_rejected_relation_requires_a_reason() -> None:
    payload = _read_payload()
    rejected = next(
        relation for relation in payload["relations"] if relation["status"] == "rejected"
    )
    rejected["rejection_reason"] = None

    with pytest.raises(ValidationError, match="rejected relation requires"):
        BenchmarkPackage.model_validate(payload)


def test_trace_must_point_back_to_the_pinning_relation() -> None:
    payload = _read_payload()
    payload["reasoning_traces"][0]["relation_id"] = payload["relations"][1][
        "relation_id"
    ]

    with pytest.raises(ValidationError, match="not pinned by its relation"):
        BenchmarkPackage.model_validate(payload)


def test_graph_rejects_dangling_edge_endpoint() -> None:
    payload = _read_payload()
    payload["graph"]["edges"][0]["target"] = "node.missing"

    with pytest.raises(ValidationError, match="unknown graph edge node"):
        BenchmarkPackage.model_validate(payload)


def test_cross_document_edge_rejects_non_accepted_relation() -> None:
    payload = _read_payload()
    cross_edge = next(
        edge for edge in payload["graph"]["edges"] if edge["cross_document"]
    )
    rejected = next(
        relation for relation in payload["relations"] if relation["status"] == "rejected"
    )
    cross_edge["relation_id"] = rejected["relation_id"]

    with pytest.raises(ValidationError, match="non-accepted relation"):
        BenchmarkPackage.model_validate(payload)


def test_cross_document_edge_must_match_relation_claim_endpoints() -> None:
    payload = _read_payload()
    cross_edges = [edge for edge in payload["graph"]["edges"] if edge["cross_document"]]
    cross_edges[0]["source"] = cross_edges[1]["source"]

    with pytest.raises(ValidationError, match="endpoints do not match relation claims"):
        BenchmarkPackage.model_validate(payload)


def test_graph_uses_only_frozen_taxonomy_types() -> None:
    package = load_benchmark_package(BENCHMARK_PATH)
    allowed_nodes = set(package.graph_taxonomy.allowed_node_types)
    allowed_edges = set(package.graph_taxonomy.allowed_edge_types)

    assert all(node.node_type in allowed_nodes for node in package.graph.nodes)
    assert all(edge.edge_type in allowed_edges for edge in package.graph.edges)


def test_metrics_are_computed_from_explicit_numerators_and_denominators() -> None:
    package = load_benchmark_package(BENCHMARK_PATH)
    expected_papers = tuple(
        dict.fromkeys(
            paper_id
            for scenario in package.search_scenarios
            for paper_id in scenario.expected_paper_ids
        )
    )
    results = evaluate_benchmark(
        package,
        BenchmarkEvaluationInput(
            retrieved_expected_paper_ids=expected_papers[:-1],
            schema_items_valid=9,
            schema_items_total=10,
            evidence_requirements_satisfied=8,
            evidence_requirements_total=10,
            human_reviewed_relations_correct=3,
            human_reviewed_relations_total=4,
            evidence_less_relations_blocked=5,
            evidence_less_relations_total=5,
        ),
    )
    by_id = {result.metric_id: result for result in results}

    assert by_id[BenchmarkMetricId.candidate_recall].numerator == 5
    assert by_id[BenchmarkMetricId.candidate_recall].denominator == 6
    assert by_id[BenchmarkMetricId.schema_pass_rate].value == 0.9
    assert by_id[BenchmarkMetricId.evidence_coverage].value == 0.8
    assert by_id[BenchmarkMetricId.relation_human_accuracy].value == 0.75
    assert by_id[BenchmarkMetricId.evidence_less_relation_block_rate].value == 1.0


def test_metrics_report_not_available_for_empty_denominators() -> None:
    package = load_benchmark_package(BENCHMARK_PATH)
    results = evaluate_benchmark(
        package,
        BenchmarkEvaluationInput(
            schema_items_valid=0,
            schema_items_total=0,
            evidence_requirements_satisfied=0,
            evidence_requirements_total=0,
            human_reviewed_relations_correct=0,
            human_reviewed_relations_total=0,
            evidence_less_relations_blocked=0,
            evidence_less_relations_total=0,
        ),
    )
    by_id = {result.metric_id: result for result in results}

    for metric_id in (
        BenchmarkMetricId.schema_pass_rate,
        BenchmarkMetricId.evidence_coverage,
        BenchmarkMetricId.relation_human_accuracy,
        BenchmarkMetricId.evidence_less_relation_block_rate,
    ):
        assert by_id[metric_id].value is None
        assert by_id[metric_id].status == "not_available"


def test_benchmark_models_export_machine_readable_json_schema() -> None:
    schema = BenchmarkPackage.model_json_schema()

    assert "content_hash" in schema["required"]
    assert "seed_papers" in schema["required"]
    assert "relations" in schema["required"]
    assert "graph" in schema["required"]
    assert BenchmarkPackagePayload.model_json_schema()["type"] == "object"
