"""Deterministic demo_replay fixture bootstrap for real integration runs.

X-01 (#122) requires the frozen M1 contract surface to stay free of public
"create project / create draft" endpoints, while real Browser E2E still needs
deterministic, known research data. This module seeds a minimal
``demo_replay`` / ``fixture`` scenario bound to the *calling session's* owner
id, so ownership, 401/403/404 and CSRF semantics stay intact end to end.

Hard boundaries:

- Only reachable when ``APP_ENV`` is ``test`` or ``integration``; the router is
  never mounted in ``development`` or ``production``.
- Not a Live pipeline: every artifact is published with
  ``source_mode="fixture"`` and the run uses ``execution_mode="demo_replay"``.
- Never returns or logs the session credential, CSRF token, or share token;
  entity ids are derived with ``uuid5`` from the opaque session id.
- Reuses the real runtime path (ResearchApplicationService,
  PersistentWorkflowStore, ArtifactPublisher) instead of hand-registering
  parallel state.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Callable, Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    ArtifactVersionModel,
    EvidenceModel,
    ResearchArtifactModel,
    ResearchContractDraftModel,
    ResearchProjectModel,
    SourceSnapshotModel,
)
from app.schemas.v2 import ConfirmResearchContractRequest, CreateRunRequest
from app.services.research import ResearchApplicationService
from app.workflow.publisher import (
    ArtifactAdmissionContext,
    ArtifactPublication,
    ArtifactPublisher,
    ProducerExecutionRequest,
    ProducerExecutionStore,
    admit_artifact_candidate,
)
from app.workflow.store import PersistentWorkflowStore

_NAMESPACE = "https://xingwen.example/test-only-bootstrap"
_NOW = datetime(2026, 7, 22, 8, tzinfo=UTC)


def _seed_uuid(session_id: str, entity: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"{_NAMESPACE}/{session_id}/{entity}")


class _FixtureDatasetCandidate(BaseModel):
    kind: Literal["dataset"] = "dataset"
    field_ids: tuple[str, ...]
    rows: tuple[dict[str, str], ...]


def _validate_evidence(context: ArtifactAdmissionContext) -> None:
    if len(context.source_snapshot_ids) != 1 or len(context.evidence_ids) != 1:
        raise ValueError("fixture publication requires one SourceSnapshot and Evidence")
    UUID(context.source_snapshot_ids[0])
    UUID(context.evidence_ids[0])


def _validate_domain(context: ArtifactAdmissionContext) -> None:
    candidate = context.candidate
    if not isinstance(candidate, _FixtureDatasetCandidate):
        raise ValueError("fixture publication requires the typed dataset candidate")
    if candidate.field_ids != ("planet.toi_id", "star.tic_id"):
        raise ValueError("fixture dataset fields must match the frozen M1 scenario")
    declared = set(candidate.field_ids)
    if any(set(row) != declared for row in candidate.rows):
        raise ValueError("every fixture row must contain exactly the declared fields")


def _validate_quality(context: ArtifactAdmissionContext) -> None:
    candidate = context.candidate
    if not isinstance(candidate, _FixtureDatasetCandidate) or len(candidate.rows) != 1:
        raise ValueError("fixture dataset must contain exactly one deterministic row")
    if any(not value.strip() for value in candidate.rows[0].values()):
        raise ValueError("fixture dataset values must be non-empty")


def _contract_input() -> dict[str, object]:
    return {
        "research_goal": "Integrate exoplanet candidates and host-star parameters",
        "target_objects": ["exoplanet_candidate", "host_star"],
        "data_requirements": {"unit_policy": "canonical"},
        "requested_fields": ["planet.toi_id", "star.tic_id"],
        "source_scope": {"allowed_sources": ["nasa_exoplanet_archive"]},
        "paper_search_scope": {
            "keywords": ["exoplanet", "host star parameters"],
            "year_from": 2018,
            "year_to": 2026,
            "source_ids": ["nasa_exoplanet_archive"],
            "max_candidates": 5,
        },
        "output_requirements": ["dataset", "graph"],
        "evidence_requirements": {
            "require_locator": True,
            "require_source_snapshot": True,
            "minimum_coverage": 1.0,
        },
        "quality_constraints": {
            "source_completeness_min": 1.0,
            "unit_consistency_min": 1.0,
        },
    }


class BootstrapResult(BaseModel):
    """Known ids of the seeded scenario. Never contains credentials."""

    model_config = ConfigDict(frozen=True)

    project_id: str
    draft_id: str
    contract_id: str | None = None
    run_id: str | None = None
    artifact_version_id: str | None = None
    evidence_id: str | None = None
    execution_mode: str = "demo_replay"
    source_mode: str = "fixture"
    scenario: str = "exoplanet_host_star"


def bootstrap_demo_scenario(
    *,
    session_id: str,
    factory: Callable[[], Session],
    research_service: ResearchApplicationService,
    workflow_store: PersistentWorkflowStore,
    complete: bool = True,
) -> BootstrapResult:
    """Seed the deterministic scenario for ``session_id`` (idempotent).

    ``complete=False`` creates only the Project and editable Draft so the real
    browser can exercise save/confirm/create-Run itself. A later complete call
    reuses that session-owned Contract and Run, then publishes the fixture
    ArtifactVersion/Evidence through the real persistence boundary.
    """
    project_id = _seed_uuid(session_id, "project")
    draft_id = _seed_uuid(session_id, "draft")
    artifact_id = _seed_uuid(session_id, "artifact")
    source_snapshot_id = _seed_uuid(session_id, "source-snapshot")
    evidence_id = _seed_uuid(session_id, "evidence")

    # ---- Project + Draft (no public endpoint exists by design) -------------
    with factory() as session, session.begin():
        project = session.get(ResearchProjectModel, project_id)
        if project is None:
            session.add(
                ResearchProjectModel(
                    id=project_id,
                    session_id=session_id,
                    name="Exoplanet host-star integration",
                    description="Evidence-bound integration for the frozen main case",
                    case_key="exoplanet_host_star",
                    revision=1,
                    created_at=_NOW,
                    updated_at=_NOW,
                )
            )
        draft = session.get(ResearchContractDraftModel, draft_id)
        if draft is None:
            session.add(
                ResearchContractDraftModel(
                    id=draft_id,
                    session_id=session_id,
                    version=1,
                    intent="Integrate exoplanet candidates and host-star parameters",
                    status="draft",
                    contract=_contract_input(),
                    warnings=[],
                    created_at=_NOW,
                    updated_at=_NOW,
                    expires_at=datetime.now(UTC) + timedelta(hours=1),
                )
            )

    if not complete:
        return BootstrapResult(project_id=str(project_id), draft_id=str(draft_id))

    # ---- Contract + Run via the real application path -----------------------
    project = research_service.get_project(
        project_id=str(project_id), session_id=session_id
    )
    contract = (
        research_service.get_contract(
            contract_id=project.active_contract_id, session_id=session_id
        )
        if project.active_contract_id is not None
        else research_service.confirm_contract(
            project_id=str(project_id),
            session_id=session_id,
            idempotency_key=f"x01-bootstrap-confirm-{session_id}",
            request=ConfirmResearchContractRequest(
                draft_id=str(draft_id), expected_draft_version=1
            ),
        )
    )
    project = research_service.get_project(
        project_id=str(project_id), session_id=session_id
    )
    run = (
        research_service.get_run(run_id=project.latest_run_id, session_id=session_id)
        if project.latest_run_id is not None
        else research_service.create_run(
            project_id=str(project_id),
            session_id=session_id,
            idempotency_key=f"x01-bootstrap-run-{session_id}",
            request=CreateRunRequest(
                contract_id=contract.id,
                execution_mode="demo_replay",
                derivation_kind="original",
            ),
        )
    )
    run_uuid = UUID(run.id)

    # ---- Fixture artifact version via the real publisher path ----------------
    with factory() as session:
        existing_version_id = session.scalar(
            select(ArtifactVersionModel.id)
            .where(ArtifactVersionModel.artifact_id == artifact_id)
            .limit(1)
        )
    if existing_version_id is None:
        existing_version_id = _publish_fixture_version(
            session_id=session_id,
            factory=factory,
            workflow_store=workflow_store,
            run_uuid=run_uuid,
            project_id=project_id,
            artifact_id=artifact_id,
            source_snapshot_id=source_snapshot_id,
            evidence_id=evidence_id,
        )

    # ---- Evidence bound to the published version ------------------------------
    with factory() as session, session.begin():
        evidence = session.get(EvidenceModel, evidence_id)
        if evidence is None:
            session.add(
                EvidenceModel(
                    id=evidence_id,
                    project_id=project_id,
                    artifact_version_id=existing_version_id,
                    target_type="field",
                    target_id="planet.toi_id",
                    evidence_type="database_query",
                    source_snapshot_id=source_snapshot_id,
                    locator={
                        "kind": "database_cell",
                        "query_hash": "qhash_01",
                        "row_key": "TOI-1234",
                        "field": "planet.toi_id",
                    },
                    quote_or_value="TOI-1234",
                    extraction_method="nasa_exoplanet_archive.api_lookup",
                    confidence=1.0,
                    created_at=_NOW,
                )
            )

    return BootstrapResult(
        project_id=str(project_id),
        draft_id=str(draft_id),
        contract_id=contract.id,
        run_id=run.id,
        artifact_version_id=str(existing_version_id),
        evidence_id=str(evidence_id),
    )


def _publish_fixture_version(
    *,
    session_id: str,
    factory: Callable[[], Session],
    workflow_store: PersistentWorkflowStore,
    run_uuid: UUID,
    project_id: UUID,
    artifact_id: UUID,
    source_snapshot_id: UUID,
    evidence_id: UUID,
) -> UUID:
    """Drive one workflow step and publish a deterministic fixture version."""
    snapshot = workflow_store.load_snapshot(run_uuid)
    lease = workflow_store.acquire_lease(
        run_uuid,
        owner="x01-test-bootstrap",
        lease_duration=timedelta(minutes=5),
        expected_status="queued",
        expected_revision=snapshot.revision,
    )
    attempt = workflow_store.begin_step(
        run_uuid,
        step_key="planning",
        attempt_idempotency_key=f"x01-bootstrap-attempt-{session_id}",
        token=lease.token,
        generation=lease.generation,
        expected_status="queued",
        expected_revision=lease.revision,
        public_message="Seeding deterministic demo_replay fixture",
    )

    with factory() as session, session.begin():
        if session.get(ResearchArtifactModel, artifact_id) is None:
            session.add(
                ResearchArtifactModel(
                    id=artifact_id,
                    project_id=project_id,
                    kind="dataset",
                    title="Exoplanet host-star dataset",
                    logical_key="dataset.primary",
                )
            )
        if session.get(SourceSnapshotModel, source_snapshot_id) is None:
            session.add(
                SourceSnapshotModel(
                    id=source_snapshot_id,
                    project_id=project_id,
                    source_id="x01_test_bootstrap_fixture",
                    source_type="fixture",
                    retrieved_at=_NOW,
                    query={"scenario": "exoplanet_host_star"},
                    query_hash="sha256:" + "1" * 64,
                    content_hash="sha256:" + "2" * 64,
                    license_note="Test-only fixture; not a live scientific source",
                    request_metadata={"execution_mode": "demo_replay"},
                )
            )

    candidate = admit_artifact_candidate(
        _FixtureDatasetCandidate(
            field_ids=("planet.toi_id", "star.tic_id"),
            rows=({"planet.toi_id": "TOI-1234", "star.tic_id": "TIC-5678"},),
        ),
        schema_version="2.0.0",
        source_snapshot_ids=(str(source_snapshot_id),),
        evidence_ids=(str(evidence_id),),
        evidence_validator=_validate_evidence,
        domain_validator=_validate_domain,
        quality_validator=_validate_quality,
    )
    ledger = ProducerExecutionStore(factory)
    execution = ledger.start_producer_execution(
        ProducerExecutionRequest(
            run_id=run_uuid,
            step_key="planning",
            attempt_id=attempt.attempt_id,
            idempotency_key=f"x01-bootstrap-producer-{session_id}",
            producer_type="pipeline",
            producer_name="x01-test-bootstrap",
            producer_version="1.0.0",
            input_hash="sha256:" + "3" * 64,
            parameters={"scenario": "exoplanet_host_star"},
        ),
        token=lease.token,
        generation=lease.generation,
        expected_status=attempt.run_status,
        expected_revision=attempt.run_revision,
    )
    ledger.finish_producer_execution(
        execution.id,
        status="completed",
        output_hash=candidate.content_hash,
    )
    published = ArtifactPublisher(factory).publish_step_outputs(
        run_uuid,
        step_key="planning",
        attempt_id=attempt.attempt_id,
        token=lease.token,
        generation=lease.generation,
        expected_status=attempt.run_status,
        expected_revision=attempt.run_revision,
        publications=(
            ArtifactPublication(
                artifact_id=artifact_id,
                publication_key=f"x01-bootstrap-fixture-{session_id}",
                producer_execution_id=execution.id,
                candidate=candidate,
                source_mode="fixture",
            ),
        ),
        public_message="Deterministic demo_replay fixture published",
    )
    return published.versions[0].id
