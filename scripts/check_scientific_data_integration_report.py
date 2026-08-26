"""Validate a produced Scientific Data Integration Benchmark report (fail-closed).

Checks that the report genuinely ran over the frozen corpus with no silent
skips: schema + self-verifying output hash, all eleven required metrics with
measured, non-empty denominators, every case passing, and failure-injection
cases pinned to their exact error codes.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from app.schemas.scientific_data_integration_benchmark import (
    REQUIRED_METRIC_NAMES,
    IntegrationCaseCategory,
    ScientificDataIntegrationReport,
)
from app.schemas.scientific_document_benchmark import BenchmarkMetricStatus


def main() -> int:
    if len(sys.argv) < 2:
        print(
            "usage: check_scientific_data_integration_report.py <report.json>",
            file=sys.stderr,
        )
        return 2
    path = Path(sys.argv[1])
    if not path.is_file():
        print(f"integration benchmark report missing: {path}", file=sys.stderr)
        return 1
    data = json.loads(path.read_text(encoding="utf-8"))
    report = ScientificDataIntegrationReport.model_validate(data)

    errors: list[str] = []
    by_name = {metric.name: metric for metric in report.metrics}
    for name in REQUIRED_METRIC_NAMES:
        metric = by_name.get(name)
        if metric is None:
            errors.append(f"missing required metric {name}")
            continue
        if metric.status != BenchmarkMetricStatus.measured:
            errors.append(f"metric {name} must be measured, got {metric.status.value}")
        elif not metric.denominator:
            errors.append(f"measured metric {name} has an empty denominator")

    repair_cases = [
        case
        for case in report.cases
        if case.category == IntegrationCaseCategory.repair_probe
    ]
    if len(repair_cases) < 2:
        errors.append("report must contain should-repair and must-not-repair cases")
    else:
        repair_expectations = {
            str(case.observed.get("expected_resolution")) for case in repair_cases
        }
        if repair_expectations != {"resolved", "unresolved"}:
            errors.append(
                "repair corpus must measure resolved and unresolved expectations"
            )

    failed = [case for case in report.cases if case.status != "passed"]
    if failed:
        for case in failed:
            errors.append(f"case {case.case_id} failed: {case.failure_detail}")
    injections = [
        case
        for case in report.cases
        if case.category == IntegrationCaseCategory.failure_injection
    ]
    if not injections:
        errors.append("report contains no failure-injection cases")
    else:
        for case in injections:
            if case.expected_error_code and (
                case.observed_error_code != case.expected_error_code
            ):
                errors.append(
                    f"case {case.case_id} recovered with "
                    f"{case.observed_error_code}, expected {case.expected_error_code}"
                )

    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1

    print(
        "Scientific Data Integration report valid: "
        f"{len(report.cases)} cases, output_hash={report.output_hash}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
