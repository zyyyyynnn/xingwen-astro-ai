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
        entry: dict[str, object] = {
            "field": field,
            "non_null_count": len(non_null),
            "null_count": len(values) - len(non_null),
            "distinct_count": len({_stable_scalar(value) for value in non_null}),
            "type_counts": dict(sorted(type_counts.items())),
        }
        entry["categorical_summary"] = _categorical_summary(non_null)
        numeric = [float(value) for value in non_null if _is_number(value)]
        if numeric:
            entry["numeric_summary"] = {
                "count": len(numeric),
                "minimum": min(numeric),
                "maximum": max(numeric),
                "mean": mean(numeric),
                "median": median(numeric),
            }
            entry["outlier_summary"] = _outlier_summary(numeric)
        profile.append(entry)
    return {
        "row_count": len(rows),
        "field_count": len(fields),
        "fields": profile,
    }


def _categorical_summary(non_null: list[object]) -> dict[str, object] | None:
    counts = Counter(_stable_scalar(value) for value in non_null)
    if len(counts) < 2 or len(counts) > 50:
        return None
    representative = {
        _stable_scalar(value): value
        for value in non_null
        if isinstance(value, str | int | float | bool)
    }
    total = len(non_null)
    top = counts.most_common(5)
    return {
        "category_count": len(counts),
        "top_categories": [
            {
                "value": representative.get(value, value),
                "count": count,
                "share": round(count / total, 4),
            }
            for value, count in top
        ],
    }


def _outlier_summary(numeric: list[float]) -> dict[str, object]:
    ordered = sorted(numeric)
    mid = len(ordered) // 2
    lower_half = ordered[: mid]
    upper_half = ordered[mid + len(ordered) % 2 :]
    q1 = median(lower_half) if lower_half else ordered[0]
    q3 = median(upper_half) if upper_half else ordered[-1]
    iqr = q3 - q1
    low_fence = q1 - 1.5 * iqr
    high_fence = q3 + 1.5 * iqr
    outliers = [value for value in numeric if value < low_fence or value > high_fence]
    return {
        "method": "iqr_fence",
        "q1": q1,
        "q3": q3,
        "iqr": iqr,
        "low_fence": low_fence,
        "high_fence": high_fence,
        "outlier_count": len(outliers),
    }


def analyze_statistics(request: ScientificSkillRequest) -> dict[str, object]:
    reject_unknown(
        request.parameters,
        {"rows", "fields", "hypothesis_tests", "alpha"},
    )
    rows = require_rows(request.parameters, max_rows=request.budget.max_input_rows)
    fields = (
        require_string_list(request.parameters, "fields", max_items=128)
        if "fields" in request.parameters
        else ()
    )
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
    alpha = request.parameters.get("alpha", 0.05)
    if (
        isinstance(alpha, bool)
        or not isinstance(alpha, int | float)
        or not isfinite(float(alpha))
        or not 0 < float(alpha) < 1
    ):
        raise ValueError("alpha must be a finite number within (0, 1)")
    tests = _hypothesis_tests(
        rows,
        request.parameters.get("hypothesis_tests", []),
        alpha=float(alpha),
    )
    if not results and not tests:
        raise ValueError("statistical_analysis requires fields or hypothesis_tests")
    return {
        "statistics": results,
        "hypothesis_tests": tests,
        "alpha": float(alpha),
    }


def analyze_correlations(request: ScientificSkillRequest) -> dict[str, object]:
    reject_unknown(request.parameters, {"rows", "fields", "method"})
    rows = require_rows(request.parameters, max_rows=request.budget.max_input_rows)
    fields = require_string_list(request.parameters, "fields", max_items=64)
    method = optional_string(request.parameters, "method", default="pearson")
    if method not in {"pearson", "spearman"}:
        raise ValueError("correlation method must be pearson or spearman")
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
            value = _spearman(pairs) if method == "spearman" else _pearson(pairs)
            correlations.append(
                {
                    "left_field": left,
                    "right_field": right,
                    "pair_count": len(pairs),
                    "method": method,
                    f"{method}_r": value,
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


def _hypothesis_tests(
    rows: tuple[dict[str, Any], ...],
    raw_tests: object,
    *,
    alpha: float,
) -> list[dict[str, object]]:
    if not isinstance(raw_tests, list):
        raise ValueError("hypothesis_tests must be an array")
    if len(raw_tests) > 32:
        raise ValueError("hypothesis_tests exceeds the bounded test count")
    return [
        _hypothesis_test(rows, raw, test_index=index, alpha=alpha)
        for index, raw in enumerate(raw_tests, start=1)
    ]


def _hypothesis_test(
    rows: tuple[dict[str, Any], ...],
    raw: object,
    *,
    test_index: int,
    alpha: float,
) -> dict[str, object]:
    if not isinstance(raw, dict):
        raise ValueError("each hypothesis test must be an object")
    kind = raw.get("kind")
    if not isinstance(kind, str):
        raise ValueError("hypothesis test kind must be text")
    from scipy import stats

    sample_counts: list[int]
    assumptions: list[str]
    effect_size: dict[str, float] | None = None
    if kind == "one_sample_t":
        _require_test_keys(raw, {"kind", "field", "expected_mean"})
        field = _test_field(raw, "field")
        values = _require_numeric_sample(rows, field, minimum=2)
        expected = _finite_test_number(raw, "expected_mean")
        result = stats.ttest_1samp(values, popmean=expected)
        sample_counts = [len(values)]
        assumptions = ["independent observations", "approximately normal sample mean"]
        effect_size = _cohens_d_one_sample(values, expected)
    elif kind in {"independent_t", "paired_t", "mann_whitney_u"}:
        _require_test_keys(raw, {"kind", "left_field", "right_field"})
        left_field = _test_field(raw, "left_field")
        right_field = _test_field(raw, "right_field")
        if left_field == right_field:
            raise ValueError("hypothesis test fields must be distinct")
        if kind == "paired_t":
            pairs = [
                (float(row[left_field]), float(row[right_field]))
                for row in rows
                if _is_number(row.get(left_field)) and _is_number(row.get(right_field))
            ]
            if len(pairs) < 2:
                raise ValueError("paired_t requires at least two complete pairs")
            left = [item[0] for item in pairs]
            right = [item[1] for item in pairs]
            result = stats.ttest_rel(left, right)
            sample_counts = [len(pairs), len(pairs)]
            assumptions = ["paired observations", "approximately normal differences"]
            differences = [a - b for a, b in pairs]
            effect_size = _cohens_d_one_sample(differences, 0.0)
        else:
            left = _require_numeric_sample(rows, left_field, minimum=2)
            right = _require_numeric_sample(rows, right_field, minimum=2)
            if kind == "independent_t":
                result = stats.ttest_ind(left, right, equal_var=False)
                assumptions = ["independent observations", "Welch unequal variances"]
                effect_size = _cohens_d_independent(left, right)
            else:
                outcome = stats.mannwhitneyu(left, right, alternative="two-sided")
                result = outcome
                assumptions = [
                    "independent observations",
                    "ordinal or continuous values",
                ]
                effect_size = {
                    "rank_biserial_r": 1.0
                    - 2.0
                    * float(outcome.statistic)
                    / (len(left) * len(right))
                }
            sample_counts = [len(left), len(right)]
    elif kind == "one_way_anova":
        _require_test_keys(raw, {"kind", "fields"})
        raw_fields = raw.get("fields")
        if (
            not isinstance(raw_fields, list)
            or not 2 <= len(raw_fields) <= 32
            or not all(isinstance(item, str) and item.strip() for item in raw_fields)
            or len(set(raw_fields)) != len(raw_fields)
        ):
            raise ValueError("one_way_anova fields must contain 2-32 unique names")
        samples = [
            _require_numeric_sample(rows, field.strip(), minimum=2)
            for field in raw_fields
        ]
        result = stats.f_oneway(*samples)
        sample_counts = [len(sample) for sample in samples]
        assumptions = ["independent groups", "approximately normal residuals"]
        effect_size = _eta_squared(samples)
    elif kind == "chi_square_independence":
        _require_test_keys(raw, {"kind", "left_field", "right_field"})
        left_field = _test_field(raw, "left_field")
        right_field = _test_field(raw, "right_field")
        table = _contingency_table(rows, left_field, right_field)
        statistic, p_value, _dof, expected = stats.chi2_contingency(table)
        if any(float(value) < 5 for row in expected for value in row):
            assumptions = ["some expected cell counts are below five"]
        else:
            assumptions = ["all expected cell counts are at least five"]
        sample_counts = [sum(sum(row) for row in table)]
        total = sum(sum(row) for row in table)
        min_dimension = min(len(table), len(table[0])) - 1
        return _test_result(
            test_index=test_index,
            kind=kind,
            statistic=float(statistic),
            p_value=float(p_value),
            alpha=alpha,
            sample_counts=sample_counts,
            assumptions=assumptions,
            effect_size={
                "cramers_v": (float(statistic) / (total * min_dimension)) ** 0.5
            },
        )
    elif kind == "shapiro_wilk":
        _require_test_keys(raw, {"kind", "field"})
        field = _test_field(raw, "field")
        values = _require_numeric_sample(rows, field, minimum=3)
        if len(values) > 5000:
            raise ValueError("shapiro_wilk accepts at most 5000 observations")
        result = stats.shapiro(values)
        sample_counts = [len(values)]
        assumptions = ["continuous observations", "independent observations"]
    else:
        raise ValueError(f"unsupported hypothesis test kind: {kind}")
    return _test_result(
        test_index=test_index,
        kind=kind,
        statistic=float(result.statistic),
        p_value=float(result.pvalue),
        alpha=alpha,
        sample_counts=sample_counts,
        assumptions=assumptions,
        effect_size=effect_size,
    )


def _require_test_keys(raw: dict[str, Any], allowed: set[str]) -> None:
    unknown = set(raw) - allowed
    if unknown:
        raise ValueError(
            "hypothesis test contains unsupported keys: " + ", ".join(sorted(unknown))
        )


def _test_field(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"hypothesis test {key} must be non-empty text")
    return value.strip()


def _finite_test_number(raw: dict[str, Any], key: str) -> float:
    value = raw.get(key)
    if (
        isinstance(value, bool)
        or not isinstance(value, int | float)
        or not isfinite(float(value))
    ):
        raise ValueError(f"hypothesis test {key} must be a finite number")
    return float(value)


def _require_numeric_sample(
    rows: tuple[dict[str, Any], ...], field: str, *, minimum: int
) -> list[float]:
    sample = _numeric_column(rows, field)
    if len(sample) < minimum:
        raise ValueError(
            f"hypothesis test field {field} requires at least {minimum} finite values"
        )
    return sample


def _contingency_table(
    rows: tuple[dict[str, Any], ...], left_field: str, right_field: str
) -> list[list[int]]:
    pairs = [
        (row.get(left_field), row.get(right_field))
        for row in rows
        if row.get(left_field) is not None and row.get(right_field) is not None
    ]
    left_values = sorted({_stable_scalar(left) for left, _right in pairs})
    right_values = sorted({_stable_scalar(right) for _left, right in pairs})
    if not 2 <= len(left_values) <= 64 or not 2 <= len(right_values) <= 64:
        raise ValueError("chi_square_independence requires 2-64 categories per field")
    counts = Counter(
        (_stable_scalar(left), _stable_scalar(right)) for left, right in pairs
    )
    table = [[counts[(left, right)] for right in right_values] for left in left_values]
    if any(sum(row) == 0 for row in table):
        raise ValueError("chi-square contingency table has an empty row")
    return table


def _test_result(
    *,
    test_index: int,
    kind: str,
    statistic: float,
    p_value: float,
    alpha: float,
    sample_counts: list[int],
    assumptions: list[str],
    effect_size: dict[str, float] | None = None,
) -> dict[str, object]:
    if not isfinite(statistic) or not isfinite(p_value) or not 0 <= p_value <= 1:
        raise ValueError(f"{kind} produced a non-finite statistic or p-value")
    result: dict[str, object] = {
        "test_id": f"hypothesis.{test_index}",
        "kind": kind,
        "statistic": statistic,
        "p_value": p_value,
        "alpha": alpha,
        "reject_null": p_value < alpha,
        "sample_counts": sample_counts,
        "assumptions": assumptions,
        "library_revision": _scipy_version(),
    }
    if effect_size is not None:
        result["effect_size"] = effect_size
    return result


def _sample_stddev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean_value = mean(values)
    return (sum((value - mean_value) ** 2 for value in values) / (len(values) - 1)) ** 0.5


def _cohens_d_one_sample(values: list[float], expected: float) -> dict[str, float]:
    stddev = _sample_stddev(values)
    if stddev == 0.0:
        return {"cohens_d": 0.0}
    return {"cohens_d": (mean(values) - expected) / stddev}


def _cohens_d_independent(
    left: list[float], right: list[float]
) -> dict[str, float]:
    pooled = (
        (
            (len(left) - 1) * _sample_stddev(left) ** 2
            + (len(right) - 1) * _sample_stddev(right) ** 2
        )
        / (len(left) + len(right) - 2)
    ) ** 0.5
    if pooled == 0.0:
        return {"cohens_d": 0.0}
    return {"cohens_d": (mean(left) - mean(right)) / pooled}


def _eta_squared(samples: list[list[float]]) -> dict[str, float]:
    overall = mean([value for sample in samples for value in sample])
    between = sum(
        len(sample) * (mean(sample) - overall) ** 2 for sample in samples
    )
    within = sum(
        (value - mean(sample)) ** 2
        for sample in samples
        for value in sample
    )
    total = between + within
    if total == 0.0:
        return {"eta_squared": 0.0}
    return {"eta_squared": between / total}


def _scipy_version() -> str:
    import scipy

    return f"scipy:{scipy.__version__}"


def _pearson(pairs: list[tuple[float, float]]) -> float:
    left = [item[0] for item in pairs]
    right = [item[1] for item in pairs]
    if pstdev(left) == 0 or pstdev(right) == 0:
        return 0.0
    return correlation(left, right)


def _spearman(pairs: list[tuple[float, float]]) -> float:
    def _ranks(values: list[float]) -> list[float]:
        order = sorted(range(len(values)), key=lambda index: values[index])
        ranks = [0.0] * len(values)
        index = 0
        while index < len(order):
            tie_start = index
            while (
                index + 1 < len(order)
                and values[order[index + 1]] == values[order[tie_start]]
            ):
                index += 1
            average_rank = (tie_start + index) / 2 + 1
            for position in range(tie_start, index + 1):
                ranks[order[position]] = average_rank
            index += 1
        return ranks

    return _pearson(
        list(zip(_ranks([item[0] for item in pairs]), _ranks([item[1] for item in pairs]), strict=True))
    )


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
