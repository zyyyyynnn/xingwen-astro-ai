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
PYTHONPATH = os.pathsep.join(
    [str(ROOT / "apps" / "api" / "src"), str(ROOT)]
)


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


def test_manifest_drift_fails_closed(tmp_path: Path) -> None:
    from services.data_pipeline.scientific_integration_benchmark import (
        load_integration_benchmark,
    )

    source = (
        ROOT
        / "services/data_pipeline/benchmarks/exoplanet_host_star/"
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
        if name == "false_repair_rate":
            # False-repair detection lives behind the scientific_repair
            # checkpoint execution surface; the frozen runner declares it
            # honestly instead of fabricating a rate.
            assert by_name[name].status == BenchmarkMetricStatus.not_run
            continue
        assert by_name[name].status == BenchmarkMetricStatus.measured, name
        assert by_name[name].denominator and by_name[name].denominator > 0, name


def test_double_evaluation_is_bit_stable() -> None:
    first = _evaluate()
    second = _evaluate()
    assert first.output_hash == second.output_hash
    assert first.input_hash == second.input_hash
    assert [c.status for c in first.cases] == [
        c.status for c in second.cases
    ]


def test_every_frozen_case_passes() -> None:
    report = _evaluate()
    failed = [case for case in report.cases if case.status != "passed"]
    assert not failed, [(c.case_id, c.failure_detail) for c in failed]


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
