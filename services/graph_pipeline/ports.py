"""Typed, version-pinned read boundary for the Evidence Graph pipeline.

The graph builder is deliberately unable to consume loose JSON, a bare
pipeline candidate, or one page from an HTTP collection.  A trusted adapter
must resolve every requested ArtifactVersion and return the complete published
envelopes defined here.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, JsonValue

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.artifact_publication import canonical_artifact_content_payload
from app.schemas.core import (
    EvidenceDetail,
    ProducerExecutionDetail,
    SourceMode,
    SourceSnapshotDetail,
)
from app.schemas.data_artifacts import (
    CrossmatchArtifactAuthority,
    DatasetArtifactCandidate,
    FieldDictionaryArtifactCandidate,
)
from app.schemas.data_quality import DataQualityProjection
from app.schemas.graph_artifact import (
    GraphIntegrityStage,
    GraphRejectionReason,
    compute_graph_upstream_evidence_hash,
)
from app.schemas.literature_claim import LiteratureClaimsCandidate
from app.schemas.literature_relation import LiteratureRelationsCandidate
from services.paper_pipeline.constants import RELATION_ADJUDICATION_PRODUCER_NAME


class GraphInputIntegrityError(ValueError):
    """A published graph input failed one explicit integrity gate.

    ``stage`` and ``reason`` are part of the error contract.  Callers must not
    infer admission semantics from human-readable message text.
    """

    def __init__(
        self,
        message: str,
        *,
        stage: GraphIntegrityStage,
        reason: GraphRejectionReason,
        path: str,
    ) -> None:
        if type(stage) is not GraphIntegrityStage:
            raise TypeError("stage must be a typed GraphIntegrityStage")
        if type(reason) is not GraphRejectionReason:
            raise TypeError("reason must be a typed GraphRejectionReason")
        _require_text(path, "path")
        _require_text(message, "message")
        super().__init__(message)
        self.stage = stage
        self.reason = reason
        self.path = path


def graph_input_security_error(
    *,
    code: str,
    status: int,
    path: str,
) -> GraphInputIntegrityError:
    """Translate storage authorization/read failures without parsing details."""

    if code == "EVIDENCE_NOT_FOUND":
        stage = GraphIntegrityStage.evidence_snapshot
        reason = GraphRejectionReason.evidence_unknown
    elif code == "SOURCE_SNAPSHOT_NOT_FOUND":
        stage = GraphIntegrityStage.evidence_snapshot
        reason = GraphRejectionReason.source_snapshot_unknown
    elif code == "ARTIFACT_KIND_MISMATCH":
        stage = GraphIntegrityStage.artifact_version
        reason = GraphRejectionReason.wrong_artifact_kind
    elif code == "PROVENANCE_SCOPE_VIOLATION" or status in {401, 403}:
        stage = GraphIntegrityStage.ownership
        reason = GraphRejectionReason.cross_project_ownership
    else:
        stage = GraphIntegrityStage.artifact_version
        reason = GraphRejectionReason.input_version_unknown
    return GraphInputIntegrityError(
        f"Graph input storage access failed ({code})",
        stage=stage,
        reason=reason,
        path=path,
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


def _require_text(value: str, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise _schema_error(
            f"{label} must be nonempty text",
            path=f"input_versions.{label}",
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class GraphDataVersionSelection:
    """Exact Dataset/FieldDictionary pair selected for a data-side graph."""

    dataset_artifact_version_id: str
    field_dictionary_artifact_version_id: str

    def __post_init__(self) -> None:
        for label, value in (
            ("dataset_artifact_version_id", self.dataset_artifact_version_id),
            (
                "field_dictionary_artifact_version_id",
                self.field_dictionary_artifact_version_id,
            ),
        ):
            _require_text(value, label)
        if (
            self.dataset_artifact_version_id
            == self.field_dictionary_artifact_version_id
        ):
            raise _schema_error(
                "Dataset and FieldDictionary must identify distinct ArtifactVersions",
                path="input_versions.data",
            )


@dataclass(frozen=True, slots=True, kw_only=True)
class GraphInputVersionSelection:
    """Exact immutable versions selected for one graph build.

    The literature benchmark is a complete graph input without synthetic data.
    Production/data-side builds add the Dataset/FieldDictionary pair as one
    typed optional unit; a half-present data closure is unrepresentable.
    """

    project_id: str
    literature_claims_artifact_version_ids: tuple[str, ...]
    literature_relations_artifact_version_id: str
    data: GraphDataVersionSelection | None = None

    def __post_init__(self) -> None:
        _require_text(self.project_id, "project_id")
        if (
            not self.literature_claims_artifact_version_ids
            or any(
                not isinstance(item, str) or not item.strip()
                for item in self.literature_claims_artifact_version_ids
            )
            or self.literature_claims_artifact_version_ids
            != tuple(sorted(set(self.literature_claims_artifact_version_ids)))
        ):
            raise _schema_error(
                "literature_claims_artifact_version_ids must be sorted unique text",
                path="input_versions.literature_claims",
            )
        _require_text(
            self.literature_relations_artifact_version_id,
            "literature_relations_artifact_version_id",
        )
        if self.data is not None and type(self.data) is not GraphDataVersionSelection:
            raise _schema_error(
                "data selection must be a typed GraphDataVersionSelection",
                path="input_versions.data",
            )
        selected_ids = {
            *self.literature_claims_artifact_version_ids,
            self.literature_relations_artifact_version_id,
        }
        if len(selected_ids) != len(self.literature_claims_artifact_version_ids) + 1:
            raise _schema_error(
                "LiteratureClaims and LiteratureRelations must identify distinct ArtifactVersions",
                path="input_versions",
            )
        if self.data is not None and selected_ids & {
            self.data.dataset_artifact_version_id,
            self.data.field_dictionary_artifact_version_id,
        }:
            raise _schema_error(
                "graph inputs must identify distinct ArtifactVersions",
                path="input_versions",
            )


@dataclass(frozen=True, slots=True)
class PublishedArtifactVersionPins:
    """Immutable ArtifactVersion and ProducerExecution facts read from storage."""

    artifact_id: str
    artifact_version_id: str
    project_id: str
    version_number: int
    schema_version: str
    content_hash: str
    input_hash: str
    output_hash: str
    source_mode: SourceMode
    producer_execution: ProducerExecutionDetail

    def __post_init__(self) -> None:
        for label, value in (
            ("artifact_id", self.artifact_id),
            ("artifact_version_id", self.artifact_version_id),
            ("project_id", self.project_id),
            ("schema_version", self.schema_version),
            ("content_hash", self.content_hash),
            ("input_hash", self.input_hash),
            ("output_hash", self.output_hash),
        ):
            _require_text(value, label)
        if type(self.version_number) is not int or self.version_number < 1:
            raise _schema_error(
                "version_number must be positive",
                path="input_versions.version_number",
            )
        if type(self.source_mode) is not SourceMode:
            raise _schema_error(
                "source_mode must be a typed SourceMode",
                path="input_versions.source_mode",
            )
        if type(self.producer_execution) is not ProducerExecutionDetail:
            raise _schema_error(
                "producer_execution must be a typed ProducerExecutionDetail",
                path="input_versions.producer_execution",
            )
        execution = self.producer_execution
        if (
            execution.status != "completed"
            or execution.input_hash != self.input_hash
            # Publisher admission binds the execution to canonical published
            # candidate content, not to the candidate's internal output_hash.
            or execution.output_hash != self.content_hash
        ):
            raise _artifact_error(
                "ProducerExecution is not completed and pinned to this ArtifactVersion",
                reason=GraphRejectionReason.producer_execution_mismatch,
                path="input_versions.producer_execution",
            )


@dataclass(frozen=True, slots=True)
class PersistedSourceSnapshotBinding:
    """Map one pipeline SourceSnapshot ID to its persisted immutable record."""

    pipeline_source_snapshot_id: str
    source_snapshot: SourceSnapshotDetail

    def __post_init__(self) -> None:
        _require_text(self.pipeline_source_snapshot_id, "pipeline_source_snapshot_id")
        if type(self.source_snapshot) is not SourceSnapshotDetail:
            raise _schema_error(
                "source_snapshot must be a typed SourceSnapshotDetail",
                path="input_versions.source_snapshots",
            )

    @property
    def persisted_source_snapshot_id(self) -> str:
        return self.source_snapshot.id


@dataclass(frozen=True, slots=True)
class EvidenceRestrictionFact:
    """Exact storage-owned restriction flag for one persisted Evidence row."""

    evidence_id: str
    project_id: str
    is_restricted: bool

    def __post_init__(self) -> None:
        _require_text(self.evidence_id, "evidence_id")
        _require_text(self.project_id, "project_id")
        if type(self.is_restricted) is not bool:
            raise _schema_error(
                "is_restricted must be the exact persisted boolean fact",
                path=f"input_versions.evidence.{self.evidence_id}.is_restricted",
            )


@dataclass(frozen=True, slots=True)
class StoredPipelineEvidenceBinding:
    """Governed storage mapping for a non-persisted pipeline Evidence ID."""

    artifact_version_id: str
    pipeline_evidence_id: str
    pipeline_evidence_content_hash: str
    pipeline_target_type: str
    pipeline_target_id: str
    persisted_evidence_id: str
    pipeline_source_snapshot_id: str
    persisted_source_snapshot_id: str
    pipeline_locator: dict[str, JsonValue]

    def __post_init__(self) -> None:
        for label, value in (
            ("artifact_version_id", self.artifact_version_id),
            ("pipeline_evidence_id", self.pipeline_evidence_id),
            (
                "pipeline_evidence_content_hash",
                self.pipeline_evidence_content_hash,
            ),
            ("pipeline_target_type", self.pipeline_target_type),
            ("pipeline_target_id", self.pipeline_target_id),
            ("persisted_evidence_id", self.persisted_evidence_id),
            ("pipeline_source_snapshot_id", self.pipeline_source_snapshot_id),
            ("persisted_source_snapshot_id", self.persisted_source_snapshot_id),
        ):
            _require_text(value, label)
        if type(self.pipeline_locator) is not dict:
            raise GraphInputIntegrityError(
                "pipeline_locator must be an exact JSON object",
                stage=GraphIntegrityStage.evidence_snapshot,
                reason=GraphRejectionReason.evidence_inconsistent,
                path=f"input_versions.evidence.{self.pipeline_evidence_id}.locator",
            )
        # Detach the governed mapping from adapter-owned mutable input.
        object.__setattr__(self, "pipeline_locator", deepcopy(self.pipeline_locator))


@dataclass(frozen=True, slots=True)
class PersistedEvidenceBinding:
    """Map pipeline Evidence to one persisted, version-owned Evidence record."""

    pipeline_evidence_id: str
    pipeline_evidence_content_hash: str
    pipeline_source_snapshot_id: str
    pipeline_target_type: str
    pipeline_target_id: str
    pipeline_locator: dict[str, JsonValue]
    evidence: EvidenceDetail
    is_restricted: bool

    def __post_init__(self) -> None:
        _require_text(self.pipeline_evidence_id, "pipeline_evidence_id")
        _require_text(
            self.pipeline_evidence_content_hash,
            "pipeline_evidence_content_hash",
        )
        _require_text(self.pipeline_source_snapshot_id, "pipeline_source_snapshot_id")
        _require_text(self.pipeline_target_type, "pipeline_target_type")
        _require_text(self.pipeline_target_id, "pipeline_target_id")
        if type(self.pipeline_locator) is not dict:
            raise GraphInputIntegrityError(
                "pipeline_locator must be an exact JSON object",
                stage=GraphIntegrityStage.evidence_snapshot,
                reason=GraphRejectionReason.evidence_inconsistent,
                path=f"input_versions.evidence.{self.pipeline_evidence_id}.locator",
            )
        object.__setattr__(self, "pipeline_locator", deepcopy(self.pipeline_locator))
        if type(self.evidence) is not EvidenceDetail:
            raise _schema_error(
                "evidence must be a typed EvidenceDetail",
                path=f"input_versions.evidence.{self.pipeline_evidence_id}",
            )
        if type(self.is_restricted) is not bool:
            raise _schema_error(
                "is_restricted must be the exact persisted boolean fact",
                path=(
                    f"input_versions.evidence.{self.pipeline_evidence_id}.is_restricted"
                ),
            )

    @property
    def persisted_evidence_id(self) -> str:
        return self.evidence.id

    @property
    def upstream_evidence_content_hash(self) -> str:
        """Hash every immutable upstream Evidence fact used by Evidence Graph."""

        return compute_graph_upstream_evidence_hash(
            self.evidence,
            is_restricted=self.is_restricted,
        )


def _canonical_source_bindings(
    values: tuple[PersistedSourceSnapshotBinding, ...],
) -> tuple[PersistedSourceSnapshotBinding, ...]:
    if any(type(item) is not PersistedSourceSnapshotBinding for item in values):
        raise _schema_error(
            "source snapshot bindings must use PersistedSourceSnapshotBinding",
            path="input_versions.source_snapshots",
        )
    ordered = tuple(
        sorted(
            values,
            key=lambda item: (
                item.pipeline_source_snapshot_id,
                item.persisted_source_snapshot_id,
            ),
        )
    )
    pipeline_ids = tuple(item.pipeline_source_snapshot_id for item in ordered)
    persisted_ids = tuple(item.persisted_source_snapshot_id for item in ordered)
    if len(pipeline_ids) != len(set(pipeline_ids)) or len(persisted_ids) != len(
        set(persisted_ids)
    ):
        raise _evidence_error(
            "SourceSnapshot bindings must be one-to-one and unique",
            reason=GraphRejectionReason.source_snapshot_inconsistent,
            path="input_versions.source_snapshots",
        )
    return ordered


def _canonical_evidence_bindings(
    values: tuple[PersistedEvidenceBinding, ...],
) -> tuple[PersistedEvidenceBinding, ...]:
    if any(type(item) is not PersistedEvidenceBinding for item in values):
        raise _schema_error(
            "Evidence bindings must use PersistedEvidenceBinding",
            path="input_versions.evidence",
        )
    ordered = tuple(
        sorted(
            values,
            key=lambda item: (
                item.pipeline_evidence_id,
                item.evidence.target_type,
                item.evidence.target_id,
                item.persisted_evidence_id,
            ),
        )
    )
    semantic_keys = tuple(
        (
            item.pipeline_evidence_id,
            item.pipeline_source_snapshot_id,
            item.evidence.target_type,
            item.evidence.target_id,
        )
        for item in ordered
    )
    persisted_ids = tuple(item.persisted_evidence_id for item in ordered)
    if len(semantic_keys) != len(set(semantic_keys)) or len(persisted_ids) != len(
        set(persisted_ids)
    ):
        raise _evidence_error(
            "semantic and persisted Evidence bindings must be unique",
            reason=GraphRejectionReason.evidence_inconsistent,
            path="input_versions.evidence",
        )
    return ordered


def _validated_candidate(
    candidate: BaseModel, expected_type: type[BaseModel]
) -> BaseModel:
    if type(candidate) is not expected_type:
        raise _schema_error(
            f"candidate must be an exact {expected_type.__name__}",
            path="input_versions.content",
        )
    try:
        return expected_type.model_validate(candidate.model_dump(mode="json"))
    except Exception as exc:  # Pydantic error types are an implementation detail here.
        raise _artifact_error(
            "published candidate is not schema-valid",
            reason=GraphRejectionReason.unsupported_schema_version,
            path="input_versions.content",
        ) from exc


def _validate_candidate_pins(
    *,
    pins: PublishedArtifactVersionPins,
    candidate: DatasetArtifactCandidate
    | FieldDictionaryArtifactCandidate
    | LiteratureClaimsCandidate
    | LiteratureRelationsCandidate,
) -> None:
    content = canonical_artifact_content_payload(candidate)
    if pins.schema_version != candidate.schema_version:
        raise _artifact_error(
            "ArtifactVersion schema pin disagrees with candidate",
            reason=GraphRejectionReason.unsupported_schema_version,
            path="input_versions.schema_version",
        )
    if pins.content_hash != compute_canonical_payload_hash(content):
        raise _artifact_error(
            "ArtifactVersion content hash disagrees with candidate",
            reason=GraphRejectionReason.content_hash_mismatch,
            path="input_versions.content_hash",
        )
    # Relation adjudication records the algorithm's canonical operation input
    # hash on the produced ArtifactVersion, which deliberately differs from the
    # inherited Relations candidate input identity.
    adjudicated = (
        pins.producer_execution.producer.name == RELATION_ADJUDICATION_PRODUCER_NAME
    )
    if pins.input_hash != candidate.input_hash and not adjudicated:
        raise _artifact_error(
            "ArtifactVersion input hash disagrees with candidate",
            reason=GraphRejectionReason.input_hash_mismatch,
            path="input_versions.input_hash",
        )
    if pins.output_hash != candidate.output_hash:
        raise _artifact_error(
            "ArtifactVersion domain output hash disagrees with candidate",
            reason=GraphRejectionReason.content_hash_mismatch,
            path="input_versions.output_hash",
        )


def _validate_data_producer(
    pins: PublishedArtifactVersionPins,
    candidate: DatasetArtifactCandidate | FieldDictionaryArtifactCandidate,
) -> None:
    execution = pins.producer_execution
    producer = execution.producer
    expected = candidate.producer
    if (
        producer.type != expected.producer_type
        or producer.name != expected.producer_name
        or producer.version != expected.producer_version
        or execution.parameters_hash != producer.parameters_hash
    ):
        raise _artifact_error(
            "published data ProducerExecution disagrees with candidate producer pins",
            reason=GraphRejectionReason.producer_execution_mismatch,
            path="input_versions.producer_execution",
        )


def _validate_literature_producer(
    execution: ProducerExecutionDetail,
    candidate: LiteratureClaimsCandidate | LiteratureRelationsCandidate,
) -> None:
    producer = execution.producer
    expected = candidate.producer
    if (
        execution.step_key != expected.step_key
        or producer.type != expected.producer_type
        or producer.name != expected.producer_name
        or producer.version != expected.producer_version
        or producer.requested_model != expected.model_name
        or producer.prompt_name != expected.prompt_name
        or producer.prompt_version != expected.prompt_version
        or producer.prompt_hash != expected.prompt_hash
        or execution.parameters_hash != expected.parameters_hash
        or producer.parameters_hash != expected.parameters_hash
    ):
        raise _artifact_error(
            "published LiteratureRelations ProducerExecution disagrees with candidate",
            reason=GraphRejectionReason.producer_execution_mismatch,
            path="input_versions.producer_execution",
        )


def _validate_persisted_provenance(
    *,
    pins: PublishedArtifactVersionPins,
    declared_snapshot_ids: tuple[str, ...],
    declared_evidence_ids: tuple[str, ...],
    source_snapshot_bindings: tuple[PersistedSourceSnapshotBinding, ...],
    evidence_bindings: tuple[PersistedEvidenceBinding, ...],
) -> None:
    snapshot_by_pipeline = {
        item.pipeline_source_snapshot_id: item for item in source_snapshot_bindings
    }
    if set(snapshot_by_pipeline) != set(declared_snapshot_ids):
        raise _evidence_error(
            "SourceSnapshot bindings must exactly cover the candidate registry",
            reason=GraphRejectionReason.source_snapshot_inconsistent,
            path="input_versions.source_snapshots",
        )
    if {item.pipeline_evidence_id for item in evidence_bindings} != set(
        declared_evidence_ids
    ):
        raise _evidence_error(
            "Evidence bindings must exactly cover the candidate registry",
            reason=GraphRejectionReason.evidence_inconsistent,
            path="input_versions.evidence",
        )
    for item in evidence_bindings:
        snapshot = snapshot_by_pipeline.get(item.pipeline_source_snapshot_id)
        if snapshot is None:
            raise _evidence_error(
                "persisted Evidence has no SourceSnapshot binding",
                reason=GraphRejectionReason.source_snapshot_missing,
                path=f"input_versions.evidence.{item.pipeline_evidence_id}",
            )
        if item.evidence.artifact_version_id != pins.artifact_version_id:
            raise _evidence_error(
                "persisted Evidence belongs to another ArtifactVersion",
                reason=GraphRejectionReason.provenance_version_mismatch,
                path=f"input_versions.evidence.{item.pipeline_evidence_id}",
            )
        if item.evidence.source_snapshot_id != snapshot.persisted_source_snapshot_id:
            raise _evidence_error(
                "persisted Evidence SourceSnapshot disagrees with its binding",
                reason=GraphRejectionReason.source_snapshot_inconsistent,
                path=f"input_versions.evidence.{item.pipeline_evidence_id}",
            )
        if (
            item.evidence.target_type != item.pipeline_target_type
            or item.evidence.target_id != item.pipeline_target_id
            or item.evidence.locator != item.pipeline_locator
        ):
            raise _evidence_error(
                "persisted Evidence target/locator disagrees with its pipeline identity",
                reason=GraphRejectionReason.evidence_inconsistent,
                path=f"input_versions.evidence.{item.pipeline_evidence_id}",
            )


def _data_evidence_error(evidence_id: str, message: str) -> GraphInputIntegrityError:
    return GraphInputIntegrityError(
        message,
        stage=GraphIntegrityStage.evidence_snapshot,
        reason=GraphRejectionReason.evidence_inconsistent,
        path=f"input_versions.data.evidence.{evidence_id}",
    )


def _validate_data_evidence_semantics(
    *,
    candidate: DatasetArtifactCandidate,
    evidence_bindings: tuple[PersistedEvidenceBinding, ...],
) -> None:
    """Close persisted rows to exact Data Artifact Transformation/Crossmatch identities."""

    transformations = {
        item.evidence_id: item for item in candidate.transformation_evidence
    }
    crossmatch_authority = (
        candidate.authority
        if isinstance(candidate.authority, CrossmatchArtifactAuthority)
        else None
    )
    crossmatch_ids = (
        set(crossmatch_authority.evidence_ids)
        if crossmatch_authority is not None
        else set()
    )
    for binding in evidence_bindings:
        evidence_id = binding.pipeline_evidence_id
        transformation = transformations.get(evidence_id)
        if transformation is not None:
            expected_locator = transformation.locator.model_dump(mode="json")
            if (
                binding.pipeline_evidence_content_hash != transformation.content_hash
                or binding.pipeline_target_type != "canonical_field"
                or binding.pipeline_target_id != transformation.canonical_field_id
                or binding.pipeline_locator != expected_locator
                or binding.pipeline_source_snapshot_id
                != transformation.locator.source_snapshot_id
            ):
                raise _data_evidence_error(
                    evidence_id,
                    "persisted data Evidence does not close its TransformationEvidence target/locator/Snapshot",
                )
            continue
        if evidence_id not in crossmatch_ids:
            raise _data_evidence_error(
                evidence_id,
                "persisted data Evidence does not resolve to a retained Data Artifact identity",
            )
        if crossmatch_authority is None:
            raise _data_evidence_error(
                evidence_id,
                "non-Transformation data Evidence requires the Crossmatch authority",
            )
        locator = binding.pipeline_locator
        content_hash = locator.get("crossmatch_content_hash")
        if (
            content_hash != binding.pipeline_evidence_content_hash
            or binding.pipeline_target_type != "crossmatch"
            or binding.pipeline_target_id != evidence_id
            or set(locator)
            != {
                "crossmatch_evidence_id",
                "crossmatch_content_hash",
            }
            or locator.get("crossmatch_evidence_id") != evidence_id
            or not isinstance(content_hash, str)
            or not content_hash.startswith("sha256:")
            or len(content_hash) != 71
            or binding.pipeline_source_snapshot_id
            not in set(crossmatch_authority.source_snapshot_ids)
        ):
            raise _data_evidence_error(
                evidence_id,
                "persisted data Evidence does not close its Data Artifact Crossmatch Evidence target/locator/Snapshot",
            )


def _validate_quality_projection(
    *,
    pins: PublishedArtifactVersionPins,
    candidate: DatasetArtifactCandidate | FieldDictionaryArtifactCandidate,
    quality_projection: DataQualityProjection,
) -> None:
    if type(quality_projection) is not DataQualityProjection:
        raise _schema_error(
            "quality_projection must be a typed DataQualityProjection",
            path="input_versions.data.quality_projection",
        )
    if (
        quality_projection.overall_status != "pass"
        or quality_projection.candidate_kind != candidate.kind
        or quality_projection.candidate_id != candidate.candidate_id
        or quality_projection.candidate_input_hash != candidate.input_hash
        or quality_projection.candidate_output_hash != candidate.output_hash
        or quality_projection.candidate_content_hash != pins.content_hash
        or quality_projection.quality_result_input_hash
        != quality_projection.quality_input_hash
    ):
        raise _artifact_error(
            "passing Data Quality Evaluation projection is not bound to the published candidate",
            reason=GraphRejectionReason.provenance_version_mismatch,
            path="input_versions.data.quality_projection",
        )


@dataclass(frozen=True, slots=True)
class PublishedDatasetVersion:
    """One fully closed, quality-passing published Dataset ArtifactVersion."""

    pins: PublishedArtifactVersionPins
    candidate: DatasetArtifactCandidate
    quality_projection: DataQualityProjection
    source_snapshot_bindings: tuple[PersistedSourceSnapshotBinding, ...]
    evidence_bindings: tuple[PersistedEvidenceBinding, ...]

    def __post_init__(self) -> None:
        if type(self.pins) is not PublishedArtifactVersionPins:
            raise _schema_error(
                "dataset pins require a published envelope",
                path="input_versions.data.dataset.pins",
            )
        candidate = _validated_candidate(self.candidate, DatasetArtifactCandidate)
        object.__setattr__(self, "candidate", candidate)
        source_bindings = _canonical_source_bindings(self.source_snapshot_bindings)
        evidence_bindings = _canonical_evidence_bindings(self.evidence_bindings)
        object.__setattr__(self, "source_snapshot_bindings", source_bindings)
        object.__setattr__(self, "evidence_bindings", evidence_bindings)
        _validate_candidate_pins(pins=self.pins, candidate=candidate)
        _validate_data_producer(self.pins, candidate)
        _validate_quality_projection(
            pins=self.pins,
            candidate=candidate,
            quality_projection=self.quality_projection,
        )
        _validate_persisted_provenance(
            pins=self.pins,
            declared_snapshot_ids=candidate.source_snapshot_ids,
            declared_evidence_ids=candidate.evidence_ids,
            source_snapshot_bindings=source_bindings,
            evidence_bindings=evidence_bindings,
        )
        _validate_data_evidence_semantics(
            candidate=candidate,
            evidence_bindings=evidence_bindings,
        )
        source_by_pipeline = {
            item.pipeline_source_snapshot_id: item.source_snapshot
            for item in source_bindings
        }
        for value in candidate.source_values:
            persisted = source_by_pipeline.get(value.source_snapshot_id)
            if (
                persisted is None
                or persisted.source_id != value.source_id
                or persisted.query_hash != value.query_hash
                or persisted.content_hash != value.source_snapshot_content_hash
            ):
                raise _evidence_error(
                    "Dataset SourceValue does not resolve to its persisted SourceSnapshot",
                    reason=GraphRejectionReason.source_snapshot_inconsistent,
                    path=f"input_versions.data.source_values.{value.source_value_id}",
                )


@dataclass(frozen=True, slots=True)
class PublishedFieldDictionaryVersion:
    """One fully closed, quality-passing published FieldDictionary version."""

    pins: PublishedArtifactVersionPins
    candidate: FieldDictionaryArtifactCandidate
    quality_projection: DataQualityProjection
    source_snapshot_bindings: tuple[PersistedSourceSnapshotBinding, ...]
    evidence_bindings: tuple[PersistedEvidenceBinding, ...]

    def __post_init__(self) -> None:
        if type(self.pins) is not PublishedArtifactVersionPins:
            raise _schema_error(
                "FieldDictionary pins require a published envelope",
                path="input_versions.data.field_dictionary.pins",
            )
        candidate = _validated_candidate(
            self.candidate, FieldDictionaryArtifactCandidate
        )
        object.__setattr__(self, "candidate", candidate)
        source_bindings = _canonical_source_bindings(self.source_snapshot_bindings)
        evidence_bindings = _canonical_evidence_bindings(self.evidence_bindings)
        object.__setattr__(self, "source_snapshot_bindings", source_bindings)
        object.__setattr__(self, "evidence_bindings", evidence_bindings)
        _validate_candidate_pins(pins=self.pins, candidate=candidate)
        _validate_data_producer(self.pins, candidate)
        _validate_quality_projection(
            pins=self.pins,
            candidate=candidate,
            quality_projection=self.quality_projection,
        )
        _validate_persisted_provenance(
            pins=self.pins,
            declared_snapshot_ids=candidate.source_snapshot_ids,
            declared_evidence_ids=candidate.evidence_ids,
            source_snapshot_bindings=source_bindings,
            evidence_bindings=evidence_bindings,
        )


@dataclass(frozen=True, slots=True)
class PublishedLiteratureRelationsVersion:
    """One complete published LiteratureRelations version and provenance closure."""

    pins: PublishedArtifactVersionPins
    candidate: LiteratureRelationsCandidate
    source_snapshot_bindings: tuple[PersistedSourceSnapshotBinding, ...]
    evidence_bindings: tuple[PersistedEvidenceBinding, ...]
    scientific_producer_execution: ProducerExecutionDetail | None = None

    def __post_init__(self) -> None:
        if type(self.pins) is not PublishedArtifactVersionPins:
            raise _schema_error(
                "LiteratureRelations pins require a published envelope",
                path="input_versions.literature_relations.pins",
            )
        candidate = _validated_candidate(self.candidate, LiteratureRelationsCandidate)
        object.__setattr__(self, "candidate", candidate)
        source_bindings = _canonical_source_bindings(self.source_snapshot_bindings)
        evidence_bindings = _canonical_evidence_bindings(self.evidence_bindings)
        object.__setattr__(self, "source_snapshot_bindings", source_bindings)
        object.__setattr__(self, "evidence_bindings", evidence_bindings)
        _validate_candidate_pins(pins=self.pins, candidate=candidate)
        scientific_execution = (
            self.scientific_producer_execution
            if self.scientific_producer_execution is not None
            else self.pins.producer_execution
        )
        _validate_literature_producer(scientific_execution, candidate)
        _validate_persisted_provenance(
            pins=self.pins,
            declared_snapshot_ids=candidate.source_snapshot_ids,
            declared_evidence_ids=candidate.evidence_ids,
            source_snapshot_bindings=source_bindings,
            evidence_bindings=evidence_bindings,
        )

        snapshot_by_pipeline = {
            item.pipeline_source_snapshot_id: item.source_snapshot
            for item in source_bindings
        }
        for evidence in candidate.evidence:
            snapshot = snapshot_by_pipeline.get(evidence.source_snapshot_id)
            effective_version = (
                snapshot.source_version_or_etag
                or snapshot.cache_version
                or snapshot.content_hash
                if snapshot is not None
                else None
            )
            if (
                snapshot is None
                or snapshot.source_id != evidence.source_id
                or snapshot.content_hash != evidence.source_snapshot_content_hash
                or effective_version != evidence.source_snapshot_version
            ):
                raise _evidence_error(
                    "Literature Evidence does not resolve to its persisted SourceSnapshot",
                    reason=GraphRejectionReason.source_snapshot_inconsistent,
                    path=f"input_versions.evidence.{evidence.evidence_id}",
                )

        expected_references = {
            (target_type, target_id, item.evidence_id, item.source_snapshot_id)
            for item in candidate.evidence_references
            for target_type, target_id in (
                ("claim", item.claim_id),
                ("relation", item.relation_id),
            )
        }
        pipeline_snapshot_by_persisted = {
            item.persisted_source_snapshot_id: item.pipeline_source_snapshot_id
            for item in source_bindings
        }
        actual_references = {
            (
                item.evidence.target_type,
                item.evidence.target_id,
                item.pipeline_evidence_id,
                pipeline_snapshot_by_persisted.get(item.evidence.source_snapshot_id),
            )
            for item in evidence_bindings
            if item.evidence.target_type in {"claim", "relation"}
        }
        pipeline_evidence_hashes = {
            item.evidence_id: compute_canonical_payload_hash(
                item.model_dump(mode="json", exclude_none=True)
            )
            for item in candidate.evidence
        }
        if actual_references != expected_references or any(
            item.evidence.target_type not in {"claim", "relation"}
            or item.evidence.locator.get("summary_evidence_id")
            != item.pipeline_evidence_id
            or item.pipeline_evidence_content_hash
            != pipeline_evidence_hashes.get(item.pipeline_evidence_id)
            for item in evidence_bindings
        ):
            raise _evidence_error(
                "persisted Literature Evidence does not exactly close Relation references",
                reason=GraphRejectionReason.evidence_inconsistent,
                path="input_versions.evidence",
            )


@dataclass(frozen=True, slots=True)
class PublishedLiteratureClaimsVersion:
    """One complete published LiteratureClaims version and provenance closure."""

    pins: PublishedArtifactVersionPins
    candidate: LiteratureClaimsCandidate
    source_snapshot_bindings: tuple[PersistedSourceSnapshotBinding, ...]
    evidence_bindings: tuple[PersistedEvidenceBinding, ...]

    def __post_init__(self) -> None:
        if type(self.pins) is not PublishedArtifactVersionPins:
            raise _schema_error(
                "LiteratureClaims pins require a published envelope",
                path="input_versions.literature_claims.pins",
            )
        candidate = _validated_candidate(self.candidate, LiteratureClaimsCandidate)
        object.__setattr__(self, "candidate", candidate)
        source_bindings = _canonical_source_bindings(self.source_snapshot_bindings)
        evidence_bindings = _canonical_evidence_bindings(self.evidence_bindings)
        object.__setattr__(self, "source_snapshot_bindings", source_bindings)
        object.__setattr__(self, "evidence_bindings", evidence_bindings)
        _validate_candidate_pins(pins=self.pins, candidate=candidate)
        _validate_literature_producer(self.pins.producer_execution, candidate)
        _validate_persisted_provenance(
            pins=self.pins,
            declared_snapshot_ids=candidate.source_snapshot_ids,
            declared_evidence_ids=candidate.evidence_ids,
            source_snapshot_bindings=source_bindings,
            evidence_bindings=evidence_bindings,
        )

        snapshot_by_pipeline = {
            item.pipeline_source_snapshot_id: item.source_snapshot
            for item in source_bindings
        }
        for evidence in candidate.evidence:
            snapshot = snapshot_by_pipeline.get(evidence.source_snapshot_id)
            effective_version = (
                snapshot.source_version_or_etag
                or snapshot.cache_version
                or snapshot.content_hash
                if snapshot is not None
                else None
            )
            if (
                snapshot is None
                or snapshot.source_id != evidence.source_id
                or snapshot.content_hash != evidence.source_snapshot_content_hash
                or effective_version != evidence.source_snapshot_version
            ):
                raise _evidence_error(
                    "Literature Claim Evidence does not resolve to its persisted SourceSnapshot",
                    reason=GraphRejectionReason.source_snapshot_inconsistent,
                    path=f"input_versions.evidence.{evidence.evidence_id}",
                )

        expected_references = {
            ("claim", item.claim_id, item.evidence_id, item.source_snapshot_id)
            for item in candidate.evidence_references
        }
        pipeline_snapshot_by_persisted = {
            item.persisted_source_snapshot_id: item.pipeline_source_snapshot_id
            for item in source_bindings
        }
        actual_references = {
            (
                item.evidence.target_type,
                item.evidence.target_id,
                item.pipeline_evidence_id,
                pipeline_snapshot_by_persisted.get(item.evidence.source_snapshot_id),
            )
            for item in evidence_bindings
        }
        pipeline_evidence_hashes = {
            item.evidence_id: compute_canonical_payload_hash(
                item.model_dump(mode="json", exclude_none=True)
            )
            for item in candidate.evidence
        }
        if actual_references != expected_references or any(
            item.evidence.target_type != "claim"
            or item.evidence.locator.get("summary_evidence_id")
            != item.pipeline_evidence_id
            or item.pipeline_evidence_content_hash
            != pipeline_evidence_hashes.get(item.pipeline_evidence_id)
            for item in evidence_bindings
        ):
            raise _evidence_error(
                "persisted Literature Claim Evidence does not exactly close Claim references",
                reason=GraphRejectionReason.evidence_inconsistent,
                path="input_versions.evidence",
            )


@dataclass(frozen=True, slots=True, kw_only=True)
class PublishedDataGraphInputs:
    """One exact, cross-validated Data Artifact/Data Quality Evaluation data input closure."""

    dataset: PublishedDatasetVersion
    field_dictionary: PublishedFieldDictionaryVersion

    def __post_init__(self) -> None:
        if (
            type(self.dataset) is not PublishedDatasetVersion
            or type(self.field_dictionary) is not PublishedFieldDictionaryVersion
        ):
            raise _schema_error(
                "data graph input requires exact published typed envelopes",
                path="input_versions.data",
            )
        if self.dataset.pins.project_id != self.field_dictionary.pins.project_id:
            raise _ownership_error(
                "Dataset and FieldDictionary must belong to one Project",
                path="input_versions.data.project_id",
            )
        dataset = self.dataset.candidate
        dictionary = self.field_dictionary.candidate
        if (
            dataset.input_hash != dictionary.input_hash
            or dataset.manifest_pins != dictionary.manifest_pins
            or dataset.requested_fields != dictionary.requested_fields
            or tuple(column.field for column in dataset.columns)
            != dictionary.field_definitions
            or dataset.source_snapshot_ids != dictionary.source_snapshot_ids
            or dataset.evidence_ids != dictionary.evidence_ids
            or dataset.producer != dictionary.producer
            or (
                dataset.mapping_rule_set_id,
                dataset.mapping_rule_set_version,
                dataset.mapping_rule_set_content_hash,
                dataset.conversion_catalog_id,
                dataset.conversion_catalog_version,
                dataset.conversion_catalog_content_hash,
            )
            != (
                dictionary.mapping_rule_set_id,
                dictionary.mapping_rule_set_version,
                dictionary.mapping_rule_set_content_hash,
                dictionary.conversion_catalog_id,
                dictionary.conversion_catalog_version,
                dictionary.conversion_catalog_content_hash,
            )
        ):
            raise _artifact_error(
                "Dataset and FieldDictionary are not one closed Data Artifact bundle",
                reason=GraphRejectionReason.cross_version_reference,
                path="input_versions.data",
            )
        dataset_quality = self.dataset.quality_projection
        dictionary_quality = self.field_dictionary.quality_projection
        shared_quality = (
            "quality_input_hash",
            "quality_result_id",
            "quality_result_input_hash",
            "quality_result_output_hash",
            "quality_result_content_hash",
            "evaluation_plan_content_hash",
            "evaluation_commitment",
            "bundle_commitment",
            "rule_set",
            "research_contract",
            "overall_status",
        )
        if any(
            getattr(dataset_quality, field) != getattr(dictionary_quality, field)
            for field in shared_quality
        ):
            raise _artifact_error(
                "Dataset and FieldDictionary do not share one passing Data Quality Evaluation bundle",
                reason=GraphRejectionReason.provenance_version_mismatch,
                path="input_versions.data.quality_projection",
            )
        _validate_data_evidence_semantics(
            candidate=dataset,
            evidence_bindings=self.field_dictionary.evidence_bindings,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class PublishedGraphInputs:
    """Complete input bundle returned by the exact version read port."""

    selection: GraphInputVersionSelection
    literature_claims: tuple[PublishedLiteratureClaimsVersion, ...]
    literature_relations: PublishedLiteratureRelationsVersion
    data: PublishedDataGraphInputs | None = None

    def __post_init__(self) -> None:
        if type(self.selection) is not GraphInputVersionSelection:
            raise _schema_error(
                "graph input bundle requires a typed version selection",
                path="input_versions",
            )
        if not self.literature_claims or any(
            type(item) is not PublishedLiteratureClaimsVersion
            for item in self.literature_claims
        ):
            raise _schema_error(
                "graph input bundle requires an exact LiteratureClaims envelope",
                path="input_versions.literature_claims",
            )
        if type(self.literature_relations) is not PublishedLiteratureRelationsVersion:
            raise _schema_error(
                "graph input bundle requires an exact LiteratureRelations envelope",
                path="input_versions.literature_relations",
            )
        if self.data is not None and type(self.data) is not PublishedDataGraphInputs:
            raise _schema_error(
                "data input must be a typed PublishedDataGraphInputs closure",
                path="input_versions.data",
            )
        if (self.selection.data is None) != (self.data is None):
            raise _schema_error(
                "selected and published data closures must both be present or absent",
                path="input_versions.data",
            )
        literature_projects = {
            self.literature_relations.pins.project_id,
            *(item.pins.project_id for item in self.literature_claims),
        }
        if literature_projects != {self.selection.project_id}:
            raise _ownership_error(
                "Literature graph envelopes belong to another Project",
                path="input_versions.literature.project_id",
            )
        selected_claim_versions = self.selection.literature_claims_artifact_version_ids
        published_claim_versions = tuple(
            sorted(item.pins.artifact_version_id for item in self.literature_claims)
        )
        if selected_claim_versions != published_claim_versions:
            raise _artifact_error(
                "LiteratureClaims envelope does not match the exact selection",
                reason=GraphRejectionReason.cross_version_reference,
                path="input_versions.literature_claims.artifact_version_id",
            )
        if (
            self.selection.literature_relations_artifact_version_id
            != self.literature_relations.pins.artifact_version_id
        ):
            raise _artifact_error(
                "LiteratureRelations envelope does not match the exact selection",
                reason=GraphRejectionReason.cross_version_reference,
                path="input_versions.literature_relations.artifact_version_id",
            )
        referenced_claim_versions = {
            item.artifact_version_id
            for item in self.literature_relations.candidate.input_versions.claim_artifact_versions
        }
        if referenced_claim_versions != set(published_claim_versions):
            raise _artifact_error(
                "LiteratureRelations must resolve to the selected LiteratureClaims version",
                reason=GraphRejectionReason.cross_version_reference,
                path="input_versions.literature_relations.claim_artifact_versions",
            )
        claim_ids = tuple(
            claim.claim_id
            for published in self.literature_claims
            for claim in published.candidate.claims
        )
        if len(claim_ids) != len(set(claim_ids)):
            raise _artifact_error(
                "LiteratureClaims versions contain duplicate Claim identities",
                reason=GraphRejectionReason.cross_version_reference,
                path="input_versions.literature_claims.claims",
            )
        if self.data is None:
            return

        assert self.selection.data is not None
        if (
            self.data.dataset.pins.project_id != self.selection.project_id
            or self.data.field_dictionary.pins.project_id != self.selection.project_id
        ):
            raise _ownership_error(
                "published data closure belongs to another Project",
                path="input_versions.data.project_id",
            )
        if (
            self.data.dataset.pins.artifact_version_id
            != self.selection.data.dataset_artifact_version_id
            or self.data.field_dictionary.pins.artifact_version_id
            != self.selection.data.field_dictionary_artifact_version_id
        ):
            raise _artifact_error(
                "published data closure does not match the exact selection",
                reason=GraphRejectionReason.cross_version_reference,
                path="input_versions.data.artifact_version_id",
            )

    @property
    def dataset(self) -> PublishedDatasetVersion | None:
        """Expose the optional Dataset envelope without weakening pair closure."""

        return self.data.dataset if self.data is not None else None

    @property
    def field_dictionary(self) -> PublishedFieldDictionaryVersion | None:
        """Expose the optional FieldDictionary envelope as the paired projection."""

        return self.data.field_dictionary if self.data is not None else None


@runtime_checkable
class VersionedGraphInputReadPort(Protocol):
    """Resolve one selection into a complete typed bundle; never return pages."""

    def read(self, selection: GraphInputVersionSelection) -> PublishedGraphInputs:
        """Read and validate all exact ArtifactVersions selected for Evidence Graph."""


@runtime_checkable
class EvidenceRestrictionReadPort(Protocol):
    """Read exact persisted restriction flags; implementations must fail closed."""

    def read_restrictions(
        self,
        *,
        project_id: str,
        evidence_ids: tuple[str, ...],
    ) -> tuple[EvidenceRestrictionFact, ...]:
        """Return one storage fact for every requested persisted Evidence ID."""


@runtime_checkable
class PipelineEvidenceBindingReadPort(Protocol):
    """Resolve governed pipeline Evidence IDs to persisted storage identities."""

    def read_bindings(
        self,
        *,
        project_id: str,
        artifact_version_id: str,
        pipeline_evidence_ids: tuple[str, ...],
    ) -> tuple[StoredPipelineEvidenceBinding, ...]:
        """Return the exact mapping registry for one ArtifactVersion."""


__all__ = [
    "EvidenceRestrictionFact",
    "EvidenceRestrictionReadPort",
    "GraphDataVersionSelection",
    "GraphInputIntegrityError",
    "GraphInputVersionSelection",
    "PersistedEvidenceBinding",
    "PersistedSourceSnapshotBinding",
    "PipelineEvidenceBindingReadPort",
    "PublishedArtifactVersionPins",
    "PublishedDataGraphInputs",
    "PublishedDatasetVersion",
    "PublishedFieldDictionaryVersion",
    "PublishedGraphInputs",
    "PublishedLiteratureRelationsVersion",
    "StoredPipelineEvidenceBinding",
    "VersionedGraphInputReadPort",
    "graph_input_security_error",
]
