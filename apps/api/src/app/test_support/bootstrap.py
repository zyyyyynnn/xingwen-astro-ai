"""Deterministic demo_replay fixture publication for real integration runs.

The public Authoring Chain keeps this module focused on fixture publication:
(``createResearchProject``, ``createResearchContractDraft``, draft update,
contract confirm, run create) is exercised through the real ``/api``
runtime, so the bootstrap no longer injects Project, ContractDraft, Contract,
Run, credentials or Share tokens. Its only job is publishing the frozen main
case's deterministic ``demo_replay``/``fixture`` ArtifactVersion + Evidence
onto a session-owned Run through the existing Persistence/Publisher boundary
(the fixture path has no live executor to produce them).

Hard boundaries:

- Only reachable when ``APP_ENV`` is ``test`` or ``integration``; the router is
  never mounted in ``development`` or ``production``.
- Not a Live pipeline: the artifact is published with ``source_mode="fixture"``
  and only onto a Run whose ``execution_mode`` is ``demo_replay``.
- Never returns or logs the session credential, CSRF token, or share token;
  entity ids are derived with ``uuid5`` from the target run id.
- No arbitrary artifact content can be uploaded: the payload is the frozen
  main-case dataset and is validated by the real admission validators.
- Reuses the real runtime path (ResearchApplicationService ownership check,
  PersistentWorkflowStore, ArtifactPublisher) instead of parallel state.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Callable
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    ArtifactVersionModel,
    EvidenceModel,
    ResearchArtifactModel,
    SourceSnapshotModel,
)
from app.schemas.core import ArtifactKind, ExportArtifactContent
from app.security import SecurityProblem
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


def _seed_uuid(run_id: str, entity: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"{_NAMESPACE}/{run_id}/{entity}")


def _validate_evidence(context: ArtifactAdmissionContext) -> None:
    if len(context.source_snapshot_ids) != 1 or len(context.evidence_ids) != 1:
        raise ValueError("fixture publication requires one SourceSnapshot and Evidence")
    UUID(context.source_snapshot_ids[0])
    UUID(context.evidence_ids[0])


def _validate_domain(context: ArtifactAdmissionContext) -> None:
    candidate = context.candidate
    if not isinstance(candidate, ExportArtifactContent):
        raise ValueError("fixture publication requires canonical export content")
    if candidate.format != "json" or candidate.artifact_version_ids != ("artv_dataset_01",):
        raise ValueError("fixture export must reference the frozen dataset version")


def _validate_quality(context: ArtifactAdmissionContext) -> None:
    candidate = context.candidate
    if not isinstance(candidate, ExportArtifactContent):
        raise ValueError("fixture publication requires canonical export content")
    if len(candidate.artifact_version_ids) != 1:
        raise ValueError("fixture export must contain one deterministic source version")


class BootstrapResult(BaseModel):
    """Known ids of the published fixture. Never contains credentials."""

    model_config = ConfigDict(frozen=True)

    run_id: str
    artifact_id: str
    artifact_version_id: str
    source_snapshot_id: str
    evidence_id: str
    execution_mode: str = "demo_replay"
    source_mode: str = "fixture"
    scenario: str = "exoplanet_host_star"


def bootstrap_fixture_artifacts(
    *,
    session_id: str,
    run_id: str,
    factory: Callable[[], Session],
    research_service: ResearchApplicationService,
    workflow_store: PersistentWorkflowStore,
) -> BootstrapResult:
    """Publish the deterministic fixture version onto ``run_id`` (idempotent).

    The run must already exist, belong to the calling session (ownership is
    checked through the real application boundary, so cross-session runs stay
    a hidden 404) and use ``execution_mode="demo_replay"``.
    """
    run = research_service.get_run(run_id=run_id, session_id=session_id)
    if run.execution_mode.value != "demo_replay":
        raise SecurityProblem(
            status=409,
            code="BOOTSTRAP_RUN_NOT_DEMO_REPLAY",
            title="Bootstrap requires a demo_replay run",
            detail="Fixture artifacts can only be published onto a demo_replay run",
        )

    run_uuid = UUID(run.id)
    project_id = UUID(run.project_id)
    artifact_id = _seed_uuid(run.id, "artifact")
    source_snapshot_id = _seed_uuid(run.id, "source-snapshot")
    evidence_id = _seed_uuid(run.id, "evidence")

    with factory() as session:
        existing_version_id = session.scalar(
            select(ArtifactVersionModel.id)
            .where(ArtifactVersionModel.artifact_id == artifact_id)
            .limit(1)
        )
    if existing_version_id is None:
        existing_version_id = _publish_fixture_version(
            run_id=run.id,
            factory=factory,
            workflow_store=workflow_store,
            run_uuid=run_uuid,
            project_id=project_id,
            artifact_id=artifact_id,
            source_snapshot_id=source_snapshot_id,
            evidence_id=evidence_id,
        )

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
        run_id=run.id,
        artifact_id=str(artifact_id),
        artifact_version_id=str(existing_version_id),
        source_snapshot_id=str(source_snapshot_id),
        evidence_id=str(evidence_id),
    )


def _publish_fixture_version(
    *,
    run_id: str,
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
        owner="real_integration-test-bootstrap",
        lease_duration=timedelta(minutes=5),
        expected_status="queued",
        expected_revision=snapshot.revision,
    )
    attempt = workflow_store.begin_step(
        run_uuid,
        step_key="planning",
        attempt_idempotency_key=f"real_integration-bootstrap-attempt-{run_id}",
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
                    kind="export",
                    title="Exoplanet host-star dataset",
                    logical_key="dataset.primary",
                )
            )
        if session.get(SourceSnapshotModel, source_snapshot_id) is None:
            session.add(
                SourceSnapshotModel(
                    id=source_snapshot_id,
                    project_id=project_id,
                    source_id="real_integration_test_bootstrap_fixture",
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
        ExportArtifactContent(
            kind=ArtifactKind.export,
            format="json",
            artifact_version_ids=("artv_dataset_01",),
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
            idempotency_key=f"real_integration-bootstrap-producer-{run_id}",
            producer_type="pipeline",
            producer_name="real_integration-test-bootstrap",
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
                publication_key=f"real_integration-bootstrap-fixture-{run_id}",
                producer_execution_id=execution.id,
                candidate=candidate,
                source_mode="fixture",
            ),
        ),
        public_message="Deterministic demo_replay fixture published",
    )
    return published.versions[0].id
