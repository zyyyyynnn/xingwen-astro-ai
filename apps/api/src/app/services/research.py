"""Research runtime application boundary for the current ``/api`` chain.

Router -> ResearchApplicationService -> manifest/domain admission + PostgreSQL /
PersistentWorkflowStore. Routers own HTTP/auth/DTO mapping only. This service
owns Project, ContractDraft, Contract and ResearchRun use cases while preserving
session ownership, idempotency and optimistic concurrency.
"""

from __future__ import annotations

import base64
import binascii
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
import hashlib
import hmac
import json
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import exists, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased

from app.contracts.manifest_policy import (
    validate_contract_against_manifest,
    validate_research_contract_admission,
)
from app.config import settings
from app.db.models import (
    ModelExecutionModel,
    ResearchContractDraftModel,
    ResearchContractModel,
    ResearchProjectModel,
    ResearchRunModel,
    ResearchThreadEntryModel,
    RevisionPlanConfirmationModel,
    RevisionPlanFeedbackModel,
    RevisionPlanModel,
    RevisionPlanVersionModel,
    RunCheckpointDecisionModel,
    RunCheckpointModel,
    RunStepModel,
    StepAttemptModel,
)
from app.schemas.core import (
    ArtifactKind,
    ConfirmResearchContractRequest,
    ContractDraftStatus,
    CreateResearchContractDraftRequest,
    CreateResearchProjectRequest,
    CreateRunRequest,
    ResearchContract,
    ResearchContractDraft,
    ResearchContractInput,
    ResearchProject,
    ResearchPlanningCatalog,
    ResearchCatalogOption,
    ResearchRun,
    ResearchThreadEntry,
    ResearchThreadEntryKind,
    ResearchThreadSummary,
    ResearchTurnRequest,
    ResearchTurnResult,
    RunCheckpoint,
    RunCheckpointDecisionRequest,
    RunStepRead,
    RunEvent,
    PlannerOutcome,
    PlannerOutcomeKind,
    UpdateResearchContractDraftRequest,
    UpdateResearchProjectRequest,
    compute_research_contract_content_hash,
    validate_research_contract_content_hash,
)
from app.services.research_thread import append_thread_entry
from app.schemas.manifest import ManifestBundle
from app.schemas.scientific_capabilities import planning_capabilities
from app.security import SecurityProblem, canonical_request_hash, require_revision
from app.services.model_execution import ModelExecutionError, ModelExecutionResponse
from app.services.research_planner import PlannerResult, ResearchContractPlanner
from app.workflow.run_plan import UnsupportedRunPlanError, compile_run_plan
from app.workflow.store import (
    TERMINAL_RUN_STATUSES,
    CheckpointDecisionConflictError,
    CheckpointOptionInvalidError,
    EventSnapshot,
    PersistentWorkflowStore,
    RunNotFoundError,
    RunSnapshot,
    StaleWorkflowWriteError,
    WorkflowConflictError,
)


DRAFT_TTL = timedelta(hours=1)


class ResearchApplicationService:
    """Ownership-scoped Project, ContractDraft, Contract and Run use cases."""

    def __init__(
        self,
        *,
        factory: Callable[[], Session],
        workflow_store: PersistentWorkflowStore,
        manifests: ManifestBundle,
        planner: ResearchContractPlanner | None = None,
        planner_resolver: Callable[[], ResearchContractPlanner] | None = None,
        model_execution_lease_duration: timedelta = timedelta(minutes=5),
    ) -> None:
        if model_execution_lease_duration <= timedelta(0):
            raise ValueError("model execution lease duration must be positive")
        self._factory = factory
        self._workflow = workflow_store
        self._manifests = manifests
        self._planner = planner
        self._planner_resolver = planner_resolver
        self._model_execution_lease_duration = model_execution_lease_duration

    # ---- Project ---------------------------------------------------------

    def get_project(self, *, project_id: str, session_id: str) -> ResearchProject:
        with self._factory() as session:
            project = self._require_project(session, project_id, session_id)
            return self._project_read(session, project)

    def list_projects(
        self,
        *,
        session_id: str,
        cursor: str | None,
        limit: int,
    ) -> tuple[tuple[ResearchProject, ...], str | None, bool]:
        """Return a stable newest-first session-scoped keyset page."""

        with self._factory() as session:
            query = select(ResearchProjectModel).where(
                ResearchProjectModel.session_id == session_id
            )
            if cursor is not None:
                anchor_uuid = _decode_project_cursor(cursor, session_id=session_id)
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
            rows = list(
                session.scalars(
                    query.order_by(
                        ResearchProjectModel.created_at.desc(),
                        ResearchProjectModel.id.desc(),
                    ).limit(limit + 1)
                )
            )
            has_more = len(rows) > limit
            selected = rows[:limit]
            next_cursor = (
                _encode_project_cursor(selected[-1].id, session_id=session_id)
                if selected and has_more
                else None
            )
            thread_summaries = self._thread_summaries(
                session, tuple(row.id for row in selected)
            )
            return (
                tuple(
                    self._project_read(
                        session,
                        row,
                        thread_summary=thread_summaries[row.id],
                    )
                    for row in selected
                ),
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
            replay = self._project_replay(
                session,
                session_id=session_id,
                idempotency_key=idempotency_key,
            )
            if replay is not None:
                _require_same_idempotent_request(replay.request_hash, request_hash)
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
            try:
                with session.begin_nested():
                    session.add(model)
                    session.flush()
            except IntegrityError as exc:
                replay = self._project_replay(
                    session,
                    session_id=session_id,
                    idempotency_key=idempotency_key,
                )
                if replay is None:
                    raise
                _require_same_idempotent_request(
                    replay.request_hash,
                    request_hash,
                    cause=exc,
                )
                return self._project_read(session, replay)
            return self._project_read(session, model)

    def update_project(
        self,
        *,
        project_id: str,
        session_id: str,
        if_match: str,
        request: UpdateResearchProjectRequest,
    ) -> ResearchProject:
        expected = _parse_if_match(if_match)
        with self._factory() as session, session.begin():
            project = self._require_project(
                session, project_id, session_id, with_for_update=True
            )
            require_revision(expected=expected, current=project.revision)
            project.name = request.name
            project.revision += 1
            project.updated_at = datetime.now(UTC)
            session.flush()
            return self._project_read(session, project)

    def delete_project(
        self,
        *,
        project_id: str,
        session_id: str,
        if_match: str,
    ) -> None:
        expected = _parse_if_match(if_match)
        with self._factory() as session, session.begin():
            project = self._require_project(
                session, project_id, session_id, with_for_update=True
            )
            require_revision(expected=expected, current=project.revision)
            session.delete(project)

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
            # Ownership is checked before any insert or idempotency side effect.
            project = self._require_project(
                session, project_id, session_id, with_for_update=True
            )
            replay = self._draft_replay(
                session,
                project_id=project.id,
                idempotency_key=idempotency_key,
            )
            if replay is not None:
                _require_same_idempotent_request(replay.request_hash, request_hash)
                project.active_draft_id = replay.id
                return _draft(replay)

            now = datetime.now(UTC)
            model = ResearchContractDraftModel(
                project_id=project.id,
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
            try:
                with session.begin_nested():
                    session.add(model)
                    session.flush()
            except IntegrityError as exc:
                replay = self._draft_replay(
                    session,
                    project_id=project.id,
                    idempotency_key=idempotency_key,
                )
                if replay is None:
                    raise
                _require_same_idempotent_request(
                    replay.request_hash,
                    request_hash,
                    cause=exc,
                )
                project.active_draft_id = replay.id
                return _draft(replay)
            project.active_draft_id = model.id
            return _draft(model)

    def get_draft(
        self,
        *,
        draft_id: str,
        session_id: str,
    ) -> ResearchContractDraft:
        draft_uuid = _uuid_or_not_found(draft_id, "DRAFT_NOT_FOUND")
        with self._factory() as session, session.begin():
            draft = session.get(
                ResearchContractDraftModel,
                draft_uuid,
                with_for_update=True,
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
                ResearchContractDraftModel,
                draft_uuid,
                with_for_update=True,
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
            project = self._require_project(
                session, str(draft.project_id), session_id, with_for_update=True
            )
            project.active_draft_id = draft.id
            session.flush()
            return _draft(draft)

    # ---- Contract --------------------------------------------------------

    def get_contract(
        self,
        *,
        contract_id: str,
        session_id: str,
    ) -> ResearchContract:
        contract_uuid = _uuid_or_not_found(contract_id, "CONTRACT_NOT_FOUND")
        with self._factory() as session:
            contract = session.get(ResearchContractModel, contract_uuid)
            if contract is None:
                raise _not_found("CONTRACT_NOT_FOUND")
            self._require_project(session, str(contract.project_id), session_id)
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
            # The Project lock serializes version allocation and confirmation.
            project = self._require_project(
                session,
                project_id,
                session_id,
                with_for_update=True,
            )
            replay = session.scalar(
                select(ResearchContractModel).where(
                    ResearchContractModel.project_id == project.id,
                    ResearchContractModel.idempotency_key == idempotency_key,
                )
            )
            if replay is not None:
                _require_same_idempotent_request(replay.request_hash, request_hash)
                return _contract(replay)

            draft = session.get(
                ResearchContractDraftModel,
                draft_uuid,
                with_for_update=True,
            )
            if (
                draft is None
                or draft.session_id != session_id
                or draft.project_id != project.id
            ):
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
                expected=request.expected_draft_version,
                current=draft.version,
            )

            contract_input = _contract_input(draft.contract)
            content_hash = compute_research_contract_content_hash(contract_input)
            next_version = (
                session.scalar(
                    select(
                        func.coalesce(func.max(ResearchContractModel.version), 0)
                    ).where(ResearchContractModel.project_id == project.id)
                )
                or 0
            ) + 1
            _validate_contract_admission_or_reject(
                contract_input,
                content_hash=content_hash,
                case_key=project.case_key,
                manifests=self._manifests,
            )
            created_at = datetime.now(UTC)
            model = ResearchContractModel(
                project_id=project.id,
                version=next_version,
                content_hash=content_hash,
                content=contract_input.model_dump(mode="json"),
                created_from_draft_id=draft.id,
                created_at=created_at,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
            )
            session.add(model)
            draft.status = ContractDraftStatus.confirmed.value
            draft.updated_at = created_at
            project.active_draft_id = None
            session.flush()
            return _contract(model)

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
        with self._factory() as session:
            self._require_project(session, project_id, session_id)
            contract = session.get(ResearchContractModel, contract_uuid)
            if contract is None or contract.project_id != project_uuid:
                raise _not_found("CONTRACT_NOT_FOUND")
            try:
                run_steps = compile_run_plan(_contract_input(contract.content))
            except UnsupportedRunPlanError as exc:
                raise SecurityProblem(
                    status=409,
                    code="RUN_PLAN_UNSUPPORTED_OUTPUT",
                    title="Run plan unsupported",
                    detail="The confirmed Contract requests an output without an executable RunStep mapping",
                ) from exc

        request_hash = canonical_request_hash(request.model_dump(mode="json"))
        try:
            snapshot = self._workflow.create_run(
                project_id=project_uuid,
                contract_id=contract_uuid,
                execution_mode=request.execution_mode.value,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                steps=run_steps,
            )
        except IntegrityError as exc:
            raise _active_run_conflict() from exc
        except WorkflowConflictError as exc:
            raise _idempotency_conflict() from exc
        return _run(snapshot)

    def get_run(self, *, run_id: str, session_id: str) -> ResearchRun:
        snapshot = self._load_owned_run(run_id, session_id)
        if snapshot.derivation_kind != "revision":
            return _run(snapshot)
        with self._factory() as session:
            confirmation = session.scalar(
                select(RevisionPlanConfirmationModel).where(
                    RevisionPlanConfirmationModel.run_id == snapshot.id
                )
            )
            if confirmation is None:
                raise RuntimeError("revision Run is missing its confirmed RevisionPlan")
            plan = session.get(RevisionPlanModel, confirmation.revision_plan_id)
            if plan is None:  # pragma: no cover - protected by foreign keys
                raise RuntimeError("revision Run is missing its RevisionPlan")
            feedback_ids = tuple(
                str(row.feedback_id)
                for row in session.scalars(
                    select(RevisionPlanFeedbackModel)
                    .where(
                        RevisionPlanFeedbackModel.revision_plan_id
                        == confirmation.revision_plan_id
                    )
                    .order_by(RevisionPlanFeedbackModel.position)
                )
            )
            reused_version_ids = tuple(
                str(row.artifact_version_id)
                for row in session.scalars(
                    select(RevisionPlanVersionModel)
                    .where(
                        RevisionPlanVersionModel.revision_plan_id
                        == confirmation.revision_plan_id,
                        RevisionPlanVersionModel.decision == "reuse",
                    )
                    .order_by(RevisionPlanVersionModel.position)
                )
            )
            return _run(
                snapshot,
                revision_plan_id=str(plan.id),
                feedback_ids=feedback_ids,
                recompute_steps=tuple(plan.recompute_steps),
                reused_artifact_version_ids=reused_version_ids,
            )

    def list_run_events(
        self,
        *,
        run_id: str,
        session_id: str,
        cursor: str | None,
        limit: int,
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

    def list_run_steps(
        self,
        *,
        run_id: str,
        session_id: str,
    ) -> tuple[RunStepRead, ...]:
        run_uuid = _uuid_or_not_found(run_id, "RUN_NOT_FOUND")
        with self._factory() as session:
            owner = session.scalar(
                select(ResearchProjectModel.session_id)
                .join(
                    ResearchRunModel,
                    ResearchRunModel.project_id == ResearchProjectModel.id,
                )
                .where(ResearchRunModel.id == run_uuid)
            )
            if owner is None or owner != session_id:
                raise _not_found("RUN_NOT_FOUND")
            rows = session.scalars(
                select(RunStepModel)
                .where(RunStepModel.run_id == run_uuid)
                .order_by(RunStepModel.position.asc())
            )
            return tuple(_run_step(row, run_id=run_id) for row in rows)

    def cancel_run(self, *, run_id: str, session_id: str) -> ResearchRun:
        snapshot = self._load_owned_run(run_id, session_id)
        if snapshot.status in TERMINAL_RUN_STATUSES:
            return _run(snapshot)
        try:
            self._workflow.cancel_run(
                snapshot.id,
                expected_status=snapshot.status,
                expected_revision=snapshot.revision,
                public_message="研究任务已取消。",
            )
        except StaleWorkflowWriteError as exc:
            raise SecurityProblem(
                status=409,
                code="RUN_CANCEL_CONFLICT",
                title="Run cancel conflict",
                detail="The run changed before cancellation; reload and retry.",
            ) from exc
        return _run(self._load_owned_run(run_id, session_id))

    def get_run_checkpoint(
        self, *, run_id: str, session_id: str
    ) -> RunCheckpoint | None:
        snapshot = self._load_owned_run(run_id, session_id)
        with self._factory() as session:
            checkpoint = session.scalar(
                select(RunCheckpointModel)
                .where(RunCheckpointModel.run_id == snapshot.id)
                .order_by(RunCheckpointModel.created_at.desc())
                .limit(1)
            )
            if checkpoint is None:
                # Absence of a checkpoint is a normal run state, not an error;
                # clients poll this read for every owned run.
                return None
            decision = session.get(RunCheckpointDecisionModel, checkpoint.id)
            return _run_checkpoint(checkpoint, decision, run_revision=snapshot.revision)

    def submit_run_checkpoint_decision(
        self,
        *,
        run_id: str,
        session_id: str,
        request: RunCheckpointDecisionRequest,
    ) -> ResearchRun:
        snapshot = self._load_owned_run(run_id, session_id)
        if snapshot.status in TERMINAL_RUN_STATUSES:
            raise SecurityProblem(
                status=409,
                code="RUN_CHECKPOINT_CONFLICT",
                title="Run checkpoint conflict",
                detail="The run already reached a terminal state.",
            )
        with self._factory() as session:
            checkpoint = session.scalar(
                select(RunCheckpointModel)
                .where(RunCheckpointModel.run_id == snapshot.id)
                .order_by(RunCheckpointModel.created_at.desc())
                .limit(1)
            )
            if checkpoint is None:
                raise _not_found("RUN_CHECKPOINT_NOT_FOUND")
            if str(checkpoint.id) != request.checkpoint_id:
                raise SecurityProblem(
                    status=409,
                    code="RUN_CHECKPOINT_CONFLICT",
                    title="Run checkpoint conflict",
                    detail="The checkpoint changed; reload before submitting a decision.",
                )
            checkpoint_id = checkpoint.id
        try:
            self._workflow.submit_checkpoint_decision(
                snapshot.id,
                checkpoint_id=checkpoint_id,
                selected_option=request.selected_option,
                free_text=request.free_text,
                repair_decisions=tuple(
                    item.model_dump(mode="json") for item in request.repair_decisions
                ),
                expected_status="waiting_for_input",
                expected_revision=request.expected_run_revision,
            )
        except CheckpointDecisionConflictError as exc:
            raise SecurityProblem(
                status=409,
                code="RUN_CHECKPOINT_CONFLICT",
                title="Run checkpoint conflict",
                detail="A different decision was already recorded for this checkpoint.",
            ) from exc
        except CheckpointOptionInvalidError as exc:
            raise SecurityProblem(
                status=422,
                code="RUN_CHECKPOINT_OPTION_INVALID",
                title="Run checkpoint option invalid",
                detail="The selected option is not part of the checkpoint.",
            ) from exc
        except StaleWorkflowWriteError as exc:
            raise SecurityProblem(
                status=409,
                code="RUN_CHECKPOINT_CONFLICT",
                title="Run checkpoint conflict",
                detail="The run changed before the decision committed; reload and retry.",
            ) from exc
        return _run(self._load_owned_run(run_id, session_id))

    def retry_run(
        self,
        *,
        run_id: str,
        session_id: str,
        idempotency_key: str,
    ) -> ResearchRun:
        snapshot = self._load_owned_run(run_id, session_id)
        if snapshot.status != "failed":
            raise SecurityProblem(
                status=409,
                code="RUN_RETRY_NOT_ALLOWED",
                title="Run retry not allowed",
                detail="Only a failed run can be retried.",
            )
        with self._factory() as session:
            failed_step = session.scalar(
                select(RunStepModel)
                .where(
                    RunStepModel.run_id == snapshot.id,
                    RunStepModel.status == "failed",
                )
                .order_by(RunStepModel.position.asc())
                .limit(1)
            )
            if failed_step is None:
                raise SecurityProblem(
                    status=409,
                    code="RUN_RETRY_NOT_ALLOWED",
                    title="Run retry not allowed",
                    detail="The failed run has no failed step to retry from.",
                )
            retryable = session.scalar(
                select(StepAttemptModel.retryable)
                .where(
                    StepAttemptModel.run_step_id == failed_step.id,
                    StepAttemptModel.status == "failed",
                )
                .order_by(StepAttemptModel.attempt_number.desc())
                .limit(1)
            )
            if not retryable:
                raise SecurityProblem(
                    status=409,
                    code="RUN_RETRY_NOT_ALLOWED",
                    title="Run retry not allowed",
                    detail="The failed step is not retryable.",
                )
            retry_from_step = failed_step.key
            contract = session.get(ResearchContractModel, snapshot.contract_id)
            if contract is None:  # pragma: no cover - protected by foreign keys
                raise _not_found("CONTRACT_NOT_FOUND")
            try:
                run_steps = compile_run_plan(_contract_input(contract.content))
            except UnsupportedRunPlanError as exc:
                raise SecurityProblem(
                    status=409,
                    code="RUN_PLAN_UNSUPPORTED_OUTPUT",
                    title="Run plan unsupported",
                    detail="The confirmed Contract requests an output without an executable RunStep mapping",
                ) from exc
            retry_position = next(
                (
                    position
                    for position, definition in enumerate(run_steps)
                    if definition.key == retry_from_step
                ),
                None,
            )
            if retry_position is None:
                raise SecurityProblem(
                    status=409,
                    code="RUN_RETRY_NOT_ALLOWED",
                    title="Run retry not allowed",
                    detail="The failed step is not part of the current run plan.",
                )
            skipped = {
                definition.key
                for position, definition in enumerate(run_steps)
                if position < retry_position
            }
            request_hash = canonical_request_hash(
                {
                    "parent_run_id": str(snapshot.id),
                    "derivation_kind": "retry",
                    "retry_from_step": retry_from_step,
                }
            )
            try:
                with session.begin():
                    derived_run_id = self._workflow.create_run_in_session(
                        session,
                        project_id=snapshot.project_id,
                        contract_id=snapshot.contract_id,
                        execution_mode=snapshot.execution_mode,
                        idempotency_key=idempotency_key,
                        request_hash=request_hash,
                        steps=run_steps,
                        parent_run_id=snapshot.id,
                        derivation_kind="retry",
                        retry_from_step=retry_from_step,
                        queued_message="重试任务已进入执行队列。",
                    )
                    if skipped:
                        session.execute(
                            update(RunStepModel)
                            .where(
                                RunStepModel.run_id == derived_run_id,
                                RunStepModel.key.in_(skipped),
                            )
                            .values(status="skipped")
                            .execution_options(synchronize_session=False)
                        )
            except WorkflowConflictError as exc:
                raise _idempotency_conflict() from exc
        return _run(self._load_owned_run(str(derived_run_id), session_id))

    def list_thread_entries(
        self,
        *,
        project_id: str,
        session_id: str,
        cursor: str | None,
        limit: int,
    ) -> tuple[tuple[ResearchThreadEntry, ...], str | None, bool]:
        with self._factory() as session:
            project = self._require_project(session, project_id, session_id)
            after = _decode_thread_cursor(cursor, project_id=project.id)
            query = select(ResearchThreadEntryModel).where(
                ResearchThreadEntryModel.project_id == project.id,
                ResearchThreadEntryModel.sequence > after,
            )
            rows = list(
                session.scalars(
                    query.order_by(ResearchThreadEntryModel.sequence.asc()).limit(
                        limit + 1
                    )
                )
            )
            has_more = len(rows) > limit
            selected = rows[:limit]
            next_cursor = (
                _encode_thread_cursor(
                    project_id=project.id,
                    sequence=selected[-1].sequence,
                )
                if selected and has_more
                else None
            )
            return tuple(_thread_entry(row) for row in selected), next_cursor, has_more

    def get_research_catalog(
        self,
        *,
        project_id: str,
        session_id: str,
    ) -> ResearchPlanningCatalog:
        with self._factory() as session:
            project = self._require_project(session, project_id, session_id)
            return _research_planning_catalog(
                project_id=str(project.id),
                case_key=project.case_key,
                manifests=self._manifests,
            )

    def submit_research_turn(
        self,
        *,
        project_id: str,
        session_id: str,
        idempotency_key: str,
        request: ResearchTurnRequest,
    ) -> ResearchTurnResult:
        planner = self._planner_resolver() if self._planner_resolver else self._planner
        if planner is None:
            raise SecurityProblem(
                status=503,
                code="MODEL_RUNTIME_UNAVAILABLE",
                title="Research assistant unavailable",
                detail="研究助手暂时不可用，请稍后重试。",
            )

        request_hash = canonical_request_hash(request.model_dump(mode="json"))
        project_uuid = _uuid_or_not_found(project_id, "PROJECT_NOT_FOUND")
        research_intent = request.message
        with self._factory() as session, session.begin():
            project = self._require_project(
                session, project_id, session_id, with_for_update=True
            )
            now = datetime.now(UTC)
            _expire_stale_model_executions(session, project=project, now=now)
            replay = session.scalar(
                select(ModelExecutionModel).where(
                    ModelExecutionModel.project_id == project_uuid,
                    ModelExecutionModel.idempotency_key == idempotency_key,
                )
            )
            if replay is not None:
                _require_same_idempotent_request(replay.request_hash, request_hash)
                if replay.status in {"pending", "running"}:
                    raise _research_assistant_busy()
                if replay.status != "succeeded":
                    raise _execution_failure(replay.error_code)
                return _turn_result(session, project, replay)

            active_execution_id = session.scalar(
                select(ModelExecutionModel.id)
                .where(
                    ModelExecutionModel.project_id == project.id,
                    ModelExecutionModel.status.in_(("pending", "running")),
                )
                .limit(1)
            )
            if active_execution_id is not None:
                raise _research_assistant_busy()

            if request.answer_to_question_id is not None:
                question_id = _uuid_or_not_found(
                    request.answer_to_question_id, "QUESTION_NOT_FOUND"
                )
                question = session.scalar(
                    select(ResearchThreadEntryModel).where(
                        ResearchThreadEntryModel.id == question_id,
                        ResearchThreadEntryModel.project_id == project.id,
                        ResearchThreadEntryModel.kind
                        == ResearchThreadEntryKind.clarification_question.value,
                    )
                )
                if question is None:
                    raise _not_found("QUESTION_NOT_FOUND")
                research_intent = _root_research_intent(
                    session,
                    project_id=project.id,
                    question=question,
                )

            current_entries = tuple(
                _thread_entry(row)
                for row in session.scalars(
                    select(ResearchThreadEntryModel)
                    .where(ResearchThreadEntryModel.project_id == project.id)
                    .order_by(ResearchThreadEntryModel.sequence.asc())
                )
            )
            project_read = self._project_read(session, project)
            prepared_request = planner.prepare_request(
                project=project_read,
                entries=current_entries,
                message=request.message,
                answer_to_question_id=request.answer_to_question_id,
            )
            lease_token = uuid4()
            execution = ModelExecutionModel(
                project_id=project.id,
                provider=prepared_request.provider,
                requested_model=prepared_request.requested_model,
                provider_returned_model=None,
                explicit_revision=prepared_request.explicit_revision,
                prompt_name=prepared_request.prompt_name,
                prompt_version=prepared_request.prompt_version,
                prompt_hash=prepared_request.prompt_hash,
                prompt_snapshot=prepared_request.prompt,
                input_hash=prepared_request.input_hash,
                input_snapshot=prepared_request.input_payload,
                parameters_hash=prepared_request.parameters_hash,
                parameters_snapshot=prepared_request.parameters,
                status="pending",
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                lease_token=lease_token,
                lease_expires_at=now + self._model_execution_lease_duration,
                created_at=now,
            )
            session.add(execution)
            session.flush()
            append_thread_entry(
                session,
                project_id=project.id,
                kind=(
                    ResearchThreadEntryKind.clarification_answer
                    if request.answer_to_question_id is not None
                    else ResearchThreadEntryKind.user_message
                ),
                actor="user",
                public_content=request.message,
                structured_payload={
                    "answer_to_question_id": request.answer_to_question_id,
                },
                model_execution_id=execution.id,
            )
            execution_id = execution.id

        with self._factory() as session, session.begin():
            execution = session.get(
                ModelExecutionModel, execution_id, with_for_update=True
            )
            if (
                execution is not None
                and execution.status == "pending"
                and execution.lease_token == lease_token
                and execution.lease_expires_at is not None
                and execution.lease_expires_at > datetime.now(UTC)
            ):
                execution.status = "running"
            else:
                raise _research_assistant_busy()

        try:
            planner_result = planner.execute(prepared_request)
            _validate_planner_outcome(
                planner_result.output,
                case_key=project_read.case_key,
                manifests=self._manifests,
                response=planner_result.response,
            )
        except ModelExecutionError as exc:
            self._finish_failed_turn(
                execution_id=execution_id,
                project_id=project_uuid,
                lease_token=lease_token,
                error=exc,
            )
            raise SecurityProblem(
                status=503,
                code=exc.code,
                title="Research assistant unavailable",
                detail=exc.public_message,
            ) from exc
        except Exception as exc:  # noqa: BLE001
            safe_error = ModelExecutionError(
                "MODEL_RUNTIME_UNAVAILABLE", "研究助手暂时不可用，请稍后重试。"
            )
            self._finish_failed_turn(
                execution_id=execution_id,
                project_id=project_uuid,
                lease_token=lease_token,
                error=safe_error,
            )
            raise SecurityProblem(
                status=503,
                code=safe_error.code,
                title="Research assistant unavailable",
                detail=safe_error.public_message,
            ) from exc

        try:
            return self._persist_successful_turn(
                project_id=project_id,
                project_uuid=project_uuid,
                session_id=session_id,
                execution_id=execution_id,
                lease_token=lease_token,
                request_hash=request_hash,
                research_intent=research_intent,
                planner_result=planner_result,
            )
        except Exception as exc:  # noqa: BLE001
            safe_error = ModelExecutionError(
                "MODEL_RESULT_PERSISTENCE_FAILED",
                "研究结果暂时无法保存，请稍后重新发送。",
                output_hash=planner_result.response.output_hash,
                token_usage=planner_result.response.token_usage,
                latency_ms=planner_result.response.latency_ms,
                provider_request_id=planner_result.response.provider_request_id,
            )
            self._finish_failed_turn(
                execution_id=execution_id,
                project_id=project_uuid,
                lease_token=lease_token,
                error=safe_error,
            )
            raise SecurityProblem(
                status=503,
                code=safe_error.code,
                title="Research result unavailable",
                detail=safe_error.public_message,
            ) from exc

    # ---- helpers ---------------------------------------------------------

    def _persist_successful_turn(
        self,
        *,
        project_id: str,
        project_uuid: UUID,
        session_id: str,
        execution_id: UUID,
        lease_token: UUID,
        request_hash: str,
        research_intent: str,
        planner_result: PlannerResult,
    ) -> ResearchTurnResult:
        with self._factory() as session, session.begin():
            project = self._require_project(
                session, project_id, session_id, with_for_update=True
            )
            execution = session.get(
                ModelExecutionModel, execution_id, with_for_update=True
            )
            now = datetime.now(UTC)
            if (
                execution is None
                or execution.project_id != project_uuid
                or execution.status != "running"
                or execution.lease_token != lease_token
                or execution.lease_expires_at is None
                or execution.lease_expires_at <= now
            ):
                raise RuntimeError("model execution lease was lost before persistence")
            execution.status = "succeeded"
            execution.output_hash = planner_result.response.output_hash
            execution.output_snapshot = planner_result.output.model_dump(mode="json")
            execution.token_usage = planner_result.response.token_usage
            execution.latency_ms = planner_result.response.latency_ms
            execution.provider_request_id = planner_result.response.provider_request_id
            execution.provider_returned_model = (
                planner_result.response.provider_returned_model
            )
            execution.finished_at = now
            output = planner_result.output
            outcome = PlannerOutcomeKind(output.outcome)
            draft_id: UUID | None = None
            if output.outcome == PlannerOutcomeKind.draft_ready.value:
                draft = ResearchContractDraftModel(
                    project_id=project.id,
                    session_id=session_id,
                    version=1,
                    intent=research_intent,
                    status=ContractDraftStatus.draft.value,
                    contract=output.contract.model_dump(mode="json"),
                    warnings=list(output.warnings),
                    created_at=now,
                    updated_at=now,
                    expires_at=now + DRAFT_TTL,
                    idempotency_key=f"research-turn:{execution.id}",
                    request_hash=request_hash,
                )
                session.add(draft)
                session.flush()
                draft_id = draft.id
                project.active_draft_id = draft.id
                if project.name == "新建研究" and output.project_title:
                    project.name = output.project_title.strip()
            payload = _planner_public_payload(output, draft_id=draft_id)
            append_thread_entry(
                session,
                project_id=project.id,
                kind=ResearchThreadEntryKind.assistant_reasoning,
                actor="assistant",
                public_content=output.public_analysis,
                structured_payload={**payload, "analysis_type": "public"},
                model_execution_id=execution.id,
            )
            append_thread_entry(
                session,
                project_id=project.id,
                kind=ResearchThreadEntryKind.assistant_message,
                actor="assistant",
                public_content=output.assistant_message,
                structured_payload=payload,
                model_execution_id=execution.id,
            )
            if output.outcome == PlannerOutcomeKind.clarification_required.value:
                question_entry = append_thread_entry(
                    session,
                    project_id=project.id,
                    kind=ResearchThreadEntryKind.clarification_question,
                    actor="assistant",
                    public_content=output.question,
                    structured_payload={**payload},
                    model_execution_id=execution.id,
                )
                question_entry.structured_payload = {
                    **payload,
                    "question_id": str(question_entry.id),
                }
                session.flush()
            entries = tuple(
                _thread_entry(row)
                for row in session.scalars(
                    select(ResearchThreadEntryModel)
                    .where(ResearchThreadEntryModel.model_execution_id == execution.id)
                    .order_by(ResearchThreadEntryModel.sequence.asc())
                )
            )
            return ResearchTurnResult(
                outcome=outcome,
                entries=entries,
                active_draft_id=(
                    str(project.active_draft_id) if project.active_draft_id else None
                ),
                model_execution_id=str(execution.id),
            )

    def _project_read(
        self,
        session: Session,
        project: ResearchProjectModel,
        *,
        thread_summary: ResearchThreadSummary | None = None,
    ) -> ResearchProject:
        active_contract_id = session.scalar(
            select(ResearchContractModel.id)
            .where(ResearchContractModel.project_id == project.id)
            .order_by(ResearchContractModel.version.desc())
            .limit(1)
        )
        latest_run = session.scalar(
            select(ResearchRunModel)
            .where(ResearchRunModel.project_id == project.id)
            .order_by(
                ResearchRunModel.created_at.desc(),
                ResearchRunModel.id.desc(),
            )
            .limit(1)
        )
        return _project(
            project,
            active_contract_id=active_contract_id,
            latest_run=latest_run,
            thread_summary=(
                thread_summary
                if thread_summary is not None
                else self._thread_summaries(session, (project.id,))[project.id]
            ),
        )

    def _thread_summaries(
        self,
        session: Session,
        project_ids: tuple[UUID, ...],
    ) -> dict[UUID, ResearchThreadSummary]:
        summaries = {
            project_id: ResearchThreadSummary(
                has_thread_entries=False,
                latest_thread_actor=None,
                has_unanswered_clarification=False,
            )
            for project_id in project_ids
        }
        if not project_ids:
            return summaries

        latest = (
            select(
                ResearchThreadEntryModel.project_id.label("project_id"),
                ResearchThreadEntryModel.actor.label("actor"),
                func.row_number()
                .over(
                    partition_by=ResearchThreadEntryModel.project_id,
                    order_by=ResearchThreadEntryModel.sequence.desc(),
                )
                .label("row_number"),
            )
            .where(ResearchThreadEntryModel.project_id.in_(project_ids))
            .subquery()
        )
        question = aliased(ResearchThreadEntryModel)
        answer = aliased(ResearchThreadEntryModel)
        matching_answer = exists(
            select(answer.id).where(
                answer.project_id == question.project_id,
                answer.kind == ResearchThreadEntryKind.clarification_answer.value,
                answer.structured_payload["answer_to_question_id"].astext
                == question.structured_payload["question_id"].astext,
            )
        )
        unanswered = (
            select(question.project_id.label("project_id"))
            .where(
                question.project_id.in_(project_ids),
                question.kind == ResearchThreadEntryKind.clarification_question.value,
                ~matching_answer,
            )
            .distinct()
            .subquery()
        )
        rows = session.execute(
            select(
                latest.c.project_id,
                latest.c.actor,
                unanswered.c.project_id.is_not(None).label(
                    "has_unanswered_clarification"
                ),
            )
            .outerjoin(
                unanswered,
                unanswered.c.project_id == latest.c.project_id,
            )
            .where(latest.c.row_number == 1)
        )
        for project_id, actor, has_unanswered_clarification in rows:
            summaries[project_id] = ResearchThreadSummary(
                has_thread_entries=True,
                latest_thread_actor=actor,
                has_unanswered_clarification=has_unanswered_clarification,
            )
        return summaries

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

    def _finish_failed_turn(
        self,
        *,
        execution_id: UUID,
        project_id: UUID,
        lease_token: UUID,
        error: ModelExecutionError,
    ) -> None:
        with self._factory() as session, session.begin():
            project = session.get(
                ResearchProjectModel, project_id, with_for_update=True
            )
            execution = session.get(
                ModelExecutionModel, execution_id, with_for_update=True
            )
            if project is None or execution is None:
                return
            if (
                execution.status not in {"pending", "running"}
                or execution.lease_token != lease_token
                or execution.lease_expires_at is None
                or execution.lease_expires_at <= datetime.now(UTC)
            ):
                return
            execution.status = "failed"
            execution.output_hash = error.output_hash
            execution.token_usage = error.token_usage
            execution.latency_ms = error.latency_ms
            execution.provider_request_id = error.provider_request_id
            execution.error_code = error.code
            execution.error_summary = error.public_message
            execution.finished_at = datetime.now(UTC)
            append_thread_entry(
                session,
                project_id=project.id,
                kind=ResearchThreadEntryKind.assistant_message,
                actor="assistant",
                public_content=error.public_message,
                structured_payload={
                    "outcome": "unavailable",
                    "error_code": error.code,
                },
                model_execution_id=execution.id,
            )

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
            ResearchProjectModel,
            project_uuid,
            with_for_update=with_for_update,
        )
        if project is None or project.session_id != session_id:
            raise _not_found("PROJECT_NOT_FOUND")
        return project

    @staticmethod
    def _require_no_active_run(session: Session, project_uuid: UUID) -> None:
        """One non-terminal Run per Project; the partial unique index is the fence."""

        active_run_id = session.scalar(
            select(ResearchRunModel.id)
            .where(
                ResearchRunModel.project_id == project_uuid,
                ResearchRunModel.status.not_in(tuple(TERMINAL_RUN_STATUSES)),
            )
            .limit(1)
        )
        if active_run_id is not None:
            raise _active_run_conflict()

    @staticmethod
    def _project_replay(
        session: Session,
        *,
        session_id: str,
        idempotency_key: str,
    ) -> ResearchProjectModel | None:
        return session.scalar(
            select(ResearchProjectModel).where(
                ResearchProjectModel.session_id == session_id,
                ResearchProjectModel.idempotency_key == idempotency_key,
            )
        )

    @staticmethod
    def _draft_replay(
        session: Session,
        *,
        project_id: UUID,
        idempotency_key: str,
    ) -> ResearchContractDraftModel | None:
        return session.scalar(
            select(ResearchContractDraftModel).where(
                ResearchContractDraftModel.project_id == project_id,
                ResearchContractDraftModel.idempotency_key == idempotency_key,
            )
        )


def _expire_stale_model_executions(
    session: Session,
    *,
    project: ResearchProjectModel,
    now: datetime,
) -> None:
    active = tuple(
        session.scalars(
            select(ModelExecutionModel)
            .where(
                ModelExecutionModel.project_id == project.id,
                ModelExecutionModel.status.in_(("pending", "running")),
            )
            .with_for_update()
        )
    )
    for execution in active:
        if execution.lease_expires_at is not None and execution.lease_expires_at > now:
            continue
        execution.status = "failed"
        execution.error_code = "MODEL_EXECUTION_LEASE_EXPIRED"
        execution.error_summary = "研究助手上一次执行已中断，你可以重新发送研究消息。"
        execution.finished_at = now
        append_thread_entry(
            session,
            project_id=project.id,
            kind=ResearchThreadEntryKind.assistant_message,
            actor="assistant",
            public_content=execution.error_summary,
            structured_payload={
                "outcome": "unavailable",
                "error_code": execution.error_code,
            },
            model_execution_id=execution.id,
        )


def _require_same_idempotent_request(
    stored_hash: str,
    request_hash: str,
    *,
    cause: Exception | None = None,
) -> None:
    if stored_hash == request_hash:
        return
    conflict = _idempotency_conflict()
    if cause is None:
        raise conflict
    raise conflict from cause


def _idempotency_conflict() -> SecurityProblem:
    return SecurityProblem(
        status=409,
        code="IDEMPOTENCY_CONFLICT",
        title="Idempotency conflict",
        detail="The idempotency key was already used with a different request",
    )


def _active_run_conflict() -> SecurityProblem:
    return SecurityProblem(
        status=409,
        code="RUN_ACTIVE_CONFLICT",
        title="Active run conflict",
        detail="This project already has a research run in progress.",
    )


def _encode_project_cursor(project_id: UUID, *, session_id: str) -> str:
    return _encode_signed_cursor(
        {
            "collection": "research_projects",
            "session_id": session_id,
            "ordering": "created_at.desc,id.desc",
            "anchor_id": str(project_id),
        }
    )


def _decode_project_cursor(cursor: str, *, session_id: str) -> UUID:
    try:
        payload = _decode_signed_cursor(cursor)
        if (
            set(payload)
            != {
                "collection",
                "session_id",
                "ordering",
                "anchor_id",
                "signature",
            }
            or payload["collection"] != "research_projects"
            or payload["session_id"] != session_id
            or payload["ordering"] != "created_at.desc,id.desc"
        ):
            raise ValueError
        return UUID(str(payload["anchor_id"]))
    except (TypeError, ValueError):
        raise _invalid_cursor() from None


def _encode_thread_cursor(*, project_id: UUID, sequence: int) -> str:
    return _encode_signed_cursor(
        {
            "collection": "research_thread",
            "project_id": str(project_id),
            "ordering": "sequence.asc",
            "sequence": sequence,
        }
    )


def _decode_thread_cursor(cursor: str | None, *, project_id: UUID) -> int:
    if cursor is None:
        return 0
    try:
        payload = _decode_signed_cursor(cursor)
        if (
            set(payload)
            != {
                "collection",
                "project_id",
                "ordering",
                "sequence",
                "signature",
            }
            or payload["collection"] != "research_thread"
            or payload["project_id"] != str(project_id)
            or payload["ordering"] != "sequence.asc"
            or not isinstance(payload["sequence"], int)
            or payload["sequence"] < 0
        ):
            raise ValueError
        return payload["sequence"]
    except (TypeError, ValueError):
        raise _invalid_cursor() from None


def _encode_signed_cursor(payload: dict[str, Any]) -> str:
    signed = {**payload, "signature": _cursor_signature(payload)}
    encoded = json.dumps(
        signed,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(encoded).decode("ascii").rstrip("=")


def _decode_signed_cursor(cursor: str) -> dict[str, Any]:
    try:
        if not cursor or len(cursor) > 4096:
            raise ValueError
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(
            base64.b64decode(padded, altchars=b"-_", validate=True).decode("utf-8")
        )
        if not isinstance(payload, dict) or not isinstance(
            payload.get("signature"), str
        ):
            raise ValueError
        unsigned = {key: value for key, value in payload.items() if key != "signature"}
        if not hmac.compare_digest(payload["signature"], _cursor_signature(unsigned)):
            raise ValueError
        return payload
    except (binascii.Error, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError from exc


def _cursor_signature(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    key = settings.CURSOR_SIGNING_KEY.get_secret_value().encode("utf-8")
    return hmac.new(key, canonical, hashlib.sha256).hexdigest()


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


def _validate_contract_admission_or_reject(
    contract_input: ResearchContractInput,
    *,
    content_hash: str,
    case_key: str,
    manifests: ManifestBundle,
) -> None:
    try:
        validate_research_contract_admission(
            contract_input,
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


def _validate_planner_outcome(
    output: PlannerOutcome,
    *,
    case_key: str,
    manifests: ManifestBundle,
    response: ModelExecutionResponse,
) -> None:
    if output.outcome != PlannerOutcomeKind.draft_ready.value:
        return
    try:
        validate_contract_against_manifest(
            output.contract,
            case_key=case_key,
            manifests=manifests,
        )
    except ValueError as exc:
        raise ModelExecutionError(
            "MODEL_RESPONSE_INVALID",
            "研究助手生成的协议超出当前研究目录，请重试或调整研究范围。",
            output_hash=response.output_hash,
            token_usage=response.token_usage,
            latency_ms=response.latency_ms,
            provider_request_id=response.provider_request_id,
        ) from exc


def _project(
    row: ResearchProjectModel,
    *,
    active_contract_id: UUID | None,
    latest_run: ResearchRunModel | None,
    thread_summary: ResearchThreadSummary,
) -> ResearchProject:
    return ResearchProject(
        id=str(row.id),
        session_id=row.session_id,
        name=row.name,
        description=row.description,
        case_key=row.case_key,
        active_draft_id=str(row.active_draft_id) if row.active_draft_id else None,
        active_contract_id=str(active_contract_id) if active_contract_id else None,
        latest_run_id=str(latest_run.id) if latest_run else None,
        latest_run_status=latest_run.status if latest_run else None,
        latest_run_failure_summary=latest_run.failure_summary if latest_run else None,
        thread_summary=thread_summary,
        created_at=_utc(row.created_at),
        updated_at=_utc(row.updated_at),
        revision=row.revision,
    )


def _draft(row: ResearchContractDraftModel) -> ResearchContractDraft:
    return ResearchContractDraft(
        id=str(row.id),
        project_id=str(row.project_id),
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


def _run(
    snapshot: RunSnapshot,
    *,
    revision_plan_id: str | None = None,
    feedback_ids: tuple[str, ...] = (),
    recompute_steps: tuple[str, ...] = (),
    reused_artifact_version_ids: tuple[str, ...] = (),
) -> ResearchRun:
    return ResearchRun(
        id=str(snapshot.id),
        project_id=str(snapshot.project_id),
        contract_id=str(snapshot.contract_id),
        execution_mode=snapshot.execution_mode,
        status=snapshot.status,
        progress=snapshot.progress,
        revision=snapshot.revision,
        parent_run_id=(str(snapshot.parent_run_id) if snapshot.parent_run_id else None),
        derivation_kind=snapshot.derivation_kind,
        retry_from_step=snapshot.retry_from_step,
        cache_policy=snapshot.cache_policy,
        revision_plan_id=revision_plan_id,
        feedback_ids=feedback_ids,
        recompute_steps=recompute_steps,
        reused_artifact_version_ids=reused_artifact_version_ids,
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
        activity_id=item.activity_id,
        activity_kind=item.activity_kind,
        activity_phase=item.activity_phase,
        activity_name=item.activity_name,
        step_key=item.step_key,
        progress=item.progress,
        content=item.content,
        details=item.details,
        artifact_version_ids=tuple(item.artifact_version_ids),
        occurred_at=_utc(item.occurred_at),
    )


def _run_step(row: RunStepModel, *, run_id: str) -> RunStepRead:
    return RunStepRead(
        id=str(row.id),
        run_id=run_id,
        position=row.position,
        key=row.key,
        label=row.label,
        phase=row.enter_status,
        task_id=row.task_id,
        skill_id=row.skill_id,
        depends_on_step_keys=tuple(row.depends_on_step_keys),
        status=row.status,
        progress=row.progress,
        public_message=row.public_message,
        started_at=_utc(row.started_at) if row.started_at else None,
        finished_at=_utc(row.finished_at) if row.finished_at else None,
        failure_code=row.failure_code,
    )


def _run_checkpoint(
    row: RunCheckpointModel,
    decision: RunCheckpointDecisionModel | None,
    *,
    run_revision: int,
) -> RunCheckpoint:
    return RunCheckpoint(
        id=str(row.id),
        run_id=str(row.run_id),
        run_revision=run_revision,
        step_key=row.step_key,
        question=row.question,
        options=tuple(row.options),
        kind=row.kind,
        repair_context=row.repair_context,
        created_at=_utc(row.created_at),
        selected_option=decision.selected_option if decision else None,
        free_text=decision.free_text if decision else None,
        repair_decisions=(
            tuple(decision.repair_decisions) if decision is not None else ()
        ),
        repair_outcome=(decision.repair_outcome if decision is not None else None),
        decided_at=_utc(decision.decided_at) if decision else None,
    )


def _thread_entry(row: ResearchThreadEntryModel) -> ResearchThreadEntry:
    return ResearchThreadEntry(
        id=str(row.id),
        project_id=str(row.project_id),
        sequence=row.sequence,
        kind=row.kind,
        actor=row.actor,
        public_content=row.public_content,
        structured_payload=dict(row.structured_payload),
        model_execution_id=(
            str(row.model_execution_id) if row.model_execution_id else None
        ),
        created_at=_utc(row.created_at),
    )


_TARGET_PRESENTATION = {
    "host_star": ("宿主恒星", "系外行星候选体所围绕的恒星。"),
    "exoplanet_candidate": (
        "系外行星候选体",
        "已进入候选目录、需要进一步核验的行星对象。",
    ),
}

_OUTPUT_PRESENTATION = {
    ArtifactKind.dataset: ("结构化数据", "汇总研究对象与关键字段。", "common"),
    ArtifactKind.paper_collection: ("文献候选", "保存候选文献与检索范围。", "common"),
    ArtifactKind.paper_summary: ("文献总结", "归纳与研究问题相关的证据。", "common"),
    ArtifactKind.graph: ("证据图谱", "呈现对象、主张与证据关系。", "common"),
    ArtifactKind.field_dictionary: (
        "字段字典",
        "解释数据字段、单位和含义。",
        "advanced",
    ),
    ArtifactKind.source_collection: (
        "数据来源汇总",
        "整理研究使用的数据来源。",
        "advanced",
    ),
    ArtifactKind.literature_claims: (
        "文献主张",
        "提取文献中的可核验主张。",
        "advanced",
    ),
    ArtifactKind.literature_relations: (
        "文献关系",
        "整理文献、主张和对象关系。",
        "advanced",
    ),
    ArtifactKind.export: ("导出结果", "生成可下载的研究结果包。", "advanced"),
    ArtifactKind.analysis_report: (
        "分析报告",
        "呈现科学技能产出的指标、结果与结论。",
        "common",
    ),
    ArtifactKind.visualization: (
        "科学可视化",
        "呈现图表、天图与影像等可视化结果。",
        "common",
    ),
    ArtifactKind.spectrum: ("光谱", "保存光谱数据与谱线测量。", "common"),
    ArtifactKind.light_curve: ("光变曲线", "保存光变数据与周期分析。", "common"),
    ArtifactKind.model_evaluation: (
        "模型评估",
        "记录模型训练、评估指标与诊断。",
        "advanced",
    ),
    ArtifactKind.model_artifact: (
        "模型产物",
        "保存可复用的 ONNX 模型与训练说明。",
        "advanced",
    ),
}


def _research_planning_catalog(
    *,
    project_id: str,
    case_key: str,
    manifests: ManifestBundle,
) -> ResearchPlanningCatalog:
    case = manifests.case_manifest
    if case.case_id != case_key:
        raise _not_found("RESEARCH_CATALOG_NOT_FOUND")
    source_by_provider = {
        source.provider_source_id: source for source in manifests.field_manifest.sources
    }
    return ResearchPlanningCatalog(
        project_id=project_id,
        case_key=case_key,
        target_objects=tuple(
            ResearchCatalogOption(
                value=target.role,
                label=_TARGET_PRESENTATION.get(target.role, (target.role, ""))[0],
                description=_TARGET_PRESENTATION.get(target.role, (target.role, ""))[1],
            )
            for target in case.target_objects
        ),
        requested_fields=tuple(
            ResearchCatalogOption(
                value=field.field_id,
                label=field.meaning_zh,
                description=field.description,
            )
            for field in manifests.field_manifest.fields
            if field.field_id in case.default_requested_fields
        ),
        allowed_sources=tuple(
            ResearchCatalogOption(
                value=source_id,
                label=source_by_provider[source_id].provider,
                description="当前研究案例批准使用的公开数据来源。",
            )
            for source_id in case.allowed_source_ids
        ),
        scientific_skills=tuple(
            ResearchCatalogOption(
                value=str(capability["id"]),
                label=str(capability["label"]),
                description=str(capability["description"]),
            )
            for capability in planning_capabilities()
        ),
        output_requirements=tuple(
            ResearchCatalogOption(
                value=kind.value,
                label=_OUTPUT_PRESENTATION[kind][0],
                description=_OUTPUT_PRESENTATION[kind][1],
                group=_OUTPUT_PRESENTATION[kind][2],
            )
            for kind in ArtifactKind
        ),
    )


def _root_research_intent(
    session: Session,
    *,
    project_id: UUID,
    question: ResearchThreadEntryModel,
) -> str:
    """Trace a clarification chain back to its initiating user message."""

    current = question
    visited: set[UUID] = set()
    for _ in range(40):
        if current.id in visited or current.model_execution_id is None:
            break
        visited.add(current.id)
        inbound = session.scalar(
            select(ResearchThreadEntryModel)
            .where(
                ResearchThreadEntryModel.project_id == project_id,
                ResearchThreadEntryModel.model_execution_id
                == current.model_execution_id,
                ResearchThreadEntryModel.kind.in_(
                    (
                        ResearchThreadEntryKind.user_message.value,
                        ResearchThreadEntryKind.clarification_answer.value,
                    )
                ),
            )
            .order_by(ResearchThreadEntryModel.sequence.asc())
        )
        if inbound is None:
            break
        if inbound.kind == ResearchThreadEntryKind.user_message.value:
            return inbound.public_content
        previous_id = inbound.structured_payload.get("answer_to_question_id")
        if not isinstance(previous_id, str):
            break
        previous_uuid = _uuid_or_not_found(previous_id, "QUESTION_NOT_FOUND")
        previous = session.scalar(
            select(ResearchThreadEntryModel).where(
                ResearchThreadEntryModel.id == previous_uuid,
                ResearchThreadEntryModel.project_id == project_id,
                ResearchThreadEntryModel.kind
                == ResearchThreadEntryKind.clarification_question.value,
            )
        )
        if previous is None:
            break
        current = previous
    raise _not_found("QUESTION_NOT_FOUND")


def _planner_public_payload(output: Any, *, draft_id: UUID | None) -> dict[str, Any]:  # noqa: ANN401
    payload: dict[str, Any] = {
        "outcome": output.outcome,
        "warnings": list(output.warnings),
    }
    if draft_id is not None:
        payload["draft_id"] = str(draft_id)
    if hasattr(output, "missing_information"):
        payload["missing_information"] = list(output.missing_information)
    if hasattr(output, "reason"):
        payload["reason"] = output.reason
    return payload


def _turn_result(
    session: Session,
    project: ResearchProjectModel,
    execution: ModelExecutionModel,
) -> ResearchTurnResult:
    entries = tuple(
        _thread_entry(row)
        for row in session.scalars(
            select(ResearchThreadEntryModel)
            .where(ResearchThreadEntryModel.model_execution_id == execution.id)
            .order_by(ResearchThreadEntryModel.sequence.asc())
        )
    )
    outcome_value = next(
        (
            str(entry.structured_payload["outcome"])
            for entry in entries
            if "outcome" in entry.structured_payload
        ),
        PlannerOutcomeKind.partial.value,
    )
    return ResearchTurnResult(
        outcome=PlannerOutcomeKind(outcome_value),
        entries=entries,
        active_draft_id=(
            str(project.active_draft_id) if project.active_draft_id else None
        ),
        model_execution_id=str(execution.id),
    )


def _execution_failure(code: str | None) -> SecurityProblem:
    return SecurityProblem(
        status=503,
        code=code or "MODEL_RUNTIME_UNAVAILABLE",
        title="Research assistant unavailable",
        detail="研究助手暂时不可用，请稍后重试。",
    )


def _research_assistant_busy() -> SecurityProblem:
    return SecurityProblem(
        status=409,
        code="RESEARCH_ASSISTANT_BUSY",
        title="Research assistant busy",
        detail="研究助手正在处理上一条消息，请等待完成后再发送。",
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
        status=404,
        code=code,
        title="Resource not found",
        detail="Resource not found",
    )


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


__all__ = ["ResearchApplicationService"]
