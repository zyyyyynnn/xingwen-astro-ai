from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.enums import GraphEdgeType, GraphNodeType
from app.schemas.graph_artifact import (
    GraphAdmissionResult,
    GraphArtifactCandidate,
    GraphArtifactEdge,
    GraphArtifactNode,
    GraphBenchmarkEvaluationCase,
    GraphBenchmarkDenominatorScope,
    GraphBenchmarkMetric,
    GraphBenchmarkReport,
    GraphBuildRequest,
    GraphBuildScope,
    GraphEvidenceUse,
    GraphIntegrityCounts,
    GraphIntegrityFinding,
    GraphIntegrityReport,
    GraphIntegrityStage,
    GraphIntegrityStatus,
    GraphRejectionReason,
    GraphStructuralEdgeRequest,
    GraphTaxonomy,
    compute_graph_integrity_report_hash,
    compute_graph_upstream_evidence_hash,
)
from services.graph_pipeline.admission import build_integrity_report
from services.graph_pipeline.pipeline import (
    GraphPipeline,
    build_complete_progressive_input,
)

from graph_pipeline_test_support import (
    build_data_graph_fixture,
    build_literature_graph_fixture,
)


_PROJECT_ID = "00000000-0000-4000-8000-000000000001"
_RELATION_VERSION_ID = "00000000-0000-4000-8000-000000000002"
_CLAIM_VERSION_ID = "00000000-0000-4000-8000-000000000003"


def _scope() -> GraphBuildScope:
    return GraphBuildScope(
        literature_paper_ids=("paper.1",),
        literature_claim_ids=("claim.1",),
        accepted_relation_ids=(),
        structural_edges=(
            GraphStructuralEdgeRequest(
                edge_type=GraphEdgeType.supports_finding,
                source_paper_id="paper.1",
                target_claim_id="claim.1",
            ),
        ),
    )


def _request_payload() -> dict:
    scope = _scope()
    progressive = build_complete_progressive_input(
        progressive_id="progressive.test",
        literature_claims_artifact_version_ids=(_CLAIM_VERSION_ID,),
        literature_relations_artifact_version_id=_RELATION_VERSION_ID,
        dataset_artifact_version_id=None,
        field_dictionary_artifact_version_id=None,
        scope=scope,
    )
    return {
        "project_id": _PROJECT_ID,
        "literature_claims_artifact_version_ids": (_CLAIM_VERSION_ID,),
        "literature_relations_artifact_version_id": _RELATION_VERSION_ID,
        "scope": scope,
        "progressive": progressive,
    }


def test_graph_request_is_strict_and_data_versions_are_an_exact_pair() -> None:
    request = GraphBuildRequest(**_request_payload())

    assert request.scope.include_data is False
    with pytest.raises(ValidationError, match="extra_forbidden"):
        GraphBuildRequest(**_request_payload(), unknown=True)
    payload = _request_payload()
    payload["dataset_artifact_version_id"] = "00000000-0000-4000-8000-000000000003"
    with pytest.raises(ValidationError, match="one pair"):
        GraphBuildRequest(**payload)


def test_tracked_graph_schemas_and_manifest_hashes_match_authoring_models() -> None:
    generated = (
        Path(__file__).resolve().parents[3]
        / "packages"
        / "schemas"
        / "generated"
        / "graph"
    )
    manifest = json.loads((generated / "manifest.json").read_text(encoding="utf-8"))
    models = {
        model.__name__: model
        for model in (
            GraphBuildRequest,
            GraphArtifactNode,
            GraphArtifactEdge,
            GraphEvidenceUse,
            GraphIntegrityReport,
            GraphArtifactCandidate,
            GraphAdmissionResult,
            GraphBenchmarkEvaluationCase,
            GraphBenchmarkReport,
        )
    }

    assert manifest["authoring_source"] == "apps/api/src/app/schemas"
    assert {item["name"] for item in manifest["models"]} == set(models)
    for item in manifest["models"]:
        schema_path = generated / item["path"]
        schema_bytes = schema_path.read_bytes()
        assert item["content_hash"] == (
            "sha256:" + hashlib.sha256(schema_bytes).hexdigest()
        )
        assert json.loads(schema_bytes) == models[item["name"]].model_json_schema()


def test_graph_json_schema_exposes_only_the_exact_authorized_taxonomy() -> None:
    node_schema = GraphArtifactNode.model_json_schema()
    edge_schema = GraphArtifactEdge.model_json_schema()
    taxonomy_schema = GraphTaxonomy.model_json_schema()

    expected_node_types = {
        GraphNodeType.research_goal.value,
        GraphNodeType.dataset.value,
        GraphNodeType.field.value,
        GraphNodeType.paper.value,
        GraphNodeType.claim.value,
    }
    expected_edge_types = {
        GraphEdgeType.uses_dataset.value,
        GraphEdgeType.provides_field.value,
        GraphEdgeType.supports_finding.value,
        GraphEdgeType.supports.value,
        GraphEdgeType.extends.value,
        GraphEdgeType.derived_from.value,
        GraphEdgeType.limits.value,
        GraphEdgeType.contradicts.value,
        GraphEdgeType.uses_same_dataset.value,
        GraphEdgeType.compares_method.value,
    }

    assert set(node_schema["properties"]["node_type"]["enum"]) == expected_node_types
    assert set(edge_schema["properties"]["edge_type"]["enum"]) == expected_edge_types
    assert (
        GraphNodeType.source.value not in node_schema["properties"]["node_type"]["enum"]
    )
    assert (
        GraphEdgeType.cites.value not in edge_schema["properties"]["edge_type"]["enum"]
    )
    assert (
        GraphEdgeType.corrected_by_feedback.value
        not in edge_schema["properties"]["edge_type"]["enum"]
    )

    taxonomy_node_schema = taxonomy_schema["properties"]["node_types"]
    taxonomy_edge_schema = taxonomy_schema["properties"]["edge_types"]
    assert taxonomy_node_schema["minItems"] == taxonomy_node_schema["maxItems"] == 5
    assert taxonomy_edge_schema["minItems"] == taxonomy_edge_schema["maxItems"] == 10
    assert tuple(
        item["const"] for item in taxonomy_node_schema["prefixItems"]
    ) == tuple(sorted(expected_node_types))
    assert tuple(
        item["const"] for item in taxonomy_edge_schema["prefixItems"]
    ) == tuple(sorted(expected_edge_types))


def test_graph_scope_cannot_infer_unpinned_research_goal() -> None:
    with pytest.raises(ValidationError, match="cannot infer uses_dataset"):
        GraphBuildScope(research_goal_id="goal.unpinned")


def test_integrity_report_hash_and_first_failure_are_recomputed() -> None:
    counts = GraphIntegrityCounts(
        input_version_count=2,
        node_count=0,
        edge_count=0,
        evidence_use_count=0,
        source_snapshot_count=0,
        relation_edge_count=0,
    )
    report = build_integrity_report(
        findings=(
            GraphIntegrityFinding(
                stage=GraphIntegrityStage.evidence_snapshot,
                reason=GraphRejectionReason.evidence_missing,
                priority=700,
                path="edges.edge.1.evidence",
                message="Evidence is missing",
            ),
            GraphIntegrityFinding(
                stage=GraphIntegrityStage.artifact_version,
                reason=GraphRejectionReason.input_version_unknown,
                priority=200,
                path="input_versions.unknown",
                message="Input version is unknown",
            ),
        ),
        counts=counts,
    )

    assert report.status is GraphIntegrityStatus.failed
    assert report.first_failure_stage is GraphIntegrityStage.artifact_version
    assert report.first_rejection_reason is GraphRejectionReason.input_version_unknown
    assert report.content_hash == compute_graph_integrity_report_hash(report)
    payload = report.model_dump(mode="json")
    payload["counts"]["node_count"] = 1
    with pytest.raises(ValidationError, match="content_hash mismatch"):
        type(report).model_validate_json(json.dumps(payload))


def test_upstream_evidence_hash_binds_restriction_without_runtime_fields() -> None:
    payload = {
        "artifact_version_id": _RELATION_VERSION_ID,
        "target_type": "relation",
        "target_id": "relation.1",
        "evidence_type": "paper_text",
        "source_snapshot_id": "00000000-0000-4000-8000-000000000004",
        "paper_id": "paper.1",
        "locator": {"summary_evidence_id": "evidence.1"},
        "quote_or_value": None,
        "extraction_method": "literature_admission",
        "confidence": 1.0,
        "is_restricted": False,
    }
    first = compute_graph_upstream_evidence_hash(payload)
    runtime_changed = deepcopy(payload)
    runtime_changed["created_at"] = "2099-01-01T00:00:00Z"
    restricted = deepcopy(payload)
    restricted["is_restricted"] = True

    assert first == compute_graph_upstream_evidence_hash(runtime_changed)
    assert first != compute_graph_upstream_evidence_hash(restricted)
    assert first == compute_canonical_payload_hash(payload)


@pytest.mark.parametrize(
    ("numerator", "denominator", "rate"),
    ((0, 0, None), (0, 2, 0.0), (1, 2, 0.5), (2, 2, 1.0)),
)
def test_benchmark_metric_empty_set_and_rates(
    numerator: int,
    denominator: int,
    rate: float | None,
) -> None:
    metric = GraphBenchmarkMetric(
        numerator=numerator,
        denominator=denominator,
        rate=rate,
        denominator_scope=GraphBenchmarkDenominatorScope.all_cases,
    )
    assert metric.rate == rate


def test_benchmark_metric_rejects_fabricated_empty_or_wrong_rate() -> None:
    with pytest.raises(ValidationError, match="does not match"):
        GraphBenchmarkMetric(
            numerator=0,
            denominator=0,
            rate=1.0,
            denominator_scope=GraphBenchmarkDenominatorScope.all_cases,
        )
    with pytest.raises(ValidationError, match="does not match"):
        GraphBenchmarkMetric(
            numerator=1,
            denominator=2,
            rate=1.0,
            denominator_scope=GraphBenchmarkDenominatorScope.all_cases,
        )


def test_provides_field_requires_aggregation_and_other_edges_forbid_it() -> None:
    data_fixture = build_data_graph_fixture()
    data_result = GraphPipeline(data_fixture.reader).admit(data_fixture.request())
    assert data_result.candidate is not None
    data_edge = next(
        item
        for item in data_result.candidate.edges
        if item.edge_type is GraphEdgeType.provides_field
    )
    assert data_edge.data_aggregation is not None
    field_node = next(
        item
        for item in data_result.candidate.nodes
        if item.node_id == data_edge.target_node_id
    )
    field_id = next(
        item.value
        for item in field_node.logical_reference
        if item.name == "canonical_field_id"
    )
    assert data_fixture.inputs.data is not None
    assert data_edge.data_aggregation.projected_row_count == sum(
        field_id in row.projected_field_ids
        for row in data_fixture.inputs.data.dataset.candidate.rows
    )
    assert data_edge.data_aggregation.upstream_evidence_count > 0

    payload = data_edge.model_dump(mode="json", exclude_none=True)
    payload.pop("data_aggregation")
    with pytest.raises(ValidationError, match="provides_field edges require"):
        GraphArtifactEdge.model_validate_json(json.dumps(payload))

    literature_fixture = build_literature_graph_fixture()
    literature_result = GraphPipeline(literature_fixture.reader).admit(
        literature_fixture.request()
    )
    assert literature_result.candidate is not None
    structural = next(
        item
        for item in literature_result.candidate.edges
        if item.edge_type is GraphEdgeType.supports_finding
    )
    payload = structural.model_dump(mode="json", exclude_none=True)
    payload["data_aggregation"] = data_edge.data_aggregation.model_dump(mode="json")
    with pytest.raises(ValidationError, match="provides_field edges require"):
        GraphArtifactEdge.model_validate_json(json.dumps(payload))


def test_candidate_rejects_duplicate_graph_evidence_use_binding_triples() -> None:
    fixture = build_data_graph_fixture()
    result = GraphPipeline(fixture.reader).admit(fixture.request())
    assert result.candidate is not None
    payload = result.candidate.model_dump(mode="json", exclude_none=True)
    duplicate = deepcopy(payload["evidence_uses"][0])
    duplicate["evidence_use_id"] += ".duplicate"
    payload["evidence_uses"].append(duplicate)
    payload["evidence_uses"].sort(key=lambda item: item["evidence_use_id"])
    payload["evidence_ids"].append(duplicate["evidence_use_id"])
    payload["evidence_ids"].sort()
    edge = next(
        item
        for item in payload["edges"]
        if item["edge_id"] == duplicate["graph_edge_id"]
    )
    edge["evidence_use_ids"].append(duplicate["evidence_use_id"])
    edge["evidence_use_ids"].sort()

    with pytest.raises(ValidationError, match="bindings must be unique"):
        GraphArtifactCandidate.model_validate_json(json.dumps(payload))
