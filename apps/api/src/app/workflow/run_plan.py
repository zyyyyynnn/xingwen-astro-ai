"""Deterministic RunStep projection from one confirmed ResearchContract."""

from __future__ import annotations

from collections.abc import Sequence
from hashlib import sha256

from app.schemas.core import (
    ArtifactKind,
    ResearchContractInput,
    ScientificSkillId,
)
from app.workflow.store import RUN_STEP_STATUS_ORDER, RunStepDefinition
from services.scientific_skills.planning import scientific_skill_phase


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
_DATA_ANALYSIS_SKILLS = frozenset(
    {
        ScientificSkillId.catalog_crossmatch,
        ScientificSkillId.data_profile,
        ScientificSkillId.statistical_analysis,
        ScientificSkillId.correlation_analysis,
        ScientificSkillId.spectrum_analysis,
        ScientificSkillId.light_curve_analysis,
        ScientificSkillId.tabular_machine_learning,
        ScientificSkillId.time_series_classification,
        ScientificSkillId.time_series_forecast,
        ScientificSkillId.image_classification,
        ScientificSkillId.model_inference,
    }
)
_OBSERVATION_SKILLS = frozenset(
    {
        ScientificSkillId.simbad_lookup,
        ScientificSkillId.skyview_fits,
        ScientificSkillId.ephemeris,
        ScientificSkillId.celestial_events,
        ScientificSkillId.gaia_cone_search,
        ScientificSkillId.vizier_tap,
        ScientificSkillId.spectrum_acquisition,
        ScientificSkillId.light_curve_acquisition,
    }
)
_ANALYSIS_SKILLS = frozenset(
    {
        ScientificSkillId.catalog_crossmatch,
        ScientificSkillId.data_profile,
        ScientificSkillId.statistical_analysis,
        ScientificSkillId.correlation_analysis,
        ScientificSkillId.fits_image_analysis,
        ScientificSkillId.spectrum_analysis,
        ScientificSkillId.light_curve_analysis,
        ScientificSkillId.vizier_tap,
        ScientificSkillId.model_inference,
    }
)
_MODEL_SKILLS = frozenset(
    {
        ScientificSkillId.tabular_machine_learning,
        ScientificSkillId.time_series_classification,
        ScientificSkillId.time_series_forecast,
        ScientificSkillId.image_classification,
    }
)
_VISUALIZATION_SKILLS = frozenset(
    {
        ScientificSkillId.chart_visualization,
        ScientificSkillId.wwt_scene,
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
    skills = frozenset(task.skill_id for task in contract.scientific_tasks)
    unsupported = outputs - SUPPORTED_RUN_OUTPUTS
    if unsupported:
        raise UnsupportedRunPlanError(unsupported)

    required = {"planning"}
    if outputs & _DATA_OUTPUTS or skills & _DATA_ANALYSIS_SKILLS:
        required.update(("fetching_data", "cleaning_data"))
    if skills & _OBSERVATION_SKILLS:
        required.add("acquiring_observations")
    if skills & _ANALYSIS_SKILLS:
        required.add("analyzing_data")
    if (
        outputs & {ArtifactKind.model_evaluation, ArtifactKind.model_artifact}
        or skills & _MODEL_SKILLS
    ):
        required.add("training_models")
    if skills & _VISUALIZATION_SKILLS:
        required.add("building_visualizations")
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
            if scientific_skill_phase(task.skill_id) == phase
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
    step_keys: frozenset[str],
) -> tuple[RunStepDefinition, ...]:
    """Freeze an already-computed affected-step closure for a revision Run."""

    unknown = step_keys - set(RUN_STEP_STATUS_ORDER)
    if unknown or "planning" not in step_keys:
        raise ValueError("revision Run steps must be canonical and include planning")
    ordered = tuple(step for step in RUN_STEP_STATUS_ORDER if step in step_keys)
    return tuple(
        RunStepDefinition(
            key=step,
            label=_STEP_LABELS[step],
            enter_status=step,
            success_status=(
                ordered[position + 1] if position + 1 < len(ordered) else "completed"
            ),
        )
        for position, step in enumerate(ordered)
    )


def _scientific_task_step_key(task_id: str) -> str:
    digest = sha256(task_id.encode("utf-8")).hexdigest()[:24]
    return f"scientific.{digest}"
