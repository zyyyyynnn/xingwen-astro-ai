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
    ScientificDataIntegrationBenchmarkManifest,
    ScientificDataIntegrationReport,
    compute_integration_manifest_content_hash,
)
from app.schemas.scientific_document_benchmark import BenchmarkMetricStatus

_PENDING_OUTPUT_HASH = "sha256:" + "0" * 64
_MANIFEST_PATH = (
    Path(__file__).resolve().parents[1]
    / "services"
    / "data_pipeline"
    / "benchmarks"
    / "exoplanet_host_star"
    / "scientific-data-integration-benchmark.json"
)


def _manifest_integrity_errors(
    manifest: ScientificDataIntegrationBenchmarkManifest,
) -> list[str]:
    actual_hash = compute_integration_manifest_content_hash(manifest)
    if manifest.content_hash != actual_hash:
        return [
            "frozen integration manifest content_hash does not self-verify "
            f"(got {manifest.content_hash}, expected {actual_hash})"
        ]
    return []


def _expected_frozen_denominators(
    manifest: ScientificDataIntegrationBenchmarkManifest,
    report: ScientificDataIntegrationReport,
) -> dict[str, float]:
    report_cases = {case.case_id: case for case in report.cases}
    expected_pairs = sum(
        len(case.expected_accepted_pairs)
        for case in manifest.cases
        if case.category == IntegrationCaseCategory.integration
    )
    predicted_pairs = sum(
        int(report_cases[case.case_id].observed.get("accepted_pair_count", 0))
        for case in manifest.cases
        if case.category == IntegrationCaseCategory.integration
        and case.case_id in report_cases
    )
    return {
        "source_retrieval_completeness": float(
            sum(len(case.source_retrieval_expectations) for case in manifest.cases)
        ),
        "field_value_correctness": float(
            sum(len(case.field_value_adjudications) for case in manifest.cases)
        ),
        "entity_alignment_precision": float(predicted_pairs),
        "entity_alignment_recall": float(expected_pairs),
        "unit_normalization_success": float(
            sum(
                not probe.expects_rejection
                for case in manifest.cases
                for probe in case.conversion_probes
            )
        ),
        "conflict_detection": float(
            sum(len(case.conflict_adjudications) for case in manifest.cases)
        ),
        "repair_success": float(
            sum(
                adjudication.expected_resolution == "resolved"
                for case in manifest.cases
                for adjudication in case.repair_adjudications
            )
        ),
        "false_repair_rate": float(
            sum(
                adjudication.expected_resolution == "unresolved"
                for case in manifest.cases
                for adjudication in case.repair_adjudications
            )
        ),
        "reproducibility_hash_stability": float(
            sum(
                case.scenario_id is not None and case.expected_error_code is None
                for case in manifest.cases
            )
        ),
        "failure_recovery": float(
            sum(
                case.category == IntegrationCaseCategory.failure_injection
                and case.scenario_id is not None
                and case.expected_error_code is not None
                for case in manifest.cases
            )
            + sum(
                case.category == IntegrationCaseCategory.failure_injection
                and probe.expects_rejection
                for case in manifest.cases
                for probe in case.conversion_probes
            )
        ),
    }


def _expected_case_ids(
    manifest: ScientificDataIntegrationBenchmarkManifest,
) -> set[str]:
    expected: set[str] = set()
    for case in manifest.cases:
        if case.scenario_id is not None:
            expected.add(case.case_id)
        if case.field_value_adjudications:
            expected.add(f"{case.case_id}.field_value")
        if case.conversion_probes:
            expected.add(case.case_id)
    return expected


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
    manifest = ScientificDataIntegrationBenchmarkManifest.model_validate_json(
        _MANIFEST_PATH.read_text(encoding="utf-8")
    )

    errors = _manifest_integrity_errors(manifest)
    if report.output_hash == _PENDING_OUTPUT_HASH:
        errors.append("integration report output_hash is still pending")
    by_name = {metric.name: metric for metric in report.metrics}
    if (
        report.benchmark_manifest_id != manifest.benchmark_id
        or report.benchmark_manifest_version != manifest.version
        or report.benchmark_manifest_content_hash != manifest.content_hash
        or report.evaluation_version != manifest.evaluation_version
        or report.metric_formulas != manifest.metric_formulas
    ):
        errors.append("report does not match the current frozen benchmark manifest")
    observed_case_ids = {case.case_id for case in report.cases}
    expected_case_ids = _expected_case_ids(manifest)
    if observed_case_ids != expected_case_ids:
        errors.append(
            "report case set does not match the frozen benchmark corpus "
            f"(missing={sorted(expected_case_ids - observed_case_ids)}, "
            f"unexpected={sorted(observed_case_ids - expected_case_ids)})"
        )
    report_cases = {case.case_id: case for case in report.cases}
    for manifest_case in manifest.cases:
        if (
            manifest_case.scenario_id is None
            or manifest_case.expected_error_code is not None
        ):
            continue
        observed_case = report_cases.get(manifest_case.case_id)
        if (
            observed_case is None
            or observed_case.output_hash is None
            or observed_case.reproduced_output_hash is None
        ):
            errors.append(
                f"case {manifest_case.case_id} lacks a completed reproducibility rerun"
            )
        elif observed_case.output_hash != observed_case.reproduced_output_hash:
            errors.append(
                f"case {manifest_case.case_id} reproducibility hashes do not match"
            )
    expected_denominators = _expected_frozen_denominators(manifest, report)
    for name in REQUIRED_METRIC_NAMES:
        metric = by_name.get(name)
        if metric is None:
            errors.append(f"missing required metric {name}")
            continue
        if metric.status != BenchmarkMetricStatus.measured:
            errors.append(f"metric {name} must be measured, got {metric.status.value}")
        elif not metric.denominator:
            errors.append(f"measured metric {name} has an empty denominator")
        expected_denominator = expected_denominators.get(name)
        if (
            expected_denominator is not None
            and metric.denominator != expected_denominator
        ):
            errors.append(
                f"metric {name} denominator {metric.denominator} does not match "
                f"frozen corpus denominator {expected_denominator}"
            )

    for name in (
        "source_retrieval_completeness",
        "evidence_coverage",
        "reproducibility_hash_stability",
    ):
        metric = by_name.get(name)
        if (
            metric is not None
            and metric.status == BenchmarkMetricStatus.measured
            and metric.numerator != metric.denominator
        ):
            errors.append(f"metric {name} must close every frozen denominator item")

    expected_retrieval_snapshots = {
        expectation.source_snapshot_id
        for case in manifest.cases
        for expectation in case.source_retrieval_expectations
    }
    observed_retrieval_snapshots = {
        str(snapshot_id)
        for case in report.cases
        for snapshot_id in (
            case.observed.get("retrieval_source_snapshot_ids", [])
            if isinstance(case.observed.get("retrieval_source_snapshot_ids", []), list)
            else []
        )
    }
    if not expected_retrieval_snapshots <= observed_retrieval_snapshots:
        errors.append(
            "report does not expose every frozen retrieval SourceSnapshot identity"
        )

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
