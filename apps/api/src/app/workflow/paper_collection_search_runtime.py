"""Production PaperCollection acquisition and workflow publication bridge.

The paper pipeline owns source acquisition and deterministic metadata
canonicalization.  This module is the narrow workflow seam: it binds the
immutable ResearchContract to that pipeline, records the external producer
before any network call, persists the returned SourceSnapshots, and hands one
admitted PaperCollection publication to ArtifactPublisher.  It never mutates
RunStep or ResearchRun state.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final
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
from app.schemas.enums import (
    PaperDataLevel,
    PaperSourceExecutionStatus,
    ProducerExecutionStatus,
    SourceMode,
)
from app.schemas.evidence import SourceSnapshotRecord
from app.schemas.paper_collection import (
    NormalizedPaperQuery,
    PaperCollection,
    PaperCollectionAcquisitionRun,
    PaperCollectionMetrics,
    PaperCollectionPayload,
    PaperCollectionRules,
    PaperSearchContractReference,
    PaperSourceExecution,
    ProducerExecution,
    compute_paper_collection_input_hash,
    compute_paper_collection_output_hash,
)
from app.workflow.publisher import (
    ArtifactEvidenceBinding,
    ArtifactPublication,
    ArtifactSourceSnapshotBinding,
    ProducerExecutionRequest,
    ProducerExecutionStore,
    PublicationAdmissionError,
    admit_artifact_candidate,
)
from app.workflow.store import AttemptHandle, LeaseGrant
from services.paper_pipeline.canonicalize import canonicalize_records
from services.paper_pipeline.constants import (
    CANONICALIZATION_VERSION,
    DEDUPE_VERSION,
    PRODUCER_NAME,
    PRODUCER_VERSION,
    QUERY_NORMALIZATION_VERSION,
    RANKING_VERSION,
    RETRY_POLICY_VERSION,
    SELECTION_VERSION,
    SOURCE_POLICY_VERSION,
)
from services.paper_pipeline.dedupe import group_duplicates
from services.paper_pipeline.query import normalize_contract_query
from services.paper_pipeline.ranking import rank_and_select
from services.paper_pipeline.sources.base import (
    Clock,
    PaperSourceAdapter,
    SourceFailure,
    SourceSearchResult,
)
from services.paper_pipeline.sources.crossref import CrossrefAdapter


_PAPER_COLLECTION_KIND: Final[str] = "paper_collection"
_PAPER_COLLECTION_LOGICAL_KEY: Final[str] = "paper_collection.searching_papers"
_NAMESPACE: Final[str] = "https://xingwen.example/paper-collection-search-runtime"


@dataclass(frozen=True, slots=True)
class _SourceAttempt:
    adapter: PaperSourceAdapter
    source_mode: SourceMode
    data_level: PaperDataLevel
    started_at: datetime
    finished_at: datetime
    result: SourceSearchResult | None
    failure: SourceFailure | None


@dataclass(frozen=True, slots=True)
class _ArtifactTarget:
    artifact_id: UUID
    publication_key: str
    supersedes_version_id: UUID | None


class PaperCollectionSearchRuntime:
    """Prepare one contract-bound PaperCollection ``ArtifactPublication``.

    The public interface is deliberately one operation.  Callers provide the
    already fenced StepAttempt and lease; the implementation owns query
    normalization, adapter calls, provenance closure, admission, and target
    selection.  Tests can inject a recorded adapter and clock without touching
    the production Crossref transport.
    """

    def __init__(
        self,
        *,
        session_factory: Callable[[], Session],
        adapters: Mapping[str, PaperSourceAdapter] | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._adapters = dict(
            adapters
            or {
                "crossref": CrossrefAdapter(
                    license_note="Crossref bibliographic metadata; DOI content remains source-owned"
                )
            }
        )
        self._clock = clock or (lambda: datetime.now(UTC))
        self._producers = ProducerExecutionStore(session_factory)

    def prepare_publication(
        self,
        *,
        project_id: UUID,
        contract: ResearchContract,
        attempt: AttemptHandle,
        lease: LeaseGrant,
        source_mode: SourceMode = SourceMode.live,
        data_level: PaperDataLevel = PaperDataLevel.live_result,
    ) -> ArtifactPublication:
        """Acquire, admit, and return a single PaperCollection publication.

        ``source_mode`` and ``data_level`` are explicit so recorded tests can
        exercise the same seam.  The Worker uses their live defaults; a live
        call cannot accidentally be labelled as a fixture or replay.
        """

        if contract.project_id != str(project_id):
            raise PublicationAdmissionError(
                "Paper search Contract does not belong to the Run Project"
            )
        if (
            source_mode is SourceMode.live
            and data_level is not PaperDataLevel.live_result
        ):
            raise PublicationAdmissionError(
                "live PaperCollection acquisition requires live_result data level"
            )

        query = normalize_contract_query(
            contract.paper_search_scope,
            research_goal=contract.research_goal,
            available_source_ids=tuple(self._adapters),
        )
        adapters = self._select_adapters(query)
        rules = self._rules(adapters, contract.paper_search_scope.max_candidates)
        contract_reference = _contract_reference(contract)
        input_hash = compute_paper_collection_input_hash(
            contract_reference, query, rules
        )
        parameters = {
            "contract_id": contract.id,
            "contract_version": contract.version,
            "contract_content_hash": contract.content_hash,
            "query_hash": query.query_hash,
            "source_ids": list(query.source_ids),
            "selection_limit": contract.paper_search_scope.max_candidates,
        }
        execution = self._producers.start_producer_execution(
            ProducerExecutionRequest(
                run_id=attempt.run_id,
                step_key="searching_papers",
                attempt_id=attempt.attempt_id,
                idempotency_key=(
                    f"paper-search:attempt:{attempt.attempt_number}:input:{input_hash}"
                ),
                producer_type="algorithm",
                producer_name=PRODUCER_NAME,
                producer_version=PRODUCER_VERSION,
                input_hash=input_hash,
                parameters=parameters,
            ),
            token=lease.token,
            generation=lease.generation,
            expected_status=attempt.run_status,
            expected_revision=attempt.run_revision,
        )

        started_at = _utc(self._clock(), "paper search clock")
        try:
            attempts = self._acquire(
                adapters,
                query=query,
                source_mode=source_mode,
                data_level=data_level,
            )
            if not any(item.result is not None for item in attempts):
                failure_code = next(
                    (
                        item.failure.code
                        for item in attempts
                        if item.failure is not None
                    ),
                    "PAPER_SOURCE_ALL_FAILED",
                )
                self._finish_failed(execution.id, failure_code)
                raise PublicationAdmissionError(
                    "Paper search produced no successful source snapshot"
                )

            finished_at = _utc(self._clock(), "paper search clock")
            collection = _build_collection(
                contract=contract,
                query=query,
                rules=rules,
                attempts=attempts,
                execution_id=f"producer.{execution.id}",
                producer_parameters_hash=execution.parameters_hash,
                run_id=attempt.run_id,
                started_at=started_at,
                finished_at=finished_at,
            )
            source_bindings = _source_bindings(project_id, collection.source_snapshots)
            evidence_bindings = _evidence_bindings(
                project_id=project_id,
                input_hash=input_hash,
                collection=collection,
                source_bindings=source_bindings,
            )
            self._persist_source_snapshots(
                project_id, collection.source_snapshots, source_bindings
            )
            admitted = admit_artifact_candidate(
                collection,
                schema_version=collection.schema_version,
                source_snapshot_ids=collection.source_snapshot_ids,
                evidence_ids=tuple(
                    item.pipeline_evidence_id for item in evidence_bindings
                ),
                evidence_validator=_validate_paper_collection_evidence,
                domain_validator=_validate_paper_collection_domain,
                quality_validator=_accept,
                source_snapshot_bindings=source_bindings,
                evidence_bindings=evidence_bindings,
            )
            self._producers.finish_producer_execution(
                execution.id,
                status="completed",
                output_hash=admitted.content_hash,
                latency_ms=max(
                    0, int((finished_at - started_at).total_seconds() * 1_000)
                ),
            )
            target = self._ensure_artifact_target(
                project_id=project_id,
                contract=contract,
                input_hash=input_hash,
            )
            return ArtifactPublication(
                artifact_id=target.artifact_id,
                publication_key=target.publication_key,
                producer_execution_id=execution.id,
                candidate=admitted,
                source_mode=source_mode.value,
                supersedes_version_id=target.supersedes_version_id,
            )
        except Exception as exc:
            self._finish_failed(execution.id, _error_code(exc))
            raise

    def _select_adapters(
        self, query: NormalizedPaperQuery
    ) -> tuple[PaperSourceAdapter, ...]:
        missing = tuple(
            source_id
            for source_id in query.source_ids
            if source_id not in self._adapters
        )
        if missing:
            raise PublicationAdmissionError(
                "Paper search source adapter is not configured: " + ", ".join(missing)
            )
        selected = tuple(self._adapters[source_id] for source_id in query.source_ids)
        if any(
            adapter.source_id != source_id
            for adapter, source_id in zip(selected, query.source_ids, strict=True)
        ):
            raise PublicationAdmissionError(
                "Paper search adapter source_id does not match Contract source scope"
            )
        return selected

    @staticmethod
    def _rules(
        adapters: Sequence[PaperSourceAdapter], selection_limit: int
    ) -> PaperCollectionRules:
        versions = {adapter.adapter_version for adapter in adapters}
        if len(versions) != 1:
            raise PublicationAdmissionError(
                "Paper search adapters must share one semantic adapter version"
            )
        return PaperCollectionRules(
            adapter_name="|".join(adapter.adapter_name for adapter in adapters),
            adapter_version=next(iter(versions)),
            query_normalization_version=QUERY_NORMALIZATION_VERSION,
            canonicalization_version=CANONICALIZATION_VERSION,
            dedupe_version=DEDUPE_VERSION,
            ranking_version=RANKING_VERSION,
            selection_version=SELECTION_VERSION,
            retry_policy_version=RETRY_POLICY_VERSION,
            source_policy_version=SOURCE_POLICY_VERSION,
            selection_limit=selection_limit,
        )

    def _acquire(
        self,
        adapters: Sequence[PaperSourceAdapter],
        *,
        query: NormalizedPaperQuery,
        source_mode: SourceMode,
        data_level: PaperDataLevel,
    ) -> tuple[_SourceAttempt, ...]:
        attempts: list[_SourceAttempt] = []
        for adapter in adapters:
            started_at = _utc(self._clock(), "paper source clock")
            try:
                result = adapter.search(
                    query, source_mode=source_mode, data_level=data_level
                )
            except SourceFailure as failure:
                finished_at = _utc(self._clock(), "paper source clock")
                attempts.append(
                    _SourceAttempt(
                        adapter=adapter,
                        source_mode=source_mode,
                        data_level=data_level,
                        started_at=started_at,
                        finished_at=finished_at,
                        result=None,
                        failure=failure,
                    )
                )
            else:
                finished_at = _utc(self._clock(), "paper source clock")
                if result.snapshot.source_id != adapter.source_id:
                    raise PublicationAdmissionError(
                        "Paper source adapter returned a mismatched SourceSnapshot"
                    )
                if source_mode is SourceMode.live and any(
                    record.synthetic_note for record in result.records
                ):
                    raise PublicationAdmissionError(
                        "live PaperCollection acquisition cannot contain synthetic records"
                    )
                attempts.append(
                    _SourceAttempt(
                        adapter=adapter,
                        source_mode=source_mode,
                        data_level=data_level,
                        started_at=started_at,
                        finished_at=finished_at,
                        result=result,
                        failure=None,
                    )
                )
        return tuple(attempts)

    def _persist_source_snapshots(
        self,
        project_id: UUID,
        snapshots: Sequence[SourceSnapshotRecord],
        bindings: Sequence[ArtifactSourceSnapshotBinding],
    ) -> None:
        persisted_by_pipeline = {
            item.pipeline_source_snapshot_id: UUID(item.persisted_source_snapshot_id)
            for item in bindings
        }
        with self._session_factory() as session, session.begin():
            for snapshot in snapshots:
                persisted_id = persisted_by_pipeline[snapshot.snapshot_id]
                expected = {
                    "project_id": project_id,
                    "source_id": snapshot.source_id,
                    "source_type": snapshot.source_type,
                    "retrieved_at": snapshot.retrieved_at,
                    "query": snapshot.query,
                    "query_hash": snapshot.query_hash,
                    "source_version_or_etag": snapshot.source_version_or_etag,
                    "content_hash": snapshot.content_hash,
                    "license_note": snapshot.license_note,
                    "cache_version": snapshot.cache_version,
                    "request_metadata": snapshot.request_metadata,
                }
                existing = session.get(SourceSnapshotModel, persisted_id)
                if existing is None:
                    session.add(SourceSnapshotModel(id=persisted_id, **expected))
                elif any(
                    getattr(existing, key) != value for key, value in expected.items()
                ):
                    raise PublicationAdmissionError(
                        "Persisted paper SourceSnapshot identity has conflicting metadata"
                    )

    def _ensure_artifact_target(
        self,
        *,
        project_id: UUID,
        contract: ResearchContract,
        input_hash: str,
    ) -> _ArtifactTarget:
        logical_key = f"{_PAPER_COLLECTION_LOGICAL_KEY}.{contract.id}"
        artifact_id = uuid5(NAMESPACE_URL, f"xingwen:{project_id}:{logical_key}")
        publication_key = str(
            uuid5(
                NAMESPACE_URL,
                f"{_NAMESPACE}/{project_id}/{logical_key}/{input_hash}",
            )
        )
        with self._session_factory() as session, session.begin():
            artifact = session.get(ResearchArtifactModel, artifact_id)
            if artifact is None:
                artifact = ResearchArtifactModel(
                    id=artifact_id,
                    project_id=project_id,
                    kind=_PAPER_COLLECTION_KIND,
                    title="研究论文集合",
                    logical_key=logical_key,
                )
                session.add(artifact)
                session.flush()
            elif (
                artifact.project_id != project_id
                or artifact.kind != _PAPER_COLLECTION_KIND
                or artifact.logical_key != logical_key
            ):
                raise PublicationAdmissionError(
                    "PaperCollection ResearchArtifact identity was reused with another meaning"
                )
            existing = session.scalar(
                select(ArtifactVersionModel).where(
                    ArtifactVersionModel.artifact_id == artifact.id,
                    ArtifactVersionModel.publication_key == publication_key,
                )
            )
            return _ArtifactTarget(
                artifact_id=artifact.id,
                publication_key=publication_key,
                supersedes_version_id=(
                    existing.supersedes_version_id
                    if existing is not None
                    else artifact.latest_version_id
                ),
            )

    def _finish_failed(self, execution_id: UUID, error_code: str) -> None:
        try:
            self._producers.finish_producer_execution(
                execution_id,
                status="failed",
                error_code=error_code,
            )
        except Exception:
            # Preserve the acquisition/admission error if the ledger was
            # already closed by an idempotent retry or a concurrent owner.
            pass


def _build_collection(
    *,
    contract: ResearchContract,
    query: NormalizedPaperQuery,
    rules: PaperCollectionRules,
    attempts: Sequence[_SourceAttempt],
    execution_id: str,
    producer_parameters_hash: str,
    run_id: UUID,
    started_at: datetime,
    finished_at: datetime,
) -> PaperCollection:
    snapshots = tuple(
        item.result.snapshot for item in attempts if item.result is not None
    )
    records = tuple(
        record
        for item in attempts
        if item.result is not None
        for record in item.result.records
    )
    source_executions = tuple(_source_execution(item, query=query) for item in attempts)
    drafts = canonicalize_records(records, snapshots)
    dedupe = group_duplicates(drafts)
    candidates = rank_and_select(
        drafts,
        dedupe,
        normalized_keywords=query.normalized_keywords,
        normalized_query=query.normalized_query_string,
        year_from=query.year_from,
        year_to=query.year_to,
        selection_limit=rules.selection_limit,
    )
    selected_paper_ids = tuple(
        sorted(
            {
                candidate.canonical_paper_id
                for candidate in candidates
                if candidate.selected
            }
        )
    )
    failure_count = sum(
        item.status is PaperSourceExecutionStatus.failed for item in source_executions
    )
    successful_count = len(source_executions) - failure_count
    acquisition_status = "partial" if failure_count else "completed"
    if successful_count == 0:
        acquisition_status = "failed"
    acquisition_id = (
        "acquisition."
        + compute_canonical_payload_hash(
            {
                "input_hash": compute_paper_collection_input_hash(
                    _contract_reference(contract), query, rules
                ),
                "source_executions": [
                    _stable_source_execution_payload(item) for item in source_executions
                ],
            }
        ).removeprefix("sha256:")[:24]
    )
    duplicate_count = len(candidates) - len(dedupe.groups)
    metrics = PaperCollectionMetrics(
        source_execution_count=len(source_executions),
        source_failure_count=failure_count,
        source_empty_result_count=sum(
            item.status is PaperSourceExecutionStatus.completed
            and item.candidate_count == 0
            for item in source_executions
        ),
        candidate_count=len(candidates),
        duplicate_candidate_count=duplicate_count,
        duplicate_rate=round(duplicate_count / len(candidates), 6)
        if candidates
        else 0.0,
        selected_count=len(selected_paper_ids),
        expected_candidate_count=0,
        recalled_expected_candidate_count=0,
        candidate_recall=None,
    )
    contract_reference = _contract_reference(contract)
    input_hash = compute_paper_collection_input_hash(contract_reference, query, rules)
    producer = ProducerExecution(
        execution_id=execution_id,
        run_id=str(run_id),
        producer_name=PRODUCER_NAME,
        producer_version=PRODUCER_VERSION,
        parameters_hash=producer_parameters_hash,
        input_hash=input_hash,
        output_hash=None,
        status=ProducerExecutionStatus.completed,
        started_at=started_at,
        finished_at=finished_at,
        latency_ms=max(0, int((finished_at - started_at).total_seconds() * 1_000)),
    )
    payload = PaperCollectionPayload(
        research_contract=contract_reference,
        query=query,
        acquisition_run=PaperCollectionAcquisitionRun(
            acquisition_id=acquisition_id,
            status=acquisition_status,
            started_at=started_at,
            finished_at=finished_at,
            candidate_count=len(candidates),
            duplicate_group_count=len(dedupe.groups),
            selected_count=len(selected_paper_ids),
            source_failure_count=failure_count,
        ),
        source_executions=source_executions,
        source_snapshots=snapshots,
        source_snapshot_ids=tuple(
            sorted(snapshot.snapshot_id for snapshot in snapshots)
        ),
        candidates=candidates,
        duplicate_groups=dedupe.groups,
        potential_duplicates=dedupe.potential_duplicates,
        selected_paper_ids=selected_paper_ids,
        dedupe_rule="doi_exact > arxiv_exact > title_year_author_match; uncertainty retained",
        ranking_rule="deterministic lexical relevance with canonical final tie-breaker",
        rules=rules,
        producer=producer,
        input_hash=input_hash,
        metrics=metrics,
    )
    output_hash = compute_paper_collection_output_hash(payload)
    final_payload = payload.model_dump(mode="json", exclude_none=False)
    final_payload["producer"]["output_hash"] = output_hash
    final_payload["output_hash"] = output_hash
    return PaperCollection.model_validate(final_payload)


def _source_execution(
    attempt: _SourceAttempt, *, query: NormalizedPaperQuery
) -> PaperSourceExecution:
    request_parameters_hash = compute_canonical_payload_hash(
        {
            "query_hash": query.query_hash,
            "source_id": attempt.adapter.source_id,
            "parameters": query.source_parameters[attempt.adapter.source_id],
            "pagination": query.pagination.model_dump(mode="json"),
        }
    )
    if attempt.result is not None:
        return PaperSourceExecution(
            source_id=attempt.adapter.source_id,
            source_mode=attempt.source_mode,
            data_level=attempt.data_level,
            status=PaperSourceExecutionStatus.completed,
            query_hash=query.query_hash,
            request_parameters_hash=request_parameters_hash,
            pagination=query.pagination,
            started_at=attempt.started_at,
            finished_at=attempt.finished_at,
            pages=attempt.result.pages,
            source_snapshot_id=attempt.result.snapshot.snapshot_id,
            candidate_count=len(attempt.result.records),
            retry_count=attempt.result.retry_count,
        )
    if attempt.failure is None:
        raise PublicationAdmissionError("Paper source attempt has no result or failure")
    return PaperSourceExecution(
        source_id=attempt.adapter.source_id,
        source_mode=attempt.source_mode,
        data_level=attempt.data_level,
        status=PaperSourceExecutionStatus.failed,
        query_hash=query.query_hash,
        request_parameters_hash=request_parameters_hash,
        pagination=query.pagination,
        started_at=attempt.started_at,
        finished_at=attempt.finished_at,
        pages=(),
        source_snapshot_id=None,
        candidate_count=0,
        retry_count=max(attempt.failure.attempt_count - 1, 0),
        failure_class=attempt.failure.classification,
        failure_code=attempt.failure.code,
    )


def _contract_reference(contract: ResearchContract) -> PaperSearchContractReference:
    return PaperSearchContractReference(
        contract_id=contract.id,
        contract_version=contract.version,
        content_hash=contract.content_hash,
    )


def _source_bindings(
    project_id: UUID, snapshots: Sequence[SourceSnapshotRecord]
) -> tuple[ArtifactSourceSnapshotBinding, ...]:
    return tuple(
        ArtifactSourceSnapshotBinding(
            pipeline_source_snapshot_id=snapshot.snapshot_id,
            persisted_source_snapshot_id=str(
                uuid5(
                    NAMESPACE_URL,
                    f"{_NAMESPACE}/{project_id}/source-snapshot/{snapshot.snapshot_id}",
                )
            ),
        )
        for snapshot in sorted(snapshots, key=lambda item: item.snapshot_id)
    )


def _evidence_bindings(
    *,
    project_id: UUID,
    input_hash: str,
    collection: PaperCollection,
    source_bindings: Sequence[ArtifactSourceSnapshotBinding],
) -> tuple[ArtifactEvidenceBinding, ...]:
    persisted_by_pipeline = {
        item.pipeline_source_snapshot_id: item.persisted_source_snapshot_id
        for item in source_bindings
    }
    bindings: list[ArtifactEvidenceBinding] = []
    for candidate in sorted(collection.candidates, key=lambda item: item.candidate_id):
        pipeline_evidence_id = f"paper_metadata.{candidate.candidate_id}"
        pipeline_snapshot_id = candidate.raw.source_snapshot_id
        persisted_snapshot_id = persisted_by_pipeline.get(pipeline_snapshot_id)
        if persisted_snapshot_id is None:
            raise PublicationAdmissionError(
                "PaperCollection candidate Evidence has no SourceSnapshot binding"
            )
        bindings.append(
            ArtifactEvidenceBinding(
                target_type="paper_candidate",
                target_id=candidate.candidate_id,
                pipeline_evidence_id=pipeline_evidence_id,
                pipeline_source_snapshot_id=pipeline_snapshot_id,
                persisted_evidence_id=str(
                    uuid5(
                        NAMESPACE_URL,
                        f"{_NAMESPACE}/{project_id}/{input_hash}/evidence/{candidate.candidate_id}",
                    )
                ),
                persisted_source_snapshot_id=persisted_snapshot_id,
            )
        )
    return tuple(bindings)


def _validate_paper_collection_evidence(context: object) -> None:
    candidate = getattr(context, "candidate", None)
    if not isinstance(candidate, PaperCollection):
        raise PublicationAdmissionError(
            "PaperCollection Evidence requires PaperCollection"
        )
    expected = {f"paper_metadata.{item.candidate_id}" for item in candidate.candidates}
    actual = set(getattr(context, "evidence_ids", ()))
    if actual != expected:
        raise PublicationAdmissionError(
            "PaperCollection Evidence registry must close every candidate"
        )
    if set(getattr(context, "source_snapshot_ids", ())) != set(
        candidate.source_snapshot_ids
    ):
        raise PublicationAdmissionError(
            "PaperCollection SourceSnapshot registry is not self-consistent"
        )


def _validate_paper_collection_domain(context: object) -> None:
    candidate = getattr(context, "candidate", None)
    if not isinstance(candidate, PaperCollection):
        raise PublicationAdmissionError(
            "PaperCollection domain admission requires typed content"
        )
    if any(
        item.raw.source_snapshot_id not in candidate.source_snapshot_ids
        for item in candidate.candidates
    ):
        raise PublicationAdmissionError(
            "PaperCollection candidate SourceSnapshot is outside the collection registry"
        )


def _accept(_: object) -> None:
    return None


def _stable_source_execution_payload(
    execution: PaperSourceExecution,
) -> dict[str, object]:
    payload = execution.model_dump(mode="json", exclude_none=True)
    payload.pop("started_at", None)
    payload.pop("finished_at", None)
    for page in payload.get("pages", []):
        if isinstance(page, dict):
            page.pop("retrieved_at", None)
    return payload


def _utc(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError(f"{label} must return a timezone-aware UTC datetime")
    return value


def _error_code(error: Exception) -> str:
    if isinstance(error, SourceFailure):
        return error.code[:128]
    if isinstance(error, PublicationAdmissionError):
        return "PAPER_COLLECTION_ADMISSION_FAILED"
    return "PAPER_COLLECTION_SEARCH_FAILED"


__all__ = ["PaperCollectionSearchRuntime"]
