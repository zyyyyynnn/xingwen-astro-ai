"""Trusted application adapter for immutable evidence-graph inputs."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import EvidenceModel
from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.core import (
    ArtifactVersionDetail,
    EvidenceDetail,
    EvidenceRead,
    ResearchArtifactDetail,
    SourceSnapshotDetail,
)
from app.schemas.data_artifacts import (
    DatasetArtifactCandidate,
    FieldDictionaryArtifactCandidate,
)
from app.schemas.data_quality import DataQualityProjection
from app.schemas.graph_artifact import GraphIntegrityStage, GraphRejectionReason
from app.schemas.literature_relation import LiteratureRelationsCandidate
from app.security import SecurityProblem
from app.services.artifacts import ArtifactReadService
from services.graph_pipeline.ports import (
    EvidenceRestrictionFact,
    EvidenceRestrictionReadPort,
    GraphInputIntegrityError,
    GraphInputVersionSelection,
    PersistedEvidenceBinding,
    PersistedSourceSnapshotBinding,
    PipelineEvidenceBindingReadPort,
    PublishedArtifactVersionPins,
    PublishedDataGraphInputs,
    PublishedDatasetVersion,
    PublishedFieldDictionaryVersion,
    PublishedGraphInputs,
    PublishedLiteratureRelationsVersion,
    StoredPipelineEvidenceBinding,
    graph_input_security_error,
)


_Candidate = TypeVar(
    "_Candidate",
    DatasetArtifactCandidate,
    FieldDictionaryArtifactCandidate,
    LiteratureRelationsCandidate,
)


class DatabaseEvidenceRestrictionReadAdapter:
    """Resolve exact persisted restriction flags for graph publication gates."""

    def __init__(self, factory: Callable[[], Session]) -> None:
        self._factory = factory

    def read_restrictions(
        self,
        *,
        project_id: str,
        evidence_ids: tuple[str, ...],
    ) -> tuple[EvidenceRestrictionFact, ...]:
        try:
            project_uuid = UUID(project_id)
            requested = tuple(UUID(value) for value in evidence_ids)
        except (AttributeError, TypeError, ValueError) as exc:
            raise SecurityProblem(
                status=404,
                code="EVIDENCE_NOT_FOUND",
                title="Evidence not found",
                detail="The requested Evidence closure was not found",
            ) from exc
        if len(requested) != len(set(requested)):
            raise SecurityProblem(
                status=409,
                code="EVIDENCE_CLOSURE_INVALID",
                title="Evidence closure invalid",
                detail="The graph Evidence selection contains duplicate identities",
            )
        with self._factory() as session:
            rows = tuple(
                session.execute(
                    select(
                        EvidenceModel.id,
                        EvidenceModel.project_id,
                        EvidenceModel.is_restricted,
                    ).where(
                        EvidenceModel.project_id == project_uuid,
                        EvidenceModel.id.in_(requested),
                    )
                ).all()
            )
        return tuple(
            EvidenceRestrictionFact(
                evidence_id=str(row.id),
                project_id=str(row.project_id),
                is_restricted=row.is_restricted,
            )
            for row in sorted(rows, key=lambda value: value.id)
        )


def _schema_error(message: str, *, path: str) -> GraphInputIntegrityError:
    return GraphInputIntegrityError(
        message,
        stage=GraphIntegrityStage.input_schema,
        reason=GraphRejectionReason.schema_invalid,
        path=path,
    )


def _artifact_error(
    message: str,
    *,
    reason: GraphRejectionReason,
    path: str,
) -> GraphInputIntegrityError:
    return GraphInputIntegrityError(
        message,
        stage=GraphIntegrityStage.artifact_version,
        reason=reason,
        path=path,
    )


def _evidence_error(
    message: str,
    *,
    reason: GraphRejectionReason,
    path: str,
) -> GraphInputIntegrityError:
    return GraphInputIntegrityError(
        message,
        stage=GraphIntegrityStage.evidence_snapshot,
        reason=reason,
        path=path,
    )


def _ownership_error(message: str, *, path: str) -> GraphInputIntegrityError:
    return GraphInputIntegrityError(
        message,
        stage=GraphIntegrityStage.ownership,
        reason=GraphRejectionReason.cross_project_ownership,
        path=path,
    )


class ArtifactVersionGraphInputReadAdapter:
    """Read exact ArtifactVersions and close every storage-owned input fact.

    The adapter is session-bound so the existing ArtifactReadService remains
    the Project-ownership gate.  It never asks that service for ``latest`` or
    for a paginated projection.
    """

    def __init__(
        self,
        *,
        artifacts: ArtifactReadService,
        session_id: str,
        evidence_restrictions: EvidenceRestrictionReadPort,
        data_evidence_bindings: PipelineEvidenceBindingReadPort | None = None,
    ) -> None:
        if not isinstance(session_id, str) or not session_id.strip():
            raise _schema_error(
                "session_id must be nonempty text",
                path="input_versions.session_id",
            )
        if not isinstance(evidence_restrictions, EvidenceRestrictionReadPort):
            raise _schema_error(
                "a typed EvidenceRestrictionReadPort is required",
                path="input_versions.evidence.restrictions",
            )
        if data_evidence_bindings is not None and not isinstance(
            data_evidence_bindings,
            PipelineEvidenceBindingReadPort,
        ):
            raise _schema_error(
                "data evidence mapping must use PipelineEvidenceBindingReadPort",
                path="input_versions.data.evidence",
            )
        self._artifacts = artifacts
        self._session_id = session_id.strip()
        self._evidence_restrictions = evidence_restrictions
        self._data_evidence_bindings = data_evidence_bindings

    def read(self, selection: GraphInputVersionSelection) -> PublishedGraphInputs:
        """Resolve only the exact selected versions into a closed typed bundle."""

        if type(selection) is not GraphInputVersionSelection:
            raise _schema_error(
                "selection must be an exact GraphInputVersionSelection",
                path="input_versions",
            )
        literature_version = self._read_version(
            version_id=selection.literature_relations_artifact_version_id,
            project_id=selection.project_id,
            expected_kind="literature_relations",
        )
        literature = self._literature_envelope(literature_version)

        data: PublishedDataGraphInputs | None = None
        if selection.data is not None:
            if self._data_evidence_bindings is None:
                raise _evidence_error(
                    "data graph input requires governed pipeline Evidence mappings",
                    reason=GraphRejectionReason.evidence_missing,
                    path="input_versions.data.evidence",
                )
            dataset_version = self._read_version(
                version_id=selection.data.dataset_artifact_version_id,
                project_id=selection.project_id,
                expected_kind="dataset",
            )
            field_version = self._read_version(
                version_id=selection.data.field_dictionary_artifact_version_id,
                project_id=selection.project_id,
                expected_kind="field_dictionary",
            )
            dataset = self._dataset_envelope(dataset_version)
            data = PublishedDataGraphInputs(
                dataset=dataset,
                field_dictionary=self._field_dictionary_envelope(
                    field_version,
                    semantic_dataset=dataset.candidate,
                ),
            )

        return PublishedGraphInputs(
            selection=selection,
            literature_relations=literature,
            data=data,
        )

    def _read_version(
        self,
        *,
        version_id: str,
        project_id: str,
        expected_kind: str,
    ) -> ArtifactVersionDetail:
        try:
            version = self._artifacts.get_version(
                version_id=version_id,
                session_id=self._session_id,
                full_content=True,
            )
        except SecurityProblem as exc:
            raise graph_input_security_error(
                code=exc.code,
                status=exc.status,
                path=f"input_versions.{version_id}",
            ) from exc
        if type(version) is not ArtifactVersionDetail:
            raise _artifact_error(
                "ArtifactReadService must return ArtifactVersionDetail",
                reason=GraphRejectionReason.input_version_unknown,
                path=f"input_versions.{version_id}",
            )
        try:
            artifact = self._artifacts.get_artifact(
                artifact_id=version.artifact_id,
                session_id=self._session_id,
            )
        except SecurityProblem as exc:
            raise graph_input_security_error(
                code=exc.code,
                status=exc.status,
                path=f"input_versions.{version_id}.artifact",
            ) from exc
        if type(artifact) is not ResearchArtifactDetail:
            raise _artifact_error(
                "ArtifactReadService must return ResearchArtifactDetail",
                reason=GraphRejectionReason.input_version_unknown,
                path=f"input_versions.{version_id}.artifact",
            )
        if version.id != version_id or artifact.id != version.artifact_id:
            raise _artifact_error(
                "selected ArtifactVersion identity disagrees with storage",
                reason=GraphRejectionReason.cross_version_reference,
                path=f"input_versions.{version_id}.artifact_version_id",
            )
        if version.project_id != project_id or artifact.project_id != project_id:
            raise _ownership_error(
                "selected ArtifactVersion belongs to another Project",
                path=f"input_versions.{version_id}.project_id",
            )
        if artifact.kind.value != expected_kind:
            raise _artifact_error(
                "selected ArtifactVersion has the wrong artifact kind",
                reason=GraphRejectionReason.wrong_artifact_kind,
                path=f"input_versions.{version_id}.kind",
            )
        runtime = version.producer_execution
        if (
            runtime.run_id != version.created_by_run_id
            or runtime.producer != version.producer
        ):
            raise _artifact_error(
                "ArtifactVersion producer metadata disagrees with its execution",
                reason=GraphRejectionReason.producer_execution_mismatch,
                path=f"input_versions.{version_id}.producer_execution",
            )
        return version

    def _dataset_envelope(
        self,
        version: ArtifactVersionDetail,
    ) -> PublishedDatasetVersion:
        candidate = _candidate(version, DatasetArtifactCandidate)
        quality = _quality_projection(version)
        sources, evidence = self._data_provenance(version, candidate)
        return PublishedDatasetVersion(
            pins=_pins(version, candidate),
            candidate=candidate,
            quality_projection=quality,
            source_snapshot_bindings=sources,
            evidence_bindings=evidence,
        )

    def _field_dictionary_envelope(
        self,
        version: ArtifactVersionDetail,
        *,
        semantic_dataset: DatasetArtifactCandidate,
    ) -> PublishedFieldDictionaryVersion:
        candidate = _candidate(version, FieldDictionaryArtifactCandidate)
        quality = _quality_projection(version)
        sources, evidence = self._data_provenance(
            version,
            candidate,
            semantic_dataset=semantic_dataset,
        )
        return PublishedFieldDictionaryVersion(
            pins=_pins(version, candidate),
            candidate=candidate,
            quality_projection=quality,
            source_snapshot_bindings=sources,
            evidence_bindings=evidence,
        )

    def _literature_envelope(
        self,
        version: ArtifactVersionDetail,
    ) -> PublishedLiteratureRelationsVersion:
        candidate = _candidate(version, LiteratureRelationsCandidate)
        source_bindings = _literature_source_bindings(version, candidate)
        restrictions = self._restriction_facts(
            project_id=version.project_id,
            evidence_ids=tuple(item.id for item in version.evidence),
        )
        candidate_evidence = {
            item.evidence_id: item for item in candidate.evidence
        }
        evidence_bindings: list[PersistedEvidenceBinding] = []
        for evidence in version.evidence:
            pipeline_id = evidence.locator.get("summary_evidence_id")
            if not isinstance(pipeline_id, str) or pipeline_id not in candidate_evidence:
                raise _evidence_error(
                    "Literature Evidence lacks governed summary_evidence_id mapping",
                    reason=GraphRejectionReason.evidence_inconsistent,
                    path=f"input_versions.{version.id}.evidence.{evidence.id}",
                )
            pipeline_evidence = candidate_evidence[pipeline_id]
            expected_locator = {
                "summary_evidence_id": pipeline_id,
                "source_record_id": pipeline_evidence.source_record_id,
                "paper_summary_locator": pipeline_evidence.locator.model_dump(
                    mode="json", exclude_none=True
                ),
            }
            if evidence.locator != expected_locator:
                raise _evidence_error(
                    "Literature Evidence locator disagrees with the sealed candidate",
                    reason=GraphRejectionReason.evidence_inconsistent,
                    path=f"input_versions.{version.id}.evidence.{evidence.id}.locator",
                )
            evidence_bindings.append(
                PersistedEvidenceBinding(
                    pipeline_evidence_id=pipeline_id,
                    pipeline_evidence_content_hash=compute_canonical_payload_hash(
                        pipeline_evidence.model_dump(
                            mode="json", exclude_none=True
                        )
                    ),
                    pipeline_source_snapshot_id=pipeline_evidence.source_snapshot_id,
                    pipeline_target_type="relation",
                    pipeline_target_id=evidence.target_id,
                    pipeline_locator=expected_locator,
                    evidence=evidence,
                    is_restricted=restrictions[evidence.id].is_restricted,
                )
            )
        return PublishedLiteratureRelationsVersion(
            pins=_pins(version, candidate),
            candidate=candidate,
            source_snapshot_bindings=source_bindings,
            evidence_bindings=tuple(evidence_bindings),
        )

    def _data_provenance(
        self,
        version: ArtifactVersionDetail,
        candidate: DatasetArtifactCandidate | FieldDictionaryArtifactCandidate,
        *,
        semantic_dataset: DatasetArtifactCandidate | None = None,
    ) -> tuple[
        tuple[PersistedSourceSnapshotBinding, ...],
        tuple[PersistedEvidenceBinding, ...],
    ]:
        assert self._data_evidence_bindings is not None
        requested_ids = tuple(sorted(candidate.evidence_ids))
        if semantic_dataset is None:
            if type(candidate) is not DatasetArtifactCandidate:
                raise _artifact_error(
                    "FieldDictionary Evidence requires its paired Dataset semantics",
                    reason=GraphRejectionReason.cross_version_reference,
                    path="input_versions.data.field_dictionary",
                )
            semantic_dataset = candidate
        try:
            resolved = self._data_evidence_bindings.read_bindings(
                project_id=version.project_id,
                artifact_version_id=version.id,
                pipeline_evidence_ids=requested_ids,
            )
        except SecurityProblem as exc:
            raise graph_input_security_error(
                code=exc.code,
                status=exc.status,
                path=f"input_versions.{version.id}.evidence",
            ) from exc
        bindings = _validated_data_mappings(
            resolved,
            artifact_version_id=version.id,
            pipeline_evidence_ids=requested_ids,
            semantic_dataset=semantic_dataset,
        )

        evidence_reads: dict[str, EvidenceRead] = {}
        for binding in bindings:
            try:
                read = self._artifacts.get_evidence(
                    evidence_id=binding.persisted_evidence_id,
                    session_id=self._session_id,
                )
            except SecurityProblem as exc:
                raise graph_input_security_error(
                    code=exc.code,
                    status=exc.status,
                    path=(
                        f"input_versions.{version.id}.evidence."
                        f"{binding.pipeline_evidence_id}"
                    ),
                ) from exc
            if type(read) is not EvidenceRead:
                raise _evidence_error(
                    "ArtifactReadService must return EvidenceRead",
                    reason=GraphRejectionReason.evidence_unknown,
                    path=(
                        f"input_versions.{version.id}.evidence."
                        f"{binding.pipeline_evidence_id}"
                    ),
                )
            if (
                read.id != binding.persisted_evidence_id
                or read.artifact_version_id != version.id
                or read.source_snapshot_id
                != binding.persisted_source_snapshot_id
                or read.source_snapshot.id
                != binding.persisted_source_snapshot_id
                or read.target_type != binding.pipeline_target_type
                or read.target_id != binding.pipeline_target_id
                or read.locator != binding.pipeline_locator
            ):
                raise GraphInputIntegrityError(
                    "governed data Evidence target/locator/Snapshot mapping disagrees with storage",
                    stage=GraphIntegrityStage.evidence_snapshot,
                    reason=GraphRejectionReason.evidence_inconsistent,
                    path=(
                        f"input_versions.{version.id}.evidence."
                        f"{binding.pipeline_evidence_id}"
                    ),
                )
            evidence_reads[read.id] = read

        if {item.id for item in version.evidence} != set(evidence_reads):
            raise _evidence_error(
                "ArtifactVersion Evidence registry and governed mapping differ",
                reason=GraphRejectionReason.evidence_inconsistent,
                path=f"input_versions.{version.id}.evidence",
            )
        version_snapshots = {item.id: item for item in version.source_snapshots}
        source_by_pipeline: dict[str, SourceSnapshotDetail] = {}
        persisted_to_pipeline: dict[str, str] = {}
        for binding in bindings:
            snapshot = evidence_reads[binding.persisted_evidence_id].source_snapshot
            existing = source_by_pipeline.setdefault(
                binding.pipeline_source_snapshot_id,
                snapshot,
            )
            if existing != snapshot:
                raise _evidence_error(
                    "pipeline SourceSnapshot maps to multiple persisted snapshots",
                    reason=GraphRejectionReason.source_snapshot_inconsistent,
                    path=f"input_versions.{version.id}.source_snapshots",
                )
            previous_pipeline = persisted_to_pipeline.setdefault(
                snapshot.id,
                binding.pipeline_source_snapshot_id,
            )
            if previous_pipeline != binding.pipeline_source_snapshot_id:
                raise _evidence_error(
                    "persisted SourceSnapshot maps to multiple pipeline identities",
                    reason=GraphRejectionReason.source_snapshot_inconsistent,
                    path=f"input_versions.{version.id}.source_snapshots",
                )
            if version_snapshots.get(snapshot.id) != snapshot:
                raise _evidence_error(
                    "mapped data SourceSnapshot is absent from ArtifactVersion",
                    reason=GraphRejectionReason.source_snapshot_missing,
                    path=f"input_versions.{version.id}.source_snapshots.{snapshot.id}",
                )
        if set(source_by_pipeline) != set(candidate.source_snapshot_ids):
            raise _evidence_error(
                "data Evidence mappings do not close the candidate snapshots",
                reason=GraphRejectionReason.source_snapshot_inconsistent,
                path=f"input_versions.{version.id}.source_snapshots",
            )

        restrictions = self._restriction_facts(
            project_id=version.project_id,
            evidence_ids=tuple(sorted(evidence_reads)),
        )
        source_bindings = tuple(
            PersistedSourceSnapshotBinding(
                pipeline_source_snapshot_id=pipeline_id,
                source_snapshot=snapshot,
            )
            for pipeline_id, snapshot in source_by_pipeline.items()
        )
        persisted_bindings = tuple(
            PersistedEvidenceBinding(
                pipeline_evidence_id=binding.pipeline_evidence_id,
                pipeline_evidence_content_hash=(
                    binding.pipeline_evidence_content_hash
                ),
                pipeline_source_snapshot_id=binding.pipeline_source_snapshot_id,
                pipeline_target_type=binding.pipeline_target_type,
                pipeline_target_id=binding.pipeline_target_id,
                pipeline_locator=binding.pipeline_locator,
                evidence=_evidence_detail(
                    evidence_reads[binding.persisted_evidence_id]
                ),
                is_restricted=restrictions[
                    binding.persisted_evidence_id
                ].is_restricted,
            )
            for binding in bindings
        )
        return source_bindings, persisted_bindings

    def _restriction_facts(
        self,
        *,
        project_id: str,
        evidence_ids: tuple[str, ...],
    ) -> dict[str, EvidenceRestrictionFact]:
        requested = tuple(sorted(evidence_ids))
        try:
            facts = self._evidence_restrictions.read_restrictions(
                project_id=project_id,
                evidence_ids=requested,
            )
        except SecurityProblem as exc:
            raise graph_input_security_error(
                code=exc.code,
                status=exc.status,
                path="input_versions.evidence.restrictions",
            ) from exc
        if not isinstance(facts, tuple) or any(
            type(item) is not EvidenceRestrictionFact for item in facts
        ):
            raise _schema_error(
                "restriction resolver must return exact typed storage facts",
                path="input_versions.evidence.restrictions",
            )
        by_id = {item.evidence_id: item for item in facts}
        if any(item.project_id != project_id for item in facts):
            raise _ownership_error(
                "restriction facts belong to another Project",
                path="input_versions.evidence.restrictions",
            )
        if len(by_id) != len(facts) or set(by_id) != set(requested):
            raise _evidence_error(
                "restriction facts do not exactly cover persisted Evidence",
                reason=GraphRejectionReason.evidence_inconsistent,
                path="input_versions.evidence.restrictions",
            )
        return by_id


def _candidate(
    version: ArtifactVersionDetail,
    model: type[_Candidate],
) -> _Candidate:
    try:
        candidate = model.model_validate(version.content)
    except ValidationError as exc:
        raise _artifact_error(
            f"published content is not an exact {model.__name__}",
            reason=GraphRejectionReason.unsupported_schema_version,
            path=f"input_versions.{version.id}.content",
        ) from exc
    if type(candidate) is not model:
        raise _artifact_error(
            f"published content is not an exact {model.__name__}",
            reason=GraphRejectionReason.unsupported_schema_version,
            path=f"input_versions.{version.id}.content",
        )
    return candidate


def _quality_projection(version: ArtifactVersionDetail) -> DataQualityProjection:
    if (
        version.quality_projection is None
        or version.quality_projection_hash is None
    ):
        raise _artifact_error(
            "data ArtifactVersion requires a persisted Data Quality Evaluation projection",
            reason=GraphRejectionReason.input_version_unpublished,
            path=f"input_versions.{version.id}.quality_projection",
        )
    try:
        projection = DataQualityProjection.model_validate(
            version.quality_projection
        )
    except ValidationError as exc:
        raise _artifact_error(
            "persisted Data Quality Evaluation projection is not schema-valid",
            reason=GraphRejectionReason.unsupported_schema_version,
            path=f"input_versions.{version.id}.quality_projection",
        ) from exc
    if projection.content_hash != version.quality_projection_hash:
        raise _artifact_error(
            "persisted Data Quality Evaluation projection hash disagrees with ArtifactVersion",
            reason=GraphRejectionReason.content_hash_mismatch,
            path=f"input_versions.{version.id}.quality_projection_hash",
        )
    return projection


def _pins(
    version: ArtifactVersionDetail,
    candidate: DatasetArtifactCandidate
    | FieldDictionaryArtifactCandidate
    | LiteratureRelationsCandidate,
) -> PublishedArtifactVersionPins:
    return PublishedArtifactVersionPins(
        artifact_id=version.artifact_id,
        artifact_version_id=version.id,
        project_id=version.project_id,
        version_number=version.version_number,
        schema_version=version.schema_version,
        content_hash=version.content_hash,
        input_hash=version.input_hash,
        output_hash=candidate.output_hash,
        source_mode=version.source_mode,
        producer_execution=version.producer_execution,
    )


def _literature_source_bindings(
    version: ArtifactVersionDetail,
    candidate: LiteratureRelationsCandidate,
) -> tuple[PersistedSourceSnapshotBinding, ...]:
    references: dict[str, tuple[str, str, str]] = {}
    for evidence in candidate.evidence:
        reference = (
            evidence.source_id,
            evidence.source_snapshot_version,
            evidence.source_snapshot_content_hash,
        )
        previous = references.setdefault(evidence.source_snapshot_id, reference)
        if previous != reference:
            raise _evidence_error(
                "Literature SourceSnapshot identity is ambiguous",
                reason=GraphRejectionReason.source_snapshot_inconsistent,
                path=f"input_versions.{version.id}.source_snapshots",
            )
    persisted: dict[tuple[str, str, str], SourceSnapshotDetail] = {}
    for snapshot in version.source_snapshots:
        key = (
            snapshot.source_id,
            snapshot.source_version_or_etag
            or snapshot.cache_version
            or snapshot.content_hash,
            snapshot.content_hash,
        )
        if key in persisted:
            raise _evidence_error(
                "persisted SourceSnapshot identity is ambiguous",
                reason=GraphRejectionReason.source_snapshot_inconsistent,
                path=f"input_versions.{version.id}.source_snapshots",
            )
        persisted[key] = snapshot
    if set(references) != set(candidate.source_snapshot_ids):
        raise _evidence_error(
            "Literature evidence does not close candidate SourceSnapshots",
            reason=GraphRejectionReason.source_snapshot_inconsistent,
            path=f"input_versions.{version.id}.source_snapshots",
        )
    bindings: list[PersistedSourceSnapshotBinding] = []
    for pipeline_id, reference in references.items():
        snapshot = persisted.get(reference)
        if snapshot is None:
            raise _evidence_error(
                "Literature SourceSnapshot mapping is incomplete",
                reason=GraphRejectionReason.source_snapshot_missing,
                path=f"input_versions.{version.id}.source_snapshots.{pipeline_id}",
            )
        bindings.append(
            PersistedSourceSnapshotBinding(
                pipeline_source_snapshot_id=pipeline_id,
                source_snapshot=snapshot,
            )
        )
    if {item.source_snapshot.id for item in bindings} != {
        item.id for item in version.source_snapshots
    }:
        raise _evidence_error(
            "Literature SourceSnapshot mapping contains extra storage rows",
            reason=GraphRejectionReason.source_snapshot_inconsistent,
            path=f"input_versions.{version.id}.source_snapshots",
        )
    return tuple(bindings)


def _validated_data_mappings(
    values: tuple[StoredPipelineEvidenceBinding, ...],
    *,
    artifact_version_id: str,
    pipeline_evidence_ids: tuple[str, ...],
    semantic_dataset: DatasetArtifactCandidate,
) -> tuple[StoredPipelineEvidenceBinding, ...]:
    if not isinstance(values, tuple) or any(
        type(item) is not StoredPipelineEvidenceBinding for item in values
    ):
        raise _schema_error(
            "data Evidence resolver must return exact typed mappings",
            path=f"input_versions.{artifact_version_id}.evidence",
        )
    ordered = tuple(sorted(values, key=lambda item: item.pipeline_evidence_id))
    pipeline_ids = tuple(item.pipeline_evidence_id for item in ordered)
    persisted_ids = tuple(item.persisted_evidence_id for item in ordered)
    if any(item.artifact_version_id != artifact_version_id for item in ordered):
        raise _artifact_error(
            "data Evidence mapping belongs to another ArtifactVersion",
            reason=GraphRejectionReason.cross_version_reference,
            path=f"input_versions.{artifact_version_id}.evidence",
        )
    if pipeline_ids != pipeline_evidence_ids or len(persisted_ids) != len(
        set(persisted_ids)
    ):
        raise _evidence_error(
            "data Evidence mappings do not exactly cover the selected version",
            reason=GraphRejectionReason.evidence_inconsistent,
            path=f"input_versions.{artifact_version_id}.evidence",
        )
    transformations = {
        item.evidence_id: item for item in semantic_dataset.transformation_evidence
    }
    crossmatch_ids = set(semantic_dataset.crossmatch_evidence_ids)
    for item in ordered:
        transformation = transformations.get(item.pipeline_evidence_id)
        if transformation is not None:
            expected_locator = transformation.locator.model_dump(mode="json")
            valid = (
                item.pipeline_evidence_content_hash == transformation.content_hash
                and item.pipeline_target_type == "canonical_field"
                and item.pipeline_target_id == transformation.canonical_field_id
                and item.pipeline_locator == expected_locator
                and item.pipeline_source_snapshot_id
                == transformation.locator.source_snapshot_id
            )
        else:
            locator_hash = item.pipeline_locator.get("crossmatch_content_hash")
            valid = (
                item.pipeline_evidence_id in crossmatch_ids
                and item.pipeline_target_type == "crossmatch"
                and item.pipeline_target_id == item.pipeline_evidence_id
                and set(item.pipeline_locator)
                == {"crossmatch_evidence_id", "crossmatch_content_hash"}
                and item.pipeline_locator.get("crossmatch_evidence_id")
                == item.pipeline_evidence_id
                and isinstance(locator_hash, str)
                and locator_hash.startswith("sha256:")
                and len(locator_hash) == 71
                and locator_hash == item.pipeline_evidence_content_hash
                and item.pipeline_source_snapshot_id
                in set(semantic_dataset.crossmatch_source_snapshot_ids)
            )
        if not valid:
            raise GraphInputIntegrityError(
                "governed data Evidence mapping does not close its Data Artifact Transformation/Crossmatch identity",
                stage=GraphIntegrityStage.evidence_snapshot,
                reason=GraphRejectionReason.evidence_inconsistent,
                path=(
                    f"input_versions.{artifact_version_id}.evidence."
                    f"{item.pipeline_evidence_id}"
                ),
            )
    return ordered


def _evidence_detail(read: EvidenceRead) -> EvidenceDetail:
    payload = read.model_dump(mode="json", exclude={"source_snapshot"})
    return EvidenceDetail.model_validate(payload)


__all__ = [
    "ArtifactVersionGraphInputReadAdapter",
    "DatabaseEvidenceRestrictionReadAdapter",
]
