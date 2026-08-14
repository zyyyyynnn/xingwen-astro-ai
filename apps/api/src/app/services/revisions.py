"""PostgreSQL application service for Feedback and revision Run orchestration."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    ArtifactVersionModel,
    ResearchArtifactModel,
    ResearchProjectModel,
    ResearchRunModel,
    RevisionPlanConfirmationModel,
    RevisionPlanFeedbackModel,
    RevisionPlanModel,
    RevisionPlanVersionModel,
    UserFeedbackModel,
)
from app.schemas.core import ArtifactKind
from app.schemas.revision import (
    ConfirmRevisionPlanRequest,
    CreateRevisionPlanRequest,
    CreateUserFeedbackRequest,
    RevisionConflict,
    RevisionDecision,
    RevisionPlan,
    RevisionPlanStatus,
    RevisionVersionDecision,
    UserFeedback,
)
from app.security import SecurityProblem, canonical_request_hash
from app.workflow.run_plan import compile_revision_run_plan
from app.workflow.store import RUN_STEP_STATUS_ORDER, PersistentWorkflowStore

_DATA_KINDS = frozenset(
    {
        ArtifactKind.dataset,
        ArtifactKind.field_dictionary,
        ArtifactKind.source_collection,
    }
)
_LITERATURE_KINDS = frozenset(
    {
        ArtifactKind.literature_claims,
        ArtifactKind.literature_relations,
        ArtifactKind.reasoning_traces,
    }
)
_AFFECTED_KIND_CLOSURE: dict[ArtifactKind, frozenset[ArtifactKind]] = {
    **{kind: frozenset({*_DATA_KINDS, ArtifactKind.graph}) for kind in _DATA_KINDS},
    ArtifactKind.paper_collection: frozenset(
        {
            ArtifactKind.paper_collection,
            ArtifactKind.paper_summary,
            *_LITERATURE_KINDS,
            ArtifactKind.graph,
        }
    ),
    ArtifactKind.paper_summary: frozenset(
        {ArtifactKind.paper_summary, *_LITERATURE_KINDS, ArtifactKind.graph}
    ),
    ArtifactKind.literature_claims: frozenset(
        {
            ArtifactKind.literature_claims,
            ArtifactKind.literature_relations,
            ArtifactKind.reasoning_traces,
            ArtifactKind.graph,
        }
    ),
    ArtifactKind.literature_relations: frozenset(
        {
            ArtifactKind.literature_relations,
            ArtifactKind.reasoning_traces,
            ArtifactKind.graph,
        }
    ),
    ArtifactKind.reasoning_traces: frozenset(
        {ArtifactKind.reasoning_traces, ArtifactKind.graph}
    ),
    ArtifactKind.graph: frozenset({ArtifactKind.graph}),
}
_KIND_STEP = {
    ArtifactKind.dataset: "cleaning_data",
    ArtifactKind.field_dictionary: "cleaning_data",
    ArtifactKind.source_collection: "fetching_data",
    ArtifactKind.paper_collection: "searching_papers",
    ArtifactKind.paper_summary: "summarizing_papers",
    ArtifactKind.literature_claims: "reasoning_literature",
    ArtifactKind.literature_relations: "reasoning_literature",
    ArtifactKind.reasoning_traces: "reasoning_literature",
    ArtifactKind.graph: "building_graph",
}


class RevisionApplicationService:
    """Owner-scoped immutable Feedback, Plan and confirmation use cases."""

    def __init__(
        self,
        *,
        factory: Callable[[], Session],
        workflow_store: PersistentWorkflowStore,
    ) -> None:
        self._factory = factory
        self._workflow = workflow_store

    def create_feedback(
        self,
        *,
        version_id: str,
        session_id: str,
        idempotency_key: str,
        request: CreateUserFeedbackRequest,
    ) -> UserFeedback:
        version_uuid = _uuid_or_not_found(version_id, "ARTIFACT_VERSION_NOT_FOUND")
        request_hash = canonical_request_hash(
            {"version_id": version_id, **request.model_dump(mode="json")}
        )
        with self._factory() as session, session.begin():
            owned = session.execute(
                select(
                    ArtifactVersionModel, ResearchArtifactModel, ResearchProjectModel
                )
                .join(
                    ResearchArtifactModel,
                    ResearchArtifactModel.id == ArtifactVersionModel.artifact_id,
                )
                .join(
                    ResearchProjectModel,
                    ResearchProjectModel.id == ArtifactVersionModel.project_id,
                )
                .where(
                    ArtifactVersionModel.id == version_uuid,
                    ResearchProjectModel.session_id == session_id,
                )
                .with_for_update()
            ).one_or_none()
            if owned is None:
                raise _not_found("ARTIFACT_VERSION_NOT_FOUND")
            version, artifact, project = owned
            existing = session.scalar(
                select(UserFeedbackModel).where(
                    UserFeedbackModel.project_id == project.id,
                    UserFeedbackModel.idempotency_key == idempotency_key,
                )
            )
            if existing is not None:
                if existing.request_hash != request_hash:
                    raise _idempotency_conflict()
                return _feedback_read(existing)
            if (
                version.version_number != request.expected_version_number
                or artifact.latest_version_id != version.id
            ):
                raise _conflict(
                    "ARTIFACT_VERSION_CONFLICT",
                    "Feedback must target the current ArtifactVersion",
                )

            frozen = {
                "project_id": str(project.id),
                "artifact_id": str(artifact.id),
                "baseline_artifact_version_id": str(version.id),
                "baseline_version_number": version.version_number,
                "baseline_content_hash": version.content_hash,
                **request.model_dump(mode="json"),
            }
            row = UserFeedbackModel(
                id=uuid4(),
                project_id=project.id,
                owner_session_id=session_id,
                artifact_id=artifact.id,
                baseline_artifact_version_id=version.id,
                baseline_version_number=version.version_number,
                baseline_content_hash=version.content_hash,
                target_type=request.target_type.value,
                target_id=request.target_id,
                target_locator=request.target_locator,
                category=request.category.value,
                summary=request.summary,
                requested_change=request.requested_change,
                feedback_hash=canonical_request_hash(frozen),
                idempotency_key=idempotency_key,
                request_hash=request_hash,
            )
            session.add(row)
            session.flush()
            return _feedback_read(row)

    def get_feedback(self, *, feedback_id: str, session_id: str) -> UserFeedback:
        feedback_uuid = _uuid_or_not_found(feedback_id, "FEEDBACK_NOT_FOUND")
        with self._factory() as session:
            row = session.scalar(
                select(UserFeedbackModel)
                .join(
                    ResearchProjectModel,
                    ResearchProjectModel.id == UserFeedbackModel.project_id,
                )
                .where(
                    UserFeedbackModel.id == feedback_uuid,
                    ResearchProjectModel.session_id == session_id,
                )
            )
            if row is None:
                raise _not_found("FEEDBACK_NOT_FOUND")
            return _feedback_read(row)

    def create_plan(
        self,
        *,
        project_id: str,
        session_id: str,
        idempotency_key: str,
        request: CreateRevisionPlanRequest,
    ) -> RevisionPlan:
        project_uuid = _uuid_or_not_found(project_id, "PROJECT_NOT_FOUND")
        request_hash = canonical_request_hash(
            {"project_id": project_id, **request.model_dump(mode="json")}
        )
        feedback_ids = tuple(
            _uuid_or_not_found(item, "FEEDBACK_NOT_FOUND")
            for item in request.feedback_ids
        )
        with self._factory() as session, session.begin():
            project = session.scalar(
                select(ResearchProjectModel)
                .where(
                    ResearchProjectModel.id == project_uuid,
                    ResearchProjectModel.session_id == session_id,
                )
                .with_for_update()
            )
            if project is None:
                raise _not_found("PROJECT_NOT_FOUND")
            existing = session.scalar(
                select(RevisionPlanModel).where(
                    RevisionPlanModel.project_id == project.id,
                    RevisionPlanModel.idempotency_key == idempotency_key,
                )
            )
            if existing is not None:
                if existing.request_hash != request_hash:
                    raise _idempotency_conflict()
                return self._plan_read(session, existing)

            feedback_rows = tuple(
                session.scalars(
                    select(UserFeedbackModel).where(
                        UserFeedbackModel.project_id == project.id,
                        UserFeedbackModel.id.in_(feedback_ids),
                    )
                )
            )
            feedback_by_id = {row.id: row for row in feedback_rows}
            if len(feedback_by_id) != len(feedback_ids):
                raise _not_found("FEEDBACK_NOT_FOUND")
            ordered_feedback = tuple(feedback_by_id[item] for item in feedback_ids)

            baseline_versions = tuple(
                session.scalars(
                    select(ArtifactVersionModel).where(
                        ArtifactVersionModel.id.in_(
                            row.baseline_artifact_version_id for row in ordered_feedback
                        )
                    )
                )
            )
            baseline_by_id = {row.id: row for row in baseline_versions}
            parent_run_ids = {
                baseline_by_id[row.baseline_artifact_version_id].created_by_run_id
                for row in ordered_feedback
            }
            if len(parent_run_ids) != 1:
                raise _conflict(
                    "REVISION_PARENT_RUN_CONFLICT",
                    "All Feedback in one RevisionPlan must share a parent Run",
                )
            parent_run_id = next(iter(parent_run_ids))
            parent = session.get(ResearchRunModel, parent_run_id)
            if parent is None or parent.project_id != project.id:
                raise _not_found("RUN_NOT_FOUND")
            if parent.status != "completed":
                raise _conflict(
                    "REVISION_PARENT_RUN_NOT_COMPLETED",
                    "A RevisionPlan requires a completed parent Run",
                )
            if parent.revision != request.expected_parent_run_revision:
                raise _conflict(
                    "REVISION_PARENT_RUN_CONFLICT",
                    "The parent Run revision changed before the plan was created",
                )

            latest_rows = tuple(
                session.execute(
                    select(ResearchArtifactModel, ArtifactVersionModel)
                    .join(
                        ArtifactVersionModel,
                        ArtifactVersionModel.id
                        == ResearchArtifactModel.latest_version_id,
                    )
                    .where(ResearchArtifactModel.project_id == project.id)
                    .order_by(ResearchArtifactModel.kind, ResearchArtifactModel.id)
                )
            )
            latest_by_artifact = {
                artifact.id: version for artifact, version in latest_rows
            }
            if any(
                latest_by_artifact.get(row.artifact_id) is None
                or latest_by_artifact[row.artifact_id].id
                != row.baseline_artifact_version_id
                for row in ordered_feedback
            ):
                raise _conflict(
                    "REVISION_BASELINE_STALE",
                    "One or more Feedback baselines are no longer current",
                )

            artifact_by_id = {artifact.id: artifact for artifact, _ in latest_rows}
            affected_kinds: set[ArtifactKind] = set()
            for feedback in ordered_feedback:
                kind = ArtifactKind(artifact_by_id[feedback.artifact_id].kind)
                closure = _AFFECTED_KIND_CLOSURE.get(kind)
                if closure is None:
                    raise _conflict(
                        "REVISION_ARTIFACT_UNSUPPORTED",
                        "The Feedback target has no revision impact mapping",
                    )
                affected_kinds.update(closure)
            affected_steps = {"planning"}
            if affected_kinds & _DATA_KINDS:
                affected_steps.update({"fetching_data", "cleaning_data"})
            affected_steps.update(
                _KIND_STEP[kind] for kind in affected_kinds if kind in _KIND_STEP
            )
            recompute_steps = tuple(
                step for step in RUN_STEP_STATUS_ORDER if step in affected_steps
            )

            plan_id = uuid4()
            decisions: list[RevisionPlanVersionModel] = []
            frozen_decisions: list[dict[str, object]] = []
            for position, (artifact, version) in enumerate(latest_rows):
                kind = ArtifactKind(artifact.kind)
                decision = (
                    RevisionDecision.recompute
                    if kind in affected_kinds
                    else RevisionDecision.reuse
                )
                step_key = (
                    _KIND_STEP.get(kind)
                    if decision is RevisionDecision.recompute
                    else None
                )
                decisions.append(
                    RevisionPlanVersionModel(
                        revision_plan_id=plan_id,
                        artifact_version_id=version.id,
                        artifact_id=artifact.id,
                        project_id=project.id,
                        position=position,
                        artifact_kind=kind.value,
                        version_number=version.version_number,
                        decision=decision.value,
                        step_key=step_key,
                    )
                )
                frozen_decisions.append(
                    {
                        "artifact_version_id": str(version.id),
                        "artifact_id": str(artifact.id),
                        "artifact_kind": kind.value,
                        "version_number": version.version_number,
                        "decision": decision.value,
                        "step_key": step_key,
                    }
                )
            plan_payload = {
                "project_id": str(project.id),
                "parent_run_id": str(parent.id),
                "parent_run_revision": parent.revision,
                "contract_id": str(parent.contract_id),
                "feedback_ids": [str(item) for item in feedback_ids],
                "recompute_steps": list(recompute_steps),
                "version_decisions": frozen_decisions,
            }
            plan = RevisionPlanModel(
                id=plan_id,
                project_id=project.id,
                owner_session_id=session_id,
                parent_run_id=parent.id,
                parent_run_revision=parent.revision,
                contract_id=parent.contract_id,
                version=1,
                recompute_steps=list(recompute_steps),
                plan_hash=canonical_request_hash(plan_payload),
                idempotency_key=idempotency_key,
                request_hash=request_hash,
            )
            session.add(plan)
            session.flush((plan,))
            session.add_all(
                [
                    RevisionPlanFeedbackModel(
                        revision_plan_id=plan_id,
                        feedback_id=feedback_id,
                        project_id=project.id,
                        position=position,
                    )
                    for position, feedback_id in enumerate(feedback_ids)
                ]
            )
            session.add_all(decisions)
            session.flush()
            return self._plan_read(session, plan)

    def get_plan(self, *, plan_id: str, session_id: str) -> RevisionPlan:
        plan_uuid = _uuid_or_not_found(plan_id, "REVISION_PLAN_NOT_FOUND")
        with self._factory() as session:
            plan = session.scalar(
                select(RevisionPlanModel)
                .join(
                    ResearchProjectModel,
                    ResearchProjectModel.id == RevisionPlanModel.project_id,
                )
                .where(
                    RevisionPlanModel.id == plan_uuid,
                    ResearchProjectModel.session_id == session_id,
                )
            )
            if plan is None:
                raise _not_found("REVISION_PLAN_NOT_FOUND")
            return self._plan_read(session, plan)

    def confirm_plan(
        self,
        *,
        plan_id: str,
        session_id: str,
        idempotency_key: str,
        request: ConfirmRevisionPlanRequest,
    ) -> UUID:
        plan_uuid = _uuid_or_not_found(plan_id, "REVISION_PLAN_NOT_FOUND")
        request_hash = canonical_request_hash(
            {"plan_id": plan_id, **request.model_dump(mode="json")}
        )
        with self._factory() as session, session.begin():
            plan = session.scalar(
                select(RevisionPlanModel)
                .join(
                    ResearchProjectModel,
                    ResearchProjectModel.id == RevisionPlanModel.project_id,
                )
                .where(
                    RevisionPlanModel.id == plan_uuid,
                    ResearchProjectModel.session_id == session_id,
                )
                .with_for_update()
            )
            if plan is None:
                raise _not_found("REVISION_PLAN_NOT_FOUND")
            confirmation = session.get(RevisionPlanConfirmationModel, plan.id)
            if confirmation is not None:
                if (
                    confirmation.idempotency_key == idempotency_key
                    and confirmation.request_hash == request_hash
                ):
                    return confirmation.run_id
                if confirmation.idempotency_key == idempotency_key:
                    raise _idempotency_conflict()
                raise _conflict(
                    "REVISION_PLAN_ALREADY_CONFIRMED",
                    "The RevisionPlan was already confirmed",
                )
            key_owner = session.scalar(
                select(RevisionPlanConfirmationModel)
                .where(
                    RevisionPlanConfirmationModel.project_id == plan.project_id,
                    RevisionPlanConfirmationModel.idempotency_key == idempotency_key,
                )
                .with_for_update()
            )
            if key_owner is not None:
                raise _idempotency_conflict()
            if plan.version != request.expected_plan_version:
                raise _conflict(
                    "REVISION_PLAN_VERSION_CONFLICT",
                    "The RevisionPlan version changed before confirmation",
                )

            parent = session.get(
                ResearchRunModel, plan.parent_run_id, with_for_update=True
            )
            if (
                parent is None
                or parent.status != "completed"
                or parent.revision != plan.parent_run_revision
            ):
                raise _conflict(
                    "REVISION_PLAN_STALE",
                    "The parent Run changed after the RevisionPlan was created",
                )
            frozen_versions = tuple(
                session.scalars(
                    select(RevisionPlanVersionModel)
                    .where(RevisionPlanVersionModel.revision_plan_id == plan.id)
                    .order_by(RevisionPlanVersionModel.position)
                )
            )
            current_artifacts = tuple(
                session.scalars(
                    select(ResearchArtifactModel)
                    .where(ResearchArtifactModel.project_id == plan.project_id)
                    .order_by(ResearchArtifactModel.id)
                    .with_for_update()
                )
            )
            frozen_by_artifact = {row.artifact_id: row for row in frozen_versions}
            if len(current_artifacts) != len(frozen_by_artifact) or any(
                artifact.id not in frozen_by_artifact
                or artifact.latest_version_id
                != frozen_by_artifact[artifact.id].artifact_version_id
                for artifact in current_artifacts
            ):
                raise _conflict(
                    "REVISION_PLAN_STALE",
                    "An Artifact latest version changed after the RevisionPlan was created",
                )

            steps = compile_revision_run_plan(frozenset(plan.recompute_steps))
            run_id = self._workflow.create_run_in_session(
                session,
                project_id=plan.project_id,
                contract_id=plan.contract_id,
                execution_mode=parent.execution_mode,
                idempotency_key=f"revision-plan:{plan.id}",
                request_hash=plan.plan_hash,
                steps=steps,
                parent_run_id=parent.id,
                derivation_kind="revision",
                queued_message="Revision run queued",
            )
            session.add(
                RevisionPlanConfirmationModel(
                    revision_plan_id=plan.id,
                    project_id=plan.project_id,
                    owner_session_id=session_id,
                    run_id=run_id,
                    idempotency_key=idempotency_key,
                    request_hash=request_hash,
                    confirmed_at=datetime.now(UTC),
                )
            )
            session.flush()
            return run_id

    def _plan_read(self, session: Session, plan: RevisionPlanModel) -> RevisionPlan:
        feedback_links = tuple(
            session.scalars(
                select(RevisionPlanFeedbackModel)
                .where(RevisionPlanFeedbackModel.revision_plan_id == plan.id)
                .order_by(RevisionPlanFeedbackModel.position)
            )
        )
        feedback_rows = tuple(
            session.scalars(
                select(UserFeedbackModel).where(
                    UserFeedbackModel.id.in_(
                        link.feedback_id for link in feedback_links
                    )
                )
            )
        )
        feedback_by_id = {row.id: row for row in feedback_rows}
        version_rows = tuple(
            session.scalars(
                select(RevisionPlanVersionModel)
                .where(RevisionPlanVersionModel.revision_plan_id == plan.id)
                .order_by(RevisionPlanVersionModel.position)
            )
        )
        confirmation = session.get(RevisionPlanConfirmationModel, plan.id)
        conflicts: tuple[RevisionConflict, ...] = ()
        if confirmation is None:
            parent = session.get(ResearchRunModel, plan.parent_run_id)
            found: list[RevisionConflict] = []
            if (
                parent is None
                or parent.status != "completed"
                or parent.revision != plan.parent_run_revision
            ):
                found.append(
                    RevisionConflict(
                        code="REVISION_PARENT_RUN_CHANGED",
                        detail="The parent Run no longer matches the frozen plan",
                    )
                )
            artifacts = tuple(
                session.scalars(
                    select(ResearchArtifactModel).where(
                        ResearchArtifactModel.project_id == plan.project_id
                    )
                )
            )
            frozen = {row.artifact_id: row for row in version_rows}
            for artifact in artifacts:
                row = frozen.get(artifact.id)
                if row is None or row.artifact_version_id != artifact.latest_version_id:
                    found.append(
                        RevisionConflict(
                            code="ARTIFACT_VERSION_CHANGED",
                            artifact_version_id=(
                                str(row.artifact_version_id)
                                if row is not None
                                else None
                            ),
                            detail="An Artifact latest version no longer matches the frozen plan",
                        )
                    )
            conflicts = tuple(found)
        decisions = tuple(
            RevisionVersionDecision(
                artifact_version_id=str(row.artifact_version_id),
                artifact_id=str(row.artifact_id),
                artifact_kind=row.artifact_kind,
                version_number=row.version_number,
                decision=row.decision,
                step_key=row.step_key,
            )
            for row in version_rows
        )
        return RevisionPlan(
            id=str(plan.id),
            project_id=str(plan.project_id),
            parent_run_id=str(plan.parent_run_id),
            parent_run_revision=plan.parent_run_revision,
            contract_id=str(plan.contract_id),
            version=plan.version,
            status=(
                RevisionPlanStatus.confirmed
                if confirmation is not None
                else RevisionPlanStatus.proposed
            ),
            feedback_ids=tuple(str(link.feedback_id) for link in feedback_links),
            baseline_artifact_version_ids=tuple(
                str(feedback_by_id[link.feedback_id].baseline_artifact_version_id)
                for link in feedback_links
            ),
            affected_artifact_version_ids=tuple(
                str(row.artifact_version_id)
                for row in version_rows
                if row.decision == RevisionDecision.recompute.value
            ),
            reusable_artifact_version_ids=tuple(
                str(row.artifact_version_id)
                for row in version_rows
                if row.decision == RevisionDecision.reuse.value
            ),
            recompute_steps=tuple(plan.recompute_steps),
            version_decisions=decisions,
            conflicts=conflicts,
            confirmed_run_id=(str(confirmation.run_id) if confirmation else None),
            plan_hash=plan.plan_hash,
            created_at=_utc(plan.created_at),
        )


def _feedback_read(row: UserFeedbackModel) -> UserFeedback:
    return UserFeedback(
        id=str(row.id),
        project_id=str(row.project_id),
        artifact_id=str(row.artifact_id),
        baseline_artifact_version_id=str(row.baseline_artifact_version_id),
        baseline_version_number=row.baseline_version_number,
        baseline_content_hash=row.baseline_content_hash,
        target_type=row.target_type,
        target_id=row.target_id,
        target_locator=dict(row.target_locator),
        category=row.category,
        summary=row.summary,
        requested_change=row.requested_change,
        feedback_hash=row.feedback_hash,
        created_at=_utc(row.created_at),
    )


def _utc(value: datetime) -> datetime:
    return value.astimezone(UTC)


def _uuid_or_not_found(value: str, code: str) -> UUID:
    try:
        return UUID(value)
    except (TypeError, ValueError) as exc:
        raise _not_found(code) from exc


def _not_found(code: str) -> SecurityProblem:
    return SecurityProblem(
        status=404,
        code=code,
        title="Resource not found",
        detail="The requested resource was not found",
    )


def _conflict(code: str, detail: str) -> SecurityProblem:
    return SecurityProblem(
        status=409, code=code, title="Revision conflict", detail=detail
    )


def _idempotency_conflict() -> SecurityProblem:
    return _conflict(
        "IDEMPOTENCY_CONFLICT",
        "The Idempotency-Key was already used for a different request",
    )


__all__ = ["RevisionApplicationService"]
