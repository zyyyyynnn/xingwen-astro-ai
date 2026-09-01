from __future__ import annotations

import pytest

from app.schemas.core import ArtifactKind, ResearchContractInput
from app.workflow.run_plan import (
    SUPPORTED_RUN_OUTPUTS,
    UnsupportedRunPlanError,
    artifact_kinds_for_steps,
    compile_revision_run_plan,
    compile_run_plan,
)
from app.workflow.store import RUN_STEP_STATUS_ORDER


def contract_for(*outputs: str) -> ResearchContractInput:
    return ResearchContractInput.model_validate(
        {
            "research_goal": "Compare a bounded astronomical sample",
            "target_objects": ["host_star"],
            "data_requirements": {"unit_policy": "canonical", "document_source_policy": "disabled"},
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
    assert {step.key: step.max_attempts for step in plan} == {
        "planning": 1,
        "fetching_data": 2,
        "cleaning_data": 1,
        "searching_papers": 2,
        "summarizing_papers": 2,
        "reasoning_literature": 2,
        "building_graph": 1,
    }


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
            ArtifactKind.spectrum,
            ArtifactKind.light_curve,
            ArtifactKind.model_evaluation,
            ArtifactKind.model_artifact,
            ArtifactKind.paper_collection,
            ArtifactKind.paper_summary,
            ArtifactKind.literature_claims,
            ArtifactKind.literature_relations,
            ArtifactKind.graph,
        }
    )


def test_compiled_run_plan_uses_the_workflow_store_step_order_authority() -> None:
    plan = compile_run_plan(contract_for("dataset", "graph"))
    positions = tuple(RUN_STEP_STATUS_ORDER.index(step.key) for step in plan)

    assert positions == tuple(sorted(positions))


@pytest.mark.parametrize("skill_id", ("clustering_analysis", "anomaly_detection"))
def test_unsupervised_skill_is_frozen_as_task_owned_analysis_step(
    skill_id: str,
) -> None:
    contract = ResearchContractInput.model_validate(
        {
            **contract_for("dataset").model_dump(mode="json"),
            "output_requirements": ["analysis_report", "visualization"],
            "scientific_tasks": [
                {
                    "task_id": f"task-{skill_id}",
                    "skill_id": skill_id,
                    "input_refs": ["dataset-version"],
                    "parameters": {"feature_fields": ["x", "y"]},
                }
            ],
        }
    )

    plan = compile_run_plan(contract)
    scientific = next(step for step in plan if step.task_id is not None)

    assert scientific.key.startswith("scientific.")
    assert scientific.task_id == f"task-{skill_id}"
    assert scientific.skill_id == skill_id
    assert scientific.enter_status == "analyzing_data"


def test_revision_plan_preserves_scientific_task_identity_and_dependencies() -> None:
    contract = ResearchContractInput.model_validate(
        {
            **contract_for("dataset").model_dump(mode="json"),
            "output_requirements": ["analysis_report", "visualization"],
            "scientific_tasks": [
                {
                    "task_id": "cluster-stars",
                    "skill_id": "clustering_analysis",
                    "input_refs": ["dataset-version"],
                    "parameters": {"feature_fields": ["x", "y"]},
                }
            ],
        }
    )
    parent = compile_run_plan(contract)
    scientific = next(step for step in parent if step.task_id == "cluster-stars")

    derived = compile_revision_run_plan(parent, frozenset({"planning", scientific.key}))

    assert tuple(step.key for step in derived) == ("planning", scientific.key)
    assert derived[1].task_id == "cluster-stars"
    assert derived[1].skill_id == "clustering_analysis"
    assert derived[1].enter_status == "analyzing_data"
    assert derived[1].depends_on_step_keys == ("planning",)


def test_scientific_artifact_closure_uses_the_frozen_skill_capability() -> None:
    contract = ResearchContractInput.model_validate(
        {
            **contract_for("dataset").model_dump(mode="json"),
            "output_requirements": ["analysis_report"],
            "scientific_tasks": [
                {
                    "task_id": "gaia-nearby",
                    "skill_id": "gaia_cone_search",
                    "input_refs": [],
                    "parameters": {
                        "ra_degrees": 10.0,
                        "dec_degrees": 20.0,
                        "radius_degrees": 0.1,
                    },
                }
            ],
        }
    )
    plan = compile_run_plan(contract)

    kinds = artifact_kinds_for_steps(
        plan,
        requested_outputs=frozenset(contract.output_requirements),
    )

    assert kinds == (ArtifactKind.analysis_report,)


def test_gaia_source_table_and_implicit_dataset_prerequisite_fail_closed() -> None:
    contract = ResearchContractInput.model_validate(
        {
            **contract_for("dataset").model_dump(mode="json"),
            "output_requirements": ["dataset", "analysis_report"],
            "source_scope": {"allowed_sources": ["esa_gaia_dr3"]},
            "scientific_tasks": [
                {
                    "task_id": "gaia-nearby",
                    "skill_id": "gaia_cone_search",
                    "input_refs": [],
                    "parameters": {
                        "ra_degrees": 10.0,
                        "dec_degrees": 20.0,
                        "radius_degrees": 0.1,
                    },
                },
                {
                    "task_id": "profile-gaia-output",
                    "skill_id": "data_profile",
                    "input_refs": [],
                    "parameters": {},
                },
            ],
        }
    )

    with pytest.raises(UnsupportedRunPlanError, match="cannot share a Run plan"):
        compile_run_plan(contract)


def test_multiple_gaia_source_table_producers_fail_closed() -> None:
    contract = ResearchContractInput.model_validate(
        {
            **contract_for("dataset").model_dump(mode="json"),
            "output_requirements": ["dataset"],
            "source_scope": {"allowed_sources": ["esa_gaia_dr3"]},
            "scientific_tasks": [
                {
                    "task_id": "gaia-nearby-a",
                    "skill_id": "gaia_cone_search",
                    "input_refs": [],
                    "parameters": {
                        "ra_degrees": 10.0,
                        "dec_degrees": 20.0,
                        "radius_degrees": 0.1,
                    },
                },
                {
                    "task_id": "gaia-nearby-b",
                    "skill_id": "gaia_cone_search",
                    "input_refs": [],
                    "parameters": {
                        "ra_degrees": 30.0,
                        "dec_degrees": 40.0,
                        "radius_degrees": 0.1,
                    },
                },
            ],
        }
    )

    with pytest.raises(UnsupportedRunPlanError, match="exactly one"):
        compile_run_plan(contract)
