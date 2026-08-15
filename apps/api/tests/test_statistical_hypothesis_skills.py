from __future__ import annotations

from app.schemas.core import ScientificSkillId
from services.scientific_skills.registry import build_scientific_skill_registry
from services.scientific_skills.types import (
    ScientificSkillBudget,
    ScientificSkillRequest,
)


def _execute(rows: list[dict[str, object]], tests: list[dict[str, object]]):
    request = ScientificSkillRequest(
        request_id="request.hypothesis",
        project_id="project.hypothesis",
        run_id="run.hypothesis",
        skill_id=ScientificSkillId.statistical_analysis,
        parameters={
            "rows": rows,
            "fields": ["control", "treatment"],
            "hypothesis_tests": tests,
            "alpha": 0.05,
        },
        source_references=(),
        budget=ScientificSkillBudget(max_input_rows=1000),
    )
    return build_scientific_skill_registry().execute(request).output


def test_categorical_hypothesis_test_does_not_require_numeric_profile_fields() -> None:
    rows = [
        {"group": "near" if index < 10 else "far", "detected": index % 2 == 0}
        for index in range(20)
    ]
    request = ScientificSkillRequest(
        request_id="request.categorical",
        project_id="project.hypothesis",
        run_id="run.hypothesis",
        skill_id=ScientificSkillId.statistical_analysis,
        parameters={
            "rows": rows,
            "hypothesis_tests": [
                {
                    "kind": "chi_square_independence",
                    "left_field": "group",
                    "right_field": "detected",
                }
            ],
        },
        source_references=(),
    )

    output = build_scientific_skill_registry().execute(request).output

    assert output["statistics"] == []
    assert output["hypothesis_tests"][0]["kind"] == "chi_square_independence"


def test_statistical_skill_runs_bounded_parametric_and_nonparametric_tests() -> None:
    rows = [
        {
            "control": float(index),
            "treatment": float(index + 8 + (index % 3)),
            "group": "near" if index < 10 else "far",
            "detected": "yes" if index % 2 == 0 else "no",
        }
        for index in range(1, 21)
    ]
    output = _execute(
        rows,
        [
            {"kind": "one_sample_t", "field": "control", "expected_mean": 0},
            {
                "kind": "independent_t",
                "left_field": "control",
                "right_field": "treatment",
            },
            {
                "kind": "paired_t",
                "left_field": "control",
                "right_field": "treatment",
            },
            {
                "kind": "mann_whitney_u",
                "left_field": "control",
                "right_field": "treatment",
            },
            {
                "kind": "one_way_anova",
                "fields": ["control", "treatment"],
            },
            {"kind": "shapiro_wilk", "field": "control"},
            {
                "kind": "chi_square_independence",
                "left_field": "group",
                "right_field": "detected",
            },
        ],
    )

    results = output["hypothesis_tests"]
    assert [item["test_id"] for item in results] == [
        f"hypothesis.{index}" for index in range(1, 8)
    ]
    assert {item["kind"] for item in results} == {
        "one_sample_t",
        "independent_t",
        "paired_t",
        "mann_whitney_u",
        "one_way_anova",
        "shapiro_wilk",
        "chi_square_independence",
    }
    assert all(0 <= item["p_value"] <= 1 for item in results)
    assert all(item["library_revision"].startswith("scipy:") for item in results)


def test_statistical_skill_rejects_unknown_tests_and_degenerate_samples() -> None:
    rows = [
        {"control": float(index), "treatment": float(index + 1)} for index in range(3)
    ]

    for tests in (
        [{"kind": "execute_python", "field": "control"}],
        [{"kind": "shapiro_wilk", "field": "missing"}],
        [
            {
                "kind": "one_sample_t",
                "field": "control",
                "expected_mean": 0,
                "code": "pass",
            }
        ],
    ):
        try:
            _execute(rows, tests)
        except ValueError:
            continue
        raise AssertionError("invalid hypothesis test must fail closed")
