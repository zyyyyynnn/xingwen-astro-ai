"""Deterministic RunStep projection from one confirmed ResearchContract."""

from __future__ import annotations

from app.schemas.core import ArtifactKind, ResearchContractInput
from app.workflow.store import RunStepDefinition


class UnsupportedRunPlanError(ValueError):
    """Raised when a requested Artifact has no executable RunStep closure."""

    def __init__(self, outputs: frozenset[ArtifactKind]) -> None:
        self.outputs = outputs
        super().__init__(
            "unsupported Run output requirements: "
            + ", ".join(sorted(item.value for item in outputs))
        )


_STEP_ORDER = (
    "planning",
    "fetching_data",
    "cleaning_data",
    "searching_papers",
    "summarizing_papers",
    "reasoning_literature",
    "building_graph",
)

_STEP_LABELS = {
    "planning": "Planning",
    "fetching_data": "Fetching data",
    "cleaning_data": "Cleaning data",
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
EXECUTABLE_OUTPUTS = frozenset(ArtifactKind) - {ArtifactKind.export}


def compile_run_plan(
    contract: ResearchContractInput,
) -> tuple[RunStepDefinition, ...]:
    """Freeze the smallest ordered prerequisite closure for requested outputs."""

    outputs = frozenset(contract.output_requirements)
    unsupported = outputs - EXECUTABLE_OUTPUTS
    if unsupported:
        raise UnsupportedRunPlanError(unsupported)

    required = {"planning"}
    if outputs & _DATA_OUTPUTS:
        required.update(("fetching_data", "cleaning_data"))
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

    ordered = tuple(step for step in _STEP_ORDER if step in required)
    return tuple(
        RunStepDefinition(
            key=step,
            label=_STEP_LABELS[step],
            enter_status=step,
            success_status=(
                ordered[position + 1]
                if position + 1 < len(ordered)
                else "completed"
            ),
        )
        for position, step in enumerate(ordered)
    )
