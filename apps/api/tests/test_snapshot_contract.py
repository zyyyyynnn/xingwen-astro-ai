"""Contract, security, and concurrency tests for snapshots and shares."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from threading import Barrier

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import settings
from app.main import create_app
from app.schemas.core import (
    CreateShareSnapshotRequest,
    PublicArtifactVersion,
    PublicEvidence,
    PublicPresentationEntry,
    WorkspaceSnapshotInput,
)
from app.security import SecurityProblem
from app.services.snapshots import InMemorySnapshotStore, SnapshotService


NOW = datetime(2026, 7, 22, 8, tzinfo=UTC)
HASH = "sha256:" + "a" * 64


def _version(*, title: str = "Frozen dataset") -> PublicArtifactVersion:
    return PublicArtifactVersion(
        id="artv_01",
        artifact_id="art_01",
        kind="dataset",
        title=title,
        version_number=1,
        schema_version="2.0.0",
        content_hash=HASH,
        source_mode="live",
        created_at=NOW,
        presentation={
            "kind": "dataset",
            "facts": [{"label": "记录", "values": ("1 条",)}],
        },
        evidence_ids=("ev_01",),
    )


def _evidence() -> PublicEvidence:
    return PublicEvidence(
        id="ev_01",
        artifact_version_id="artv_01",
        source_snapshot_id="srcs_01",
        locator={"kind": "database_cell", "field": "host_name"},
        quote_or_value="TOI-700",
        created_at=NOW,
        source={
            "source_id": "gaia",
            "source_type": "database",
            "retrieved_at": NOW,
            "license_note": "Gaia archive terms",
            "request_metadata": {},
        },
    )


def _workspace_payload(*, layout_preset: str = "research-default") -> dict[str, object]:
    return {
        "active_run_id": "run_01",
        "panel_slots": [
            {
                "slot_id": "primary",
                "panel_type": "atlas",
                "artifact_version_id": "artv_01",
            }
        ],
        "selected_object_ref": {
            "object_type": "exoplanet_candidate",
            "object_id": "TOI-700 d",
            "artifact_version_id": "artv_01",
        },
        "pinned_evidence_ids": ["ev_01"],
        "atlas_state": {"focus_mode": "candidate"},
        "observatory_state": {
            "active_artifact_version_id": "artv_01",
            "active_evidence_id": "ev_01",
        },
        "layout_preset": layout_preset,
    }


def test_public_artifact_contract_rejects_raw_content_and_unknown_fields() -> None:
    payload = _version().model_dump(mode="json")
    payload["content"] = {"producer": {"model": "private"}}

    with pytest.raises(ValidationError):
        PublicArtifactVersion.model_validate(payload)


def test_public_evidence_preserves_document_verification_locator() -> None:
    payload = _evidence().model_dump()
    payload["locator"] = {
        "kind": "paper_text",
        "page": 2,
        "block_id": "paragraph-4",
        "table_id": "table-1",
        "cell_id": "r2c3",
        "bbox": {"x1": 10, "y1": 20, "x2": 30, "y2": 40},
    }
    projected = PublicEvidence.model_validate(payload)

    assert projected.locator.page == 2
    assert projected.locator.block_id == "paragraph-4"
    assert projected.locator.table_id == "table-1"
    assert projected.locator.cell_id == "r2c3"
    assert projected.locator.bbox is not None


def _session_client() -> tuple[FastAPI, TestClient, str, str]:
    app = create_app()
    store = InMemorySnapshotStore()
    app.state.snapshot_store = store
    app.state.snapshot_service = SnapshotService(store)
    client = TestClient(app, base_url="https://testserver")
    created = client.post("/api/sessions")
    assert created.status_code == 201
    csrf_token = created.json()["data"]["csrf_token"]
    credential = client.cookies.get(settings.SESSION_COOKIE_NAME)
    assert credential is not None
    session_id = app.state.session_service.authenticate(credential).id
    return app, client, session_id, csrf_token


def test_snapshot_runtime_reports_unavailable_without_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Isolate from host DATABASE_URL / Compose credentials so the assertion
    # always exercises the no-authority path rather than a live PG lookup.
    monkeypatch.setattr(settings, "DATABASE_URL", None)
    app = create_app()
    client = TestClient(app, base_url="https://testserver")
    created = client.post("/api/sessions")
    assert created.status_code == 201

    response = client.get("/api/projects/proj_unknown/workspace-snapshot")

    assert response.status_code == 503
    assert response.json()["code"] == "SNAPSHOT_RUNTIME_UNAVAILABLE"


def _seed_project(
    app: FastAPI, session_id: str, *, project_id: str = "proj_01"
) -> None:
    store: InMemorySnapshotStore = app.state.snapshot_store
    store.register_project(project_id=project_id, owner_session_id=session_id)
    store.register_run(run_id="run_01", project_id=project_id)
    store.register_artifact_version(project_id=project_id, projection=_version())
    store.register_evidence(project_id=project_id, projection=_evidence())


def test_workspace_schema_is_bounded_and_rejects_duplicate_slots() -> None:
    payload = _workspace_payload()
    WorkspaceSnapshotInput.model_validate(payload)
    four_slots = [
        {"slot_id": f"slot-{index}", "panel_type": "atlas"} for index in range(4)
    ]
    with pytest.raises(ValidationError, match="too_long"):
        WorkspaceSnapshotInput.model_validate({**payload, "panel_slots": four_slots})
    duplicate_slots = [
        {"slot_id": "primary", "panel_type": "atlas"},
        {"slot_id": "primary", "panel_type": "observatory"},
    ]
    with pytest.raises(ValidationError, match="unique slot_id"):
        WorkspaceSnapshotInput.model_validate(
            {**payload, "panel_slots": duplicate_slots}
        )
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        WorkspaceSnapshotInput.model_validate({**payload, "session_token": "secret"})


def test_workspace_put_is_idempotent_and_uses_revision_conflicts() -> None:
    app, client, session_id, csrf_token = _session_client()
    _seed_project(app, session_id)
    headers = {"X-CSRF-Token": csrf_token, "If-Match": "0"}

    first = client.put(
        "/api/projects/proj_01/workspace-snapshot",
        headers=headers,
        json=_workspace_payload(),
    )
    assert first.status_code == 200
    assert first.json()["data"]["revision"] == 1
    assert first.headers["etag"] == "1"
    assert first.headers["cache-control"] == "no-store"
    assert "session_id" not in first.json()["data"]

    replay = client.put(
        "/api/projects/proj_01/workspace-snapshot",
        headers=headers,
        json=_workspace_payload(),
    )
    assert replay.status_code == 200
    assert replay.json()["data"] == first.json()["data"]

    conflict = client.put(
        "/api/projects/proj_01/workspace-snapshot",
        headers=headers,
        json=_workspace_payload(layout_preset="observatory-focus"),
    )
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "VERSION_CONFLICT"
    assert conflict.json()["request_id"]

    updated = client.put(
        "/api/projects/proj_01/workspace-snapshot",
        headers={"X-CSRF-Token": csrf_token, "If-Match": "1"},
        json=_workspace_payload(layout_preset="observatory-focus"),
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["revision"] == 2
    restored = client.get("/api/projects/proj_01/workspace-snapshot")
    assert restored.json()["data"] == updated.json()["data"]


def test_workspace_concurrent_overwrite_allows_one_revision_winner() -> None:
    store = InMemorySnapshotStore()
    store.register_project(project_id="proj_01", owner_session_id="sess_01")
    service = SnapshotService(store)
    initial = WorkspaceSnapshotInput(layout_preset="initial")
    service.save_workspace(
        project_id="proj_01",
        session_id="sess_01",
        expected_revision=0,
        payload=initial,
        now=NOW,
    )
    barrier = Barrier(2)

    def overwrite(layout: str) -> int:
        barrier.wait()
        try:
            service.save_workspace(
                project_id="proj_01",
                session_id="sess_01",
                expected_revision=1,
                payload=WorkspaceSnapshotInput(layout_preset=layout),
                now=NOW + timedelta(seconds=1),
            )
        except SecurityProblem as exc:
            return exc.status
        return 200

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = sorted(executor.map(overwrite, ("atlas-focus", "observatory-focus")))
    assert outcomes == [200, 409]


def test_cross_session_private_resources_are_hidden() -> None:
    app, owner_client, session_id, _ = _session_client()
    _seed_project(app, session_id)
    other = TestClient(app, base_url="https://testserver")
    assert other.post("/api/sessions").status_code == 201
    hidden = other.get("/api/projects/proj_01/workspace-snapshot")
    assert hidden.status_code == 404
    assert hidden.json()["code"] == "PROJECT_NOT_FOUND"
    assert "proj_01" not in hidden.json()["detail"]
    assert (
        owner_client.get("/api/projects/missing/workspace-snapshot").status_code == 404
    )


def test_share_freezes_redacted_scope_and_never_lists_token_material() -> None:
    app, client, session_id, csrf_token = _session_client()
    _seed_project(app, session_id)
    app.state.snapshot_store.register_artifact_version(
        project_id="proj_01",
        projection=_version().model_copy(update={"evidence_ids": ("ev_01", "ev_02")}),
    )
    app.state.snapshot_store.register_evidence(
        project_id="proj_01",
        projection=_evidence().model_copy(
            update={"id": "ev_02", "quote_or_value": "not selected"}
        ),
    )
    expires_at = datetime.now(UTC) + timedelta(hours=1)
    payload = {
        "title": "Public dataset evidence",
        "artifact_version_ids": ["artv_01"],
        "evidence_ids": ["ev_01"],
        "redaction_policy": "redacted_public_snapshot",
        "expires_at": expires_at.isoformat(),
    }
    missing_csrf = client.post("/api/projects/proj_01/shares", json=payload)
    assert missing_csrf.status_code == 403
    assert missing_csrf.json()["code"] == "CSRF_INVALID"

    created = client.post(
        "/api/projects/proj_01/shares",
        headers={"X-CSRF-Token": csrf_token},
        json=payload,
    )
    assert created.status_code == 201
    data = created.json()["data"]
    assert created.headers["location"] == (f"/api/projects/proj_01/shares/{data['id']}")
    assert created.headers["ratelimit-limit"] == str(settings.SHARE_CREATE_RATE_LIMIT)
    assert int(created.headers["ratelimit-remaining"]) == (
        settings.SHARE_CREATE_RATE_LIMIT - 1
    )
    assert int(created.headers["ratelimit-reset"]) >= 0
    raw_token = data["share_token"]
    assert len(raw_token) >= 32
    token_hash = app.state.snapshot_store.token_hash_for_testing(data["id"])
    assert token_hash != raw_token
    assert len(token_hash) == 64
    assert raw_token not in repr(app.state.snapshot_store.__dict__)

    listed = client.get("/api/projects/proj_01/shares")
    assert listed.status_code == 200
    listed_wire = listed.text
    assert raw_token not in listed_wire
    assert token_hash not in listed_wire
    assert "share_token" not in listed.json()["data"][0]
    assert "token_hash" not in listed.json()["data"][0]

    app.state.snapshot_store.register_artifact_version(
        project_id="proj_01",
        projection=_version(title="Changed catalog title"),
    )
    anonymous = TestClient(app, base_url="https://testserver")
    public = anonymous.get(f"/api/public/shares/{raw_token}")
    assert public.status_code == 200
    public_data = public.json()["data"]
    assert public_data["artifact_versions"][0]["title"] == "Frozen dataset"
    assert public_data["artifact_versions"][0]["presentation"] == {
        "kind": "dataset",
        "summary": None,
        "facts": [{"label": "记录", "values": ["1 条"]}],
        "sections": [],
        "entries": [],
        "tables": [],
        "graph_nodes": [],
        "graph_edges": [],
    }
    assert "content" not in public_data["artifact_versions"][0]
    assert public_data["artifact_versions"][0]["evidence_ids"] == ["ev_01"]
    assert [item["id"] for item in public_data["evidence"]] == ["ev_01"]
    assert "ev_02" not in public.text
    assert public_data["evidence"][0]["quote_or_value"] == "TOI-700"
    assert public_data["evidence"][0]["source"]["source_id"] == "gaia"
    assert "project_id" not in public_data
    assert "session_id" not in public.text
    assert raw_token not in public.text
    assert public.headers["cache-control"] == "no-store"
    assert public.headers["referrer-policy"] == "no-referrer"
    assert "default-src 'none'" in public.headers["content-security-policy"]
    assert public.headers["x-content-type-options"] == "nosniff"

    revoked = client.delete(
        f"/api/projects/proj_01/shares/{data['id']}",
        headers={"X-CSRF-Token": csrf_token},
    )
    assert revoked.status_code == 204
    assert revoked.content == b""
    assert "content-type" not in revoked.headers
    after_revoke = anonymous.get(f"/api/public/shares/{raw_token}")
    invalid = anonymous.get("/api/public/shares/not-a-real-token")
    assert after_revoke.status_code == invalid.status_code == 404
    assert after_revoke.json()["code"] == invalid.json()["code"] == "SHARE_NOT_FOUND"
    assert after_revoke.json()["detail"] == invalid.json()["detail"]
    assert after_revoke.json()["instance"] == "/api/public/shares/public"
    assert raw_token not in after_revoke.text
    assert after_revoke.headers["referrer-policy"] == "no-referrer"
    assert "default-src 'none'" in after_revoke.headers["content-security-policy"]


def test_share_create_has_an_independent_per_session_rate_limit() -> None:
    app, client, session_id, csrf_token = _session_client()
    _seed_project(app, session_id)
    app.state.share_rate_limiter.limit = 1
    payload = {
        "title": "Rate-limited share",
        "artifact_version_ids": ["artv_01"],
        "redaction_policy": "redacted_public_snapshot",
        "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
    }

    first = client.post(
        "/api/projects/proj_01/shares",
        headers={"X-CSRF-Token": csrf_token},
        json=payload,
    )
    assert first.status_code == 201
    assert first.headers["ratelimit-limit"] == "1"
    assert first.headers["ratelimit-remaining"] == "0"

    limited = client.post(
        "/api/projects/proj_01/shares",
        headers={"X-CSRF-Token": csrf_token},
        json=payload,
    )
    assert limited.status_code == 429
    assert limited.json()["code"] == "RATE_LIMITED"
    assert limited.json()["request_id"]
    assert limited.headers["ratelimit-limit"] == "1"
    assert limited.headers["ratelimit-remaining"] == "0"
    assert int(limited.headers["ratelimit-reset"]) >= 1
    assert limited.headers["retry-after"] == limited.headers["ratelimit-reset"]


def test_share_rejects_cross_project_versions_and_unselected_evidence() -> None:
    store = InMemorySnapshotStore()
    store.register_project(project_id="proj_01", owner_session_id="sess_01")
    store.register_project(project_id="proj_02", owner_session_id="sess_01")
    store.register_artifact_version(project_id="proj_02", projection=_version())
    store.register_evidence(project_id="proj_01", projection=_evidence())
    service = SnapshotService(store)

    request = CreateShareSnapshotRequest(
        title="Invalid scope",
        artifact_version_ids=("artv_01",),
        evidence_ids=(),
        redaction_policy="redacted_public_snapshot",
        expires_at=NOW + timedelta(hours=1),
    )
    with pytest.raises(SecurityProblem) as cross_project:
        service.create_share(
            project_id="proj_01",
            session_id="sess_01",
            request=request,
            now=NOW,
        )
    assert cross_project.value.status == 404
    assert cross_project.value.code == "ARTIFACT_VERSION_NOT_FOUND"

    store.register_artifact_version(project_id="proj_01", projection=_version())
    unrelated = PublicEvidence(
        id="ev_02",
        artifact_version_id="artv_other",
        source_snapshot_id="srcs_02",
        locator={"kind": "database_cell", "field": "host_name"},
        quote_or_value="unrelated",
        created_at=NOW,
        source={
            "source_id": "gaia",
            "source_type": "database",
            "retrieved_at": NOW,
            "license_note": "Gaia archive terms",
            "request_metadata": {},
        },
    )
    store.register_evidence(project_id="proj_01", projection=unrelated)
    with pytest.raises(SecurityProblem) as invalid_scope:
        service.create_share(
            project_id="proj_01",
            session_id="sess_01",
            request=request.model_copy(update={"evidence_ids": ("ev_02",)}),
            now=NOW,
        )
    assert invalid_scope.value.status == 422
    assert invalid_scope.value.code == "SHARE_SCOPE_INVALID"


def test_share_requires_and_revalidates_presentation_evidence_closure() -> None:
    store = InMemorySnapshotStore()
    store.register_project(project_id="proj_01", owner_session_id="sess_01")
    version = _version()
    version = version.model_copy(
        update={
            "presentation": version.presentation.model_copy(
                update={
                    "entries": (
                        PublicPresentationEntry(
                            key="finding.1",
                            title="可核验结论",
                            evidence_ids=("ev_01",),
                        ),
                    )
                }
            )
        }
    )
    store.register_artifact_version(project_id="proj_01", projection=version)
    store.register_evidence(project_id="proj_01", projection=_evidence())
    service = SnapshotService(store)
    request = CreateShareSnapshotRequest(
        title="Evidence closure",
        artifact_version_ids=(version.id,),
        evidence_ids=(),
        redaction_policy="redacted_public_snapshot",
        expires_at=NOW + timedelta(hours=1),
    )

    with pytest.raises(SecurityProblem) as missing:
        service.create_share(
            project_id="proj_01",
            session_id="sess_01",
            request=request,
            now=NOW,
        )
    assert missing.value.code == "SHARE_SCOPE_INVALID"

    created = service.create_share(
        project_id="proj_01",
        session_id="sess_01",
        request=request.model_copy(update={"evidence_ids": ("ev_01",)}),
        now=NOW,
    )
    record = store._shares[created.id]
    store._shares[created.id] = replace(
        record,
        artifact_versions=(
            record.artifact_versions[0].model_copy(
                update={"evidence_ids": ("ev_01", "ev_02")}
            ),
        ),
    )
    with pytest.raises(SecurityProblem) as overdeclared:
        service.get_public_share(raw_token=created.share_token, now=NOW)
    assert overdeclared.value.status == 404
    assert overdeclared.value.code == "SHARE_NOT_FOUND"

    store._shares[created.id] = replace(record, evidence=())
    with pytest.raises(SecurityProblem) as corrupted:
        service.get_public_share(raw_token=created.share_token, now=NOW)
    assert corrupted.value.status == 404
    assert corrupted.value.code == "SHARE_NOT_FOUND"


def test_expired_and_invalid_share_tokens_have_identical_public_errors() -> None:
    store = InMemorySnapshotStore()
    store.register_project(project_id="proj_01", owner_session_id="sess_01")
    store.register_artifact_version(project_id="proj_01", projection=_version())
    service = SnapshotService(store)
    created = service.create_share(
        project_id="proj_01",
        session_id="sess_01",
        request=CreateShareSnapshotRequest(
            title="Expiring share",
            artifact_version_ids=("artv_01",),
            redaction_policy="redacted_public_snapshot",
            expires_at=NOW + timedelta(seconds=1),
        ),
        now=NOW,
    )
    failures: list[SecurityProblem] = []
    for token in (created.share_token, "invalid-token"):
        with pytest.raises(SecurityProblem) as failure:
            service.get_public_share(raw_token=token, now=NOW + timedelta(seconds=2))
        failures.append(failure.value)
    assert [(item.status, item.code, item.detail) for item in failures] == [
        (404, "SHARE_NOT_FOUND", "Resource not found"),
        (404, "SHARE_NOT_FOUND", "Resource not found"),
    ]


def test_private_share_cursor_is_stable_and_invalid_cursor_is_rejected() -> None:
    store = InMemorySnapshotStore()
    store.register_project(project_id="proj_01", owner_session_id="sess_01")
    store.register_artifact_version(project_id="proj_01", projection=_version())
    service = SnapshotService(store)
    request = CreateShareSnapshotRequest(
        title="Share",
        artifact_version_ids=("artv_01",),
        redaction_policy="redacted_public_snapshot",
        expires_at=NOW + timedelta(hours=1),
    )
    service.create_share(
        project_id="proj_01", session_id="sess_01", request=request, now=NOW
    )
    service.create_share(
        project_id="proj_01",
        session_id="sess_01",
        request=request,
        now=NOW + timedelta(seconds=1),
    )
    first, cursor, has_more = service.list_shares(
        project_id="proj_01",
        session_id="sess_01",
        cursor=None,
        limit=1,
        now=NOW,
    )
    second, final_cursor, final_has_more = service.list_shares(
        project_id="proj_01",
        session_id="sess_01",
        cursor=cursor,
        limit=1,
        now=NOW,
    )
    assert len(first) == len(second) == 1
    assert first[0].id != second[0].id
    assert cursor is not None and has_more is True
    assert final_cursor is None and final_has_more is False
    with pytest.raises(SecurityProblem) as invalid:
        service.list_shares(
            project_id="proj_01",
            session_id="sess_01",
            cursor="not-a-cursor",
            limit=1,
            now=NOW,
        )
    assert invalid.value.code == "INVALID_CURSOR"
