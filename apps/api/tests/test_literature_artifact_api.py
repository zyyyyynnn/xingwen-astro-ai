from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest
from app.config import settings
from app.main import create_app
from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.literature_artifact_api import (
    LiteratureClaimRead,
    LiteratureReasoningTraceRead,
    LiteratureRelationRead,
)
from app.schemas.literature_claim import LiteratureClaimStatus
from app.schemas.literature_relation import (
    LiteratureRelationsCandidate,
    LiteratureRelationStatus,
)
from app.security import SecurityProblem
from app.services.literature_artifacts import (
    LiteratureArtifactReadService,
    _encode_cursor,
    _relation_snapshot_references,
)
from fastapi.testclient import TestClient
from literature_artifact_test_support import (
    LiteratureFixture,
    build_literature_fixture,
)


@pytest.fixture(scope="module")
def fixture() -> LiteratureFixture:
    return build_literature_fixture()


def _client(fixture: LiteratureFixture, *, owner: bool = True) -> TestClient:
    app = create_app()
    app.state.artifact_read_service = fixture.artifacts  # type: ignore[assignment]
    session, credential, _ = app.state.session_service.create(now=datetime.now(UTC))
    session_id = "owner" if owner else "other"
    app.state.session_service.store.put(replace(session, id=session_id))
    client = TestClient(app)
    client.cookies.set(settings.SESSION_COOKIE_NAME, credential, path="/api")
    return client


def test_claim_read_is_version_pinned_and_closes_summary_evidence(
    fixture: LiteratureFixture,
) -> None:
    service = LiteratureArtifactReadService(fixture.artifacts)  # type: ignore[arg-type]
    items, cursor, has_more = service.list_claims(
        version_id=fixture.claim_version_ids[0],
        session_id="owner",
        status=LiteratureClaimStatus.accepted,
        cursor=None,
        limit=20,
    )

    assert len(items) == 1
    assert cursor is None
    assert has_more is False
    item = LiteratureClaimRead.model_validate(items[0])
    assert item.version.artifact_version_id == fixture.claim_version_ids[0]
    assert (
        item.paper_summary.artifact_version_id
        == item.claim.source_paper_summary_artifact_version_id
    )
    assert item.evidence
    assert item.source_snapshots
    assert {evidence.target_id for evidence in item.evidence} == {item.claim.claim_id}
    assert fixture.artifacts.full_content_requests
    assert all(fixture.artifacts.full_content_requests)


def test_relation_and_trace_http_reads_return_complete_associations(
    fixture: LiteratureFixture,
) -> None:
    client = _client(fixture)
    relation_response = client.get(
        f"/api/artifact-versions/{fixture.relation_version_id}"
        f"/literature-relations/{fixture.accepted_relation_id}"
    )

    assert relation_response.status_code == 200
    relation = LiteratureRelationRead.model_validate(relation_response.json()["data"])
    assert relation.version.artifact_version_id == fixture.relation_version_id
    assert relation.relation.status is LiteratureRelationStatus.accepted
    assert relation.graph_eligible is True
    assert relation.source_claim is not None
    assert relation.target_claim is not None
    assert relation.reasoning_trace is not None
    assert relation.evidence
    assert relation.source_snapshots
    assert relation_response.headers["cache-control"] == "no-store"

    trace_response = client.get(
        f"/api/artifact-versions/{fixture.relation_version_id}"
        f"/reasoning-traces/{fixture.trace_id}"
    )
    assert trace_response.status_code == 200
    trace = LiteratureReasoningTraceRead.model_validate(trace_response.json()["data"])
    assert trace.trace.relation_id == fixture.accepted_relation_id
    assert trace.relation.reasoning_trace_id == trace.trace.trace_id
    assert trace.source_claim.claim.claim_id == trace.trace.premise_claim_ids[0]
    assert trace.target_claim.claim.claim_id == trace.trace.premise_claim_ids[1]
    assert "chain_of_thought" not in trace_response.text
    assert "raw_model_response" not in trace_response.text
    assert trace.trace.model_response_hash.startswith("sha256:")


def test_relation_status_filter_and_cursor_scope_are_bound(
    fixture: LiteratureFixture,
) -> None:
    client = _client(fixture)
    response = client.get(
        f"/api/artifact-versions/{fixture.relation_version_id}/literature-relations",
        params={"status": "accepted", "limit": 1},
    )
    assert response.status_code == 200
    assert len(response.json()["data"]) == 1
    assert response.json()["data"][0]["graph_eligible"] is True

    cursor = _encode_cursor(
        version_id=fixture.relation_version_id,
        collection="literature_relations",
        status=None,
        last_id=fixture.accepted_relation_id,
    )
    mismatched = client.get(
        f"/api/artifact-versions/{fixture.relation_version_id}/literature-relations",
        params={"status": "accepted", "cursor": cursor},
    )
    assert mismatched.status_code == 400
    assert mismatched.json()["code"] == "INVALID_CURSOR"


def test_literature_reads_use_problem_details_for_kind_schema_and_provenance(
    fixture: LiteratureFixture,
) -> None:
    client = _client(fixture)
    wrong_kind = client.get(
        f"/api/artifact-versions/{fixture.relation_version_id}/literature-claims"
    )
    assert wrong_kind.status_code == 409
    assert wrong_kind.json()["code"] == "ARTIFACT_KIND_MISMATCH"

    original = fixture.artifacts.versions[fixture.relation_version_id]
    content = dict(original.content)
    relations = [dict(item) for item in content["relations"]]
    relations[0]["status"] = "unknown"
    content["relations"] = relations
    fixture.artifacts.versions[fixture.relation_version_id] = original.model_copy(
        update={
            "content": content,
            "content_hash": compute_canonical_payload_hash(content),
        }
    )
    try:
        invalid = client.get(
            f"/api/artifact-versions/{fixture.relation_version_id}/literature-relations"
        )
        assert invalid.status_code == 422
        assert invalid.json()["code"] == "LITERATURE_RELATIONS_SCHEMA_INVALID"
    finally:
        fixture.artifacts.versions[fixture.relation_version_id] = original

    fixture.artifacts.versions[fixture.relation_version_id] = original.model_copy(
        update={"evidence": (), "evidence_ids": ()}
    )
    try:
        incomplete = client.get(
            f"/api/artifact-versions/{fixture.relation_version_id}/literature-relations"
        )
        assert incomplete.status_code == 403
        assert incomplete.json()["code"] == "PROVENANCE_SCOPE_VIOLATION"
    finally:
        fixture.artifacts.versions[fixture.relation_version_id] = original


def test_relation_snapshot_registry_rejects_conflicting_pipeline_identity(
    fixture: LiteratureFixture,
) -> None:
    original = fixture.artifacts.versions[fixture.relation_version_id]
    candidate = LiteratureRelationsCandidate.model_validate(original.content)
    first, second = candidate.evidence
    conflicting = candidate.model_copy(
        update={
            "evidence": (
                first.model_copy(
                    update={"source_snapshot_id": second.source_snapshot_id}
                ),
                second,
            )
        }
    )

    with pytest.raises(SecurityProblem) as exc_info:
        _relation_snapshot_references(conflicting)

    assert exc_info.value.status == 403
    assert exc_info.value.code == "PROVENANCE_SCOPE_VIOLATION"


def test_literature_reads_require_session_and_hide_other_projects(
    fixture: LiteratureFixture,
) -> None:
    app = create_app()
    app.state.artifact_read_service = fixture.artifacts  # type: ignore[assignment]
    path = f"/api/artifact-versions/{fixture.relation_version_id}/literature-relations"
    assert TestClient(app).get(path).status_code == 401

    response = _client(fixture, owner=False).get(path)
    assert response.status_code == 404
    assert response.json()["code"] == "ARTIFACT_VERSION_NOT_FOUND"


def test_unknown_literature_objects_return_non_disclosing_404(
    fixture: LiteratureFixture,
) -> None:
    client = _client(fixture)
    claim = client.get(
        f"/api/artifact-versions/{fixture.claim_version_ids[0]}"
        "/literature-claims/missing"
    )
    relation = client.get(
        f"/api/artifact-versions/{fixture.relation_version_id}"
        "/literature-relations/missing"
    )
    trace = client.get(
        f"/api/artifact-versions/{fixture.relation_version_id}/reasoning-traces/missing"
    )
    assert (claim.status_code, claim.json()["code"]) == (
        404,
        "LITERATURE_CLAIM_NOT_FOUND",
    )
    assert (relation.status_code, relation.json()["code"]) == (
        404,
        "LITERATURE_RELATION_NOT_FOUND",
    )
    assert (trace.status_code, trace.json()["code"]) == (
        404,
        "REASONING_TRACE_NOT_FOUND",
    )
