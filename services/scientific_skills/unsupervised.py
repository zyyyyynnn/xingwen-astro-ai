"""Bounded clustering, PCA projection, and anomaly detection.

AutoAstro exposes these tasks through generated Python.  This module preserves
the user-facing analysis while replacing that execution model with explicit
algorithms, deterministic seeds, strict numeric inputs, and bounded outputs.
"""

from __future__ import annotations

from math import isfinite
from typing import Any

from .parameters import (
    optional_integer,
    optional_number,
    optional_string,
    reject_unknown,
    require_rows,
    require_string_list,
)
from .types import ScientificSkillRequest


def run_clustering(request: ScientificSkillRequest) -> dict[str, object]:
    reject_unknown(
        request.parameters,
        {
            "rows",
            "feature_fields",
            "algorithm",
            "cluster_count",
            "eps",
            "min_samples",
            "random_seed",
        },
    )
    rows = require_rows(request.parameters, max_rows=request.budget.max_input_rows)
    fields = require_string_list(
        request.parameters, "feature_fields", max_items=64
    )
    algorithm = optional_string(
        request.parameters, "algorithm", default="kmeans"
    )
    seed = optional_integer(
        request.parameters,
        "random_seed",
        default=42,
        lower=0,
        upper=2**32 - 1,
    )
    matrix, row_ids = _numeric_matrix(rows, fields)
    if len(matrix) < 10:
        raise ValueError("clustering requires at least 10 complete numeric rows")

    import numpy as np
    from sklearn.cluster import DBSCAN, KMeans
    from sklearn.metrics import silhouette_score
    from sklearn.preprocessing import StandardScaler

    scaled = StandardScaler().fit_transform(np.asarray(matrix, dtype=float))
    if algorithm == "kmeans":
        cluster_count = optional_integer(
            request.parameters,
            "cluster_count",
            default=3,
            lower=2,
            upper=min(20, len(matrix) - 1),
        )
        labels = KMeans(
            n_clusters=cluster_count,
            n_init=10,
            random_state=seed,
        ).fit_predict(scaled)
        parameters: dict[str, int | float] = {"cluster_count": cluster_count}
    elif algorithm == "dbscan":
        eps = optional_number(request.parameters, "eps", default=0.5)
        min_samples = optional_integer(
            request.parameters,
            "min_samples",
            default=5,
            lower=2,
            upper=min(100, len(matrix)),
        )
        if not 0 < eps <= 20:
            raise ValueError("eps must be within (0, 20]")
        labels = DBSCAN(eps=eps, min_samples=min_samples).fit_predict(scaled)
        parameters = {"eps": eps, "min_samples": min_samples}
    else:
        raise ValueError("clustering algorithm must be kmeans or dbscan")

    non_noise = labels != -1
    distinct = sorted({int(value) for value in labels if int(value) >= 0})
    silhouette: float | None = None
    if 1 < len(distinct) < int(non_noise.sum()):
        silhouette = float(silhouette_score(scaled[non_noise], labels[non_noise]))
    projection, explained = _pca_projection(scaled)
    limit = min(len(matrix), request.budget.max_output_rows)
    return {
        "algorithm": algorithm,
        "algorithm_version": _sklearn_version(),
        "feature_fields": list(fields),
        "sample_count": len(matrix),
        "cluster_count": len(distinct),
        "noise_count": int((labels == -1).sum()),
        "silhouette_score": silhouette,
        "parameters": parameters,
        "pca_explained_variance_ratio": explained,
        "assignments": [
            {
                "row_id": row_ids[index],
                "cluster": int(labels[index]),
                "pca_x": projection[index][0],
                "pca_y": projection[index][1],
            }
            for index in range(limit)
        ],
        "truncated": limit < len(matrix),
    }


def detect_anomalies(request: ScientificSkillRequest) -> dict[str, object]:
    reject_unknown(
        request.parameters,
        {
            "rows",
            "feature_fields",
            "algorithm",
            "contamination",
            "z_threshold",
            "random_seed",
        },
    )
    rows = require_rows(request.parameters, max_rows=request.budget.max_input_rows)
    fields = require_string_list(
        request.parameters, "feature_fields", max_items=64
    )
    algorithm = optional_string(
        request.parameters, "algorithm", default="isolation_forest"
    )
    seed = optional_integer(
        request.parameters,
        "random_seed",
        default=42,
        lower=0,
        upper=2**32 - 1,
    )
    matrix, row_ids = _numeric_matrix(rows, fields)
    if len(matrix) < 20:
        raise ValueError("anomaly detection requires at least 20 complete numeric rows")

    import numpy as np
    from sklearn.ensemble import IsolationForest
    from sklearn.preprocessing import StandardScaler

    scaled = StandardScaler().fit_transform(np.asarray(matrix, dtype=float))
    if algorithm == "isolation_forest":
        contamination = optional_number(
            request.parameters, "contamination", default=0.05
        )
        if not 0 < contamination <= 0.25:
            raise ValueError("contamination must be within (0, 0.25]")
        model = IsolationForest(
            n_estimators=200,
            contamination=contamination,
            random_state=seed,
            n_jobs=1,
        )
        predictions = model.fit_predict(scaled)
        scores = -model.score_samples(scaled)
        is_anomaly = predictions == -1
        parameters: dict[str, float] = {"contamination": contamination}
    elif algorithm == "robust_zscore":
        threshold = optional_number(
            request.parameters, "z_threshold", default=3.5
        )
        if not 1 <= threshold <= 10:
            raise ValueError("z_threshold must be within [1, 10]")
        median = np.median(scaled, axis=0)
        deviation = np.abs(scaled - median)
        mad = np.median(deviation, axis=0)
        safe_mad = np.where(mad > 1e-12, mad, 1.0)
        robust = 0.6744897501960817 * deviation / safe_mad
        scores = np.max(robust, axis=1)
        is_anomaly = scores > threshold
        parameters = {"z_threshold": threshold}
    else:
        raise ValueError(
            "anomaly detection algorithm must be isolation_forest or robust_zscore"
        )

    projection, explained = _pca_projection(scaled)
    ranked = sorted(
        range(len(matrix)),
        key=lambda index: (-float(scores[index]), row_ids[index]),
    )
    limit = min(len(ranked), request.budget.max_output_rows)
    return {
        "algorithm": algorithm,
        "algorithm_version": _sklearn_version(),
        "feature_fields": list(fields),
        "sample_count": len(matrix),
        "anomaly_count": int(np.sum(is_anomaly)),
        "parameters": parameters,
        "pca_explained_variance_ratio": explained,
        "ranked_observations": [
            {
                "row_id": row_ids[index],
                "anomaly_score": float(scores[index]),
                "is_anomaly": bool(is_anomaly[index]),
                "pca_x": projection[index][0],
                "pca_y": projection[index][1],
            }
            for index in ranked[:limit]
        ],
        "truncated": limit < len(ranked),
    }


def _numeric_matrix(
    rows: tuple[dict[str, Any], ...], fields: tuple[str, ...]
) -> tuple[list[list[float]], list[str]]:
    if not fields:
        raise ValueError("feature_fields must not be empty")
    matrix: list[list[float]] = []
    row_ids: list[str] = []
    for index, row in enumerate(rows):
        values = [row.get(field) for field in fields]
        if any(
            isinstance(value, bool)
            or not isinstance(value, int | float)
            or not isfinite(float(value))
            for value in values
        ):
            continue
        matrix.append([float(value) for value in values])
        row_ids.append(str(row.get("row_id", f"row.{index + 1}")))
    if len(row_ids) != len(set(row_ids)):
        raise ValueError("row_id values must be unique after numeric filtering")
    return matrix, row_ids


def _pca_projection(matrix: Any) -> tuple[list[tuple[float, float]], list[float]]:
    import numpy as np
    from sklearn.decomposition import PCA

    component_count = min(2, matrix.shape[0], matrix.shape[1])
    model = PCA(n_components=component_count, svd_solver="full")
    transformed = model.fit_transform(matrix)
    if component_count == 1:
        transformed = np.column_stack((transformed[:, 0], np.zeros(matrix.shape[0])))
    projection = [
        (float(point[0]), float(point[1])) for point in transformed.tolist()
    ]
    explained = [float(value) for value in model.explained_variance_ratio_.tolist()]
    if component_count == 1:
        explained.append(0.0)
    return projection, explained


def _sklearn_version() -> str:
    import sklearn

    return f"scikit-learn:{sklearn.__version__}"


__all__ = ["detect_anomalies", "run_clustering"]
