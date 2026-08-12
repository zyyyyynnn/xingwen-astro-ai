from __future__ import annotations

import pytest

from app.schemas.core import ResearchContractInput
from app.workflow.run_plan import UnsupportedRunPlanError, compile_run_plan


def contract_for(*outputs: str) -> ResearchContractInput:
    return ResearchContractInput.model_validate(
        {
            "research_goal": "Compare a bounded astronomical sample",
            "target_objects": ["host_star"],
            "data_requirements": {"unit_policy": "canonical"},
            "requested_fields": ["star.mass"],
            "source_scope": {"allowed_sources": ["nasa_exoplanet_archive"]},
            "paper_search_scope": {"max_candidates": 20},
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
    ],
)
def test_compile_run_plan_freezes_the_minimum_prerequisite_closure(
    outputs: tuple[str, ...], expected_steps: tuple[str, ...]
) -> None:
    plan = compile_run_plan(contract_for(*outputs))

    assert tuple(step.key for step in plan) == expected_steps
    assert tuple(step.enter_status for step in plan) == expected_steps
    assert tuple(step.success_status for step in plan) == (*expected_steps[1:], "completed")


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
