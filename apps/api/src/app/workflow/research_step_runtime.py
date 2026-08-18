"""Thin dispatch facade over the frozen server-owned RunStep plan."""

from __future__ import annotations

from typing import Callable

from sqlalchemy.orm import Session

from app.schemas.manifest import ManifestBundle
from app.services.model_execution import ModelExecutionPort
from app.workflow.agent_runtime import AgentActivity, ResearchStepAgent
from app.workflow.step_publication import (
    PreparedStep,
    RunStepContext,
    StepModelCaller,
    StepPublicationFactory,
    TrackedStepModelExecutionPort,
    step_uuid,
)
from app.workflow.steps.data_steps import DataStepService
from app.workflow.steps.graph_steps import GraphStepService
from app.workflow.steps.literature_steps import LiteratureStepService
from app.workflow.steps.paper_steps import PaperStepService
from app.workflow.store import AttemptHandle, LeaseGrant, PersistentWorkflowStore
from packages.prompts.registry import PromptRegistry
from services.paper_pipeline.live_collection import LivePaperCollectionRunner

__all__ = ["PreparedStep", "ResearchStepRuntime", "RunStepContext", "step_uuid"]


class ResearchStepRuntime:
    """Dispatch one immutable RunStep and keep attempt-scoped execution facts."""

    def __init__(
        self,
        *,
        factory: Callable[[], Session],
        store: PersistentWorkflowStore,
        manifests: ManifestBundle,
        model_port: ModelExecutionPort,
        requested_model: str,
        explicit_revision: str | None,
        prompts: PromptRegistry | None = None,
        paper_collection_runner: LivePaperCollectionRunner | None = None,
    ) -> None:
        self._store = store
        self._prompts = prompts or PromptRegistry()
        self._publications = StepPublicationFactory(factory=factory)
        self._model_port = model_port
        self._requested_model = requested_model
        self._explicit_revision = explicit_revision
        self._data_steps = DataStepService(
            manifests=manifests, publications=self._publications
        )
        self._paper_steps = PaperStepService(
            publications=self._publications,
            collection_runner=paper_collection_runner,
        )
        self._literature_steps = LiteratureStepService(
            publications=self._publications
        )
        self._graph_steps = GraphStepService(
            factory=factory, publications=self._publications
        )

    def prepare_step(
        self,
        context: RunStepContext,
        step_key: str,
        attempt: AttemptHandle,
        lease: LeaseGrant,
    ) -> PreparedStep:
        def emit(activity: AgentActivity) -> None:
            self._store.append_activity_event(
                context.run_id,
                token=lease.token,
                generation=lease.generation,
                expected_status=attempt.run_status,
                expected_revision=attempt.run_revision,
                activity_id=activity.activity_id,
                activity_kind=activity.activity_kind,
                activity_phase=activity.activity_phase,
                activity_name=activity.activity_name,
                content=activity.content,
                step_key=step_key,
                progress=None,
                details=activity.details,
            )

        tracked_model = TrackedStepModelExecutionPort(
            base=self._model_port,
            publications=self._publications,
            context=context,
            step_key=step_key,
            attempt=attempt,
            lease=lease,
        )
        model_caller = StepModelCaller(
            model_port=tracked_model,
            provider="qwen",
            requested_model=self._requested_model,
            explicit_revision=self._explicit_revision,
            prompts=self._prompts,
        )
        result = ResearchStepAgent(
            model_port=tracked_model,
            provider="qwen",
            requested_model=self._requested_model,
            explicit_revision=self._explicit_revision,
            prompt=self._prompts.get("research_step_agent"),
            emit=emit,
        ).run(
            step_key=step_key,
            attempt_id=str(attempt.attempt_id),
            contract=context.contract.model_dump(mode="json"),
            available_artifacts={
                kind: str(version_id) for kind, version_id in context.versions.items()
            },
            execute_primary=lambda: self._execute_step_tool(
                context, step_key, attempt, lease, model_caller
            ),
            describe_primary_result=lambda prepared: prepared.activity_result_summary,
        )
        return PreparedStep(
            publications=result.value.publications,
            activity_result_summary=result.value.activity_result_summary,
            assistant_narrative=result.assistant_narrative,
            activity_id=result.activity_id,
            activity_name=result.activity_name,
        )

    def _execute_step_tool(
        self,
        context: RunStepContext,
        step_key: str,
        attempt: AttemptHandle,
        lease: LeaseGrant,
        model_caller: StepModelCaller,
    ) -> PreparedStep:
        if step_key == "planning":
            return PreparedStep((), "已按确认协议冻结本次研究执行路径。")
        if step_key == "fetching_data":
            return self._data_steps.fetch(
                context, step_key=step_key, attempt=attempt, lease=lease
            )
        if step_key == "cleaning_data":
            return self._data_steps.clean(
                context, step_key=step_key, attempt=attempt, lease=lease
            )
        if step_key == "searching_papers":
            return self._paper_steps.search(
                context, step_key=step_key, attempt=attempt, lease=lease
            )
        if step_key == "summarizing_papers":
            return self._paper_steps.summarize(
                context,
                step_key=step_key,
                attempt=attempt,
                lease=lease,
                model_caller=model_caller,
            )
        if step_key == "reasoning_literature":
            return self._literature_steps.reason(
                context,
                step_key=step_key,
                attempt=attempt,
                lease=lease,
                model_caller=model_caller,
            )
        if step_key == "building_graph":
            return self._graph_steps.build(
                context, step_key=step_key, attempt=attempt, lease=lease
            )
        raise ValueError(f"Unsupported RunStep: {step_key}")
