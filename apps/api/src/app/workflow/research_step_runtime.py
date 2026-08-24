"""Thin dispatch facade over the frozen server-owned RunStep plan."""

from __future__ import annotations

from typing import Callable

from sqlalchemy.orm import Session

from app.db.models import RunStepModel
from app.schemas.manifest import ManifestBundle
from app.schemas.scientific_capabilities import capability_for
from app.services.artifacts import ArtifactReadService
from app.services.content_storage import ContentStorage
from app.services.data_artifact_build_inputs import DataArtifactBuildInputRepository
from app.services.document_data_admission import DocumentDataAdmissionService
from app.services.document_parse_store import (
    DocumentParseRepository,
    DocumentParseService,
)
from app.services.model_execution import ModelExecutionPort
from app.services.model_provider_configuration import ModelRuntimeSnapshot
from app.services.paper_candidate_inputs import (
    PaperCandidateInputReadService,
    PaperCandidateInputRepository,
)
from app.services.paper_summaries import PaperSummaryReadService
from app.services.research_input_store import PersistentResearchInputStore
from app.services.scientific_document.ports import DocumentParserPort
from app.workflow.agent_runtime import AgentActivity, ResearchStepAgent, StepTool
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
from app.workflow.steps.scientific_steps import ScientificStepService
from app.workflow.store import AttemptHandle, LeaseGrant, PersistentWorkflowStore
from packages.prompts.registry import PromptRegistry
from services.paper_pipeline.live_collection import LivePaperCollectionRunner
from services.scientific_skills.registry import build_scientific_skill_registry

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
        model_runtime_resolver: Callable[[], ModelRuntimeSnapshot] | None = None,
        prompts: PromptRegistry | None = None,
        paper_collection_runner: LivePaperCollectionRunner | None = None,
        content_storage: ContentStorage | None = None,
        document_parser: DocumentParserPort | None = None,
    ) -> None:
        self._factory = factory
        self._store = store
        self._prompts = prompts or PromptRegistry()
        self._publications = StepPublicationFactory(factory=factory)
        self._model_port = model_port
        self._requested_model = requested_model
        self._explicit_revision = explicit_revision
        self._model_runtime_resolver = model_runtime_resolver
        build_inputs = DataArtifactBuildInputRepository(factory)
        self._scientific_steps = (
            ScientificStepService(
                factory=factory,
                content_storage=content_storage,
                publications=self._publications,
                build_inputs=build_inputs,
            )
            if content_storage is not None
            else None
        )
        self._scientific_skill_registry = (
            build_scientific_skill_registry() if content_storage is not None else None
        )
        paper_inputs = (
            PaperCandidateInputReadService(
                research_inputs=PersistentResearchInputStore(factory),
                repository=PaperCandidateInputRepository(factory),
            )
            if content_storage is not None
            else None
        )
        # One shared DocumentParseService instance: PaperStepService and the
        # document admission service must never hold parallel storage views.
        document_parses = (
            DocumentParseService(DocumentParseRepository(factory), content_storage)
            if content_storage is not None
            else None
        )
        document_admission = (
            DocumentDataAdmissionService(
                factory=factory,
                document_parses=document_parses,
                manifests=manifests,
            )
            if content_storage is not None
            else None
        )
        self._data_steps = DataStepService(
            manifests=manifests,
            publications=self._publications,
            store=store,
            document_admission=document_admission,
            build_inputs=build_inputs,
        )
        self._paper_steps = PaperStepService(
            publications=self._publications,
            collection_runner=paper_collection_runner,
            paper_inputs=paper_inputs,
            content_storage=content_storage,
            document_parser=document_parser,
            document_parses=document_parses,
        )
        summary_reader = PaperSummaryReadService(
            ArtifactReadService(factory),
            document_parses=document_parses,
        )
        self._literature_steps = LiteratureStepService(
            publications=self._publications,
            summary_reader=summary_reader,
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
        scientific_tool = (
            self._scientific_step_tool(attempt.run_step_id)
            if step_key.startswith("scientific.")
            else None
        )

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

        runtime = (
            self._model_runtime_resolver()
            if self._model_runtime_resolver is not None
            else ModelRuntimeSnapshot(
                port=self._model_port,
                provider="qwen",
                requested_model=self._requested_model,
                explicit_revision=self._explicit_revision,
                revision=0,
                source=None,
                preset=None,
                base_url=None,
                api_key_hint=None,
                verified_at=None,
                updated_at=None,
            )
        )
        tracked_model = TrackedStepModelExecutionPort(
            base=runtime.port,
            publications=self._publications,
            context=context,
            step_key=step_key,
            attempt=attempt,
            lease=lease,
            runtime_resolver=self._model_runtime_resolver,
        )
        model_caller = StepModelCaller(
            model_port=tracked_model,
            provider=runtime.provider,
            requested_model=runtime.requested_model,
            explicit_revision=runtime.explicit_revision,
            prompts=self._prompts,
        )
        result = ResearchStepAgent(
            model_port=tracked_model,
            provider=runtime.provider,
            requested_model=runtime.requested_model,
            explicit_revision=runtime.explicit_revision,
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
            tool=scientific_tool,
        )
        return PreparedStep(
            publications=result.value.publications,
            activity_result_summary=result.value.activity_result_summary,
            assistant_narrative=result.assistant_narrative,
            activity_id=result.activity_id,
            activity_name=result.activity_name,
        )

    def _scientific_step_tool(self, run_step_id: object) -> StepTool:
        """Bind the step's single authorized tool to its exact frozen skill."""

        with self._factory() as session:
            step = session.get(RunStepModel, run_step_id)
        if step is None or step.skill_id is None:
            raise ValueError(f"scientific RunStep {run_step_id} has no skill binding")
        skill_id = step.skill_id
        if self._scientific_skill_registry is None:
            raise ValueError(
                "scientific steps require the content-addressed storage runtime"
            )
        skill_revision = self._scientific_skill_registry.revision_for(skill_id)
        capability = capability_for(skill_id)
        return StepTool(
            name=f"execute_science_skill_{skill_id}",
            label=f"执行{capability['label']}",
            tool_kind="scientific_skill",
            description=(
                "执行当前冻结研究步骤唯一授权的科学技能，"
                "技能、参数与输入均由已确认研究协议冻结。"
            ),
            authorized_skill_id=skill_id,
            registry_revision=skill_revision,
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
        if step_key.startswith("scientific."):
            if self._scientific_steps is None:
                raise ValueError(
                    "scientific steps require the content-addressed storage runtime"
                )
            return self._scientific_steps.execute(
                context, step_key=step_key, attempt=attempt, lease=lease
            )
        raise ValueError(f"Unsupported RunStep: {step_key}")
