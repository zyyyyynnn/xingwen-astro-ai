"""Statistics and unsupervised correctness through the public skill API.

A small representative set with hand-computed expected values; no algorithm
benchmark suite.  Code-execution parameters must be rejected by every skill.
"""

from __future__ import annotations

import math
from uuid import uuid4

import pytest

from app.schemas.core import ScientificSkillId
from services.scientific_skills import (
    ScientificSkillBudget,
    ScientificSkillRequest,
    build_scientific_skill_registry,
)

PROJECT_ID = str(uuid4())
RUN_ID = str(uuid4())


def _execute(skill_id: ScientificSkillId, parameters: dict[str, object]) -> dict:
    result = build_scientific_skill_registry().execute(
        ScientificSkillRequest(
            request_id=f"request.{skill_id.value}",
            project_id=PROJECT_ID,
            run_id=RUN_ID,
            skill_id=skill_id,
            parameters=parameters,
            source_references=(),
            budget=ScientificSkillBudget(timeout_seconds=60),
        )
    )
    return result.output


def test_independent_t_reports_hand_computed_cohens_d() -> None:
    # left: mean 14, sample variance 10; right: mean 3, sample variance 2.5.
    # Pooled variance = (4*10 + 4*2.5) / 8 = 6.25 -> pooled sd 2.5.
    # Cohen's d = (14 - 3) / 2.5 = 4.4.
    rows = [{"left": value} for value in (10, 12, 14, 16, 18)]
    for index, value in enumerate((1, 2, 3, 4, 5)):
        rows[index]["right"] = value
    output = _execute(
        ScientificSkillId.statistical_analysis,
        {
            "rows": rows,
            "hypothesis_tests": [
                {"kind": "independent_t", "left_field": "left", "right_field": "right"}
            ],
        },
    )
    test = output["hypothesis_tests"][0]
    assert test["kind"] == "independent_t"
    assert test["p_value"] < 0.05
    pooled_sd = math.sqrt((4 * 10 + 4 * 2.5) / 8)
    assert float(test["effect_size"]["cohens_d"]) == pytest.approx(
        (14 - 3) / pooled_sd, rel=1e-9
    )


def test_one_way_anova_reports_hand_computed_eta_squared() -> None:
    # Three groups of three: between-group SS = 54, within SS = 6, eta^2 = 0.9.
    rows = []
    for value in (1, 2, 3):
        rows.append({"a": value})
    for index, value in enumerate((4, 5, 6)):
        rows[index]["b"] = value
    for index, value in enumerate((7, 8, 9)):
        rows[index]["c"] = value
    output = _execute(
        ScientificSkillId.statistical_analysis,
        {
            "rows": rows,
            "hypothesis_tests": [{"kind": "one_way_anova", "fields": ["a", "b", "c"]}],
        },
    )
    test = output["hypothesis_tests"][0]
    assert test["kind"] == "one_way_anova"
    assert float(test["effect_size"]["eta_squared"]) == pytest.approx(
        0.9, rel=1e-9
    )


def test_chi_square_reports_cramers_v_of_one_for_perfect_association() -> None:
    rows = [
        {"group": "A", "outcome": "X"} for _ in range(20)
    ] + [{"group": "B", "outcome": "Y"} for _ in range(20)]
    output = _execute(
        ScientificSkillId.statistical_analysis,
        {
            "rows": rows,
            "hypothesis_tests": [
                {
                    "kind": "chi_square_independence",
                    "left_field": "group",
                    "right_field": "outcome",
                }
            ],
        },
    )
    test = output["hypothesis_tests"][0]
    assert test["kind"] == "chi_square_independence"
    # Perfect diagonal 2x2 table under the Yates correction applied by
    # chi2_contingency: ((|ad - bc| - N/2)^2 * N) / (r1 * r2 * c1 * c2).
    expected_statistic = ((400 - 20) ** 2 * 40) / (20 * 20 * 20 * 20)
    assert float(test["statistic"]) == pytest.approx(expected_statistic, rel=1e-9)
    assert float(test["effect_size"]["cramers_v"]) == pytest.approx(
        math.sqrt(expected_statistic / 40), rel=1e-9
    )


@pytest.mark.parametrize(
    "skill_id",
    [
        ScientificSkillId.statistical_analysis,
        ScientificSkillId.clustering_analysis,
        ScientificSkillId.anomaly_detection,
    ],
)
def test_code_execution_parameters_are_rejected(
    skill_id: ScientificSkillId,
) -> None:
    parameters: dict[str, object] = {
        "rows": [{"x": 1.0} for _ in range(24)],
        "execute_python": "import os",
        "code": "print('run')",
    }
    if skill_id is ScientificSkillId.statistical_analysis:
        parameters["fields"] = ["x"]
    else:
        parameters["feature_fields"] = ["x"]
    with pytest.raises(ValueError, match="unsupported scientific skill parameters"):
        build_scientific_skill_registry().execute(
            ScientificSkillRequest(
                request_id=f"request.{skill_id.value}",
                project_id=PROJECT_ID,
                run_id=RUN_ID,
                skill_id=skill_id,
                parameters=parameters,
                source_references=(),
                budget=ScientificSkillBudget(timeout_seconds=30),
            )
        )


def test_kmeans_is_deterministic_with_silhouette_and_pca_projection() -> None:
    rows = []
    for index in range(15):
        rows.append({"row_id": f"near.origin.{index}", "x": index * 0.1, "y": index * 0.05})
    for index in range(15):
        rows.append({"row_id": f"far.cluster.{index}", "x": 50 + index * 0.1, "y": 40 + index * 0.05})
    parameters = {
        "rows": rows,
        "feature_fields": ["x", "y"],
        "algorithm": "kmeans",
        "cluster_count": 2,
        "random_seed": 7,
    }
    first = _execute(ScientificSkillId.clustering_analysis, dict(parameters))
    second = _execute(ScientificSkillId.clustering_analysis, dict(parameters))

    assert first == second, "KMeans output must be deterministic for a fixed seed"
    assert first["cluster_count"] == 2
    assert first["silhouette_score"] is not None
    assert float(first["silhouette_score"]) > 0.9

    assignments = {item["row_id"]: item["cluster"] for item in first["assignments"]}
    near_clusters = {assignments[f"near.origin.{index}"] for index in range(15)}
    far_clusters = {assignments[f"far.cluster.{index}"] for index in range(15)}
    assert len(near_clusters) == 1 and len(far_clusters) == 1
    assert near_clusters != far_clusters
    for item in first["assignments"]:
        assert math.isfinite(float(item["pca_x"]))
        assert math.isfinite(float(item["pca_y"]))
    ratios = first["pca_explained_variance_ratio"]
    assert float(ratios[0]) > 0.9, "the dominant axis carries both clusters"


def test_isolation_forest_ranks_the_injected_outlier_as_the_top_anomaly() -> None:
    rows = [
        {"row_id": f"regular.{index}", "x": 1.0 + 0.01 * index, "y": 2.0 + 0.01 * index}
        for index in range(40)
    ]
    rows.append({"row_id": "outlier.1", "x": 500.0, "y": -400.0})
    output = _execute(
        ScientificSkillId.anomaly_detection,
        {
            "rows": rows,
            "feature_fields": ["x", "y"],
            "algorithm": "isolation_forest",
            "random_seed": 3,
        },
    )
    ranked = output["ranked_observations"]
    assert ranked
    assert ranked[0]["row_id"] == "outlier.1"
    assert ranked[0]["is_anomaly"] is True
