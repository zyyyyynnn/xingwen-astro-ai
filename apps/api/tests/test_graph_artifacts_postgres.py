"""PostgreSQL integration coverage for version-pinned Evidence Graph reads.

Set TEST_DATABASE_URL to an isolated database whose name contains ``test``.
The module persists one real Evidence Graph ArtifactVersion together with the
complete upstream LiteratureRelation/LiteratureClaim closure it projects, so
the read boundary is exercised against real UUID storage identities instead of
in-memory fixtures.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select, update

from app.config import settings
from app.db.models import (
    ArtifactVersionModel,
    EvidenceModel,
    ProducerExecutionModel,
    ResearchArtifactModel,
    ResearchRunModel,
    RunStepModel,
    SourceSnapshotModel,
    StepAttemptModel,
)
from app.db.session import session_factory
from app.main import create_app
from app.schemas.core import ArtifactVersionDetail
from app.services.artifacts import ArtifactReadService
from app.services.graph_inputs import PostgresEvidenceRestrictionReadAdapter

from authoring_test_support import (
    build_contract_draft,
    build_research_contract,
    build_research_project,
    persist_authoring_models,
)
from graph_read_test_support import PROJECT_ID, build_graph_read_fixture
from literature_artifact_test_support import FixturePaperSummaryReads
from test_artifact_publisher_postgres import postgres_engine  # noqa: F401

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL, reason="TEST_DATABASE_URL is not configured"
)
GRAPH_PROJECT_ID = UUID(PROJECT_ID)
NOW = datetime(2026, 8, 10, 8, 0, tzinfo=UTC)
HASH_A = "sha256:" + "a" * 64
HASH_B = "sha256:" + "b" * 64


def _stable_uuid(label: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"graph-read-postgres:{label}")


def _persisted_uuid(value: str) -> UUID:
    """Keep already-persistent identities and derive the fixture-owned rest."""

    try:
        return UUID(value)
    except (AttributeError, TypeError, ValueError):
        return _stable_uuid(value)


@pytest.fixture(scope="module")
def graph_context(postgres_engine: Engine) -> dict[str, Any]:  # noqa: F811
    fixture = build_graph_read_fixture()
    versions: tuple[ArtifactVersionDetail, ...] = tuple(
        sorted(fixture.artifacts.versions.values(), key=lambda item: item.id)
    )
    kinds = {
        version.id: fixture.artifacts.artifacts[version.artifact_id].kind.value
        for version in versions
    }
    artifact_ids = {
        version.artifact_id: _persisted_uuid(version.artifact_id)
        for version in versions
    }
    snapshot_details = {
        snapshot.id: snapshot
        for version in versions
        for snapshot in version.source_snapshots
    }
    snapshot_ids = {key: _persisted_uuid(key) for key in snapshot_details}
    evidence_details = {
        evidence.id: evidence for version in versions for evidence in version.evidence
    }
    evidence_ids = {key: _persisted_uuid(key) for key in evidence_details}

    contract_id = _stable_uuid("contract")
    draft_id = _stable_uuid("draft")
    run_id = _stable_uuid("run")
    step_id = _stable_uuid("step")
    attempt_id = _stable_uuid("attempt")

    factory = session_factory(postgres_engine)
    app = create_app()
    reads = ArtifactReadService(factory)
    app.state.artifact_read_service = reads
    app.state.paper_summary_read_service = FixturePaperSummaryReads(reads)
    session_now = datetime.now(UTC)
    owner, owner_credential, _ = app.state.session_service.create(now=session_now)
    _, other_credential, _ = app.state.session_service.create(now=session_now)

    project = build_research_project(
        project_id=GRAPH_PROJECT_ID,
        session_id=owner.id,
        name="Evidence Graph PostgreSQL reads",
        case_key="exoplanet_host_star",
        created_at=NOW,
        updated_at=NOW,
    )
    draft = build_contract_draft(
        project,
        draft_id=draft_id,
        intent="Evidence Graph PostgreSQL read fixture",
        content={},
        created_at=NOW,
        updated_at=NOW,
    )
    contract = build_research_contract(
        project,
        draft,
        contract_id=contract_id,
        content_hash=HASH_A,
        content={},
        created_at=NOW,
    )

    with factory() as session, session.begin():
        persist_authoring_models(
            session,
            project=project,
            draft=draft,
            contract=contract,
        )
        session.add(
            ResearchRunModel(
                id=run_id,
                project_id=GRAPH_PROJECT_ID,
                contract_id=contract_id,
                execution_mode="live",
                status="completed",
                progress=100,
                derivation_kind="original",
                cache_policy="disabled",
                latest_event_sequence=0,
                revision=1,
                idempotency_key="graph-read-postgres-run",
                request_hash=HASH_B,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        session.flush()
        session.add(
            RunStepModel(
                id=step_id,
                run_id=run_id,
                position=0,
                key="building_graph",
                label="Build graph",
                enter_status="building_graph",
                success_status="completed",
                status="completed",
                progress=100,
                public_message="Completed",
                created_at=NOW,
            )
        )
        session.flush()
        session.add(
            StepAttemptModel(
                id=attempt_id,
                run_step_id=step_id,
                attempt_number=1,
                idempotency_key="graph-read-postgres-attempt",
                status="completed",
                started_at=NOW,
                finished_at=NOW + timedelta(seconds=1),
                created_at=NOW,
            )
        )
        session.flush()
        for key, detail in snapshot_details.items():
            session.add(
                SourceSnapshotModel(
                    id=snapshot_ids[key],
                    project_id=GRAPH_PROJECT_ID,
                    source_id=detail.source_id,
                    source_type=detail.source_type,
                    retrieved_at=detail.retrieved_at,
                    query=detail.query,
                    query_hash=detail.query_hash,
                    source_version_or_etag=detail.source_version_or_etag,
                    content_hash=detail.content_hash,
                    license_note=detail.license_note,
                    cache_version=detail.cache_version,
                    request_metadata=detail.request_metadata,
                )
            )
        session.flush()
        for index, version in enumerate(versions):
            kind = kinds[version.id]
            artifact_id = artifact_ids[version.artifact_id]
            execution_id = _persisted_uuid(version.producer_execution.id)
            runtime = version.producer_execution
            producer = runtime.producer
            artifact = ResearchArtifactModel(
                id=artifact_id,
                project_id=GRAPH_PROJECT_ID,
                kind=kind,
                title=f"Evidence Graph read {kind}",
                logical_key=f"{kind}.{index}",
                created_at=NOW,
            )
            session.add(artifact)
            session.flush()
            session.add(
                ProducerExecutionModel(
                    id=execution_id,
                    run_id=run_id,
                    run_step_id=step_id,
                    step_attempt_id=attempt_id,
                    step_key=runtime.step_key,
                    idempotency_key=f"graph-read-producer-{index}",
                    lease_generation=1,
                    producer_type=producer.type,
                    producer_name=producer.name,
                    producer_version=producer.version,
                    model_provider=producer.model_provider,
                    requested_model=producer.requested_model,
                    prompt_name=producer.prompt_name,
                    prompt_version=producer.prompt_version,
                    prompt_hash=producer.prompt_hash,
                    parameters=runtime.parameters,
                    parameters_hash=runtime.parameters_hash,
                    input_hash=runtime.input_hash,
                    output_hash=runtime.output_hash,
                    status=runtime.status,
                    started_at=runtime.started_at,
                    finished_at=runtime.finished_at,
                    token_usage=runtime.token_usage,
                    latency_ms=runtime.latency_ms,
                    error_code=runtime.error_code,
                    created_at=NOW,
                )
            )
            session.flush()
            row = ArtifactVersionModel(
                id=UUID(version.id),
                artifact_id=artifact_id,
                project_id=GRAPH_PROJECT_ID,
                created_by_run_id=run_id,
                run_step_id=step_id,
                step_attempt_id=attempt_id,
                producer_execution_id=execution_id,
                version_number=1,
                publication_key=f"graph-read-postgres-{index}",
                schema_version=version.schema_version,
                content=version.content,
                content_hash=version.content_hash,
                input_hash=version.input_hash,
                source_mode=version.source_mode,
                producer=version.producer.model_dump(mode="json", exclude_none=True),
                source_snapshot_ids=[
                    str(snapshot_ids[item.id]) for item in version.source_snapshots
                ],
                evidence_ids=[str(evidence_ids[item.id]) for item in version.evidence],
                created_at=NOW,
            )
            session.add(row)
            session.flush()
            artifact.latest_version_id = row.id
        session.flush()
        for key, detail in evidence_details.items():
            session.add(
                EvidenceModel(
                    id=evidence_ids[key],
                    project_id=GRAPH_PROJECT_ID,
                    artifact_version_id=UUID(detail.artifact_version_id),
                    target_type=detail.target_type,
                    target_id=detail.target_id,
                    evidence_type=detail.evidence_type,
                    source_snapshot_id=snapshot_ids[detail.source_snapshot_id],
                    paper_id=detail.paper_id,
                    locator=detail.locator,
                    quote_or_value=detail.quote_or_value,
                    extraction_method=detail.extraction_method,
                    confidence=detail.confidence,
                    is_restricted=False,
                    created_at=NOW,
                )
            )

    def client(credential: str) -> TestClient:
        result = TestClient(app)
        result.cookies.set(settings.SESSION_COOKIE_NAME, credential, path="/api")
        return result

    graph_evidence_ids = tuple(
        str(evidence_ids[item.id]) for item in fixture.graph_version.evidence
    )
    return {
        "factory": factory,
        "owner": client(owner_credential),
        "other": client(other_credential),
        "fixture": fixture,
        "graph_evidence_ids": graph_evidence_ids,
        "graph_snapshot_ids": tuple(
            str(snapshot_ids[item.id]) for item in fixture.graph_version.source_snapshots
        ),
    }



def test_postgres_evidence_restriction_adapter_reads_exact_storage_truth(
    graph_context: dict[str, Any],
) -> None:
    factory = graph_context["factory"]
    evidence_id = str(graph_context["graph_evidence_ids"][0])
    adapter = PostgresEvidenceRestrictionReadAdapter(factory)

    initial = adapter.read_restrictions(
        project_id=str(GRAPH_PROJECT_ID), evidence_ids=(evidence_id,)
    )
    assert len(initial) == 1
    assert initial[0].evidence_id == evidence_id
    assert initial[0].project_id == str(GRAPH_PROJECT_ID)
    assert initial[0].is_restricted is False

    with factory() as session, session.begin():
        session.execute(
            update(EvidenceModel)
            .where(EvidenceModel.id == UUID(evidence_id))
            .values(is_restricted=True)
        )

    restricted = adapter.read_restrictions(
        project_id=str(GRAPH_PROJECT_ID), evidence_ids=(evidence_id,)
    )
    assert len(restricted) == 1
    assert restricted[0].is_restricted is True

    with factory() as session, session.begin():
        session.execute(
            update(EvidenceModel)
            .where(EvidenceModel.id == UUID(evidence_id))
            .values(is_restricted=False)
        )

def _graph_path(graph_context: dict[str, Any], suffix: str = "") -> str:
    version_id = graph_context["fixture"].graph_version_id
    return f"/api/artifact-versions/{version_id}/graph{suffix}"


def test_postgres_graph_reads_close_uuid_provenance_on_every_endpoint(
    graph_context: dict[str, Any],
) -> None:
    owner = graph_context["owner"]
    fixture = graph_context["fixture"]
    candidate = fixture.candidate

    metadata = owner.get(_graph_path(graph_context))
    nodes = owner.get(_graph_path(graph_context, "/nodes"), params={"limit": 100})
    edges = owner.get(_graph_path(graph_context, "/edges"), params={"limit": 100})
    node = owner.get(
        _graph_path(
            graph_context,
            f"/nodes/{sorted(candidate.nodes, key=lambda item: item.node_id)[0].node_id}",
        )
    )
    edge = owner.get(
        _graph_path(graph_context, f"/edges/{fixture.literature_edge_id}")
    )

    assert metadata.status_code == 200
    graph = metadata.json()["data"]
    assert graph["project_id"] == str(GRAPH_PROJECT_ID)
    assert graph["node_count"] == len(candidate.nodes)
    assert graph["edge_count"] == len(candidate.edges)
    assert graph["evidence_use_count"] == len(candidate.evidence_uses)

    assert nodes.status_code == 200
    assert len(nodes.json()["data"]) == len(candidate.nodes)
    assert edges.status_code == 200
    assert len(edges.json()["data"]) == len(candidate.edges)
    assert node.status_code == 200
    assert edge.status_code == 200

    payload = edge.json()["data"]
    assert payload["relation"] is not None
    assert payload["relation"]["relation"]["status"] == "accepted"
    assert payload["relation"]["graph_eligible"] is True
    assert (
        payload["relation"]["version"]["artifact_version_id"]
        == fixture.relation_version_id
    )
    assert payload["evidence"]
    persisted_evidence_ids = set(graph_context["graph_evidence_ids"])
    persisted_snapshot_ids = set(graph_context["graph_snapshot_ids"])
    for item in payload["evidence"]:
        assert item["evidence"]["id"] in persisted_evidence_ids
        assert item["source_snapshot"]["id"] in persisted_snapshot_ids
        assert item["evidence"]["source_snapshot_id"] == item["source_snapshot"]["id"]
        assert item["evidence"]["target_id"] == payload["edge"]["edge_id"]
        assert item["evidence"]["id"] != item["use"]["upstream_evidence_id"]
        UUID(item["evidence"]["id"])
        UUID(item["source_snapshot"]["id"])
    assert "chain_of_thought" not in edge.text
    assert "raw_model_response" not in edge.text


def test_postgres_graph_reads_hide_cross_session_versions(
    graph_context: dict[str, Any],
) -> None:
    response = graph_context["other"].get(_graph_path(graph_context))

    assert response.status_code == 404
    assert response.json()["code"] == "ARTIFACT_VERSION_NOT_FOUND"


def test_postgres_graph_node_pagination_is_stable_and_cursor_scoped(
    graph_context: dict[str, Any],
) -> None:
    owner = graph_context["owner"]
    expected = tuple(
        sorted(item.node_id for item in graph_context["fixture"].candidate.nodes)
    )

    collected: list[str] = []
    cursor: str | None = None
    while True:
        params: dict[str, Any] = {"limit": 2}
        if cursor is not None:
            params["cursor"] = cursor
        page = owner.get(_graph_path(graph_context, "/nodes"), params=params)
        assert page.status_code == 200
        body = page.json()
        collected.extend(item["node"]["node_id"] for item in body["data"])
        cursor = body["page"]["next_cursor"]
        if cursor is None:
            break
    assert tuple(collected) == expected

    first = owner.get(_graph_path(graph_context, "/nodes"), params={"limit": 1})
    reusable = first.json()["page"]["next_cursor"]
    assert reusable is not None
    reused = owner.get(
        _graph_path(graph_context, "/nodes"),
        params={"node_type": "claim", "cursor": reusable, "limit": 1},
    )
    assert reused.status_code == 400
    assert reused.json()["code"] == "INVALID_CURSOR"


def test_postgres_graph_reads_reject_tampered_graph_owned_evidence(
    graph_context: dict[str, Any],
) -> None:
    factory = graph_context["factory"]
    evidence_id = UUID(graph_context["graph_evidence_ids"][0])
    with factory() as session, session.begin():
        row = session.get(EvidenceModel, evidence_id)
        assert row is not None
        original = dict(row.locator)
        row.locator = {
            **original,
            "upstream_evidence_id": str(uuid5(NAMESPACE_URL, "forged")),
        }
    try:
        response = graph_context["owner"].get(_graph_path(graph_context))
        assert response.status_code == 403
        assert response.json()["code"] == "PROVENANCE_SCOPE_VIOLATION"
    finally:
        with factory() as session, session.begin():
            row = session.get(EvidenceModel, evidence_id)
            assert row is not None
            row.locator = original


def test_postgres_graph_reads_reject_upstream_input_version_drift(
    graph_context: dict[str, Any],
) -> None:
    """The frozen input pins must be re-closed against real UUID storage.

    ``version_number`` and the producer ``parameters_hash`` live outside the
    upstream payload, so no content hash protects them. Drifting either row in
    PostgreSQL leaves the LiteratureRelations ArtifactVersion internally
    readable while breaking a pin the Graph committed to, which the read
    boundary must refuse instead of projecting a stale input.
    """

    factory = graph_context["factory"]
    version_id = UUID(graph_context["fixture"].relation_version_id)
    owner = graph_context["owner"]

    with factory() as session:
        row = session.get(ArtifactVersionModel, version_id)
        assert row is not None
        execution_id = row.producer_execution_id
        original_version_number = row.version_number
        execution = session.get(ProducerExecutionModel, execution_id)
        assert execution is not None
        original_parameters_hash = execution.parameters_hash

    with factory() as session, session.begin():
        row = session.get(ArtifactVersionModel, version_id)
        assert row is not None
        row.version_number = original_version_number + 1
    try:
        drifted = owner.get(_graph_path(graph_context))
        assert drifted.status_code == 403
        assert drifted.json()["code"] == "PROVENANCE_SCOPE_VIOLATION"
    finally:
        with factory() as session, session.begin():
            row = session.get(ArtifactVersionModel, version_id)
            assert row is not None
            row.version_number = original_version_number

    assert owner.get(_graph_path(graph_context)).status_code == 200

    with factory() as session, session.begin():
        execution = session.get(ProducerExecutionModel, execution_id)
        assert execution is not None
        execution.parameters_hash = HASH_A
    try:
        drifted = owner.get(_graph_path(graph_context))
        assert drifted.status_code == 403
        assert drifted.json()["code"] == "PROVENANCE_SCOPE_VIOLATION"
    finally:
        with factory() as session, session.begin():
            execution = session.get(ProducerExecutionModel, execution_id)
            assert execution is not None
            execution.parameters_hash = original_parameters_hash

    assert owner.get(_graph_path(graph_context)).status_code == 200


def test_postgres_graph_cursor_reuse_across_artifact_versions_is_rejected(
    graph_context: dict[str, Any],
) -> None:
    """Cursor scope stays bound to one persisted Graph ArtifactVersion."""

    owner = graph_context["owner"]
    fixture = graph_context["fixture"]
    first = fixture.graph_version_id
    second = fixture.second_graph_version_id

    def next_cursor(version_id: str) -> str:
        page = owner.get(
            f"/api/artifact-versions/{version_id}/graph/nodes", params={"limit": 1}
        )
        assert page.status_code == 200
        cursor = page.json()["page"]["next_cursor"]
        assert isinstance(cursor, str)
        return cursor

    first_cursor = next_cursor(first)
    second_cursor = next_cursor(second)
    assert first_cursor != second_cursor

    for version_id, foreign in ((second, first_cursor), (first, second_cursor)):
        rejected = owner.get(
            f"/api/artifact-versions/{version_id}/graph/nodes",
            params={"cursor": foreign, "limit": 1},
        )
        assert rejected.status_code == 400
        assert rejected.json()["code"] == "INVALID_CURSOR"


def test_postgres_graph_reads_reject_a_non_graph_artifact_kind(
    graph_context: dict[str, Any],
) -> None:
    version_id = graph_context["fixture"].relation_version_id
    response = graph_context["owner"].get(
        f"/api/artifact-versions/{version_id}/graph"
    )

    assert response.status_code == 409
    assert response.json()["code"] == "ARTIFACT_KIND_MISMATCH"


def test_postgres_graph_version_rows_are_uuid_bound_to_the_project(
    graph_context: dict[str, Any],
) -> None:
    factory = graph_context["factory"]
    version_id = UUID(graph_context["fixture"].graph_version_id)
    with factory() as session:
        row = session.get(ArtifactVersionModel, version_id)
        assert row is not None
        assert row.project_id == GRAPH_PROJECT_ID
        evidence = tuple(
            session.scalars(
                select(EvidenceModel).where(
                    EvidenceModel.artifact_version_id == version_id
                )
            )
        )
    assert {str(item.id) for item in evidence} == set(
        graph_context["graph_evidence_ids"]
    )
    assert all(item.target_type == "graph_edge" for item in evidence)
    assert all(item.extraction_method == "graph_admission" for item in evidence)
