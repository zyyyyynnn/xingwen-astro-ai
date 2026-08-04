"""Research runtime application boundary for the minimal ``/api`` chain.

Thin layer wiring the runtime routers to authoritative persistence:

    Router -> ResearchApplicationService -> SQLAlchemy / PersistentWorkflowStore

Project/Draft/Contract identity and the immutable frozen contract live in
PostgreSQL through SQLAlchemy; Run creation, reads and Event pagination reuse
the existing :class:`PersistentWorkflowStore`. Every resource is ownership
scoped by the anonymous session so cross-session existence is hidden as 404.
"""

from __future__ import annotations

import base64
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.contracts.manifest_policy import confirm_research_contract
from app.db.models import (
    ResearchContractDraftModel,
    ResearchContractModel,
    ResearchProjectModel,
    ResearchRunModel,
)
from app.schemas.manifest import ManifestBundle
from app.schemas.core import (
    ConfirmResearchContractRequest,
    ContractDraftStatus,
    CreateResearchContractDraftRequest,
    CreateResearchProjectRequest,
    CreateRunRequest,
    ResearchContract,
    ResearchContractDraft,
    ResearchContractInput,
    ResearchProject,
    ResearchRun,
    RunEvent,
    UpdateResearchContractDraftRequest,
    compute_research_contract_content_hash,
    validate_research_contract_content_hash,
)
from app.security import SecurityProblem, canonical_request_hash, require_revision
from app.workflow.store import (
    EventSnapshot,
    PersistentWorkflowStore,
    RunNotFoundError,
    RunSnapshot,
    RunStepDefinition,
    WorkflowConflictError,
)


# The frozen canonical pipeline plan a run commits at creation. M1 has no live
# executor, so a created run stays ``queued`` with the seeded ``run.queued``
# event; the deterministic demo seed publishes a completed run separately.
CANONICAL_RUN_STEPS: tuple[RunStepDefinition, ...] = (
    RunStepDefinition(
        key="planning", label="Planning", enter_status="planning", success_status="fetching_data"
    ),
    RunStepDefinition(
        key="fetching_data",
        label="Fetching data",
        enter_status="fetching_data",
        success_status="cleaning_data",
    ),
    RunStepDefinition(
        key="cleaning_data",
        label="Cleaning data",
        enter_status="cleaning_data",
        success_status="searching_papers",
    ),
    RunStepDefinition(
        key="searching_papers",
        label="Searching papers",
        enter_status="searching_papers",
        success_status="summarizing_papers",
    ),
    RunStepDefinition(
        key="summarizing_papers",
        label="Summarizing papers",
        enter_status="summarizing_papers",
        success_status="reasoning_literature",
    ),
    RunStepDefinition(
        key="reasoning_literature",
        label="Reasoning over literature",
        enter_status="reasoning_literature",
        success_status="building_graph",
    ),
    RunStepDefinition(
        key="building_graph",
        label="Building graph",
        enter_status="building_graph",
        success_status="completed",
    ),
)


class ResearchApplicationService:
    """Ownership-scoped reads/writes for Project, Draft, Contract and Run."""

    def __init__(
        self,
        *,
        factory: Callable[[], Session],
        workflow_store: PersistentWorkflowStore,
        manifests: ManifestBundle,
    ) -> None:
        self._factory = factory
        self._workflow = workflow_store
        self._manifests = manifests

    # ---- Project ---------------------------------------------------------

    def get_project(self, *, project_id: str, session_id: str) -> ResearchProject:
        with self._factory() as session:
            project = self._require_project(session, project_id, session_id)
            return self._project_read(session, project)

    def list_projects(
        self, *, session_id: str, cursor: str | None, limit: int
    ) -> tuple[tuple[ResearchProject, ...], str | None, bool]:
        """Session-scoped project listing with a stable keyset cursor.

        Ordered by ``(created_at DESC, id DESC)`` so newly created projects
        appear first and the ordering is total (id breaks timestamp ties).
        """
        with self._factory() as session:
            query = select(ResearchProjectModel).where(
                ResearchProjectModel.session_id == session_id
            )
            if cursor is not None:
                anchor_uuid = _decode_project_cursor(cursor)
                anchor = session.get(ResearchProjectModel, anchor_uuid)
                if anchor is None or anchor.session_id != session_id:
                    raise _invalid_cursor()
                query = query.where(
                    (ResearchProjectModel.created_at < anchor.created_at)
                    | (
                        (ResearchProjectModel.created_at == anchor.created_at)
                        & (ResearchProjectModel.id < anchor.id)
                    )
                )
            rows = (
                session.scalars(
                    query.order_by(
                        ResearchProjectModel.created_at.desc(),
                        ResearchProjectModel.id.desc(),
                    ).limit(limit + 1)
                )
            ).all()
            has_more = len(rows) > limit
            selected = rows[:limit]
            next_cursor = (
                _encode_project_cursor(selected[-1].id)
                if selected and has_more
                else None
            )
            return (
                tuple(self._project_read(session, row) for row in selected),
                next_cursor,
                has_more,
            )

    def create_project(
        self,
        *,
        session_id: str,
        idempotency_key: str,
        request: CreateResearchProjectRequest,
    ) -> ResearchProject:
        request_hash = canonical_request_hash(request.model_dump(mode="json"))
        with self._factory() as session, session.begin():
            replay = session.scalar(
                select(ResearchProjectModel).where(
                    ResearchProjectModel.session_id == session_id,
                    ResearchProjectModel.idempotency_key == idempotency_key,
                )
            )
            if replay is not None:
                if replay.request_hash != request_hash:
                    raise _idempotency_conflict()
                return self._project_read(session, replay)
            now = datetime.now(UTC)
            model = ResearchProjectModel(
                session_id=session_id,
                name=request.name,
                description=request.description,
                case_key=request.case_key,
                revision=1,
                created_at=now,
                updated_at=now,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
            )
            session.add(model)
            session.flush()
            return self._project_read(session, model)

    # ---- Contract Draft --------------------------------------------------

    def create_draft(
        self,
        *,
        project_id: str,
        session_id: str,
        idempotency_key: str,
        request: CreateResearchContractDraftRequest,
    ) -> ResearchContractDraft:
        request_hash = canonical_request_hash(request.model_dump(mode="json"))
        with self._factory() as session, session.begin():
            # The draft must bind to an existing project owned by this
            # session; cross-session and unknown projects stay hidden as 404.
            self._require_project(session, project_id, session_id)
            replay = session.scalar(
                select(ResearchContractDraftModel).where(
                    ResearchContractDraftModel.session_id == session_id,
                    ResearchContractDraftModel.idempotency_key == idempotency_key,
                )
            )
            if replay is not None:
                if replay.request_hash != request_hash:
                    raise _idempotency_conflict()
                return _draft(replay)
            now = datetime.now(UTC)
            model = ResearchContractDraftModel(
                session_id=session_id,
                version=1,
                intent=request.intent,
                status=ContractDraftStatus.draft.value,
                contract=request.contract.model_dump(mode="json"),
                warnings=[],
                created_at=now,
                updated_at=now,
                expires_at=now + DRAFT_TTL,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
            )
            session.add(model)
            session.flush()
            return _draft(model)

    def get_draft(self, *, draft_id: str, session_id: str) -> ResearchContractDraft:
        draft_uuid = _uuid_or_not_found(draft_id, "DRAFT_NOT_FOUND")
        with self._factory() as session, session.begin():
            draft = session.get(
                ResearchContractDraftModel, draft_uuid, with_for_update=True
            )
            if draft is None or draft.session_id != session_id:
                raise _not_found("DRAFT_NOT_FOUND")
            _expire_draft(draft)
            return _draft(draft)

    def update_draft(
        self,
        *,
        draft_id: str,
        session_id: str,
        if_match: str,
        request: UpdateResearchContractDraftRequest,
    ) -> ResearchContractDraft:
        expected = _parse_if_match(if_match)
        draft_uuid = _uuid_or_not_found(draft_id, "DRAFT_NOT_FOUND")
        with self._factory() as session, session.begin():
            draft = session.get(
                ResearchContractDraftModel, draft_uuid, with_for_update=True
            )
            if draft is None or draft.session_id != session_id:
                raise _not_found("DRAFT_NOT_FOUND")
            _expire_draft(draft)
            if draft.status != ContractDraftStatus.draft.value:
                raise SecurityProblem(
                    status=409,
                    code="DRAFT_NOT_EDITABLE",
                    title="Draft not editable",
                    detail="Only a draft in the draft state can be updated",
                )
            require_revision(expected=expected, current=draft.version)
            if request.intent is not None:
                draft.intent = request.intent
            if request.contract is not None:
                draft.contract = request.contract.model_dump(mode="json")
            draft.version += 1
            draft.updated_at = datetime.now(UTC)
            session.flush()
            return _draft(draft)

    # ---- Contract --------------------------------------------------------

    def get_contract(self, *, contract_id: str, session_id: str) -> ResearchContract:
        contract_uuid = _uuid_or_not_found(contract_id, "CONTRACT_NOT_FOUND")
        with self._factory() as session:
            contract = session.get(ResearchContractModel, contract_uuid)
            if contract is None:
                raise _not_found("CONTRACT_NOT_FOUND")
            self._require_project(session, str(contract.project_id), session_id)
            if contract.content is None or contract.created_from_draft_id is None:
                raise _not_found("CONTRACT_NOT_FOUND")
            return _contract(contract)

    def confirm_contract(
        self,
        *,
        project_id: str,
        session_id: str,
        idempotency_key: str,
        request: ConfirmResearchContractRequest,
    ) -> ResearchContract:
        draft_uuid = _uuid_or_not_found(request.draft_id, "DRAFT_NOT_FOUND")
        request_hash = canonical_request_hash(request.model_dump(mode="json"))
        with self._factory() as session, session.begin():
            project = self._require_project(
                session, project_id, session_id, with_for_update=True
            )
            replay = session.scalar(
                select(ResearchContractModel).where(
                    ResearchContractModel.project_id == project.id,
                    ResearchContractModel.idempotency_key == idempotency_key,
                )
            )
            if replay is not None:
                if replay.request_hash != request_hash:
                    raise _idempotency_conflict()
                return _contract(replay)
            draft = session.get(
                ResearchContractDraftModel, draft_uuid, with_for_update=True
            )
            if draft is None or draft.session_id != session_id:
                raise _not_found("DRAFT_NOT_FOUND")
            _expire_draft(draft)
            if draft.status != ContractDraftStatus.draft.value:
                raise SecurityProblem(
                    status=409,
                    code="DRAFT_NOT_EDITABLE",
                    title="Draft not editable",
                    detail="Only a draft in the draft state can be confirmed",
                )
            require_revision(
                expected=request.expected_draft_version, current=draft.version
            )
            contract_input = _contract_input(draft.contract)
            content_hash = compute_research_contract_content_hash(contract_input)
            next_version = (
                session.scalar(
                    select(func.coalesce(func.max(ResearchContractModel.version), 0)).where(
                        ResearchContractModel.project_id == project.id
                    )
                )
                or 0
            ) + 1
            confirmed = _confirm_or_reject(
                contract_input,
                project_id=str(project.id),
                version=next_version,
                created_from_draft_id=str(draft.id),
                content_hash=content_hash,
                case_key=project.case_key,
                manifests=self._manifests,
            )
            model = ResearchContractModel(
                project_id=project.id,
                version=next_version,
                content_hash=content_hash,
                content=contract_input.model_dump(mode="json"),
                created_from_draft_id=draft.id,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
            )
            session.add(model)
            draft.status = ContractDraftStatus.confirmed.value
            draft.updated_at = datetime.now(UTC)
            session.flush()
            return confirmed.model_copy(update={"id": str(model.id)})

    # ---- Run + Events ----------------------------------------------------

    def create_run(
        self,
        *,
        project_id: str,
        session_id: str,
        idempotency_key: str,
        request: CreateRunRequest,
    ) -> ResearchRun:
        project_uuid = _uuid_or_not_found(project_id, "PROJECT_NOT_FOUND")
        contract_uuid = _uuid_or_not_found(request.contract_id, "CONTRACT_NOT_FOUND")
        parent_uuid = (
            _uuid_or_not_found(request.parent_run_id, "RUN_NOT_FOUND")
            if request.parent_run_id is not None
            else None
        )
        with self._factory() as session:
            self._require_project(session, project_id, session_id)
            contract = session.get(ResearchContractModel, contract_uuid)
            if contract is None or contract.project_id != project_uuid:
                raise _not_found("CONTRACT_NOT_FOUND")
            if parent_uuid is not None:
                parent = session.get(ResearchRunModel, parent_uuid)
                if parent is None or parent.project_id != project_uuid:
                    raise _not_found("RUN_NOT_FOUND")
        request_hash = canonical_request_hash(request.model_dump(mode="json"))
        try:
            snapshot = self._workflow.create_run(
                project_id=project_uuid,
                contract_id=contract_uuid,
                execution_mode=request.execution_mode.value,
                cache_policy=request.cache_policy.value,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                steps=CANONICAL_RUN_STEPS,
                parent_run_id=parent_uuid,
                derivation_kind=request.derivation_kind.value,
                retry_from_step=request.retry_from_step,
            )
        except WorkflowConflictError as exc:
            raise SecurityProblem(
                status=409,
                code="IDEMPOTENCY_CONFLICT",
                title="Idempotency conflict",
                detail="The idempotency key was already used with a different request",
            ) from exc
        return _run(snapshot)

    def get_run(self, *, run_id: str, session_id: str) -> ResearchRun:
        snapshot = self._load_owned_run(run_id, session_id)
        return _run(snapshot)

    def list_run_events(
        self, *, run_id: str, session_id: str, cursor: str | None, limit: int
    ) -> tuple[tuple[RunEvent, ...], str | None, bool]:
        after = _parse_event_cursor(cursor)
        snapshot = self._load_owned_run(run_id, session_id, after_event_sequence=after, event_limit=limit)
        events = tuple(_event(item, run_id=run_id) for item in snapshot.events)
        next_cursor = (
            str(snapshot.next_event_cursor) if snapshot.has_more_events else None
        )
        return events, next_cursor, snapshot.has_more_events

    # ---- helpers ---------------------------------------------------------

    def _project_read(
        self, session: Session, project: ResearchProjectModel
    ) -> ResearchProject:
        active_contract_id = session.scalar(
            select(ResearchContractModel.id)
            .where(
                ResearchContractModel.project_id == project.id,
                ResearchContractModel.content.is_not(None),
            )
            .order_by(ResearchContractModel.version.desc())
            .limit(1)
        )
        latest_run_id = session.scalar(
            select(ResearchRunModel.id)
            .where(ResearchRunModel.project_id == project.id)
            .order_by(ResearchRunModel.created_at.desc(), ResearchRunModel.id.desc())
            .limit(1)
        )
        return _project(
            project,
            active_contract_id=active_contract_id,
            latest_run_id=latest_run_id,
        )

    def _load_owned_run(
        self,
        run_id: str,
        session_id: str,
        *,
        after_event_sequence: int = 0,
        event_limit: int = 100,
    ) -> RunSnapshot:
        run_uuid = _uuid_or_not_found(run_id, "RUN_NOT_FOUND")
        try:
            snapshot = self._workflow.load_snapshot(
                run_uuid,
                after_event_sequence=after_event_sequence,
                event_limit=event_limit,
            )
        except RunNotFoundError as exc:
            raise _not_found("RUN_NOT_FOUND") from exc
        with self._factory() as session:
            owner = session.scalar(
                select(ResearchProjectModel.session_id).where(
                    ResearchProjectModel.id == snapshot.project_id
                )
            )
        if owner is None or owner != session_id:
            raise _not_found("RUN_NOT_FOUND")
        return snapshot

    def _require_project(
        self,
        session: Session,
        project_id: str,
        session_id: str,
        *,
        with_for_update: bool = False,
    ) -> ResearchProjectModel:
        project_uuid = _uuid_or_not_found(project_id, "PROJECT_NOT_FOUND")
        project = session.get(
            ResearchProjectModel, project_uuid, with_for_update=with_for_update
        )
        if project is None or project.session_id != session_id:
            raise _not_found("PROJECT_NOT_FOUND")
        return project


def _idempotency_conflict() -> SecurityProblem:
    return SecurityProblem(
        status=409,
        code="IDEMPOTENCY_CONFLICT",
        title="Idempotency conflict",
        detail="The idempotency key was already used with a different request",
    )


# Editable drafts share the one-hour lifetime the deterministic demo seed used.
DRAFT_TTL = timedelta(hours=1)


def _encode_project_cursor(project_id: UUID) -> str:
    encoded = base64.urlsafe_b64encode(str(project_id).encode("ascii")).decode("ascii")
    return encoded.rstrip("=")


def _decode_project_cursor(cursor: str) -> UUID:
    try:
        padding = "=" * (-len(cursor) % 4)
        decoded = base64.urlsafe_b64decode(cursor + padding).decode("ascii")
        return UUID(decoded)
    except (UnicodeDecodeError, ValueError):
        raise _invalid_cursor() from None


def _invalid_cursor() -> SecurityProblem:
    return SecurityProblem(
        status=400,
        code="INVALID_CURSOR",
        title="Invalid cursor",
        detail="The pagination cursor is invalid for this collection",
    )


def _expire_draft(draft: ResearchContractDraftModel) -> None:
    now = datetime.now(UTC)
    if (
        draft.status == ContractDraftStatus.draft.value
        and _utc(draft.expires_at) <= now
    ):
        draft.status = ContractDraftStatus.expired.value
        draft.updated_at = now


def _confirm_or_reject(
    contract_input: ResearchContractInput,
    *,
    project_id: str,
    version: int,
    created_from_draft_id: str,
    content_hash: str,
    case_key: str,
    manifests: ManifestBundle,
) -> ResearchContract:
    try:
        return confirm_research_contract(
            contract_input,
            id="pending",
            project_id=project_id,
            version=version,
            created_from_draft_id=created_from_draft_id,
            created_at=datetime.now(UTC),
            content_hash=content_hash,
            case_key=case_key,
            manifests=manifests,
        )
    except ValueError as exc:
        raise SecurityProblem(
            status=422,
            code="CONTRACT_ADMISSION_FAILED",
            title="Contract admission failed",
            detail=str(exc),
        ) from exc


def _project(
    row: ResearchProjectModel,
    *,
    active_contract_id: UUID | None,
    latest_run_id: UUID | None,
) -> ResearchProject:
    return ResearchProject(
        id=str(row.id),
        session_id=row.session_id,
        name=row.name,
        description=row.description or "",
        case_key=row.case_key,
        active_contract_id=str(active_contract_id) if active_contract_id else None,
        latest_run_id=str(latest_run_id) if latest_run_id else None,
        created_at=_utc(row.created_at),
        updated_at=_utc(row.updated_at),
        revision=row.revision,
    )


def _draft(row: ResearchContractDraftModel) -> ResearchContractDraft:
    return ResearchContractDraft(
        id=str(row.id),
        session_id=row.session_id,
        version=row.version,
        intent=row.intent,
        status=row.status,
        contract=_contract_input(row.contract),
        warnings=tuple(row.warnings),
        created_at=_utc(row.created_at),
        updated_at=_utc(row.updated_at),
        expires_at=_utc(row.expires_at),
    )


def _contract(row: ResearchContractModel) -> ResearchContract:
    payload = dict(row.content or {})
    contract = ResearchContract(
        **payload,
        id=str(row.id),
        project_id=str(row.project_id),
        version=row.version,
        created_from_draft_id=str(row.created_from_draft_id),
        created_at=_utc(row.created_at),
        content_hash=row.content_hash,
    )
    return validate_research_contract_content_hash(contract)


def _contract_input(payload: dict[str, object]) -> ResearchContractInput:
    return ResearchContractInput.model_validate(payload)


def _run(snapshot: RunSnapshot) -> ResearchRun:
    return ResearchRun(
        id=str(snapshot.id),
        project_id=str(snapshot.project_id),
        contract_id=str(snapshot.contract_id),
        execution_mode=snapshot.execution_mode,
        status=snapshot.status,
        progress=snapshot.progress,
        parent_run_id=(
            str(snapshot.parent_run_id) if snapshot.parent_run_id is not None else None
        ),
        derivation_kind=snapshot.derivation_kind,
        retry_from_step=snapshot.retry_from_step,
        cache_policy=snapshot.cache_policy,
        started_at=_utc(snapshot.started_at) if snapshot.started_at else None,
        finished_at=_utc(snapshot.finished_at) if snapshot.finished_at else None,
        created_at=_utc(snapshot.created_at),
        updated_at=_utc(snapshot.updated_at),
        latest_event_sequence=snapshot.latest_event_sequence,
        failure_code=snapshot.failure_code,
        failure_summary=snapshot.failure_summary,
    )


def _event(item: EventSnapshot, *, run_id: str) -> RunEvent:
    return RunEvent(
        run_id=run_id,
        sequence=item.sequence,
        event_type=item.event_type,
        step_key=item.step_key,
        progress=item.progress,
        public_message=item.public_message,
        artifact_version_ids=tuple(item.artifact_version_ids),
        occurred_at=_utc(item.occurred_at),
    )


def _parse_if_match(if_match: str) -> int:
    try:
        return int(if_match.strip().strip('"'))
    except (AttributeError, TypeError, ValueError) as exc:
        raise SecurityProblem(
            status=400,
            code="INVALID_REQUEST",
            title="Invalid If-Match",
            detail="If-Match must be the integer draft version",
        ) from exc


def _parse_event_cursor(cursor: str | None) -> int:
    if cursor is None:
        return 0
    try:
        value = int(cursor)
    except (TypeError, ValueError) as exc:
        raise SecurityProblem(
            status=400,
            code="INVALID_CURSOR",
            title="Invalid cursor",
            detail="The event cursor must be an event sequence integer",
        ) from exc
    if value < 0:
        raise SecurityProblem(
            status=400,
            code="INVALID_CURSOR",
            title="Invalid cursor",
            detail="The event cursor must be nonnegative",
        )
    return value


def _uuid_or_not_found(value: str, code: str) -> UUID:
    try:
        return UUID(value)
    except (AttributeError, TypeError, ValueError) as exc:
        raise _not_found(code) from exc


def _not_found(code: str) -> SecurityProblem:
    return SecurityProblem(
        status=404, code=code, title="Resource not found", detail="Resource not found"
    )


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


__all__ = ["CANONICAL_RUN_STEPS", "ResearchApplicationService"]
