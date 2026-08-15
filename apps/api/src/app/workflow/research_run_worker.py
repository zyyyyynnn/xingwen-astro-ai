"""Persistent consumer for task-owned scientific ResearchRun steps."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass
from datetime import timedelta
import logging
import os
import socket
from typing import Callable, cast
from uuid import UUID, uuid4

from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.db.models import (
    ResearchContractModel,
    ResearchRunModel,
    RunStepModel,
    WorkflowProjectDispatchModel,
)
from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.core import ResearchContract, ScientificSkillId
from app.services.content_storage import ContentStorage, ContentStorageError
from app.services.image_dataset import ImageDatasetPolicy
from app.services.model_execution import (
    ModelExecutionError,
    ModelExecutionPort,
)
from app.workflow.agent_runtime import (
    AgentDecision,
    AgentSelectionValidationError,
    ResearchStepAgent,
)
from app.workflow.capacity import (
    PersistentWorkerRegistry,
    WorkerSnapshot,
    WorkflowCapacityPolicy,
)
from app.workflow.data_pipeline_publication_runtime import (
    DataPipelinePublicationRuntime,
)
from app.workflow.data_pipeline_runtime import DataPipelineRuntime
from app.workflow.document_pipeline_runtime import DocumentPipelineRuntime
from app.workflow.document_pipeline_runtime import DocumentPipelineInputError
from app.workflow.literature_workflow_runtime import LiteratureWorkflowRuntime
from app.workflow.paper_collection_search_runtime import PaperCollectionSearchRuntime
from app.workflow.persistent_executor import (
    FailureDecision,
    HumanCheckpointRequirement,
    PersistentWorkflowExecutionError,
    PersistentWorkflowExecutor,
)
from app.workflow.publisher import (
    ArtifactPublication,
    ArtifactPublisher,
    ProducerExecutionConflictError,
    ProducerExecutionRequest,
    ProducerExecutionSnapshot,
    ProducerExecutionStore,
    PublicationResult,
)
from app.workflow.scientific_inputs import DatabaseScientificInputResolver
from app.workflow.scientific_provenance import DatabaseScientificSourceRecorder
from app.workflow.scientific_publication import ScientificStepPublisher
from app.workflow.store import (
    AttemptHandle,
    LeaseGrant,
    LeaseUnavailableError,
    PersistentWorkflowStore,
)
from packages.prompts.registry import PromptRegistry
from services.scientific_skills.execution import (
    ScientificStepAdapter,
    ScientificStepOutput,
)
from services.scientific_skills.registry import build_scientific_skill_registry
from services.scientific_skills.process_execution import ScientificSkillProcessExecutor
from services.data_pipeline.manifest import load_frozen_manifest_bundle


LOGGER = logging.getLogger(__name__)
_LEASE_DURATION = timedelta(minutes=30)
_RETRYABLE_MODEL_FAILURES = frozenset(
    {
        "MODEL_PROVIDER_TIMEOUT",
        "MODEL_RATE_LIMITED",
        "MODEL_PROVIDER_UNAVAILABLE",
        "MODEL_RUNTIME_UNAVAILABLE",
    }
)
_TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled"})


@dataclass(frozen=True, slots=True)
class _RunContext:
    run_id: UUID
    project_id: UUID
    contract: ResearchContract


@dataclass(frozen=True, slots=True)
class _PreparedStep:
    decision: AgentDecision
    scientific_output: ScientificStepOutput | None
    publications: tuple[ArtifactPublication, ...] = ()


class ResearchRunWorker:
    """Poll queued Runs and execute their frozen task-owned scientific chain."""

    def __init__(
        self,
        *,
        session_factory: Callable[[], Session],
        store: PersistentWorkflowStore,
        executor: PersistentWorkflowExecutor[_PreparedStep, PublicationResult],
        content_storage: ContentStorage,
        model_port: ModelExecutionPort,
        model_name: str,
        model_revision: str,
        capacity_policy: WorkflowCapacityPolicy | None = None,
        worker_id: str | None = None,
        image_dataset_policy: ImageDatasetPolicy | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._store = store
        self._executor = executor
        self._content_storage = content_storage
        self._image_dataset_policy = image_dataset_policy or ImageDatasetPolicy()
        scientific_registry = build_scientific_skill_registry()
        self._agent = ResearchStepAgent(
            model_port=model_port,
            provider="qwen",
            model=model_name,
            model_revision=model_revision,
            prompt=PromptRegistry().get("research_step_agent"),
        )
        self._scientific_registry = scientific_registry
        self._producer_executions = ProducerExecutionStore(session_factory)
        self._scientific = ScientificStepAdapter(
            executor=ScientificSkillProcessExecutor(scientific_registry),
            content_storage=content_storage,
            source_recorder=DatabaseScientificSourceRecorder(session_factory),
        )
        self._scientific_publisher = ScientificStepPublisher(session_factory)
        self._artifact_publisher = ArtifactPublisher(session_factory)
        self._documents = DocumentPipelineRuntime(
            session_factory=session_factory,
            content_storage=content_storage,
            model_port=model_port,
            model_name=model_name,
            model_revision=model_revision,
        )
        self._paper_search = PaperCollectionSearchRuntime(
            session_factory=session_factory,
        )
        self._data = DataPipelinePublicationRuntime(
            session_factory=session_factory,
            pipeline=DataPipelineRuntime(load_frozen_manifest_bundle()),
        )
        self._literature = LiteratureWorkflowRuntime(
            session_factory=session_factory,
            model_port=model_port,
            model_name=model_name,
            model_revision=model_revision,
        )
        self._capacity_policy = capacity_policy or WorkflowCapacityPolicy(
            max_queued_global=64,
            max_queued_per_project=8,
            max_nonterminal_global=128,
            max_nonterminal_per_project=16,
            max_active_global=4,
            max_active_per_project=2,
            worker_capacity=2,
            queue_timeout=timedelta(minutes=15),
            retry_after_seconds=5,
        )
        self.worker_id = worker_id or (
            f"{socket.gethostname()}:{os.getpid()}:{uuid4().hex[:12]}"
        )
        self._registry = PersistentWorkerRegistry(session_factory)
        self._registered = False
        self._active_runs: dict[asyncio.Task[None], UUID] = {}
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()

    def start(self) -> None:
        if self._task is None:
            self._stop.clear()
            self._registry.register(
                self.worker_id,
                configured_capacity=self._capacity_policy.worker_capacity,
            )
            self._registered = True
            self._task = asyncio.create_task(self._serve(), name="research-run-worker")

    async def stop(self) -> None:
        if self._task is not None:
            await asyncio.to_thread(self._registry.request_drain, self.worker_id)
            self._stop.set()
            await self._task
            self._task = None

    async def _serve(self) -> None:
        try:
            while True:
                state = await asyncio.to_thread(
                    self._registry.heartbeat, self.worker_id
                )
                await asyncio.to_thread(self._store.expire_queued_runs)
                await self._reap_finished_runs()
                if state.state == "draining":
                    if not self._active_runs:
                        break
                    await asyncio.wait(
                        tuple(self._active_runs),
                        timeout=0.5,
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    continue

                available = self._capacity_policy.worker_capacity - len(
                    self._active_runs
                )
                if available > 0:
                    run_ids = await asyncio.to_thread(self._runnable_run_ids, available)
                    for run_id in run_ids:
                        task = asyncio.create_task(
                            self.execute_run(run_id),
                            name=f"research-run:{run_id}",
                        )
                        self._active_runs[task] = run_id
                if self._active_runs:
                    await asyncio.wait(
                        tuple(self._active_runs),
                        timeout=0.5,
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                else:
                    try:
                        await asyncio.wait_for(self._stop.wait(), timeout=0.5)
                    except TimeoutError:
                        pass
        finally:
            if self._active_runs:
                await asyncio.gather(*self._active_runs, return_exceptions=True)
                await self._reap_finished_runs()
            await asyncio.to_thread(self._registry.mark_stopped, self.worker_id)

    async def _reap_finished_runs(self) -> None:
        finished = tuple(task for task in self._active_runs if task.done())
        for task in finished:
            run_id = self._active_runs.pop(task)
            try:
                await task
            except LeaseUnavailableError:
                continue
            except Exception:  # noqa: BLE001 - keep the durable consumer alive
                LOGGER.exception(
                    "ResearchRun execution failed", extra={"run_id": str(run_id)}
                )

    def health_snapshot(self) -> WorkerSnapshot:
        return self._registry.load(self.worker_id)

    def _runnable_run_ids(self, limit: int | None = None) -> tuple[UUID, ...]:
        bounded_limit = min(
            limit or self._capacity_policy.worker_capacity,
            self._capacity_policy.worker_capacity,
        )
        with self._session_factory() as session:
            now = func.clock_timestamp()
            active = aliased(ResearchRunModel)
            active_for_project = (
                select(func.count())
                .select_from(active)
                .where(
                    active.execution_mode == "live",
                    active.project_id == ResearchRunModel.project_id,
                    active.status.not_in(_TERMINAL_STATUSES),
                    active.lease_token.is_not(None),
                    active.lease_expires_at > now,
                )
                .correlate(ResearchRunModel)
                .scalar_subquery()
            )
            ranked = (
                select(
                    ResearchRunModel.id.label("run_id"),
                    ResearchRunModel.project_id.label("project_id"),
                    ResearchRunModel.created_at.label("created_at"),
                    WorkflowProjectDispatchModel.last_dispatched_at.label(
                        "last_dispatched_at"
                    ),
                    func.row_number()
                    .over(
                        partition_by=ResearchRunModel.project_id,
                        order_by=(
                            ResearchRunModel.created_at.asc(),
                            ResearchRunModel.id.asc(),
                        ),
                    )
                    .label("project_rank"),
                )
                .outerjoin(
                    WorkflowProjectDispatchModel,
                    WorkflowProjectDispatchModel.project_id
                    == ResearchRunModel.project_id,
                )
                .where(
                    ResearchRunModel.execution_mode == "live",
                    ResearchRunModel.status.not_in(_TERMINAL_STATUSES),
                    ResearchRunModel.status != "waiting_for_input",
                    or_(
                        ResearchRunModel.status != "queued",
                        ResearchRunModel.queue_expires_at.is_(None),
                        ResearchRunModel.queue_expires_at > now,
                    ),
                    or_(
                        ResearchRunModel.lease_token.is_(None),
                        ResearchRunModel.lease_expires_at <= now,
                    ),
                    active_for_project < self._capacity_policy.max_active_per_project,
                    exists(
                        select(1)
                        .select_from(RunStepModel)
                        .where(
                            RunStepModel.run_id == ResearchRunModel.id,
                            RunStepModel.status.in_(("pending", "running")),
                        )
                    ),
                )
                .cte("ranked_runnable_runs")
            )
            return tuple(
                session.scalars(
                    select(ranked.c.run_id)
                    .where(ranked.c.project_rank == 1)
                    .order_by(
                        ranked.c.last_dispatched_at.asc().nulls_first(),
                        ranked.c.created_at.asc(),
                        ranked.c.project_id.asc(),
                    )
                    .limit(bounded_limit)
                )
            )

    async def execute_run(self, run_id: UUID) -> None:
        if self._registered:
            worker_state = await asyncio.to_thread(self._registry.load, self.worker_id)
            if worker_state.state != "accepting":
                return
        context = await asyncio.to_thread(self._load_context, run_id)
        snapshot = self._store.load_snapshot(run_id)
        if (
            snapshot.status in _TERMINAL_STATUSES
            or snapshot.status == "waiting_for_input"
        ):
            return
        lease = self._store.acquire_lease(
            run_id,
            owner=self.worker_id,
            lease_duration=_LEASE_DURATION,
            expected_status=snapshot.status,
            expected_revision=snapshot.revision,
        )
        snapshot = self._store.load_snapshot(run_id)
        while snapshot.status not in _TERMINAL_STATUSES:
            pending = next(
                (step for step in snapshot.steps if step.status == "pending"), None
            )
            if pending is None:
                raise RuntimeError("non-terminal ResearchRun has no pending RunStep")
            lease = self._store.heartbeat_lease(
                run_id,
                token=lease.token,
                generation=lease.generation,
                lease_duration=_LEASE_DURATION,
                expected_status=snapshot.status,
                expected_revision=snapshot.revision,
            )

            async def runner(attempt: AttemptHandle) -> _PreparedStep:
                return await self._prepare_step(context, pending, attempt, lease)

            async def commit(
                attempt: AttemptHandle,
                active_lease: LeaseGrant,
                prepared: _PreparedStep,
            ) -> PublicationResult:
                if prepared.scientific_output is None:
                    return await asyncio.to_thread(
                        self._artifact_publisher.publish_step_outputs,
                        run_id,
                        step_key=pending.key,
                        attempt_id=attempt.attempt_id,
                        token=active_lease.token,
                        generation=active_lease.generation,
                        expected_status=attempt.run_status,
                        expected_revision=attempt.run_revision,
                        publications=prepared.publications,
                        public_message=prepared.decision.public_analysis,
                    )
                return await asyncio.to_thread(
                    self._scientific_publisher.publish,
                    attempt=attempt,
                    lease=active_lease,
                    step_key=pending.key,
                    contract=context.contract,
                    output=prepared.scientific_output,
                    source_mode="live",
                    public_message=prepared.decision.public_analysis,
                )

            try:
                completed = await self._execute_until_cancelled(
                    run_id,
                    self._executor.execute_step(
                        run_id=run_id,
                        step_key=pending.key,
                        attempt_idempotency_key=(
                            f"run:{run_id}:step:{pending.key}:attempt:"
                            f"{len(pending.attempts) + 1}"
                        ),
                        lease=lease,
                        expected_status=snapshot.status,
                        expected_revision=snapshot.revision,
                        public_message=f"正在执行 {pending.label}",
                        runner=runner,
                        commit_success=commit,
                        classify_failure=self._classify_failure,
                    ),
                )
                if not completed:
                    return
            except PersistentWorkflowExecutionError:
                LOGGER.exception(
                    "ResearchRun step execution failed",
                    extra={"run_id": str(run_id), "step_key": pending.key},
                )
                snapshot = self._store.load_snapshot(run_id)
                failed = next(
                    step for step in snapshot.steps if step.key == pending.key
                )
                if failed.status == "pending":
                    continue
                return
            snapshot = self._store.load_snapshot(run_id)
            if self._registered and snapshot.status not in _TERMINAL_STATUSES:
                worker_state = await asyncio.to_thread(
                    self._registry.load, self.worker_id
                )
                if worker_state.state != "accepting":
                    await asyncio.to_thread(
                        self._store.release_lease,
                        run_id,
                        token=lease.token,
                        generation=lease.generation,
                    )
                    return

    async def _execute_until_cancelled(
        self,
        run_id: UUID,
        operation: object,
    ) -> bool:
        task = asyncio.ensure_future(operation)  # type: ignore[arg-type]
        try:
            while not task.done():
                await asyncio.wait((task,), timeout=0.25)
                if task.done():
                    break
                cancelled = await asyncio.to_thread(
                    lambda: self._store.load_snapshot(run_id).status == "cancelled"
                )
                if cancelled:
                    task.cancel()
                    with suppress(asyncio.CancelledError):
                        await task
                    return False
            await task
            return True
        except asyncio.CancelledError:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
            raise

    async def _prepare_step(
        self,
        context: _RunContext,
        step: object,
        attempt: AttemptHandle,
        lease: LeaseGrant,
    ) -> _PreparedStep:
        step_key = str(getattr(step, "key"))
        task_id = getattr(step, "task_id")
        raw_skill_id = getattr(step, "skill_id")
        skill_id = ScientificSkillId(raw_skill_id) if raw_skill_id is not None else None
        decision = await self._select_step(
            context=context,
            step_key=step_key,
            task_id=task_id,
            skill_id=skill_id,
            attempt=attempt,
            lease=lease,
        )
        if skill_id is None:
            if step_key == "planning":
                return _PreparedStep(decision=decision, scientific_output=None)
            if step_key == "fetching_data":
                return _PreparedStep(decision=decision, scientific_output=None)
            if step_key == "cleaning_data":
                publications = await asyncio.to_thread(
                    self._data.prepare_publications,
                    contract=context.contract,
                    step_key=step_key,
                    attempt=attempt,
                    lease=lease,
                )
                return _PreparedStep(
                    decision=decision,
                    scientific_output=None,
                    publications=publications,
                )
            if step_key == "searching_papers":
                # Contract-scoped Paper Search is independent of uploads;
                # Document binding remains authoritative for summarizing_papers.
                publication = await asyncio.to_thread(
                    self._paper_search.prepare_publication,
                    project_id=context.project_id,
                    contract=context.contract,
                    attempt=attempt,
                    lease=lease,
                )
                return _PreparedStep(
                    decision=decision,
                    scientific_output=None,
                    publications=(publication,),
                )
            if step_key == "summarizing_papers":
                publications = await self._documents.prepare_publications(
                    run_id=context.run_id,
                    project_id=context.project_id,
                    research_goal=context.contract.research_goal,
                    step_key=step_key,
                    attempt=attempt,
                    lease=lease,
                )
                return _PreparedStep(
                    decision=decision,
                    scientific_output=None,
                    publications=publications,
                )
            if step_key == "reasoning_literature":
                publications = await self._literature.prepare_reasoning_publications(
                    project_id=context.project_id,
                    run_id=context.run_id,
                    contract=context.contract,
                    attempt=attempt,
                    lease=lease,
                )
                return _PreparedStep(
                    decision=decision,
                    scientific_output=None,
                    publications=publications,
                )
            if step_key == "building_graph":
                publication = await self._literature.prepare_graph_publication(
                    project_id=context.project_id,
                    run_id=context.run_id,
                    attempt=attempt,
                    lease=lease,
                )
                return _PreparedStep(
                    decision=decision,
                    scientific_output=None,
                    publications=(publication,),
                )
            raise ValueError(f"fixed pipeline RunStep is not connected yet: {step_key}")
        resolver = DatabaseScientificInputResolver(
            self._session_factory,
            self._content_storage,
            project_id=str(context.project_id),
            image_dataset_policy=self._image_dataset_policy,
        )
        output = await self._scientific.execute(
            task_id=str(task_id),
            project_id=str(context.project_id),
            run_id=str(context.run_id),
            contract=context.contract,
            resolve_inputs=resolver.resolve,
        )
        return _PreparedStep(decision=decision, scientific_output=output)

    async def _select_step(
        self,
        *,
        context: _RunContext,
        step_key: str,
        task_id: str | None,
        skill_id: ScientificSkillId | None,
        attempt: AttemptHandle,
        lease: LeaseGrant,
    ) -> AgentDecision:
        skill_revision = (
            self._scientific_registry.revision_for(skill_id)
            if skill_id is not None
            else None
        )
        prepared = self._agent.prepare_selection(
            step_key=step_key,
            task_id=task_id,
            skill_id=skill_id,
            contract=context.contract.model_dump(mode="json"),
            skill_revision=skill_revision,
        )
        request = prepared.model_request
        execution = await asyncio.to_thread(
            self._producer_executions.start_producer_execution,
            ProducerExecutionRequest(
                run_id=context.run_id,
                step_key=step_key,
                attempt_id=attempt.attempt_id,
                idempotency_key=(f"research-step-agent:{attempt.attempt_number}"),
                producer_type="model",
                producer_name="research_step_agent",
                producer_version="1.0.0",
                input_hash=request.input_hash,
                parameters=request.parameters,
                model_provider=request.provider,
                model_name=request.model_revision,
                prompt_name=request.prompt_name,
                prompt_version=request.prompt_version,
                prompt_hash=request.prompt_hash,
                authorized_tool_name=prepared.authorized_tool_name,
                authorized_skill_id=prepared.authorized_skill_id,
                registry_revision=prepared.registry_revision,
            ),
            token=lease.token,
            generation=lease.generation,
            expected_status=attempt.run_status,
            expected_revision=attempt.run_revision,
        )
        if execution.replayed:
            return _replayed_agent_decision(execution)
        try:
            decision = await asyncio.to_thread(self._agent.execute_selection, prepared)
        except ModelExecutionError as exc:
            await asyncio.to_thread(
                self._producer_executions.finish_producer_execution,
                execution.id,
                status="failed",
                output_hash=exc.output_hash,
                token_usage=exc.token_usage,
                latency_ms=exc.latency_ms,
                error_code=exc.code,
                provider_request_id=exc.provider_request_id,
                error_hash=_agent_error_hash(exc.code, exc.output_hash),
            )
            raise
        except AgentSelectionValidationError as exc:
            response = exc.response
            await asyncio.to_thread(
                self._producer_executions.finish_producer_execution,
                execution.id,
                status="rejected",
                output_hash=response.output_hash,
                token_usage=response.token_usage,
                latency_ms=response.latency_ms,
                error_code=exc.code,
                provider_request_id=response.provider_request_id,
                tool_call_id=exc.tool_call_id,
                rejected_arguments_hash=exc.rejected_arguments_hash,
                error_hash=_agent_error_hash(exc.code, response.output_hash),
            )
            raise
        await asyncio.to_thread(
            self._producer_executions.finish_producer_execution,
            execution.id,
            status="completed",
            output_hash=decision.output_hash,
            token_usage=decision.token_usage,
            latency_ms=decision.latency_ms,
            provider_request_id=decision.provider_request_id,
            tool_call_id=decision.tool_call_id,
            validated_arguments_hash=decision.validated_arguments_hash,
            public_message=decision.public_analysis,
        )
        return decision

    def _load_context(self, run_id: UUID) -> _RunContext:
        with self._session_factory() as session:
            run = session.get(ResearchRunModel, run_id)
            if run is None:
                raise ValueError("ResearchRun not found")
            contract = session.get(ResearchContractModel, run.contract_id)
            if contract is None or contract.project_id != run.project_id:
                raise ValueError("ResearchRun contract ownership is incomplete")
            content = ResearchContract.model_validate(
                {
                    **contract.content,
                    "id": str(contract.id),
                    "project_id": str(contract.project_id),
                    "version": contract.version,
                    "created_from_draft_id": str(contract.created_from_draft_id),
                    "created_at": contract.created_at,
                    "content_hash": contract.content_hash,
                }
            )
            return _RunContext(
                run_id=run.id,
                project_id=run.project_id,
                contract=content,
            )

    @staticmethod
    def _classify_failure(error: Exception) -> FailureDecision:
        if isinstance(error, DocumentPipelineInputError):
            requirement = HumanCheckpointRequirement(
                error_code="DOCUMENT_INPUT_REQUIRED",
                public_message="请补充 PDF、Markdown 或纯文本文档后继续研究。",
                required_input_types=("pdf", "text"),
            )
            return FailureDecision(
                error_code=requirement.error_code,
                public_message=requirement.public_message,
                retryable=False,
                checkpoint=requirement,
            )
        if isinstance(error, AgentSelectionValidationError):
            return FailureDecision(
                error_code=error.code,
                public_message=error.public_message,
                retryable=False,
                upstream_request_id=error.response.provider_request_id,
            )
        if isinstance(error, ModelExecutionError):
            return FailureDecision(
                error_code=error.code,
                public_message=error.public_message,
                retryable=error.code in _RETRYABLE_MODEL_FAILURES,
                upstream_request_id=error.provider_request_id,
            )
        if isinstance(error, TimeoutError):
            return FailureDecision(
                error_code="SCIENTIFIC_SKILL_TIMEOUT",
                public_message="科学计算超时，请稍后重试。",
                retryable=True,
            )
        if isinstance(error, ContentStorageError):
            return FailureDecision(
                error_code="CONTENT_STORAGE_UNAVAILABLE",
                public_message="研究内容存储暂时不可用，请稍后重试。",
                retryable=True,
            )
        return FailureDecision(
            error_code="RUN_EXECUTION_FAILED",
            public_message="研究执行遇到问题，请检查输入与研究协议后重试。",
            retryable=False,
        )


def _agent_error_hash(error_code: str, result_hash: str | None) -> str:
    return compute_canonical_payload_hash(
        {"error_code": error_code, "result_hash": result_hash}
    )


def _replayed_agent_decision(
    execution: ProducerExecutionSnapshot,
) -> AgentDecision:
    required = (
        execution.output_hash,
        execution.tool_call_id,
        execution.validated_arguments_hash,
        execution.public_message,
        execution.authorized_tool_name,
        execution.registry_revision,
        execution.latency_ms,
    )
    if execution.status != "completed" or any(value is None for value in required):
        raise ProducerExecutionConflictError(
            "Function Calling execution cannot replay an incomplete audit record"
        )
    return AgentDecision(
        public_analysis=cast(str, execution.public_message),
        tool_call_id=cast(str, execution.tool_call_id),
        provider_request_id=execution.provider_request_id,
        output_hash=cast(str, execution.output_hash),
        validated_arguments_hash=cast(str, execution.validated_arguments_hash),
        token_usage=(
            dict(execution.token_usage) if execution.token_usage is not None else None
        ),
        latency_ms=cast(int, execution.latency_ms),
        authorized_tool_name=cast(str, execution.authorized_tool_name),
        authorized_skill_id=execution.authorized_skill_id,
        registry_revision=cast(str, execution.registry_revision),
    )


__all__ = ["ResearchRunWorker"]
