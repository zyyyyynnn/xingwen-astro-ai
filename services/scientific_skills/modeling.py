"""Deterministic bounded modeling skills replacing AutoAstro code generation."""

from __future__ import annotations

from base64 import b64encode
from collections import Counter
from datetime import UTC, datetime
from hashlib import sha256
from math import ceil, isfinite
from typing import Any

from .parameters import (
    optional_integer,
    optional_number,
    optional_string,
    reject_unknown,
    require_rows,
    require_string,
    require_string_list,
)
from .types import ScientificSkillRequest


SPLIT_STRATEGIES = ("random", "stratified", "group", "entity", "time")


def evaluate_tabular_model(request: ScientificSkillRequest) -> dict[str, object]:
    reject_unknown(
        request.parameters,
        {
            "rows",
            "feature_fields",
            "target_field",
            "task_kind",
            "algorithm",
            "split_strategy",
            "group_field",
            "entity_field",
            "time_field",
            "test_fraction",
            "random_seed",
            "cv_folds",
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
    cv_folds = optional_integer(
        request.parameters,
        "cv_folds",
        default=5,
        lower=2,
        upper=10,
    )
    if task not in {"classification", "regression"}:
        raise ValueError("task_kind must be classification or regression")
    if not 0.1 <= test_fraction <= 0.5:
        raise ValueError("test_fraction must be within [0.1, 0.5]")

    strategy = optional_string(
        request.parameters,
        "split_strategy",
        default="stratified" if task == "classification" else "random",
    )
    if strategy not in SPLIT_STRATEGIES:
        raise ValueError(
            f"split_strategy must be one of {', '.join(SPLIT_STRATEGIES)}"
        )
    strategy_field = {
        "group": "group_field",
        "entity": "entity_field",
        "time": "time_field",
    }
    strategy_parameter = strategy_field.get(strategy)
    split_field: str | None = None
    if strategy_parameter is not None:
        if strategy_parameter not in request.parameters:
            raise ValueError(f"{strategy} split requires {strategy_parameter}")
        split_field = require_string(request.parameters, strategy_parameter)
        if split_field == target:
            raise ValueError(f"{strategy_parameter} cannot be the target field")
    carry_fields = (split_field,) if split_field else ()

    matrix, labels, admitted_row_ids, carried = _tabular_matrix(
        rows, features, target, task=task, carry_fields=carry_fields
    )
    if len(matrix) < 10:
        raise ValueError("tabular model requires at least 10 complete rows")

    groups: list[object] = []
    times: list[float] = []
    if strategy in {"group", "entity"} and split_field is not None:
        groups = [row[split_field] for row in carried]
        if any(value is None for value in groups):
            raise ValueError(f"{split_field} must be present on every row")
        if len({_stable_key(value) for value in groups}) < 2:
            raise ValueError(f"{split_field} must contain at least two groups")
    elif strategy == "time" and split_field is not None:
        for row in carried:
            _kind, value = _time_sort_value(row[split_field], split_field)
            times.append(value)

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
        cv_folds=cv_folds,
        max_output_bytes=request.budget.max_output_bytes,
        split_strategy=strategy,
        groups=groups,
        times=times,
        split_field_name=split_field,
    )


def classify_time_series(request: ScientificSkillRequest) -> dict[str, object]:
    """Classify independent fixed-length series without reference-side code execution.

    Each row is one sample and ``series_fields`` defines the ordered observation
    axis.  This preserves AutoAstro's user-visible time-series classification
    task while using the same bounded, reproducible estimator and ONNX boundary
    as the canonical tabular modeling skill.
    """

    reject_unknown(
        request.parameters,
        {
            "rows",
            "series_fields",
            "target_field",
            "algorithm",
            "test_fraction",
            "random_seed",
            "cv_folds",
        },
    )
    rows = require_rows(request.parameters, max_rows=request.budget.max_input_rows)
    series_fields = require_string_list(
        request.parameters, "series_fields", max_items=256
    )
    if len(series_fields) < 4:
        raise ValueError("time-series classification requires at least four samples")
    target = require_string(request.parameters, "target_field")
    if target in series_fields:
        raise ValueError("target_field cannot also be a series field")
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
    cv_folds = optional_integer(
        request.parameters,
        "cv_folds",
        default=5,
        lower=2,
        upper=10,
    )
    if not 0.1 <= test_fraction <= 0.5:
        raise ValueError("test_fraction must be within [0.1, 0.5]")

    matrix, labels, admitted_row_ids, _carried = _tabular_matrix(
        rows, series_fields, target, task="classification"
    )
    if len(matrix) < 10:
        raise ValueError("time-series classification requires at least 10 complete rows")
    result = _fit_tabular(
        matrix=matrix,
        labels=labels,
        row_ids=admitted_row_ids,
        features=series_fields,
        target=target,
        task="classification",
        algorithm=algorithm,
        test_fraction=test_fraction,
        seed=seed,
        cv_folds=cv_folds,
        max_output_bytes=request.budget.max_output_bytes,
    )
    result["task_kind"] = "time_series_classification"
    result["series_layout"] = "ordered_fields"
    result["sequence_length"] = len(series_fields)
    return result


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
    model_binary = _serialize_onnx_model(
        model,
        samples[:split_index],
        max_output_bytes=request.budget.max_output_bytes,
    )
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
        "model_binary": model_binary,
    }


def classify_images(request: ScientificSkillRequest) -> dict[str, object]:
    reject_unknown(
        request.parameters,
        {
            "images",
            "image_count",
            "source_total_pixels",
            "image_shape",
            "preprocessing",
            "label_schema",
            "test_fraction",
            "random_seed",
        },
    )
    image_shape = request.parameters.get("image_shape")
    if image_shape != [32, 32, 3]:
        raise ValueError("image classification requires the fixed RGB image shape")
    preprocessing = request.parameters.get("preprocessing")
    expected_preprocessing = {
        "schema_version": "1.0.0",
        "color_mode": "RGB",
        "exif_transpose": True,
        "resize_height": 32,
        "resize_width": 32,
        "resize_mode": "contain_pad",
        "resampling": "bilinear",
        "normalization": "uint8_to_unit_interval",
    }
    if preprocessing != expected_preprocessing:
        raise ValueError("image classification preprocessing registry is invalid")
    raw_images = request.parameters.get("images")
    if not isinstance(raw_images, list) or len(raw_images) < 10:
        raise ValueError("image classification requires at least 10 labeled images")
    if len(raw_images) > request.budget.max_input_rows:
        raise ValueError("image count exceeds the row budget")
    matrix: list[list[float]] = []
    labels: list[str] = []
    image_ids: list[str] = []
    feature_count = 32 * 32 * 3
    for item in raw_images:
        if (
            not isinstance(item, dict)
            or set(item) != {"image_id", "label", "pixels"}
            or not isinstance(item.get("image_id"), str)
            or not item["image_id"].strip()
            or not isinstance(item.get("label"), str)
        ):
            raise ValueError("each resolved image requires identity, label and pixels")
        pixels = item.get("pixels")
        if (
            not isinstance(pixels, list)
            or len(pixels) != feature_count
        ):
            raise ValueError("each resolved image must match the fixed image shape")
        flat: list[float] = []
        for value in pixels:
            if (
                isinstance(value, bool)
                or not isinstance(value, int | float)
                or not isfinite(float(value))
                or not 0 <= float(value) <= 1
            ):
                raise ValueError("image pixels must be finite normalized numbers")
            flat.append(float(value))
        matrix.append(flat)
        labels.append(item["label"].strip())
        image_ids.append(item["image_id"].strip())
    if not labels or any(not item for item in labels):
        raise ValueError("image labels must not be blank")
    if len(image_ids) != len(set(image_ids)):
        raise ValueError("image identities must be unique")
    if len(matrix) * len(matrix[0]) * 8 > request.budget.max_input_bytes:
        raise ValueError("image tensor exceeds the byte budget")
    if request.parameters.get("image_count") != len(matrix):
        raise ValueError("image count does not match the resolved tensor")
    source_total_pixels = request.parameters.get("source_total_pixels")
    if (
        isinstance(source_total_pixels, bool)
        or not isinstance(source_total_pixels, int)
        or source_total_pixels <= 0
    ):
        raise ValueError("source total pixels metadata is invalid")
    label_schema = _validated_label_schema(
        request.parameters.get("label_schema"), labels=labels
    )
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
        row_ids=image_ids,
        features=("flattened_pixels",),
        target="label",
        task="classification",
        algorithm="random_forest",
        test_fraction=test_fraction,
        seed=seed,
        cv_folds=min(5, min(Counter(labels).values())),
        max_output_bytes=request.budget.max_output_bytes,
    )
    result["task_kind"] = "image_classification"
    result["image_count"] = len(matrix)
    result["source_total_pixels"] = source_total_pixels
    result["image_shape"] = list(image_shape)
    result["preprocessing"] = dict(expected_preprocessing)
    result["label_schema"] = label_schema
    return result


def _validated_label_schema(
    value: object,
    *,
    labels: list[str],
) -> list[dict[str, object]]:
    if not isinstance(value, list) or len(value) < 2:
        raise ValueError("image classification label schema is invalid")
    counts = Counter(labels)
    expected = [
        {"class_index": index, "label": label, "sample_count": counts[label]}
        for index, label in enumerate(
            sorted(counts, key=lambda item: (item.casefold(), item))
        )
    ]
    if value != expected:
        raise ValueError("image classification label schema does not match the images")
    return expected


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
    cv_folds: int,
    max_output_bytes: int,
    split_strategy: str | None = None,
    groups: list[object] | None = None,
    times: list[float] | None = None,
    split_field_name: str | None = None,
) -> dict[str, object]:
    from sklearn.dummy import DummyClassifier, DummyRegressor
    from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
    from sklearn.linear_model import LinearRegression, LogisticRegression
    from sklearn.metrics import (
        accuracy_score,
        brier_score_loss,
        confusion_matrix,
        f1_score,
        log_loss,
        mean_absolute_error,
        mean_squared_error,
        r2_score,
    )
    from sklearn.model_selection import (
        GroupShuffleSplit,
        train_test_split,
    )
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    if split_strategy is None:
        split_strategy = "stratified" if task == "classification" else "random"
    if split_strategy == "stratified" and task != "classification":
        raise ValueError("stratified split requires a classification target")

    label_counts = Counter(labels)
    if task == "classification" and len(label_counts) < 2:
        raise ValueError("classification requires at least two target classes")
    expected_test_count = max(1, ceil(len(matrix) * test_fraction))
    if (
        task == "classification"
        and split_strategy in {"random", "stratified"}
        and (
            min(label_counts.values()) < 2
            or expected_test_count < len(label_counts)
        )
    ):
        raise ValueError(
            "classification split cannot represent every class in both partitions"
        )
    if (
        task == "classification"
        and split_strategy in {"random", "stratified"}
        and min(label_counts.values()) < cv_folds
    ):
        raise ValueError(
            "classification cross-validation folds exceed the smallest class"
        )
    if (
        task == "regression"
        and split_strategy != "time"
        and len(matrix) < cv_folds * 2
    ):
        raise ValueError("regression cross-validation requires two rows per fold")

    indices = list(range(len(matrix)))
    train_indices: list[int]
    test_indices: list[int]
    if split_strategy in {"group", "entity"}:
        group_keys = [_stable_key(value) for value in (groups or [])]
        if not group_keys or len(group_keys) != len(matrix):
            raise ValueError("group split requires a group value for every row")
        splitter = GroupShuffleSplit(
            n_splits=1, test_size=test_fraction, random_state=seed
        )
        train_indices, test_indices = next(
            splitter.split(matrix, labels, groups=group_keys)
        )
    elif split_strategy == "time":
        if not times or len(times) != len(matrix):
            raise ValueError("time split requires a time value for every row")
        ordered = sorted(indices, key=lambda index: times[index])
        cutoff = int(len(ordered) * (1 - test_fraction))
        if cutoff <= 0 or len(ordered) - cutoff < 2:
            raise ValueError("time split produces an empty partition")
        train_indices = ordered[:cutoff]
        test_indices = ordered[cutoff:]
    elif split_strategy == "random":
        train_indices, test_indices = train_test_split(
            indices, test_size=test_fraction, random_state=seed
        )
    else:
        train_indices, test_indices = train_test_split(
            indices,
            test_size=test_fraction,
            random_state=seed,
            stratify=labels if task == "classification" else None,
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
        probabilities = model.predict_proba(test_x)
        metrics["log_loss"] = float(
            log_loss(test_y, probabilities, labels=model.classes_)
        )
        if len(model.classes_) == 2:
            positive = model.classes_[1]
            binary_actual = [1 if item == positive else 0 for item in test_y]
            metrics["brier_score"] = float(
                brier_score_loss(binary_actual, probabilities[:, 1])
            )
        baseline_metrics = {
            "accuracy": float(accuracy_score(test_y, baseline_predicted)),
            "macro_f1": float(f1_score(test_y, baseline_predicted, average="macro")),
        }
        matrix_table = confusion_matrix(
            test_y, predicted, labels=list(model.classes_)
        )
        confusion = {
            "labels": [_native(item) for item in model.classes_],
            "rows": matrix_table.tolist(),
        }
    else:
        numeric_labels = [float(item) for item in labels]
        train_y = [numeric_labels[index] for index in train_indices]
        test_y = [numeric_labels[index] for index in test_indices]
        confusion = None
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
    limitations: list[str] = []
    if split_strategy == "time":
        limitations.append(
            "validation is strictly after the training cutoff; cross-validation is"
            " skipped to avoid future leakage"
        )
    elif split_strategy in {"group", "entity"}:
        limitations.append(
            f"rows sharing one {split_field_name} value never cross the"
            " train/test boundary; cross-validation is grouped"
        )
        metrics.update(
            _cross_validation_metrics(
                model,
                matrix,
                labels,
                task=task,
                folds=cv_folds,
                seed=seed,
                groups=[_stable_key(value) for value in (groups or [])],
            )
        )
    else:
        metrics.update(
            _cross_validation_metrics(
                model,
                matrix,
                labels,
                task=task,
                folds=cv_folds,
                seed=seed,
            )
        )
    metrics.update(_feature_importance_metrics(model, features))
    if task == "classification":
        if len(label_counts) > 2:
            limitations.append("calibration is reported only for binary targets")
        smallest = min(label_counts.values())
        if smallest < 5:
            limitations.append(
                f"the smallest class has only {smallest} observations"
            )
    if len(test_indices) < 20:
        limitations.append(
            f"the evaluation partition has only {len(test_indices)} rows"
        )
    model_binary = _serialize_onnx_model(
        model,
        train_x,
        max_output_bytes=max_output_bytes,
    )
    split_report: dict[str, object] = {
        "strategy": split_strategy,
        "random_seed": seed if split_strategy != "time" else None,
        "train_count": len(train_indices),
        "test_count": len(test_indices),
        "cross_validation_folds": cv_folds
        if split_strategy != "time"
        else None,
    }
    if split_field_name is not None:
        split_report["field"] = split_field_name
    if split_strategy == "time":
        split_report["train_cutoff"] = max(times[index] for index in train_indices)
    result: dict[str, object] = {
        "task_kind": task,
        "algorithm": algorithm,
        "algorithm_version": _sklearn_version(),
        "feature_fields": list(features),
        "target_field": target,
        "split": split_report,
        "metrics": metrics,
        "baseline_metrics": baseline_metrics,
        "limitations": limitations,
        "predictions": [
            {
                "row_id": row_ids[index],
                "actual": _native(labels[index]),
                "predicted": _native(predicted[position]),
            }
            for position, index in enumerate(test_indices)
        ],
        "model_binary": model_binary,
    }
    if confusion is not None:
        result["confusion_matrix"] = confusion
    return result


def _cross_validation_metrics(
    model: object,
    matrix: list[list[float]],
    labels: list[Any],
    *,
    task: str,
    folds: int,
    seed: int,
    groups: list[str] | None = None,
) -> dict[str, float]:
    import numpy as np
    from sklearn.model_selection import (
        GroupKFold,
        KFold,
        StratifiedKFold,
        cross_validate,
    )

    if groups is not None:
        if len(set(groups)) < folds:
            raise ValueError("group cross-validation folds exceed the group count")
        splitter: object = GroupKFold(n_splits=folds)
        scoring = (
            {"accuracy": "accuracy", "macro_f1": "f1_macro"}
            if task == "classification"
            else {
                "r2": "r2",
                "mean_absolute_error": "neg_mean_absolute_error",
                "root_mean_squared_error": "neg_root_mean_squared_error",
            }
        )
        target: list[Any] = (
            labels
            if task == "classification"
            else [float(item) for item in labels]
        )
        scores = cross_validate(
            model,
            matrix,
            target,
            cv=splitter,
            scoring=scoring,
            groups=groups,
            n_jobs=1,
            error_score="raise",
        )
    else:
        if task == "classification":
            splitter = StratifiedKFold(n_splits=folds, shuffle=True, random_state=seed)
            scoring = {"accuracy": "accuracy", "macro_f1": "f1_macro"}
            target = labels
        else:
            splitter = KFold(n_splits=folds, shuffle=True, random_state=seed)
            scoring = {
                "r2": "r2",
                "mean_absolute_error": "neg_mean_absolute_error",
                "root_mean_squared_error": "neg_root_mean_squared_error",
            }
            target = [float(item) for item in labels]
        scores = cross_validate(
            model,
            matrix,
            target,
            cv=splitter,
            scoring=scoring,
            n_jobs=1,
            error_score="raise",
        )
    metrics: dict[str, float] = {}
    for name in scoring:
        values = np.asarray(scores[f"test_{name}"], dtype=float)
        if name in {"mean_absolute_error", "root_mean_squared_error"}:
            values = -values
        mean_value = float(values.mean())
        std_value = float(values.std(ddof=0))
        if not isfinite(mean_value) or not isfinite(std_value):
            raise ValueError("cross-validation produced a non-finite metric")
        metrics[f"cv_{name}_mean"] = mean_value
        metrics[f"cv_{name}_stddev"] = std_value
    return metrics


def _feature_importance_metrics(
    model: object,
    features: tuple[str, ...],
) -> dict[str, float]:
    import numpy as np

    estimator = model.steps[-1][1] if hasattr(model, "steps") else model
    raw = getattr(estimator, "feature_importances_", None)
    if raw is None:
        coefficients = getattr(estimator, "coef_", None)
        if coefficients is None:
            return {}
        coefficient_array = np.asarray(coefficients, dtype=float)
        raw = (
            np.abs(coefficient_array)
            if coefficient_array.ndim == 1
            else np.mean(np.abs(coefficient_array), axis=0)
        )
    values = np.asarray(raw, dtype=float).reshape(-1)
    if not len(values) or not np.all(np.isfinite(values)):
        raise ValueError("model produced invalid feature importance values")
    values = np.abs(values)
    total = float(values.sum())
    normalized = values / total if total > 0 else np.zeros_like(values)
    if len(normalized) != len(features):
        if features == ("flattened_pixels",):
            return {"feature_importance_flattened_pixels": float(normalized.sum())}
        raise ValueError("model feature importance shape does not match feature fields")
    return {
        f"feature_importance_{field}": float(value)
        for field, value in zip(features, normalized, strict=True)
    }


def _serialize_onnx_model(
    model: object,
    samples: list[list[float]],
    *,
    max_output_bytes: int,
) -> dict[str, object]:
    import numpy as np
    import onnx
    from skl2onnx import to_onnx

    if not samples or not samples[0]:
        raise ValueError("ONNX export requires a non-empty numeric input shape")
    input_sample = np.asarray(samples[:1], dtype=np.float32)
    exported = to_onnx(model, input_sample)
    content = exported.SerializeToString()
    if not content or len(content) > max_output_bytes:
        raise ValueError("ONNX model exceeds the output byte budget")
    onnx.checker.check_model(onnx.load_model_from_string(content))
    content_hash = "sha256:" + sha256(content).hexdigest()
    return {
        "media_type": "application/onnx",
        "content_base64": b64encode(content).decode("ascii"),
        "content_hash": content_hash,
        "input_name": exported.graph.input[0].name,
        "output_names": [item.name for item in exported.graph.output],
        "input_shape": [None, len(samples[0])],
        "opset_imports": {
            item.domain or "ai.onnx": item.version for item in exported.opset_import
        },
    }


def _tabular_matrix(
    rows: tuple[dict[str, Any], ...],
    features: tuple[str, ...],
    target: str,
    *,
    task: str,
    carry_fields: tuple[str, ...] = (),
) -> tuple[list[list[float]], list[Any], list[str], list[dict[str, object]]]:
    matrix: list[list[float]] = []
    labels: list[Any] = []
    row_ids: list[str] = []
    carried: list[dict[str, object]] = []
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
        carried.append({field: row.get(field) for field in carry_fields})
    return matrix, labels, row_ids, carried


def _stable_key(value: object) -> str:
    if isinstance(value, str):
        return f"s:{value}"
    if isinstance(value, bool):
        return f"b:{value}"
    if isinstance(value, int | float):
        return f"n:{value}"
    return repr(value)


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
