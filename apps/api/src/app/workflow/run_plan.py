"""Deterministic RunStep projection from one confirmed ResearchContract."""

from __future__ import annotations

from app.schemas.core import ArtifactKind, ResearchContractInput, ScientificSkillId
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
        ScientificSkillId.tabular_machine_learning,
        ScientificSkillId.time_series_forecast,
        ScientificSkillId.image_classification,
    }
)
_OBSERVATION_SKILLS = frozenset(
    {
        ScientificSkillId.simbad_lookup,
        ScientificSkillId.skyview_fits,
        ScientificSkillId.ephemeris,
        ScientificSkillId.celestial_events,
    }
)
_ANALYSIS_SKILLS = frozenset(
    {
        ScientificSkillId.catalog_crossmatch,
        ScientificSkillId.data_profile,
        ScientificSkillId.statistical_analysis,
        ScientificSkillId.correlation_analysis,
        ScientificSkillId.fits_image_analysis,
    }
)
_MODEL_SKILLS = frozenset(
    {
        ScientificSkillId.tabular_machine_learning,
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
SUPPORTED_RUN_OUTPUTS = frozenset(
    {
        ArtifactKind.dataset,
        ArtifactKind.field_dictionary,
        ArtifactKind.source_collection,
        ArtifactKind.analysis_report,
        ArtifactKind.visualization,
        ArtifactKind.model_evaluation,
        ArtifactKind.paper_collection,
        ArtifactKind.paper_summary,
        ArtifactKind.literature_claims,
        ArtifactKind.literature_relations,
        ArtifactKind.reasoning_traces,
        ArtifactKind.graph,
    }
)


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
    if ArtifactKind.model_evaluation in outputs or skills & _MODEL_SKILLS:
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

    ordered = tuple(step for step in RUN_STEP_STATUS_ORDER if step in required)
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
