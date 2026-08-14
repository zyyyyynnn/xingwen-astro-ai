"""Restart-safe Session, WorkspaceSnapshot, and ShareSnapshot PostgreSQL tests."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
import pytest
from pydantic import SecretStr
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import (
    ResearchProjectModel,
    ResearchSessionModel,
    ShareSnapshotModel,
)
from app.db.session import create_engine_from_url, session_factory
from app.main import create_app
from app.schemas.core import (
    CreateShareSnapshotRequest,
    PublicArtifactVersion,
    PublicEvidence,
    WorkspaceSnapshotInput,
)
from app.security import PersistentSessionStore, SecurityProblem, SessionService
from app.services.resource_authority import InMemoryResourceAuthority
from app.services.snapshots import PersistentSnapshotStore, SnapshotService


API_ROOT = Path(__file__).parents[1]
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
NOW = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)


@pytest.fixture()
def database() -> Iterator[tuple[Engine, Callable[[], Session]]]:
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL is not configured")
    if "test" not in TEST_DATABASE_URL.lower():
        pytest.fail("TEST_DATABASE_URL must identify an isolated test database")
    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(API_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    engine = create_engine_from_url(TEST_DATABASE_URL)
    factory = session_factory(engine)
    try:
        yield engine, factory
    finally:
        engine.dispose()
        command.downgrade(config, "base")
        command.upgrade(config, "head")


def _project(factory: Callable[[], Session], *, session_id: str) -> str:
    project_id = uuid4()
    with factory() as session, session.begin():
        session.add(
            ResearchProjectModel(
                id=project_id,
                session_id=session_id,
                name="Restart-safe snapshots",
                description="",
                case_key="exoplanet_host_star",
                active_draft_id=None,
                revision=1,
                idempotency_key=f"project-{uuid4().hex}",
                request_hash="sha256:" + "1" * 64,
                created_at=NOW,
                updated_at=NOW,
            )
        )
    return str(project_id)


def _authority(
    *, session_id: str, project_id: str
) -> tuple[InMemoryResourceAuthority, PublicArtifactVersion, PublicEvidence]:
    authority = InMemoryResourceAuthority()
    authority.register_project(project_id=project_id, owner_session_id=session_id)
    version = PublicArtifactVersion(
        id=str(uuid4()),
        artifact_id=str(uuid4()),
        kind="dataset",
        title="Frozen dataset",
        version_number=1,
        schema_version="2.0.0",
        content_hash="sha256:" + "a" * 64,
        source_mode="live",
        created_at=NOW,
    )
    evidence = PublicEvidence(
        id=str(uuid4()),
        artifact_version_id=version.id,
        source_snapshot_id=str(uuid4()),
    )
    authority.register_artifact_version(project_id=project_id, projection=version)
    authority.register_evidence(project_id=project_id, projection=evidence)
    return authority, version, evidence


def _share_request(
    version: PublicArtifactVersion,
    evidence: PublicEvidence,
    *,
    expires_at: datetime,
) -> CreateShareSnapshotRequest:
    return CreateShareSnapshotRequest(
        title="Restart-safe public share",
        artifact_version_ids=(version.id,),
        evidence_ids=(evidence.id,),
        redaction_policy="public_metadata_only",
        expires_at=expires_at,
    )


def test_restart_recovers_session_workspace_and_frozen_share(
    database: tuple[Engine, Callable[[], Session]],
) -> None:
    _engine, factory = database
    first_sessions = SessionService(PersistentSessionStore(factory), ttl_seconds=3600)
    owner, credential, csrf = first_sessions.create(now=NOW)
    project_id = _project(factory, session_id=owner.id)
    authority, version, evidence = _authority(
        session_id=owner.id, project_id=project_id
    )
    first_snapshots = SnapshotService(PersistentSnapshotStore(factory, authority))

    workspace = first_snapshots.save_workspace(
        project_id=project_id,
        session_id=owner.id,
        expected_revision=0,
        payload=WorkspaceSnapshotInput(layout_preset="research-default"),
        now=NOW,
    )
    created_share = first_snapshots.create_share(
        project_id=project_id,
        session_id=owner.id,
        request=_share_request(
            version, evidence, expires_at=NOW + timedelta(hours=1)
        ),
        now=NOW,
    )

    # New service/store objects simulate another process after restart. Public
    # resolution intentionally has no in-memory Artifact/Evidence authority.
    restarted_sessions = SessionService(
        PersistentSessionStore(factory), ttl_seconds=3600
    )
    restarted_snapshots = SnapshotService(
        PersistentSnapshotStore(factory, InMemoryResourceAuthority())
    )
    recovered = restarted_sessions.authenticate(credential, now=NOW)
    restarted_sessions.verify_csrf(recovered, csrf)
    resumed = restarted_sessions.resume(credential, now=NOW + timedelta(seconds=1))
    assert resumed is not None
    assert resumed[0].id == owner.id
    assert resumed[0].security_version == owner.security_version + 1
    restarted_sessions.verify_csrf(resumed[0], csrf)
    restarted_sessions.verify_csrf(resumed[0], resumed[1])

    restored_workspace = restarted_snapshots.get_workspace(
        project_id=project_id, session_id=owner.id
    )
    assert restored_workspace == workspace
    public = restarted_snapshots.get_public_share(
        raw_token=created_share.share_token, now=NOW + timedelta(seconds=2)
    )
    assert public.artifact_versions == (version,)
    assert public.evidence == (evidence,)

    # Mutating the old authority cannot alter the frozen public projection.
    authority.register_artifact_version(
        project_id=project_id,
        projection=version.model_copy(update={"title": "Changed authority title"}),
    )
    assert restarted_snapshots.get_public_share(
        raw_token=created_share.share_token, now=NOW + timedelta(seconds=3)
    ).artifact_versions == (version,)

    with factory() as session:
        row = session.get(ShareSnapshotModel, created_share.id)
        assert row is not None
        assert row.token_hash == hashlib.sha256(
            created_share.share_token.encode("utf-8")
        ).hexdigest()
        assert created_share.share_token not in repr(row.artifact_versions)
        assert created_share.share_token not in repr(row.evidence)


def test_two_api_instances_share_session_and_workspace_runtime(
    database: tuple[Engine, Callable[[], Session]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _engine, factory = database
    assert TEST_DATABASE_URL is not None
    monkeypatch.setattr(settings, "DATABASE_URL", SecretStr(TEST_DATABASE_URL))
    first_app = create_app()
    with TestClient(first_app) as first_client:
        created = first_client.post("/api/sessions")
        assert created.status_code == 201
        first_csrf = created.json()["data"]["csrf_token"]
        credential = first_client.cookies.get(settings.SESSION_COOKIE_NAME)
        assert credential is not None
        owner = first_app.state.session_service.authenticate(credential)
        project_id = _project(factory, session_id=owner.id)
        saved = first_client.put(
            f"/api/projects/{project_id}/workspace-snapshot",
            json={"layout_preset": "restart-http"},
            headers={"If-Match": "0", "X-CSRF-Token": first_csrf},
        )
        assert saved.status_code == 200

        second_app = create_app()
        with TestClient(second_app) as second_client:
            second_client.cookies.set(
                settings.SESSION_COOKIE_NAME, credential, path="/api"
            )
            resumed = second_client.post("/api/sessions")
            assert resumed.status_code == 201
            second_csrf = resumed.json()["data"]["csrf_token"]
            restored = second_client.get(
                f"/api/projects/{project_id}/workspace-snapshot"
            )
            assert restored.status_code == 200
            assert restored.json()["data"]["layout_preset"] == "restart-http"
            revoked = second_client.delete(
                "/api/sessions/current", headers={"X-CSRF-Token": second_csrf}
            )
            assert revoked.status_code == 204

        assert first_client.get("/api/sessions/current").status_code == 401


def test_multi_instance_rotation_and_workspace_update_are_serialized(
    database: tuple[Engine, Callable[[], Session]],
) -> None:
    _engine, factory = database
    creator = SessionService(PersistentSessionStore(factory), ttl_seconds=3600)
    owner, credential, _csrf = creator.create(now=NOW)
    project_id = _project(factory, session_id=owner.id)
    authority, _version, _evidence = _authority(
        session_id=owner.id, project_id=project_id
    )
    first_session_service = SessionService(
        PersistentSessionStore(factory), ttl_seconds=3600
    )
    second_session_service = SessionService(
        PersistentSessionStore(factory), ttl_seconds=3600
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        rotations = tuple(
            executor.map(
                lambda service: service.resume(
                    credential, now=NOW + timedelta(seconds=1)
                ),
                (first_session_service, second_session_service),
            )
        )
    assert all(item is not None for item in rotations)
    current = creator.authenticate(credential, now=NOW + timedelta(seconds=2))
    assert current.security_version == 3
    for rotation in rotations:
        assert rotation is not None
        creator.verify_csrf(current, rotation[1])

    first_snapshots = SnapshotService(PersistentSnapshotStore(factory, authority))
    second_snapshots = SnapshotService(PersistentSnapshotStore(factory, authority))
    first_snapshots.save_workspace(
        project_id=project_id,
        session_id=owner.id,
        expected_revision=0,
        payload=WorkspaceSnapshotInput(layout_preset="initial"),
        now=NOW,
    )

    def update(service: SnapshotService, preset: str) -> object:
        try:
            return service.save_workspace(
                project_id=project_id,
                session_id=owner.id,
                expected_revision=1,
                payload=WorkspaceSnapshotInput(layout_preset=preset),
                now=NOW + timedelta(seconds=3),
            )
        except SecurityProblem as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = tuple(
            executor.map(
                lambda item: update(*item),
                ((first_snapshots, "left"), (second_snapshots, "right")),
            )
        )
    successes = [item for item in outcomes if not isinstance(item, SecurityProblem)]
    conflicts = [item for item in outcomes if isinstance(item, SecurityProblem)]
    assert len(successes) == 1
    assert len(conflicts) == 1
    assert conflicts[0].code == "VERSION_CONFLICT"
    assert first_snapshots.get_workspace(
        project_id=project_id, session_id=owner.id
    ).revision == 2


def test_revocation_expiry_and_retention_are_fail_closed(
    database: tuple[Engine, Callable[[], Session]],
) -> None:
    _engine, factory = database
    sessions = PersistentSessionStore(factory)
    service = SessionService(sessions, ttl_seconds=3600)
    owner, credential, _csrf = service.create(now=NOW)
    project_id = _project(factory, session_id=owner.id)
    authority, version, evidence = _authority(
        session_id=owner.id, project_id=project_id
    )
    snapshots = PersistentSnapshotStore(factory, authority)
    share = snapshots.create_share(
        project_id=project_id,
        session_id=owner.id,
        request=_share_request(
            version, evidence, expires_at=NOW + timedelta(seconds=1)
        ),
        now=NOW,
    )
    with pytest.raises(SecurityProblem) as expired:
        snapshots.resolve_public_share(
            raw_token=share.share_token, now=NOW + timedelta(seconds=2)
        )
    assert expired.value.code == "SHARE_NOT_FOUND"

    active_share = snapshots.create_share(
        project_id=project_id,
        session_id=owner.id,
        request=_share_request(
            version, evidence, expires_at=NOW + timedelta(hours=1)
        ),
        now=NOW,
    )
    snapshots.revoke_share(
        project_id=project_id,
        share_id=active_share.id,
        session_id=owner.id,
        now=NOW + timedelta(seconds=3),
    )
    with pytest.raises(SecurityProblem) as revoked_share:
        snapshots.resolve_public_share(
            raw_token=active_share.share_token, now=NOW + timedelta(seconds=4)
        )
    assert revoked_share.value.code == "SHARE_NOT_FOUND"

    old_service = SessionService(PersistentSessionStore(factory), ttl_seconds=1)
    old, _old_credential, _old_csrf = old_service.create(
        now=NOW - timedelta(minutes=10)
    )
    service.revoke(credential, now=NOW + timedelta(seconds=5))
    with pytest.raises(SecurityProblem) as revoked_session:
        service.authenticate(credential, now=NOW + timedelta(seconds=6))
    assert revoked_session.value.code == "SESSION_REQUIRED"

    assert sessions.cleanup(now=NOW, retention=timedelta(minutes=1)) == 1
    assert snapshots.cleanup(
        now=NOW + timedelta(hours=2), retention=timedelta(minutes=1)
    ) == 2
    with factory() as session:
        # The unreferenced expired Session is gone. The revoked owner identity
        # remains because Project ownership history still references it.
        assert session.get(ResearchSessionModel, old.id) is None
        assert session.get(ResearchSessionModel, owner.id) is not None
        assert tuple(session.scalars(select(ShareSnapshotModel))) == ()


def test_cleanup_failure_rolls_back_session_and_share_creation(
    database: tuple[Engine, Callable[[], Session]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _engine, factory = database

    def fail_cleanup(*_args: object, **_kwargs: object) -> int:
        raise RuntimeError("cleanup failed")

    with monkeypatch.context() as patch:
        patch.setattr(
            PersistentSessionStore, "_cleanup", staticmethod(fail_cleanup)
        )
        sessions = SessionService(
            PersistentSessionStore(factory, retention=timedelta()),
            ttl_seconds=3600,
        )
        with pytest.raises(RuntimeError, match="cleanup failed"):
            sessions.create(now=NOW)

    with factory() as session:
        assert tuple(session.scalars(select(ResearchSessionModel))) == ()

    owner, _credential, _csrf = SessionService(
        PersistentSessionStore(factory), ttl_seconds=3600
    ).create(now=NOW)
    project_id = _project(factory, session_id=owner.id)
    authority, version, evidence = _authority(
        session_id=owner.id, project_id=project_id
    )
    snapshots = PersistentSnapshotStore(
        factory, authority, retention=timedelta()
    )
    with monkeypatch.context() as patch:
        patch.setattr(
            PersistentSnapshotStore, "_cleanup", staticmethod(fail_cleanup)
        )
        with pytest.raises(RuntimeError, match="cleanup failed"):
            snapshots.create_share(
                project_id=project_id,
                session_id=owner.id,
                request=_share_request(
                    version, evidence, expires_at=NOW + timedelta(hours=1)
                ),
                now=NOW,
            )

    with factory() as session:
        assert tuple(session.scalars(select(ShareSnapshotModel))) == ()
