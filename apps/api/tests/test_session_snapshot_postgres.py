"""Restart-safe Session, WorkspaceSnapshot, and ShareSnapshot PostgreSQL tests."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
import pytest

from db_bootstrap import reset_current_schema
from pydantic import SecretStr
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import (
    ArtifactVersionModel,
    EvidenceModel,
    ProducerExecutionModel,
    ResearchArtifactModel,
    ResearchProjectModel,
    ResearchRunModel,
    ResearchSessionModel,
    RunStepModel,
    ShareSnapshotModel,
    SourceSnapshotModel,
    StepAttemptModel,
    WorkspaceSnapshotModel,
)
from app.db.session import create_engine_from_url, session_factory
from app.main import create_app
from app.schemas.core import (
    CreateShareSnapshotRequest,
    PublicArtifactVersion,
    PublicEvidence,
    WorkspaceSnapshotInput,
)
from app.schemas.data_artifacts import DatasetArtifactCandidate
from app.security import PersistentSessionStore, SecurityProblem, SessionService
from app.services.resource_authority import InMemoryResourceAuthority
from app.services.snapshots import PersistentSnapshotStore, SnapshotService
from artifact_publication_test_support import build_reference_dataset_candidate
from authoring_test_support import (
    build_contract_draft,
    build_research_contract,
    build_research_project,
    persist_authoring_models,
)


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
NOW = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)
HASH_A = "sha256:" + "a" * 64
HASH_B = "sha256:" + "b" * 64
HASH_C = "sha256:" + "c" * 64


@pytest.fixture()
def database() -> Iterator[tuple[Engine, Callable[[], Session]]]:
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL is not configured")
    if "test" not in TEST_DATABASE_URL.lower():
        pytest.fail("TEST_DATABASE_URL must identify an isolated test database")
    reset_current_schema(TEST_DATABASE_URL)
    engine = create_engine_from_url(TEST_DATABASE_URL)
    factory = session_factory(engine)
    try:
        yield engine, factory
    finally:
        engine.dispose()
    reset_current_schema(TEST_DATABASE_URL)


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


def _persistent_resource_graph(
    factory: Callable[[], Session], *, session_id: str, label: str
) -> dict[str, UUID | tuple[UUID, ...]]:
    ids = {
        key: uuid4()
        for key in (
            "project",
            "contract",
            "run",
            "step",
            "attempt",
            "producer",
            "artifact",
            "version",
            "snapshot",
            "evidence",
        )
    }
    dataset_candidate = build_reference_dataset_candidate(run_id=ids["run"])
    dataset = DatasetArtifactCandidate.model_validate(dataset_candidate.content)
    evidence_ids = tuple(
        ids["evidence"] if index == 0 else uuid4()
        for index, _item in enumerate(dataset.transformation_evidence)
    )
    ids["evidence_ids"] = evidence_ids
    with factory() as session, session.begin():
        project = build_research_project(
            project_id=ids["project"],
            session_id=session_id,
            name=f"{label} snapshot project",
            case_key="exoplanet_host_star",
            created_at=NOW,
            updated_at=NOW,
        )
        draft = build_contract_draft(project, created_at=NOW, updated_at=NOW)
        contract = build_research_contract(
            project,
            draft,
            contract_id=ids["contract"],
            content_hash=HASH_A,
            created_at=NOW,
        )
        run = ResearchRunModel(
            id=ids["run"],
            project_id=project.id,
            contract_id=contract.id,
            execution_mode="live",
            status="completed",
            progress=100,
            latest_event_sequence=0,
            revision=1,
            idempotency_key=f"{label}-run",
            request_hash=HASH_B,
            created_at=NOW,
            updated_at=NOW,
        )
        step = RunStepModel(
            id=ids["step"],
            run_id=run.id,
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
        attempt = StepAttemptModel(
            id=ids["attempt"],
            run_step_id=step.id,
            attempt_number=1,
            idempotency_key=f"{label}-attempt",
            status="completed",
            started_at=NOW,
            finished_at=NOW + timedelta(seconds=1),
            created_at=NOW,
        )
        producer = ProducerExecutionModel(
            id=ids["producer"],
            run_id=run.id,
            run_step_id=step.id,
            step_attempt_id=attempt.id,
            step_key=step.key,
            idempotency_key=f"{label}-producer",
            lease_generation=1,
            producer_type="algorithm",
            producer_name="snapshot-test-producer",
            producer_version="1.0.0",
            parameters={},
            parameters_hash=HASH_A,
            input_hash=HASH_B,
            output_hash=HASH_C,
            status="completed",
            started_at=NOW,
            finished_at=NOW + timedelta(seconds=1),
            created_at=NOW,
        )
        artifact = ResearchArtifactModel(
            id=ids["artifact"],
            project_id=project.id,
            kind="dataset",
            title=f"Frozen {label} dataset",
            logical_key=f"dataset.{label}",
            created_at=NOW,
        )
        snapshot = SourceSnapshotModel(
            id=ids["snapshot"],
            project_id=project.id,
            source_id=f"{label}-source",
            source_type="catalog",
            retrieved_at=NOW,
            query={"target": label},
            query_hash=HASH_A,
            content_hash=HASH_B,
            license_note="Public metadata only.",
            request_metadata={"method": "GET"},
        )
        version = ArtifactVersionModel(
            id=ids["version"],
            artifact_id=artifact.id,
            project_id=project.id,
            created_by_run_id=run.id,
            run_step_id=step.id,
            step_attempt_id=attempt.id,
            producer_execution_id=producer.id,
            version_number=1,
            publication_key=f"{label}-publication-1",
            schema_version="2.0.0",
            content=dataset_candidate.content,
            content_hash=HASH_C,
            input_hash=HASH_B,
            source_mode="live",
            producer={
                "type": "algorithm",
                "name": "snapshot-test-producer",
                "version": "1.0.0",
                "parameters_hash": HASH_A,
            },
            source_snapshot_ids=[str(snapshot.id)],
            evidence_ids=[str(item) for item in evidence_ids],
            created_at=NOW,
        )
        evidence = tuple(
            EvidenceModel(
                id=persisted_id,
                project_id=project.id,
                artifact_version_id=version.id,
                target_type="canonical_field",
                target_id=item.canonical_field_id,
                evidence_type="data_transformation",
                source_snapshot_id=snapshot.id,
                locator=item.locator.model_dump(mode="json"),
                quote_or_value=(
                    item.canonical_value
                    if item.canonical_value is not None
                    else item.raw_value
                ),
                extraction_method="data_artifact_admission",
                confidence=1.0,
                is_restricted=False,
                created_at=NOW,
            )
            for persisted_id, item in zip(
                evidence_ids,
                dataset.transformation_evidence,
                strict=True,
            )
        )
        persist_authoring_models(
            session, project=project, draft=draft, contract=contract
        )
        session.add(run)
        session.flush()
        session.add(step)
        session.flush()
        session.add(attempt)
        session.flush()
        session.add(producer)
        session.flush()
        session.add_all((artifact, snapshot))
        session.flush()
        session.add(version)
        session.flush()
        session.add_all(evidence)
        session.flush()
        artifact.latest_version_id = version.id
    return ids


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
        presentation={"kind": "dataset"},
        evidence_ids=(),
    )
    evidence = PublicEvidence(
        id=str(uuid4()),
        artifact_version_id=version.id,
        source_snapshot_id=str(uuid4()),
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
    version = version.model_copy(update={"evidence_ids": (evidence.id,)})
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
        redaction_policy="redacted_public_snapshot",
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
        request=_share_request(version, evidence, expires_at=NOW + timedelta(hours=1)),
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
        assert (
            row.token_hash
            == hashlib.sha256(created_share.share_token.encode("utf-8")).hexdigest()
        )
        assert created_share.share_token not in repr(row.artifact_versions)
        assert created_share.share_token not in repr(row.evidence)

    with factory() as session, session.begin():
        row = session.get(ShareSnapshotModel, created_share.id, with_for_update=True)
        assert row is not None
        row.artifact_versions = [{"kind": "dataset"}]

    with pytest.raises(SecurityProblem) as corrupted:
        restarted_snapshots.get_public_share(
            raw_token=created_share.share_token,
            now=NOW + timedelta(seconds=4),
        )
    assert corrupted.value.status == 404
    assert corrupted.value.code == "SHARE_NOT_FOUND"


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


def test_http_persistent_authority_conceals_resources_and_freezes_share(
    database: tuple[Engine, Callable[[], Session]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _engine, factory = database
    assert TEST_DATABASE_URL is not None
    monkeypatch.setattr(settings, "DATABASE_URL", SecretStr(TEST_DATABASE_URL))

    first_app = create_app()
    with TestClient(first_app, base_url="https://testserver") as client:
        victim_created = client.post("/api/sessions")
        assert victim_created.status_code == 201
        victim_csrf = victim_created.json()["data"]["csrf_token"]
        victim_credential = client.cookies.get(settings.SESSION_COOKIE_NAME)
        assert victim_credential is not None
        victim_session = first_app.state.session_service.authenticate(victim_credential)

        client.cookies.clear()
        attacker_created = client.post("/api/sessions")
        assert attacker_created.status_code == 201
        attacker_csrf = attacker_created.json()["data"]["csrf_token"]
        attacker_credential = client.cookies.get(settings.SESSION_COOKIE_NAME)
        assert attacker_credential is not None
        attacker_session = first_app.state.session_service.authenticate(
            attacker_credential
        )

        victim = _persistent_resource_graph(
            factory, session_id=victim_session.id, label="victim"
        )
        attacker = _persistent_resource_graph(
            factory, session_id=attacker_session.id, label="attacker"
        )
        missing = {
            "run": uuid4(),
            "version": uuid4(),
            "evidence": uuid4(),
        }

        workspace_failures: list[tuple[int, str, str, str]] = []
        for references in (victim, missing, attacker):
            response = client.put(
                f"/api/projects/{victim['project']}/workspace-snapshot",
                json={
                    "active_run_id": str(references["run"]),
                    "panel_slots": [
                        {
                            "slot_id": "primary",
                            "panel_type": "atlas",
                            "artifact_version_id": str(references["version"]),
                            "evidence_id": str(references["evidence"]),
                        }
                    ],
                    "pinned_evidence_ids": [str(references["evidence"])],
                    "layout_preset": "owner-concealing",
                },
                headers={
                    "If-Match": "0",
                    "X-CSRF-Token": attacker_csrf,
                },
            )
            problem = response.json()
            workspace_failures.append(
                (
                    response.status_code,
                    problem["code"],
                    problem["title"],
                    problem["detail"],
                )
            )
        assert set(workspace_failures) == {
            (404, "PROJECT_NOT_FOUND", "Resource not found", "Resource not found")
        }

        expires_at = datetime.now(UTC) + timedelta(hours=1)
        share_failures: list[tuple[int, str, str, str]] = []
        for references in (victim, missing, attacker):
            response = client.post(
                f"/api/projects/{victim['project']}/shares",
                json={
                    "title": "Must remain concealed",
                    "artifact_version_ids": [str(references["version"])],
                    "evidence_ids": [str(references["evidence"])],
                    "redaction_policy": "redacted_public_snapshot",
                    "expires_at": expires_at.isoformat(),
                },
                headers={"X-CSRF-Token": attacker_csrf},
            )
            problem = response.json()
            share_failures.append(
                (
                    response.status_code,
                    problem["code"],
                    problem["title"],
                    problem["detail"],
                )
            )
        assert set(share_failures) == {
            (404, "PROJECT_NOT_FOUND", "Resource not found", "Resource not found")
        }

        with factory() as session:
            assert session.get(WorkspaceSnapshotModel, victim["project"]) is None
            assert tuple(session.scalars(select(ShareSnapshotModel))) == ()

        client.cookies.clear()
        client.cookies.set(settings.SESSION_COOKIE_NAME, victim_credential, path="/api")
        created = client.post(
            f"/api/projects/{victim['project']}/shares",
            json={
                "title": "Frozen production share",
                "artifact_version_ids": [str(victim["version"])],
                "evidence_ids": [str(item) for item in victim["evidence_ids"]],
                "redaction_policy": "redacted_public_snapshot",
                "expires_at": expires_at.isoformat(),
            },
            headers={"X-CSRF-Token": victim_csrf},
        )
        assert created.status_code == 201
        created_share = created.json()["data"]
        raw_token = created_share["share_token"]

    replacement_version_id = uuid4()
    with factory() as session, session.begin():
        artifact = session.get(ResearchArtifactModel, victim["artifact"])
        assert artifact is not None
        session.add(
            ArtifactVersionModel(
                id=replacement_version_id,
                artifact_id=artifact.id,
                project_id=victim["project"],
                created_by_run_id=victim["run"],
                run_step_id=victim["step"],
                step_attempt_id=victim["attempt"],
                producer_execution_id=victim["producer"],
                version_number=2,
                publication_key="victim-publication-2",
                schema_version="2.0.0",
                content={"kind": "dataset", "rows": [{"changed": True}]},
                content_hash=HASH_A,
                input_hash=HASH_B,
                source_mode="live",
                producer={
                    "type": "algorithm",
                    "name": "snapshot-test-producer",
                    "version": "1.0.0",
                    "parameters_hash": HASH_A,
                },
                source_snapshot_ids=[str(victim["snapshot"])],
                evidence_ids=[],
                created_at=NOW + timedelta(minutes=1),
            )
        )
        session.flush()
        artifact.title = "Changed dynamic authority title"
        artifact.latest_version_id = replacement_version_id

    restarted_app = create_app()
    with TestClient(restarted_app, base_url="https://testserver") as public_client:
        resolved = public_client.get(f"/api/public/shares/{raw_token}")
    assert resolved.status_code == 200
    projection = resolved.json()["data"]
    assert projection["title"] == "Frozen production share"
    assert len(projection["artifact_versions"]) == 1
    frozen_version = projection["artifact_versions"][0]
    assert frozen_version["id"] == str(victim["version"])
    assert frozen_version["artifact_id"] == str(victim["artifact"])
    assert frozen_version["title"] == "Frozen victim dataset"
    assert frozen_version["version_number"] == 1
    assert frozen_version["evidence_ids"] == [
        str(item) for item in victim["evidence_ids"]
    ]
    assert "content" not in frozen_version
    assert frozen_version["presentation"]["kind"] == "dataset"
    assert [entry["key"] for entry in frozen_version["presentation"]["entries"]] == [
        "planet.toi_id",
        "star.tic_id",
    ]

    assert len(projection["evidence"]) == len(victim["evidence_ids"])
    frozen_evidence = projection["evidence"][0]
    assert frozen_evidence["id"] == str(victim["evidence"])
    assert frozen_evidence["artifact_version_id"] == str(victim["version"])
    assert frozen_evidence["source_snapshot_id"] == str(victim["snapshot"])
    assert frozen_evidence["locator"]["kind"] == "database_cell"
    assert "row" not in frozen_evidence["locator"]
    assert frozen_evidence["quote_or_value"] is None
    assert frozen_evidence["source"] == {
        "source_id": "victim-source",
        "source_type": "catalog",
        "retrieved_at": NOW.isoformat().replace("+00:00", "Z"),
        "license_note": "Public metadata only.",
        "request_metadata": {},
    }


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
    assert (
        first_snapshots.get_workspace(
            project_id=project_id, session_id=owner.id
        ).revision
        == 2
    )


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
        request=_share_request(version, evidence, expires_at=NOW + timedelta(hours=1)),
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
    assert (
        snapshots.cleanup(now=NOW + timedelta(hours=2), retention=timedelta(minutes=1))
        == 2
    )
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
        patch.setattr(PersistentSessionStore, "_cleanup", staticmethod(fail_cleanup))
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
    snapshots = PersistentSnapshotStore(factory, authority, retention=timedelta())
    with monkeypatch.context() as patch:
        patch.setattr(PersistentSnapshotStore, "_cleanup", staticmethod(fail_cleanup))
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
