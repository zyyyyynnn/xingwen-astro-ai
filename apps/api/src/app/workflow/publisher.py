"""Producer execution ledger and atomic ArtifactVersion publication for B-14."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import TypeAlias
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
    RunEventModel,
    RunStepModel,
    SourceSnapshotModel,
    StepAttemptModel,
)
from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.data_quality import DataQualityProjection
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
_SOURCE_MODES = frozenset({"fixture", "live", "cached"})
_ADMISSION_SEAL = object()
_QUALITY_ATTESTATION_SEAL = object()
_SEMANTIC_VERSION_PATTERN = re.compile(r"^[1-9]\d*\.\d+\.\d+$")

ProducerParameter: TypeAlias = str | int | float | bool | None
AdmissionValidator: TypeAlias = Callable[["ArtifactAdmissionContext"], None]


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
    model_provider: str | None = None
    model_name: str | None = None
    prompt_name: str | None = None
    prompt_version: str | None = None
    prompt_hash: str | None = None


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
    model_name: str | None
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


@dataclass(frozen=True, slots=True, init=False)
class AdmittedArtifactCandidate:
    """Opaque structured candidate that can only be created by the admission port."""

    _content_json: str
    content_hash: str
    schema_version: str
    source_snapshot_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    _quality_projection_json: str | None
    quality_projection_hash: str | None
    _literature_source_snapshot_materializations: tuple[
        _LiteratureSourceSnapshotMaterialization, ...
    ]
    _literature_evidence_materializations: tuple[
        _LiteratureEvidenceMaterialization, ...
    ]

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
            tuple(literature_source_snapshot_materializations),
        )
        object.__setattr__(
            self,
            "_literature_evidence_materializations",
            tuple(literature_evidence_materializations),
        )

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
        return self._literature_source_snapshot_materializations

    @property
    def literature_evidence_materializations(
        self,
    ) -> tuple[_LiteratureEvidenceMaterialization, ...]:
        return self._literature_evidence_materializations


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
    content = candidate.model_dump(mode="json", exclude_none=True)
    candidate_content_hash = compute_canonical_payload_hash(content)
    if (
        projection.candidate_kind != getattr(candidate, "kind", None)
        or projection.candidate_id != getattr(candidate, "candidate_id", None)
        or projection.candidate_input_hash != getattr(candidate, "input_hash", None)
        or projection.candidate_output_hash != getattr(candidate, "output_hash", None)
        or projection.candidate_content_hash != candidate_content_hash
    ):
        raise PublicationAdmissionError(
            "C-05 attestation does not match the exact data candidate"
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
            "Final data Artifact publication requires a C-05 attestation"
        )
    content_hash = compute_canonical_payload_hash(
        candidate.model_dump(mode="json", exclude_none=True)
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
            "C-05 attestation is not sealed to the exact data candidate"
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
    ) = _publication_references(
        candidate,
        source_snapshot_ids=snapshots,
        evidence_ids=evidence,
        source_snapshot_bindings=source_snapshot_bindings,
        evidence_bindings=evidence_bindings,
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
    content = candidate.model_dump(mode="json", exclude_none=True)
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
        literature_source_snapshot_materializations=(
            source_snapshot_materializations
        ),
        literature_evidence_materializations=evidence_materializations,
        _seal=_ADMISSION_SEAL,
    )


@dataclass(frozen=True, slots=True)
class ArtifactPublication:
    artifact_id: UUID
    publication_key: str
    producer_execution_id: UUID
    candidate: AdmittedArtifactCandidate
    source_mode: str
    supersedes_version_id: UUID | None = None


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
        parameters_hash = compute_canonical_payload_hash(parameters)
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
                return _execution_snapshot(existing)
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
                model_name=_optional_text(request.model_name),
                prompt_name=_optional_text(request.prompt_name),
                prompt_version=_optional_text(request.prompt_version),
                prompt_hash=request.prompt_hash,
                parameters=parameters,
                parameters_hash=parameters_hash,
                input_hash=request.input_hash,
                status="running",
                started_at=session.scalar(select(func.clock_timestamp())),
            )
            session.add(row)
            session.flush()
            return _execution_snapshot(row)

    def finish_producer_execution(
        self,
        execution_id: UUID,
        *,
        status: str,
        output_hash: str | None = None,
        token_usage: Mapping[str, int] | None = None,
        latency_ms: int | None = None,
        error_code: str | None = None,
    ) -> ProducerExecutionSnapshot:
        _validate_execution_outcome(
            status=status,
            output_hash=output_hash,
            token_usage=token_usage,
            latency_ms=latency_ms,
            error_code=error_code,
        )
        usage = _validated_usage(token_usage)
        normalized_error = _optional_text(error_code)
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
                    and row.latency_ms == latency_ms
                    and row.error_code == normalized_error
                ):
                    return _execution_snapshot(row)
                raise ProducerExecutionConflictError(
                    "ProducerExecution already finished with a different outcome"
                )
            row.status = status
            row.output_hash = output_hash
            row.token_usage = usage
            row.latency_ms = latency_ms
            row.error_code = normalized_error
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
                _require_unused_literature_evidence_ids(
                    session, output.candidate
                )
                version_id = uuid4()
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
                    source_mode=output.source_mode,
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
                _materialize_literature_evidence(
                    session, version, output.candidate
                )
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
                    event_type="step.completed",
                    step_key=step.key,
                    progress=progress,
                    public_message=public_message,
                    artifact_version_ids=artifact_version_ids,
                )
            )
            if is_final:
                sequence += 1
                session.add(
                    RunEventModel(
                        run_id=run.id,
                        sequence=sequence,
                        event_type="run.completed",
                        step_key=step.key,
                        progress=100,
                        public_message="Run completed",
                        artifact_version_ids=artifact_version_ids,
                    )
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
            _require_same_publication(
                version,
                run_id=run.id,
                step_id=step.id,
                attempt_id=attempt_id,
                output=output,
            )
            _validate_materialized_literature_provenance(
                session, version, output.candidate
            )
            versions.append(version)
        completed_event = session.scalar(
            select(RunEventModel)
            .where(
                RunEventModel.run_id == run.id,
                RunEventModel.step_key == step.key,
                RunEventModel.event_type == "step.completed",
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
        generation,
        request.producer_type,
        request.producer_name.strip(),
        request.producer_version.strip(),
        _optional_text(request.model_provider),
        _optional_text(request.model_name),
        _optional_text(request.prompt_name),
        _optional_text(request.prompt_version),
        request.prompt_hash,
        dict(parameters),
        parameters_hash,
        request.input_hash,
    )
    actual = (
        row.run_id,
        row.run_step_id,
        row.step_attempt_id,
        row.step_key,
        row.lease_generation,
        row.producer_type,
        row.producer_name,
        row.producer_version,
        row.model_provider,
        row.model_name,
        row.prompt_name,
        row.prompt_version,
        row.prompt_hash,
        row.parameters,
        row.parameters_hash,
        row.input_hash,
    )
    if actual != expected:
        raise ProducerExecutionConflictError(
            "ProducerExecution idempotency key was reused with different input"
        )


def _execution_snapshot(row: ProducerExecutionModel) -> ProducerExecutionSnapshot:
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
        model_name=row.model_name,
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
    candidate_kind = getattr(candidate, "kind", None)
    if hasattr(candidate_kind, "value"):
        candidate_kind = candidate_kind.value

    # D-07/D-08 own these Artifact kinds exclusively. Caller-defined wrappers
    # cannot opt out by omitting the marker or opt in with a forged method.
    if candidate_kind == "literature_claims":
        from app.schemas.literature_claim import LiteratureClaimsCandidate

        if candidate_class is not LiteratureClaimsCandidate:
            raise PublicationAdmissionError(
                "literature_claims cannot bypass its authoritative Pipeline candidate"
            )
    elif candidate_kind == "literature_relations":
        from app.schemas.literature_relation import LiteratureRelationsCandidate

        if candidate_class is not LiteratureRelationsCandidate:
            raise PublicationAdmissionError(
                "literature_relations requires the authoritative Pipeline candidate"
            )
    elif candidate_kind == "reasoning_traces":
        raise PublicationAdmissionError(
            "ReasoningTrace cannot be published outside literature_relations"
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
) -> tuple[
    tuple[str, ...],
    tuple[str, ...],
    tuple[_LiteratureSourceSnapshotMaterialization, ...],
    tuple[_LiteratureEvidenceMaterialization, ...],
]:
    candidate_kind = getattr(candidate, "kind", None)
    if hasattr(candidate_kind, "value"):
        candidate_kind = candidate_kind.value
    if candidate_kind not in {"literature_claims", "literature_relations"}:
        if source_snapshot_bindings is not None or evidence_bindings is not None:
            raise PublicationAdmissionError(
                "Explicit provenance bindings are only supported for literature artifacts"
            )
        return source_snapshot_ids, evidence_ids, (), ()
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
        for item in sorted(snapshots, key=lambda value: value.pipeline_source_snapshot_id)
    )

    target_type = "claim" if candidate_kind == "literature_claims" else "relation"
    expected_evidence: dict[tuple[str, str, str, str], object] = {}
    for reference in getattr(candidate, "evidence_references", ()):
        target_id = (
            reference.claim_id
            if candidate_kind == "literature_claims"
            else reference.relation_id
        )
        key = (
            target_type,
            target_id,
            reference.evidence_id,
            reference.source_snapshot_id,
        )
        existing = expected_evidence.get(key)
        if existing is not None and existing != reference:
            raise PublicationAdmissionError(
                "Literature Evidence references are not uniquely materializable"
            )
        expected_evidence[key] = reference

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
    if len(actual_evidence) != len(bindings) or set(actual_evidence) != set(expected_evidence):
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
        raise PublicationAdmissionError(
            "Persisted Evidence bindings must be unique"
        )

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
    )


def _literature_snapshot_references(
    candidate: BaseModel,
) -> dict[str, tuple[str, str, str]]:
    candidate_kind = getattr(candidate, "kind", None)
    references: dict[str, tuple[str, str, str]] = {}
    if candidate_kind == "literature_claims":
        values = getattr(getattr(candidate, "input_versions", None), "source_snapshots", ())
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
                evidence_type="paper_text",
                source_snapshot_id=UUID(item.persisted_source_snapshot_id),
                paper_id=item.paper_id,
                locator={
                    "summary_evidence_id": item.pipeline_evidence_id,
                    "source_record_id": item.source_record_id,
                },
                quote_or_value=None,
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
            or row.evidence_type != "paper_text"
            or row.extraction_method != "literature_admission"
            or row.locator.get("summary_evidence_id") != item.pipeline_evidence_id
            or row.locator.get("source_record_id") != item.source_record_id
            or row.is_restricted
        ):
            raise PublicationConflictError(
                "The idempotent literature publication provenance differs from admission"
            )


def _validated_publications(
    publications: Sequence[ArtifactPublication],
) -> tuple[ArtifactPublication, ...]:
    outputs = tuple(publications)
    if not outputs:
        raise PublicationAdmissionError("At least one admitted output is required")
    artifact_ids = [output.artifact_id for output in outputs]
    if len(artifact_ids) != len(set(artifact_ids)):
        raise PublicationAdmissionError(
            "A Step output set may publish each ResearchArtifact only once"
        )
    for output in outputs:
        if not output.publication_key.strip():
            raise PublicationAdmissionError("publication_key is required")
        if not isinstance(output.candidate, AdmittedArtifactCandidate):
            raise PublicationAdmissionError(
                "Only admitted typed candidates may publish"
            )
        if output.source_mode not in _SOURCE_MODES:
            raise PublicationAdmissionError(
                "source_mode must be fixture, live, or cached"
            )
    return tuple(sorted(outputs, key=lambda output: output.artifact_id))


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
        ("model_name", producer.model_name),
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
    run_id: UUID,
    step_id: UUID,
    attempt_id: UUID,
    output: ArtifactPublication,
) -> None:
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
        output.source_mode,
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
