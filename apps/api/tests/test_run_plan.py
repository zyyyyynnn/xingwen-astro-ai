from __future__ import annotations

import pytest

from app.schemas.core import ArtifactKind, ResearchContractInput, ScientificSkillId
from app.workflow.run_plan import (
    SUPPORTED_RUN_OUTPUTS,
    UnsupportedRunPlanError,
    compile_run_plan,
)
from app.workflow.store import RUN_STEP_STATUS_ORDER


def contract_for(*outputs: str, skills: tuple[str, ...] = ()) -> ResearchContractInput:
    return ResearchContractInput.model_validate(
        {
            "research_goal": "Compare a bounded astronomical sample",
            "target_objects": ["host_star"],
            "data_requirements": {"unit_policy": "canonical"},
            "requested_fields": ["star.mass"],
            "source_scope": {"allowed_sources": ["nasa_exoplanet_archive"]},
            "paper_search_scope": {"max_candidates": 20},
            "scientific_tasks": [
                {
                    "task_id": f"task_{index}",
                    "skill_id": skill,
                    "parameters": {},
                    "input_refs": [],
                }
                for index, skill in enumerate(skills, start=1)
            ],
            "output_requirements": list(outputs),
            "evidence_requirements": {"require_locator": True},
            "quality_constraints": {"source_completeness_min": 1.0},
        }
    )


@pytest.mark.parametrize(
    ("outputs", "expected_steps"),
    [
        (("dataset",), ("planning", "fetching_data", "cleaning_data")),
        (("paper_collection",), ("planning", "searching_papers")),
        (
            ("paper_summary",),
            ("planning", "searching_papers", "summarizing_papers"),
        ),
        (
            ("literature_claims",),
            (
                "planning",
                "searching_papers",
                "summarizing_papers",
                "reasoning_literature",
            ),
        ),
        (
            ("graph",),
            (
                "planning",
                "searching_papers",
                "summarizing_papers",
                "reasoning_literature",
                "building_graph",
            ),
        ),
        (
            ("analysis_report",),
            (
                "planning",
                "fetching_data",
                "cleaning_data",
                "analyzing_data",
            ),
        ),
        (
            ("visualization",),
            (
                "planning",
                "building_visualizations",
            ),
        ),
        (
            ("model_evaluation",),
            (
                "planning",
                "fetching_data",
                "cleaning_data",
                "training_models",
            ),
        ),
    ],
)
def test_compile_run_plan_freezes_the_minimum_prerequisite_closure(
    outputs: tuple[str, ...], expected_steps: tuple[str, ...]
) -> None:
    skills = {
        "analysis_report": ("data_profile",),
        "visualization": ("wwt_scene",),
        "model_evaluation": ("tabular_machine_learning",),
    }.get(outputs[0], ())
    plan = compile_run_plan(contract_for(*outputs, skills=skills))

    assert tuple(step.key for step in plan) == expected_steps
    assert tuple(step.enter_status for step in plan) == expected_steps
    assert tuple(step.success_status for step in plan) == (
        *expected_steps[1:],
        "completed",
    )


def test_compile_run_plan_includes_data_closure_only_when_requested() -> None:
    plan = compile_run_plan(contract_for("dataset", "graph"))

    assert tuple(step.key for step in plan) == (
        "planning",
        "fetching_data",
        "cleaning_data",
        "searching_papers",
        "summarizing_papers",
        "reasoning_literature",
        "building_graph",
    )


def test_compile_run_plan_fails_closed_for_an_unmapped_output() -> None:
    with pytest.raises(UnsupportedRunPlanError, match="export"):
        compile_run_plan(contract_for("export"))


def test_supported_run_outputs_are_an_explicit_fail_closed_allowlist() -> None:
    assert SUPPORTED_RUN_OUTPUTS == frozenset(
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


def test_compiled_run_plan_uses_the_workflow_store_step_order_authority() -> None:
    plan = compile_run_plan(contract_for("dataset", "graph"))
    positions = tuple(RUN_STEP_STATUS_ORDER.index(step.key) for step in plan)

    assert positions == tuple(sorted(positions))


def test_contract_requires_an_explicit_capable_skill_for_scientific_outputs() -> None:
    with pytest.raises(ValueError, match="analysis_report requires"):
        contract_for("analysis_report")
    with pytest.raises(ValueError, match="visualization requires"):
        contract_for("visualization", skills=("catalog_crossmatch",))
    with pytest.raises(ValueError, match="model_evaluation requires"):
        contract_for("model_evaluation", skills=("data_profile",))


def test_plan_combines_observation_analysis_model_and_visualization_once() -> None:
    contract = contract_for(
        "analysis_report",
        "visualization",
        "model_evaluation",
        skills=(
            ScientificSkillId.skyview_fits,
            ScientificSkillId.statistical_analysis,
            ScientificSkillId.tabular_machine_learning,
            ScientificSkillId.wwt_scene,
        ),
    )

    assert tuple(step.key for step in compile_run_plan(contract)) == (
        "planning",
        "fetching_data",
        "cleaning_data",
        "acquiring_observations",
        "analyzing_data",
        "training_models",
        "building_visualizations",
    )
