"""Execution worker driving background Research Runs through the frozen run plan."""

from __future__ import annotations

import asyncio
from datetime import timezone
import logging
from typing import Any, Callable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    ResearchArtifactModel,
    ResearchContractModel,
    ResearchProjectModel,
    ResearchRunModel,
)
from app.schemas.core import ResearchContract
from app.schemas.manifest import ManifestBundle
from app.schemas.scientific_capabilities import capability_for
from app.services.content_storage import ContentStorage
from app.services.data_revision_context import DataRevisionContextLoader
from app.services.scientific_document.ports import DocumentParserPort
from app.services.model_execution import (
    ModelExecutionError,
    ModelExecutionPort,
)
from app.services.model_provider_configuration import ModelRuntimeSnapshot
from app.workflow.agent_runtime import AgentActivityError
from app.workflow.capacity import PersistentWorkerRegistry
from app.workflow.persistent_executor import (
    FailureDecision,
    PersistentWorkflowExecutionError,
    PersistentWorkflowExecutor,
)
from app.workflow.publisher import (
    ArtifactPublisher,
    ProducerExecutionStore,
    PublicationResult,
)
from app.workflow.research_step_runtime import (
    PreparedStep,
    ResearchStepRuntime,
    RunStepContext,
)
from app.workflow.steps.literature_steps import RelationConfidenceBuilder
from app.workflow.run_plan import artifact_kinds_for_steps
from app.workflow.step_publication import step_uuid
from app.workflow.store import (
    AttemptHandle,
    PersistentWorkflowStore,
    RunSnapshot,
    WorkflowCheckpointRequested,
)
from app.services.research_thread import append_assistant_message
from packages.prompts.registry import PromptRegistry
from services.paper_pipeline.errors import (
    LiteratureAdmissionExecutionError,
    PaperSearchExecutionError,
)
from services.data_pipeline.revision import DataRevisionError, DataRevisionErrorCode
from services.paper_pipeline.live_collection import LivePaperCollectionRunner

LOGGER = logging.getLogger(__name__)

_ARTIFACT_TITLES: dict[str, str] = {
    "dataset": "科学数据集",
    "field_dictionary": "字段数据字典",
    "source_collection": "原始数据源快照集合",
    "paper_collection": "论文检索集合",
    "paper_summary": "论文结构化精读摘要",
    "literature_claims": "论文事实论点",
    "literature_relations": "论文论点关系",
    "graph": "证据与实体图谱",
}

_STEP_STARTED_MESSAGES = {
    "planning": "正在核对已确认研究协议并冻结本次执行路径。",
    "fetching_data": "正在按研究协议从允许的数据来源获取所需材料。",
    "cleaning_data": "正在按研究协议整理、对齐并校验研究数据。",
    "searching_papers": "正在按研究协议限定的主题、年份与来源检索论文。",
    "summarizing_papers": "正在读取已选论文并整理可追溯的研究摘要。",
    "reasoning_literature": "正在提取并核验文献论点、关系与支持证据。",
    "building_graph": "正在把已验证的研究事实组织为证据图谱。",
}


def _step_started_message(*, step_key: str, skill_id: str | None) -> str:
    """Render one public start message from the frozen RunStep identity."""

    if skill_id is not None:
        label = str(capability_for(skill_id)["label"])
        return f"正在执行{label}。"
    return _STEP_STARTED_MESSAGES[step_key]


_RETRYABLE_MODEL_FAILURE_CODES: frozenset[str] = frozenset(
    {
        "MODEL_PROVIDER_TIMEOUT",
        "MODEL_RATE_LIMITED",
        "MODEL_PROVIDER_UNAVAILABLE",
        "MODEL_ACCESS_UNAVAILABLE",
    }
)


class ResearchRunWorker:
    """Poll and execute the frozen RunStep chain through existing authorities."""

    def __init__(
        self,
        *,
        factory: Callable[[], Session],
        store: PersistentWorkflowStore,
        executor: PersistentWorkflowExecutor[Any, PublicationResult],
        manifests: ManifestBundle,
        model_port: ModelExecutionPort,
        requested_model: str,
        explicit_revision: str | None,
        model_runtime_resolver: Callable[[], ModelRuntimeSnapshot] | None = None,
        prompts: PromptRegistry | None = None,
        paper_collection_runner: LivePaperCollectionRunner | None = None,
        content_storage: ContentStorage | None = None,
        document_parser: DocumentParserPort | None = None,
        relation_confidence_builder: RelationConfidenceBuilder | None = None,
    ) -> None:
        self._factory = factory
        self._store = store
        self._executor = executor
        self._manifests = manifests
        self._model_port = model_port
        self._requested_model = requested_model
        self._explicit_revision = explicit_revision
        self._publisher = ArtifactPublisher(factory)
        self._executions = ProducerExecutionStore(factory)
        self._revision_contexts = DataRevisionContextLoader(
            factory,
            manifests=manifests,
        )
        self._prompts = prompts or PromptRegistry()
        self._step_runtime = ResearchStepRuntime(
            factory=factory,
            store=store,
            manifests=manifests,
            model_port=model_port,
            requested_model=requested_model,
            explicit_revision=explicit_revision,
            model_runtime_resolver=model_runtime_resolver,
            prompts=self._prompts,
            paper_collection_runner=paper_collection_runner,
            content_storage=content_storage,
            document_parser=document_parser,
            relation_confidence_builder=relation_confidence_builder,
        )
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self._workers = PersistentWorkerRegistry(factory)
        self._worker_id = "api-research-run-worker"

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._serve(), name="research-run-worker")

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            await self._task
            self._task = None

    async def _serve(self) -> None:
        worker_state = await asyncio.to_thread(
            self._workers.register,
            self._worker_id,
            configured_capacity=1,
        )
        draining = worker_state.state == "draining"
        active_run: asyncio.Task[None] | None = None
        while not self._stop.is_set() or active_run is not None:
            if active_run is not None and active_run.done():
                try:
                    await active_run
                except Exception as error:
                    LOGGER.error(
                        "ResearchRun execution failed",
                        extra={
                            "run_id": active_run.get_name(),
                            "error_class": type(error).__name__,
                        },
                    )
                active_run = None
            try:
                snapshot = await asyncio.to_thread(
                    self._workers.heartbeat, self._worker_id
                )
                draining = snapshot.state == "draining"
            except RuntimeError:
                draining = True
            if active_run is None and not draining and not self._stop.is_set():
                run_ids = await asyncio.to_thread(self._queued_run_ids)
                if run_ids and not self._stop.is_set():
                    run_id = run_ids[0]
                    active_run = asyncio.create_task(
                        self.execute_run(run_id), name=str(run_id)
                    )
            if active_run is not None:
                await asyncio.wait((active_run,), timeout=0.5)
            elif not self._stop.is_set():
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=0.5)
                except TimeoutError:
                    pass
        try:
            await asyncio.to_thread(self._workers.mark_stopped, self._worker_id)
        except RuntimeError:
            LOGGER.warning("worker lifecycle record missing on shutdown")

    def _queued_run_ids(self) -> tuple[UUID, ...]:
        with self._factory() as session:
            return tuple(
                session.scalars(
                    select(ResearchRunModel.id)
                    .where(ResearchRunModel.status == "queued")
                    .order_by(ResearchRunModel.created_at.asc())
                    .limit(4)
                )
            )

    async def execute_run(self, run_id: UUID) -> None:
        snapshot = self._store.load_snapshot(run_id)
        context = (
            None
            if snapshot.derivation_kind == "revision"
            else await asyncio.to_thread(self._load_context, run_id, snapshot)
        )
        lease = self._store.acquire_lease(
            run_id,
            owner=self._worker_id,
            lease_duration=self._executor.lease_duration,
            expected_status=snapshot.status,
            expected_revision=snapshot.revision,
        )
        if context is None:
            try:
                context = await asyncio.to_thread(self._load_context, run_id, snapshot)
            except DataRevisionError as error:
                first_step = snapshot.steps[0]
                attempt = self._store.begin_step(
                    run_id,
                    step_key=first_step.key,
                    attempt_idempotency_key=f"run:{run_id}:revision-preflight",
                    token=lease.token,
                    generation=lease.generation,
                    expected_status=snapshot.status,
                    expected_revision=lease.revision,
                    public_message="正在校验修订计划冻结的执行输入。",
                )
                public_message = (
                    "修订计划冻结的数据版本已变化，请重新生成修订计划。"
                    if error.code is DataRevisionErrorCode.baseline_stale
                    else "修订计划无法按冻结输入执行，请重新生成修订计划。"
                )
                self._store.fail_run(
                    run_id,
                    step_key=first_step.key,
                    attempt_id=attempt.attempt_id,
                    token=lease.token,
                    generation=lease.generation,
                    expected_status=attempt.run_status,
                    expected_revision=attempt.run_revision,
                    error_class=type(error).__name__,
                    error_code=error.code.value,
                    public_message=public_message,
                )
                return
        snapshot = self._store.load_snapshot(run_id)
        await asyncio.to_thread(
            self._append_run_assistant_message,
            context,
            step_key="run_started",
            run_id=run_id,
            message="研究已开始，我会按已确认的研究协议逐步完成数据准备、文献检索与证据整理。",
            milestone_key=f"run:{run_id}:started",
        )
        for planned_step in snapshot.steps:
            while True:
                current_step = next(
                    step for step in snapshot.steps if step.key == planned_step.key
                )
                if current_step.status == "completed":
                    break

                async def runner(
                    attempt: AttemptHandle,
                    *,
                    step_key: str = current_step.key,
                ) -> PreparedStep:
                    try:
                        return await asyncio.to_thread(
                            self._step_runtime.prepare_step,
                            context,
                            step_key,
                            attempt,
                            lease,
                        )
                    except Exception as error:
                        LOGGER.error(
                            "ResearchRun step execution failed",
                            extra={
                                "run_id": str(run_id),
                                "step_key": step_key,
                                "attempt_id": str(attempt.attempt_id),
                                "error_class": type(error).__name__,
                                "error_code": self._classify_failure(error).error_code,
                            },
                        )
                        raise

                async def commit(
                    attempt: AttemptHandle,
                    active_lease: object,
                    prepared: PreparedStep,
                    *,
                    step_key: str = current_step.key,
                ) -> PublicationResult:
                    result = await asyncio.to_thread(
                        self._publisher.publish_step_outputs,
                        run_id,
                        step_key=step_key,
                        attempt_id=attempt.attempt_id,
                        token=lease.token,
                        generation=lease.generation,
                        expected_status=attempt.run_status,
                        expected_revision=attempt.run_revision,
                        publications=prepared.publications,
                        public_message=prepared.activity_result_summary,
                        activity_id=prepared.activity_id,
                        activity_name=prepared.activity_name,
                    )
                    for version in result.versions:
                        kind = next(
                            (
                                name
                                for name, artifact_id in context.artifacts.items()
                                if artifact_id == version.artifact_id
                            ),
                            None,
                        )
                        if kind is not None:
                            context.versions[kind] = version.id
                    await asyncio.to_thread(
                        self._append_run_assistant_message,
                        context,
                        step_key=step_key,
                        run_id=run_id,
                        message=prepared.assistant_narrative
                        or f"“{prepared.activity_name or step_key}”已完成，结果已纳入后续研究。",
                        milestone_key=f"run:{run_id}:step:{step_key}:completed",
                    )
                    return result

                attempt_number = len(current_step.attempts) + 1
                try:
                    result = await self._executor.execute_step(
                        run_id=run_id,
                        step_key=current_step.key,
                        attempt_idempotency_key=(
                            f"run:{run_id}:step:{current_step.key}:attempt:{attempt_number}"
                        ),
                        lease=lease,
                        expected_status=snapshot.status,
                        expected_revision=snapshot.revision,
                        public_message=_step_started_message(
                            step_key=current_step.key,
                            skill_id=current_step.skill_id,
                        ),
                        runner=runner,
                        commit_success=commit,
                        classify_failure=self._classify_failure,
                    )
                except WorkflowCheckpointRequested:
                    return
                except PersistentWorkflowExecutionError:
                    snapshot = self._store.load_snapshot(run_id)
                    failed_step = next(
                        step for step in snapshot.steps if step.key == current_step.key
                    )
                    await asyncio.to_thread(
                        self._append_run_assistant_message,
                        context,
                        step_key=current_step.key,
                        run_id=run_id,
                        message=(
                            failed_step.public_message
                            or "研究步骤遇到问题，当前研究暂时无法继续。"
                        ),
                        milestone_key=(
                            f"run:{run_id}:step:{current_step.key}:failure:"
                            f"{len(failed_step.attempts)}"
                        ),
                    )
                    if failed_step.status == "pending":
                        continue
                    return
                snapshot = self._store.load_snapshot(result.run_id)
                break

    def _append_run_assistant_message(
        self,
        context: RunStepContext,
        *,
        step_key: str,
        run_id: UUID,
        message: str,
        milestone_key: str | None = None,
    ) -> None:
        """Write one idempotent semantic assistant entry through thread."""

        assistant_milestone_key = milestone_key or (
            f"run:{run_id}:step:{step_key}:completed"
        )
        with self._factory() as session, session.begin():
            append_assistant_message(
                session,
                project_id=context.project_id,
                public_content=message,
                structured_payload={
                    "origin": "research_run",
                    "run_id": str(run_id),
                    "step_key": step_key,
                    "assistant_milestone_key": assistant_milestone_key,
                },
                idempotency_key=assistant_milestone_key,
            )

    def _load_context(self, run_id: UUID, snapshot: RunSnapshot) -> RunStepContext:
        with self._factory() as session, session.begin():
            run = session.get(ResearchRunModel, run_id)
            if run is None:
                raise ValueError("ResearchRun not found")
            project = session.get(ResearchProjectModel, run.project_id)
            contract = session.get(ResearchContractModel, run.contract_id)
            if project is None or contract is None:
                raise ValueError("ResearchRun ownership is incomplete")
            contract_created_at = (
                contract.created_at.astimezone(timezone.utc)
                if contract.created_at.tzinfo is not None
                else contract.created_at.replace(tzinfo=timezone.utc)
            )
            contract_value = ResearchContract(
                id=str(contract.id),
                project_id=str(contract.project_id),
                version=contract.version,
                content_hash=contract.content_hash,
                created_from_draft_id=str(contract.created_from_draft_id),
                created_at=contract_created_at,
                **contract.content,
            )
            revision = self._revision_contexts.load(
                run_id=run.id,
                session_id=project.session_id,
            )
            if revision is not None:
                return RunStepContext(
                    run_id=run.id,
                    project_id=run.project_id,
                    session_id=project.session_id,
                    contract=contract_value,
                    artifacts=revision.artifacts,
                    versions=revision.versions,
                    data_revision=revision.data_execution,
                    data_recompute_step_key=revision.data_recompute_step_key,
                    non_data_recompute_step_keys=(
                        revision.non_data_recompute_step_keys
                    ),
                    relation_adjudications=revision.relation_adjudications,
                )
            # Fixed pipeline steps need their stable primary Artifact targets
            # before execution. A Gaia SourceTable is assembled by the
            # scientific step but still publishes through these same primary
            # data targets.
            fixed_steps = tuple(
                step for step in snapshot.steps if step.skill_id is None
            )
            scientific_steps = tuple(
                step for step in snapshot.steps if step.skill_id is not None
            )
            required_kinds = {
                kind.value for kind in artifact_kinds_for_steps(fixed_steps)
            }
            required_kinds.update(
                kind.value
                for kind in artifact_kinds_for_steps(
                    scientific_steps,
                    requested_outputs=frozenset(contract_value.output_requirements),
                )
                if kind.value in {"dataset", "field_dictionary", "source_collection"}
            )

            artifacts: dict[str, UUID] = {}
            versions: dict[str, UUID] = {}
            for value in sorted(required_kinds):
                artifact = session.scalar(
                    select(ResearchArtifactModel).where(
                        ResearchArtifactModel.project_id == run.project_id,
                        ResearchArtifactModel.logical_key == f"{value}.primary",
                    )
                )
                if artifact is None:
                    artifact = ResearchArtifactModel(
                        id=step_uuid(str(run.project_id), f"artifact:{value}"),
                        project_id=run.project_id,
                        kind=value,
                        title=_ARTIFACT_TITLES.get(value, value),
                        logical_key=f"{value}.primary",
                    )
                    session.add(artifact)
                    session.flush()
                artifacts[value] = artifact.id
                if artifact.latest_version_id is not None:
                    versions[value] = artifact.latest_version_id
            return RunStepContext(
                run_id=run.id,
                project_id=run.project_id,
                session_id=project.session_id,
                contract=contract_value,
                artifacts=artifacts,
                versions=versions,
            )

    @staticmethod
    def _classify_failure(error: Exception) -> FailureDecision:
        activity_error = error if isinstance(error, AgentActivityError) else None
        cause = activity_error.cause if activity_error is not None else error
        activity_fields = {
            "activity_id": activity_error.activity_id if activity_error else None,
            "activity_kind": activity_error.activity_kind if activity_error else None,
            "activity_name": activity_error.activity_name if activity_error else None,
        }
        if isinstance(cause, PaperSearchExecutionError):
            return FailureDecision(
                error_code=cause.code,
                public_message=cause.public_message,
                retryable=cause.retryable,
                **activity_fields,
            )
        if isinstance(cause, LiteratureAdmissionExecutionError):
            return FailureDecision(
                error_code=cause.code,
                public_message=cause.public_message,
                retryable=cause.retryable,
                **activity_fields,
            )
        if isinstance(cause, ModelExecutionError):
            return FailureDecision(
                error_code=cause.code,
                public_message=cause.public_message,
                retryable=cause.code in _RETRYABLE_MODEL_FAILURE_CODES,
                upstream_request_id=cause.provider_request_id,
                **activity_fields,
            )
        if isinstance(cause, DataRevisionError):
            return FailureDecision(
                error_code=cause.code.value,
                public_message="修订计划无法按冻结输入执行，请重新生成修订计划。",
                retryable=False,
                **activity_fields,
            )
        return FailureDecision(
            error_code="RUN_EXECUTION_FAILED",
            public_message="研究执行遇到问题，请稍后重试。",
            retryable=False,
            **activity_fields,
        )


__all__ = ["ResearchRunWorker"]
