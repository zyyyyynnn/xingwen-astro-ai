"""Scientific Data Integration Benchmark frozen-corpus contract tests.

Pure-pipeline tests over synthetic fixtures: they exercise the production
alignment / normalization / conversion engines through the benchmark runner
and never touch a database or mutate production state.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[3]
PYTHONPATH = os.pathsep.join([str(ROOT / "apps" / "api" / "src"), str(ROOT)])


def _load():
    from services.data_pipeline.scientific_integration_benchmark import (
        load_integration_benchmark,
    )

    return load_integration_benchmark()


def _evaluate():
    from services.data_pipeline.scientific_integration_benchmark import (
        evaluate,
    )

    return evaluate(_load())


def _run_checker(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "check_scientific_data_integration_report.py"),
            str(path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": PYTHONPATH},
    )


def test_manifest_is_frozen_and_self_verifying() -> None:
    manifest = _load()
    assert manifest.data_level == "synthetic_fixture"
    categories = {case.category.value for case in manifest.cases}
    assert categories == {"integration", "failure_injection", "repair_probe"}
    injection_classes = {
        case.injection_class
        for case in manifest.cases
        if case.category.value == "failure_injection"
    }
    # Required injection classes stay fixed in the corpus.
    assert {
        "source_failure",
        "stale_binding",
        "capacity_exhaustion",
        "unit_conflict",
    } <= injection_classes
    from app.schemas.scientific_data_integration_benchmark import (
        REQUIRED_METRIC_NAMES,
    )

    assert set(manifest.metric_formulas) == set(REQUIRED_METRIC_NAMES)
    assert manifest.adjudication_source
    assert manifest.inconclusive_policy
    repair_expectations = {
        adjudication.expected_resolution
        for case in manifest.cases
        for adjudication in case.repair_adjudications
    }
    assert repair_expectations == {"resolved", "unresolved"}


def test_manifest_drift_fails_closed(tmp_path: Path) -> None:
    from services.data_pipeline.scientific_integration_benchmark import (
        load_integration_benchmark,
    )

    source = (
        ROOT / "services/data_pipeline/benchmarks/exoplanet_host_star/"
        "scientific-data-integration-benchmark.json"
    )
    payload = json.loads(source.read_text(encoding="utf-8"))
    payload["cases"][0]["expected_accepted_pairs"] = []
    drifted = tmp_path / "drifted.json"
    drifted.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(RuntimeError, match="drift"):
        load_integration_benchmark(drifted)


def test_report_declares_all_core_metrics_honestly() -> None:
    from app.schemas.scientific_data_integration_benchmark import (
        REQUIRED_METRIC_NAMES,
    )
    from app.schemas.scientific_document_benchmark import BenchmarkMetricStatus

    report = _evaluate()
    by_name = {metric.name: metric for metric in report.metrics}
    missing = set(REQUIRED_METRIC_NAMES) - set(by_name)
    assert not missing, f"report omitted required metrics: {missing}"
    for name in REQUIRED_METRIC_NAMES:
        assert by_name[name].status == BenchmarkMetricStatus.measured, name
        assert by_name[name].denominator and by_name[name].denominator > 0, name
    assert by_name["repair_success"].numerator == 1
    assert by_name["repair_success"].denominator == 1
    assert by_name["false_repair_rate"].numerator == 0
    assert by_name["false_repair_rate"].denominator == 1
    assert by_name["source_retrieval_completeness"].denominator == 2
    assert by_name["field_value_correctness"].denominator == 2
    assert by_name["unit_normalization_success"].denominator == 4
    assert by_name["conflict_detection"].denominator == 3


def test_double_evaluation_is_bit_stable() -> None:
    first = _evaluate()
    second = _evaluate()
    assert first.output_hash == second.output_hash
    assert first.input_hash == second.input_hash
    assert [c.status for c in first.cases] == [c.status for c in second.cases]
    repair_cases = [
        case for case in first.cases if case.category.value == "repair_probe"
    ]
    assert repair_cases
    assert all(case.reproduced_output_hash == case.output_hash for case in repair_cases)


def test_every_frozen_case_passes() -> None:
    report = _evaluate()
    failed = [case for case in report.cases if case.status != "passed"]
    assert not failed, [(c.case_id, c.failure_detail) for c in failed]
    assert len({case.case_id for case in report.cases}) == len(report.cases)


def test_retrieval_and_conflict_metrics_do_not_inherit_pair_failure() -> None:
    from services.data_pipeline.scientific_integration_benchmark import evaluate

    manifest = _load()
    cases = tuple(
        case.model_copy(update={"expected_accepted_pairs": ()})
        if case.case_id == "int.exact_one_to_one"
        else case
        for case in manifest.cases
    )

    report = evaluate(manifest.model_copy(update={"cases": cases}))

    by_name = {metric.name: metric for metric in report.metrics}
    assert by_name["source_retrieval_completeness"].numerator == 2
    assert by_name["source_retrieval_completeness"].denominator == 2
    assert by_name["conflict_detection"].numerator == 3
    assert by_name["conflict_detection"].denominator == 3
    failed = next(
        case for case in report.cases if case.case_id == "int.exact_one_to_one"
    )
    assert failed.status == "failed"
    assert "pairs mismatch" in (failed.failure_detail or "")


def test_failure_injection_cases_recover_with_exact_codes() -> None:
    report = _evaluate()
    injections = [
        case for case in report.cases if case.category.value == "failure_injection"
    ]
    assert injections
    for case in injections:
        assert case.status == "passed", (case.case_id, case.failure_detail)
        observed = case.observed_error_code
        expected = case.expected_error_code
        if expected is not None:
            assert observed == expected, (case.case_id, observed, expected)


def test_tampered_report_fails_self_verification() -> None:
    from app.schemas.scientific_data_integration_benchmark import (
        ScientificDataIntegrationReport,
    )

    report = _evaluate()
    payload = json.loads(report.model_dump_json())
    payload["metrics"][0]["numerator"] = payload["metrics"][0]["numerator"] + 1
    with pytest.raises(ValidationError):
        ScientificDataIntegrationReport.model_validate(payload)


def test_report_rejects_duplicate_case_identity() -> None:
    from app.schemas.scientific_data_integration_benchmark import (
        ScientificDataIntegrationReport,
    )

    payload = json.loads(_evaluate().model_dump_json())
    payload["cases"].append(payload["cases"][0])

    with pytest.raises(ValidationError, match="case_ids must be unique"):
        ScientificDataIntegrationReport.model_validate(payload)


def test_cli_writes_machine_report_and_human_summary(tmp_path: Path) -> None:
    output = tmp_path / "integration-report.json"
    summary = tmp_path / "integration-summary.md"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "services.data_pipeline.scientific_integration_benchmark",
            "--output",
            str(output),
            "--summary",
            str(summary),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": PYTHONPATH},
    )
    assert result.returncode == 0, result.stderr
    from app.schemas.scientific_data_integration_benchmark import (
        ScientificDataIntegrationReport,
    )

    parsed = ScientificDataIntegrationReport.model_validate_json(
        output.read_text(encoding="utf-8")
    )
    text = summary.read_text(encoding="utf-8")
    assert "# Scientific Data Integration Benchmark Summary" in text
    assert "| entity_alignment_recall |" in text
    assert "All frozen cases passed." in text
    assert parsed.report_id == "scientific-data-integration-benchmark-report"
    checked = _run_checker(output)
    assert checked.returncode == 0, checked.stderr


def test_checker_requires_measured_false_repair_denominator(tmp_path: Path) -> None:
    from app.schemas.scientific_data_integration_benchmark import (
        compute_integration_report_hash,
    )
    from app.schemas.scientific_document_benchmark import BenchmarkMetricStatus

    report = _evaluate()
    metrics = tuple(
        metric.model_copy(
            update={
                "status": BenchmarkMetricStatus.not_run,
                "numerator": 0.0,
                "denominator": 0.0,
                "rate": None,
            }
        )
        if metric.name == "false_repair_rate"
        else metric
        for metric in report.metrics
    )
    report = report.model_copy(
        update={"metrics": metrics, "output_hash": "sha256:" + "0" * 64}
    )
    report = report.model_copy(
        update={"output_hash": compute_integration_report_hash(report)}
    )
    path = tmp_path / "false-repair-not-run.json"
    path.write_text(report.model_dump_json(), encoding="utf-8")

    checked = _run_checker(path)

    assert checked.returncode == 1
    assert "false_repair_rate must be measured" in checked.stderr


def test_checker_rejects_pending_output_hash(tmp_path: Path) -> None:
    report = _evaluate().model_copy(update={"output_hash": "sha256:" + "0" * 64})
    path = tmp_path / "pending-output-hash.json"
    path.write_text(report.model_dump_json(), encoding="utf-8")

    checked = _run_checker(path)

    assert checked.returncode == 1
    assert "output_hash is still pending" in checked.stderr
