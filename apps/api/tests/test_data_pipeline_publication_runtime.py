"""PostgreSQL and pure admission proof for the live Data Pipeline bridge."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import os
from pathlib import Path
from uuid import UUID, uuid4

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
    RunStepModel,
    StepAttemptModel,
    SourceSnapshotModel,
)
from app.db.session import create_engine_from_url, session_factory
from app.schemas.core import ResearchContract, compute_research_contract_content_hash
from app.schemas.crossmatch import CrossmatchSourceInput
from app.schemas.enums import SourceMode
from app.schemas.manifest import ManifestBundle
from app.schemas.source_acquisition import DataSourceDataLevel
from app.workflow.data_pipeline_publication_runtime import (
    DataPipelinePublicationRuntime,
)
from app.workflow.data_pipeline_runtime import (
    DataPipelineAcquisitionPort,
    DataPipelineRunInput,
    DataPipelineRuntime,
)
from app.workflow.publisher import (
    ArtifactPublisher,
    admit_artifact_candidate,
)
from app.workflow.store import PersistentWorkflowStore, RunStepDefinition
from authoring_test_support import (
    build_contract_draft,
    build_research_contract,
    build_research_project,
    persist_authoring_models,
)
from data_artifact_test_support import build_input
from services.data_pipeline.data_artifacts.admission import (
    validate_data_artifact_domain,
    validate_data_artifact_evidence,
)
from services.data_pipeline.data_quality import build_data_quality_publication_validator
from services.data_pipeline.manifest import load_frozen_manifest_bundle


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


class _LiveAcquisition(DataPipelineAcquisitionPort):
    def __init__(
        self,
        acquisitions: tuple[CrossmatchSourceInput, CrossmatchSourceInput],
    ) -> None:
        self._acquisitions = acquisitions

    def discover_nearby_confirmed_tic_ids(self) -> tuple[str, ...]:
        return ("307210830",)

    def acquire(
        self,
        *,
        manifests: ManifestBundle,
        tic_ids: tuple[str, ...],
    ) -> tuple[CrossmatchSourceInput, CrossmatchSourceInput]:
        assert manifests.case_manifest.case_id and tic_ids == ("307210830",)
        return self._acquisitions


def _live(value: CrossmatchSourceInput) -> CrossmatchSourceInput:
    metadata = {
        **value.snapshot.request_metadata,
        "source_mode": SourceMode.live.value,
        "data_level": DataSourceDataLevel.live_result.value,
    }
    return CrossmatchSourceInput.model_validate(
        {
            **value.model_dump(mode="json"),
            "source_mode": SourceMode.live.value,
            "data_level": DataSourceDataLevel.live_result.value,
            "snapshot": {
                **value.snapshot.model_dump(mode="json"),
                "request_metadata": metadata,
            },
        }
    )


def _contract(project_id: str) -> ResearchContract:
    payload = {
        "id": str(uuid4()),
        "project_id": project_id,
        "version": 1,
        "research_goal": "构建近邻已确认系外行星证据数据集",
        "target_objects": ["exoplanet_candidate", "host_star"],
        "data_requirements": {"unit_policy": "canonical"},
        "requested_fields": ["star.tic_id"],
        "source_scope": {"allowed_sources": ["nasa_exoplanet_archive"]},
        "paper_search_scope": {"max_candidates": 20},
        "output_requirements": ["dataset"],
        "evidence_requirements": {
            "require_locator": True,
            "require_source_snapshot": True,
            "minimum_coverage": 1.0,
        },
        "quality_constraints": {
            "source_completeness_min": 1.0,
            "unit_consistency_min": 1.0,
        },
        "created_from_draft_id": str(uuid4()),
        "created_at": datetime(2026, 8, 14, tzinfo=UTC),
        "content_hash": "sha256:" + "0" * 64,
    }
    payload["content_hash"] = compute_research_contract_content_hash(payload)
    return ResearchContract.model_validate(payload)


def _alembic_config(url: str) -> Config:
    root = Path(__file__).resolve().parents[1]
    config = Config(root / "alembic.ini")
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


@pytest.fixture(scope="module")
def postgres_engine() -> Engine:
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL is not configured")
    assert "test" in TEST_DATABASE_URL.rsplit("/", 1)[-1].lower(), (
        "refusing non-test database"
    )
    config = _alembic_config(TEST_DATABASE_URL)
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    engine = create_engine_from_url(TEST_DATABASE_URL)
    yield engine
    engine.dispose()
    command.downgrade(config, "base")
    command.upgrade(config, "head")


def _prepared_bundle() -> tuple[ResearchContract, object]:
    project_id = uuid4()
    contract = _contract(str(project_id))
    source_input = build_input("star.tic_id")
    acquisitions = (
        _live(source_input.left_acquisition),
        _live(source_input.right_acquisition),
    )
    prepared = DataPipelineRuntime(
        load_frozen_manifest_bundle(), acquisition=_LiveAcquisition(acquisitions)
    ).prepare(
        DataPipelineRunInput(
            project_id=project_id,
            run_id=uuid4(),
            step_key="cleaning_data",
            contract=contract,
            acquisitions=acquisitions,
        )
    )
    return contract, prepared


def test_data_bundle_admission_reuses_shared_provenance_facts() -> None:
    _, prepared = _prepared_bundle()
    admitted = {}
    for item in prepared.artifacts:
        validator = build_data_quality_publication_validator(
            prepared.quality,
            candidate_kind=item.kind,
        )
        admitted[item.kind] = admit_artifact_candidate(
            item.candidate,
            schema_version=item.candidate.schema_version,
            source_snapshot_ids=item.candidate.source_snapshot_ids,
            evidence_ids=item.candidate.evidence_ids,
            evidence_validator=validate_data_artifact_evidence,
            domain_validator=validate_data_artifact_domain,
            quality_validator=validator,
            source_snapshot_bindings=item.source_snapshot_bindings,
            evidence_bindings=item.evidence_bindings,
            data_provenance_candidate=(
                None if item.kind == "dataset" else prepared.dataset
            ),
        )

    assert set(admitted) == {"dataset", "field_dictionary", "source_collection"}
    dataset_snapshots = {
        item.pipeline_source_snapshot_id: (
            item.source_id,
            item.query_hash,
            item.content_hash,
        )
        for item in admitted["dataset"].data_source_snapshot_materializations
    }
    dataset_evidence = {
        item.pipeline_evidence_id: (
            item.pipeline_source_snapshot_id,
            item.target_type,
            item.target_id,
            item.evidence_type,
            item.locator_json,
            item.quote_or_value_json,
        )
        for item in admitted["dataset"].data_evidence_materializations
    }
    persisted_evidence_ids: set[str] = set()
    for candidate in admitted.values():
        assert {
            item.pipeline_source_snapshot_id: (
                item.source_id,
                item.query_hash,
                item.content_hash,
            )
            for item in candidate.data_source_snapshot_materializations
        } == dataset_snapshots
        assert {
            item.pipeline_evidence_id: (
                item.pipeline_source_snapshot_id,
                item.target_type,
                item.target_id,
                item.evidence_type,
                item.locator_json,
                item.quote_or_value_json,
            )
            for item in candidate.data_evidence_materializations
        } == dataset_evidence
        for item in candidate.data_evidence_materializations:
            assert item.persisted_evidence_id not in persisted_evidence_ids
            persisted_evidence_ids.add(item.persisted_evidence_id)


def _active_data_run(factory, *, project_id: UUID, contract: ResearchContract):
    project = build_research_project(
        project_id=project_id,
        session_id=f"session-{uuid4()}",
        name="Data Pipeline integration",
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
            "id": str(persisted_contract.id),
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
    run = workflow.create_run(
        project_id=project.id,
        contract_id=persisted_contract.id,
        execution_mode="live",
        idempotency_key=f"data-run-{uuid4()}",
        request_hash="sha256:" + "b" * 64,
        steps=(
            RunStepDefinition(
                key="planning",
                label="Planning",
                enter_status="planning",
                success_status="cleaning_data",
            ),
            RunStepDefinition(
                key="cleaning_data",
                label="Cleaning data",
                enter_status="cleaning_data",
                success_status="completed",
                depends_on_step_keys=("planning",),
            ),
        ),
    )
    lease = workflow.acquire_lease(
        run.id,
        owner="data-pipeline-test",
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
        step_key="cleaning_data",
        attempt_idempotency_key=f"cleaning-{uuid4()}",
        token=lease.token,
        generation=lease.generation,
        expected_status=planning.status,
        expected_revision=planning.revision,
        public_message="正在处理实时数据",
    )
    return domain_contract, run, lease, attempt


def _live_pipeline() -> DataPipelineRuntime:
    source_input = build_input("star.tic_id")
    acquisitions = (
        _live(source_input.left_acquisition),
        _live(source_input.right_acquisition),
    )
    return DataPipelineRuntime(
        load_frozen_manifest_bundle(), acquisition=_LiveAcquisition(acquisitions)
    )


def _prepare_publications(factory, *, contract, attempt, lease):
    return DataPipelinePublicationRuntime(
        session_factory=factory,
        pipeline=_live_pipeline(),
    ).prepare_publications(
        contract=contract,
        step_key="cleaning_data",
        attempt=attempt,
        lease=lease,
    )


def test_data_pipeline_publishes_three_artifacts_with_shared_live_facts(
    postgres_engine: Engine,
) -> None:
    factory = session_factory(postgres_engine)
    project_id = uuid4()
    domain_contract, run, lease, attempt = _active_data_run(
        factory,
        project_id=project_id,
        contract=_contract(str(project_id)),
    )
    publications = _prepare_publications(
        factory, contract=domain_contract, attempt=attempt, lease=lease
    )
    assert {publication.candidate.content["kind"] for publication in publications} == {
        "dataset",
        "field_dictionary",
        "source_collection",
    }
    result = ArtifactPublisher(factory).publish_step_outputs(
        run.id,
        step_key="cleaning_data",
        attempt_id=attempt.attempt_id,
        token=lease.token,
        generation=lease.generation,
        expected_status=attempt.run_status,
        expected_revision=attempt.run_revision,
        publications=publications,
        public_message="实时数据三产物已发布",
    )

    assert result.status == "completed"
    assert len(result.versions) == 3
    with factory() as session:
        versions = tuple(
            session.scalars(
                select(ArtifactVersionModel)
                .where(ArtifactVersionModel.id.in_(item.id for item in result.versions))
                .order_by(ArtifactVersionModel.id)
            )
        )
        assert {version.content["kind"] for version in versions} == {
            "dataset",
            "field_dictionary",
            "source_collection",
        }
        assert {tuple(version.source_snapshot_ids) for version in versions}
        assert len({tuple(version.source_snapshot_ids) for version in versions}) == 1
        for version in versions:
            assert version.source_mode == "live"
            producer = session.get(
                ProducerExecutionModel, version.producer_execution_id
            )
            assert producer is not None
            assert producer.status == "completed"
            assert producer.output_hash == version.content_hash
            assert (
                session.scalar(
                    select(ResearchArtifactModel.latest_version_id).where(
                        ResearchArtifactModel.id == version.artifact_id
                    )
                )
                == version.id
            )
            evidence = tuple(
                session.scalars(
                    select(EvidenceModel).where(
                        EvidenceModel.artifact_version_id == version.id
                    )
                )
            )
            assert evidence
            assert {str(item.source_snapshot_id) for item in evidence} <= set(
                version.source_snapshot_ids
            )
        assert (
            session.scalar(
                select(func.count(SourceSnapshotModel.id)).where(
                    SourceSnapshotModel.project_id == run.project_id
                )
            )
            == 2
        )
        assert (
            session.scalar(
                select(func.count(ProducerExecutionModel.id)).where(
                    ProducerExecutionModel.run_id == run.id
                )
            )
            == 4
        )
        assert (
            session.scalar(
                select(func.count(EvidenceModel.id)).where(
                    EvidenceModel.project_id == run.project_id
                )
            )
            > 0
        )


class _FailingPublisher(ArtifactPublisher):
    def _before_commit(self, session) -> None:
        raise RuntimeError("forced publication rollback")


def test_data_pipeline_publication_rolls_back_all_latest_pointers(
    postgres_engine: Engine,
) -> None:
    factory = session_factory(postgres_engine)
    project_id = uuid4()
    domain_contract, run, lease, attempt = _active_data_run(
        factory,
        project_id=project_id,
        contract=_contract(str(project_id)),
    )
    publications = _prepare_publications(
        factory, contract=domain_contract, attempt=attempt, lease=lease
    )

    with pytest.raises(RuntimeError, match="forced publication rollback"):
        _FailingPublisher(factory).publish_step_outputs(
            run.id,
            step_key="cleaning_data",
            attempt_id=attempt.attempt_id,
            token=lease.token,
            generation=lease.generation,
            expected_status=attempt.run_status,
            expected_revision=attempt.run_revision,
            publications=publications,
            public_message="不应提交",
        )

    with factory() as session:
        project_version_ids = select(ArtifactVersionModel.id).where(
            ArtifactVersionModel.project_id == run.project_id
        )
        assert session.scalar(
            select(func.count(ArtifactVersionModel.id)).where(
                ArtifactVersionModel.project_id == run.project_id
            )
        ) == 0
        assert session.scalar(
            select(func.count(EvidenceModel.id)).where(
                EvidenceModel.artifact_version_id.in_(project_version_ids)
            )
        ) == 0
        artifacts = tuple(
            session.scalars(
                select(ResearchArtifactModel).where(
                    ResearchArtifactModel.project_id == run.project_id
                )
            )
        )
        assert len(artifacts) == 3
        assert all(artifact.latest_version_id is None for artifact in artifacts)
        active_run = session.get(ResearchRunModel, run.id)
        assert active_run is not None and active_run.status == "cleaning_data"
        step = session.scalar(
            select(RunStepModel).where(
                RunStepModel.run_id == run.id,
                RunStepModel.key == "cleaning_data",
            )
        )
        assert step is not None and step.status == "running"
        active_attempt = session.get(StepAttemptModel, attempt.attempt_id)
        assert active_attempt is not None and active_attempt.status == "running"
        # Source snapshots and producer rows are audit records created before
        # the publication transaction; no half-written version/latest pointer
        # remains after the publisher rollback.
        assert (
            session.scalar(
                select(func.count(SourceSnapshotModel.id)).where(
                    SourceSnapshotModel.project_id == run.project_id
                )
            )
            == 2
        )
        assert (
            session.scalar(
                select(func.count(ProducerExecutionModel.id)).where(
                    ProducerExecutionModel.run_id == run.id
                )
            )
            == 4
        )
