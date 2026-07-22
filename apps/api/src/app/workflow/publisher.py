"""Producer execution ledger and atomic ArtifactVersion publication for B-14."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
import json
import re
from typing import TypeAlias
from uuid import UUID, uuid4

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    ArtifactVersionModel,
    ProducerExecutionModel,
    ResearchArtifactModel,
    ResearchRunModel,
    RunEventModel,
    RunStepModel,
    StepAttemptModel,
)
from app.schemas._hashing import compute_canonical_payload_hash
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

    def __init__(
        self,
        *,
        content_json: str,
        content_hash: str,
        schema_version: str,
        source_snapshot_ids: tuple[str, ...],
        evidence_ids: tuple[str, ...],
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

    @property
    def content(self) -> dict[str, object]:
        return json.loads(self._content_json)


@dataclass(frozen=True, slots=True)
class ArtifactAdmissionContext:
    candidate: BaseModel
    source_snapshot_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]


def admit_artifact_candidate(
    candidate: BaseModel,
    *,
    schema_version: str,
    source_snapshot_ids: Sequence[str],
    evidence_ids: Sequence[str],
    evidence_validator: AdmissionValidator,
    domain_validator: AdmissionValidator,
    quality_validator: AdmissionValidator,
) -> AdmittedArtifactCandidate:
    """Run the caller-owned Evidence, domain, and quality gates on typed content."""

    if not isinstance(candidate, BaseModel) or candidate.__class__ is BaseModel:
        raise PublicationAdmissionError("A validated Pydantic model is required")
    if not candidate.__class__.model_fields:
        raise PublicationAdmissionError(
            "An empty or untyped candidate cannot be published"
        )
    if not _SEMANTIC_VERSION_PATTERN.fullmatch(schema_version.strip()):
        raise PublicationAdmissionError("schema_version must be semantic version text")
    snapshots = _validated_references(source_snapshot_ids, "source_snapshot_ids")
    evidence = _validated_references(evidence_ids, "evidence_ids")
    context = ArtifactAdmissionContext(
        candidate=candidate,
        source_snapshot_ids=snapshots,
        evidence_ids=evidence,
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
    content = candidate.model_dump(mode="json", exclude_none=True)
    content_json = json.dumps(
        content,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return AdmittedArtifactCandidate(
        content_json=content_json,
        content_hash=compute_canonical_payload_hash(content),
        schema_version=schema_version.strip(),
        source_snapshot_ids=snapshots,
        evidence_ids=evidence,
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
                version = ArtifactVersionModel(
                    id=uuid4(),
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
                    supersedes_version_id=output.supersedes_version_id,
                )
                session.add(version)
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
            or _parameter_key_is_sensitive(key)
        ):
            raise ValueError("parameters contain a forbidden or invalid key")
        if not isinstance(value, (str, int, float, bool, type(None))):
            raise ValueError("parameters may contain only scalar JSON values")
        if isinstance(value, str) and len(value) > 256:
            raise ValueError("parameter strings must not contain long raw content")
        safe[key] = value
    return safe


def _parameter_key_is_sensitive(key: str) -> bool:
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
    "ArtifactPublication",
    "ArtifactPublisher",
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
