"""Paired native/hybrid Scientific Document Parsing benchmark contract tests.

The visual transport used here is a deterministic in-process fixture that
mimics the official PaddleOCR-VL ``/layout-parsing`` response shape so the
runner plumbing can be tested without model weights. These tests never claim a
Live visual execution; the real-Paddle exit gate is governed separately by
controlled integration evidence.
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

pytestmark = pytest.mark.scientific_document_native

ROOT = Path(__file__).resolve().parents[3]
PYTHONPATH = os.pathsep.join(
    [str(ROOT / "apps" / "api" / "src"), str(ROOT), str(ROOT / "scripts")]
)


def _stub_layout_parsing_payload() -> dict:
    """Canned official-response shape with title + scientific-value anchors."""
    return {
        "errorCode": 0,
        "errorMsg": "Success",
        "result": {
            "layoutParsingResults": [
                {
                    "prunedResult": {
                        "width": 612,
                        "height": 792,
                        "parsing_res_list": [
                            {
                                "block_label": "title",
                                "block_content": (
                                    "Exoplanet Host-Star Integration Study"
                                ),
                                "block_bbox": [40, 40, 560, 80],
                                "block_order": 0,
                            },
                            {
                                "block_label": "text",
                                "block_content": (
                                    "period=2.1 d radius=1.3 R_earth Teff=5200 K"
                                ),
                                "block_bbox": [40, 100, 560, 140],
                                "block_order": 1,
                            },
                        ],
                    }
                }
            ]
        },
    }


def _stub_visual_client() -> object:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/layout-parsing")
        body = json.loads(request.content.decode("ascii"))
        assert isinstance(body["file"], str)
        base64.b64decode(body["file"])  # must be real page bytes
        return httpx.Response(200, json=_stub_layout_parsing_payload())

    from app.services.scientific_document.hybrid_parser import PaddleOcrVlClient

    return PaddleOcrVlClient(
        base_url="http://127.0.0.1:9/vision",
        model_revision="stub-0",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def _run_checker(report_path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "check_scientific_document_benchmark_report.py"),
            str(report_path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": PYTHONPATH},
    )


@pytest.mark.scientific_document_native
def test_native_report_stable_and_passes_checker(tmp_path: Path) -> None:
    from services.scientific_document.benchmark_runner import run_native_only

    first = run_native_only()
    second = run_native_only()
    assert first.output_hash == second.output_hash
    path = tmp_path / "native-report.json"
    path.write_text(first.model_dump_json(), encoding="utf-8")
    result = _run_checker(path)
    assert result.returncode == 0, result.stderr


@pytest.mark.scientific_document_native
def test_hybrid_refuses_to_start_without_configured_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import settings
    from services.scientific_document.benchmark_runner import (
        run_hybrid,
        visual_parser_from_settings,
    )

    monkeypatch.setattr(settings, "PADDLEOCR_VL_BASE_URL", None, raising=False)
    monkeypatch.setattr(
        settings, "PADDLEOCR_VL_MODEL_REVISION", None, raising=False
    )
    with pytest.raises(RuntimeError, match="visual backend"):
        visual_parser_from_settings()
    with pytest.raises(RuntimeError, match="visual backend"):
        run_hybrid()


def _paired_report_with_stub() -> object:
    from services.scientific_document import benchmark_runner

    original = benchmark_runner.visual_parser_from_settings
    benchmark_runner.visual_parser_from_settings = lambda: _stub_visual_client()
    try:
        return benchmark_runner.run_paired()
    finally:
        benchmark_runner.visual_parser_from_settings = original


@pytest.mark.scientific_document_native
def test_paired_report_is_comparable_and_proves_visual_execution(
    tmp_path: Path,
) -> None:
    report = _paired_report_with_stub()
    modes = {case.parser_mode.value for case in report.cases}
    assert modes == {"native_only", "hybrid"}
    by_mode: dict[str, set[str]] = {}
    for case in report.cases:
        by_mode.setdefault(case.parser_mode.value, set()).add(case.entry_id)
    assert by_mode["native_only"] == by_mode["hybrid"]
    hybrid_cases = [
        case
        for case in report.cases
        if case.parser_mode.value == "hybrid"
        and case.failure_category is None
    ]
    assert hybrid_cases, "every hybrid case failed against the stub backend"
    # Visual routing actually happened on stubbed pages and latency is real.
    assert any(case.visual_routing_coverage for case in hybrid_cases)
    assert all(case.latency_seconds is not None for case in report.cases)
    metrics = {metric.name for metric in report.metrics}
    assert "native_only_accepted_rate" in metrics
    assert "hybrid_accepted_rate" in metrics
    assert "hybrid_latency" in metrics
    assert report.visual_model_id is not None

    path = tmp_path / "paired-report.json"
    path.write_text(report.model_dump_json(), encoding="utf-8")
    result = _run_checker(path)
    assert result.returncode == 0, result.stderr


def test_paired_report_without_visual_provenance_fails_closed() -> None:
    report = _paired_report_with_stub()
    payload = json.loads(report.model_dump_json())
    payload["output_hash"] = "sha256:" + "0" * 64
    payload["visual_engine"] = None
    with pytest.raises(ValidationError):
        from app.schemas.scientific_document_benchmark import BenchmarkReport

        BenchmarkReport.model_validate(payload)


def test_paired_report_entry_sets_must_match_across_modes() -> None:
    report = _paired_report_with_stub()
    payload = json.loads(report.model_dump_json())
    payload["output_hash"] = "sha256:" + "0" * 64
    payload["cases"] = [
        case
        for case in payload["cases"]
        if not (
            case["parser_mode"] == "native_only"
            and case["entry_id"] == payload["cases"][0]["entry_id"]
        )
    ]
    with pytest.raises(ValidationError):
        from app.schemas.scientific_document_benchmark import BenchmarkReport

        BenchmarkReport.model_validate(payload)


def test_gpu_claim_without_run_status_rejected() -> None:
    from app.schemas.scientific_document_benchmark import (
        BenchmarkCaseResult,
        BenchmarkParserMode,
    )

    with pytest.raises(ValidationError):
        BenchmarkCaseResult(
            entry_id="gs-x",
            parser_mode=BenchmarkParserMode.hybrid,
            document_parse_id="parse_x",
            overall_quality="accepted",
            gpu_result=True,
            gpu_status="not_run",
            input_hash="sha256:" + "a" * 64,
            output_hash="sha256:" + "b" * 64,
        )


def test_memory_without_basis_rejected() -> None:
    from app.schemas.scientific_document_benchmark import (
        BenchmarkCaseResult,
        BenchmarkParserMode,
    )

    with pytest.raises(ValidationError):
        BenchmarkCaseResult(
            entry_id="gs-x",
            parser_mode=BenchmarkParserMode.native_only,
            document_parse_id="parse_x",
            overall_quality="accepted",
            peak_memory_bytes=1024,
            input_hash="sha256:" + "a" * 64,
            output_hash="sha256:" + "b" * 64,
        )


def test_checker_rejects_unproven_hybrid_latency(tmp_path: Path) -> None:
    from app.schemas.scientific_document_benchmark import (
        BenchmarkCaseResult,
        BenchmarkMetricValue,
        BenchmarkParserMode,
        BenchmarkReport,
        compute_benchmark_report_hash,
    )

    case = BenchmarkCaseResult(
        entry_id="gs-x",
        parser_mode=BenchmarkParserMode.hybrid,
        document_parse_id="parse_x",
        overall_quality="accepted",
        latency_seconds=None,
        input_hash="sha256:" + "a" * 64,
        output_hash="sha256:" + "b" * 64,
    )

    def metric(name: str) -> BenchmarkMetricValue:
        return BenchmarkMetricValue(
            name=name,
            status="measured",
            numerator=1,
            denominator=1,
            rate=1.0,
            version="1.2.0",
        )

    report = BenchmarkReport(
        report_id="r-hybrid",
        schema_version="1.2.0",
        parser_mode=BenchmarkParserMode.hybrid,
        golden_set_manifest_id="m",
        golden_set_version="1.0.0",
        golden_set_content_hash="sha256:" + "c" * 64,
        expected_annotation_hash="sha256:" + "d" * 64,
        native_engine="docling-parse==7.11.0",
        native_engine_version="7.11.0",
        visual_engine="PaddleOCR-VL layout-parsing service",
        visual_engine_version="1.6",
        visual_model_id="PaddleOCR-VL-1.6-0.9B",
        visual_model_revision="stub-0",
        config_hash="sha256:" + "e" * 64,
        metrics=(
            metric("accepted_rate"),
            metric("latency"),
            metric("visual_routing_coverage"),
        ),
        cases=(case,),
        input_hash="sha256:" + "f" * 64,
        output_hash="sha256:" + "0" * 64,
        created_at="2026-08-25T00:00:00Z",
    )
    report = report.model_copy(update={"output_hash": compute_benchmark_report_hash(report)})
    path = tmp_path / "unproven-hybrid.json"
    path.write_text(report.model_dump_json(), encoding="utf-8")
    result = _run_checker(path)
    assert result.returncode == 1
    assert "latency-measured" in result.stderr
