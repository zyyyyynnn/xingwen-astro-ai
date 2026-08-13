"""Deterministic bounded modeling skills replacing AutoAstro code generation."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from math import ceil, isfinite
from typing import Any

from .parameters import (
    optional_number,
    optional_integer,
    optional_string,
    reject_unknown,
    require_rows,
    require_string,
    require_string_list,
)
from .types import ScientificSkillRequest


def evaluate_tabular_model(request: ScientificSkillRequest) -> dict[str, object]:
    reject_unknown(
        request.parameters,
        {
            "rows",
            "feature_fields",
            "target_field",
            "task_kind",
            "algorithm",
            "test_fraction",
            "random_seed",
        },
    )
    rows = require_rows(request.parameters, max_rows=request.budget.max_input_rows)
    features = require_string_list(request.parameters, "feature_fields", max_items=256)
    target = require_string(request.parameters, "target_field")
    if target in features:
        raise ValueError("target_field cannot also be a feature field")
    task = optional_string(request.parameters, "task_kind", default="classification")
    algorithm = optional_string(
        request.parameters, "algorithm", default="random_forest"
    )
    test_fraction = optional_number(request.parameters, "test_fraction", default=0.2)
    seed = optional_integer(
        request.parameters,
        "random_seed",
        default=42,
        lower=0,
        upper=2**32 - 1,
    )
    if task not in {"classification", "regression"}:
        raise ValueError("task_kind must be classification or regression")
    if not 0.1 <= test_fraction <= 0.5:
        raise ValueError("test_fraction must be within [0.1, 0.5]")

    matrix, labels, admitted_row_ids = _tabular_matrix(
        rows, features, target, task=task
    )
    if len(matrix) < 10:
        raise ValueError("tabular model requires at least 10 complete rows")
    return _fit_tabular(
        matrix=matrix,
        labels=labels,
        row_ids=admitted_row_ids,
        features=features,
        target=target,
        task=task,
        algorithm=algorithm,
        test_fraction=test_fraction,
        seed=seed,
    )


def forecast_time_series(request: ScientificSkillRequest) -> dict[str, object]:
    reject_unknown(
        request.parameters,
        {
            "rows",
            "time_field",
            "target_field",
            "lags",
            "horizon",
            "test_fraction",
            "random_seed",
        },
    )
    rows = require_rows(request.parameters, max_rows=request.budget.max_input_rows)
    time_field = require_string(request.parameters, "time_field")
    target_field = require_string(request.parameters, "target_field")
    lags = optional_integer(request.parameters, "lags", default=8, lower=1, upper=128)
    horizon = optional_integer(
        request.parameters,
        "horizon",
        default=8,
        lower=1,
        upper=request.budget.max_output_rows,
    )
    test_fraction = optional_number(request.parameters, "test_fraction", default=0.2)
    seed = optional_integer(
        request.parameters,
        "random_seed",
        default=42,
        lower=0,
        upper=2**32 - 1,
    )
    if not 0.1 <= test_fraction <= 0.5:
        raise ValueError("test_fraction must be within [0.1, 0.5]")
    series = _ordered_series(rows, time_field=time_field, target_field=target_field)
    if len(series) < max(20, lags * 3):
        raise ValueError("time-series forecast has too few finite observations")
    samples = [series[index - lags : index] for index in range(lags, len(series))]
    labels = series[lags:]
    split_index = int(len(samples) * (1 - test_fraction))
    if split_index <= 0 or len(samples) - split_index < 2:
        raise ValueError("time-series split produces an empty partition")

    from sklearn.ensemble import RandomForestRegressor
    from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

    model = RandomForestRegressor(
        n_estimators=200,
        min_samples_leaf=2,
        random_state=seed,
        n_jobs=1,
    )
    model.fit(samples[:split_index], labels[:split_index])
    predictions = model.predict(samples[split_index:])
    rolling = list(series[-lags:])
    future: list[float] = []
    for _ in range(horizon):
        value = float(model.predict([rolling[-lags:]])[0])
        future.append(value)
        rolling.append(value)
    actual = labels[split_index:]
    return {
        "task_kind": "forecast",
        "algorithm": "random_forest_autoregression",
        "algorithm_version": _sklearn_version(),
        "split": {
            "strategy": "time_ordered",
            "train_count": split_index,
            "test_count": len(actual),
            "lags": lags,
        },
        "metrics": _regression_metrics(actual, predictions),
        "forecast": [
            {"step": index + 1, "predicted_value": value}
            for index, value in enumerate(future)
        ],
        "diagnostics": {
            "r2": float(r2_score(actual, predictions)),
            "mean_absolute_error": float(mean_absolute_error(actual, predictions)),
            "root_mean_squared_error": float(
                mean_squared_error(actual, predictions) ** 0.5
            ),
        },
    }


def classify_images(request: ScientificSkillRequest) -> dict[str, object]:
    reject_unknown(
        request.parameters,
        {"images", "test_fraction", "random_seed"},
    )
    raw_images = request.parameters.get("images")
    if not isinstance(raw_images, list) or len(raw_images) < 10:
        raise ValueError("image classification requires at least 10 labeled images")
    if len(raw_images) > request.budget.max_input_rows:
        raise ValueError("image count exceeds the row budget")
    matrix: list[list[float]] = []
    labels: list[str] = []
    shape: tuple[int, int] | None = None
    for item in raw_images:
        if not isinstance(item, dict) or not isinstance(item.get("label"), str):
            raise ValueError("each image requires a string label")
        pixels = item.get("pixels")
        if (
            not isinstance(pixels, list)
            or not pixels
            or not all(isinstance(row, list) and row for row in pixels)
        ):
            raise ValueError("each image requires a non-empty 2D pixels array")
        current_shape = (len(pixels), len(pixels[0]))
        if any(len(row) != current_shape[1] for row in pixels):
            raise ValueError("image rows must have an equal width")
        if shape is None:
            shape = current_shape
        elif shape != current_shape:
            raise ValueError("all images must have the same shape")
        if current_shape[0] * current_shape[1] * len(raw_images) * 8 > (
            request.budget.max_input_bytes
        ):
            raise ValueError("image tensor exceeds the byte budget")
        flat: list[float] = []
        for row in pixels:
            for value in row:
                if (
                    isinstance(value, bool)
                    or not isinstance(value, int | float)
                    or not isfinite(float(value))
                ):
                    raise ValueError("image pixels must be finite numbers")
                flat.append(float(value))
        matrix.append(flat)
        labels.append(item["label"].strip())
    if not labels or any(not item for item in labels):
        raise ValueError("image labels must not be blank")
    if len(matrix) * len(matrix[0]) * 8 > request.budget.max_input_bytes:
        raise ValueError("image tensor exceeds the byte budget")
    test_fraction = optional_number(request.parameters, "test_fraction", default=0.2)
    if not 0.1 <= test_fraction <= 0.5:
        raise ValueError("test_fraction must be within [0.1, 0.5]")
    seed = optional_integer(
        request.parameters,
        "random_seed",
        default=42,
        lower=0,
        upper=2**32 - 1,
    )
    result = _fit_tabular(
        matrix=matrix,
        labels=labels,
        row_ids=[f"image.{index + 1}" for index in range(len(matrix))],
        features=("flattened_pixels",),
        target="label",
        task="classification",
        algorithm="random_forest",
        test_fraction=test_fraction,
        seed=seed,
    )
    result["task_kind"] = "image_classification"
    result["image_shape"] = list(shape or ())
    return result


def _fit_tabular(
    *,
    matrix: list[list[float]],
    labels: list[Any],
    row_ids: list[str],
    features: tuple[str, ...],
    target: str,
    task: str,
    algorithm: str,
    test_fraction: float,
    seed: int,
) -> dict[str, object]:
    from sklearn.dummy import DummyClassifier, DummyRegressor
    from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
    from sklearn.linear_model import LinearRegression, LogisticRegression
    from sklearn.metrics import (
        accuracy_score,
        f1_score,
        mean_absolute_error,
        mean_squared_error,
        r2_score,
    )
    from sklearn.model_selection import train_test_split
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    label_counts = Counter(labels)
    if task == "classification" and len(label_counts) < 2:
        raise ValueError("classification requires at least two target classes")
    expected_test_count = max(1, ceil(len(matrix) * test_fraction))
    if task == "classification" and (
        min(label_counts.values()) < 2 or expected_test_count < len(label_counts)
    ):
        raise ValueError(
            "classification split cannot represent every class in both partitions"
        )
    stratify = labels if task == "classification" else None
    indices = list(range(len(matrix)))
    train_indices, test_indices = train_test_split(
        indices,
        test_size=test_fraction,
        random_state=seed,
        stratify=stratify,
    )
    train_x = [matrix[index] for index in train_indices]
    test_x = [matrix[index] for index in test_indices]
    train_y = [labels[index] for index in train_indices]
    test_y = [labels[index] for index in test_indices]
    if task == "classification":
        if algorithm == "random_forest":
            model = RandomForestClassifier(
                n_estimators=200,
                min_samples_leaf=2,
                class_weight="balanced",
                random_state=seed,
                n_jobs=1,
            )
        elif algorithm == "logistic_regression":
            model = make_pipeline(
                StandardScaler(),
                LogisticRegression(max_iter=2000, random_state=seed),
            )
        else:
            raise ValueError("unsupported classification algorithm")
        baseline = DummyClassifier(strategy="most_frequent")
        model.fit(train_x, train_y)
        baseline.fit(train_x, train_y)
        predicted = model.predict(test_x)
        baseline_predicted = baseline.predict(test_x)
        metrics = {
            "accuracy": float(accuracy_score(test_y, predicted)),
            "macro_f1": float(f1_score(test_y, predicted, average="macro")),
        }
        baseline_metrics = {
            "accuracy": float(accuracy_score(test_y, baseline_predicted)),
            "macro_f1": float(f1_score(test_y, baseline_predicted, average="macro")),
        }
    else:
        numeric_labels = [float(item) for item in labels]
        train_y = [numeric_labels[index] for index in train_indices]
        test_y = [numeric_labels[index] for index in test_indices]
        if algorithm == "random_forest":
            model = RandomForestRegressor(
                n_estimators=200,
                min_samples_leaf=2,
                random_state=seed,
                n_jobs=1,
            )
        elif algorithm == "linear_regression":
            model = LinearRegression()
        else:
            raise ValueError("unsupported regression algorithm")
        baseline = DummyRegressor(strategy="mean")
        model.fit(train_x, train_y)
        baseline.fit(train_x, train_y)
        predicted = model.predict(test_x)
        baseline_predicted = baseline.predict(test_x)
        metrics = {
            "r2": float(r2_score(test_y, predicted)),
            "mean_absolute_error": float(mean_absolute_error(test_y, predicted)),
            "root_mean_squared_error": float(
                mean_squared_error(test_y, predicted) ** 0.5
            ),
        }
        baseline_metrics = {
            "r2": float(r2_score(test_y, baseline_predicted)),
            "mean_absolute_error": float(
                mean_absolute_error(test_y, baseline_predicted)
            ),
            "root_mean_squared_error": float(
                mean_squared_error(test_y, baseline_predicted) ** 0.5
            ),
        }
    return {
        "task_kind": task,
        "algorithm": algorithm,
        "algorithm_version": _sklearn_version(),
        "feature_fields": list(features),
        "target_field": target,
        "split": {
            "strategy": "stratified_holdout" if stratify is not None else "holdout",
            "random_seed": seed,
            "train_count": len(train_indices),
            "test_count": len(test_indices),
        },
        "metrics": metrics,
        "baseline_metrics": baseline_metrics,
        "predictions": [
            {
                "row_id": row_ids[index],
                "actual": _native(labels[index]),
                "predicted": _native(predicted[position]),
            }
            for position, index in enumerate(test_indices)
        ],
    }


def _tabular_matrix(
    rows: tuple[dict[str, Any], ...],
    features: tuple[str, ...],
    target: str,
    *,
    task: str,
) -> tuple[list[list[float]], list[Any], list[str]]:
    matrix: list[list[float]] = []
    labels: list[Any] = []
    row_ids: list[str] = []
    for index, row in enumerate(rows):
        values = [row.get(field) for field in features]
        label = row.get(target)
        if any(
            isinstance(value, bool)
            or not isinstance(value, int | float)
            or not isfinite(float(value))
            for value in values
        ) or not _valid_target(label, task=task):
            continue
        matrix.append([float(value) for value in values])
        labels.append(label)
        row_ids.append(str(row.get("row_id", f"row.{index + 1}")))
    return matrix, labels, row_ids


def _valid_target(value: object, *, task: str) -> bool:
    if task == "regression":
        return (
            isinstance(value, int | float)
            and not isinstance(value, bool)
            and isfinite(float(value))
        )
    if isinstance(value, str):
        return bool(value.strip())
    return isinstance(value, int | bool) or (
        isinstance(value, float) and isfinite(value)
    )


def _ordered_series(
    rows: tuple[dict[str, Any], ...],
    *,
    time_field: str,
    target_field: str,
) -> list[float]:
    points: list[tuple[str, float, float]] = []
    for row in rows:
        target = row.get(target_field)
        if (
            isinstance(target, bool)
            or not isinstance(target, int | float)
            or not isfinite(float(target))
        ):
            continue
        time_kind, time_value = _time_sort_value(row.get(time_field), time_field)
        points.append((time_kind, time_value, float(target)))
    kinds = {item[0] for item in points}
    if len(kinds) > 1:
        raise ValueError("time_field must use one consistent numeric or ISO-8601 type")
    times = [item[1] for item in points]
    if len(times) != len(set(times)):
        raise ValueError("time_field must not contain duplicate values")
    return [item[2] for item in sorted(points, key=lambda item: item[1])]


def _time_sort_value(value: object, field: str) -> tuple[str, float]:
    if (
        isinstance(value, int | float)
        and not isinstance(value, bool)
        and isfinite(float(value))
    ):
        return "numeric", float(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError(f"{field} must contain ISO-8601 timestamps") from error
        normalized = parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed
        return "iso8601", normalized.timestamp()
    raise ValueError(f"{field} must contain finite numbers or ISO-8601 timestamps")


def _regression_metrics(actual: list[float], predicted: Any) -> dict[str, float]:
    from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

    return {
        "r2": float(r2_score(actual, predicted)),
        "mean_absolute_error": float(mean_absolute_error(actual, predicted)),
        "root_mean_squared_error": float(mean_squared_error(actual, predicted) ** 0.5),
    }


def _native(value: Any) -> object:
    item = value.item() if hasattr(value, "item") else value
    if isinstance(item, str | int | float | bool) or item is None:
        return item
    return str(item)


def _sklearn_version() -> str:
    import sklearn

    return f"scikit-learn:{sklearn.__version__}"


__all__ = [
    "classify_images",
    "evaluate_tabular_model",
    "forecast_time_series",
]
