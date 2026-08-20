"""Task-owned scientific RunStep execution within the current Workflow."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from sqlalchemy.orm import Session

from app.db.models import RunStepModel
from app.schemas.scientific_capabilities import capability_for
from app.services.content_storage import ContentStorage
from app.workflow.scientific_admission import ScientificStepAdmission
from app.workflow.scientific_inputs import DatabaseScientificInputResolver
from app.workflow.scientific_provenance import (
    DatabaseGaiaTapResponseCache,
    DatabaseScientificSourceRecorder,
)
from app.workflow.step_publication import PreparedStep, RunStepContext
from app.workflow.store import AttemptHandle, LeaseGrant
from services.scientific_skills.execution import ScientificStepAdapter
from services.scientific_skills.astro_acquisition import GaiaTapAdapter
from services.scientific_skills.registry import (
    ScientificSkillRegistry,
    build_scientific_skill_registry,
)


class ScientificStepService:
    """Execute one task-owned scientific step through the bounded skill seam."""

    def __init__(
        self,
        *,
        factory: Callable[[], Session],
        content_storage: ContentStorage,
        registry: ScientificSkillRegistry | None = None,
    ) -> None:
        self._factory = factory
        self._content_storage = content_storage
        self._registry = registry or build_scientific_skill_registry(
            gaia_handler=GaiaTapAdapter(
                cache=DatabaseGaiaTapResponseCache(factory)
            ).acquire
        )
        self._admission = ScientificStepAdmission(factory)

    def execute(
        self,
        context: RunStepContext,
        *,
        step_key: str,
        attempt: AttemptHandle,
        lease: LeaseGrant,
    ) -> PreparedStep:
        task_id, skill_id = self._step_binding(attempt.run_step_id)
        resolver = DatabaseScientificInputResolver(
            self._factory,
            self._content_storage,
            project_id=str(context.project_id),
        )
        recorder = DatabaseScientificSourceRecorder(self._factory)
        adapter = ScientificStepAdapter(
            registry=self._registry,
            content_storage=self._content_storage,
            source_recorder=recorder,
        )
        output = asyncio.run(
            adapter.execute(
                task_id=task_id,
                project_id=str(context.project_id),
                run_id=str(context.run_id),
                contract=context.contract,
                resolve_inputs=resolver.resolve,
            )
        )
        publications = self._admission.prepare_publications(
            attempt=attempt,
            lease=lease,
            step_key=step_key,
            contract=context.contract,
            output=output,
            source_mode=output.source_mode,
        )
        capability = capability_for(skill_id)
        summary = f"{capability['label']}已完成，产出 {len(publications)} 个结果版本"
        return PreparedStep(
            publications=publications,
            activity_result_summary=summary,
        )

    def _step_binding(self, run_step_id: object) -> tuple[str, str]:
        with self._factory() as session:
            step = session.get(RunStepModel, run_step_id)
        if step is None or step.task_id is None or step.skill_id is None:
            raise ValueError("scientific RunStep is missing its task binding")
        return step.task_id, step.skill_id
