"""PostgreSQL publication and replay contracts for Evidence Graph artifacts.

Set TEST_DATABASE_URL to an isolated database whose name contains ``test``.
The module reuses the Publisher integration migration fixture and deletes only
the deterministic Evidence Graph project between cases.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
import os
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, delete, func, select
from sqlalchemy.orm import Session

from app.db.models import (
    ArtifactVersionModel,
    EvidenceModel,
    ProducerExecutionModel,
    ResearchArtifactModel,
    ResearchContractModel,
    ResearchProjectModel,
    ResearchRunModel,
    RunStepModel,
    SourceSnapshotModel,
    StepAttemptModel,
)
from app.db.session import session_factory
from authoring_test_support import (
    build_contract_draft,
    build_research_contract,
    build_research_project,
    persist_authoring_models,
)
from app.schemas.graph_artifact import (
    GraphArtifactCandidate,
    graph_algorithm_parameters,
)
from app.workflow.publisher import (
    ArtifactAdmissionContext,
    ArtifactEvidenceBinding,
    ArtifactPublication,
    ArtifactPublisher,
    ArtifactSourceSnapshotBinding,
    ProducerExecutionRequest,
    ProducerExecutionStore,
    PublicationAdmissionError,
    PublicationConflictError,
    PublicationResult,
    admit_artifact_candidate,
)
from app.workflow.store import PersistentWorkflowStore
from services.graph_pipeline.pipeline import GraphPipeline

from graph_pipeline_test_support import (
    LiteratureGraphFixture,
    build_literature_graph_fixture,
    stable_uuid,
)
from test_artifact_publisher_postgres import _steps, postgres_engine


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL, reason="TEST_DATABASE_URL is not configured"
)
GRAPH_PROJECT_ID = UUID(stable_uuid("project:evidence_graph-real-literature_relation"))


def _accept(_: ArtifactAdmissionContext) -> None:
    return None


@pytest.fixture(autouse=True)
def _clean_graph_project(postgres_engine: Engine):
    """Keep this module repeatable without truncating another test's project."""

    factory = session_factory(postgres_engine)
    with factory() as session, session.begin():
        session.execute(
            delete(ResearchProjectModel).where(
                ResearchProjectModel.id == GRAPH_PROJECT_ID
            )
        )
    yield
    with factory() as session, session.begin():
        session.execute(
            delete(ResearchProjectModel).where(
                ResearchProjectModel.id == GRAPH_PROJECT_ID
            )
        )


def _candidate_and_fixture() -> tuple[GraphArtifactCandidate, LiteratureGraphFixture]:
    fixture = build_literature_graph_fixture()
    result = GraphPipeline(fixture.reader).admit(fixture.request())
    assert result.candidate is not None
    return result.candidate, fixture


def _admitted(candidate: GraphArtifactCandidate):
    snapshots = tuple(
        ArtifactSourceSnapshotBinding(
            pipeline_source_snapshot_id=item.source_snapshot_id,
            persisted_source_snapshot_id=item.persisted_source_snapshot_id,
        )
        for item in candidate.source_snapshots
    )
    persisted_snapshot_by_pipeline = {
        item.pipeline_source_snapshot_id: item.persisted_source_snapshot_id
        for item in snapshots
    }
    evidence = tuple(
        ArtifactEvidenceBinding(
            target_type="graph_edge",
            target_id=item.graph_edge_id,
            pipeline_evidence_id=item.evidence_use_id,
            pipeline_source_snapshot_id=item.source_snapshot_id,
            persisted_evidence_id=stable_uuid(
                f"graph-owned-evidence:{item.evidence_use_id}"
            ),
            persisted_source_snapshot_id=persisted_snapshot_by_pipeline[
                item.source_snapshot_id
            ],
        )
        for item in candidate.evidence_uses
    )
    return admit_artifact_candidate(
        candidate,
        schema_version=candidate.schema_version,
        source_snapshot_ids=candidate.source_snapshot_ids,
        evidence_ids=candidate.evidence_ids,
        source_snapshot_bindings=snapshots,
        evidence_bindings=evidence,
        evidence_validator=_accept,
        domain_validator=_accept,
        quality_validator=_accept,
    )


@dataclass(frozen=True, slots=True)
class ActiveGraphPublication:
    factory: Callable[[], Session]
    publisher: ArtifactPublisher
    candidate: GraphArtifactCandidate
    artifact: ResearchArtifactModel
    run_id: UUID
    token: UUID
    generation: int
    attempt_id: UUID
    run_status: str
    run_revision: int
    execution_id: UUID
    publication: ArtifactPublication


def _active_graph_publication(
    engine: Engine,
    *,
    artifact_kind: str = "graph",
    producer_mutation: str | None = None,
    publisher_class: type[ArtifactPublisher] = ArtifactPublisher,
) -> ActiveGraphPublication:
    candidate, fixture = _candidate_and_fixture()
    admitted = _admitted(candidate)
    factory = session_factory(engine)
    project = build_research_project(
        project_id=GRAPH_PROJECT_ID,
        session_id=f"session-{uuid4()}",
        name="Evidence Graph publisher integration",
        case_key="exoplanet_host_star",
    )
    draft = build_contract_draft(project)
    contract = build_research_contract(
        project,
        draft,
        contract_id=uuid4(),
        content_hash="sha256:" + "a" * 64,
    )
    with factory() as session, session.begin():
        persist_authoring_models(
            session, project=project, draft=draft, contract=contract
        )

    workflow = PersistentWorkflowStore(factory)
    snapshot = workflow.create_run(
        project_id=project.id,
        contract_id=contract.id,
        execution_mode="live",
        idempotency_key=f"graph-run-{uuid4()}",
        request_hash="sha256:" + "b" * 64,
        steps=_steps(),
    )
    lease = workflow.acquire_lease(
        snapshot.id,
        owner=f"graph-publisher-{uuid4()}",
        lease_duration=timedelta(minutes=5),
        expected_status="queued",
        expected_revision=snapshot.revision,
    )
    attempt = workflow.begin_step(
        snapshot.id,
        step_key="planning",
        attempt_idempotency_key=f"graph-attempt-{uuid4()}",
        token=lease.token,
        generation=lease.generation,
        expected_status="queued",
        expected_revision=lease.revision,
        public_message="Build Evidence Graph",
    )

    producer = candidate.producer
    producer_type = producer.producer_type
    producer_name = producer.producer_name
    producer_version = producer.producer_version
    input_hash = candidate.input_hash
    parameters = graph_algorithm_parameters(candidate.policies, candidate.taxonomy)
    model_provider = None
    model_name = None
    prompt_name = None
    prompt_version = None
    prompt_hash = None
    if producer_mutation == "type":
        producer_type = "pipeline"
    elif producer_mutation == "name":
        producer_name = "wrong-graph-producer"
    elif producer_mutation == "version":
        producer_version = "9.9.9"
    elif producer_mutation == "input_hash":
        input_hash = "sha256:" + "c" * 64
    elif producer_mutation == "parameters_hash":
        parameters = {**parameters, "max_nodes": parameters["max_nodes"] - 1}
    elif producer_mutation == "model_provider":
        model_provider = "fabricated-provider"
    elif producer_mutation == "model_name":
        model_name = "fabricated-model"
    elif producer_mutation == "prompt_name":
        prompt_name = "fabricated-prompt"
    elif producer_mutation == "prompt_version":
        prompt_version = "invalid-version"
    elif producer_mutation == "prompt_hash":
        prompt_hash = "sha256:" + "d" * 64

    ledger = ProducerExecutionStore(factory)
    execution = ledger.start_producer_execution(
        ProducerExecutionRequest(
            run_id=snapshot.id,
            step_key="planning",
            attempt_id=attempt.attempt_id,
            idempotency_key=f"graph-producer-{uuid4()}",
            producer_type=producer_type,
            producer_name=producer_name,
            producer_version=producer_version,
            input_hash=input_hash,
            parameters=parameters,
            model_provider=model_provider,
            model_name=model_name,
            prompt_name=prompt_name,
            prompt_version=prompt_version,
            prompt_hash=prompt_hash,
        ),
        token=lease.token,
        generation=lease.generation,
        expected_status=attempt.run_status,
        expected_revision=attempt.run_revision,
    )
    ledger.finish_producer_execution(
        execution.id,
        status="completed",
        output_hash=admitted.content_hash,
        token_usage={"graph_nodes": len(candidate.nodes)},
        latency_ms=1,
    )

    artifact = ResearchArtifactModel(
        id=uuid4(),
        project_id=project.id,
        kind=artifact_kind,
        title="Evidence Graph",
        logical_key=f"graph-{uuid4()}",
    )
    with factory() as session, session.begin():
        session.add(artifact)
        _seed_upstream_graph_closure(
            session,
            fixture=fixture,
            candidate=candidate,
            project=project,
            run_id=snapshot.id,
            step_key="planning",
            attempt_id=attempt.attempt_id,
            generation=lease.generation,
        )

    publication = ArtifactPublication(
        artifact_id=artifact.id,
        publication_key="graph.evidence_graph.publisher",
        producer_execution_id=execution.id,
        candidate=admitted,
        source_mode="fixture",
    )
    return ActiveGraphPublication(
        factory=factory,
        publisher=publisher_class(factory),
        candidate=candidate,
        artifact=artifact,
        run_id=snapshot.id,
        token=lease.token,
        generation=lease.generation,
        attempt_id=attempt.attempt_id,
        run_status=attempt.run_status,
        run_revision=attempt.run_revision,
        execution_id=execution.id,
        publication=publication,
    )


def _seed_upstream_graph_closure(
    session: Session,
    *,
    fixture: LiteratureGraphFixture,
    candidate: GraphArtifactCandidate,
    project: ResearchProjectModel,
    run_id: UUID,
    step_key: str,
    attempt_id: UUID,
    generation: int,
) -> None:
    upstream = fixture.inputs.literature_relations
    pins = upstream.pins
    step = session.scalar(
        select(RunStepModel).where(
            RunStepModel.run_id == run_id,
            RunStepModel.key == step_key,
        )
    )
    assert step is not None
    upstream_artifact = ResearchArtifactModel(
        id=UUID(pins.artifact_id),
        project_id=project.id,
        kind="literature_relations",
        title="LiteratureRelation Pipeline admitted LiteratureRelations",
        logical_key="literature_relation-literature-relations",
    )
    upstream_execution = ProducerExecutionModel(
        id=UUID(pins.producer_execution.id),
        run_id=run_id,
        run_step_id=step.id,
        step_attempt_id=attempt_id,
        step_key=step_key,
        idempotency_key=f"upstream-{pins.artifact_version_id}",
        lease_generation=generation,
        producer_type=pins.producer_execution.producer.type,
        producer_name=pins.producer_execution.producer.name,
        producer_version=pins.producer_execution.producer.version,
        model_provider=pins.producer_execution.producer.model_provider,
        model_name=pins.producer_execution.producer.model_name,
        prompt_name=pins.producer_execution.producer.prompt_name,
        prompt_version=pins.producer_execution.producer.prompt_version,
        prompt_hash=pins.producer_execution.producer.prompt_hash,
        parameters={},
        parameters_hash=pins.producer_execution.parameters_hash,
        input_hash=pins.input_hash,
        output_hash=pins.content_hash,
        status="completed",
        started_at=pins.producer_execution.started_at,
        finished_at=pins.producer_execution.finished_at,
        token_usage=None,
        latency_ms=pins.producer_execution.latency_ms,
        error_code=None,
    )
    session.add_all((upstream_artifact, upstream_execution))
    session.flush()
    upstream_version = ArtifactVersionModel(
        id=UUID(pins.artifact_version_id),
        artifact_id=upstream_artifact.id,
        project_id=project.id,
        created_by_run_id=run_id,
        run_step_id=step.id,
        step_attempt_id=attempt_id,
        producer_execution_id=upstream_execution.id,
        version_number=pins.version_number,
        publication_key="literature_relation.fixture.upstream",
        schema_version=pins.schema_version,
        content=upstream.candidate.model_dump(mode="json", exclude_none=True),
        content_hash=pins.content_hash,
        input_hash=pins.input_hash,
        source_mode=pins.source_mode.value,
        producer={
            "type": upstream_execution.producer_type,
            "name": upstream_execution.producer_name,
            "version": upstream_execution.producer_version,
            "parameters_hash": upstream_execution.parameters_hash,
        },
        source_snapshot_ids=[
            item.persisted_source_snapshot_id
            for item in upstream.source_snapshot_bindings
        ],
        evidence_ids=[
            item.persisted_evidence_id for item in upstream.evidence_bindings
        ],
    )
    session.add(upstream_version)
    session.flush()
    upstream_artifact.latest_version_id = upstream_version.id

    for binding in upstream.source_snapshot_bindings:
        item = binding.source_snapshot
        session.add(
            SourceSnapshotModel(
                id=UUID(item.id),
                project_id=project.id,
                source_id=item.source_id,
                source_type=item.source_type,
                retrieved_at=item.retrieved_at,
                query=item.query,
                query_hash=item.query_hash,
                source_version_or_etag=item.source_version_or_etag,
                content_hash=item.content_hash,
                license_note=item.license_note,
                cache_version=item.cache_version,
                request_metadata=item.request_metadata,
            )
        )
    session.flush()
    expected_use_ids = {item.upstream_evidence_id for item in candidate.evidence_uses}
    for binding in upstream.evidence_bindings:
        item = binding.evidence
        if item.id not in expected_use_ids:
            continue
        session.add(
            EvidenceModel(
                id=UUID(item.id),
                project_id=project.id,
                artifact_version_id=UUID(item.artifact_version_id),
                target_type=item.target_type,
                target_id=item.target_id,
                evidence_type=item.evidence_type,
                source_snapshot_id=UUID(item.source_snapshot_id),
                paper_id=item.paper_id,
                locator=item.locator,
                quote_or_value=item.quote_or_value,
                extraction_method=item.extraction_method,
                confidence=item.confidence,
                is_restricted=binding.is_restricted,
            )
        )


def _publish(active: ActiveGraphPublication) -> PublicationResult:
    return active.publisher.publish_step_outputs(
        active.run_id,
        step_key="planning",
        attempt_id=active.attempt_id,
        token=active.token,
        generation=active.generation,
        expected_status=active.run_status,
        expected_revision=active.run_revision,
        publications=(active.publication,),
        public_message="Evidence Graph published",
    )


def test_graph_publish_materializes_new_edge_owned_evidence_and_replays_once(
    postgres_engine: Engine,
) -> None:
    active = _active_graph_publication(postgres_engine)
    first = _publish(active)
    replay = _publish(active)

    assert first.replayed is False
    assert replay.replayed is True
    assert replay.versions == first.versions
    version_id = first.versions[0].id
    uses = {item.evidence_use_id: item for item in active.candidate.evidence_uses}
    upstream_ids = {UUID(item.upstream_evidence_id) for item in uses.values()}
    with active.factory() as session:
        rows = tuple(
            session.scalars(
                select(EvidenceModel)
                .where(EvidenceModel.artifact_version_id == version_id)
                .order_by(EvidenceModel.id)
            )
        )
        assert len(rows) == len(uses)
        assert {row.id for row in rows}.isdisjoint(upstream_ids)
        assert (
            session.scalar(
                select(func.count())
                .select_from(EvidenceModel)
                .where(EvidenceModel.artifact_version_id == version_id)
            )
            == len(uses)
        )
        for row in rows:
            use = uses[row.locator["graph_evidence_use_id"]]
            snapshot = session.get(SourceSnapshotModel, row.source_snapshot_id)
            assert row.target_type == "graph_edge"
            assert row.target_id == use.graph_edge_id
            assert row.source_snapshot_id == UUID(
                next(
                    item.persisted_source_snapshot_id
                    for item in active.candidate.source_snapshots
                    if item.source_snapshot_id == use.source_snapshot_id
                )
            )
            assert snapshot is not None and snapshot.project_id == GRAPH_PROJECT_ID
            assert row.locator == {
                "graph_evidence_use_id": use.evidence_use_id,
                "upstream_artifact_version_id": use.upstream_artifact_version_id,
                "upstream_evidence_id": use.upstream_evidence_id,
                "upstream_target_type": use.upstream_target_type,
                "upstream_target_id": use.upstream_target_id,
                "upstream_evidence_hash": use.upstream_evidence_hash,
            }
            assert row.quote_or_value is None
            assert row.extraction_method == "graph_admission"
            assert row.confidence == 1.0
            assert row.is_restricted is use.upstream_is_restricted


@pytest.mark.parametrize("mutation", ("input_hash", "producer"))
def test_graph_replay_rejects_persisted_version_producer_drift(
    postgres_engine: Engine,
    mutation: str,
) -> None:
    active = _active_graph_publication(postgres_engine)
    first = _publish(active)
    with active.factory() as session, session.begin():
        version = session.get(ArtifactVersionModel, first.versions[0].id)
        assert version is not None
        if mutation == "input_hash":
            version.input_hash = "sha256:" + "e" * 64
        else:
            version.producer = {**version.producer, "prompt_name": "fabricated"}

    with pytest.raises(PublicationConflictError, match="producer metadata"):
        _publish(active)


@pytest.mark.parametrize("mutation", ("missing", "extra", "tampered"))
def test_graph_replay_rejects_non_exact_materialized_evidence_registry(
    postgres_engine: Engine,
    mutation: str,
) -> None:
    active = _active_graph_publication(postgres_engine)
    first = _publish(active)
    version_id = first.versions[0].id
    with active.factory() as session, session.begin():
        rows = tuple(
            session.scalars(
                select(EvidenceModel)
                .where(EvidenceModel.artifact_version_id == version_id)
                .order_by(EvidenceModel.id)
            )
        )
        assert rows
        if mutation == "missing":
            session.delete(rows[0])
        elif mutation == "extra":
            session.add(
                EvidenceModel(
                    id=uuid4(),
                    project_id=GRAPH_PROJECT_ID,
                    artifact_version_id=version_id,
                    target_type="graph_edge",
                    target_id=active.candidate.edges[0].edge_id,
                    evidence_type=rows[0].evidence_type,
                    source_snapshot_id=rows[0].source_snapshot_id,
                    paper_id=None,
                    locator={"unexpected": True},
                    quote_or_value=None,
                    extraction_method="graph_admission",
                    confidence=1.0,
                    is_restricted=False,
                )
            )
        else:
            rows[0].locator = {**rows[0].locator, "upstream_target_id": "tampered"}

    with pytest.raises(PublicationConflictError, match="Graph publication"):
        _publish(active)


def test_graph_target_kind_is_checked_before_idempotent_replay(
    postgres_engine: Engine,
) -> None:
    active = _active_graph_publication(postgres_engine)
    _publish(active)
    with active.factory() as session, session.begin():
        artifact = session.get(ResearchArtifactModel, active.artifact.id)
        assert artifact is not None
        artifact.kind = "export"

    with pytest.raises(PublicationAdmissionError, match="graph ResearchArtifacts"):
        _publish(active)


@pytest.mark.parametrize(
    "producer_mutation",
    (
        "type",
        "name",
        "version",
        "input_hash",
        "parameters_hash",
        "model_provider",
        "model_name",
        "prompt_name",
        "prompt_version",
        "prompt_hash",
    ),
)
def test_graph_publish_rejects_non_exact_producer_execution(
    postgres_engine: Engine,
    producer_mutation: str,
) -> None:
    active = _active_graph_publication(
        postgres_engine,
        producer_mutation=producer_mutation,
    )

    with pytest.raises(PublicationAdmissionError, match="matching ProducerExecution"):
        _publish(active)
    with active.factory() as session:
        artifact = session.get(ResearchArtifactModel, active.artifact.id)
        assert artifact is not None and artifact.latest_version_id is None
        assert (
            session.scalar(
                select(func.count())
                .select_from(ArtifactVersionModel)
                .where(ArtifactVersionModel.artifact_id == active.artifact.id)
            )
            == 0
        )


class _FailingGraphPublisher(ArtifactPublisher):
    def _before_commit(self, session: Session) -> None:
        raise RuntimeError("injected Graph transaction failure")


def test_graph_evidence_write_failure_rolls_back_entire_publication(
    postgres_engine: Engine,
) -> None:
    active = _active_graph_publication(
        postgres_engine,
        publisher_class=_FailingGraphPublisher,
    )
    graph_evidence_ids = {
        UUID(item.persisted_evidence_id)
        for item in active.publication.candidate.graph_evidence_materializations
    }

    with pytest.raises(RuntimeError, match="Graph transaction failure"):
        _publish(active)
    with active.factory() as session:
        artifact = session.get(ResearchArtifactModel, active.artifact.id)
        run = session.get(ResearchRunModel, active.run_id)
        step = session.scalar(
            select(RunStepModel).where(
                RunStepModel.run_id == active.run_id,
                RunStepModel.key == "planning",
            )
        )
        attempt = session.get(StepAttemptModel, active.attempt_id)
        assert artifact is not None and artifact.latest_version_id is None
        assert run is not None and run.status == "planning"
        assert step is not None and step.status == "running"
        assert attempt is not None and attempt.status == "running"
        assert (
            session.scalar(
                select(func.count())
                .select_from(ArtifactVersionModel)
                .where(ArtifactVersionModel.artifact_id == active.artifact.id)
            )
            == 0
        )
        assert set(
            session.scalars(
                select(EvidenceModel.id).where(EvidenceModel.id.in_(graph_evidence_ids))
            )
        ) == set()
