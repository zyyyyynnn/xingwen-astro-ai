from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from graph_pipeline_test_support import stable_uuid
from graph_read_test_support import (
    GraphReadFixture,
    build_graph_read_fixture,
    build_multi_relation_graph_read_fixture,
)

from app.config import settings
from app.main import create_app
from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.core import ArtifactVersionDetail, SourceMode
from app.schemas.enums import GraphEdgeType, GraphNodeType
from app.schemas.graph_artifact import (
    GraphArtifactCandidate,
    compute_graph_input_hash,
    compute_graph_layout_hash,
    compute_graph_output_hash,
    compute_graph_scientific_hash,
)
from app.schemas.literature_artifact_api import LiteratureRelationRead
from app.schemas.literature_relation import (
    LiteratureRelationsCandidate,
    LiteratureRelationStatus,
)
from app.security import SecurityProblem
from app.services.graph_artifacts import GraphArtifactReadService
from app.services.literature_artifacts import LiteratureArtifactReadService

FORGED_HASH = f"sha256:{'0' * 64}"


@pytest.fixture(scope="module")
def read_fixture() -> GraphReadFixture:
    return build_graph_read_fixture()


def _service(fixture: GraphReadFixture) -> GraphArtifactReadService:
    """Bind the read service to the complete published upstream closure.

    A Graph read resolves every frozen ``GraphArtifactVersionReference``, so the
    service cannot be exercised against a stub that only holds the Graph
    ArtifactVersion; the whole upstream relation closure must be readable.
    """

    literature = LiteratureArtifactReadService(
        fixture.artifacts,  # type: ignore[arg-type]
        paper_summary_reader=fixture.artifacts.paper_summary_reader,  # type: ignore[arg-type]
    )
    return GraphArtifactReadService(
        fixture.artifacts,  # type: ignore[arg-type]
        literature_reader=literature,
    )


def test_graph_metadata_and_node_page_are_version_pinned(
    read_fixture: GraphReadFixture,
) -> None:
    service = _service(read_fixture)
    version_id = read_fixture.graph_version_id
    graph = service.get_graph(version_id=version_id, session_id="owner")
    nodes, cursor, has_more = service.list_nodes(
        version_id=version_id,
        session_id="owner",
        node_type=None,
        cursor=None,
        limit=2,
    )

    assert graph.version.artifact_version_id == version_id
    assert graph.node_count > 2
    assert tuple(item.node.node_id for item in nodes) == tuple(
        sorted(item.node.node_id for item in nodes)
    )
    assert cursor is not None
    assert has_more is True


def test_graph_cursor_is_bound_to_filter_scope(
    read_fixture: GraphReadFixture,
) -> None:
    service = _service(read_fixture)
    version_id = read_fixture.graph_version_id
    _, cursor, _ = service.list_nodes(
        version_id=version_id,
        session_id="owner",
        node_type=None,
        cursor=None,
        limit=1,
    )
    assert cursor is not None

    with pytest.raises(SecurityProblem) as exc_info:
        service.list_nodes(
            version_id=version_id,
            session_id="owner",
            node_type=GraphNodeType.claim,
            cursor=cursor,
            limit=1,
        )

    assert exc_info.value.code == "INVALID_CURSOR"


def test_graph_structural_edge_projects_evidence_and_snapshot(
    read_fixture: GraphReadFixture,
) -> None:
    edges, _, _ = asyncio.run(
        _service(read_fixture).list_edges(
            version_id=read_fixture.graph_version_id,
            session_id="owner",
            edge_type=GraphEdgeType.supports_finding,
            node_id=None,
            cursor=None,
            limit=100,
        )
    )

    assert edges
    assert all(item.relation is None for item in edges)
    assert all(item.evidence for item in edges)
    assert all(
        use.evidence.target_id == item.edge.edge_id
        for item in edges
        for use in item.evidence
    )


def test_graph_read_rejects_graph_owned_evidence_locator_swap(
    read_fixture: GraphReadFixture,
) -> None:
    service = _service(read_fixture)
    original = read_fixture.graph_version
    first = original.evidence[0]
    damaged = original.model_copy(
        update={
            "evidence": (
                first.model_copy(
                    update={
                        "locator": {
                            **first.locator,
                            "upstream_evidence_id": stable_uuid("forged:evidence-id"),
                        }
                    }
                ),
                *original.evidence[1:],
            )
        }
    )
    read_fixture.artifacts.versions[read_fixture.graph_version_id] = damaged
    try:
        with pytest.raises(SecurityProblem) as exc_info:
            service.get_graph(
                version_id=read_fixture.graph_version_id, session_id="owner"
            )
        assert exc_info.value.code == "PROVENANCE_SCOPE_VIOLATION"
    finally:
        read_fixture.artifacts.versions[read_fixture.graph_version_id] = original


def _drift_version_number(version: ArtifactVersionDetail) -> ArtifactVersionDetail:
    return version.model_copy(update={"version_number": version.version_number + 1})


def _drift_parameters_hash(version: ArtifactVersionDetail) -> ArtifactVersionDetail:
    runtime = version.producer_execution
    return version.model_copy(
        update={
            "producer_execution": runtime.model_copy(
                update={"parameters_hash": FORGED_HASH}
            )
        }
    )


def _drift_producer_version(version: ArtifactVersionDetail) -> ArtifactVersionDetail:
    producer = version.producer.model_copy(update={"version": "9.9.9"})
    runtime = version.producer_execution
    return version.model_copy(
        update={
            "producer": producer,
            "producer_execution": runtime.model_copy(update={"producer": producer}),
        }
    )


def _drift_source_mode(version: ArtifactVersionDetail) -> ArtifactVersionDetail:
    return version.model_copy(update={"source_mode": SourceMode.live})


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(None, id="missing_version"),
        pytest.param(_drift_version_number, id="version_number_drift"),
        pytest.param(_drift_parameters_hash, id="parameters_hash_drift"),
        pytest.param(_drift_producer_version, id="producer_version_drift"),
        pytest.param(_drift_source_mode, id="source_mode_drift"),
    ],
)
def test_graph_read_rejects_upstream_input_version_drift(
    read_fixture: GraphReadFixture,
    mutate: object,
) -> None:
    """A Graph read must re-close every frozen input pin against storage.

    ``GraphArtifactVersionReference`` freezes the upstream version number,
    source mode and producer identity, none of which are covered by the
    upstream payload's own hashes. Each mutation therefore keeps the
    LiteratureRelations ArtifactVersion internally self-consistent while
    breaking a pin the Graph committed to, and a deleted version leaves the
    Graph declaring an input that no longer exists. Both are cross-version
    references the read boundary must refuse.
    """

    service = _service(read_fixture)
    version_id = read_fixture.relation_version_id
    original = read_fixture.relation_version
    if mutate is None:
        del read_fixture.artifacts.versions[version_id]
    else:
        read_fixture.artifacts.versions[version_id] = mutate(original)  # type: ignore[operator]
    try:
        with pytest.raises(SecurityProblem) as exc_info:
            service.get_graph(
                version_id=read_fixture.graph_version_id, session_id="owner"
            )
        assert exc_info.value.status == 403
        assert exc_info.value.code == "PROVENANCE_SCOPE_VIOLATION"
    finally:
        read_fixture.artifacts.versions[version_id] = original


@pytest.mark.parametrize(
    "field",
    ["version_number", "content_hash", "input_hash", "output_hash", "parameters_hash"],
)
def test_graph_read_rejects_a_forged_input_version_pin(
    read_fixture: GraphReadFixture, field: str
) -> None:
    """A self-consistent Graph body cannot invent its own upstream facts.

    ``input_versions`` feeds ``input_hash``, ``scientific_hash`` and
    ``output_hash``, so a tampered pin can be made to satisfy every graph
    self-check by recomputing those hashes. Nothing inside the Graph can then
    detect the lie, which is exactly why the read boundary has to compare each
    pin against the persisted upstream ArtifactVersion.
    """

    original = read_fixture.graph_version
    content = json.loads(json.dumps(original.content))
    reference = content["input_versions"]["versions"][0]
    reference[field] = (
        reference["version_number"] + 1 if field == "version_number" else FORGED_HASH
    )
    content["input_hash"] = compute_graph_input_hash(content)
    content["scientific_hash"] = compute_graph_scientific_hash(content)
    content["graph_id"] = (
        f"graph.{content['scientific_hash'].removeprefix('sha256:')[:24]}"
    )
    content["output_hash"] = compute_graph_output_hash(content)
    content_hash = compute_canonical_payload_hash(content)
    runtime = original.producer_execution
    read_fixture.artifacts.versions[read_fixture.graph_version_id] = (
        original.model_copy(
            update={
                "content": content,
                "content_hash": content_hash,
                "input_hash": content["input_hash"],
                "producer_execution": runtime.model_copy(
                    update={
                        "input_hash": content["input_hash"],
                        "output_hash": content_hash,
                    }
                ),
            }
        )
    )
    try:
        with pytest.raises(SecurityProblem) as exc_info:
            _service(read_fixture).get_graph(
                version_id=read_fixture.graph_version_id, session_id="owner"
            )
        assert exc_info.value.status == 403
        assert exc_info.value.code == "PROVENANCE_SCOPE_VIOLATION"
    finally:
        read_fixture.artifacts.versions[read_fixture.graph_version_id] = original


def _client(fixture: GraphReadFixture, *, owner: bool = True) -> TestClient:
    app = create_app()
    app.state.artifact_read_service = fixture.artifacts  # type: ignore[assignment]
    app.state.paper_summary_read_service = fixture.artifacts.paper_summary_reader
    session, credential, _ = app.state.session_service.create(now=datetime.now(UTC))
    app.state.session_service.store.put(
        replace(session, id="owner" if owner else "other")
    )
    client = TestClient(app)
    client.cookies.set(settings.SESSION_COOKIE_NAME, credential, path="/api")
    return client


def _graph_path(fixture: GraphReadFixture, suffix: str = "") -> str:
    return f"/api/artifact-versions/{fixture.graph_version_id}/graph{suffix}"


def test_graph_http_reads_serialize_the_typed_projection_without_caching(
    read_fixture: GraphReadFixture,
) -> None:
    """HTTP must emit exactly the typed projection the service produced.

    ``GraphArtifactRead`` composes the ``strict=True`` graph domain models, so
    the transport direction is model -> JSON only. Comparing the response body
    against the serialized service result pins the transport without asking
    Pydantic to re-parse its own strict output.
    """

    client = _client(read_fixture)
    service = GraphArtifactReadService(read_fixture.artifacts)  # type: ignore[arg-type]
    expected = service.get_graph(
        version_id=read_fixture.graph_version_id, session_id="owner"
    )

    metadata = client.get(_graph_path(read_fixture))
    nodes = client.get(_graph_path(read_fixture, "/nodes"), params={"limit": 100})
    edges = client.get(_graph_path(read_fixture, "/edges"), params={"limit": 100})

    assert metadata.status_code == 200
    graph = metadata.json()["data"]
    assert graph == expected.model_dump(mode="json")
    assert graph["version"]["artifact_version_id"] == read_fixture.graph_version_id
    assert graph["project_id"] == read_fixture.graph_version.project_id
    assert graph["node_count"] == len(read_fixture.candidate.nodes)
    assert graph["edge_count"] == len(read_fixture.candidate.edges)
    assert graph["evidence_use_count"] == len(read_fixture.candidate.evidence_uses)
    assert metadata.json()["meta"]["request_id"]

    assert nodes.status_code == 200
    node_page = nodes.json()
    assert len(node_page["data"]) == graph["node_count"]
    assert node_page["page"]["has_more"] is False
    assert all(
        item["version"]["artifact_version_id"] == read_fixture.graph_version_id
        for item in node_page["data"]
    )

    assert edges.status_code == 200
    assert len(edges.json()["data"]) == graph["edge_count"]
    for response in (metadata, nodes, edges):
        assert response.headers["cache-control"] == "no-store"


def test_graph_metadata_layers_scientific_relation_and_layout_hint(
    read_fixture: GraphReadFixture,
) -> None:
    """Layout stays a declared hint; the API neither computes nor invents it."""

    client = _client(read_fixture)
    graph = client.get(_graph_path(read_fixture)).json()["data"]
    candidate = read_fixture.candidate

    assert graph["layout_hint"] == candidate.layout_hint.model_dump(mode="json")
    assert graph["version"]["layout_hash"] == candidate.layout_hash
    assert graph["version"]["scientific_hash"] == candidate.scientific_hash
    assert candidate.scientific_hash != candidate.layout_hash
    assert graph["integrity_report"] == candidate.integrity_report.model_dump(
        mode="json"
    )
    assert graph["progressive"] == candidate.progressive.model_dump(mode="json")
    assert "x" not in graph["layout_hint"]
    assert "y" not in graph["layout_hint"]


def test_graph_literature_edge_projects_its_accepted_relation_and_trace(
    read_fixture: GraphReadFixture,
) -> None:
    client = _client(read_fixture)
    response = client.get(
        _graph_path(read_fixture, f"/edges/{read_fixture.literature_edge_id}")
    )

    assert response.status_code == 200
    edge = response.json()["data"]
    binding = edge["edge"]["relation_trace"]
    assert binding is not None
    assert edge["relation"] is not None
    relation = LiteratureRelationRead.model_validate(edge["relation"])
    assert relation.relation.relation_id == binding["relation_id"]
    assert relation.relation.status is LiteratureRelationStatus.accepted
    assert relation.version.artifact_version_id == read_fixture.relation_version_id
    assert relation.version.project_id == read_fixture.graph_version.project_id
    assert relation.graph_eligible is True
    assert relation.reasoning_trace is not None
    assert relation.reasoning_trace.trace_id == binding["reasoning_trace_id"]
    assert relation.source_claim is not None
    assert relation.target_claim is not None
    assert relation.source_claim.claim.claim_id == binding["source_claim_id"]
    assert relation.target_claim.claim.claim_id == binding["target_claim_id"]
    assert edge["evidence"]
    assert sorted(item["use"]["evidence_use_id"] for item in edge["evidence"]) == list(
        edge["edge"]["evidence_use_ids"]
    )
    assert all(
        item["evidence"]["target_id"] == edge["edge"]["edge_id"]
        and item["source_snapshot"]["id"] == item["evidence"]["source_snapshot_id"]
        for item in edge["evidence"]
    )
    assert "chain_of_thought" not in response.text
    assert "raw_model_response" not in response.text


def test_graph_structural_edge_carries_no_scientific_relation(
    read_fixture: GraphReadFixture,
) -> None:
    response = _client(read_fixture).get(
        _graph_path(read_fixture, f"/edges/{read_fixture.structural_edge_id}")
    )

    assert response.status_code == 200
    edge = response.json()["data"]
    assert edge["edge"]["relation_trace"] is None
    assert edge["relation"] is None
    assert edge["evidence"]


@pytest.mark.parametrize(
    "update",
    [
        pytest.param({"status": LiteratureRelationStatus.candidate}, id="status"),
        pytest.param({"reasoning_trace_id": "trace.forged"}, id="trace_id"),
        pytest.param({"relation_id": "relation.forged"}, id="relation_id"),
    ],
)
def test_graph_literature_edge_rejects_a_relation_that_lost_its_binding(
    read_fixture: GraphReadFixture, update: dict[str, object]
) -> None:
    """A Graph edge only stores IDs, so the projection must be re-bound.

    Each mutation keeps the Relation ArtifactVersion internally readable but
    breaks one field the Graph committed to, which is a dangling reference the
    read boundary must refuse instead of repairing.
    """

    original = read_fixture.relation_version
    candidate = LiteratureRelationsCandidate.model_validate(original.content)
    target = next(
        item
        for item in candidate.relations
        if item.relation_id == read_fixture.relation_id
    )
    tampered = candidate.model_copy(
        update={
            "relations": tuple(
                item.model_copy(update=update)
                if item.relation_id == target.relation_id
                else item
                for item in candidate.relations
            )
        }
    )
    content = tampered.model_dump(mode="json", exclude_none=True)
    read_fixture.artifacts.versions[read_fixture.relation_version_id] = (
        original.model_copy(
            update={
                "content": content,
                "content_hash": compute_canonical_payload_hash(content),
            }
        )
    )
    try:
        response = _client(read_fixture).get(
            _graph_path(read_fixture, f"/edges/{read_fixture.literature_edge_id}")
        )
        assert response.status_code == 403
        assert response.json()["code"] == "PROVENANCE_SCOPE_VIOLATION"
    finally:
        read_fixture.artifacts.versions[read_fixture.relation_version_id] = original


def test_graph_filters_bound_pagination_and_stable_progressive_ordering(
    read_fixture: GraphReadFixture,
) -> None:
    client = _client(read_fixture)
    expected = tuple(sorted(item.node_id for item in read_fixture.candidate.nodes))

    collected: list[str] = []
    cursor: str | None = None
    pages = 0
    while True:
        params: dict[str, object] = {"limit": 2}
        if cursor is not None:
            params["cursor"] = cursor
        page = client.get(_graph_path(read_fixture, "/nodes"), params=params)
        assert page.status_code == 200
        body = page.json()
        assert body["page"]["limit"] == 2
        collected.extend(item["node"]["node_id"] for item in body["data"])
        pages += 1
        cursor = body["page"]["next_cursor"]
        if cursor is None:
            assert body["page"]["has_more"] is False
            break
    assert pages > 1
    assert tuple(collected) == expected

    claims = client.get(
        _graph_path(read_fixture, "/nodes"), params={"node_type": "claim", "limit": 100}
    )
    assert claims.status_code == 200
    assert claims.json()["data"]
    assert all(item["node"]["node_type"] == "claim" for item in claims.json()["data"])

    structural = client.get(
        _graph_path(read_fixture, "/edges"),
        params={"edge_type": "supports_finding", "limit": 100},
    )
    assert structural.status_code == 200
    assert [item["edge"]["edge_id"] for item in structural.json()["data"]] == [
        read_fixture.structural_edge_id
    ]

    literature_edge = next(
        item
        for item in read_fixture.candidate.edges
        if item.edge_id == read_fixture.literature_edge_id
    )
    incident = client.get(
        _graph_path(read_fixture, "/edges"),
        params={"node_id": literature_edge.source_node_id, "limit": 100},
    )
    assert incident.status_code == 200
    assert read_fixture.literature_edge_id in {
        item["edge"]["edge_id"] for item in incident.json()["data"]
    }

    assert (
        client.get(_graph_path(read_fixture, "/nodes"), params={"limit": 0}).status_code
        == 422
    )
    assert (
        client.get(
            _graph_path(read_fixture, "/nodes"), params={"limit": 101}
        ).status_code
        == 422
    )


def test_graph_cursor_reuse_across_filter_and_collection_is_rejected(
    read_fixture: GraphReadFixture,
) -> None:
    client = _client(read_fixture)
    page = client.get(_graph_path(read_fixture, "/nodes"), params={"limit": 1})
    cursor = page.json()["page"]["next_cursor"]
    assert cursor is not None

    filtered = client.get(
        _graph_path(read_fixture, "/nodes"),
        params={"node_type": "claim", "cursor": cursor, "limit": 1},
    )
    other_collection = client.get(
        _graph_path(read_fixture, "/edges"),
        params={"cursor": cursor, "limit": 1},
    )
    tampered = client.get(
        _graph_path(read_fixture, "/nodes"),
        params={"cursor": cursor[:-2] + "xy", "limit": 1},
    )
    for response in (filtered, other_collection, tampered):
        assert response.status_code == 400
        assert response.json()["code"] == "INVALID_CURSOR"


def test_graph_cursor_reuse_across_artifact_versions_is_rejected(
    read_fixture: GraphReadFixture,
) -> None:
    """A page cursor is scoped to one Graph ArtifactVersion.

    The fixture publishes a second, independently identified Graph
    ArtifactVersion carrying the same admitted content, so node identifiers
    alone cannot distinguish the two. Only the cursor scope's ``version_id``
    can, which is what makes this a real cross-version regression rather than
    an ordering coincidence.
    """

    client = _client(read_fixture)
    first = read_fixture.graph_version_id
    second = read_fixture.second_graph_version_id
    assert first != second
    assert (
        read_fixture.second_graph_version.content == read_fixture.graph_version.content
    )

    def page(version_id: str, cursor: str | None = None) -> dict[str, object]:
        params: dict[str, object] = {"limit": 1}
        if cursor is not None:
            params["cursor"] = cursor
        response = client.get(
            f"/api/artifact-versions/{version_id}/graph/nodes", params=params
        )
        return {"status": response.status_code, "body": response.json()}

    first_page = page(first)
    second_page = page(second)
    assert first_page["status"] == 200
    assert second_page["status"] == 200
    first_cursor = first_page["body"]["page"]["next_cursor"]  # type: ignore[index]
    second_cursor = second_page["body"]["page"]["next_cursor"]  # type: ignore[index]
    assert isinstance(first_cursor, str)
    assert isinstance(second_cursor, str)
    assert first_cursor != second_cursor

    for version_id, foreign in ((second, first_cursor), (first, second_cursor)):
        rejected = page(version_id, foreign)
        assert rejected["status"] == 400
        assert rejected["body"]["code"] == "INVALID_CURSOR"  # type: ignore[index]


def test_graph_reads_require_a_session_and_hide_other_projects(
    read_fixture: GraphReadFixture,
) -> None:
    app = create_app()
    app.state.artifact_read_service = read_fixture.artifacts  # type: ignore[assignment]
    assert TestClient(app).get(_graph_path(read_fixture)).status_code == 401

    response = _client(read_fixture, owner=False).get(_graph_path(read_fixture))
    assert response.status_code == 404
    assert response.json()["code"] == "ARTIFACT_VERSION_NOT_FOUND"


def test_unknown_graph_objects_return_non_disclosing_404(
    read_fixture: GraphReadFixture,
) -> None:
    client = _client(read_fixture)
    node = client.get(_graph_path(read_fixture, "/nodes/node.missing"))
    edge = client.get(_graph_path(read_fixture, "/edges/edge.missing"))

    assert (node.status_code, node.json()["code"]) == (404, "GRAPH_NODE_NOT_FOUND")
    assert (edge.status_code, edge.json()["code"]) == (404, "GRAPH_EDGE_NOT_FOUND")


def test_graph_reads_reject_a_non_graph_artifact_kind(
    read_fixture: GraphReadFixture,
) -> None:
    path = f"/api/artifact-versions/{read_fixture.relation_version_id}/graph"
    response = _client(read_fixture).get(path)

    assert response.status_code == 409
    assert response.json()["code"] == "ARTIFACT_KIND_MISMATCH"


def test_graph_reads_reject_invalid_schema_and_oversized_content(
    read_fixture: GraphReadFixture,
) -> None:
    client = _client(read_fixture)
    original = read_fixture.graph_version
    invalid_content = {**original.content, "taxonomy": {"taxonomy_version": "9.9.9"}}
    read_fixture.artifacts.versions[read_fixture.graph_version_id] = (
        original.model_copy(
            update={
                "content": invalid_content,
                "content_hash": compute_canonical_payload_hash(invalid_content),
            }
        )
    )
    try:
        invalid = client.get(_graph_path(read_fixture))
        assert invalid.status_code == 422
        assert invalid.json()["code"] == "GRAPH_SCHEMA_INVALID"
    finally:
        read_fixture.artifacts.versions[read_fixture.graph_version_id] = original

    oversized = {**original.content, "_fixture_padding": "p" * (9 * 1024 * 1024)}
    read_fixture.artifacts.versions[read_fixture.graph_version_id] = (
        original.model_copy(
            update={
                "content": oversized,
                "content_hash": compute_canonical_payload_hash(oversized),
            }
        )
    )
    try:
        too_large = client.get(_graph_path(read_fixture))
        assert too_large.status_code == 413
        assert too_large.json()["code"] == "GRAPH_ARTIFACT_SIZE_LIMIT_EXCEEDED"
    finally:
        read_fixture.artifacts.versions[read_fixture.graph_version_id] = original


def test_graph_cursor_invalid_base64_characters_rejected(
    read_fixture: GraphReadFixture,
) -> None:
    client = _client(read_fixture)
    valid_cursor = client.get(_graph_path(read_fixture, "/nodes?limit=1")).json()[
        "page"
    ]["next_cursor"]
    assert valid_cursor is not None

    invalid_cursor = valid_cursor + "!!!!"
    response = client.get(_graph_path(read_fixture, f"/nodes?cursor={invalid_cursor}"))
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_CURSOR"


def test_graph_cursor_overlong_string_rejected(
    read_fixture: GraphReadFixture,
) -> None:
    client = _client(read_fixture)
    overlong_cursor = "A" * 4097
    response = client.get(_graph_path(read_fixture, f"/nodes?cursor={overlong_cursor}"))
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_CURSOR"


def test_graph_list_edges_resolves_literature_relations_context_once_per_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from typing import Any
    from app.services.literature_artifacts import LiteratureArtifactReadService

    fixture = build_multi_relation_graph_read_fixture()

    call_count = 0
    original_context = LiteratureArtifactReadService._relations_context

    async def counting_relations_context(
        self: LiteratureArtifactReadService, **kwargs: Any
    ) -> Any:
        nonlocal call_count
        call_count += 1
        return await original_context(self, **kwargs)

    monkeypatch.setattr(
        LiteratureArtifactReadService,
        "_relations_context",
        counting_relations_context,
    )

    client = _client(fixture)
    response = client.get(_graph_path(fixture, "/edges"))
    assert response.status_code == 200
    edges = response.json()["data"]
    literature_edges = [item for item in edges if item["relation"] is not None]

    assert len(literature_edges) >= 2, (
        "Multi-relation fixture must return >= 2 literature edges"
    )
    assert call_count == 1, (
        "Single list_edges page must resolve LiteratureRelations context exactly once"
    )

    expected_bindings = {
        edge.edge_id: edge.relation_trace
        for edge in fixture.candidate.edges
        if edge.relation_trace is not None
    }
    expected_relation_ids = {
        binding.relation_id
        for binding in expected_bindings.values()
        if binding is not None
    }
    returned_relation_ids = {
        item["relation"]["relation"]["relation_id"] for item in literature_edges
    }
    assert len(literature_edges) == len(expected_bindings)
    assert len(expected_relation_ids) >= 2
    assert len(expected_relation_ids) == len(expected_bindings)
    assert returned_relation_ids == expected_relation_ids

    for item in literature_edges:
        binding = item["edge"]["relation_trace"]
        relation = item["relation"]
        assert relation is not None
        assert relation["relation"]["relation_id"] == binding["relation_id"]
        assert relation["relation"]["source_claim_id"] == binding["source_claim_id"]
        assert relation["relation"]["target_claim_id"] == binding["target_claim_id"]
        assert relation["reasoning_trace"]["trace_id"] == binding["reasoning_trace_id"]
        assert item["relation"]["graph_eligible"] is True

    original_version = fixture.artifacts.versions[fixture.graph_version_id]
    content = dict(original_version.content)
    raw_edges = [dict(e) for e in content["edges"]]
    first_lit_index = next(
        i
        for i, e in enumerate(raw_edges)
        if e.get("edge_id") == fixture.literature_edge_id
    )
    second_trace_id = next(
        e["relation_trace"]["reasoning_trace_id"]
        for e in raw_edges
        if e.get("relation_trace") is not None
        and e["edge_id"] != fixture.literature_edge_id
    )
    trace = dict(raw_edges[first_lit_index]["relation_trace"])
    assert trace["reasoning_trace_id"] != second_trace_id
    trace["reasoning_trace_id"] = second_trace_id
    raw_edges[first_lit_index]["relation_trace"] = trace
    content["edges"] = raw_edges

    content["input_hash"] = compute_graph_input_hash(content)
    content["scientific_hash"] = compute_graph_scientific_hash(content)
    content["layout_hash"] = compute_graph_layout_hash(content)
    content["graph_id"] = (
        f"graph.{content['scientific_hash'].removeprefix('sha256:')[:24]}"
    )
    content["output_hash"] = compute_graph_output_hash(content)
    validated = GraphArtifactCandidate.model_validate_json(
        json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )
    validated = GraphArtifactCandidate.model_validate(
        validated.model_dump(mode="python", exclude_none=True)
    )
    assert validated.input_hash == original_version.input_hash
    assert validated.edges[first_lit_index].relation_trace is not None
    assert (
        validated.edges[first_lit_index].relation_trace.reasoning_trace_id
        == second_trace_id
    )

    tampered_content_hash = compute_canonical_payload_hash(content)
    tampered_runtime = original_version.producer_execution.model_copy(
        update={"output_hash": tampered_content_hash}
    )

    fixture.artifacts.versions[fixture.graph_version_id] = original_version.model_copy(
        update={
            "content": content,
            "content_hash": tampered_content_hash,
            "producer_execution": tampered_runtime,
        }
    )
    from app.services import graph_artifacts as graph_artifacts_module

    projection_call_count = 0
    original_projection = graph_artifacts_module._validate_relation_trace_projection

    def counting_projection(*args: Any, **kwargs: Any) -> None:
        nonlocal projection_call_count
        projection_call_count += 1
        original_projection(*args, **kwargs)

    monkeypatch.setattr(
        graph_artifacts_module,
        "_validate_relation_trace_projection",
        counting_projection,
    )
    try:
        tampered_response = client.get(_graph_path(fixture, "/edges"))
        assert projection_call_count >= 1
        assert tampered_response.status_code == 403
        assert tampered_response.json()["code"] == "PROVENANCE_SCOPE_VIOLATION"
    finally:
        fixture.artifacts.versions[fixture.graph_version_id] = original_version
