"""Deterministic RunStep projection from one confirmed ResearchContract."""

from __future__ import annotations

from collections.abc import Sequence
from hashlib import sha256

from app.schemas.core import (
    ArtifactKind,
    ResearchContractInput,
)
from app.schemas.scientific_capabilities import (
    requires_dataset_prerequisite,
    scientific_skill_phase,
)
from app.workflow.store import RUN_STEP_STATUS_ORDER, RunStepDefinition


class UnsupportedRunPlanError(ValueError):
    """Raised when a requested Artifact has no executable RunStep closure."""

    def __init__(self, outputs: frozenset[ArtifactKind]) -> None:
        self.outputs = outputs
        super().__init__(
            "unsupported Run output requirements: "
            + ", ".join(sorted(item.value for item in outputs))
        )


_STEP_LABELS = {
    "planning": "Planning",
    "fetching_data": "Fetching data",
    "cleaning_data": "Cleaning data",
    "acquiring_observations": "Acquiring astronomical observations",
    "analyzing_data": "Analyzing scientific data",
    "training_models": "Training scientific models",
    "building_visualizations": "Building scientific visualizations",
    "searching_papers": "Searching papers",
    "summarizing_papers": "Summarizing papers",
    "reasoning_literature": "Reasoning over literature",
    "building_graph": "Building graph",
}
_STEP_MAX_ATTEMPTS = {
    "reasoning_literature": 2,
}

_DATA_OUTPUTS = frozenset(
    {
        ArtifactKind.dataset,
        ArtifactKind.field_dictionary,
        ArtifactKind.source_collection,
    }
)
_LITERATURE_OUTPUTS = frozenset(
    {
        ArtifactKind.literature_claims,
        ArtifactKind.literature_relations,
        ArtifactKind.reasoning_traces,
    }
)
_SCIENTIFIC_PHASES = frozenset(
    {
        "acquiring_observations",
        "analyzing_data",
        "training_models",
        "building_visualizations",
    }
)
_SCIENTIFIC_OUTPUT_KINDS = frozenset(
    {
        ArtifactKind.analysis_report,
        ArtifactKind.visualization,
        ArtifactKind.spectrum,
        ArtifactKind.light_curve,
        ArtifactKind.model_evaluation,
        ArtifactKind.model_artifact,
    }
)
SUPPORTED_RUN_OUTPUTS = frozenset(
    {
        ArtifactKind.dataset,
        ArtifactKind.field_dictionary,
        ArtifactKind.source_collection,
        ArtifactKind.analysis_report,
        ArtifactKind.visualization,
        ArtifactKind.spectrum,
        ArtifactKind.light_curve,
        ArtifactKind.model_evaluation,
        ArtifactKind.model_artifact,
        ArtifactKind.paper_collection,
        ArtifactKind.paper_summary,
        ArtifactKind.literature_claims,
        ArtifactKind.literature_relations,
        ArtifactKind.reasoning_traces,
        ArtifactKind.graph,
    }
)

#: Canonical Artifact kind order shared by plan compilation and the runtime.
ARTIFACT_KIND_ORDER = (
    ArtifactKind.dataset,
    ArtifactKind.field_dictionary,
    ArtifactKind.source_collection,
    ArtifactKind.analysis_report,
    ArtifactKind.visualization,
    ArtifactKind.spectrum,
    ArtifactKind.light_curve,
    ArtifactKind.model_evaluation,
    ArtifactKind.model_artifact,
    ArtifactKind.paper_collection,
    ArtifactKind.paper_summary,
    ArtifactKind.literature_claims,
    ArtifactKind.literature_relations,
    ArtifactKind.reasoning_traces,
    ArtifactKind.graph,
)

#: The Artifact kinds each frozen RunStep publishes. The frozen RunStep chain
#: is the sole owner of the Artifact dependency closure: the runtime derives
#: required kinds from the persisted steps and never recomputes them from the
#: contract. Scientific phases list the union of kinds their task-owned steps
#: may produce.
STEP_ARTIFACT_KINDS = {
    "planning": (),
    "fetching_data": (),
    "cleaning_data": (
        ArtifactKind.dataset,
        ArtifactKind.field_dictionary,
        ArtifactKind.source_collection,
    ),
    "acquiring_observations": (
        ArtifactKind.dataset,
        ArtifactKind.spectrum,
        ArtifactKind.light_curve,
        ArtifactKind.analysis_report,
        ArtifactKind.visualization,
    ),
    "analyzing_data": (
        ArtifactKind.analysis_report,
        ArtifactKind.visualization,
        ArtifactKind.spectrum,
        ArtifactKind.light_curve,
    ),
    "training_models": (
        ArtifactKind.model_evaluation,
        ArtifactKind.model_artifact,
    ),
    "building_visualizations": (ArtifactKind.visualization,),
    "searching_papers": (ArtifactKind.paper_collection,),
    "summarizing_papers": (ArtifactKind.paper_summary,),
    "reasoning_literature": (
        ArtifactKind.literature_claims,
        ArtifactKind.literature_relations,
        ArtifactKind.reasoning_traces,
    ),
    "building_graph": (ArtifactKind.graph,),
}


def artifact_kinds_for_steps(
    step_keys: Sequence[str],
) -> tuple[ArtifactKind, ...]:
    """Return the Artifact kinds published by one frozen RunStep chain."""

    required: set[ArtifactKind] = set()
    for key in step_keys:
        if key in STEP_ARTIFACT_KINDS:
            required.update(STEP_ARTIFACT_KINDS[key])
        elif key.startswith("scientific."):
            # Task-owned scientific steps publish within the bounded scientific
            # kind set; the exact kinds stay bounded by the frozen step's skill.
            required.update(_SCIENTIFIC_OUTPUT_KINDS)
        else:
            raise KeyError(f"unknown RunStep key: {key}")
    return tuple(kind for kind in ARTIFACT_KIND_ORDER if kind in required)


def compile_run_plan(
    contract: ResearchContractInput,
) -> tuple[RunStepDefinition, ...]:
    """Freeze the smallest ordered prerequisite closure for requested outputs."""

    outputs = frozenset(contract.output_requirements)
    unsupported = outputs - SUPPORTED_RUN_OUTPUTS
    if unsupported:
        raise UnsupportedRunPlanError(unsupported)

    required = {"planning"}
    if outputs & _DATA_OUTPUTS:
        required.update(("fetching_data", "cleaning_data"))
    # Every scientific task owns its phase and dataset prerequisites through
    # the capability table; a planned task can never be silently dropped from
    # the frozen step chain.
    for task in contract.scientific_tasks:
        required.add(scientific_skill_phase(task.skill_id.value))
        if requires_dataset_prerequisite(task.skill_id.value):
            required.update(("fetching_data", "cleaning_data"))
    if outputs & {ArtifactKind.model_evaluation, ArtifactKind.model_artifact}:
        required.add("training_models")
    if ArtifactKind.paper_collection in outputs:
        required.add("searching_papers")
    if (
        ArtifactKind.paper_summary in outputs
        or outputs & _LITERATURE_OUTPUTS
        or ArtifactKind.graph in outputs
    ):
        required.update(("searching_papers", "summarizing_papers"))
    if outputs & _LITERATURE_OUTPUTS or ArtifactKind.graph in outputs:
        required.add("reasoning_literature")
    if ArtifactKind.graph in outputs:
        required.add("building_graph")

    tasks_by_phase = {
        phase: tuple(
            task
            for task in contract.scientific_tasks
            if scientific_skill_phase(task.skill_id.value) == phase
        )
        for phase in _SCIENTIFIC_PHASES
    }
    planned: list[RunStepDefinition] = []
    for phase in RUN_STEP_STATUS_ORDER:
        if phase not in required:
            continue
        phase_tasks = tasks_by_phase.get(phase, ())
        if phase_tasks:
            planned.extend(
                RunStepDefinition(
                    key=_scientific_task_step_key(task.task_id),
                    label=(
                        f"{task.skill_id.value.replace('_', ' ').title()} · "
                        f"{task.task_id}"
                    ),
                    enter_status=phase,
                    success_status="completed",
                    task_id=task.task_id,
                    skill_id=task.skill_id.value,
                )
                for task in phase_tasks
            )
            continue
        planned.append(
            RunStepDefinition(
                key=phase,
                label=_STEP_LABELS[phase],
                enter_status=phase,
                success_status="completed",
                max_attempts=_STEP_MAX_ATTEMPTS.get(phase, 1),
            )
        )

    return tuple(
        RunStepDefinition(
            key=step.key,
            label=step.label,
            enter_status=step.enter_status,
            success_status=(
                planned[position + 1].enter_status
                if position + 1 < len(planned)
                else "completed"
            ),
            max_attempts=step.max_attempts,
            task_id=step.task_id,
            skill_id=step.skill_id,
            depends_on_step_keys=(planned[position - 1].key,) if position else (),
        )
        for position, step in enumerate(planned)
    )


def compile_revision_run_plan(
    parent_steps: tuple[RunStepDefinition, ...],
    step_keys: frozenset[str],
) -> tuple[RunStepDefinition, ...]:
    """Freeze selected parent steps without losing scientific task identity."""

    parent_by_key = {step.key: step for step in parent_steps}
    if len(parent_by_key) != len(parent_steps):
        raise ValueError("parent Run steps must use unique keys")
    unknown = step_keys - set(parent_by_key)
    if unknown or "planning" not in step_keys:
        raise ValueError("revision Run steps must belong to the parent and include planning")
    ordered = tuple(step for step in parent_steps if step.key in step_keys)
    return tuple(
        RunStepDefinition(
            key=step.key,
            label=step.label,
            enter_status=step.enter_status,
            success_status=(
                ordered[position + 1].enter_status
                if position + 1 < len(ordered)
                else "completed"
            ),
            max_attempts=step.max_attempts,
            task_id=step.task_id,
            skill_id=step.skill_id,
            depends_on_step_keys=tuple(
                dependency
                for dependency in step.depends_on_step_keys
                if dependency in step_keys
            )
            or ((ordered[position - 1].key,) if position else ()),
        )
        for position, step in enumerate(ordered)
    )


def _scientific_task_step_key(task_id: str) -> str:
    digest = sha256(task_id.encode("utf-8")).hexdigest()[:24]
    return f"scientific.{digest}"
