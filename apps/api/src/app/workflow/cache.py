"""Durable CacheRecord registration and strict failed-Run cache selection."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.db.models import (
    ArtifactVersionModel,
    CacheRecordModel,
    CacheSelectionAuditModel,
    EvidenceModel,
    ProducerExecutionModel,
    ResearchArtifactModel,
    ResearchContractModel,
    ResearchRunModel,
    RunEventModel,
    RunStepModel,
    SourceSnapshotModel,
    StepAttemptModel,
)
from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.core import (
    ArtifactKind,
    ResearchContractInput,
    compute_research_contract_content_hash,
)
from app.schemas.data_quality import DataQualityProjection


class CacheError(RuntimeError):
    """Base error with a stable application code."""

    code = "CACHE_ERROR"


class CacheRecordAdmissionError(CacheError):
    code = "CACHE_RECORD_ADMISSION_REJECTED"


class CacheResourceNotFoundError(CacheError):
    code = "CACHE_RESOURCE_NOT_FOUND"


class CacheSelectionNotAllowedError(CacheError):
    code = "CACHE_SELECTION_NOT_ALLOWED"


class CacheRejectionReason(StrEnum):
    selected = "CACHE_SELECTED"
    record_not_found = "CACHE_RECORD_NOT_FOUND"
    expired = "CACHE_RECORD_EXPIRED"
    contract_mismatch = "CACHE_CONTRACT_MISMATCH"
    input_mismatch = "CACHE_INPUT_MISMATCH"
    producer_mismatch = "CACHE_PRODUCER_IDENTITY_MISMATCH"
    prompt_mismatch = "CACHE_PROMPT_IDENTITY_MISMATCH"
    source_scope_mismatch = "CACHE_SOURCE_SCOPE_MISMATCH"
    quality_mismatch = "CACHE_QUALITY_CONSTRAINTS_MISMATCH"
    evidence_mismatch = "CACHE_EVIDENCE_REQUIREMENTS_MISMATCH"
    provenance_invalid = "CACHE_PROVENANCE_INVALID"


@dataclass(frozen=True, slots=True)
class CacheRecordSnapshot:
    id: UUID
    project_id: UUID
    origin_run_id: UUID
    origin_artifact_version_id: UUID
    artifact_kind: str
    contract_hash: str
    input_hash: str
    producer_identity: Mapping[str, Any]
    producer_identity_hash: str
    source_scope_hash: str
    evidence_requirements_hash: str
    quality_constraints_hash: str
    source_snapshot_ids: tuple[str, ...]
    source_snapshot_hash: str
    evidence_ids: tuple[str, ...]
    evidence_hash: str
    quality_projection_hash: str | None
    valid_from: datetime
    expires_at: datetime
    record_hash: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class CacheSelectionResult:
    audit_id: UUID
    run_id: UUID
    step_key: str
    failed_producer_execution_id: UUID
    outcome: str
    reason: str
    request_hash: str
    live_failure_class: str
    live_failure_code: str
    cache_record_id: UUID | None
    origin_run_id: UUID | None
    origin_artifact_version_id: UUID | None
    event_sequence: int
    replayed: bool


@dataclass(frozen=True, slots=True)
class _SelectionIdentity:
    contract_hash: str
    input_hash: str
    producer_identity: Mapping[str, Any]
    producer_identity_hash: str
    source_scope_hash: str
    evidence_requirements_hash: str
    quality_constraints_hash: str


_DATA_ARTIFACT_KINDS = frozenset(
    {"dataset", "field_dictionary", "source_collection"}
)
_PROMPT_IDENTITY_KEYS = frozenset(
    {"model_provider", "model_name", "prompt_name", "prompt_version", "prompt_hash"}
)


class CacheRecordStore:
    """Materialize an immutable selector candidate from published live provenance."""

    def __init__(self, factory: Callable[[], Session]) -> None:
        self._factory = factory

    def register(
        self,
        artifact_version_id: UUID,
        *,
        expires_at: datetime,
    ) -> CacheRecordSnapshot:
        _require_aware_datetime(expires_at)
        expires_at = expires_at.astimezone(UTC)
        with self._factory() as session, session.begin():
            now = session.scalar(select(func.clock_timestamp()))
            if expires_at <= now:
                raise CacheRecordAdmissionError(
                    "CacheRecord expiry must be later than database time"
                )
            facts = _load_origin_facts(session, artifact_version_id)
            (
                version,
                artifact,
                run,
                step,
                attempt,
                contract,
                producer,
                snapshots,
                evidence,
            ) = facts
            _validate_origin(
                version=version,
                artifact=artifact,
                run=run,
                step=step,
                attempt=attempt,
                contract=contract,
                producer=producer,
                snapshots=snapshots,
                evidence=evidence,
            )
            contract_input = _validated_contract(contract)
            identity = _identity(contract_input, contract.content_hash, producer)
            source_ids = _sorted_uuid_text(version.source_snapshot_ids)
            source_snapshot_hash = _source_snapshot_hash(snapshots)
            evidence_ids = _sorted_uuid_text(version.evidence_ids)
            producer_identity = dict(identity.producer_identity)
            evidence_hash = _evidence_hash(evidence)
            valid_from = version.created_at
            record_payload = {
                "project_id": str(version.project_id),
                "origin_run_id": str(run.id),
                "origin_artifact_version_id": str(version.id),
                "artifact_kind": artifact.kind,
                "contract_hash": identity.contract_hash,
                "input_hash": identity.input_hash,
                "producer_identity_hash": identity.producer_identity_hash,
                "source_scope_hash": identity.source_scope_hash,
                "evidence_requirements_hash": identity.evidence_requirements_hash,
                "quality_constraints_hash": identity.quality_constraints_hash,
                "source_snapshot_ids": source_ids,
                "source_snapshot_hash": source_snapshot_hash,
                "evidence_ids": evidence_ids,
                "evidence_hash": evidence_hash,
                "quality_projection_hash": version.quality_projection_hash,
                "valid_from": valid_from.isoformat(),
                "expires_at": expires_at.isoformat(),
            }
            record_hash = compute_canonical_payload_hash(record_payload)
            record_id = uuid4()
            inserted = session.scalar(
                pg_insert(CacheRecordModel)
                .values(
                    id=record_id,
                    project_id=version.project_id,
                    origin_run_id=run.id,
                    origin_artifact_version_id=version.id,
                    artifact_kind=artifact.kind,
                    contract_hash=identity.contract_hash,
                    input_hash=identity.input_hash,
                    producer_identity=producer_identity,
                    producer_identity_hash=identity.producer_identity_hash,
                    source_scope_hash=identity.source_scope_hash,
                    evidence_requirements_hash=identity.evidence_requirements_hash,
                    quality_constraints_hash=identity.quality_constraints_hash,
                    source_snapshot_ids=list(source_ids),
                    source_snapshot_hash=source_snapshot_hash,
                    evidence_ids=list(evidence_ids),
                    evidence_hash=evidence_hash,
                    quality_projection_hash=version.quality_projection_hash,
                    valid_from=valid_from,
                    expires_at=expires_at,
                    record_hash=record_hash,
                )
                .on_conflict_do_nothing(constraint="uq_cache_record_project_hash")
                .returning(CacheRecordModel.id)
            )
            if inserted is None:
                row = session.scalar(
                    select(CacheRecordModel).where(
                        CacheRecordModel.project_id == version.project_id,
                        CacheRecordModel.record_hash == record_hash,
                    )
                )
                if row is None:  # pragma: no cover - database invariant safeguard
                    raise CacheRecordAdmissionError(
                        "Idempotent CacheRecord registration lost its winner"
                    )
            else:
                row = session.get(CacheRecordModel, inserted)
                if row is None:  # pragma: no cover - database invariant safeguard
                    raise CacheRecordAdmissionError("CacheRecord insert was not readable")
            return _record_snapshot(row)


class CacheSelector:
    """Select a strict historical match while retaining the failed Run terminal state."""

    def __init__(
        self,
        factory: Callable[[], Session],
        *,
        clock: Callable[[Session], datetime] | None = None,
    ) -> None:
        self._factory = factory
        self._clock = clock or _database_clock

    def select_for_failed_run(
        self,
        run_id: UUID,
        *,
        step_key: str,
        artifact_kind: str,
        failed_producer_execution_id: UUID,
    ) -> CacheSelectionResult:
        try:
            normalized_kind = ArtifactKind(artifact_kind).value
        except ValueError as exc:
            raise CacheSelectionNotAllowedError(
                f"Unsupported cache artifact kind: {artifact_kind!r}"
            ) from exc

        with self._factory() as session, session.begin():
            run = session.scalar(
                select(ResearchRunModel)
                .where(ResearchRunModel.id == run_id)
                .with_for_update()
            )
            if run is None:
                raise CacheResourceNotFoundError(f"Run {run_id} was not found")
            _require_selectable_run(run)
            step = session.scalar(
                select(RunStepModel).where(
                    RunStepModel.run_id == run.id,
                    RunStepModel.key == step_key,
                ).with_for_update()
            )
            if step is None:
                raise CacheResourceNotFoundError(
                    f"RunStep {step_key!r} was not found for Run {run.id}"
                )
            if step.status != "failed":
                raise CacheSelectionNotAllowedError(
                    "Cache selection requires the failed RunStep"
                )
            attempt = session.scalar(
                select(StepAttemptModel)
                .where(StepAttemptModel.run_step_id == step.id)
                .order_by(StepAttemptModel.attempt_number.desc())
                .limit(1)
                .with_for_update()
            )
            if (
                attempt is None
                or attempt.status != "failed"
                or not attempt.retryable
                or not attempt.error_class
                or not attempt.error_code
            ):
                raise CacheSelectionNotAllowedError(
                    "Cache selection requires an explicit recoverable failed attempt"
                )
            producer = session.scalar(
                select(ProducerExecutionModel)
                .where(
                    ProducerExecutionModel.id == failed_producer_execution_id,
                    ProducerExecutionModel.step_attempt_id == attempt.id,
                    ProducerExecutionModel.run_step_id == step.id,
                )
                .with_for_update()
            )
            if (
                producer is None
                or producer.status != "failed"
                or producer.error_code != attempt.error_code
                or step.input_hash != producer.input_hash
            ):
                raise CacheSelectionNotAllowedError(
                    "Cache selection requires the failed ProducerExecution identity"
                )
            if producer.parameters_hash != compute_canonical_payload_hash(
                producer.parameters
            ):
                raise CacheSelectionNotAllowedError(
                    "Failed ProducerExecution parameters identity is invalid"
                )
            contract = session.scalar(
                select(ResearchContractModel).where(
                    ResearchContractModel.id == run.contract_id,
                    ResearchContractModel.project_id == run.project_id,
                ).with_for_update()
            )
            if contract is None:
                raise CacheResourceNotFoundError("Run Contract was not found")
            contract_input = _validated_contract(contract)
            identity = _identity(contract_input, contract.content_hash, producer)
            selector_identity_hash = compute_canonical_payload_hash(
                {
                    "artifact_kind": normalized_kind,
                    "contract_hash": identity.contract_hash,
                    "input_hash": identity.input_hash,
                    "producer_identity_hash": identity.producer_identity_hash,
                    "source_scope_hash": identity.source_scope_hash,
                    "evidence_requirements_hash": identity.evidence_requirements_hash,
                    "quality_constraints_hash": identity.quality_constraints_hash,
                }
            )
            request_hash = compute_canonical_payload_hash(
                {
                    "run_id": str(run.id),
                    "run_step_id": str(step.id),
                    "failed_producer_execution_id": str(producer.id),
                    "selector_identity_hash": selector_identity_hash,
                    "live_failure_class": attempt.error_class,
                    "live_failure_code": attempt.error_code,
                }
            )
            existing = session.scalar(
                select(CacheSelectionAuditModel).where(
                    CacheSelectionAuditModel.run_step_id == step.id,
                    CacheSelectionAuditModel.request_hash == request_hash,
                )
            )
            if existing is not None:
                return _selection_result(existing, step.key, True)

            now = self._clock(session)
            candidates = tuple(
                session.scalars(
                    select(CacheRecordModel)
                    .where(
                        CacheRecordModel.project_id == run.project_id,
                        CacheRecordModel.artifact_kind == normalized_kind,
                    )
                    .order_by(CacheRecordModel.created_at.desc(), CacheRecordModel.id)
                )
            )
            selected: CacheRecordModel | None = None
            rejection_reasons: list[CacheRejectionReason] = []
            for candidate in candidates:
                reason = _candidate_rejection(
                    session,
                    candidate=candidate,
                    identity=identity,
                    now=now,
                )
                if reason is None:
                    selected = candidate
                    break
                rejection_reasons.append(reason)

            if selected is None:
                outcome = "rejected"
                reason = _best_rejection(rejection_reasons)
                event_type = "cache.rejected"
                message = (
                    "Recoverable live failure retained; no eligible cache record selected"
                )
                artifact_version_ids: list[str] = []
            else:
                outcome = "selected"
                reason = CacheRejectionReason.selected
                event_type = "cache.selected"
                message = (
                    "Recoverable live failure retained; matching historical "
                    "ArtifactVersion selected"
                )
                artifact_version_ids = [str(selected.origin_artifact_version_id)]

            sequence = run.latest_event_sequence + 1
            audit = CacheSelectionAuditModel(
                id=uuid4(),
                project_id=run.project_id,
                run_id=run.id,
                run_step_id=step.id,
                failed_producer_execution_id=producer.id,
                request_hash=request_hash,
                selector_identity_hash=selector_identity_hash,
                outcome=outcome,
                reason=reason.value,
                cache_record_id=selected.id if selected is not None else None,
                origin_run_id=selected.origin_run_id if selected is not None else None,
                origin_artifact_version_id=(
                    selected.origin_artifact_version_id if selected is not None else None
                ),
                live_failure_class=attempt.error_class,
                live_failure_code=attempt.error_code,
                event_sequence=sequence,
            )
            session.add(
                RunEventModel(
                    run_id=run.id,
                    sequence=sequence,
                    event_type=event_type,
                    step_key=step.key,
                    progress=run.progress,
                    public_message=message,
                    artifact_version_ids=artifact_version_ids,
                )
            )
            run.latest_event_sequence = sequence
            run.revision += 1
            run.updated_at = now
            session.flush()
            session.add(audit)
            session.flush()
            return _selection_result(audit, step.key, False)


def _require_selectable_run(run: ResearchRunModel) -> None:
    if run.execution_mode != "live":
        raise CacheSelectionNotAllowedError("Cache selection requires a Live Run")
    if run.status != "failed":
        raise CacheSelectionNotAllowedError("Cache selection requires a failed Run")
    if run.cache_policy != "fallback_on_recoverable_failure":
        raise CacheSelectionNotAllowedError(
            "Run cache policy does not allow failure fallback"
        )


def _validated_contract(contract: ResearchContractModel) -> ResearchContractInput:
    try:
        value = ResearchContractInput.model_validate(contract.content)
    except ValidationError as exc:
        raise CacheRecordAdmissionError("ResearchContract content is invalid") from exc
    expected = compute_research_contract_content_hash(value)
    if contract.content_hash != expected:
        raise CacheRecordAdmissionError("ResearchContract content hash is invalid")
    return value


def _identity(
    contract: ResearchContractInput,
    contract_hash: str,
    producer: ProducerExecutionModel,
) -> _SelectionIdentity:
    producer_identity = _producer_identity(producer)
    return _SelectionIdentity(
        contract_hash=contract_hash,
        input_hash=producer.input_hash,
        producer_identity=producer_identity,
        producer_identity_hash=compute_canonical_payload_hash(producer_identity),
        source_scope_hash=compute_canonical_payload_hash(
            contract.source_scope.model_dump(mode="json")
        ),
        evidence_requirements_hash=compute_canonical_payload_hash(
            contract.evidence_requirements.model_dump(mode="json")
        ),
        quality_constraints_hash=compute_canonical_payload_hash(
            contract.quality_constraints.model_dump(mode="json")
        ),
    )


def _producer_identity(producer: ProducerExecutionModel) -> dict[str, Any]:
    return {
        "producer_type": producer.producer_type,
        "producer_name": producer.producer_name,
        "producer_version": producer.producer_version,
        "model_provider": producer.model_provider,
        "model_name": producer.model_name,
        "prompt_name": producer.prompt_name,
        "prompt_version": producer.prompt_version,
        "prompt_hash": producer.prompt_hash,
        "parameters_hash": producer.parameters_hash,
    }


def _load_origin_facts(
    session: Session, artifact_version_id: UUID
) -> tuple[
    ArtifactVersionModel,
    ResearchArtifactModel,
    ResearchRunModel,
    RunStepModel,
    StepAttemptModel,
    ResearchContractModel,
    ProducerExecutionModel,
    tuple[SourceSnapshotModel, ...],
    tuple[EvidenceModel, ...],
]:
    version = session.scalar(
        select(ArtifactVersionModel)
        .where(ArtifactVersionModel.id == artifact_version_id)
        .with_for_update()
    )
    if version is None:
        raise CacheResourceNotFoundError(
            f"ArtifactVersion {artifact_version_id} was not found"
        )
    artifact = session.scalar(
        select(ResearchArtifactModel).where(
            ResearchArtifactModel.id == version.artifact_id,
            ResearchArtifactModel.project_id == version.project_id,
        ).with_for_update()
    )
    run = session.scalar(
        select(ResearchRunModel).where(
            ResearchRunModel.id == version.created_by_run_id,
            ResearchRunModel.project_id == version.project_id,
        ).with_for_update()
    )
    step = session.scalar(
        select(RunStepModel)
        .where(
            RunStepModel.id == version.run_step_id,
            RunStepModel.run_id == version.created_by_run_id,
        )
        .with_for_update()
    )
    attempt = session.scalar(
        select(StepAttemptModel)
        .where(
            StepAttemptModel.id == version.step_attempt_id,
            StepAttemptModel.run_step_id == version.run_step_id,
        )
        .with_for_update()
    )
    producer = session.scalar(
        select(ProducerExecutionModel)
        .where(
            ProducerExecutionModel.id == version.producer_execution_id,
            ProducerExecutionModel.run_id == version.created_by_run_id,
        )
        .with_for_update()
    )
    if (
        artifact is None
        or run is None
        or step is None
        or attempt is None
        or producer is None
    ):
        raise CacheRecordAdmissionError("ArtifactVersion provenance is incomplete")
    contract = session.scalar(
        select(ResearchContractModel).where(
            ResearchContractModel.id == run.contract_id,
            ResearchContractModel.project_id == run.project_id,
        ).with_for_update()
    )
    if contract is None:
        raise CacheRecordAdmissionError("Origin Run Contract is missing")
    source_ids = _uuid_values(version.source_snapshot_ids, "source_snapshot_ids")
    evidence_ids = _uuid_values(version.evidence_ids, "evidence_ids")
    snapshots = tuple(
        session.scalars(
            select(SourceSnapshotModel)
            .where(
                SourceSnapshotModel.id.in_(source_ids),
                SourceSnapshotModel.project_id == version.project_id,
            )
            .order_by(SourceSnapshotModel.id)
            .with_for_update()
        )
    )
    evidence = tuple(
        session.scalars(
            select(EvidenceModel)
            .where(
                EvidenceModel.id.in_(evidence_ids),
                EvidenceModel.project_id == version.project_id,
            )
            .order_by(EvidenceModel.id)
            .with_for_update()
        )
    )
    return (
        version,
        artifact,
        run,
        step,
        attempt,
        contract,
        producer,
        snapshots,
        evidence,
    )


def _validate_origin(
    *,
    version: ArtifactVersionModel,
    artifact: ResearchArtifactModel,
    run: ResearchRunModel,
    step: RunStepModel,
    attempt: StepAttemptModel,
    contract: ResearchContractModel,
    producer: ProducerExecutionModel,
    snapshots: tuple[SourceSnapshotModel, ...],
    evidence: tuple[EvidenceModel, ...],
) -> None:
    if run.execution_mode != "live" or run.status != "completed":
        raise CacheRecordAdmissionError(
            "CacheRecord origin must be a completed Live Run"
        )
    if (
        step.status != "completed"
        or attempt.status != "completed"
        or producer.run_step_id != step.id
        or producer.step_attempt_id != attempt.id
        or step.input_hash != version.input_hash
    ):
        raise CacheRecordAdmissionError(
            "CacheRecord origin StepAttempt provenance is incomplete"
        )
    if version.source_mode != "live":
        raise CacheRecordAdmissionError(
            "CacheRecord origin ArtifactVersion must have source_mode=live"
        )
    if version.content_hash != compute_canonical_payload_hash(version.content):
        raise CacheRecordAdmissionError(
            "CacheRecord origin ArtifactVersion content hash is invalid"
        )
    if producer.status != "completed" or producer.output_hash != version.content_hash:
        raise CacheRecordAdmissionError(
            "CacheRecord origin ProducerExecution must be completed and output-bound"
        )
    if producer.input_hash != version.input_hash:
        raise CacheRecordAdmissionError(
            "CacheRecord origin input hash does not match ProducerExecution"
        )
    if producer.parameters_hash != compute_canonical_payload_hash(producer.parameters):
        raise CacheRecordAdmissionError(
            "CacheRecord origin ProducerExecution parameters hash is invalid"
        )
    expected_public_producer = {
        "type": producer.producer_type,
        "name": producer.producer_name,
        "version": producer.producer_version,
        "parameters_hash": producer.parameters_hash,
    }
    expected_public_producer.update(
        {
            key: value
            for key, value in (
                ("model_provider", producer.model_provider),
                ("model_name", producer.model_name),
                ("prompt_name", producer.prompt_name),
                ("prompt_version", producer.prompt_version),
                ("prompt_hash", producer.prompt_hash),
            )
            if value is not None
        }
    )
    if version.producer != expected_public_producer:
        raise CacheRecordAdmissionError(
            "CacheRecord origin public producer metadata is invalid"
        )
    if artifact.kind != version.content.get("kind"):
        raise CacheRecordAdmissionError("ArtifactVersion kind provenance is invalid")
    contract_input = _validated_contract(contract)
    try:
        normalized_kind = ArtifactKind(artifact.kind)
    except ValueError as exc:
        raise CacheRecordAdmissionError("ArtifactVersion kind is not governed") from exc
    if normalized_kind not in contract_input.output_requirements:
        raise CacheRecordAdmissionError(
            "ArtifactVersion kind is outside the origin Contract outputs"
        )
    source_ids = _sorted_uuid_text(version.source_snapshot_ids)
    evidence_ids = _sorted_uuid_text(version.evidence_ids)
    if not source_ids or len(snapshots) != len(source_ids):
        raise CacheRecordAdmissionError(
            "CacheRecord requires a closed non-empty SourceSnapshot set"
        )
    if any(
        snapshot.query_hash != compute_canonical_payload_hash(snapshot.query)
        for snapshot in snapshots
    ):
        raise CacheRecordAdmissionError(
            "CacheRecord SourceSnapshot query hash is invalid"
        )
    if not evidence_ids or len(evidence) != len(evidence_ids):
        raise CacheRecordAdmissionError(
            "CacheRecord requires a closed non-empty Evidence set"
        )
    allowed_sources = set(contract_input.source_scope.allowed_sources)
    if any(snapshot.source_id not in allowed_sources for snapshot in snapshots):
        raise CacheRecordAdmissionError(
            "CacheRecord SourceSnapshot falls outside the Contract source scope"
        )
    snapshot_id_set = {str(item.id) for item in snapshots}
    if any(
        item.artifact_version_id != version.id
        or str(item.source_snapshot_id) not in snapshot_id_set
        or (
            contract_input.evidence_requirements.require_locator
            and not item.locator
        )
        for item in evidence
    ):
        raise CacheRecordAdmissionError(
            "CacheRecord Evidence does not close over the origin ArtifactVersion"
        )
    if artifact.kind in _DATA_ARTIFACT_KINDS:
        if version.quality_projection is None or version.quality_projection_hash is None:
            raise CacheRecordAdmissionError(
                "Data CacheRecord requires a persisted quality projection"
            )
        try:
            projection = DataQualityProjection.model_validate(version.quality_projection)
        except ValidationError as exc:
            raise CacheRecordAdmissionError(
                "Data CacheRecord quality projection is invalid"
            ) from exc
        if (
            projection.content_hash != version.quality_projection_hash
            or projection.research_contract.content_hash != contract.content_hash
            or projection.candidate_kind != artifact.kind
            or projection.candidate_input_hash != version.input_hash
            or projection.candidate_output_hash != version.content_hash
            or projection.candidate_content_hash != version.content_hash
            or projection.quality_result_input_hash != projection.quality_input_hash
            or projection.overall_status != "pass"
        ):
            raise CacheRecordAdmissionError(
                "Data CacheRecord quality projection does not match its Contract"
            )


def _candidate_rejection(
    session: Session,
    *,
    candidate: CacheRecordModel,
    identity: _SelectionIdentity,
    now: datetime,
) -> CacheRejectionReason | None:
    if candidate.input_hash != identity.input_hash:
        return CacheRejectionReason.input_mismatch
    if candidate.producer_identity_hash != identity.producer_identity_hash:
        expected = dict(identity.producer_identity)
        actual = dict(candidate.producer_identity)
        non_prompt_keys = set(expected) - _PROMPT_IDENTITY_KEYS
        if all(actual.get(key) == expected.get(key) for key in non_prompt_keys):
            return CacheRejectionReason.prompt_mismatch
        return CacheRejectionReason.producer_mismatch
    if candidate.source_scope_hash != identity.source_scope_hash:
        return CacheRejectionReason.source_scope_mismatch
    if candidate.quality_constraints_hash != identity.quality_constraints_hash:
        return CacheRejectionReason.quality_mismatch
    if candidate.evidence_requirements_hash != identity.evidence_requirements_hash:
        return CacheRejectionReason.evidence_mismatch
    if candidate.contract_hash != identity.contract_hash:
        return CacheRejectionReason.contract_mismatch
    if not _record_provenance_is_closed(session, candidate):
        return CacheRejectionReason.provenance_invalid
    if candidate.valid_from > now or candidate.expires_at <= now:
        return CacheRejectionReason.expired
    return None


def _record_provenance_is_closed(
    session: Session, record: CacheRecordModel
) -> bool:
    try:
        facts = _load_origin_facts(session, record.origin_artifact_version_id)
        (
            version,
            artifact,
            run,
            step,
            attempt,
            contract,
            producer,
            snapshots,
            evidence,
        ) = facts
        _validate_origin(
            version=version,
            artifact=artifact,
            run=run,
            step=step,
            attempt=attempt,
            contract=contract,
            producer=producer,
            snapshots=snapshots,
            evidence=evidence,
        )
        contract_input = _validated_contract(contract)
        identity = _identity(contract_input, contract.content_hash, producer)
    except CacheError:
        return False
    return (
        record.project_id == version.project_id
        and record.origin_run_id == run.id
        and record.artifact_kind == artifact.kind
        and record.contract_hash == identity.contract_hash
        and record.input_hash == identity.input_hash
        and dict(record.producer_identity) == dict(identity.producer_identity)
        and record.producer_identity_hash == identity.producer_identity_hash
        and record.source_scope_hash == identity.source_scope_hash
        and record.evidence_requirements_hash == identity.evidence_requirements_hash
        and record.quality_constraints_hash == identity.quality_constraints_hash
        and tuple(record.source_snapshot_ids)
        == _sorted_uuid_text(version.source_snapshot_ids)
        and record.source_snapshot_hash == _source_snapshot_hash(snapshots)
        and tuple(record.evidence_ids) == _sorted_uuid_text(version.evidence_ids)
        and record.evidence_hash == _evidence_hash(evidence)
        and record.quality_projection_hash == version.quality_projection_hash
        and record.valid_from == version.created_at
        and record.record_hash == _cache_record_hash(record)
    )


def _cache_record_hash(record: CacheRecordModel) -> str:
    return compute_canonical_payload_hash(
        {
            "project_id": str(record.project_id),
            "origin_run_id": str(record.origin_run_id),
            "origin_artifact_version_id": str(record.origin_artifact_version_id),
            "artifact_kind": record.artifact_kind,
            "contract_hash": record.contract_hash,
            "input_hash": record.input_hash,
            "producer_identity_hash": record.producer_identity_hash,
            "source_scope_hash": record.source_scope_hash,
            "evidence_requirements_hash": record.evidence_requirements_hash,
            "quality_constraints_hash": record.quality_constraints_hash,
            "source_snapshot_ids": tuple(record.source_snapshot_ids),
            "source_snapshot_hash": record.source_snapshot_hash,
            "evidence_ids": tuple(record.evidence_ids),
            "evidence_hash": record.evidence_hash,
            "quality_projection_hash": record.quality_projection_hash,
            "valid_from": record.valid_from.isoformat(),
            "expires_at": record.expires_at.isoformat(),
        }
    )


def _best_rejection(
    reasons: list[CacheRejectionReason],
) -> CacheRejectionReason:
    if not reasons:
        return CacheRejectionReason.record_not_found
    priority = (
        CacheRejectionReason.expired,
        CacheRejectionReason.contract_mismatch,
        CacheRejectionReason.input_mismatch,
        CacheRejectionReason.prompt_mismatch,
        CacheRejectionReason.producer_mismatch,
        CacheRejectionReason.source_scope_mismatch,
        CacheRejectionReason.quality_mismatch,
        CacheRejectionReason.evidence_mismatch,
        CacheRejectionReason.provenance_invalid,
    )
    return next(reason for reason in priority if reason in reasons)


def _evidence_hash(evidence: tuple[EvidenceModel, ...]) -> str:
    return compute_canonical_payload_hash(
        [
            {
                "id": str(item.id),
                "artifact_version_id": str(item.artifact_version_id),
                "target_type": item.target_type,
                "target_id": item.target_id,
                "evidence_type": item.evidence_type,
                "source_snapshot_id": str(item.source_snapshot_id),
                "paper_id": item.paper_id,
                "locator": item.locator,
                "quote_or_value": item.quote_or_value,
                "extraction_method": item.extraction_method,
                "confidence": item.confidence,
                "is_restricted": item.is_restricted,
            }
            for item in sorted(evidence, key=lambda value: value.id)
        ]
    )


def _source_snapshot_hash(snapshots: tuple[SourceSnapshotModel, ...]) -> str:
    return compute_canonical_payload_hash(
        [
            {
                "id": str(item.id),
                "project_id": str(item.project_id),
                "source_id": item.source_id,
                "source_type": item.source_type,
                "retrieved_at": item.retrieved_at.isoformat(),
                "query": item.query,
                "query_hash": item.query_hash,
                "source_version_or_etag": item.source_version_or_etag,
                "content_hash": item.content_hash,
                "license_note": item.license_note,
                "cache_version": item.cache_version,
                "request_metadata": item.request_metadata,
            }
            for item in sorted(snapshots, key=lambda value: value.id)
        ]
    )


def _uuid_values(values: list[str], field_name: str) -> tuple[UUID, ...]:
    try:
        normalized = tuple(UUID(value) for value in values)
    except (TypeError, ValueError) as exc:
        raise CacheRecordAdmissionError(
            f"ArtifactVersion {field_name} contains an invalid UUID"
        ) from exc
    if len(normalized) != len(set(normalized)):
        raise CacheRecordAdmissionError(
            f"ArtifactVersion {field_name} contains duplicates"
        )
    return normalized


def _sorted_uuid_text(values: list[str]) -> tuple[str, ...]:
    return tuple(str(value) for value in sorted(_uuid_values(values, "references")))


def _require_aware_datetime(value: datetime) -> None:
    if value.utcoffset() is None:
        raise ValueError("CacheRecord expiry must be timezone-aware")


def _database_clock(session: Session) -> datetime:
    return session.scalar(select(func.clock_timestamp()))


def _record_snapshot(row: CacheRecordModel) -> CacheRecordSnapshot:
    return CacheRecordSnapshot(
        id=row.id,
        project_id=row.project_id,
        origin_run_id=row.origin_run_id,
        origin_artifact_version_id=row.origin_artifact_version_id,
        artifact_kind=row.artifact_kind,
        contract_hash=row.contract_hash,
        input_hash=row.input_hash,
        producer_identity=dict(row.producer_identity),
        producer_identity_hash=row.producer_identity_hash,
        source_scope_hash=row.source_scope_hash,
        evidence_requirements_hash=row.evidence_requirements_hash,
        quality_constraints_hash=row.quality_constraints_hash,
        source_snapshot_ids=tuple(row.source_snapshot_ids),
        source_snapshot_hash=row.source_snapshot_hash,
        evidence_ids=tuple(row.evidence_ids),
        evidence_hash=row.evidence_hash,
        quality_projection_hash=row.quality_projection_hash,
        valid_from=row.valid_from,
        expires_at=row.expires_at,
        record_hash=row.record_hash,
        created_at=row.created_at,
    )


def _selection_result(
    row: CacheSelectionAuditModel,
    step_key: str,
    replayed: bool,
) -> CacheSelectionResult:
    return CacheSelectionResult(
        audit_id=row.id,
        run_id=row.run_id,
        step_key=step_key,
        failed_producer_execution_id=row.failed_producer_execution_id,
        outcome=row.outcome,
        reason=row.reason,
        request_hash=row.request_hash,
        live_failure_class=row.live_failure_class,
        live_failure_code=row.live_failure_code,
        cache_record_id=row.cache_record_id,
        origin_run_id=row.origin_run_id,
        origin_artifact_version_id=row.origin_artifact_version_id,
        event_sequence=row.event_sequence,
        replayed=replayed,
    )


__all__ = [
    "CacheError",
    "CacheRecordAdmissionError",
    "CacheRecordSnapshot",
    "CacheRecordStore",
    "CacheRejectionReason",
    "CacheResourceNotFoundError",
    "CacheSelectionNotAllowedError",
    "CacheSelectionResult",
    "CacheSelector",
]
