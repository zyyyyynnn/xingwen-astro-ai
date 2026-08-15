from __future__ import annotations

from app.schemas.core import ScientificSkillId
from services.scientific_skills import (
    ScientificSkillBudget,
    ScientificSkillRequest,
    build_scientific_skill_registry,
)


def _request(
    skill_id: ScientificSkillId, parameters: dict[str, object]
) -> ScientificSkillRequest:
    return ScientificSkillRequest(
        request_id=f"request.{skill_id.value}",
        project_id="project.unsupervised",
        run_id="run.unsupervised",
        skill_id=skill_id,
        parameters=parameters,
        source_references=(),
        budget=ScientificSkillBudget(timeout_seconds=30, max_output_rows=100),
    )


def _cluster_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index in range(30):
        rows.append(
            {
                "row_id": f"cluster.a.{index}",
                "x": -5 + (index % 5) * 0.1,
                "y": -5 + (index // 5) * 0.1,
            }
        )
        rows.append(
            {
                "row_id": f"cluster.b.{index}",
                "x": 5 + (index % 5) * 0.1,
                "y": 5 + (index // 5) * 0.1,
            }
        )
    return rows


def test_kmeans_returns_deterministic_assignments_and_pca_projection() -> None:
    registry = build_scientific_skill_registry()
    request = _request(
        ScientificSkillId.clustering_analysis,
        {
            "rows": _cluster_rows(),
            "feature_fields": ["x", "y"],
            "algorithm": "kmeans",
            "cluster_count": 2,
            "random_seed": 7,
        },
    )

    first = registry.execute(request)
    second = registry.execute(request)

    assert first.output_hash == second.output_hash
    assert first.output["cluster_count"] == 2
    assert first.output["noise_count"] == 0
    assert len(first.output["assignments"]) == 60
    assert len(first.output["pca_explained_variance_ratio"]) == 2
    assert float(first.output["silhouette_score"]) > 0.9


def test_isolation_forest_ranks_the_injected_outlier_first() -> None:
    rows = [
        {"row_id": f"row.{index}", "x": index / 100, "y": (index % 7) / 100}
        for index in range(40)
    ]
    rows.append({"row_id": "row.outlier", "x": 50.0, "y": -50.0})

    result = build_scientific_skill_registry().execute(
        _request(
            ScientificSkillId.anomaly_detection,
            {
                "rows": rows,
                "feature_fields": ["x", "y"],
                "algorithm": "isolation_forest",
                "contamination": 0.05,
                "random_seed": 11,
            },
        )
    )

    ranked = result.output["ranked_observations"]
    assert isinstance(ranked, list)
    assert ranked[0]["row_id"] == "row.outlier"
    assert ranked[0]["is_anomaly"] is True
    assert result.output["anomaly_count"] >= 1
