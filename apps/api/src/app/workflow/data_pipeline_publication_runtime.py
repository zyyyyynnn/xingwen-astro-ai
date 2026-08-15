"""Workflow-owned bridge for atomic publication of live Data Artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    ArtifactVersionModel,
    ResearchArtifactModel,
    SourceSnapshotModel,
)
from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.core import ResearchContract
from app.schemas.enums import SourceMode
from app.schemas.source_acquisition import DataSourceDataLevel
from app.workflow.data_pipeline_runtime import (
    DataPipelinePreparedArtifact,
    DataPipelinePreparedResult,
    DataPipelineRunInput,
    DataPipelineRuntime,
)
from app.workflow.publisher import (
    ArtifactPublication,
    ProducerExecutionRequest,
    ProducerExecutionStore,
    PublicationAdmissionError,
    admit_artifact_candidate,
)
from app.workflow.store import AttemptHandle, LeaseGrant
from services.data_pipeline.data_artifacts.admission import (
    validate_data_artifact_domain,
    validate_data_artifact_evidence,
)
from services.data_pipeline.data_quality import build_data_quality_publication_validator


@dataclass(frozen=True, slots=True)
class _ArtifactTarget:
    kind: str
    artifact_id: UUID
    publication_key: str
    supersedes_version_id: UUID | None


class DataPipelinePublicationRuntime:
    """Prepare the complete Dataset/FieldDictionary/SourceCollection set.

    The data runtime owns external acquisition and deterministic scientific
    derivation. This bridge owns only workflow-facing producer lifecycles,
    shared live SourceSnapshot persistence, and construction of the three
    publisher-ready outputs. It never advances RunStep or Run state; the
    caller hands the returned tuple to ``ArtifactPublisher`` which commits all
    versions and latest pointers in one transaction.
    """

    _KINDS = ("dataset", "field_dictionary", "source_collection")

    def __init__(
        self,
        *,
        session_factory: Callable[[], Session],
        pipeline: DataPipelineRuntime,
    ) -> None:
        self._session_factory = session_factory
        self._pipeline = pipeline
        self._producers = ProducerExecutionStore(session_factory)

    def prepare_publications(
        self,
        *,
        contract: ResearchContract,
        step_key: str,
        attempt: AttemptHandle,
        lease: LeaseGrant,
    ) -> tuple[ArtifactPublication, ...]:
        """Return three publications backed by one live provenance registry."""

        if step_key != "cleaning_data":
            raise ValueError("Data Pipeline publication belongs to cleaning_data")

        acquisition_input_hash = compute_canonical_payload_hash(
            {
                "contract_id": contract.id,
                "contract_version": contract.version,
                "contract_content_hash": contract.content_hash,
                "policy_id": "nearby-confirmed-tic-cross-source-v1",
            }
        )
        acquisition_execution = self._producers.start_producer_execution(
            ProducerExecutionRequest(
                run_id=attempt.run_id,
                step_key=step_key,
                attempt_id=attempt.attempt_id,
                idempotency_key=f"data-acquisition:attempt:{attempt.attempt_number}",
                producer_type="pipeline",
                producer_name="nasa_cross_source_acquisition",
                producer_version="1.0.0",
                input_hash=acquisition_input_hash,
                parameters={
                    "confirmed_only": True,
                    "default_only": True,
                    "max_distance_parsecs": 20,
                },
            ),
            token=lease.token,
            generation=lease.generation,
            expected_status=attempt.run_status,
            expected_revision=attempt.run_revision,
        )

        try:
            prepared = self._pipeline.prepare(
                DataPipelineRunInput(
                    project_id=UUID(contract.project_id),
                    run_id=attempt.run_id,
                    step_key=step_key,
                    contract=contract,
                )
            )
            _require_live_acquisitions(prepared)
            _require_prepared_bundle(
                prepared,
                contract=contract,
                run_id=attempt.run_id,
                step_key=step_key,
            )
        except Exception:
            self._producers.finish_producer_execution(
                acquisition_execution.id,
                status="failed",
                error_code="DATA_ACQUISITION_FAILED",
            )
            raise

        acquisition_output_hash = compute_canonical_payload_hash(
            [
                item.model_dump(mode="json", exclude_none=True)
                for item in prepared.acquisitions
            ]
        )
        self._producers.finish_producer_execution(
            acquisition_execution.id,
            status="completed",
            output_hash=acquisition_output_hash,
        )

        admitted_by_kind = {
            item.kind: _admit_data_artifact(prepared, item)
            for item in _ordered_prepared_artifacts(prepared)
        }
        # Materialize shared facts before producer rows are closed. Any
        # conflict aborts before a candidate can reach the Publisher.
        self._persist_source_snapshots(prepared)
        targets = self._ensure_artifact_targets(
            contract=contract,
            input_hash=prepared.data_input.input_hash,
            step_key=step_key,
        )

        publications: list[ArtifactPublication] = []
        for kind in self._KINDS:
            candidate = admitted_by_kind[kind]
            assembly_execution = self._producers.start_producer_execution(
                ProducerExecutionRequest(
                    run_id=attempt.run_id,
                    step_key=step_key,
                    attempt_id=attempt.attempt_id,
                    idempotency_key=(
                        f"data-assembly:{kind}:attempt:{attempt.attempt_number}"
                    ),
                    producer_type="pipeline",
                    producer_name="data_artifact_pipeline",
                    producer_version="1.0.0",
                    input_hash=candidate.content["input_hash"],
                    parameters={
                        "artifact_kind": kind,
                        "quality_gate": "required",
                    },
                ),
                token=lease.token,
                generation=lease.generation,
                expected_status=attempt.run_status,
                expected_revision=attempt.run_revision,
            )
            self._producers.finish_producer_execution(
                assembly_execution.id,
                status="completed",
                output_hash=candidate.content_hash,
            )
            target = targets[kind]
            publications.append(
                ArtifactPublication(
                    artifact_id=target.artifact_id,
                    publication_key=target.publication_key,
                    producer_execution_id=assembly_execution.id,
                    candidate=candidate,
                    source_mode="live",
                    supersedes_version_id=target.supersedes_version_id,
                )
            )
        return tuple(publications)

    def _persist_source_snapshots(self, prepared: DataPipelinePreparedResult) -> None:
        artifacts = _ordered_prepared_artifacts(prepared)
        reference_bindings = tuple(
            (
                item.pipeline_source_snapshot_id,
                item.persisted_source_snapshot_id,
            )
            for item in artifacts[0].source_snapshot_bindings
        )
        if any(
            tuple(
                (
                    item.pipeline_source_snapshot_id,
                    item.persisted_source_snapshot_id,
                )
                for item in artifact.source_snapshot_bindings
            )
            != reference_bindings
            for artifact in artifacts[1:]
        ):
            raise PublicationAdmissionError(
                "Data Artifact candidates must share one persisted SourceSnapshot registry"
            )

        persisted_by_pipeline = {
            pipeline_id: UUID(persisted_id)
            for pipeline_id, persisted_id in reference_bindings
        }
        sources = {
            item.snapshot.snapshot_id: item.snapshot for item in prepared.acquisitions
        }
        if set(sources) != set(persisted_by_pipeline):
            raise PublicationAdmissionError(
                "Live Data Pipeline snapshot bindings do not close the acquisition set"
            )
        with self._session_factory() as session, session.begin():
            for pipeline_id, source in sources.items():
                persisted_id = persisted_by_pipeline[pipeline_id]
                existing = session.get(SourceSnapshotModel, persisted_id)
                expected = {
                    "project_id": prepared.project_id,
                    "source_id": source.source_id,
                    "source_type": source.source_type,
                    "retrieved_at": source.retrieved_at,
                    "query": source.query,
                    "query_hash": source.query_hash,
                    "source_version_or_etag": source.source_version_or_etag,
                    "content_hash": source.content_hash,
                    "license_note": source.license_note,
                    "cache_version": source.cache_version,
                    "request_metadata": source.request_metadata,
                }
                if existing is None:
                    session.add(SourceSnapshotModel(id=persisted_id, **expected))
                    continue
                if any(
                    getattr(existing, key) != value for key, value in expected.items()
                ):
                    raise PublicationAdmissionError(
                        "Persisted live SourceSnapshot identity has conflicting metadata"
                    )

    def _ensure_artifact_targets(
        self,
        *,
        contract: ResearchContract,
        input_hash: str,
        step_key: str,
    ) -> dict[str, _ArtifactTarget]:
        project_id = UUID(contract.project_id)
        titles = {
            "dataset": "研究数据集",
            "field_dictionary": "字段字典",
            "source_collection": "来源集合",
        }
        targets: dict[str, _ArtifactTarget] = {}
        with self._session_factory() as session, session.begin():
            for kind in self._KINDS:
                logical_key = f"data.{kind}.{contract.id}"
                artifact_id = uuid5(
                    NAMESPACE_URL, f"xingwen:{project_id}:{logical_key}"
                )
                publication_key = str(
                    uuid5(
                        NAMESPACE_URL,
                        f"xingwen:{project_id}:{step_key}:{logical_key}:{input_hash}",
                    )
                )
                artifact = session.get(ResearchArtifactModel, artifact_id)
                if artifact is None:
                    artifact = ResearchArtifactModel(
                        id=artifact_id,
                        project_id=project_id,
                        kind=kind,
                        title=titles[kind],
                        logical_key=logical_key,
                    )
                    session.add(artifact)
                    session.flush()
                elif (
                    artifact.project_id != project_id
                    or artifact.kind != kind
                    or artifact.logical_key != logical_key
                ):
                    raise PublicationAdmissionError(
                        "Data Artifact ResearchArtifact identity was reused with another meaning"
                    )
                existing = session.scalar(
                    select(ArtifactVersionModel).where(
                        ArtifactVersionModel.artifact_id == artifact.id,
                        ArtifactVersionModel.publication_key == publication_key,
                    )
                )
                targets[kind] = _ArtifactTarget(
                    kind=kind,
                    artifact_id=artifact.id,
                    publication_key=publication_key,
                    supersedes_version_id=(
                        existing.supersedes_version_id
                        if existing is not None
                        else artifact.latest_version_id
                    ),
                )
        return targets


def _ordered_prepared_artifacts(
    prepared: DataPipelinePreparedResult,
) -> tuple[DataPipelinePreparedArtifact, ...]:
    by_kind = {item.kind: item for item in prepared.artifacts}
    if set(by_kind) != set(DataPipelinePublicationRuntime._KINDS) or len(
        by_kind
    ) != len(prepared.artifacts):
        raise PublicationAdmissionError(
            "Data Pipeline preparation must contain exactly one candidate per artifact kind"
        )
    expected_candidates = {
        "dataset": prepared.dataset,
        "field_dictionary": prepared.field_dictionary,
        "source_collection": prepared.source_collection,
    }
    if any(
        by_kind[kind].candidate is not expected_candidates[kind] for kind in by_kind
    ):
        raise PublicationAdmissionError(
            "Data Pipeline preparation contains a candidate detached from its build bundle"
        )
    return tuple(by_kind[kind] for kind in DataPipelinePublicationRuntime._KINDS)


def _admit_data_artifact(
    prepared: DataPipelinePreparedResult,
    artifact: DataPipelinePreparedArtifact,
):
    quality_validator = build_data_quality_publication_validator(
        prepared.quality,
        candidate_kind=artifact.kind,
    )
    return admit_artifact_candidate(
        artifact.candidate,
        schema_version=artifact.candidate.schema_version,
        source_snapshot_ids=artifact.candidate.source_snapshot_ids,
        evidence_ids=artifact.candidate.evidence_ids,
        evidence_validator=validate_data_artifact_evidence,
        domain_validator=validate_data_artifact_domain,
        quality_validator=quality_validator,
        source_snapshot_bindings=artifact.source_snapshot_bindings,
        evidence_bindings=artifact.evidence_bindings,
        data_provenance_candidate=(
            None if artifact.kind == "dataset" else prepared.dataset
        ),
    )


def _require_prepared_bundle(
    prepared: DataPipelinePreparedResult,
    *,
    contract: ResearchContract,
    run_id: UUID,
    step_key: str,
) -> None:
    if (
        prepared.project_id != UUID(contract.project_id)
        or prepared.run_id != run_id
        or prepared.step_key != step_key
    ):
        raise PublicationAdmissionError(
            "Data Pipeline preparation is not owned by the active contract/step"
        )


def _require_live_acquisitions(prepared: DataPipelinePreparedResult) -> None:
    if any(
        item.source_mode is not SourceMode.live
        or item.data_level is not DataSourceDataLevel.live_result
        for item in prepared.acquisitions
    ):
        raise ValueError(
            "Data Pipeline publication requires real live source acquisitions"
        )


__all__ = ["DataPipelinePublicationRuntime"]
