"""Session-scoped Project/Contract/Run application service backed by PostgreSQL."""

from __future__ import annotations

import base64
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    ResearchContractDraftModel,
    ResearchContractModel,
    ResearchProjectModel,
    ResearchRunModel,
)
from app.schemas.core import (
    ContractDraftStatus,
    ContractDraftUpdate,
    CreateContractDraftRequest,
    CreateProjectRequest,
    CreateRunRequest,
    ResearchContract,
    ResearchContractDraft,
    ResearchContractInput,
    ResearchProject,
    ResearchRun,
    RunEvent,
    confirm_research_contract,
    validate_research_contract_content_hash,
)
from app.schemas.manifest import ManifestBundle
from app.security import SecurityProblem
from app.services.resource_authority import canonical_request_hash
from app.workflow.store import (
    EventSnapshot,
    PersistentWorkflowStore,
    RunNotFoundError,
    RunSnapshot,
    RunStepDefinition,
    WorkflowConflictError,
)


SessionFactory = Callable[[], Session]

CANONICAL_RUN_STEPS = (
    RunStepDefinition(
        position=0,
        key="planning",
        label="Planning",
        enter_status="planning",
        success_status="fetching_data",
        max_attempts=1,
    ),
    RunStepDefinition(
        position=1,
        key="fetching_data",
        label="Fetching data",
        enter_status="fetching_data",
        success_status="cleaning_data",
        max_attempts=2,
    ),
    RunStepDefinition(
        position=2,
        key="cleaning_data",
        label="Cleaning data",
        enter_status="cleaning_data",
        success_status="searching_papers",
        max_attempts=1,
    ),
    RunStepDefinition(
        position=3,
        key="searching_papers",
        label="Searching papers",
        enter_status="searching_papers",
        success_status="summarizing_papers",
        max_attempts=2,
    ),
    RunStepDefinition(
        position=4,
        key="summarizing_papers",
        label="Summarizing papers",
        enter_status="summarizing_papers",
        success_status="reasoning_literature",
        max_attempts=1,
    ),
    RunStepDefinition(
        position=5,
        key="reasoning_literature",
        label="Reasoning literature",
        enter_status="reasoning_literature",
        success_status="building_graph",
        max_attempts=1,
    ),
    RunStepDefinition(
        position=6,
        key="building_graph",
        label="Building graph",
        enter_status="building_graph",
        success_status="completed",
        max_attempts=1,
    ),
)


class ResearchInvalidState(SecurityProblem):
    def __init__(self, detail: str) -> None:
        super().__init__(
            status=409,
            code="INVALID_STATE_TRANSITION",
            title="Invalid state transition",
            detail=detail,
        )


class ResearchApplicationService:
    """Own public authoring and Run resource application semantics."""

    def __init__(
        self,
        *,
        factory: SessionFactory,
        workflow_store: PersistentWorkflowStore,
        manifests: ManifestBundle,
    ) -> None:
        self._factory = factory
        self._workflow = workflow_store
        self._manifests = manifests

    # ---- Projects ---------------------------------------------------------

    def create_project(
        self,
        *,
        session_id: str,
        idempotency_key: str,
        request: CreateProjectRequest,
    ) -> ResearchProject:
        request_hash = canonical_request_hash(request.model_dump(mode="json"))
        with self._factory() as session, session.begin():
            existing = session.scalar(
                select(ResearchProjectModel).where(
                    ResearchProjectModel.session_id == session_id,
                    ResearchProjectModel.idempotency_key == idempotency_key,
                )
            )
            if existing is not None:
                if existing.request_hash != request_hash:
                    raise _idempotency_conflict()
                return self._project_read(session, existing)

            model = ResearchProjectModel(
                session_id=session_id,
                name=request.name,
                description=request.description,
                case_key=request.case_key,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
            )
            session.add(model)
            try:
                session.flush()
            except IntegrityError as exc:
                raise _idempotency_conflict() from exc
            return self._project_read(session, model)

    def list_projects(
        self,
        *,
        session_id: str,
        cursor: str | None,
        limit: int,
    ) -> tuple[tuple[ResearchProject, ...], str | None, bool]:
        after_id = _decode_project_cursor(cursor) if cursor else None
        with self._factory() as session:
            query = select(ResearchProjectModel).where(
                ResearchProjectModel.session_id == session_id
            )
            if after_id is not None:
                query = query.where(ResearchProjectModel.id > after_id)
            rows = tuple(
                session.scalars(
                    query.order_by(ResearchProjectModel.id).limit(limit + 1)
                )
            )
            has_more = len(rows) > limit
            page = rows[:limit]
            items = tuple(self._project_read(session, row) for row in page)
            next_cursor = (
                _encode_project_cursor(page[-1].id)
                if has_more and page
                else None
            )
            return items, next_cursor, has_more

    def get_project(self, *, project_id: str, session_id: str) -> ResearchProject:
        with self._factory() as session:
            project = self._require_project(session, project_id, session_id)
            return self._project_read(session, project)

    # ---- Contract drafts --------------------------------------------------

    def create_contract_draft(
        self,
        *,
        session_id: str,
        idempotency_key: str,
        request: CreateContractDraftRequest,
    ) -> ResearchContractDraft:
        request_hash = canonical_request_hash(request.model_dump(mode="json"))
        with self._factory() as session, session.begin():
            existing = session.scalar(
                select(ResearchContractDraftModel).where(
                    ResearchContractDraftModel.session_id == session_id,
                    ResearchContractDraftModel.idempotency_key == idempotency_key,
                )
            )
            if existing is not None:
                if existing.request_hash != request_hash:
                    raise _idempotency_conflict()
                _expire_draft(existing)
                return _draft(existing)

            now = datetime.now(UTC)
            model = ResearchContractDraftModel(
                session_id=session_id,
                intent=request.intent,
                contract=request.contract.model_dump(mode="json"),
                warnings=list(request.warnings),
                expires_at=now + DRAFT_TTL,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
            )
            session.add(model)
            try:
                session.flush()
            except IntegrityError as exc:
                raise _idempotency_conflict() from exc
            return _draft(model)

    def get_contract_draft(
        self, *, draft_id: str, session_id: str
    ) -> ResearchContractDraft:
        draft_uuid = _uuid_or_not_found(draft_id, "CONTRACT_DRAFT_NOT_FOUND")
        with self._factory() as session, session.begin():
            draft = session.get(ResearchContractDraftModel, draft_uuid)
            if draft is None or draft.session_id != session_id:
                raise _not_found("CONTRACT_DRAFT_NOT_FOUND")
            _expire_draft(draft)
            return _draft(draft)

    def update_contract_draft(
        self,
        *,
        draft_id: str,
        session_id: str,
        if_match: str,
        request: ContractDraftUpdate,
    ) -> ResearchContractDraft:
        expected_version = _parse_if_match(if_match)
        draft_uuid = _uuid_or_not_found(draft_id, "CONTRACT_DRAFT_NOT_FOUND")
        with self._factory() as session, session.begin():
            draft = session.get(
                ResearchContractDraftModel, draft_uuid, with_for_update=True
            )
            if draft is None or draft.session_id != session_id:
                raise _not_found("CONTRACT_DRAFT_NOT_FOUND")
            _expire_draft(draft)
            if draft.status != ContractDraftStatus.draft.value:
                raise ResearchInvalidState("Only draft contracts may be updated")
            if draft.version != expected_version:
                raise SecurityProblem(
                    status=412,
                    code="CONTRACT_VERSION_MISMATCH",
                    title="Contract version mismatch",
                    detail="The draft version changed; reload before updating",
                )
            if request.contract is not None:
                draft.contract = request.contract.model_dump(mode="json")
            if request.warnings is not None:
                draft.warnings = list(request.warnings)
            draft.version += 1
            draft.updated_at = datetime.now(UTC)
            session.flush()
            return _draft(draft)

    # ---- Contracts --------------------------------------------------------

    def get_contract(self, *, contract_id: str, session_id: str) -> ResearchContract:
        contract_uuid = _uuid_or_not_found(contract_id, "CONTRACT_NOT_FOUND")
        with self._factory() as session:
            row = session.get(ResearchContractModel, contract_uuid)
            if row is None:
                raise _not_found("CONTRACT_NOT_FOUND")
            project = session.get(ResearchProjectModel, row.project_id)
            if project is None or project.session_id != session_id:
                raise _not_found("CONTRACT_NOT_FOUND")
            return _contract(row)

    def confirm_contract(
        self,
        *,
        project_id: str,
        draft_id: str,
        session_id: str,
        idempotency_key: str,
    ) -> ResearchContract:
        project_uuid = _uuid_or_not_found(project_id, "PROJECT_NOT_FOUND")
        draft_uuid = _uuid_or_not_found(draft_id, "CONTRACT_DRAFT_NOT_FOUND")
        request_hash = canonical_request_hash(
            {"project_id": project_id, "draft_id": draft_id}
        )
        with self._factory() as session, session.begin():
            project = self._require_project(
                session, project_id, session_id, with_for_update=True
            )
            existing = session.scalar(
                select(ResearchContractModel).where(
                    ResearchContractModel.project_id == project_uuid,
                    ResearchContractModel.idempotency_key == idempotency_key,
                )
            )
            if existing is not None:
                if existing.request_hash != request_hash:
                    raise _idempotency_conflict()
                return _contract(existing)

            draft = session.get(
                ResearchContractDraftModel, draft_uuid, with_for_update=True
            )
            if draft is None or draft.session_id != session_id:
                raise _not_found("CONTRACT_DRAFT_NOT_FOUND")
            _expire_draft(draft)
            if draft.status != ContractDraftStatus.draft.value:
                raise ResearchInvalidState("Only draft contracts may be confirmed")
            already_confirmed = session.scalar(
                select(ResearchContractModel).where(
                    ResearchContractModel.created_from_draft_id == draft.id
                )
            )
            if already_confirmed is not None:
                raise ResearchInvalidState(
                    "This draft has already been confirmed as a Contract"
                )
            next_version = (
                session.scalar(
                    select(ResearchContractModel.version)
                    .where(ResearchContractModel.project_id == project.id)
                    .order_by(ResearchContractModel.version.desc())
                    .limit(1)
                )
                or 0
            ) + 1
            contract_input = _contract_input(draft.contract)
            content_hash = contract_input.content_hash()
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
        snapshot = self._load_owned_run(
            run_id,
            session_id,
            after_event_sequence=after,
            event_limit=limit,
        )
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
            .where(ResearchContractModel.project_id == project.id)
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


# Drafts expire after one hour.
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
    contract = ResearchContract(
        **dict(row.content),
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
