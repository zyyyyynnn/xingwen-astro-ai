"""PostgreSQL application service for Feedback and revision Run orchestration."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    ArtifactVersionModel,
    ProducerExecutionModel,
    ResearchArtifactModel,
    ResearchContractModel,
    ResearchProjectModel,
    ResearchRunModel,
    RevisionPlanConfirmationModel,
    RevisionPlanFeedbackModel,
    RevisionPlanModel,
    RevisionPlanVersionModel,
    RunStepModel,
    UserFeedbackModel,
)
from app.schemas.core import ResearchThreadEntryKind
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
from app.services.artifacts import ArtifactReadService
from app.services.feedback_targets import FeedbackTargetAuthority
from app.services.research_thread import append_thread_entry
from app.services.revision_plan_hash import compute_revision_plan_hash
from app.workflow.run_plan import compile_revision_run_plan
from app.workflow.store import PersistentWorkflowStore, RunStepDefinition


class RevisionApplicationService:
    """Owner-scoped immutable Feedback, Plan and confirmation use cases."""

    def __init__(
        self,
        *,
        factory: Callable[[], Session],
        workflow_store: PersistentWorkflowStore,
        target_authority: FeedbackTargetAuthority | None = None,
    ) -> None:
        self._factory = factory
        self._workflow = workflow_store
        self._targets = target_authority or FeedbackTargetAuthority(
            ArtifactReadService(factory)
        )

    async def create_feedback(
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
            await self._targets.validate(
                version_id=str(version.id),
                artifact_id=str(artifact.id),
                artifact_kind=artifact.kind,
                session_id=session_id,
                request=request,
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
            append_thread_entry(
                session,
                project_id=project.id,
                kind=ResearchThreadEntryKind.assistant_message,
                actor="assistant",
                public_content="已记录这项正式修改要求。接下来会基于当前结果生成可确认的修订计划。",
                structured_payload={"revision_stage": "feedback_recorded"},
                idempotency_key=f"revision-feedback:{row.id}",
            )
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
            contract = session.get(ResearchContractModel, parent.contract_id)
            if contract is None or contract.project_id != project.id:
                raise _not_found("CONTRACT_NOT_FOUND")
            parent_steps = tuple(
                session.scalars(
                    select(RunStepModel)
                    .where(RunStepModel.run_id == parent.id)
                    .order_by(RunStepModel.position)
                )
            )
            if not parent_steps or parent_steps[0].key != "planning":
                raise _conflict(
                    "REVISION_PARENT_STEPS_INVALID",
                    "The parent Run has no valid frozen step plan",
                )
            parent_step_by_id = {step.id: step for step in parent_steps}
            parent_step_by_key = {step.key: step for step in parent_steps}
            if len(parent_step_by_key) != len(parent_steps):
                raise _conflict(
                    "REVISION_PARENT_STEPS_INVALID",
                    "The parent Run step keys are not unique",
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

            parent_versions = tuple(
                version
                for _, version in latest_rows
                if version.created_by_run_id == parent.id
            )
            producer_ids = {
                version.producer_execution_id for version in parent_versions
            }
            producers = tuple(
                session.scalars(
                    select(ProducerExecutionModel).where(
                        ProducerExecutionModel.id.in_(producer_ids)
                    )
                )
            )
            producer_by_id = {producer.id: producer for producer in producers}

            def producer_step_key(version: ArtifactVersionModel) -> str:
                producer = producer_by_id.get(version.producer_execution_id)
                step = parent_step_by_id.get(version.run_step_id)
                if (
                    producer is None
                    or step is None
                    or producer.run_id != parent.id
                    or producer.run_step_id != step.id
                    or producer.step_key != step.key
                    or version.step_attempt_id != producer.step_attempt_id
                ):
                    raise _conflict(
                        "REVISION_PRODUCER_INVALID",
                        "An ArtifactVersion producer does not match the parent RunStep",
                    )
                return step.key

            baseline_step_keys = {
                producer_step_key(baseline_by_id[feedback.baseline_artifact_version_id])
                for feedback in ordered_feedback
            }
            affected_step_keys = set(baseline_step_keys)
            artifact_kind_by_id = {
                artifact.id: artifact.kind for artifact, _version in latest_rows
            }
            source_reacquisition_feedback = tuple(
                feedback
                for feedback in ordered_feedback
                if artifact_kind_by_id.get(feedback.artifact_id)
                == "source_collection"
                and feedback.target_type in {"artifact", "artifact_version"}
                and feedback.category in {"correction", "evidence"}
            )
            if source_reacquisition_feedback and "fetching_data" in parent_step_by_key:
                affected_step_keys.add("fetching_data")
            data_kinds = {"dataset", "field_dictionary", "source_collection"}
            data_version_ids = {
                version.id
                for artifact, version in latest_rows
                if artifact.kind in data_kinds
            }
            direct_data_feedback = tuple(
                feedback
                for feedback in ordered_feedback
                if feedback.baseline_artifact_version_id in data_version_ids
            )
            if direct_data_feedback:
                current_data_rows = tuple(
                    (artifact, version)
                    for artifact, version in latest_rows
                    if artifact.kind in data_kinds
                )
                data_kind_counts = {
                    kind: sum(
                        artifact.kind == kind
                        for artifact, _version in current_data_rows
                    )
                    for kind in data_kinds
                }
                coherent = (
                    data_kind_counts == {kind: 1 for kind in data_kinds}
                    and all(
                        version.created_by_run_id == parent.id
                        for _artifact, version in current_data_rows
                    )
                    and len(
                        {version.input_hash for _artifact, version in current_data_rows}
                    )
                    == 1
                )
                if coherent:
                    data_step_keys: set[str] = set()
                    for _artifact, version in current_data_rows:
                        producer = producer_by_id.get(version.producer_execution_id)
                        step = parent_step_by_id.get(version.run_step_id)
                        if (
                            producer is None
                            or step is None
                            or producer.run_id != parent.id
                            or producer.run_step_id != step.id
                            or producer.step_key != step.key
                            or version.step_attempt_id != producer.step_attempt_id
                        ):
                            coherent = False
                            break
                        data_step_keys.add(step.key)
                    coherent = coherent and len(data_step_keys) == 1
                if not coherent:
                    raise _conflict(
                        "REVISION_DATA_BUNDLE_CONFLICT",
                        "Current data ArtifactVersions do not form one revisable parent bundle",
                    )
            source_feedback_ids = {
                feedback.id for feedback in source_reacquisition_feedback
            }
            candidate_data_only_scientific_steps = {
                producer_step_key(
                    baseline_by_id[feedback.baseline_artifact_version_id]
                )
                for feedback in direct_data_feedback
                if feedback.id not in source_feedback_ids
                and (
                    step := parent_step_by_key[
                        producer_step_key(
                            baseline_by_id[feedback.baseline_artifact_version_id]
                        )
                    ]
                ).skill_id
                == "gaia_cone_search"
            }
            direct_non_data_step_keys = {
                producer_step_key(
                    baseline_by_id[feedback.baseline_artifact_version_id]
                )
                for feedback in ordered_feedback
                if artifact_kind_by_id.get(feedback.artifact_id) not in data_kinds
            }
            source_reacquisition_step_keys = {
                producer_step_key(
                    baseline_by_id[feedback.baseline_artifact_version_id]
                )
                for feedback in source_reacquisition_feedback
            }
            data_only_scientific_steps = (
                candidate_data_only_scientific_steps
                - direct_non_data_step_keys
                - source_reacquisition_step_keys
            )
            changed = True
            while changed:
                changed = False
                for step in parent_steps:
                    if step.key in affected_step_keys:
                        continue
                    propagating_steps = (
                        affected_step_keys - data_only_scientific_steps
                    )
                    if set(step.depends_on_step_keys) & propagating_steps:
                        affected_step_keys.add(step.key)
                        changed = True
            affected_step_keys.add("planning")
            plan_id = uuid4()
            decisions: list[RevisionPlanVersionModel] = []
            frozen_decisions: list[dict[str, object]] = []
            for position, (artifact, version) in enumerate(latest_rows):
                producer_key = (
                    producer_step_key(version)
                    if version.created_by_run_id == parent.id
                    else None
                )
                complete_data_bundle_recompute = (
                    bool(direct_data_feedback) and artifact.kind in data_kinds
                )
                data_only_scientific_co_output = (
                    producer_key in data_only_scientific_steps
                    and artifact.kind not in data_kinds
                )
                decision = (
                    RevisionDecision.recompute
                    if (
                        complete_data_bundle_recompute
                        or (
                            producer_key in affected_step_keys
                            and not data_only_scientific_co_output
                        )
                    )
                    else RevisionDecision.reuse
                )
                step_key = (
                    producer_key
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
                        artifact_kind=artifact.kind,
                        version_number=version.version_number,
                        decision=decision.value,
                        step_key=step_key,
                    )
                )
                frozen_decisions.append(
                    {
                        "artifact_version_id": str(version.id),
                        "artifact_id": str(artifact.id),
                        "artifact_kind": artifact.kind,
                        "version_number": version.version_number,
                        "decision": decision.value,
                        "step_key": step_key,
                    }
                )
            recompute_version_ids = {
                item.artifact_version_id
                for item in decisions
                if item.decision == RevisionDecision.recompute.value
            }
            if any(
                row.baseline_artifact_version_id not in recompute_version_ids
                for row in ordered_feedback
            ):
                raise _conflict(
                    "REVISION_BASELINE_OUTSIDE_CONTRACT",
                    "A Feedback baseline is outside the parent Contract output closure",
                )
            recompute_steps = tuple(
                step.key for step in parent_steps if step.key in affected_step_keys
            )
            if len(recompute_steps) < 2:
                raise _conflict(
                    "REVISION_BASELINE_OUTSIDE_CONTRACT",
                    "A Feedback baseline has no recomputable parent RunStep",
                )
            recompute_decision_step_keys = {
                item.step_key
                for item in decisions
                if item.decision == RevisionDecision.recompute.value
            }
            prerequisite_step_keys = {"planning"}
            if source_reacquisition_feedback and "fetching_data" in parent_step_by_key:
                prerequisite_step_keys.add("fetching_data")
            if (
                set(recompute_steps) - prerequisite_step_keys
                != recompute_decision_step_keys
            ):
                raise _conflict(
                    "REVISION_AFFECTED_OUTPUT_CONFLICT",
                    "The recomputed steps do not close over the frozen recompute decisions",
                )
            plan = RevisionPlanModel(
                id=plan_id,
                project_id=project.id,
                owner_session_id=session_id,
                parent_run_id=parent.id,
                parent_run_revision=parent.revision,
                contract_id=parent.contract_id,
                version=1,
                recompute_steps=list(recompute_steps),
                plan_hash=compute_revision_plan_hash(
                    project_id=project.id,
                    parent_run_id=parent.id,
                    parent_run_revision=parent.revision,
                    contract_id=parent.contract_id,
                    feedback_ids=feedback_ids,
                    recompute_steps=recompute_steps,
                    version_decisions=frozen_decisions,
                ),
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
            append_thread_entry(
                session,
                project_id=project.id,
                kind=ResearchThreadEntryKind.assistant_message,
                actor="assistant",
                public_content=(
                    f"修订计划已生成：将重新执行 {len(recompute_steps)} 个研究步骤。"
                    "确认后会创建派生研究，当前结果保持不变。"
                ),
                structured_payload={"revision_stage": "plan_proposed"},
                idempotency_key=f"revision-plan:{plan.id}:proposed",
            )
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

            parent_steps = tuple(
                RunStepDefinition(
                    key=step.key,
                    label=step.label,
                    enter_status=step.enter_status,
                    success_status=step.success_status,
                    max_attempts=step.max_attempts,
                    task_id=step.task_id,
                    skill_id=step.skill_id,
                    depends_on_step_keys=tuple(step.depends_on_step_keys),
                )
                for step in session.scalars(
                    select(RunStepModel)
                    .where(RunStepModel.run_id == parent.id)
                    .order_by(RunStepModel.position)
                )
            )
            steps = compile_revision_run_plan(
                parent_steps, frozenset(plan.recompute_steps)
            )
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
            append_thread_entry(
                session,
                project_id=plan.project_id,
                kind=ResearchThreadEntryKind.assistant_message,
                actor="assistant",
                public_content="修订计划已确认，派生研究已创建。原研究与已发布结果会继续保留。",
                structured_payload={"revision_stage": "derived_run_created"},
                idempotency_key=f"revision-plan:{plan.id}:confirmed",
            )
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
