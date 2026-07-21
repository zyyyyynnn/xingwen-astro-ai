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


def _review_fixture(
    *,
    package_status: BenchmarkReviewStatus,
    approved_relation_count: int,
) -> BenchmarkPackage:
    payload = _read_payload()
    payload["review_status"] = package_status.value
    for index, relation in enumerate(payload["relations"]):
        relation["review_status"] = (
            BenchmarkReviewStatus.approved.value
            if index < approved_relation_count
            else BenchmarkReviewStatus.pending_human_review.value
        )
        if relation["review_status"] != BenchmarkReviewStatus.approved.value:
            continue
        claim_ids = {relation["source_claim_id"], relation["target_claim_id"]}
        claims = [claim for claim in payload["claims"] if claim["claim_id"] in claim_ids]
        for claim in claims:
            claim["review_status"] = BenchmarkReviewStatus.approved.value
        related_evidence_ids = {
            *relation["evidence_ids"],
            *(evidence_id for claim in claims for evidence_id in claim["evidence_ids"]),
        }
        if relation["reasoning_trace_id"] is not None:
            trace = next(
                trace
                for trace in payload["reasoning_traces"]
                if trace["trace_id"] == relation["reasoning_trace_id"]
            )
            trace["review_status"] = BenchmarkReviewStatus.approved.value
            related_evidence_ids.update(
                evidence_id
                for step in trace["steps"]
                for evidence_id in step["evidence_ids"]
            )
        for evidence in payload["evidence"]:
            if evidence["evidence_id"] in related_evidence_ids:
                evidence["review_status"] = BenchmarkReviewStatus.approved.value

    if package_status is BenchmarkReviewStatus.approved:
        assert approved_relation_count == len(payload["relations"])
        for collection in (
            payload["paper_summaries"],
            payload["evidence"],
            payload["claims"],
            payload["relations"],
            payload["reasoning_traces"],
        ):
            for item in collection:
                item["review_status"] = BenchmarkReviewStatus.approved.value
        payload["review_records"].append(
            {
                "review_id": "review.synthetic_human_approval",
                "reviewed_at": "2026-07-21",
                "reviewer_type": "human",
                "reviewer_identity": "github:human-reviewer",
                "reviewer_role": "scientific_benchmark_reviewer",
                "status": "approved",
                "review_evidence_url": "https://github.com/zyyyyynnn/xingwen-astro-ai/pull/999#pullrequestreview-1",
                "scope": [
                    {
                        "target_type": "benchmark_package",
                        "target_ids": [payload["benchmark_id"]],
                    },
                    {
                        "target_type": "source_policy",
                        "target_ids": [
                            source["source_id"] for source in payload["source_policies"]
                        ],
                    },
                    {
                        "target_type": "seed_paper",
                        "target_ids": [
                            paper["paper_id"] for paper in payload["seed_papers"]
                        ],
                    },
                    {
                        "target_type": "paper_summary",
                        "target_ids": [
                            summary["summary_id"]
                            for summary in payload["paper_summaries"]
                        ],
                    },
                    {
                        "target_type": "evidence",
                        "target_ids": [
                            evidence["evidence_id"] for evidence in payload["evidence"]
                        ],
                    },
                    {
                        "target_type": "claim",
                        "target_ids": [claim["claim_id"] for claim in payload["claims"]],
                    },
                    {
                        "target_type": "relation",
                        "target_ids": [
                            relation["relation_id"] for relation in payload["relations"]
                        ],
                    },
                    {
                        "target_type": "reasoning_trace",
                        "target_ids": [
                            trace["trace_id"] for trace in payload["reasoning_traces"]
                        ],
                    },
                    {
                        "target_type": "graph_edge",
                        "target_ids": [
                            edge["edge_id"] for edge in payload["graph"]["edges"]
                        ],
                    },
                ],
                "notes": "Synthetic human approval for metric contract tests only.",
            }
        )
    payload["content_hash"] = compute_benchmark_content_hash(payload)
    return BenchmarkPackage.model_validate(payload)


def _evaluation_input(**overrides: int) -> BenchmarkEvaluationInput:
    values = {
        "schema_items_valid": 0,
        "schema_items_total": 0,
        "evidence_requirements_satisfied": 0,
        "evidence_requirements_total": 0,
        "evidence_less_relations_blocked": 0,
        "evidence_less_relations_total": 0,
    }
    values.update(overrides)
    return BenchmarkEvaluationInput(**values)


def test_benchmark_package_is_machine_readable_and_versioned() -> None:
    package = load_benchmark_package(BENCHMARK_PATH)

    assert package.benchmark_id == "exoplanet_host_star.paper_reasoning"
    assert package.schema_version == "1.1.0"
    assert package.benchmark_version == "1.1.0"
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


def test_verification_sources_use_revalidated_stable_records() -> None:
    package = load_benchmark_package(BENCHMARK_PATH)

    for paper in package.seed_papers:
        for source in paper.verification_sources:
            assert source.verified_at.isoformat() == "2026-07-21"
            if source.source_id == "crossref":
                assert str(source.url).startswith("https://api.crossref.org/works/")

    clark = next(
        paper
        for paper in package.seed_papers
        if paper.paper_id == "paper.clark_2021_galah_tess"
    )
    assert {source.source_id for source in clark.verification_sources} == {
        "arxiv",
        "crossref",
    }


def test_crossref_policy_has_structured_request_class_limits() -> None:
    package = load_benchmark_package(BENCHMARK_PATH)
    crossref = next(
        source for source in package.source_policies if source.source_id == "crossref"
    )

    assert crossref.crossref_rate_limits is not None
    assert crossref.crossref_rate_limits.verified_at.isoformat() == "2026-07-21"
    assert crossref.crossref_rate_limits.rate_limit_unit == "requests_per_second"
    assert {
        (limit.pool, limit.request_class)
        for limit in crossref.crossref_rate_limits.limits
    } == {
        ("public", "single_record"),
        ("public", "list_or_search"),
        ("polite", "single_record"),
        ("polite", "list_or_search"),
    }


def test_automation_review_cannot_approve_package() -> None:
    payload = _read_payload()
    payload.pop("content_hash")
    payload["review_status"] = "approved"
    payload["review_records"][0]["status"] = "approved"

    with pytest.raises(ValidationError, match="approved package requires human review"):
        BenchmarkPackagePayload.model_validate(payload)


def test_non_github_identity_cannot_claim_human_review() -> None:
    payload = _read_payload()
    record = payload["review_records"][0]
    record["reviewer_type"] = "human"
    record["reviewer_identity"] = "test:fixture-reviewer"
    record["review_evidence_url"] = (
        "https://github.com/zyyyyynnn/xingwen-astro-ai/"
        "pull/999#pullrequestreview-1"
    )

    with pytest.raises(ValidationError, match="must use the github namespace"):
        BenchmarkPackagePayload.model_validate(payload)


def test_review_records_have_stable_identity_and_machine_readable_scope() -> None:
    package = load_benchmark_package(BENCHMARK_PATH)

    for record in package.review_records:
        assert record.reviewer_type.value in {"human", "automation"}
        assert ":" in record.reviewer_identity
        assert record.scope
        assert all(scope.target_ids for scope in record.scope)


def test_human_approval_must_cover_every_package_object() -> None:
    approved = _review_fixture(
        package_status=BenchmarkReviewStatus.approved,
        approved_relation_count=4,
    )
    payload = approved.model_dump(mode="json", exclude={"content_hash"})
    human_review = next(
        record
        for record in payload["review_records"]
        if record["reviewer_type"] == "human"
    )
    graph_scope = next(
        scope
        for scope in human_review["scope"]
        if scope["target_type"] == "graph_edge"
    )
    graph_scope["target_ids"].pop()

    with pytest.raises(ValidationError, match="human review scope is incomplete"):
        BenchmarkPackagePayload.model_validate(payload)


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


def test_paper_metadata_evidence_is_rejected_without_a_supported_locator() -> None:
    package = load_benchmark_package(BENCHMARK_PATH)
    assert len(package.evidence) == 18
    assert {evidence.evidence_type for evidence in package.evidence} == {"paper_text"}

    payload = _read_payload()
    payload["evidence"][0]["evidence_type"] = "paper_metadata"

    with pytest.raises(ValidationError, match="paper_metadata"):
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


def test_directional_relations_use_source_relation_target_order() -> None:
    package = load_benchmark_package(BENCHMARK_PATH)
    relations = {relation.relation_id: relation for relation in package.relations}
    traces = {trace.relation_id: trace for trace in package.reasoning_traces}
    nodes = {node.node_id: node for node in package.graph.nodes}

    extends = relations["relation.revised_tic_extends_initial_tic"]
    assert extends.source_claim_id == "claim.stassun_2019_gaia_revision"
    assert extends.target_claim_id == "claim.stassun_2018_tic_method"
    assert traces[extends.relation_id].premise_claim_ids == (
        extends.source_claim_id,
        extends.target_claim_id,
    )

    derived = relations["relation.clark_catalog_derived_from_tic"]
    assert derived.source_claim_id == "claim.clark_crossmatched_catalog"
    assert derived.target_claim_id == "claim.stassun_2019_gaia_revision"
    assert traces[derived.relation_id].premise_claim_ids == (
        derived.source_claim_id,
        derived.target_claim_id,
    )

    for edge in package.graph.edges:
        if edge.cross_document:
            relation = relations[edge.relation_id]
            assert nodes[edge.source].ref_id == relation.source_claim_id
            assert nodes[edge.target].ref_id == relation.target_claim_id


def test_trace_premises_cannot_reverse_directional_relation() -> None:
    payload = _read_payload()
    trace = payload["reasoning_traces"][0]
    trace["premise_claim_ids"].reverse()

    with pytest.raises(ValidationError, match="premises must follow relation direction"):
        BenchmarkPackage.model_validate(payload)


def test_approved_relation_requires_approved_dependencies() -> None:
    payload = _read_payload()
    payload.pop("content_hash")
    relation = next(
        relation for relation in payload["relations"] if relation["status"] == "accepted"
    )
    relation["review_status"] = "approved"

    with pytest.raises(ValidationError, match="has unapproved source claim"):
        BenchmarkPackagePayload.model_validate(payload)


@pytest.mark.parametrize(
    ("dependency", "expected_message"),
    [
        ("target_claim", "has unapproved target claim"),
        ("reasoning_trace", "has unapproved reasoning trace"),
        ("evidence", "has unapproved evidence"),
    ],
)
def test_approved_relation_rejects_each_unapproved_dependency(
    dependency: str,
    expected_message: str,
) -> None:
    package = _review_fixture(
        package_status=BenchmarkReviewStatus.pending_human_review,
        approved_relation_count=1,
    )
    payload = package.model_dump(mode="json", exclude={"content_hash"})
    relation = next(
        relation
        for relation in payload["relations"]
        if relation["review_status"] == "approved"
    )

    if dependency == "target_claim":
        target_claim = next(
            claim
            for claim in payload["claims"]
            if claim["claim_id"] == relation["target_claim_id"]
        )
        target_claim["review_status"] = "pending_human_review"
    elif dependency == "reasoning_trace":
        trace = next(
            trace
            for trace in payload["reasoning_traces"]
            if trace["trace_id"] == relation["reasoning_trace_id"]
        )
        trace["review_status"] = "pending_human_review"
    else:
        related_evidence = next(
            evidence
            for evidence in payload["evidence"]
            if evidence["evidence_id"] in relation["evidence_ids"]
        )
        related_evidence["review_status"] = "pending_human_review"

    with pytest.raises(ValidationError, match=expected_message):
        BenchmarkPackagePayload.model_validate(payload)


def test_approved_relation_cannot_omit_reasoning_trace() -> None:
    package = _review_fixture(
        package_status=BenchmarkReviewStatus.pending_human_review,
        approved_relation_count=4,
    )
    payload = package.model_dump(mode="json", exclude={"content_hash"})
    rejected = next(
        relation for relation in payload["relations"] if relation["status"] == "rejected"
    )
    rejected["reasoning_trace_id"] = None

    with pytest.raises(ValidationError, match="requires approved reasoning trace"):
        BenchmarkPackagePayload.model_validate(payload)


def test_accepted_relation_requires_trace_and_both_claims_evidence() -> None:
    payload = _read_payload()
    accepted = next(
        relation for relation in payload["relations"] if relation["status"] == "accepted"
    )
    source_claim = next(
        claim
        for claim in payload["claims"]
        if claim["claim_id"] == accepted["source_claim_id"]
    )
    accepted["evidence_ids"] = [source_claim["evidence_ids"][0]]

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


def test_metrics_are_computed_from_approved_relation_fixture() -> None:
    package = _review_fixture(
        package_status=BenchmarkReviewStatus.approved,
        approved_relation_count=4,
    )
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


def test_relation_human_accuracy_is_not_available_without_approved_relations() -> None:
    package = _review_fixture(
        package_status=BenchmarkReviewStatus.pending_human_review,
        approved_relation_count=0,
    )
    results = evaluate_benchmark(package, _evaluation_input())
    by_id = {result.metric_id: result for result in results}

    relation_accuracy = by_id[BenchmarkMetricId.relation_human_accuracy]
    assert relation_accuracy.numerator == 0
    assert relation_accuracy.denominator == 0
    assert relation_accuracy.value is None
    assert relation_accuracy.status == "not_available"


def test_relation_human_accuracy_rejects_nonzero_counts_without_approved_relations() -> None:
    package = _review_fixture(
        package_status=BenchmarkReviewStatus.pending_human_review,
        approved_relation_count=0,
    )

    with pytest.raises(ValueError, match="counts must be zero"):
        evaluate_benchmark(
            package,
            _evaluation_input(
                human_reviewed_relations_correct=1,
                human_reviewed_relations_total=1,
            ),
        )


def test_relation_human_accuracy_total_must_match_approved_relations() -> None:
    package = _review_fixture(
        package_status=BenchmarkReviewStatus.approved,
        approved_relation_count=4,
    )

    with pytest.raises(ValueError, match="total must equal"):
        evaluate_benchmark(
            package,
            _evaluation_input(
                human_reviewed_relations_correct=3,
                human_reviewed_relations_total=3,
            ),
        )


def test_relation_human_accuracy_rejects_correct_above_total() -> None:
    with pytest.raises(ValidationError, match="numerator must not exceed denominator"):
        _evaluation_input(
            human_reviewed_relations_correct=4,
            human_reviewed_relations_total=3,
        )


def test_pending_benchmark_does_not_report_relation_accuracy() -> None:
    package = load_benchmark_package(BENCHMARK_PATH)
    results = evaluate_benchmark(package, _evaluation_input())
    by_id = {result.metric_id: result for result in results}

    assert package.review_status is BenchmarkReviewStatus.pending_human_review
    assert all(
        relation.review_status is BenchmarkReviewStatus.pending_human_review
        for relation in package.relations
    )
    assert by_id[BenchmarkMetricId.relation_human_accuracy].status == "not_available"


def test_pending_package_blocks_accuracy_even_with_approved_relations() -> None:
    package = _review_fixture(
        package_status=BenchmarkReviewStatus.pending_human_review,
        approved_relation_count=4,
    )
    results = evaluate_benchmark(package, _evaluation_input())
    by_id = {result.metric_id: result for result in results}

    assert by_id[BenchmarkMetricId.relation_human_accuracy].status == "not_available"


def test_pending_package_rejects_nonzero_relation_accuracy_counts() -> None:
    package = _review_fixture(
        package_status=BenchmarkReviewStatus.pending_human_review,
        approved_relation_count=4,
    )

    with pytest.raises(ValueError, match="counts must be zero"):
        evaluate_benchmark(
            package,
            _evaluation_input(
                human_reviewed_relations_correct=3,
                human_reviewed_relations_total=4,
            ),
        )


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
