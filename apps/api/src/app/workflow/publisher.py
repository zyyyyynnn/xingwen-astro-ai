"""Producer execution ledger and atomic ArtifactVersion publication."""

from __future__ import annotations

import json
import re
import sys
import weakref
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, fields
from datetime import datetime
from threading import RLock
from typing import TypeAlias, TypeVar
from uuid import UUID, uuid4

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    ArtifactVersionModel,
    DatasetRowProjectionModel,
    EvidenceModel,
    ProducerExecutionModel,
    ResearchArtifactModel,
    ResearchRunModel,
    ResearchThreadEntryModel,
    RunEventModel,
    RunStepModel,
    SourceSnapshotModel,
    StepAttemptModel,
)
from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.artifact_publication import (
    canonical_artifact_content_payload,
    canonical_artifact_content_model,
    normalize_artifact_kind,
)
from app.schemas.data_quality import DataQualityProjection
from app.schemas.data_artifacts import (
    CrossmatchArtifactAuthority,
    CrossmatchTransformationAuthority,
    SourceTableArtifactAuthority,
    SourceTableTransformationAuthority,
)
from app.schemas.enums import SourceMode
from app.services.research_thread import append_assistant_message
from app.workflow.store import TERMINAL_RUN_STATUSES

_HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_PARAMETER_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_SENSITIVE_PARAMETER_KEY_FRAGMENTS = frozenset(
    {
        "api_key",
        "apikey",
        "apitoken",
        "authheader",
        "authorization",
        "bearertoken",
        "cookie",
        "credential",
        "database_url",
        "password",
        "privatekey",
        "raw_model_output",
        "refresh_token",
        "restricted_full_text",
        "secret",
        "session_token",
        "access_token",
        "chain_of_thought",
    }
)
_TOKEN_CREDENTIAL_QUALIFIERS = frozenset(
    {
        "access",
        "api",
        "auth",
        "authentication",
        "authorization",
        "bearer",
        "refresh",
        "session",
    }
)
_KEY_CREDENTIAL_QUALIFIERS = frozenset(
    {"api", "credential", "encryption", "private", "secret", "signing"}
)
_HEADER_CREDENTIAL_QUALIFIERS = frozenset(
    {"auth", "authentication", "authorization", "bearer", "credential", "proxy"}
)
_PRODUCER_TYPES = frozenset({"pipeline", "model", "algorithm"})
_PRODUCER_TERMINAL_STATUSES = frozenset(
    {"completed", "failed", "rejected", "cancelled"}
)
_SOURCE_MODES = frozenset(mode.value for mode in SourceMode)
_SCIENTIFIC_ARTIFACT_KINDS = frozenset(
    {
        "analysis_report",
        "visualization",
        "spectrum",
        "light_curve",
        "model_evaluation",
        "model_artifact",
    }
)
_ADMISSION_SEAL = object()
_QUALITY_ATTESTATION_SEAL = object()
_SEMANTIC_VERSION_PATTERN = re.compile(r"^[1-9]\d*\.\d+\.\d+$")

ProducerParameter: TypeAlias = str | int | float | bool | None
AdmissionValidator: TypeAlias = Callable[["ArtifactAdmissionContext"], None]
_CanonicalMaterialization: TypeAlias = tuple[tuple[str, str | bool], ...]
_MaterializationT = TypeVar("_MaterializationT")


class PublisherError(RuntimeError):
    """Base error with a stable application code."""

    code = "ARTIFACT_PUBLISHER_ERROR"


class ProducerExecutionNotFoundError(PublisherError):
    code = "PRODUCER_EXECUTION_NOT_FOUND"


class ProducerExecutionConflictError(PublisherError):
    code = "PRODUCER_EXECUTION_CONFLICT"


class PublicationConflictError(PublisherError):
    code = "PUBLICATION_CONFLICT"


class PublicationAdmissionError(PublisherError):
    code = "PUBLICATION_ADMISSION_REJECTED"


class PublicationResourceNotFoundError(PublisherError):
    code = "PUBLICATION_RESOURCE_NOT_FOUND"


class StalePublicationError(PublicationConflictError):
    code = "STALE_PUBLICATION"


@dataclass(frozen=True, slots=True)
class ProducerExecutionRequest:
    run_id: UUID
    step_key: str
    attempt_id: UUID
    idempotency_key: str
    producer_type: str
    producer_name: str
    producer_version: str
    input_hash: str
    parameters: Mapping[str, ProducerParameter]
    parameters_hash: str | None = None
    model_provider: str | None = None
    requested_model: str | None = None
    explicit_revision: str | None = None
    prompt_name: str | None = None
    prompt_version: str | None = None
    prompt_hash: str | None = None
    authorized_tool_name: str | None = None
    authorized_skill_id: str | None = None
    registry_revision: str | None = None


@dataclass(frozen=True, slots=True)
class ProducerExecutionSnapshot:
    id: UUID
    run_id: UUID
    run_step_id: UUID
    step_attempt_id: UUID
    step_key: str
    idempotency_key: str
    lease_generation: int
    producer_type: str
    producer_name: str
    producer_version: str
    model_provider: str | None
    requested_model: str | None
    provider_returned_model: str | None
    provider_request_id: str | None
    explicit_revision: str | None
    prompt_name: str | None
    prompt_version: str | None
    prompt_hash: str | None
    parameters: Mapping[str, ProducerParameter]
    parameters_hash: str
    input_hash: str
    output_hash: str | None
    status: str
    started_at: datetime
    finished_at: datetime | None
    token_usage: Mapping[str, int] | None
    latency_ms: int | None
    error_code: str | None
    model_response: Mapping[str, object] | None
    replayed: bool


@dataclass(frozen=True, slots=True, init=False, weakref_slot=True)
class AdmittedArtifactCandidate:
    """Opaque structured candidate that can only be created by the admission port."""

    _content_json: str
    content_hash: str
    schema_version: str
    source_snapshot_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    _quality_projection_json: str | None
    quality_projection_hash: str | None
    _literature_source_snapshot_materializations: tuple[_CanonicalMaterialization, ...]
    _literature_evidence_materializations: tuple[_CanonicalMaterialization, ...]
    _graph_source_snapshot_materializations: tuple[_CanonicalMaterialization, ...]
    _graph_evidence_materializations: tuple[_CanonicalMaterialization, ...]
    _data_source_snapshot_materializations: tuple[_CanonicalMaterialization, ...]
    _owned_evidence_materializations: tuple[_CanonicalMaterialization, ...]

    def __init__(
        self,
        *,
        content_json: str,
        content_hash: str,
        schema_version: str,
        source_snapshot_ids: tuple[str, ...],
        evidence_ids: tuple[str, ...],
        quality_projection: DataQualityProjection | None = None,
        literature_source_snapshot_materializations: Sequence[
            _LiteratureSourceSnapshotMaterialization
        ] = (),
        literature_evidence_materializations: Sequence[
            _LiteratureEvidenceMaterialization
        ] = (),
        graph_source_snapshot_materializations: Sequence[
            _GraphSourceSnapshotMaterialization
        ] = (),
        graph_evidence_materializations: Sequence[_GraphEvidenceMaterialization] = (),
        data_source_snapshot_materializations: Sequence[
            _DataSourceSnapshotMaterialization
        ] = (),
        owned_evidence_materializations: Sequence[_OwnedEvidenceMaterialization] = (),
        _seal: object,
    ) -> None:
        if _seal is not _ADMISSION_SEAL:
            raise PublicationAdmissionError(
                "Artifact candidates must pass the structured publication admission port"
            )
        object.__setattr__(self, "_content_json", content_json)
        object.__setattr__(self, "content_hash", content_hash)
        object.__setattr__(self, "schema_version", schema_version)
        object.__setattr__(self, "source_snapshot_ids", source_snapshot_ids)
        object.__setattr__(self, "evidence_ids", evidence_ids)
        projection_json = (
            json.dumps(
                quality_projection.model_dump(mode="json"),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            if quality_projection is not None
            else None
        )
        object.__setattr__(self, "_quality_projection_json", projection_json)
        object.__setattr__(
            self,
            "quality_projection_hash",
            quality_projection.content_hash if quality_projection is not None else None,
        )
        object.__setattr__(
            self,
            "_literature_source_snapshot_materializations",
            _canonicalize_materializations(
                literature_source_snapshot_materializations,
                _LiteratureSourceSnapshotMaterialization,
            ),
        )
        object.__setattr__(
            self,
            "_literature_evidence_materializations",
            _canonicalize_materializations(
                literature_evidence_materializations,
                _LiteratureEvidenceMaterialization,
            ),
        )
        object.__setattr__(
            self,
            "_graph_source_snapshot_materializations",
            _canonicalize_materializations(
                graph_source_snapshot_materializations,
                _GraphSourceSnapshotMaterialization,
            ),
        )
        object.__setattr__(
            self,
            "_graph_evidence_materializations",
            _canonicalize_materializations(
                graph_evidence_materializations,
                _GraphEvidenceMaterialization,
            ),
        )
        object.__setattr__(
            self,
            "_data_source_snapshot_materializations",
            _canonicalize_materializations(
                data_source_snapshot_materializations,
                _DataSourceSnapshotMaterialization,
            ),
        )
        object.__setattr__(
            self,
            "_owned_evidence_materializations",
            _canonicalize_materializations(
                owned_evidence_materializations,
                _OwnedEvidenceMaterialization,
            ),
        )
        _register_admitted_candidate(self)

    @property
    def content(self) -> dict[str, object]:
        return json.loads(self._content_json)

    @property
    def quality_projection(self) -> DataQualityProjection | None:
        if self._quality_projection_json is None:
            return None
        return DataQualityProjection.model_validate_json(self._quality_projection_json)

    @property
    def literature_source_snapshot_materializations(
        self,
    ) -> tuple[_LiteratureSourceSnapshotMaterialization, ...]:
        return _rebuild_materializations(
            self._literature_source_snapshot_materializations,
            _LiteratureSourceSnapshotMaterialization,
        )

    @property
    def literature_evidence_materializations(
        self,
    ) -> tuple[_LiteratureEvidenceMaterialization, ...]:
        return _rebuild_materializations(
            self._literature_evidence_materializations,
            _LiteratureEvidenceMaterialization,
        )

    @property
    def graph_source_snapshot_materializations(
        self,
    ) -> tuple[_GraphSourceSnapshotMaterialization, ...]:
        return _rebuild_materializations(
            self._graph_source_snapshot_materializations,
            _GraphSourceSnapshotMaterialization,
        )

    @property
    def graph_evidence_materializations(
        self,
    ) -> tuple[_GraphEvidenceMaterialization, ...]:
        return _rebuild_materializations(
            self._graph_evidence_materializations,
            _GraphEvidenceMaterialization,
        )

    @property
    def data_source_snapshot_materializations(
        self,
    ) -> tuple[_DataSourceSnapshotMaterialization, ...]:
        return _rebuild_materializations(
            self._data_source_snapshot_materializations,
            _DataSourceSnapshotMaterialization,
        )

    @property
    def owned_evidence_materializations(
        self,
    ) -> tuple[_OwnedEvidenceMaterialization, ...]:
        return _rebuild_materializations(
            self._owned_evidence_materializations,
            _OwnedEvidenceMaterialization,
        )


@dataclass(frozen=True, slots=True)
class _DataQualityPublicationAttestation:
    token: object
    candidate_object_id: int
    candidate_kind: str
    candidate_id: str
    candidate_input_hash: str
    candidate_output_hash: str
    candidate_content_hash: str
    projection_json: str
    projection_hash: str


def _seal_data_quality_attestation(
    candidate: BaseModel,
    projection: DataQualityProjection,
) -> _DataQualityPublicationAttestation:
    content = canonical_artifact_content_payload(candidate)
    candidate_content_hash = compute_canonical_payload_hash(content)
    if (
        projection.candidate_kind != getattr(candidate, "kind", None)
        or projection.candidate_id != getattr(candidate, "candidate_id", None)
        or projection.candidate_input_hash != getattr(candidate, "input_hash", None)
        or projection.candidate_output_hash != getattr(candidate, "output_hash", None)
        or projection.candidate_content_hash != candidate_content_hash
    ):
        raise PublicationAdmissionError(
            "Data Quality Evaluation attestation does not match the exact data candidate"
        )
    projection_json = json.dumps(
        projection.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return _DataQualityPublicationAttestation(
        token=_QUALITY_ATTESTATION_SEAL,
        candidate_object_id=id(candidate),
        candidate_kind=projection.candidate_kind,
        candidate_id=projection.candidate_id,
        candidate_input_hash=projection.candidate_input_hash,
        candidate_output_hash=projection.candidate_output_hash,
        candidate_content_hash=candidate_content_hash,
        projection_json=projection_json,
        projection_hash=projection.content_hash,
    )


def _quality_projection_from_attestation(
    candidate: BaseModel,
    attestation: object,
) -> DataQualityProjection:
    if not isinstance(attestation, _DataQualityPublicationAttestation):
        raise PublicationAdmissionError(
            "Final data Artifact publication requires a Data Quality Evaluation attestation"
        )
    content_hash = compute_canonical_payload_hash(
        canonical_artifact_content_payload(candidate)
    )
    projection = DataQualityProjection.model_validate_json(attestation.projection_json)
    if (
        attestation.token is not _QUALITY_ATTESTATION_SEAL
        or attestation.candidate_object_id != id(candidate)
        or attestation.candidate_kind != getattr(candidate, "kind", None)
        or attestation.candidate_id != getattr(candidate, "candidate_id", None)
        or attestation.candidate_input_hash != getattr(candidate, "input_hash", None)
        or attestation.candidate_output_hash != getattr(candidate, "output_hash", None)
        or attestation.candidate_content_hash != content_hash
        or attestation.projection_hash != projection.content_hash
        or projection.candidate_content_hash != content_hash
    ):
        raise PublicationAdmissionError(
            "Data Quality Evaluation attestation is not sealed to the exact data candidate"
        )
    return projection


@dataclass(frozen=True, slots=True)
class ArtifactAdmissionContext:
    candidate: BaseModel
    source_snapshot_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    persisted_source_snapshot_ids: tuple[str, ...]
    persisted_evidence_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ArtifactSourceSnapshotBinding:
    """Bind one Pipeline snapshot identity to its persisted SourceSnapshot id."""

    pipeline_source_snapshot_id: str
    persisted_source_snapshot_id: str


@dataclass(frozen=True, slots=True)
class ArtifactEvidenceBinding:
    """Bind one domain Evidence use to its persisted Evidence/Snapshot ids."""

    target_type: str
    target_id: str
    pipeline_evidence_id: str
    pipeline_source_snapshot_id: str
    persisted_evidence_id: str
    persisted_source_snapshot_id: str

    @property
    def materialization_key(self) -> tuple[str, str, str, str]:
        return (
            self.target_type,
            self.target_id,
            self.pipeline_evidence_id,
            self.pipeline_source_snapshot_id,
        )


@dataclass(frozen=True, slots=True)
class _LiteratureSourceSnapshotMaterialization:
    pipeline_source_snapshot_id: str
    persisted_source_snapshot_id: str
    source_id: str
    source_version: str
    content_hash: str


@dataclass(frozen=True, slots=True)
class _LiteratureEvidenceMaterialization:
    target_type: str
    target_id: str
    pipeline_evidence_id: str
    pipeline_source_snapshot_id: str
    persisted_evidence_id: str
    persisted_source_snapshot_id: str
    paper_id: str
    source_record_id: str
    evidence_type: str
    locator_json: str
    quote_or_value_json: str


@dataclass(frozen=True, slots=True)
class _GraphSourceSnapshotMaterialization:
    pipeline_source_snapshot_id: str
    persisted_source_snapshot_id: str
    source_id: str
    source_version: str
    content_hash: str


@dataclass(frozen=True, slots=True)
class _GraphEvidenceMaterialization:
    target_id: str
    pipeline_evidence_id: str
    pipeline_source_snapshot_id: str
    persisted_evidence_id: str
    persisted_source_snapshot_id: str
    upstream_artifact_version_id: str
    upstream_evidence_id: str
    upstream_target_type: str
    upstream_target_id: str
    upstream_evidence_hash: str
    evidence_type: str
    upstream_is_restricted: bool


@dataclass(frozen=True, slots=True)
class _DataSourceSnapshotMaterialization:
    pipeline_source_snapshot_id: str
    persisted_source_snapshot_id: str
    source_id: str
    query_hash: str
    content_hash: str


@dataclass(frozen=True, slots=True)
class _OwnedEvidenceMaterialization:
    target_type: str
    target_id: str
    pipeline_evidence_id: str
    pipeline_source_snapshot_id: str
    persisted_evidence_id: str
    persisted_source_snapshot_id: str
    evidence_type: str
    locator_json: str
    quote_or_value_json: str
    extraction_method: str
    confidence: str


def _canonicalize_materializations(
    materializations: Sequence[_MaterializationT],
    materialization_type: type[_MaterializationT],
) -> tuple[_CanonicalMaterialization, ...]:
    """Detach an authority plan from caller-reachable dataclass instances."""

    field_names = tuple(field.name for field in fields(materialization_type))
    canonical: list[_CanonicalMaterialization] = []
    for item in materializations:
        if type(item) is not materialization_type:
            raise PublicationAdmissionError(
                "Artifact materialization plan uses an unexpected value type"
            )
        values = tuple((name, getattr(item, name)) for name in field_names)
        if any(type(value) not in {str, bool} for _, value in values):
            raise PublicationAdmissionError(
                "Artifact materialization plan must contain canonical scalar values"
            )
        canonical.append(values)
    return tuple(canonical)


def _rebuild_materializations(
    materializations: tuple[_CanonicalMaterialization, ...],
    materialization_type: type[_MaterializationT],
) -> tuple[_MaterializationT, ...]:
    """Return fresh typed plans without exposing the sealed authority snapshot."""

    return tuple(materialization_type(**dict(item)) for item in materializations)


def admit_artifact_candidate(
    candidate: BaseModel,
    *,
    schema_version: str,
    source_snapshot_ids: Sequence[str],
    evidence_ids: Sequence[str],
    evidence_validator: AdmissionValidator,
    domain_validator: AdmissionValidator,
    quality_validator: AdmissionValidator,
    source_snapshot_bindings: Sequence[ArtifactSourceSnapshotBinding] | None = None,
    evidence_bindings: Sequence[ArtifactEvidenceBinding] | None = None,
    data_provenance_candidate: BaseModel | None = None,
) -> AdmittedArtifactCandidate:
    """Run the caller-owned Evidence, domain, and quality gates on typed content."""

    if not isinstance(candidate, BaseModel) or candidate.__class__ is BaseModel:
        raise PublicationAdmissionError("A validated Pydantic model is required")
    _require_pipeline_admission(candidate)
    if not candidate.__class__.model_fields:
        raise PublicationAdmissionError(
            "An empty or untyped candidate cannot be published"
        )
    normalized_schema_version = schema_version.strip()
    if not _SEMANTIC_VERSION_PATTERN.fullmatch(normalized_schema_version):
        raise PublicationAdmissionError("schema_version must be semantic version text")
    snapshots = _validated_references(source_snapshot_ids, "source_snapshot_ids")
    evidence = _validated_references(evidence_ids, "evidence_ids")
    _require_declared_candidate_context(
        candidate,
        schema_version=normalized_schema_version,
        source_snapshot_ids=snapshots,
        evidence_ids=evidence,
    )
    (
        persisted_snapshots,
        persisted_evidence,
        source_snapshot_materializations,
        evidence_materializations,
        graph_source_snapshot_materializations,
        graph_evidence_materializations,
        data_source_snapshot_materializations,
        owned_evidence_materializations,
    ) = _publication_references(
        candidate,
        source_snapshot_ids=snapshots,
        evidence_ids=evidence,
        source_snapshot_bindings=source_snapshot_bindings,
        evidence_bindings=evidence_bindings,
        data_provenance_candidate=data_provenance_candidate,
    )
    context = ArtifactAdmissionContext(
        candidate=candidate,
        source_snapshot_ids=snapshots,
        evidence_ids=evidence,
        persisted_source_snapshot_ids=persisted_snapshots,
        persisted_evidence_ids=persisted_evidence,
    )
    for validator in (evidence_validator, domain_validator, quality_validator):
        if not callable(validator):
            raise PublicationAdmissionError("All publication validators are required")
        try:
            outcome = validator(context)
        except Exception as exc:
            raise PublicationAdmissionError(
                "Artifact candidate admission failed"
            ) from exc
        if outcome is not None:
            raise PublicationAdmissionError(
                "Publication validators must reject by raising and otherwise return None"
            )
    # Validators receive the typed object. Recheck the process-local commitment
    # before serialization so even an illicit in-validator mutation cannot publish.
    _require_pipeline_admission(candidate)
    _require_declared_candidate_context(
        candidate,
        schema_version=normalized_schema_version,
        source_snapshot_ids=snapshots,
        evidence_ids=evidence,
    )
    try:
        content = canonical_artifact_content_payload(candidate)
    except (TypeError, ValueError) as exc:
        raise PublicationAdmissionError(
            "Canonical Artifact content must remain valid after persistence serialization"
        ) from exc
    content_json = json.dumps(
        content,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    requires_quality_attestation = getattr(candidate, "kind", None) in {
        "dataset",
        "field_dictionary",
        "source_collection",
    }
    quality_projection = None
    if requires_quality_attestation:
        quality_projection = _quality_projection_from_attestation(
            candidate,
            getattr(quality_validator, "_data_quality_attestation", None),
        )
    return AdmittedArtifactCandidate(
        content_json=content_json,
        content_hash=compute_canonical_payload_hash(content),
        schema_version=normalized_schema_version,
        source_snapshot_ids=persisted_snapshots,
        evidence_ids=persisted_evidence,
        quality_projection=quality_projection,
        literature_source_snapshot_materializations=(source_snapshot_materializations),
        literature_evidence_materializations=evidence_materializations,
        graph_source_snapshot_materializations=(graph_source_snapshot_materializations),
        graph_evidence_materializations=graph_evidence_materializations,
        data_source_snapshot_materializations=data_source_snapshot_materializations,
        owned_evidence_materializations=owned_evidence_materializations,
        _seal=_ADMISSION_SEAL,
    )


def _build_admitted_candidate_authority(
    admitted_code: object,
) -> tuple[
    Callable[[AdmittedArtifactCandidate], None],
    Callable[[AdmittedArtifactCandidate], bool],
]:
    """Bind the generic wrapper to the exact admission call and payload.

    The constructor's private token alone is not an authority boundary in
    Python because module globals can be imported. Keep the registration
    ledger inside this closure, require the exact admission frame, and verify
    every immutable field again before any publication or replay.
    """

    lock = RLock()
    registry: dict[
        int,
        tuple[weakref.ReferenceType[AdmittedArtifactCandidate], tuple[object, ...]],
    ] = {}
    admitted_init_code = AdmittedArtifactCandidate.__init__.__code__

    def snapshot(value: AdmittedArtifactCandidate) -> tuple[object, ...]:
        return (
            value._content_json,
            value.content_hash,
            value.schema_version,
            tuple(value.source_snapshot_ids),
            tuple(value.evidence_ids),
            value._quality_projection_json,
            value.quality_projection_hash,
            tuple(value._literature_source_snapshot_materializations),
            tuple(value._literature_evidence_materializations),
            tuple(value._graph_source_snapshot_materializations),
            tuple(value._graph_evidence_materializations),
            tuple(value._data_source_snapshot_materializations),
            tuple(value._owned_evidence_materializations),
        )

    def register(value: AdmittedArtifactCandidate) -> None:
        init_frame = sys._getframe(1)
        admission_frame = init_frame.f_back
        if (
            init_frame.f_code is not admitted_init_code
            or init_frame.f_locals.get("self") is not value
            or admission_frame is None
            or admission_frame.f_code is not admitted_code
        ):
            raise PublicationAdmissionError(
                "Artifact candidate authority requires the active admission port"
            )
        object_id = id(value)

        def revoke(reference: weakref.ReferenceType[AdmittedArtifactCandidate]) -> None:
            with lock:
                current = registry.get(object_id)
                if current is not None and current[0] is reference:
                    registry.pop(object_id, None)

        reference = weakref.ref(value, revoke)
        with lock:
            registry[object_id] = (reference, snapshot(value))

    def verify(value: AdmittedArtifactCandidate) -> bool:
        if type(value) is not AdmittedArtifactCandidate:
            return False
        with lock:
            authority = registry.get(id(value))
        return (
            authority is not None
            and authority[0]() is value
            and authority[1] == snapshot(value)
        )

    return register, verify


(
    _register_admitted_candidate,
    _admitted_candidate_is_valid,
) = _build_admitted_candidate_authority(admit_artifact_candidate.__code__)
del _build_admitted_candidate_authority


@dataclass(frozen=True, slots=True)
class ArtifactPublication:
    artifact_id: UUID
    publication_key: str
    producer_execution_id: UUID
    candidate: AdmittedArtifactCandidate
    source_mode: SourceMode
    supersedes_version_id: UUID | None = None
    version_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class PublishedVersion:
    id: UUID
    artifact_id: UUID
    version_number: int
    publication_key: str
    content_hash: str
    source_mode: str
    supersedes_version_id: UUID | None


@dataclass(frozen=True, slots=True)
class PublicationResult:
    run_id: UUID
    status: str
    revision: int
    latest_event_sequence: int
    versions: tuple[PublishedVersion, ...]
    replayed: bool


class ProducerExecutionStore:
    """Short-transaction ledger around external producer calls."""

    def __init__(self, factory: Callable[[], Session]) -> None:
        self._factory = factory

    def start_producer_execution(
        self,
        request: ProducerExecutionRequest,
        *,
        token: UUID,
        generation: int,
        expected_status: str,
        expected_revision: int,
    ) -> ProducerExecutionSnapshot:
        parameters = _validated_parameters(request.parameters)
        _validate_execution_request(request)
        authorization = _validated_function_call_authorization(
            authorized_tool_name=request.authorized_tool_name,
            authorized_skill_id=request.authorized_skill_id,
            registry_revision=request.registry_revision,
        )
        parameters_hash = (
            request.parameters_hash
            if request.parameters_hash is not None
            else compute_canonical_payload_hash(parameters)
        )
        with self._factory() as session, session.begin():
            run = _lock_run(session, request.run_id)
            _require_active_lease(
                session,
                run,
                token=token,
                generation=generation,
                expected_status=expected_status,
                expected_revision=expected_revision,
            )
            step = _lock_step(session, request.run_id, request.step_key)
            attempt = session.scalar(
                select(StepAttemptModel)
                .where(
                    StepAttemptModel.id == request.attempt_id,
                    StepAttemptModel.run_step_id == step.id,
                )
                .with_for_update()
            )
            if (
                attempt is None
                or attempt.status != "running"
                or step.status != "running"
            ):
                raise ProducerExecutionConflictError(
                    "ProducerExecution requires the active running StepAttempt"
                )
            existing = session.scalar(
                select(ProducerExecutionModel)
                .where(
                    ProducerExecutionModel.run_step_id == step.id,
                    ProducerExecutionModel.idempotency_key == request.idempotency_key,
                )
                .with_for_update()
            )
            if existing is not None:
                _require_same_execution(
                    existing,
                    request=request,
                    step_id=step.id,
                    parameters=parameters,
                    parameters_hash=parameters_hash,
                    generation=generation,
                )
                resumable_parent = (
                    existing.status == "running"
                    and existing.producer_type == "model"
                    and existing.producer_name == "xingwen.paper_summary"
                    and parameters.get("resume_from_completed_children") is True
                )
                if resumable_parent:
                    existing.lease_generation = generation
                    session.flush()
                    return _execution_snapshot(existing)
                return _execution_snapshot(existing, replayed=True)
            row = ProducerExecutionModel(
                id=uuid4(),
                run_id=request.run_id,
                run_step_id=step.id,
                step_attempt_id=attempt.id,
                step_key=step.key,
                idempotency_key=request.idempotency_key,
                lease_generation=generation,
                producer_type=request.producer_type,
                producer_name=request.producer_name.strip(),
                producer_version=request.producer_version.strip(),
                model_provider=_optional_text(request.model_provider),
                requested_model=_optional_text(request.requested_model),
                provider_returned_model=None,
                provider_request_id=None,
                explicit_revision=_optional_text(request.explicit_revision),
                prompt_name=_optional_text(request.prompt_name),
                prompt_version=_optional_text(request.prompt_version),
                prompt_hash=request.prompt_hash,
                parameters=parameters,
                parameters_hash=parameters_hash,
                input_hash=request.input_hash,
                status="running",
                started_at=session.scalar(select(func.clock_timestamp())),
                authorized_tool_name=authorization["authorized_tool_name"],
                authorized_skill_id=authorization["authorized_skill_id"],
                registry_revision=authorization["registry_revision"],
            )
            session.add(row)
            session.flush()
            return _execution_snapshot(row)

    def find_completed_model_execution(
        self,
        request: ProducerExecutionRequest,
    ) -> ProducerExecutionSnapshot | None:
        """Return an exact completed model response for resumable child work."""

        parameters = _validated_parameters(request.parameters)
        _validate_execution_request(request)
        parameters_hash = request.parameters_hash or compute_canonical_payload_hash(
            parameters
        )
        with self._factory() as session:
            row = session.scalar(
                select(ProducerExecutionModel)
                .where(
                    ProducerExecutionModel.run_id == request.run_id,
                    ProducerExecutionModel.step_key == request.step_key,
                    ProducerExecutionModel.producer_type == "model",
                    ProducerExecutionModel.producer_name
                    == request.producer_name.strip(),
                    ProducerExecutionModel.producer_version
                    == request.producer_version.strip(),
                    ProducerExecutionModel.input_hash == request.input_hash,
                    ProducerExecutionModel.parameters_hash == parameters_hash,
                    ProducerExecutionModel.model_provider
                    == _optional_text(request.model_provider),
                    ProducerExecutionModel.requested_model
                    == _optional_text(request.requested_model),
                    ProducerExecutionModel.explicit_revision
                    == _optional_text(request.explicit_revision),
                    ProducerExecutionModel.prompt_name
                    == _optional_text(request.prompt_name),
                    ProducerExecutionModel.prompt_version
                    == _optional_text(request.prompt_version),
                    ProducerExecutionModel.prompt_hash == request.prompt_hash,
                    ProducerExecutionModel.status == "completed",
                    ProducerExecutionModel.model_response.is_not(None),
                )
                .order_by(ProducerExecutionModel.finished_at.desc())
            )
        if row is None or row.parameters != parameters:
            return None
        return _execution_snapshot(row, replayed=True)

    def finish_producer_execution(
        self,
        execution_id: UUID,
        *,
        status: str,
        output_hash: str | None = None,
        token_usage: Mapping[str, int] | None = None,
        latency_ms: int | None = None,
        input_hash: str | None = None,
        provider_returned_model: str | None = None,
        provider_request_id: str | None = None,
        error_code: str | None = None,
        tool_call_id: str | None = None,
        validated_arguments_hash: str | None = None,
        rejected_arguments_hash: str | None = None,
        error_hash: str | None = None,
        public_message: str | None = None,
        model_response: Mapping[str, object] | None = None,
    ) -> ProducerExecutionSnapshot:
        _validate_execution_outcome(
            status=status,
            output_hash=output_hash,
            token_usage=token_usage,
            latency_ms=latency_ms,
            error_code=error_code,
        )
        audit = _validated_function_call_audit(
            status=status,
            tool_call_id=tool_call_id,
            validated_arguments_hash=validated_arguments_hash,
            rejected_arguments_hash=rejected_arguments_hash,
            error_hash=error_hash,
            public_message=public_message,
        )
        usage = _validated_usage(token_usage)
        normalized_error = _optional_text(error_code)
        if input_hash is not None and (
            len(input_hash) != 71 or not input_hash.startswith("sha256:")
        ):
            raise ValueError(
                "ProducerExecution input_hash must be a sha256 content hash"
            )
        normalized_provider_model = _optional_text(provider_returned_model)
        normalized_provider_request_id = _optional_text(provider_request_id)
        normalized_model_response = (
            dict(model_response) if model_response is not None else None
        )
        with self._factory() as session, session.begin():
            row = session.scalar(
                select(ProducerExecutionModel)
                .where(ProducerExecutionModel.id == execution_id)
                .with_for_update()
            )
            if row is None:
                raise ProducerExecutionNotFoundError(
                    f"ProducerExecution {execution_id} was not found"
                )
            if row.status != "running":
                if (
                    row.status == status
                    and row.output_hash == output_hash
                    and row.token_usage == usage
                    and (input_hash is None or row.input_hash == input_hash)
                    and row.latency_ms == latency_ms
                    and row.provider_returned_model == normalized_provider_model
                    and row.provider_request_id == normalized_provider_request_id
                    and row.error_code == normalized_error
                    and row.tool_call_id == audit["tool_call_id"]
                    and row.validated_arguments_hash
                    == audit["validated_arguments_hash"]
                    and row.rejected_arguments_hash == audit["rejected_arguments_hash"]
                    and row.error_hash == audit["error_hash"]
                    and row.public_message == audit["public_message"]
                    and row.model_response == normalized_model_response
                ):
                    return _execution_snapshot(row)
                raise ProducerExecutionConflictError(
                    "ProducerExecution already finished with a different outcome"
                )
            row.status = status
            row.output_hash = output_hash
            row.token_usage = usage
            row.latency_ms = latency_ms
            if input_hash is not None:
                row.input_hash = input_hash
            row.provider_returned_model = normalized_provider_model
            row.provider_request_id = normalized_provider_request_id
            row.error_code = normalized_error
            row.tool_call_id = audit["tool_call_id"]
            row.validated_arguments_hash = audit["validated_arguments_hash"]
            row.rejected_arguments_hash = audit["rejected_arguments_hash"]
            row.error_hash = audit["error_hash"]
            row.public_message = audit["public_message"]
            row.model_response = normalized_model_response
            row.finished_at = session.scalar(select(func.clock_timestamp()))
            session.flush()
            return _execution_snapshot(row)


class ArtifactPublisher:
    """Publish one complete Step output set in a single fenced transaction."""

    def __init__(self, factory: Callable[[], Session]) -> None:
        self._factory = factory

    def publish_step_outputs(
        self,
        run_id: UUID,
        *,
        step_key: str,
        attempt_id: UUID,
        token: UUID,
        generation: int,
        expected_status: str,
        expected_revision: int,
        publications: Sequence[ArtifactPublication],
        public_message: str,
        activity_id: str | None = None,
        activity_name: str | None = None,
    ) -> PublicationResult:
        outputs = _validated_publications(publications)
        with self._factory() as session, session.begin():
            run = _lock_run(session, run_id)
            step = _lock_step(session, run_id, step_key)
            artifacts = tuple(
                session.scalars(
                    select(ResearchArtifactModel)
                    .where(
                        ResearchArtifactModel.id.in_(
                            output.artifact_id for output in outputs
                        ),
                        ResearchArtifactModel.project_id == run.project_id,
                    )
                    .order_by(ResearchArtifactModel.id)
                    .with_for_update()
                )
            )
            if len(artifacts) != len(outputs):
                raise PublicationResourceNotFoundError(
                    "A target ResearchArtifact was not found in the Run Project"
                )
            artifacts_by_id = {artifact.id: artifact for artifact in artifacts}
            for output in outputs:
                _validate_candidate_artifact_kind(
                    artifacts_by_id[output.artifact_id],
                    output.candidate,
                )
                _validate_export_references(
                    session,
                    output.candidate,
                    project_id=run.project_id,
                )
            existing = _existing_publications(session, outputs)
            if existing:
                return self._replay_existing(
                    session,
                    run=run,
                    step=step,
                    attempt_id=attempt_id,
                    outputs=outputs,
                    existing=existing,
                )
            _require_active_lease(
                session,
                run,
                token=token,
                generation=generation,
                expected_status=expected_status,
                expected_revision=expected_revision,
            )
            if step.status != "running" or run.status != step.enter_status:
                raise StalePublicationError(
                    "Only the active running RunStep may publish outputs"
                )
            attempt = session.scalar(
                select(StepAttemptModel)
                .where(
                    StepAttemptModel.id == attempt_id,
                    StepAttemptModel.run_step_id == step.id,
                )
                .with_for_update()
            )
            if attempt is None or attempt.status != "running":
                raise StalePublicationError(
                    "Only the active running StepAttempt may publish outputs"
                )
            producers = _lock_producers(session, outputs)
            producer_by_id = {producer.id: producer for producer in producers}
            versions: list[ArtifactVersionModel] = []
            for output in outputs:
                artifact = artifacts_by_id[output.artifact_id]
                producer = producer_by_id.get(output.producer_execution_id)
                _validate_publishable_producer(
                    producer,
                    run_id=run.id,
                    step_id=step.id,
                    attempt_id=attempt.id,
                    output=output,
                )
                _validate_supersedes(
                    session,
                    artifact=artifact,
                    supersedes_version_id=output.supersedes_version_id,
                )
                version_number = (
                    session.scalar(
                        select(
                            func.coalesce(
                                func.max(ArtifactVersionModel.version_number), 0
                            )
                        ).where(ArtifactVersionModel.artifact_id == artifact.id)
                    )
                    + 1
                )
                _validate_literature_source_snapshots(
                    session,
                    output.candidate,
                    project_id=run.project_id,
                )
                _require_unused_literature_evidence_ids(session, output.candidate)
                _validate_graph_source_snapshots(
                    session,
                    output.candidate,
                    project_id=run.project_id,
                )
                _validate_graph_upstream_evidence(
                    session,
                    output.candidate,
                    project_id=run.project_id,
                )
                _require_unused_graph_evidence_ids(session, output.candidate)
                _validate_data_source_snapshots(
                    session,
                    output.candidate,
                    project_id=run.project_id,
                )
                _validate_owned_evidence_sources(
                    session, output.candidate, project_id=run.project_id
                )
                _require_unused_owned_evidence_ids(session, output.candidate)
                version_id = output.version_id or uuid4()
                version = ArtifactVersionModel(
                    id=version_id,
                    artifact_id=artifact.id,
                    project_id=run.project_id,
                    created_by_run_id=run.id,
                    run_step_id=step.id,
                    step_attempt_id=attempt.id,
                    producer_execution_id=producer.id,
                    version_number=version_number,
                    publication_key=output.publication_key,
                    schema_version=output.candidate.schema_version,
                    content=output.candidate.content,
                    content_hash=output.candidate.content_hash,
                    input_hash=producer.input_hash,
                    source_mode=SourceMode(output.source_mode).value,
                    producer=_public_producer_metadata(producer),
                    source_snapshot_ids=list(output.candidate.source_snapshot_ids),
                    evidence_ids=list(output.candidate.evidence_ids),
                    quality_projection=(
                        output.candidate.quality_projection.model_dump(mode="json")
                        if output.candidate.quality_projection is not None
                        else None
                    ),
                    quality_projection_hash=output.candidate.quality_projection_hash,
                    supersedes_version_id=output.supersedes_version_id,
                )
                session.add(version)
                session.flush()
                _materialize_literature_evidence(session, version, output.candidate)
                _materialize_graph_evidence(session, version, output.candidate)
                _materialize_owned_evidence(session, version, output.candidate)
                if output.candidate.content.get("kind") == "dataset":
                    for row in output.candidate.content.get("rows", []):
                        if isinstance(row, dict) and isinstance(row.get("row_id"), str):
                            session.add(
                                DatasetRowProjectionModel(
                                    artifact_version_id=version.id,
                                    project_id=version.project_id,
                                    row_id=row["row_id"],
                                    row=row,
                                )
                            )
                versions.append(version)
            session.flush()
            for version in versions:
                artifacts_by_id[version.artifact_id].latest_version_id = version.id

            now = session.scalar(select(func.clock_timestamp()))
            attempt.status = "completed"
            attempt.finished_at = now
            attempt.error_class = None
            attempt.error_code = None
            attempt.retryable = False
            step.status = "completed"
            step.progress = 100
            step.finished_at = now
            step.failure_code = None
            step.public_message = public_message
            total_steps = session.scalar(
                select(func.count())
                .select_from(RunStepModel)
                .where(RunStepModel.run_id == run.id)
            )
            is_final = step.success_status == "completed"
            progress = (
                100
                if is_final
                else max(run.progress, int(((step.position + 1) / total_steps) * 100))
            )
            artifact_version_ids = [str(version.id) for version in versions]
            sequence = run.latest_event_sequence + 1
            session.add(
                RunEventModel(
                    run_id=run.id,
                    sequence=sequence,
                    activity_id=activity_id or str(attempt.id),
                    activity_kind="artifact" if versions else "tool",
                    activity_phase="completed",
                    activity_name=activity_name or public_message,
                    step_key=step.key,
                    progress=progress,
                    content=public_message,
                    details={"artifact_count": len(artifact_version_ids)},
                    artifact_version_ids=artifact_version_ids,
                )
            )
            if is_final:
                sequence += 1
                session.add(
                    RunEventModel(
                        run_id=run.id,
                        sequence=sequence,
                        activity_id=f"run:{run.id}",
                        activity_kind="completion",
                        activity_phase="completed",
                        activity_name="研究任务",
                        step_key=step.key,
                        progress=100,
                        content="研究任务已完成。",
                        details={},
                        artifact_version_ids=artifact_version_ids,
                    )
                )
                completion_entry = next(
                    (
                        entry
                        for entry in session.scalars(
                            select(ResearchThreadEntryModel).where(
                                ResearchThreadEntryModel.project_id == run.project_id,
                                ResearchThreadEntryModel.kind == "assistant_message",
                            )
                        )
                        if entry.structured_payload.get("run_id") == str(run.id)
                        and entry.structured_payload.get("outcome") == "completed"
                    ),
                    None,
                )
                if completion_entry is None:
                    artifact_count = len(artifact_version_ids)
                    append_assistant_message(
                        session,
                        project_id=run.project_id,
                        public_content=(
                            "研究任务已完成。"
                            if artifact_count == 0
                            else f"研究任务已完成，已生成 {artifact_count} 项研究产物。"
                        ),
                        structured_payload={
                            "outcome": "completed",
                            "run_id": str(run.id),
                            "artifact_version_ids": artifact_version_ids,
                            "warnings": [],
                            "draft_id": None,
                            "missing_information": [],
                            "reason": None,
                            "error_code": None,
                        },
                    )
                run.finished_at = now
                run.lease_token = None
                run.lease_owner = None
                run.lease_expires_at = None
            run.status = step.success_status
            run.progress = progress
            run.revision += 1
            run.latest_event_sequence = sequence
            run.updated_at = now
            self._before_commit(session)
            session.flush()
            return PublicationResult(
                run_id=run.id,
                status=run.status,
                revision=run.revision,
                latest_event_sequence=sequence,
                versions=tuple(_published_version(version) for version in versions),
                replayed=False,
            )

    def _replay_existing(
        self,
        session: Session,
        *,
        run: ResearchRunModel,
        step: RunStepModel,
        attempt_id: UUID,
        outputs: tuple[ArtifactPublication, ...],
        existing: Mapping[tuple[UUID, str], ArtifactVersionModel],
    ) -> PublicationResult:
        if len(existing) != len(outputs) or step.status != "completed":
            raise PublicationConflictError(
                "A publication key exists outside a completed atomic output set"
            )
        versions: list[ArtifactVersionModel] = []
        for output in outputs:
            version = existing[(output.artifact_id, output.publication_key)]
            producer = session.scalar(
                select(ProducerExecutionModel).where(
                    ProducerExecutionModel.id == output.producer_execution_id
                )
            )
            if producer is None:
                raise PublicationAdmissionError(
                    "Publication requires a completed matching ProducerExecution"
                )
            _require_same_publication(
                version,
                producer=producer,
                run_id=run.id,
                step_id=step.id,
                attempt_id=attempt_id,
                output=output,
            )
            _validate_publishable_producer(
                producer,
                run_id=run.id,
                step_id=step.id,
                attempt_id=attempt_id,
                output=output,
            )
            _validate_materialized_literature_provenance(
                session, version, output.candidate
            )
            _validate_materialized_graph_provenance(session, version, output.candidate)
            _validate_materialized_data_provenance(session, version, output.candidate)
            _validate_materialized_owned_evidence(session, version, output.candidate)
            versions.append(version)
        completed_event = session.scalar(
            select(RunEventModel)
            .where(
                RunEventModel.run_id == run.id,
                RunEventModel.step_key == step.key,
                RunEventModel.activity_phase == "completed",
            )
            .order_by(RunEventModel.sequence.desc())
        )
        expected_ids = {str(version.id) for version in versions}
        if (
            completed_event is None
            or set(completed_event.artifact_version_ids) != expected_ids
        ):
            raise PublicationConflictError(
                "The idempotent publication set differs from the completed Step event"
            )
        return PublicationResult(
            run_id=run.id,
            status=run.status,
            revision=run.revision,
            latest_event_sequence=run.latest_event_sequence,
            versions=tuple(_published_version(version) for version in versions),
            replayed=True,
        )

    def _before_commit(self, session: Session) -> None:
        """Test seam used to prove the surrounding transaction rolls back."""


def _lock_run(session: Session, run_id: UUID) -> ResearchRunModel:
    run = session.scalar(
        select(ResearchRunModel).where(ResearchRunModel.id == run_id).with_for_update()
    )
    if run is None:
        raise PublicationResourceNotFoundError(f"ResearchRun {run_id} was not found")
    return run


def _lock_step(session: Session, run_id: UUID, step_key: str) -> RunStepModel:
    step = session.scalar(
        select(RunStepModel)
        .where(RunStepModel.run_id == run_id, RunStepModel.key == step_key)
        .with_for_update()
    )
    if step is None:
        raise PublicationResourceNotFoundError(
            f"RunStep {step_key!r} was not found for the Run"
        )
    return step


def _require_active_lease(
    session: Session,
    run: ResearchRunModel,
    *,
    token: UUID,
    generation: int,
    expected_status: str,
    expected_revision: int,
) -> None:
    now = session.scalar(select(func.clock_timestamp()))
    if (
        run.status != expected_status
        or run.revision != expected_revision
        or run.lease_token != token
        or run.lease_generation != generation
        or run.lease_expires_at is None
        or run.lease_expires_at <= now
        or run.status in TERMINAL_RUN_STATUSES
    ):
        raise StalePublicationError(
            "Run status, revision, lease token, or lease generation is stale"
        )


def _validate_execution_request(request: ProducerExecutionRequest) -> None:
    for name, value in (
        ("step_key", request.step_key),
        ("idempotency_key", request.idempotency_key),
        ("producer_name", request.producer_name),
        ("producer_version", request.producer_version),
    ):
        if not value.strip():
            raise ValueError(f"{name} is required")
    if request.producer_type not in _PRODUCER_TYPES:
        raise ValueError("producer_type must be pipeline, model, or algorithm")
    _require_hash(request.input_hash, "input_hash")
    if request.parameters_hash is not None:
        _require_hash(request.parameters_hash, "parameters_hash")
    if request.prompt_hash is not None:
        _require_hash(request.prompt_hash, "prompt_hash")


def _validated_parameters(
    parameters: Mapping[str, ProducerParameter],
) -> dict[str, ProducerParameter]:
    if not isinstance(parameters, Mapping) or len(parameters) > 32:
        raise ValueError("parameters must be a mapping with at most 32 entries")
    safe: dict[str, ProducerParameter] = {}
    for key, value in parameters.items():
        if (
            not isinstance(key, str)
            or not _PARAMETER_KEY_PATTERN.fullmatch(key)
            or producer_parameter_key_is_sensitive(key)
        ):
            raise ValueError("parameters contain a forbidden or invalid key")
        if not isinstance(value, (str, int, float, bool, type(None))):
            raise ValueError("parameters may contain only scalar JSON values")
        if isinstance(value, str) and len(value) > 256:
            raise ValueError("parameter strings must not contain long raw content")
        safe[key] = value
    return safe


def producer_parameter_key_is_sensitive(key: str) -> bool:
    """Return whether a normalized producer key denotes credential material."""
    segments = frozenset(key.split("_"))
    return (
        any(fragment in key for fragment in _SENSITIVE_PARAMETER_KEY_FRAGMENTS)
        or (
            bool(segments & {"token", "tokens"})
            and bool(segments & _TOKEN_CREDENTIAL_QUALIFIERS)
        )
        or (
            bool(segments & {"key", "keys"})
            and bool(segments & _KEY_CREDENTIAL_QUALIFIERS)
        )
        or (
            bool(segments & {"header", "headers"})
            and bool(segments & _HEADER_CREDENTIAL_QUALIFIERS)
        )
    )


def _validated_usage(usage: Mapping[str, int] | None) -> dict[str, int] | None:
    if usage is None:
        return None
    if not isinstance(usage, Mapping) or len(usage) > 16:
        raise ValueError("token_usage must be a small mapping")
    validated: dict[str, int] = {}
    for key, value in usage.items():
        if (
            not _PARAMETER_KEY_PATTERN.fullmatch(key)
            or not isinstance(value, int)
            or value < 0
        ):
            raise ValueError("token_usage values must be nonnegative integers")
        validated[key] = value
    return validated


def _validate_execution_outcome(
    *,
    status: str,
    output_hash: str | None,
    token_usage: Mapping[str, int] | None,
    latency_ms: int | None,
    error_code: str | None,
) -> None:
    if status not in _PRODUCER_TERMINAL_STATUSES:
        raise ValueError("ProducerExecution must finish in a terminal status")
    if output_hash is not None:
        _require_hash(output_hash, "output_hash")
    if status == "completed" and output_hash is None:
        raise ValueError("completed ProducerExecution requires output_hash")
    if status in {"failed", "rejected"} and not (error_code or "").strip():
        raise ValueError("failed or rejected ProducerExecution requires error_code")
    if latency_ms is not None and latency_ms < 0:
        raise ValueError("latency_ms must be nonnegative")
    _validated_usage(token_usage)


def _validated_function_call_authorization(
    *,
    authorized_tool_name: str | None,
    authorized_skill_id: str | None,
    registry_revision: str | None,
) -> dict[str, str | None]:
    """Authorization identity for one governed function-calling producer.

    The trio is all-or-nothing: either the complete authorization identity is
    recorded, or none of it is. Partial authorization cannot masquerade as a
    governed tool call.
    """

    values = (authorized_tool_name, authorized_skill_id, registry_revision)
    if all(value is None for value in values):
        return {
            "authorized_tool_name": None,
            "authorized_skill_id": None,
            "registry_revision": None,
        }
    if any(value is None for value in values):
        raise ValueError(
            "function-call authorization requires tool, skill and registry identity"
        )
    tool = _optional_text(authorized_tool_name)
    skill = _optional_text(authorized_skill_id)
    revision = _optional_text(registry_revision)
    if tool is None or skill is None or revision is None:
        raise ValueError("function-call authorization fields must be non-blank")
    if len(tool) > 128 or len(skill) > 128 or len(revision) > 71:
        raise ValueError("function-call authorization field is too long")
    return {
        "authorized_tool_name": tool,
        "authorized_skill_id": skill,
        "registry_revision": revision,
    }


def _validated_function_call_audit(
    *,
    status: str,
    tool_call_id: str | None,
    validated_arguments_hash: str | None,
    rejected_arguments_hash: str | None,
    error_hash: str | None,
    public_message: str | None,
) -> dict[str, str | None]:
    """Validate the terminal audit facts against the closure invariants.

    Producers that do not use function calling leave the audit fields empty;
    once any audit fact is supplied the full closure is enforced.
    """

    if all(
        value is None
        for value in (
            tool_call_id,
            validated_arguments_hash,
            rejected_arguments_hash,
            error_hash,
            public_message,
        )
    ):
        return {
            "tool_call_id": None,
            "validated_arguments_hash": None,
            "rejected_arguments_hash": None,
            "error_hash": None,
            "public_message": None,
        }
    for label, value in (
        ("validated_arguments_hash", validated_arguments_hash),
        ("rejected_arguments_hash", rejected_arguments_hash),
        ("error_hash", error_hash),
    ):
        if value is not None:
            _require_hash(value, label)
    normalized_call_id = _optional_text(tool_call_id)
    if normalized_call_id is not None and len(normalized_call_id) > 256:
        raise ValueError("tool_call_id is too long")
    normalized_message = public_message.strip() if public_message else None
    if status == "completed":
        if (
            normalized_call_id is None
            or validated_arguments_hash is None
            or not normalized_message
        ):
            raise ValueError(
                "completed function-call producer requires tool_call_id, "
                "validated arguments hash and public message"
            )
        if rejected_arguments_hash is not None or error_hash is not None:
            raise ValueError(
                "completed function-call producer cannot carry rejection facts"
            )
        return {
            "tool_call_id": normalized_call_id,
            "validated_arguments_hash": validated_arguments_hash,
            "rejected_arguments_hash": None,
            "error_hash": None,
            "public_message": normalized_message,
        }
    if status == "rejected":
        if error_hash is None:
            raise ValueError("rejected function-call producer requires error_hash")
        if validated_arguments_hash is not None or public_message:
            raise ValueError(
                "rejected function-call producer cannot carry validated facts"
            )
        return {
            "tool_call_id": normalized_call_id,
            "validated_arguments_hash": None,
            "rejected_arguments_hash": rejected_arguments_hash,
            "error_hash": error_hash,
            "public_message": None,
        }
    if normalized_call_id is not None or validated_arguments_hash is not None:
        raise ValueError(
            "failed or cancelled function-call producer cannot carry tool facts"
        )
    if rejected_arguments_hash is not None:
        raise ValueError(
            "failed or cancelled function-call producer cannot carry rejection facts"
        )
    return {
        "tool_call_id": None,
        "validated_arguments_hash": None,
        "rejected_arguments_hash": None,
        "error_hash": error_hash,
        "public_message": None,
    }


def _require_same_execution(
    row: ProducerExecutionModel,
    *,
    request: ProducerExecutionRequest,
    step_id: UUID,
    parameters: Mapping[str, ProducerParameter],
    parameters_hash: str,
    generation: int,
) -> None:
    expected = (
        request.run_id,
        step_id,
        request.attempt_id,
        request.step_key,
        request.producer_type,
        request.producer_name.strip(),
        request.producer_version.strip(),
        _optional_text(request.model_provider),
        _optional_text(request.requested_model),
        _optional_text(request.explicit_revision),
        _optional_text(request.prompt_name),
        _optional_text(request.prompt_version),
        request.prompt_hash,
        dict(parameters),
        parameters_hash,
        _optional_text(request.authorized_tool_name),
        _optional_text(request.authorized_skill_id),
        _optional_text(request.registry_revision),
    )
    actual = (
        row.run_id,
        row.run_step_id,
        row.step_attempt_id,
        row.step_key,
        row.producer_type,
        row.producer_name,
        row.producer_version,
        row.model_provider,
        row.requested_model,
        row.explicit_revision,
        row.prompt_name,
        row.prompt_version,
        row.prompt_hash,
        row.parameters,
        row.parameters_hash,
        row.authorized_tool_name,
        row.authorized_skill_id,
        row.registry_revision,
    )
    resumable_parent = (
        row.producer_type == "model"
        and row.producer_name == "xingwen.paper_summary"
        and parameters.get("resume_from_completed_children") is True
    )
    if row.status == "running" and (
        row.input_hash != request.input_hash
        or (row.lease_generation != generation and not resumable_parent)
    ):
        raise ProducerExecutionConflictError(
            "ProducerExecution idempotency key was reused with different input"
        )
    if actual != expected:
        raise ProducerExecutionConflictError(
            "ProducerExecution idempotency key was reused with a different request"
        )


def _execution_snapshot(
    row: ProducerExecutionModel, *, replayed: bool = False
) -> ProducerExecutionSnapshot:
    return ProducerExecutionSnapshot(
        id=row.id,
        run_id=row.run_id,
        run_step_id=row.run_step_id,
        step_attempt_id=row.step_attempt_id,
        step_key=row.step_key,
        idempotency_key=row.idempotency_key,
        lease_generation=row.lease_generation,
        producer_type=row.producer_type,
        producer_name=row.producer_name,
        producer_version=row.producer_version,
        model_provider=row.model_provider,
        requested_model=row.requested_model,
        provider_returned_model=row.provider_returned_model,
        provider_request_id=row.provider_request_id,
        explicit_revision=row.explicit_revision,
        prompt_name=row.prompt_name,
        prompt_version=row.prompt_version,
        prompt_hash=row.prompt_hash,
        parameters=dict(row.parameters),
        parameters_hash=row.parameters_hash,
        input_hash=row.input_hash,
        output_hash=row.output_hash,
        status=row.status,
        started_at=row.started_at,
        finished_at=row.finished_at,
        token_usage=dict(row.token_usage) if row.token_usage is not None else None,
        latency_ms=row.latency_ms,
        error_code=row.error_code,
        model_response=(
            dict(row.model_response) if row.model_response is not None else None
        ),
        replayed=replayed,
    )


def _validated_references(values: Sequence[str], name: str) -> tuple[str, ...]:
    references = tuple(values)
    if len(references) != len(set(references)) or any(
        not isinstance(value, str) or not value.strip() for value in references
    ):
        raise PublicationAdmissionError(f"{name} must contain unique nonempty ids")
    return references


def _require_declared_candidate_context(
    candidate: BaseModel,
    *,
    schema_version: str,
    source_snapshot_ids: tuple[str, ...],
    evidence_ids: tuple[str, ...],
) -> None:
    """Keep caller-supplied publication context bound to typed candidate fields."""

    if not getattr(
        candidate.__class__, "__artifact_publication_requires_admission__", False
    ):
        return

    declared_schema_version = getattr(candidate, "schema_version", None)
    if (
        declared_schema_version is not None
        and declared_schema_version != schema_version
    ):
        raise PublicationAdmissionError("schema_version must match the typed candidate")
    for field, supplied in (
        ("source_snapshot_ids", source_snapshot_ids),
        ("evidence_ids", evidence_ids),
    ):
        declared = getattr(candidate, field, None)
        if declared is not None and tuple(declared) != supplied:
            raise PublicationAdmissionError(f"{field} must match the typed candidate")


def _require_pipeline_admission(candidate: BaseModel) -> None:
    candidate_class = candidate.__class__
    candidate_kind = normalize_artifact_kind(getattr(candidate, "kind", None))
    expected_class = canonical_artifact_content_model(candidate_kind)
    if expected_class is None:
        raise PublicationAdmissionError(
            f"{candidate_kind or 'unknown'} candidate cannot bypass its authoritative publication pipeline"
        )
    if candidate_class is not expected_class:
        messages = {
            "graph": "graph requires the authoritative Evidence Graph Pipeline candidate",
            "literature_claims": (
                "literature_claims cannot bypass its authoritative Pipeline candidate"
            ),
            "literature_relations": (
                "literature_relations requires the authoritative Pipeline candidate"
            ),
        }
        raise PublicationAdmissionError(
            messages.get(
                candidate_kind,
                f"{candidate_kind} requires its authoritative Pipeline candidate",
            )
        )

    if not getattr(
        candidate_class, "__artifact_publication_requires_admission__", False
    ):
        return
    # Resolve the verifier on the class and invoke it unbound. Looking it up on
    # the instance would let an injected instance attribute shadow the sealed
    # implementation.
    admission_check = getattr(
        candidate_class, "__artifact_publication_is_admitted__", None
    )
    try:
        admitted = callable(admission_check) and admission_check(candidate) is True
    except Exception as exc:
        raise PublicationAdmissionError(
            "Model output cannot bypass its artifact admission pipeline"
        ) from exc
    if not admitted:
        raise PublicationAdmissionError(
            "Model output cannot bypass its artifact admission pipeline"
        )


def _publication_references(
    candidate: BaseModel,
    *,
    source_snapshot_ids: tuple[str, ...],
    evidence_ids: tuple[str, ...],
    source_snapshot_bindings: Sequence[ArtifactSourceSnapshotBinding] | None,
    evidence_bindings: Sequence[ArtifactEvidenceBinding] | None,
    data_provenance_candidate: BaseModel | None,
) -> tuple[
    tuple[str, ...],
    tuple[str, ...],
    tuple[_LiteratureSourceSnapshotMaterialization, ...],
    tuple[_LiteratureEvidenceMaterialization, ...],
    tuple[_GraphSourceSnapshotMaterialization, ...],
    tuple[_GraphEvidenceMaterialization, ...],
    tuple[_DataSourceSnapshotMaterialization, ...],
    tuple[_OwnedEvidenceMaterialization, ...],
]:
    candidate_kind = getattr(candidate, "kind", None)
    if hasattr(candidate_kind, "value"):
        candidate_kind = candidate_kind.value
    if candidate_kind == "graph":
        return _graph_publication_references(
            candidate,
            source_snapshot_ids=source_snapshot_ids,
            evidence_ids=evidence_ids,
            source_snapshot_bindings=source_snapshot_bindings,
            evidence_bindings=evidence_bindings,
        )
    if candidate_kind in {"dataset", "field_dictionary", "source_collection"}:
        return _data_publication_references(
            candidate,
            source_snapshot_ids=source_snapshot_ids,
            evidence_ids=evidence_ids,
            source_snapshot_bindings=source_snapshot_bindings,
            evidence_bindings=evidence_bindings,
            data_provenance_candidate=data_provenance_candidate,
        )
    if candidate_kind == "paper_collection":
        return _paper_collection_publication_references(
            candidate,
            source_snapshot_ids=source_snapshot_ids,
            evidence_ids=evidence_ids,
            source_snapshot_bindings=source_snapshot_bindings,
            evidence_bindings=evidence_bindings,
        )
    if candidate_kind == "paper_summary":
        return _paper_summary_publication_references(
            candidate,
            source_snapshot_ids=source_snapshot_ids,
            evidence_ids=evidence_ids,
            source_snapshot_bindings=source_snapshot_bindings,
            evidence_bindings=evidence_bindings,
        )
    if candidate_kind in _SCIENTIFIC_ARTIFACT_KINDS:
        return _scientific_publication_references(
            candidate,
            source_snapshot_ids=source_snapshot_ids,
            evidence_ids=evidence_ids,
            source_snapshot_bindings=source_snapshot_bindings,
            evidence_bindings=evidence_bindings,
        )
    if candidate_kind not in {"literature_claims", "literature_relations"}:
        if source_snapshot_bindings is not None or evidence_bindings is not None:
            raise PublicationAdmissionError(
                "Explicit provenance bindings are only supported for admitted domain artifacts"
            )
        return source_snapshot_ids, evidence_ids, (), (), (), (), (), ()
    if source_snapshot_bindings is None or evidence_bindings is None:
        raise PublicationAdmissionError(
            "Literature artifact publication requires explicit persisted provenance bindings"
        )

    snapshot_references = _literature_snapshot_references(candidate)
    if set(snapshot_references) != set(source_snapshot_ids):
        raise PublicationAdmissionError(
            "Literature candidate SourceSnapshot registry is not self-consistent"
        )
    snapshots = tuple(source_snapshot_bindings)
    pipeline_snapshot_ids = tuple(
        item.pipeline_source_snapshot_id for item in snapshots
    )
    persisted_snapshot_ids = tuple(
        item.persisted_source_snapshot_id for item in snapshots
    )
    try:
        persisted_snapshot_uuids = tuple(UUID(item) for item in persisted_snapshot_ids)
    except ValueError as exc:
        raise PublicationAdmissionError(
            "Persisted SourceSnapshot bindings must use UUID identifiers"
        ) from exc
    if (
        tuple(sorted(pipeline_snapshot_ids)) != tuple(sorted(source_snapshot_ids))
        or len(pipeline_snapshot_ids) != len(set(pipeline_snapshot_ids))
        or len(persisted_snapshot_uuids) != len(set(persisted_snapshot_uuids))
        or any(not item.pipeline_source_snapshot_id.strip() for item in snapshots)
    ):
        raise PublicationAdmissionError(
            "SourceSnapshot bindings must exactly cover the literature candidate"
        )
    persisted_snapshot_by_pipeline = {
        item.pipeline_source_snapshot_id: item.persisted_source_snapshot_id
        for item in snapshots
    }
    source_materializations = tuple(
        _LiteratureSourceSnapshotMaterialization(
            pipeline_source_snapshot_id=item.pipeline_source_snapshot_id,
            persisted_source_snapshot_id=item.persisted_source_snapshot_id,
            source_id=snapshot_references[item.pipeline_source_snapshot_id][0],
            source_version=snapshot_references[item.pipeline_source_snapshot_id][1],
            content_hash=snapshot_references[item.pipeline_source_snapshot_id][2],
        )
        for item in sorted(
            snapshots, key=lambda value: value.pipeline_source_snapshot_id
        )
    )

    expected_evidence: dict[tuple[str, str, str, str], object] = {}
    for reference in getattr(candidate, "evidence_references", ()):
        targets = (
            (("claim", reference.claim_id),)
            if candidate_kind == "literature_claims"
            else (
                ("claim", reference.claim_id),
                ("relation", reference.relation_id),
            )
        )
        for target_type, target_id in targets:
            key = (
                target_type,
                target_id,
                reference.evidence_id,
                reference.source_snapshot_id,
            )
            existing = expected_evidence.get(key)
            if existing is not None and (
                existing.paper_id,
                existing.source_snapshot_version,
                existing.source_snapshot_content_hash,
                existing.status,
                existing.validation_code,
            ) != (
                reference.paper_id,
                reference.source_snapshot_version,
                reference.source_snapshot_content_hash,
                reference.status,
                reference.validation_code,
            ):
                raise PublicationAdmissionError(
                    "Literature Evidence references are not uniquely materializable"
                )
            expected_evidence.setdefault(key, reference)

    bindings = tuple(evidence_bindings)
    actual_evidence = {item.materialization_key: item for item in bindings}
    if len(actual_evidence) != len(bindings) or set(actual_evidence) != set(
        expected_evidence
    ):
        raise PublicationAdmissionError(
            "Evidence bindings must exactly close the literature provenance graph"
        )
    persisted_evidence_ids = tuple(item.persisted_evidence_id for item in bindings)
    try:
        persisted_evidence_uuids = tuple(UUID(item) for item in persisted_evidence_ids)
    except ValueError as exc:
        raise PublicationAdmissionError(
            "Persisted Evidence bindings must use UUID identifiers"
        ) from exc
    if len(persisted_evidence_uuids) != len(set(persisted_evidence_uuids)):
        raise PublicationAdmissionError("Persisted Evidence bindings must be unique")

    pipeline_evidence = {
        item.evidence_id: item for item in getattr(candidate, "evidence", ())
    }
    evidence_materializations: list[_LiteratureEvidenceMaterialization] = []
    for key, binding in sorted(actual_evidence.items()):
        reference = expected_evidence[key]
        evidence = pipeline_evidence.get(binding.pipeline_evidence_id)
        source_record_id = getattr(evidence, "source_record_id", None)
        paper_id = getattr(reference, "paper_id", None)
        if (
            evidence is None
            or binding.pipeline_evidence_id not in evidence_ids
            or binding.persisted_source_snapshot_id
            != persisted_snapshot_by_pipeline.get(binding.pipeline_source_snapshot_id)
            or not isinstance(source_record_id, str)
            or not source_record_id
            or not isinstance(paper_id, str)
            or not paper_id
        ):
            raise PublicationAdmissionError(
                "Evidence bindings must exactly close the literature provenance graph"
            )
        evidence_materializations.append(
            _LiteratureEvidenceMaterialization(
                target_type=binding.target_type,
                target_id=binding.target_id,
                pipeline_evidence_id=binding.pipeline_evidence_id,
                pipeline_source_snapshot_id=binding.pipeline_source_snapshot_id,
                persisted_evidence_id=binding.persisted_evidence_id,
                persisted_source_snapshot_id=binding.persisted_source_snapshot_id,
                paper_id=paper_id,
                source_record_id=source_record_id,
                evidence_type=(
                    "paper_metadata"
                    if evidence.locator.kind == "paper_metadata"
                    else "paper_text"
                ),
                locator_json=json.dumps(
                    {
                        "kind": evidence.locator.kind,
                        "section": evidence.locator.section,
                        "page": evidence.locator.page_index,
                        "paragraph": evidence.locator.paragraph,
                        "range": evidence.locator.text_range,
                        "metadata_field": (
                            evidence.locator.metadata_field
                            if evidence.locator.metadata_field is not None
                            else None
                        ),
                        "summary_evidence_id": binding.pipeline_evidence_id,
                        "source_record_id": source_record_id,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                quote_or_value_json=json.dumps(
                    evidence.quote_or_value,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            )
        )

    ordered_snapshots = tuple(
        item.persisted_source_snapshot_id for item in source_materializations
    )
    ordered_evidence = tuple(
        item.persisted_evidence_id for item in evidence_materializations
    )
    return (
        ordered_snapshots,
        ordered_evidence,
        source_materializations,
        tuple(evidence_materializations),
        (),
        (),
        (),
        (),
    )


def _data_snapshot_references(
    candidate: BaseModel,
) -> dict[str, tuple[str, str, str]]:
    references: dict[str, tuple[str, str, str]] = {}
    for value in getattr(candidate, "source_values", ()):
        reference = (
            value.source_id,
            value.query_hash,
            value.source_snapshot_content_hash,
        )
        existing = references.get(value.source_snapshot_id)
        if existing is not None and existing != reference:
            raise PublicationAdmissionError(
                "Data Artifact SourceSnapshot identity is ambiguous"
            )
        references[value.source_snapshot_id] = reference
    collection_members = (
        *getattr(candidate, "crossmatch_sources", ()),
        *getattr(candidate, "source_table_sources", ()),
        *getattr(candidate, "supplemental_document_sources", ()),
    )
    for member in collection_members:
        snapshot = (
            member.pipeline_source_snapshot
            if member.member_kind == "document"
            else member.source_snapshot
        )
        reference = (snapshot.source_id, snapshot.query_hash, snapshot.content_hash)
        existing = references.get(snapshot.snapshot_id)
        if existing is not None and existing != reference:
            raise PublicationAdmissionError(
                "Data Artifact SourceSnapshot identity is ambiguous"
            )
        references[snapshot.snapshot_id] = reference
    return references


def _data_publication_references(
    candidate: BaseModel,
    *,
    source_snapshot_ids: tuple[str, ...],
    evidence_ids: tuple[str, ...],
    source_snapshot_bindings: Sequence[ArtifactSourceSnapshotBinding] | None,
    evidence_bindings: Sequence[ArtifactEvidenceBinding] | None,
    data_provenance_candidate: BaseModel | None,
) -> tuple[
    tuple[str, ...],
    tuple[str, ...],
    tuple[_LiteratureSourceSnapshotMaterialization, ...],
    tuple[_LiteratureEvidenceMaterialization, ...],
    tuple[_GraphSourceSnapshotMaterialization, ...],
    tuple[_GraphEvidenceMaterialization, ...],
    tuple[_DataSourceSnapshotMaterialization, ...],
    tuple[_OwnedEvidenceMaterialization, ...],
]:
    candidate_kind = normalize_artifact_kind(getattr(candidate, "kind", None))
    semantic_candidate = candidate
    if candidate_kind != "dataset":
        if (
            normalize_artifact_kind(getattr(data_provenance_candidate, "kind", None))
            != "dataset"
            or getattr(data_provenance_candidate, "input_hash", None)
            != getattr(candidate, "input_hash", None)
            or tuple(getattr(data_provenance_candidate, "source_snapshot_ids", ()))
            != source_snapshot_ids
            or tuple(getattr(data_provenance_candidate, "evidence_ids", ()))
            != evidence_ids
        ):
            raise PublicationAdmissionError(
                f"{candidate_kind} publication requires its exact paired Dataset provenance"
            )
        semantic_candidate = data_provenance_candidate
    if source_snapshot_bindings is None or evidence_bindings is None:
        raise PublicationAdmissionError(
            "Data Artifact publication requires explicit persisted provenance bindings"
        )
    snapshots = tuple(source_snapshot_bindings)
    evidences = tuple(evidence_bindings)
    snapshot_by_pipeline = {
        item.pipeline_source_snapshot_id: item for item in snapshots
    }
    if (
        len(snapshot_by_pipeline) != len(snapshots)
        or set(snapshot_by_pipeline) != set(source_snapshot_ids)
        or any(not item.pipeline_source_snapshot_id.strip() for item in snapshots)
    ):
        raise PublicationAdmissionError(
            "SourceSnapshot bindings must exactly cover the Data Artifact candidate"
        )
    persisted_snapshot_ids = tuple(
        snapshot_by_pipeline[item].persisted_source_snapshot_id
        for item in source_snapshot_ids
    )
    try:
        persisted_snapshot_uuids = tuple(UUID(item) for item in persisted_snapshot_ids)
    except ValueError as exc:
        raise PublicationAdmissionError(
            "Persisted Data Artifact SourceSnapshot bindings must use UUID identifiers"
        ) from exc
    if len(persisted_snapshot_uuids) != len(set(persisted_snapshot_uuids)):
        raise PublicationAdmissionError(
            "Persisted Data Artifact SourceSnapshot bindings must be unique"
        )

    evidence_by_pipeline = {item.pipeline_evidence_id: item for item in evidences}
    if len(evidence_by_pipeline) != len(evidences) or set(evidence_by_pipeline) != set(
        evidence_ids
    ):
        raise PublicationAdmissionError(
            "Evidence bindings must exactly cover the Data Artifact candidate"
        )
    persisted_evidence_ids = tuple(
        evidence_by_pipeline[item].persisted_evidence_id for item in evidence_ids
    )
    try:
        persisted_evidence_uuids = tuple(UUID(item) for item in persisted_evidence_ids)
    except ValueError as exc:
        raise PublicationAdmissionError(
            "Persisted Data Artifact Evidence bindings must use UUID identifiers"
        ) from exc
    if len(persisted_evidence_uuids) != len(set(persisted_evidence_uuids)):
        raise PublicationAdmissionError(
            "Persisted Data Artifact Evidence bindings must be unique"
        )

    snapshot_references = _data_snapshot_references(semantic_candidate)
    if set(snapshot_references) != set(source_snapshot_ids):
        raise PublicationAdmissionError(
            "Data Artifact SourceSnapshot registry must exactly cover the candidate"
        )
    data_snapshot_materializations: list[_DataSourceSnapshotMaterialization] = []
    for pipeline_id in source_snapshot_ids:
        reference = snapshot_references.get(pipeline_id)
        if reference is None:
            raise PublicationAdmissionError(
                "Data Artifact SourceSnapshot registry is not materializable"
            )
        binding = snapshot_by_pipeline[pipeline_id]
        data_snapshot_materializations.append(
            _DataSourceSnapshotMaterialization(
                pipeline_source_snapshot_id=pipeline_id,
                persisted_source_snapshot_id=binding.persisted_source_snapshot_id,
                source_id=reference[0],
                query_hash=reference[1],
                content_hash=reference[2],
            )
        )

    transformations = {
        item.evidence_id: item
        for item in getattr(semantic_candidate, "transformation_evidence", ())
    }
    crossmatch_identity: dict[str, tuple[str, str]] = {}
    crossmatch_evidence = {}
    if isinstance(semantic_candidate.authority, CrossmatchArtifactAuthority):
        for item in transformations.values():
            if not isinstance(item.authority, CrossmatchTransformationAuthority):
                raise PublicationAdmissionError(
                    "Crossmatch Data Artifact transformation Evidence has the wrong authority"
                )
            for evidence_id in item.authority.evidence_ids:
                identity = (
                    item.authority.result_id,
                    item.authority.result_content_hash,
                )
                existing = crossmatch_identity.get(evidence_id)
                if existing is not None and existing != identity:
                    raise PublicationAdmissionError(
                        "Data Artifact crossmatch Evidence has conflicting result identity"
                    )
                crossmatch_identity[evidence_id] = identity
        crossmatch_evidence = {
            item.evidence_id: item for item in semantic_candidate.authority.evidence
        }
    elif not isinstance(semantic_candidate.authority, SourceTableArtifactAuthority):
        raise PublicationAdmissionError(
            "Data Artifact candidate has an unsupported authority"
        )

    candidate_evidence_ids = set(transformations) | set(crossmatch_evidence)
    if candidate_evidence_ids != set(evidence_ids):
        raise PublicationAdmissionError(
            "Data Artifact Evidence registry must exactly cover the candidate"
        )

    owned_evidence_materializations: list[_OwnedEvidenceMaterialization] = []
    for pipeline_id in evidence_ids:
        binding = evidence_by_pipeline[pipeline_id]
        if binding.pipeline_source_snapshot_id not in snapshot_by_pipeline:
            raise PublicationAdmissionError(
                "Data Artifact Evidence binding references an unknown SourceSnapshot"
            )
        expected_snapshot_id = snapshot_by_pipeline[
            binding.pipeline_source_snapshot_id
        ].persisted_source_snapshot_id
        if binding.persisted_source_snapshot_id != expected_snapshot_id:
            raise PublicationAdmissionError(
                "Data Artifact Evidence binding does not match its SourceSnapshot"
            )
        transformation = transformations.get(pipeline_id)
        if transformation is not None:
            if (
                binding.pipeline_source_snapshot_id
                != transformation.locator.source_snapshot_id
            ):
                raise PublicationAdmissionError(
                    "Data Artifact transformation Evidence binding must use its declared SourceSnapshot"
                )
            target_type = "canonical_field"
            target_id = transformation.canonical_field_id
            evidence_type = "data_transformation"
            locator = transformation.locator.model_dump(mode="json")
            quote_or_value = (
                transformation.canonical_value
                if transformation.canonical_value is not None
                else transformation.raw_value
            )
            if isinstance(semantic_candidate.authority, SourceTableArtifactAuthority):
                if not isinstance(
                    transformation.authority, SourceTableTransformationAuthority
                ) or (
                    transformation.authority.admission_id
                    != semantic_candidate.authority.admission_id
                    or transformation.authority.row_id != transformation.dataset_row_id
                    or transformation.locator.source_snapshot_id
                    != semantic_candidate.authority.source_snapshot_id
                ):
                    raise PublicationAdmissionError(
                        "SourceTable transformation Evidence authority disagrees with the admitted table"
                    )
                extraction_method = "source_table_admission"
            else:
                if not isinstance(
                    transformation.authority, CrossmatchTransformationAuthority
                ):
                    raise PublicationAdmissionError(
                        "Crossmatch transformation Evidence has the wrong authority"
                    )
                extraction_method = "data_artifact_admission"
        else:
            evidence = crossmatch_evidence.get(pipeline_id)
            identity = crossmatch_identity.get(pipeline_id)
            if evidence is None or identity is None:
                raise PublicationAdmissionError(
                    "Data Artifact Evidence registry is not materializable"
                )
            left_source_ids = {
                item.source_snapshot_id for item in evidence.left_locators
            }
            right_source_ids = {
                item.source_snapshot_id for item in evidence.right_locators
            }
            if (
                len(left_source_ids) != 1
                or len(right_source_ids) != 1
                or left_source_ids == right_source_ids
            ):
                raise PublicationAdmissionError(
                    "CrossmatchEvidence must bind one distinct SourceSnapshot per side"
                )
            left_source_id = next(iter(left_source_ids))
            right_source_id = next(iter(right_source_ids))
            if (
                left_source_id not in snapshot_by_pipeline
                or right_source_id not in snapshot_by_pipeline
            ):
                raise PublicationAdmissionError(
                    "CrossmatchEvidence references an unknown SourceSnapshot"
                )
            left_persisted_id = snapshot_by_pipeline[
                left_source_id
            ].persisted_source_snapshot_id
            right_persisted_id = snapshot_by_pipeline[
                right_source_id
            ].persisted_source_snapshot_id
            target_type = "crossmatch"
            target_id = pipeline_id
            evidence_type = "crossmatch_decision"
            locator = {
                "crossmatch_result_id": identity[0],
                "crossmatch_result_content_hash": identity[1],
                "crossmatch_evidence": evidence.model_dump(mode="json"),
                "source_provenance": {
                    "left": {
                        "pipeline_source_snapshot_id": left_source_id,
                        "persisted_source_snapshot_id": left_persisted_id,
                    },
                    "right": {
                        "pipeline_source_snapshot_id": right_source_id,
                        "persisted_source_snapshot_id": right_persisted_id,
                    },
                },
            }
            quote_or_value = evidence.decision.value
            extraction_method = "crossmatch_admission"
            if (
                binding.pipeline_source_snapshot_id != left_source_id
                or binding.persisted_source_snapshot_id != left_persisted_id
            ):
                raise PublicationAdmissionError(
                    "Data Artifact crossmatch Evidence binding must use its declared left SourceSnapshot anchor"
                )
        if binding.target_type != target_type or binding.target_id != target_id:
            raise PublicationAdmissionError(
                "Data Artifact Evidence binding target disagrees with the candidate"
            )
        owned_evidence_materializations.append(
            _OwnedEvidenceMaterialization(
                target_type=target_type,
                target_id=target_id,
                pipeline_evidence_id=pipeline_id,
                pipeline_source_snapshot_id=binding.pipeline_source_snapshot_id,
                persisted_evidence_id=binding.persisted_evidence_id,
                persisted_source_snapshot_id=binding.persisted_source_snapshot_id,
                evidence_type=evidence_type,
                locator_json=json.dumps(
                    locator,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                quote_or_value_json=json.dumps(
                    quote_or_value,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                extraction_method=extraction_method,
                confidence=(
                    str(evidence.confidence) if transformation is None else "1.0"
                ),
            )
        )
    return (
        persisted_snapshot_ids,
        persisted_evidence_ids,
        (),
        (),
        (),
        (),
        tuple(data_snapshot_materializations),
        tuple(owned_evidence_materializations),
    )


def _literature_snapshot_references(
    candidate: BaseModel,
) -> dict[str, tuple[str, str, str]]:
    candidate_kind = getattr(candidate, "kind", None)
    references: dict[str, tuple[str, str, str]] = {}
    if candidate_kind in {"paper_summary", "literature_claims"}:
        values = getattr(
            getattr(candidate, "input_versions", None), "source_snapshots", ()
        )
        for item in values:
            reference = (item.source_id, item.source_version, item.content_hash)
            existing = references.get(item.source_snapshot_id)
            if existing is not None and existing != reference:
                raise PublicationAdmissionError(
                    "Literature SourceSnapshot identity is ambiguous"
                )
            references[item.source_snapshot_id] = reference
    else:
        for item in getattr(candidate, "evidence", ()):
            reference = (
                item.source_id,
                item.source_snapshot_version,
                item.source_snapshot_content_hash,
            )
            existing = references.get(item.source_snapshot_id)
            if existing is not None and existing != reference:
                raise PublicationAdmissionError(
                    "Literature SourceSnapshot identity is ambiguous"
                )
            references[item.source_snapshot_id] = reference
    return references


def _paper_collection_publication_references(
    candidate: BaseModel,
    *,
    source_snapshot_ids: tuple[str, ...],
    evidence_ids: tuple[str, ...],
    source_snapshot_bindings: Sequence[ArtifactSourceSnapshotBinding] | None,
    evidence_bindings: Sequence[ArtifactEvidenceBinding] | None,
) -> tuple[
    tuple[str, ...],
    tuple[str, ...],
    tuple[_LiteratureSourceSnapshotMaterialization, ...],
    tuple[_LiteratureEvidenceMaterialization, ...],
    tuple[_GraphSourceSnapshotMaterialization, ...],
    tuple[_GraphEvidenceMaterialization, ...],
    tuple[_DataSourceSnapshotMaterialization, ...],
    tuple[_OwnedEvidenceMaterialization, ...],
]:
    if evidence_ids or tuple(evidence_bindings or ()):
        raise PublicationAdmissionError(
            "PaperCollection publication cannot declare Evidence rows"
        )
    references = {
        item.snapshot_id: (
            item.source_id,
            item.source_version_or_etag or item.cache_version or item.content_hash,
            item.content_hash,
        )
        for item in getattr(candidate, "source_snapshots", ())
    }
    if set(references) != set(source_snapshot_ids):
        raise PublicationAdmissionError(
            "PaperCollection SourceSnapshot registry is not self-consistent"
        )
    bindings = tuple(source_snapshot_bindings or ())
    by_pipeline = {
        item.pipeline_source_snapshot_id: item.persisted_source_snapshot_id
        for item in bindings
    }
    if len(by_pipeline) != len(bindings) or set(by_pipeline) != set(
        source_snapshot_ids
    ):
        raise PublicationAdmissionError(
            "PaperCollection SourceSnapshot bindings must exactly cover the candidate"
        )
    try:
        persisted_ids = tuple(UUID(by_pipeline[item]) for item in source_snapshot_ids)
    except ValueError as exc:
        raise PublicationAdmissionError(
            "Persisted PaperCollection SourceSnapshot bindings must use UUID identifiers"
        ) from exc
    if len(persisted_ids) != len(set(persisted_ids)):
        raise PublicationAdmissionError(
            "Persisted PaperCollection SourceSnapshot bindings must be unique"
        )
    materializations = tuple(
        _LiteratureSourceSnapshotMaterialization(
            pipeline_source_snapshot_id=pipeline_id,
            persisted_source_snapshot_id=by_pipeline[pipeline_id],
            source_id=references[pipeline_id][0],
            source_version=references[pipeline_id][1],
            content_hash=references[pipeline_id][2],
        )
        for pipeline_id in source_snapshot_ids
    )
    return (
        tuple(str(item) for item in persisted_ids),
        (),
        materializations,
        (),
        (),
        (),
        (),
        (),
    )


def _paper_summary_publication_references(
    candidate: BaseModel,
    *,
    source_snapshot_ids: tuple[str, ...],
    evidence_ids: tuple[str, ...],
    source_snapshot_bindings: Sequence[ArtifactSourceSnapshotBinding] | None,
    evidence_bindings: Sequence[ArtifactEvidenceBinding] | None,
) -> tuple[
    tuple[str, ...],
    tuple[str, ...],
    tuple[_LiteratureSourceSnapshotMaterialization, ...],
    tuple[_LiteratureEvidenceMaterialization, ...],
    tuple[_GraphSourceSnapshotMaterialization, ...],
    tuple[_GraphEvidenceMaterialization, ...],
    tuple[_DataSourceSnapshotMaterialization, ...],
    tuple[_OwnedEvidenceMaterialization, ...],
]:
    references = _literature_snapshot_references(candidate)
    if set(references) != set(source_snapshot_ids):
        raise PublicationAdmissionError(
            "PaperSummary SourceSnapshot registry is not self-consistent"
        )
    snapshots = tuple(source_snapshot_bindings or ())
    snapshot_by_pipeline = {
        item.pipeline_source_snapshot_id: item.persisted_source_snapshot_id
        for item in snapshots
    }
    if len(snapshot_by_pipeline) != len(snapshots) or set(snapshot_by_pipeline) != set(
        source_snapshot_ids
    ):
        raise PublicationAdmissionError(
            "PaperSummary SourceSnapshot bindings must exactly cover the candidate"
        )
    evidence = {item.evidence_id: item for item in getattr(candidate, "evidence", ())}
    bindings = tuple(evidence_bindings or ())
    binding_by_pipeline = {item.pipeline_evidence_id: item for item in bindings}
    if (
        len(binding_by_pipeline) != len(bindings)
        or set(binding_by_pipeline) != set(evidence_ids)
        or set(evidence) != set(evidence_ids)
    ):
        raise PublicationAdmissionError(
            "PaperSummary Evidence bindings must exactly cover the candidate"
        )
    statement_targets: dict[str, set[str]] = {
        pipeline_id: set() for pipeline_id in evidence_ids
    }
    for statement in getattr(candidate, "statements")():
        for pipeline_id in statement.evidence_ids:
            statement_targets.setdefault(pipeline_id, set()).add(statement.statement_id)
    source_materializations: list[_LiteratureSourceSnapshotMaterialization] = []
    for pipeline_id in source_snapshot_ids:
        persisted_id = snapshot_by_pipeline[pipeline_id]
        try:
            UUID(persisted_id)
        except ValueError as exc:
            raise PublicationAdmissionError(
                "Persisted PaperSummary SourceSnapshot bindings must use UUID identifiers"
            ) from exc
        source_materializations.append(
            _LiteratureSourceSnapshotMaterialization(
                pipeline_source_snapshot_id=pipeline_id,
                persisted_source_snapshot_id=persisted_id,
                source_id=references[pipeline_id][0],
                source_version=references[pipeline_id][1],
                content_hash=references[pipeline_id][2],
            )
        )
    evidence_materializations: list[_LiteratureEvidenceMaterialization] = []
    for pipeline_id in evidence_ids:
        item = evidence[pipeline_id]
        binding = binding_by_pipeline[pipeline_id]
        if (
            binding.target_type != "paper_summary"
            or binding.target_id not in statement_targets.get(pipeline_id, set())
            or binding.pipeline_source_snapshot_id != item.source_snapshot_id
            or binding.persisted_source_snapshot_id
            != snapshot_by_pipeline.get(item.source_snapshot_id)
        ):
            raise PublicationAdmissionError(
                "PaperSummary Evidence binding disagrees with the candidate"
            )
        try:
            UUID(binding.persisted_evidence_id)
        except ValueError as exc:
            raise PublicationAdmissionError(
                "Persisted PaperSummary Evidence bindings must use UUID identifiers"
            ) from exc
        evidence_materializations.append(
            _LiteratureEvidenceMaterialization(
                target_type="paper_summary",
                target_id=binding.target_id,
                pipeline_evidence_id=pipeline_id,
                pipeline_source_snapshot_id=item.source_snapshot_id,
                persisted_evidence_id=binding.persisted_evidence_id,
                persisted_source_snapshot_id=binding.persisted_source_snapshot_id,
                paper_id=item.paper_id,
                source_record_id=item.source_record_id,
                evidence_type=(
                    "paper_metadata"
                    if item.locator.kind == "paper_metadata"
                    else "paper_text"
                ),
                locator_json=json.dumps(
                    {
                        "kind": item.locator.kind,
                        "section": item.locator.section,
                        "page": item.locator.page_index,
                        "paragraph": item.locator.paragraph,
                        "range": item.locator.text_range,
                        "metadata_field": (
                            item.locator.metadata_field
                            if item.locator.metadata_field is not None
                            else None
                        ),
                        "summary_evidence_id": pipeline_id,
                        "source_record_id": item.source_record_id,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                quote_or_value_json=json.dumps(
                    item.quote_or_value,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            )
        )
    return (
        tuple(item.persisted_source_snapshot_id for item in source_materializations),
        tuple(item.persisted_evidence_id for item in evidence_materializations),
        tuple(source_materializations),
        tuple(evidence_materializations),
        (),
        (),
        (),
        (),
    )


def _scientific_publication_references(
    candidate: BaseModel,
    *,
    source_snapshot_ids: tuple[str, ...],
    evidence_ids: tuple[str, ...],
    source_snapshot_bindings: Sequence[ArtifactSourceSnapshotBinding] | None,
    evidence_bindings: Sequence[ArtifactEvidenceBinding] | None,
) -> tuple[
    tuple[str, ...],
    tuple[str, ...],
    tuple[_LiteratureSourceSnapshotMaterialization, ...],
    tuple[_LiteratureEvidenceMaterialization, ...],
    tuple[_GraphSourceSnapshotMaterialization, ...],
    tuple[_GraphEvidenceMaterialization, ...],
    tuple[_DataSourceSnapshotMaterialization, ...],
    tuple[_OwnedEvidenceMaterialization, ...],
]:
    if source_snapshot_bindings is not None or evidence_bindings is not None:
        raise PublicationAdmissionError(
            "Scientific artifacts use already-persisted SourceSnapshot identities"
        )
    declared = {
        item.evidence_id: item for item in getattr(candidate, "scientific_evidence", ())
    }
    if len(declared) != len(getattr(candidate, "scientific_evidence", ())):
        raise PublicationAdmissionError("Scientific Evidence ids must be unique")
    if set(declared) != set(evidence_ids):
        raise PublicationAdmissionError(
            "Scientific Evidence must exactly cover the candidate registry"
        )
    source_ids = set(source_snapshot_ids)
    try:
        tuple(UUID(item) for item in source_snapshot_ids)
        tuple(UUID(item) for item in evidence_ids)
    except ValueError as exc:
        raise PublicationAdmissionError(
            "Scientific provenance must use persisted UUID identities"
        ) from exc
    materializations: list[_OwnedEvidenceMaterialization] = []
    for evidence_id in evidence_ids:
        item = declared[evidence_id]
        if item.source_snapshot_id not in source_ids:
            raise PublicationAdmissionError(
                "Scientific Evidence references an undeclared SourceSnapshot"
            )
        materializations.append(
            _OwnedEvidenceMaterialization(
                target_type=item.target_type,
                target_id=item.target_id,
                pipeline_evidence_id=item.evidence_id,
                pipeline_source_snapshot_id=item.source_snapshot_id,
                persisted_evidence_id=item.evidence_id,
                persisted_source_snapshot_id=item.source_snapshot_id,
                evidence_type=item.evidence_type,
                locator_json=json.dumps(
                    item.locator,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                quote_or_value_json=json.dumps(
                    item.quote_or_value,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                extraction_method=item.extraction_method,
                confidence=str(item.confidence),
            )
        )
    return (
        source_snapshot_ids,
        evidence_ids,
        (),
        (),
        (),
        (),
        (),
        tuple(materializations),
    )


def _graph_publication_references(
    candidate: BaseModel,
    *,
    source_snapshot_ids: tuple[str, ...],
    evidence_ids: tuple[str, ...],
    source_snapshot_bindings: Sequence[ArtifactSourceSnapshotBinding] | None,
    evidence_bindings: Sequence[ArtifactEvidenceBinding] | None,
) -> tuple[
    tuple[str, ...],
    tuple[str, ...],
    tuple[_LiteratureSourceSnapshotMaterialization, ...],
    tuple[_LiteratureEvidenceMaterialization, ...],
    tuple[_GraphSourceSnapshotMaterialization, ...],
    tuple[_GraphEvidenceMaterialization, ...],
    tuple[_DataSourceSnapshotMaterialization, ...],
    tuple[_OwnedEvidenceMaterialization, ...],
]:
    if source_snapshot_bindings is None or evidence_bindings is None:
        raise PublicationAdmissionError(
            "Graph publication requires explicit persisted provenance bindings"
        )

    snapshot_references = {
        item.source_snapshot_id: item
        for item in getattr(candidate, "source_snapshots", ())
    }
    if len(snapshot_references) != len(
        getattr(candidate, "source_snapshots", ())
    ) or set(snapshot_references) != set(source_snapshot_ids):
        raise PublicationAdmissionError(
            "Graph candidate SourceSnapshot registry is not self-consistent"
        )

    snapshots = tuple(source_snapshot_bindings)
    pipeline_snapshot_ids = tuple(
        item.pipeline_source_snapshot_id for item in snapshots
    )
    persisted_snapshot_ids = tuple(
        item.persisted_source_snapshot_id for item in snapshots
    )
    try:
        persisted_snapshot_uuids = tuple(UUID(item) for item in persisted_snapshot_ids)
    except ValueError as exc:
        raise PublicationAdmissionError(
            "Persisted Graph SourceSnapshot bindings must use UUID identifiers"
        ) from exc
    if (
        tuple(sorted(pipeline_snapshot_ids)) != tuple(sorted(source_snapshot_ids))
        or len(pipeline_snapshot_ids) != len(set(pipeline_snapshot_ids))
        or len(persisted_snapshot_uuids) != len(set(persisted_snapshot_uuids))
        or any(
            snapshot_references[
                item.pipeline_source_snapshot_id
            ].persisted_source_snapshot_id
            != item.persisted_source_snapshot_id
            for item in snapshots
        )
    ):
        raise PublicationAdmissionError(
            "SourceSnapshot bindings must exactly cover the Graph candidate"
        )
    persisted_snapshot_by_pipeline = {
        item.pipeline_source_snapshot_id: item.persisted_source_snapshot_id
        for item in snapshots
    }
    source_materializations = tuple(
        _GraphSourceSnapshotMaterialization(
            pipeline_source_snapshot_id=item.pipeline_source_snapshot_id,
            persisted_source_snapshot_id=item.persisted_source_snapshot_id,
            source_id=snapshot_references[item.pipeline_source_snapshot_id].source_id,
            source_version=snapshot_references[
                item.pipeline_source_snapshot_id
            ].source_version,
            content_hash=snapshot_references[
                item.pipeline_source_snapshot_id
            ].content_hash,
        )
        for item in sorted(
            snapshots, key=lambda value: value.pipeline_source_snapshot_id
        )
    )

    uses = tuple(getattr(candidate, "evidence_uses", ()))
    expected_evidence = {
        (
            "graph_edge",
            item.graph_edge_id,
            item.evidence_use_id,
            item.source_snapshot_id,
        ): item
        for item in uses
    }
    if len(expected_evidence) != len(uses) or {
        item.evidence_use_id for item in uses
    } != set(evidence_ids):
        raise PublicationAdmissionError(
            "Graph Evidence-use registry is not uniquely materializable"
        )
    bindings = tuple(evidence_bindings)
    actual_evidence = {
        (
            item.target_type,
            item.target_id,
            item.pipeline_evidence_id,
            item.pipeline_source_snapshot_id,
        ): item
        for item in bindings
    }
    if len(actual_evidence) != len(bindings) or set(actual_evidence) != set(
        expected_evidence
    ):
        raise PublicationAdmissionError(
            "Evidence bindings must exactly close the Graph provenance graph"
        )

    persisted_evidence_ids = tuple(item.persisted_evidence_id for item in bindings)
    upstream_evidence_ids = tuple(item.upstream_evidence_id for item in uses)
    try:
        persisted_evidence_uuids = tuple(UUID(item) for item in persisted_evidence_ids)
        upstream_evidence_uuids = tuple(UUID(item) for item in upstream_evidence_ids)
    except ValueError as exc:
        raise PublicationAdmissionError(
            "Graph Evidence bindings must use persisted UUID identifiers"
        ) from exc
    if len(persisted_evidence_uuids) != len(set(persisted_evidence_uuids)) or set(
        persisted_evidence_uuids
    ) & set(upstream_evidence_uuids):
        raise PublicationAdmissionError(
            "Graph-owned Evidence ids must be new, unique, and never reuse upstream ids"
        )

    evidence_materializations: list[_GraphEvidenceMaterialization] = []
    for key, binding in sorted(actual_evidence.items()):
        evidence_use = expected_evidence[key]
        if binding.persisted_source_snapshot_id != persisted_snapshot_by_pipeline.get(
            binding.pipeline_source_snapshot_id
        ):
            raise PublicationAdmissionError(
                "Graph Evidence binding does not match its persisted SourceSnapshot"
            )
        evidence_type = evidence_use.evidence_type
        if hasattr(evidence_type, "value"):
            evidence_type = evidence_type.value
        evidence_materializations.append(
            _GraphEvidenceMaterialization(
                target_id=binding.target_id,
                pipeline_evidence_id=binding.pipeline_evidence_id,
                pipeline_source_snapshot_id=binding.pipeline_source_snapshot_id,
                persisted_evidence_id=binding.persisted_evidence_id,
                persisted_source_snapshot_id=binding.persisted_source_snapshot_id,
                upstream_artifact_version_id=(
                    evidence_use.upstream_artifact_version_id
                ),
                upstream_evidence_id=evidence_use.upstream_evidence_id,
                upstream_target_type=evidence_use.upstream_target_type,
                upstream_target_id=evidence_use.upstream_target_id,
                upstream_evidence_hash=evidence_use.upstream_evidence_hash,
                evidence_type=str(evidence_type),
                upstream_is_restricted=evidence_use.upstream_is_restricted,
            )
        )

    return (
        tuple(item.persisted_source_snapshot_id for item in source_materializations),
        tuple(item.persisted_evidence_id for item in evidence_materializations),
        (),
        (),
        source_materializations,
        tuple(evidence_materializations),
        (),
        (),
    )


def _validate_literature_source_snapshots(
    session: Session,
    candidate: AdmittedArtifactCandidate,
    *,
    project_id: UUID,
) -> None:
    materializations = candidate.literature_source_snapshot_materializations
    if not materializations:
        return
    ids = tuple(UUID(item.persisted_source_snapshot_id) for item in materializations)
    rows = tuple(
        session.scalars(
            select(SourceSnapshotModel).where(
                SourceSnapshotModel.id.in_(ids),
                SourceSnapshotModel.project_id == project_id,
            )
        )
    )
    by_id = {row.id: row for row in rows}
    if len(by_id) != len(ids):
        raise PublicationAdmissionError(
            "A persisted literature SourceSnapshot binding was not found in the Run Project"
        )
    for item in materializations:
        row = by_id[UUID(item.persisted_source_snapshot_id)]
        effective_version = (
            row.source_version_or_etag or row.cache_version or row.content_hash
        )
        if (
            row.source_id != item.source_id
            or effective_version != item.source_version
            or row.content_hash != item.content_hash
        ):
            raise PublicationAdmissionError(
                "A persisted literature SourceSnapshot does not match its Pipeline identity"
            )


def _validate_data_source_snapshots(
    session: Session,
    candidate: AdmittedArtifactCandidate,
    *,
    project_id: UUID,
) -> None:
    materializations = candidate.data_source_snapshot_materializations
    if not materializations:
        return
    ids = tuple(UUID(item.persisted_source_snapshot_id) for item in materializations)
    rows = tuple(
        session.scalars(
            select(SourceSnapshotModel).where(
                SourceSnapshotModel.id.in_(ids),
                SourceSnapshotModel.project_id == project_id,
            )
        )
    )
    by_id = {row.id: row for row in rows}
    if len(by_id) != len(ids):
        raise PublicationAdmissionError(
            "A persisted Data Artifact SourceSnapshot binding was not found in the Run Project"
        )
    for item in materializations:
        row = by_id[UUID(item.persisted_source_snapshot_id)]
        if (
            row.source_id != item.source_id
            or row.query_hash != item.query_hash
            or row.content_hash != item.content_hash
        ):
            raise PublicationAdmissionError(
                "A persisted Data Artifact SourceSnapshot does not match its Pipeline identity"
            )


def _require_unused_owned_evidence_ids(
    session: Session,
    candidate: AdmittedArtifactCandidate,
) -> None:
    materializations = candidate.owned_evidence_materializations
    if not materializations:
        return
    ids = tuple(UUID(item.persisted_evidence_id) for item in materializations)
    existing = tuple(
        session.scalars(select(EvidenceModel.id).where(EvidenceModel.id.in_(ids)))
    )
    if existing:
        raise PublicationConflictError(
            "An owned Evidence id is already bound to another publication"
        )


def _validate_owned_evidence_sources(
    session: Session,
    candidate: AdmittedArtifactCandidate,
    *,
    project_id: UUID,
) -> None:
    materializations = candidate.owned_evidence_materializations
    if not materializations:
        return
    ids = {UUID(item.persisted_source_snapshot_id) for item in materializations}
    persisted = set(
        session.scalars(
            select(SourceSnapshotModel.id).where(
                SourceSnapshotModel.id.in_(ids),
                SourceSnapshotModel.project_id == project_id,
            )
        )
    )
    if persisted != ids:
        raise PublicationAdmissionError(
            "Owned Evidence must reference SourceSnapshots in the Run Project"
        )


def _materialize_owned_evidence(
    session: Session,
    version: ArtifactVersionModel,
    candidate: AdmittedArtifactCandidate,
) -> None:
    for item in candidate.owned_evidence_materializations:
        session.add(
            EvidenceModel(
                id=UUID(item.persisted_evidence_id),
                project_id=version.project_id,
                artifact_version_id=version.id,
                target_type=item.target_type,
                target_id=item.target_id,
                evidence_type=item.evidence_type,
                source_snapshot_id=UUID(item.persisted_source_snapshot_id),
                paper_id=None,
                locator=json.loads(item.locator_json),
                quote_or_value=json.loads(item.quote_or_value_json),
                extraction_method=item.extraction_method,
                confidence=float(item.confidence),
                is_restricted=False,
            )
        )


def _validate_materialized_data_provenance(
    session: Session,
    version: ArtifactVersionModel,
    candidate: AdmittedArtifactCandidate,
) -> None:
    try:
        _validate_data_source_snapshots(
            session,
            candidate,
            project_id=version.project_id,
        )
    except PublicationAdmissionError as exc:
        raise PublicationConflictError(
            "The idempotent Data Artifact publication source provenance has drifted"
        ) from exc


def _validate_materialized_owned_evidence(
    session: Session,
    version: ArtifactVersionModel,
    candidate: AdmittedArtifactCandidate,
) -> None:
    materializations = candidate.owned_evidence_materializations
    if not materializations:
        return
    ids = tuple(UUID(item.persisted_evidence_id) for item in materializations)
    rows = tuple(
        session.scalars(
            select(EvidenceModel).where(
                EvidenceModel.project_id == version.project_id,
                EvidenceModel.artifact_version_id == version.id,
            )
        )
    )
    by_id = {row.id: row for row in rows}
    if set(by_id) != set(ids):
        raise PublicationConflictError(
            "The idempotent publication has a non-exact owned Evidence registry"
        )
    for item in materializations:
        row = by_id[UUID(item.persisted_evidence_id)]
        if (
            row.target_type != item.target_type
            or row.target_id != item.target_id
            or row.evidence_type != item.evidence_type
            or row.source_snapshot_id != UUID(item.persisted_source_snapshot_id)
            or row.paper_id is not None
            or row.locator != json.loads(item.locator_json)
            or row.quote_or_value != json.loads(item.quote_or_value_json)
            or row.extraction_method != item.extraction_method
            or row.confidence != float(item.confidence)
            or row.is_restricted
        ):
            raise PublicationConflictError(
                "The idempotent owned Evidence differs from admission"
            )


def _require_unused_literature_evidence_ids(
    session: Session,
    candidate: AdmittedArtifactCandidate,
) -> None:
    materializations = candidate.literature_evidence_materializations
    if not materializations:
        return
    ids = tuple(UUID(item.persisted_evidence_id) for item in materializations)
    existing = tuple(
        session.scalars(select(EvidenceModel.id).where(EvidenceModel.id.in_(ids)))
    )
    if existing:
        raise PublicationConflictError(
            "A persisted Evidence id is already bound to another publication"
        )


def _materialize_literature_evidence(
    session: Session,
    version: ArtifactVersionModel,
    candidate: AdmittedArtifactCandidate,
) -> None:
    for item in candidate.literature_evidence_materializations:
        session.add(
            EvidenceModel(
                id=UUID(item.persisted_evidence_id),
                project_id=version.project_id,
                artifact_version_id=version.id,
                target_type=item.target_type,
                target_id=item.target_id,
                evidence_type=item.evidence_type,
                source_snapshot_id=UUID(item.persisted_source_snapshot_id),
                paper_id=item.paper_id,
                locator=json.loads(item.locator_json),
                quote_or_value=json.loads(item.quote_or_value_json),
                extraction_method="literature_admission",
                confidence=1.0,
                is_restricted=False,
            )
        )


def _validate_materialized_literature_provenance(
    session: Session,
    version: ArtifactVersionModel,
    candidate: AdmittedArtifactCandidate,
) -> None:
    _validate_literature_source_snapshots(
        session,
        candidate,
        project_id=version.project_id,
    )
    materializations = candidate.literature_evidence_materializations
    if not materializations:
        return
    ids = tuple(UUID(item.persisted_evidence_id) for item in materializations)
    rows = tuple(
        session.scalars(
            select(EvidenceModel).where(
                EvidenceModel.id.in_(ids),
                EvidenceModel.project_id == version.project_id,
                EvidenceModel.artifact_version_id == version.id,
            )
        )
    )
    by_id = {row.id: row for row in rows}
    if len(by_id) != len(ids):
        raise PublicationConflictError(
            "The idempotent literature publication has incomplete persisted Evidence"
        )
    for item in materializations:
        row = by_id[UUID(item.persisted_evidence_id)]
        if (
            row.target_type != item.target_type
            or row.target_id != item.target_id
            or row.source_snapshot_id != UUID(item.persisted_source_snapshot_id)
            or row.paper_id != item.paper_id
            or row.evidence_type != item.evidence_type
            or row.extraction_method != "literature_admission"
            or row.locator != json.loads(item.locator_json)
            or row.quote_or_value != json.loads(item.quote_or_value_json)
            or row.is_restricted
        ):
            raise PublicationConflictError(
                "The idempotent literature publication provenance differs from admission"
            )


def _validate_graph_source_snapshots(
    session: Session,
    candidate: AdmittedArtifactCandidate,
    *,
    project_id: UUID,
) -> None:
    materializations = candidate.graph_source_snapshot_materializations
    if not materializations:
        return
    ids = tuple(UUID(item.persisted_source_snapshot_id) for item in materializations)
    rows = tuple(
        session.scalars(
            select(SourceSnapshotModel).where(
                SourceSnapshotModel.id.in_(ids),
                SourceSnapshotModel.project_id == project_id,
            )
        )
    )
    by_id = {row.id: row for row in rows}
    if len(by_id) != len(ids):
        raise PublicationAdmissionError(
            "A persisted Graph SourceSnapshot binding was not found in the Run Project"
        )
    for item in materializations:
        row = by_id[UUID(item.persisted_source_snapshot_id)]
        effective_version = (
            row.source_version_or_etag or row.cache_version or row.content_hash
        )
        if (
            row.source_id != item.source_id
            or effective_version != item.source_version
            or row.content_hash != item.content_hash
        ):
            raise PublicationAdmissionError(
                "A persisted Graph SourceSnapshot does not match its Pipeline identity"
            )


def _graph_upstream_evidence_payload(row: EvidenceModel) -> dict[str, object]:
    return {
        "artifact_version_id": str(row.artifact_version_id),
        "target_type": row.target_type,
        "target_id": row.target_id,
        "evidence_type": row.evidence_type,
        "source_snapshot_id": str(row.source_snapshot_id),
        "paper_id": row.paper_id,
        "locator": row.locator,
        "quote_or_value": row.quote_or_value,
        "extraction_method": row.extraction_method,
        "confidence": row.confidence,
        "is_restricted": row.is_restricted,
    }


def _validate_graph_upstream_evidence(
    session: Session,
    candidate: AdmittedArtifactCandidate,
    *,
    project_id: UUID,
) -> None:
    materializations = candidate.graph_evidence_materializations
    if not materializations:
        return
    from app.schemas.graph_artifact import compute_graph_upstream_evidence_hash

    upstream_ids = tuple(
        sorted({UUID(item.upstream_evidence_id) for item in materializations})
    )
    rows = tuple(
        session.scalars(
            select(EvidenceModel).where(
                EvidenceModel.id.in_(upstream_ids),
                EvidenceModel.project_id == project_id,
            )
        )
    )
    by_id = {row.id: row for row in rows}
    if len(by_id) != len(upstream_ids):
        raise PublicationAdmissionError(
            "An upstream Graph Evidence binding was not found in the Run Project"
        )
    for item in materializations:
        row = by_id[UUID(item.upstream_evidence_id)]
        if (
            row.artifact_version_id != UUID(item.upstream_artifact_version_id)
            or row.target_type != item.upstream_target_type
            or row.target_id != item.upstream_target_id
            or row.evidence_type != item.evidence_type
            or row.source_snapshot_id != UUID(item.persisted_source_snapshot_id)
            or row.is_restricted is not item.upstream_is_restricted
            or compute_graph_upstream_evidence_hash(
                _graph_upstream_evidence_payload(row)
            )
            != item.upstream_evidence_hash
        ):
            raise PublicationAdmissionError(
                "Upstream Graph Evidence does not match its admitted version/target closure"
            )


def _require_unused_graph_evidence_ids(
    session: Session,
    candidate: AdmittedArtifactCandidate,
) -> None:
    materializations = candidate.graph_evidence_materializations
    if not materializations:
        return
    ids = tuple(UUID(item.persisted_evidence_id) for item in materializations)
    existing = tuple(
        session.scalars(select(EvidenceModel.id).where(EvidenceModel.id.in_(ids)))
    )
    if existing:
        raise PublicationConflictError(
            "A Graph-owned persisted Evidence id is already bound to another publication"
        )


def _materialize_graph_evidence(
    session: Session,
    version: ArtifactVersionModel,
    candidate: AdmittedArtifactCandidate,
) -> None:
    for item in candidate.graph_evidence_materializations:
        session.add(
            EvidenceModel(
                id=UUID(item.persisted_evidence_id),
                project_id=version.project_id,
                artifact_version_id=version.id,
                target_type="graph_edge",
                target_id=item.target_id,
                evidence_type=item.evidence_type,
                source_snapshot_id=UUID(item.persisted_source_snapshot_id),
                paper_id=None,
                locator={
                    "graph_evidence_use_id": item.pipeline_evidence_id,
                    "upstream_artifact_version_id": (item.upstream_artifact_version_id),
                    "upstream_evidence_id": item.upstream_evidence_id,
                    "upstream_target_type": item.upstream_target_type,
                    "upstream_target_id": item.upstream_target_id,
                    "upstream_evidence_hash": item.upstream_evidence_hash,
                },
                quote_or_value=None,
                extraction_method="graph_admission",
                confidence=1.0,
                is_restricted=item.upstream_is_restricted,
            )
        )


def _validate_materialized_graph_provenance(
    session: Session,
    version: ArtifactVersionModel,
    candidate: AdmittedArtifactCandidate,
) -> None:
    try:
        _validate_graph_source_snapshots(
            session,
            candidate,
            project_id=version.project_id,
        )
        _validate_graph_upstream_evidence(
            session,
            candidate,
            project_id=version.project_id,
        )
    except PublicationAdmissionError as exc:
        raise PublicationConflictError(
            "The idempotent Graph publication upstream provenance has drifted"
        ) from exc
    materializations = candidate.graph_evidence_materializations
    if not materializations:
        return
    ids = tuple(UUID(item.persisted_evidence_id) for item in materializations)
    rows = tuple(
        session.scalars(
            select(EvidenceModel).where(
                EvidenceModel.project_id == version.project_id,
                EvidenceModel.artifact_version_id == version.id,
            )
        )
    )
    by_id = {row.id: row for row in rows}
    if set(by_id) != set(ids):
        raise PublicationConflictError(
            "The idempotent Graph publication has a non-exact Graph-owned Evidence registry"
        )
    for item in materializations:
        row = by_id[UUID(item.persisted_evidence_id)]
        expected_locator = {
            "graph_evidence_use_id": item.pipeline_evidence_id,
            "upstream_artifact_version_id": item.upstream_artifact_version_id,
            "upstream_evidence_id": item.upstream_evidence_id,
            "upstream_target_type": item.upstream_target_type,
            "upstream_target_id": item.upstream_target_id,
            "upstream_evidence_hash": item.upstream_evidence_hash,
        }
        if (
            row.target_type != "graph_edge"
            or row.target_id != item.target_id
            or row.evidence_type != item.evidence_type
            or row.source_snapshot_id != UUID(item.persisted_source_snapshot_id)
            or row.paper_id is not None
            or row.locator != expected_locator
            or row.quote_or_value is not None
            or row.extraction_method != "graph_admission"
            or row.confidence != 1.0
            or row.is_restricted is not item.upstream_is_restricted
        ):
            raise PublicationConflictError(
                "The idempotent Graph publication provenance differs from admission"
            )


def _validated_publications(
    publications: Sequence[ArtifactPublication],
) -> tuple[ArtifactPublication, ...]:
    outputs = tuple(publications)
    artifact_ids = [output.artifact_id for output in outputs]
    if len(artifact_ids) != len(set(artifact_ids)):
        raise PublicationAdmissionError(
            "A Step output set may publish each ResearchArtifact only once"
        )
    version_ids = [
        output.version_id for output in outputs if output.version_id is not None
    ]
    if len(version_ids) != len(set(version_ids)):
        raise PublicationAdmissionError(
            "A Step output set may reserve each ArtifactVersion id only once"
        )
    for output in outputs:
        if not output.publication_key.strip():
            raise PublicationAdmissionError("publication_key is required")
        if not isinstance(output.candidate, AdmittedArtifactCandidate):
            raise PublicationAdmissionError(
                "Only admitted typed candidates may publish"
            )
        if not _admitted_candidate_is_valid(output.candidate):
            raise PublicationAdmissionError(
                "Admitted candidate wrapper was forged or mutated after admission"
            )
        if output.source_mode not in _SOURCE_MODES:
            raise PublicationAdmissionError(
                "source_mode must be fixture, recorded, live, or cached"
            )
    return tuple(sorted(outputs, key=lambda output: output.artifact_id))


def _validate_candidate_artifact_kind(
    artifact: ResearchArtifactModel,
    candidate: AdmittedArtifactCandidate,
) -> None:
    candidate_kind = candidate.content.get("kind")
    artifact_kind = (
        artifact.kind.value if hasattr(artifact.kind, "value") else artifact.kind
    )
    if candidate_kind == "graph" and artifact_kind != "graph":
        raise PublicationAdmissionError(
            "Graph candidates may only publish to graph ResearchArtifacts"
        )
    if artifact_kind == "graph" and candidate_kind != "graph":
        raise PublicationAdmissionError(
            "Graph ResearchArtifacts require an admitted Evidence Graph candidate"
        )
    if candidate_kind != artifact_kind:
        raise PublicationAdmissionError(
            "Artifact candidate kind must match its ResearchArtifact kind"
        )


def _validate_export_references(
    session: Session,
    candidate: AdmittedArtifactCandidate,
    *,
    project_id: UUID,
) -> None:
    if candidate.content.get("kind") != "export":
        return
    references = candidate.content.get("artifact_version_ids")
    if not isinstance(references, (list, tuple)) or not references:
        raise PublicationAdmissionError(
            "Export candidates must reference at least one ArtifactVersion"
        )
    if any(
        not isinstance(reference, str) or not reference.strip()
        for reference in references
    ):
        raise PublicationAdmissionError(
            "Export ArtifactVersion references must be unique and nonempty"
        )
    try:
        version_ids = tuple(UUID(reference) for reference in references)
    except (TypeError, ValueError) as exc:
        raise PublicationAdmissionError(
            "Export ArtifactVersion references must use UUID identifiers"
        ) from exc
    if len(version_ids) != len(set(version_ids)):
        raise PublicationAdmissionError(
            "Export ArtifactVersion references must be unique and nonempty"
        )
    persisted_ids = tuple(
        session.scalars(
            select(ArtifactVersionModel.id).where(
                ArtifactVersionModel.id.in_(version_ids),
                ArtifactVersionModel.project_id == project_id,
            )
        )
    )
    if set(persisted_ids) != set(version_ids):
        raise PublicationAdmissionError(
            "Export ArtifactVersion references must resolve within the Run Project"
        )


def _existing_publications(
    session: Session,
    outputs: Sequence[ArtifactPublication],
) -> dict[tuple[UUID, str], ArtifactVersionModel]:
    existing: dict[tuple[UUID, str], ArtifactVersionModel] = {}
    for output in outputs:
        version = session.scalar(
            select(ArtifactVersionModel)
            .where(
                ArtifactVersionModel.artifact_id == output.artifact_id,
                ArtifactVersionModel.publication_key == output.publication_key,
            )
            .with_for_update()
        )
        if version is not None:
            existing[(output.artifact_id, output.publication_key)] = version
    return existing


def _lock_producers(
    session: Session, outputs: Sequence[ArtifactPublication]
) -> tuple[ProducerExecutionModel, ...]:
    ids = {output.producer_execution_id for output in outputs}
    producers = tuple(
        session.scalars(
            select(ProducerExecutionModel)
            .where(ProducerExecutionModel.id.in_(ids))
            .order_by(ProducerExecutionModel.id)
            .with_for_update()
        )
    )
    if len(producers) != len(ids):
        raise ProducerExecutionNotFoundError(
            "A ProducerExecution required by the publication was not found"
        )
    return producers


def _validate_publishable_producer(
    producer: ProducerExecutionModel | None,
    *,
    run_id: UUID,
    step_id: UUID,
    attempt_id: UUID,
    output: ArtifactPublication,
) -> None:
    if (
        producer is None
        or producer.status != "completed"
        or producer.run_id != run_id
        or producer.run_step_id != step_id
        or producer.step_attempt_id != attempt_id
        or producer.output_hash != output.candidate.content_hash
    ):
        raise PublicationAdmissionError(
            "Publication requires a completed matching ProducerExecution"
        )
    if not _producer_matches_candidate_input_hash(producer, output.candidate):
        raise PublicationAdmissionError(
            "ProducerExecution input_hash must match the admitted candidate"
        )
    if not _producer_matches_graph_candidate(producer, output.candidate):
        raise PublicationAdmissionError(
            "Publication requires a completed matching ProducerExecution"
        )


def _producer_matches_candidate_input_hash(
    producer: ProducerExecutionModel,
    candidate: AdmittedArtifactCandidate,
) -> bool:
    """Bind every typed candidate input to the ProducerExecution that publishes it."""

    content = candidate.content
    if content.get("kind") == "export":
        return True
    declared_input_hash = content.get("input_hash")
    return isinstance(declared_input_hash, str) and (
        producer.input_hash == declared_input_hash
    )


def _producer_matches_graph_candidate(
    producer: ProducerExecutionModel,
    candidate: AdmittedArtifactCandidate,
) -> bool:
    content = candidate.content
    if content.get("kind") != "graph":
        return True
    expected = content.get("producer")
    return isinstance(expected, dict) and (
        producer.input_hash == content.get("input_hash")
        and producer.producer_type == expected.get("producer_type")
        and producer.producer_name == expected.get("producer_name")
        and producer.producer_version == expected.get("producer_version")
        and producer.parameters_hash == expected.get("parameters_hash")
        and producer.model_provider is None
        and producer.requested_model is None
        and producer.provider_returned_model is None
        and producer.explicit_revision is None
        and producer.prompt_name is None
        and producer.prompt_version is None
        and producer.prompt_hash is None
    )


def _validate_supersedes(
    session: Session,
    *,
    artifact: ResearchArtifactModel,
    supersedes_version_id: UUID | None,
) -> None:
    if artifact.latest_version_id != supersedes_version_id:
        raise PublicationConflictError(
            "supersedes_version_id must match the locked latest ArtifactVersion"
        )
    if supersedes_version_id is not None:
        previous = session.scalar(
            select(ArtifactVersionModel).where(
                ArtifactVersionModel.id == supersedes_version_id,
                ArtifactVersionModel.artifact_id == artifact.id,
            )
        )
        if previous is None:
            raise PublicationConflictError(
                "supersedes_version_id does not belong to the target Artifact"
            )


def _public_producer_metadata(producer: ProducerExecutionModel) -> dict[str, object]:
    metadata: dict[str, object] = {
        "type": producer.producer_type,
        "name": producer.producer_name,
        "version": producer.producer_version,
        "parameters_hash": producer.parameters_hash,
    }
    for key, value in (
        ("model_provider", producer.model_provider),
        ("requested_model", producer.requested_model),
        ("provider_returned_model", producer.provider_returned_model),
        ("explicit_revision", producer.explicit_revision),
        ("prompt_name", producer.prompt_name),
        ("prompt_version", producer.prompt_version),
        ("prompt_hash", producer.prompt_hash),
    ):
        if value is not None:
            metadata[key] = value
    return metadata


def _require_same_publication(
    version: ArtifactVersionModel,
    *,
    producer: ProducerExecutionModel,
    run_id: UUID,
    step_id: UUID,
    attempt_id: UUID,
    output: ArtifactPublication,
) -> None:
    _require_same_persisted_producer(version, producer)
    expected = (
        output.artifact_id,
        run_id,
        step_id,
        attempt_id,
        output.producer_execution_id,
        output.publication_key,
        output.candidate.schema_version,
        output.candidate.content,
        output.candidate.content_hash,
        SourceMode(output.source_mode).value,
        list(output.candidate.source_snapshot_ids),
        list(output.candidate.evidence_ids),
        (
            output.candidate.quality_projection.model_dump(mode="json")
            if output.candidate.quality_projection is not None
            else None
        ),
        output.candidate.quality_projection_hash,
        output.supersedes_version_id,
    )
    actual = (
        version.artifact_id,
        version.created_by_run_id,
        version.run_step_id,
        version.step_attempt_id,
        version.producer_execution_id,
        version.publication_key,
        version.schema_version,
        version.content,
        version.content_hash,
        version.source_mode,
        version.source_snapshot_ids,
        version.evidence_ids,
        version.quality_projection,
        version.quality_projection_hash,
        version.supersedes_version_id,
    )
    if actual != expected:
        raise PublicationConflictError(
            "publication_key was reused with different content or producer conditions"
        )


def _require_same_persisted_producer(
    version: ArtifactVersionModel,
    producer: ProducerExecutionModel,
) -> None:
    if (
        version.input_hash != producer.input_hash
        or version.producer != _public_producer_metadata(producer)
    ):
        raise PublicationConflictError(
            "The idempotent publication has drifted input or public producer metadata"
        )


def _published_version(version: ArtifactVersionModel) -> PublishedVersion:
    return PublishedVersion(
        id=version.id,
        artifact_id=version.artifact_id,
        version_number=version.version_number,
        publication_key=version.publication_key,
        content_hash=version.content_hash,
        source_mode=version.source_mode,
        supersedes_version_id=version.supersedes_version_id,
    )


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _require_hash(value: str, name: str) -> None:
    if not _HASH_PATTERN.fullmatch(value):
        raise ValueError(f"{name} must be a sha256 content hash")


__all__ = [
    "AdmittedArtifactCandidate",
    "ArtifactAdmissionContext",
    "ArtifactEvidenceBinding",
    "ArtifactPublication",
    "ArtifactPublisher",
    "ArtifactSourceSnapshotBinding",
    "ProducerExecutionConflictError",
    "ProducerExecutionNotFoundError",
    "ProducerExecutionRequest",
    "ProducerExecutionSnapshot",
    "ProducerExecutionStore",
    "PublicationAdmissionError",
    "PublicationConflictError",
    "PublicationResourceNotFoundError",
    "PublicationResult",
    "PublishedVersion",
    "StalePublicationError",
    "admit_artifact_candidate",
]
