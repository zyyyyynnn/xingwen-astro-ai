"""PostgreSQL proof for the recorded PaperCollection publication closure.

The adapter is deliberately recorded and deterministic: this file exercises
the real runtime, PostgreSQL persistence, and ArtifactPublisher transaction,
without calling Crossref or treating a fixture as Live evidence.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
import os
from pathlib import Path
from uuid import UUID, uuid4
from unittest.mock import patch

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import Engine, func, select

from app.db.models import (
    ArtifactVersionModel,
    EvidenceModel,
    ProducerExecutionModel,
    ResearchArtifactModel,
    ResearchRunModel,
    RunEventModel,
    RunStepModel,
    SourceSnapshotModel,
    StepAttemptModel,
)
from app.db.session import create_engine_from_url, session_factory
from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.core import (
    ArtifactKind,
    DataRequirements,
    EvidenceRequirements,
    PaperSearchScope,
    QualityConstraints,
    ResearchContract,
    ResearchContractInput,
    SourceScope,
)
from app.schemas.enums import PaperDataLevel, SourceMode
from app.schemas.evidence import SourceSnapshotRecord
from app.schemas.paper_collection import PaperSourcePage
from app.workflow.paper_collection_search_runtime import (
    PaperCollectionSearchRuntime,
)
from app.workflow.publisher import ArtifactPublisher
from app.workflow.store import PersistentWorkflowStore, RunStepDefinition
from authoring_test_support import (
    build_contract_draft,
    build_research_contract,
    build_research_project,
    persist_authoring_models,
)
from services.paper_pipeline.sources.base import (
    RawSourceRecord,
    SourceSearchResult,
)


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL, reason="TEST_DATABASE_URL is not configured"
)

NOW = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)


class _RecordedCrossrefAdapter:
    """Deterministic Crossref-shaped source; never performs network I/O."""

    source_id = "crossref"
    adapter_name = "recorded_crossref_postgres"
    adapter_version = "1.0.0"

    def __init__(self) -> None:
        self.calls: list[tuple[SourceMode, PaperDataLevel]] = []
        self.records = (
            RawSourceRecord(
                source_id="crossref",
                source_record_id="crossref:recorded-1",
                title="Recorded Exoplanet Host-Star Study",
                authors=("Ada Researcher",),
                year=2024,
                doi="10.1234/recorded.1",
                arxiv_id=None,
                url="https://doi.org/10.1234/recorded.1",
            ),
        )

    def search(self, query, *, source_mode, data_level):  # type: ignore[no-untyped-def]
        self.calls.append((source_mode, data_level))
        records_hash = compute_canonical_payload_hash(
            [record.hash_payload() for record in self.records]
        )
        snapshot = SourceSnapshotRecord(
            snapshot_id="snapshot.crossref.recorded.postgres",
            source_id=self.source_id,
            source_type="paper_metadata",
            retrieved_at=NOW,
            query=query.normalized_query_string,
            query_hash=query.query_hash,
            content_hash=records_hash,
            license_note="Recorded Crossref metadata for PostgreSQL integration testing",
            request_metadata={"adapter_name": self.adapter_name},
        )
        page = PaperSourcePage(
            page_number=1,
            offset=0,
            requested_rows=len(self.records),
            returned_rows=len(self.records),
            total_results=len(self.records),
            attempt_count=1,
            status_code=200,
            retrieved_at=NOW,
            request_hash=compute_canonical_payload_hash(
                {"query_hash": query.query_hash}
            ),
            response_hash=records_hash,
        )
        return SourceSearchResult(
            records=self.records,
            pages=(page,),
            snapshot=snapshot,
            retry_count=0,
        )


def _alembic_config(url: str) -> Config:
    root = Path(__file__).resolve().parents[1]
    config = Config(root / "alembic.ini")
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


@pytest.fixture(scope="module")
def postgres_engine() -> Iterator[Engine]:
    assert TEST_DATABASE_URL is not None
    assert "test" in TEST_DATABASE_URL.rsplit("/", 1)[-1].lower(), (
        "refusing non-test database"
    )
    config = _alembic_config(TEST_DATABASE_URL)
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    engine = create_engine_from_url(TEST_DATABASE_URL)
    try:
        yield engine
    finally:
        engine.dispose()
        command.downgrade(config, "base")
        command.upgrade(config, "head")


def _contract(project_id: UUID) -> ResearchContract:
    content = ResearchContractInput(
        research_goal="Study transiting exoplanet host stars",
        target_objects=("exoplanet",),
        data_requirements=DataRequirements(),
        requested_fields=("planet.toi_id",),
        # Data source authority is intentionally separate from paper search.
        source_scope=SourceScope(allowed_sources=("nasa_exoplanet_archive",)),
        paper_search_scope=PaperSearchScope(
            keywords=("transiting exoplanet",),
            year_from=2020,
            year_to=2025,
            source_ids=("crossref",),
            max_candidates=2,
        ),
        output_requirements=(ArtifactKind.paper_collection,),
        evidence_requirements=EvidenceRequirements(),
        quality_constraints=QualityConstraints(),
    )
    return ResearchContract(
        **content.model_dump(),
        id=str(uuid4()),
        project_id=str(project_id),
        version=1,
        created_from_draft_id=str(uuid4()),
        created_at=NOW,
        content_hash=compute_canonical_payload_hash(content.model_dump(mode="json")),
    )


def _active_paper_run(
    factory,  # type: ignore[no-untyped-def]
    *,
    project_id: UUID,
    contract: ResearchContract,
):
    project = build_research_project(
        project_id=project_id,
        session_id=f"session-{uuid4()}",
        name="Paper Search PostgreSQL integration",
        case_key="exoplanet_host_star",
    )
    draft = build_contract_draft(
        project,
        draft_id=uuid4(),
        content=contract.model_dump(
            mode="json",
            exclude={
                "id",
                "project_id",
                "version",
                "created_from_draft_id",
                "created_at",
                "content_hash",
            },
        ),
    )
    persisted_contract = build_research_contract(
        project,
        draft,
        contract_id=uuid4(),
        content_hash=contract.content_hash,
        content=draft.contract,
    )
    domain_contract = contract.model_copy(
        update={
            # Database identity is a UUID FK; the domain/API Contract
            # reference is a stable Identifier used inside PaperCollection.
            "id": f"contract.paper.{persisted_contract.id.hex}",
            "project_id": str(project.id),
            "created_from_draft_id": str(draft.id),
        }
    )
    with factory() as session, session.begin():
        persist_authoring_models(
            session,
            project=project,
            draft=draft,
            contract=persisted_contract,
        )

    workflow = PersistentWorkflowStore(factory)

    def _identifier_uuid_sequence() -> Iterator[UUID]:
        base_suffix = project_id.int & ((1 << 48) - 1)
        for offset in range(16):
            yield UUID(
                f"00000000-0000-4000-8000-{(base_suffix + offset) % (1 << 48):012x}"
            )

    # Exercise the UUID lineage boundary with a numeric-leading UUID.  This
    # must not be confused with the letter-prefixed domain identifiers used by
    # offline benchmark runs.
    with patch("app.workflow.store.uuid4", side_effect=_identifier_uuid_sequence()):
        run = workflow.create_run(
            project_id=project.id,
            contract_id=persisted_contract.id,
            execution_mode="demo_replay",
            idempotency_key=f"paper-search-run-{uuid4()}",
            request_hash="sha256:" + "a" * 64,
            steps=(
                RunStepDefinition(
                    key="planning",
                    label="Planning",
                    enter_status="planning",
                    success_status="searching_papers",
                ),
                RunStepDefinition(
                    key="searching_papers",
                    label="Searching papers",
                    enter_status="searching_papers",
                    success_status="completed",
                    depends_on_step_keys=("planning",),
                ),
            ),
        )
        lease = workflow.acquire_lease(
            run.id,
            owner="paper-search-postgres-test",
            lease_duration=timedelta(minutes=5),
            expected_status="queued",
            expected_revision=run.revision,
        )
        planning_attempt = workflow.begin_step(
            run.id,
            step_key="planning",
            attempt_idempotency_key=f"planning-{uuid4()}",
            token=lease.token,
            generation=lease.generation,
            expected_status="queued",
            expected_revision=lease.revision,
            public_message="正在规划",
        )
        planning = ArtifactPublisher(factory).publish_step_outputs(
            run.id,
            step_key="planning",
            attempt_id=planning_attempt.attempt_id,
            token=lease.token,
            generation=lease.generation,
            expected_status=planning_attempt.run_status,
            expected_revision=planning_attempt.run_revision,
            publications=(),
            public_message="规划已完成",
        )
        attempt = workflow.begin_step(
            run.id,
            step_key="searching_papers",
            attempt_idempotency_key=f"searching-papers-{uuid4()}",
            token=lease.token,
            generation=lease.generation,
            expected_status=planning.status,
            expected_revision=planning.revision,
            public_message="正在检索论文",
        )
    return domain_contract, run, lease, attempt


def _prepare_publication(factory, *, project_id, contract, attempt, lease):  # type: ignore[no-untyped-def]
    adapter = _RecordedCrossrefAdapter()
    runtime = PaperCollectionSearchRuntime(
        session_factory=factory,
        adapters={"crossref": adapter},
        clock=lambda: NOW,
    )
    publication = runtime.prepare_publication(
        project_id=project_id,
        contract=contract,
        attempt=attempt,
        lease=lease,
        source_mode=SourceMode.fixture,
        data_level=PaperDataLevel.recorded_response,
    )
    assert adapter.calls == [(SourceMode.fixture, PaperDataLevel.recorded_response)]
    return publication


def test_recorded_crossref_publishes_complete_postgres_provenance_closure(
    postgres_engine: Engine,
) -> None:
    factory = session_factory(postgres_engine)
    project_id = uuid4()
    contract = _contract(project_id)
    domain_contract, run, lease, attempt = _active_paper_run(
        factory,
        project_id=project_id,
        contract=contract,
    )
    publication = _prepare_publication(
        factory,
        project_id=project_id,
        contract=domain_contract,
        attempt=attempt,
        lease=lease,
    )

    result = ArtifactPublisher(factory).publish_step_outputs(
        run.id,
        step_key="searching_papers",
        attempt_id=attempt.attempt_id,
        token=lease.token,
        generation=lease.generation,
        expected_status=attempt.run_status,
        expected_revision=attempt.run_revision,
        publications=(publication,),
        public_message="论文集合已发布",
    )

    assert result.status == "completed"
    assert len(result.versions) == 1
    version_id = result.versions[0].id

    with factory() as session:
        version = session.get(ArtifactVersionModel, version_id)
        assert version is not None
        assert version.project_id == project_id
        assert version.source_mode == SourceMode.fixture.value
        assert version.content["kind"] == "paper_collection"
        assert "research_contract" in version.content
        assert "benchmark" not in version.content

        artifact = session.get(ResearchArtifactModel, version.artifact_id)
        assert artifact is not None
        assert artifact.kind == "paper_collection"
        assert artifact.latest_version_id == version.id
        assert artifact.logical_key.endswith(domain_contract.id)

        producers = tuple(
            session.scalars(
                select(ProducerExecutionModel).where(
                    ProducerExecutionModel.run_id == run.id
                )
            )
        )
        assert len(producers) == 1
        producer = producers[0]
        assert producer.step_key == "searching_papers"
        assert producer.step_attempt_id == attempt.attempt_id
        assert producer.status == "completed"
        assert producer.output_hash == version.content_hash

        snapshots = tuple(
            session.scalars(
                select(SourceSnapshotModel).where(
                    SourceSnapshotModel.project_id == project_id
                )
            )
        )
        assert len(snapshots) == 1
        snapshot = snapshots[0]
        assert snapshot.source_id == "crossref"
        assert snapshot.source_type == "paper_metadata"
        assert str(snapshot.id) in set(version.source_snapshot_ids)

        evidence = tuple(
            session.scalars(
                select(EvidenceModel).where(
                    EvidenceModel.artifact_version_id == version.id
                )
            )
        )
        assert len(evidence) == 1
        assert evidence[0].target_type == "paper_candidate"
        assert evidence[0].evidence_type == "paper_metadata"
        assert evidence[0].source_snapshot_id == snapshot.id
        assert evidence[0].id in {UUID(item) for item in version.evidence_ids}

        run_row = session.get(ResearchRunModel, run.id)
        step = session.scalar(
            select(RunStepModel).where(
                RunStepModel.run_id == run.id,
                RunStepModel.key == "searching_papers",
            )
        )
        active_attempt = session.get(StepAttemptModel, attempt.attempt_id)
        assert run_row is not None and run_row.status == "completed"
        assert step is not None and step.status == "completed"
        assert active_attempt is not None and active_attempt.status == "completed"

        events = tuple(
            session.scalars(
                select(RunEventModel)
                .where(RunEventModel.run_id == run.id)
                .order_by(RunEventModel.sequence)
            )
        )
        assert events[-1].event_type == "run.completed"
        assert any(
            event.event_type == "step.completed"
            and str(version.id) in event.artifact_version_ids
            for event in events
        )

        # The astronomy data authority remains separate from the paper source
        # actually acquired and persisted by this runtime.
        assert domain_contract.source_scope.allowed_sources == (
            "nasa_exoplanet_archive",
        )
        assert domain_contract.paper_search_scope.source_ids == ("crossref",)
        assert {item.source_id for item in snapshots} == {"crossref"}


class _FailingPublisher(ArtifactPublisher):
    def _before_commit(self, session) -> None:  # type: ignore[no-untyped-def]
        raise RuntimeError("forced paper publication rollback")


def test_paper_publication_rollback_leaves_no_version_or_latest_pointer(
    postgres_engine: Engine,
) -> None:
    factory = session_factory(postgres_engine)
    project_id = uuid4()
    domain_contract, run, lease, attempt = _active_paper_run(
        factory,
        project_id=project_id,
        contract=_contract(project_id),
    )
    publication = _prepare_publication(
        factory,
        project_id=project_id,
        contract=domain_contract,
        attempt=attempt,
        lease=lease,
    )

    with pytest.raises(RuntimeError, match="forced paper publication rollback"):
        _FailingPublisher(factory).publish_step_outputs(
            run.id,
            step_key="searching_papers",
            attempt_id=attempt.attempt_id,
            token=lease.token,
            generation=lease.generation,
            expected_status=attempt.run_status,
            expected_revision=attempt.run_revision,
            publications=(publication,),
            public_message="不应提交",
        )

    with factory() as session:
        assert (
            session.scalar(
                select(func.count(ArtifactVersionModel.id)).where(
                    ArtifactVersionModel.project_id == project_id
                )
            )
            == 0
        )
        assert (
            session.scalar(
                select(func.count(EvidenceModel.id)).where(
                    EvidenceModel.project_id == project_id
                )
            )
            == 0
        )
        artifact = session.scalar(
            select(ResearchArtifactModel).where(
                ResearchArtifactModel.project_id == project_id
            )
        )
        assert artifact is not None and artifact.latest_version_id is None

        # Runtime audit rows and the immutable SourceSnapshot were created
        # before the Publisher transaction; the failed Publisher leaves no
        # half-written version, Evidence, or latest pointer.
        assert (
            session.scalar(
                select(func.count(SourceSnapshotModel.id)).where(
                    SourceSnapshotModel.project_id == project_id
                )
            )
            == 1
        )
        producer = session.scalar(
            select(ProducerExecutionModel).where(
                ProducerExecutionModel.run_id == run.id
            )
        )
        assert producer is not None and producer.status == "completed"

        run_row = session.get(ResearchRunModel, run.id)
        step = session.scalar(
            select(RunStepModel).where(
                RunStepModel.run_id == run.id,
                RunStepModel.key == "searching_papers",
            )
        )
        active_attempt = session.get(StepAttemptModel, attempt.attempt_id)
        assert run_row is not None and run_row.status == "searching_papers"
        assert step is not None and step.status == "running"
        assert active_attempt is not None and active_attempt.status == "running"
        assert not session.scalar(
            select(func.count(RunEventModel.id)).where(
                RunEventModel.run_id == run.id,
                RunEventModel.event_type == "step.completed",
                RunEventModel.step_key == "searching_papers",
            )
        )


def test_astronomy_data_source_is_not_used_as_paper_source(
    postgres_engine: Engine,
) -> None:
    factory = session_factory(postgres_engine)
    project_id = uuid4()
    contract = _contract(project_id).model_copy(
        update={
            "paper_search_scope": PaperSearchScope(
                keywords=("transiting exoplanet",),
                source_ids=("nasa_exoplanet_archive",),
                max_candidates=2,
            )
        }
    )
    domain_contract, run, lease, attempt = _active_paper_run(
        factory,
        project_id=project_id,
        contract=contract,
    )

    with pytest.raises(ValueError, match="not configured"):
        _prepare_publication(
            factory,
            project_id=project_id,
            contract=domain_contract,
            attempt=attempt,
            lease=lease,
        )

    with factory() as session:
        assert (
            session.scalar(
                select(func.count(ProducerExecutionModel.id)).where(
                    ProducerExecutionModel.run_id == run.id
                )
            )
            == 0
        )
        assert (
            session.scalar(
                select(func.count(SourceSnapshotModel.id)).where(
                    SourceSnapshotModel.project_id == project_id
                )
            )
            == 0
        )
