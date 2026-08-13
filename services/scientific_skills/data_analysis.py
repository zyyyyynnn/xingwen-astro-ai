"""Bounded data-analysis skills adapted from AutoAstro task semantics."""

from __future__ import annotations

from collections import Counter
from math import isfinite
from statistics import correlation, mean, median, pstdev
from typing import Any

from .parameters import (
    optional_string,
    reject_unknown,
    require_rows,
    require_string,
    require_string_list,
)
from .types import ScientificSkillRequest


def build_data_profile(request: ScientificSkillRequest) -> dict[str, object]:
    reject_unknown(request.parameters, {"rows"})
    rows = require_rows(request.parameters, max_rows=request.budget.max_input_rows)
    fields = tuple(sorted({key for row in rows for key in row}))
    profile: list[dict[str, object]] = []
    for field in fields:
        values = [row.get(field) for row in rows]
        non_null = [value for value in values if value is not None]
        type_counts = Counter(_value_kind(value) for value in non_null)
        profile.append(
            {
                "field": field,
                "non_null_count": len(non_null),
                "null_count": len(values) - len(non_null),
                "distinct_count": len({_stable_scalar(value) for value in non_null}),
                "type_counts": dict(sorted(type_counts.items())),
            }
        )
    return {
        "row_count": len(rows),
        "field_count": len(fields),
        "fields": profile,
    }


def analyze_statistics(request: ScientificSkillRequest) -> dict[str, object]:
    reject_unknown(request.parameters, {"rows", "fields"})
    rows = require_rows(request.parameters, max_rows=request.budget.max_input_rows)
    fields = require_string_list(request.parameters, "fields", max_items=128)
    results = []
    for field in fields:
        values = _numeric_column(rows, field)
        if not values:
            raise ValueError(f"{field} has no finite numeric values")
        results.append(
            {
                "field": field,
                "count": len(values),
                "minimum": min(values),
                "maximum": max(values),
                "mean": mean(values),
                "median": median(values),
                "population_stddev": pstdev(values),
            }
        )
    return {"statistics": results}


def analyze_correlations(request: ScientificSkillRequest) -> dict[str, object]:
    reject_unknown(request.parameters, {"rows", "fields"})
    rows = require_rows(request.parameters, max_rows=request.budget.max_input_rows)
    fields = require_string_list(request.parameters, "fields", max_items=64)
    correlations: list[dict[str, object]] = []
    for index, left in enumerate(fields):
        for right in fields[index + 1 :]:
            pairs = [
                (float(row[left]), float(row[right]))
                for row in rows
                if _is_number(row.get(left)) and _is_number(row.get(right))
            ]
            if len(pairs) < 2:
                continue
            correlations.append(
                {
                    "left_field": left,
                    "right_field": right,
                    "pair_count": len(pairs),
                    "pearson_r": _pearson(pairs),
                }
            )
    return {"correlations": correlations}


def build_visualization(request: ScientificSkillRequest) -> dict[str, object]:
    reject_unknown(
        request.parameters,
        {"rows", "x_field", "y_field", "mark", "title", "series_label"},
    )
    rows = require_rows(request.parameters, max_rows=request.budget.max_output_rows)
    x_field = require_string(request.parameters, "x_field")
    y_field = require_string(request.parameters, "y_field")
    mark = optional_string(request.parameters, "mark", default="point")
    if mark not in {"line", "point", "bar", "area"}:
        raise ValueError("mark is not supported")
    points = []
    for row in rows:
        if x_field not in row or y_field not in row:
            continue
        points.append(
            {
                "x": _chart_value(row[x_field], x_field),
                "y": _chart_value(row[y_field], y_field),
            }
        )
    if not points:
        raise ValueError("chart has no finite scalar points")
    return {
        "mode": "chart",
        "title": optional_string(
            request.parameters, "title", default=f"{y_field} by {x_field}"
        ),
        "x_field": x_field,
        "y_field": y_field,
        "series": [
            {
                "series_id": "series.primary",
                "label": optional_string(
                    request.parameters, "series_label", default=y_field
                ),
                "mark": mark,
                "points": points,
            }
        ],
    }


def run_catalog_crossmatch(request: ScientificSkillRequest) -> dict[str, object]:
    """Execute the existing project-owned crossmatch engine from a typed input."""

    reject_unknown(request.parameters, {"crossmatch_input"})
    raw = request.parameters.get("crossmatch_input")
    if not isinstance(raw, dict):
        raise ValueError("crossmatch_input must be an object")
    from app.schemas.crossmatch import CrossmatchInput
    from services.data_pipeline.crossmatch import align_cross_source_records

    result = align_cross_source_records(CrossmatchInput.model_validate(raw))
    return result.model_dump(mode="json")


def _value_kind(value: object) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int | float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _stable_scalar(value: Any) -> str:
    return repr(value)


def _is_number(value: object) -> bool:
    return (
        isinstance(value, int | float)
        and not isinstance(value, bool)
        and isfinite(float(value))
    )


def _numeric_column(rows: tuple[dict[str, Any], ...], field: str) -> list[float]:
    return [float(row[field]) for row in rows if _is_number(row.get(field))]


def _pearson(pairs: list[tuple[float, float]]) -> float:
    left = [item[0] for item in pairs]
    right = [item[1] for item in pairs]
    if pstdev(left) == 0 or pstdev(right) == 0:
        return 0.0
    return correlation(left, right)


def _chart_value(value: object, field: str) -> int | float | str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if _is_number(value):
        return value
    raise ValueError(f"{field} contains a non-finite or non-scalar chart value")


__all__ = [
    "analyze_correlations",
    "analyze_statistics",
    "build_data_profile",
    "build_visualization",
    "run_catalog_crossmatch",
]
