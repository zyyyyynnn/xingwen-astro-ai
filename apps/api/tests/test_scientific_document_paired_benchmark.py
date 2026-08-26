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


def _run_checker(
    report_path: Path, *, require_local_bundle: bool = False
) -> subprocess.CompletedProcess[str]:
    command = [
        sys.executable,
        str(ROOT / "scripts" / "check_scientific_document_benchmark_report.py"),
        str(report_path),
    ]
    if require_local_bundle:
        command.append("--require-local-bundle")
    return subprocess.run(
        command,
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
    monkeypatch.setattr(settings, "PADDLEOCR_VL_MODEL_REVISION", None, raising=False)
    monkeypatch.setattr(settings, "PADDLEOCR_VL_LOCAL_BUNDLE", None, raising=False)
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
        if case.parser_mode.value == "hybrid" and case.failure_category is None
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
    local_proof = _run_checker(path, require_local_bundle=True)
    assert local_proof.returncode == 1
    assert "verified local Paddle bundle" in local_proof.stderr


def test_checker_rejects_report_with_missing_current_fixture(tmp_path: Path) -> None:
    from app.schemas.scientific_document_benchmark import (
        compute_benchmark_report_hash,
    )

    report = _paired_report_with_stub()
    omitted_entry_id = report.cases[-1].entry_id
    remaining_cases = tuple(
        case for case in report.cases if case.entry_id != omitted_entry_id
    )
    report = report.model_copy(
        update={"cases": remaining_cases, "output_hash": "sha256:" + "0" * 64}
    )
    report = report.model_copy(
        update={"output_hash": compute_benchmark_report_hash(report)}
    )
    path = tmp_path / "missing-fixture.json"
    path.write_text(report.model_dump_json(), encoding="utf-8")

    checked = _run_checker(path)

    assert checked.returncode == 1
    assert "case/mode set" in checked.stderr


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


def test_missing_memory_measurement_is_not_reported_as_zero() -> None:
    from app.schemas.scientific_document_benchmark import (
        BenchmarkCaseResult,
        BenchmarkMetricStatus,
        BenchmarkParserMode,
    )
    from services.scientific_document.benchmark_runner import _mode_quality_metrics

    case = BenchmarkCaseResult(
        entry_id="gs-x",
        parser_mode=BenchmarkParserMode.native_only,
        document_parse_id="parse_x",
        overall_quality="accepted",
        latency_seconds=0.1,
        input_hash="sha256:" + "a" * 64,
        output_hash="sha256:" + "b" * 64,
    )

    metrics = {metric.name: metric for metric in _mode_quality_metrics("", [case])}

    assert metrics["peak_memory"].status is BenchmarkMetricStatus.not_run
    assert metrics["peak_memory"].rate is None


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
        visual_runtime_binding_hash="sha256:" + "f" * 64,
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
    report = report.model_copy(
        update={"output_hash": compute_benchmark_report_hash(report)}
    )
    path = tmp_path / "unproven-hybrid.json"
    path.write_text(report.model_dump_json(), encoding="utf-8")
    result = _run_checker(path)
    assert result.returncode == 1
    assert "latency-measured" in result.stderr


def test_checker_rejects_hybrid_without_successful_visual_routing(
    tmp_path: Path,
) -> None:
    from app.schemas.scientific_document_benchmark import (
        BenchmarkParserMode,
        compute_benchmark_report_hash,
    )

    report = _paired_report_with_stub()
    cases = tuple(
        case.model_copy(update={"visual_routing_coverage": 0.0})
        if case.parser_mode == BenchmarkParserMode.hybrid
        else case
        for case in report.cases
    )
    report = report.model_copy(
        update={"cases": cases, "output_hash": "sha256:" + "0" * 64}
    )
    report = report.model_copy(
        update={"output_hash": compute_benchmark_report_hash(report)}
    )
    path = tmp_path / "hybrid-without-routing.json"
    path.write_text(report.model_dump_json(), encoding="utf-8")

    result = _run_checker(path)

    assert result.returncode == 1
    assert "successful visual routing" in result.stderr


def test_checker_rejects_pending_output_hash(tmp_path: Path) -> None:
    report = _paired_report_with_stub().model_copy(
        update={"output_hash": "sha256:" + "0" * 64}
    )
    path = tmp_path / "pending-output-hash.json"
    path.write_text(report.model_dump_json(), encoding="utf-8")

    result = _run_checker(path)

    assert result.returncode == 1
    assert "output_hash is still pending" in result.stderr


def test_local_bundle_backend_refuses_unverified_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unverified/absent bundle must fail closed before any vendor import."""
    from app.config import settings
    from services.scientific_document.benchmark_runner import (
        visual_parser_from_settings,
    )

    monkeypatch.setattr(settings, "PADDLEOCR_VL_BASE_URL", None, raising=False)
    monkeypatch.setattr(settings, "PADDLEOCR_VL_MODEL_REVISION", None, raising=False)
    monkeypatch.setattr(settings, "PADDLEOCR_VL_LOCAL_BUNDLE", str(tmp_path))
    with pytest.raises(RuntimeError):
        visual_parser_from_settings()


def test_local_bundle_backend_wiring(monkeypatch: pytest.MonkeyPatch) -> None:
    """Settings routing selects the in-process pipeline backend unchanged."""
    import app.services.scientific_document.local_paddle_pipeline as local_mod
    from app.config import settings
    from services.scientific_document.benchmark_runner import (
        visual_parser_from_settings,
    )

    class _Dummy:
        def __init__(self, *, bundle_root) -> None:
            self.bundle_root = bundle_root

        def engine_version(self):  # pragma: no cover - property protocol only
            raise AssertionError

    monkeypatch.setattr(settings, "PADDLEOCR_VL_BASE_URL", None, raising=False)
    monkeypatch.setattr(settings, "PADDLEOCR_VL_MODEL_REVISION", None, raising=False)
    monkeypatch.setattr(settings, "PADDLEOCR_VL_LOCAL_BUNDLE", "bundle-x")
    monkeypatch.setattr(local_mod, "LocalPaddleOcrVlPipeline", _Dummy)
    parser = visual_parser_from_settings()
    assert isinstance(parser, _Dummy)


@pytest.mark.scientific_document_native
def test_real_local_pipeline_constructs_against_verified_bundle() -> None:
    """Operator-local proof path: construct the official pipeline against a
    verified bundle when the approved runtime AND provisioned bundle exist;
    otherwise skip silently so public CI stays deterministic."""
    import importlib.util

    if importlib.util.find_spec("paddleocr") is None:
        pytest.skip("approved paddleocr runtime not installed")
    bundle = ROOT / "models"
    if not (bundle / "vlm_recognition").is_dir():
        pytest.skip("operator bundle not provisioned")

    from app.services.scientific_document.local_paddle_pipeline import (
        LocalPaddleOcrVlPipeline,
    )

    pipeline = LocalPaddleOcrVlPipeline(bundle_root=bundle)
    assert pipeline.model_revision.startswith("cdc88f5f")
    assert pipeline.engine_version == "1.6"


def test_local_pipeline_projects_official_layout_block_objects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The in-process API returns LayoutBlock objects, not HTTP-shaped dicts."""
    from io import BytesIO
    import sys
    from types import SimpleNamespace

    from PIL import Image

    from app.services.scientific_document.local_paddle_pipeline import (
        LocalPaddleOcrVlPipeline,
    )

    class _Engine:
        def predict(self, _array, **kwargs):
            assert kwargs["format_block_content"] is True
            return [
                {
                    "width": 200,
                    "height": 100,
                    "parsing_res_list": [
                        SimpleNamespace(
                            label="table",
                            content="| TOI | Teff [K] |\n| --- | --- |\n| 101.01 | 5200 |",
                            bbox=[10, 20, 190, 90],
                            order_index=2,
                        )
                    ],
                }
            ]

    image = Image.new("RGB", (200, 100), "white")
    encoded = BytesIO()
    image.save(encoded, format="PNG")
    monkeypatch.setitem(
        sys.modules,
        "cv2",
        SimpleNamespace(
            IMREAD_COLOR=1,
            imdecode=lambda _buffer, _mode: object(),
        ),
    )
    pipeline = object.__new__(LocalPaddleOcrVlPipeline)
    pipeline._engine = _Engine()

    result = pipeline.parse_page(encoded.getvalue())

    assert len(result.blocks) == 1
    assert result.blocks[0].label == "table"
    assert result.blocks[0].content == (
        "| TOI | Teff [K] |\n| --- | --- |\n| 101.01 | 5200 |"
    )
    assert result.blocks[0].bbox == (10.0, 20.0, 190.0, 90.0)
    assert result.blocks[0].order == 2


def test_visual_projection_rejects_oversized_block_lists_before_projection() -> None:
    from app.services.scientific_document.hybrid_parser import (
        VisualParseError,
        project_visual_page_result,
    )

    with pytest.raises(VisualParseError, match="block budget"):
        project_visual_page_result(
            width=200,
            height=100,
            raw_blocks=[object()] * 4097,
        )


def test_visual_projection_rejects_oversized_block_content() -> None:
    from app.services.scientific_document.hybrid_parser import (
        VisualParseError,
        project_visual_page_result,
    )

    with pytest.raises(VisualParseError, match="character budget"):
        project_visual_page_result(
            width=200,
            height=100,
            raw_blocks=[
                {
                    "block_label": "text",
                    "block_content": "x" * (4 * 1024 * 1024 + 1),
                    "block_bbox": [0, 0, 200, 100],
                    "block_order": 0,
                }
            ],
        )


def test_official_html_table_projects_to_canonical_cells() -> None:
    from app.services.scientific_document.hybrid_parser import (
        VisualPageBlock,
        VisualPageResult,
        _canonical_visual_page,
    )

    _blocks, tables, _formulas, _figures = _canonical_visual_page(
        VisualPageResult(
            width_pixels=200,
            height_pixels=100,
            blocks=(
                VisualPageBlock(
                    label="table",
                    content=(
                        "<table><tr><td>TOI</td><td>Teff [K]</td></tr>"
                        "<tr><td>101.01</td><td>5200</td></tr></table>"
                    ),
                    bbox=(10.0, 20.0, 190.0, 90.0),
                    order=0,
                ),
            ),
        ),
        page_index=1,
        page_width=200.0,
        page_height=100.0,
        profile_id="hybrid-default",
    )

    assert len(tables) == 1
    assert tables[0].quality.value == "accepted"
    assert [[cell.text for cell in row] for row in tables[0].rows] == [
        ["TOI", "Teff [K]"],
        ["101.01", "5200"],
    ]
    assert all(cell.bbox is None for row in tables[0].rows for cell in row)
    assert _blocks[0].bbox is not None


def test_official_html_table_rejects_unbounded_span_before_projection() -> None:
    from app.services.scientific_document.hybrid_parser import (
        VisualPageBlock,
        VisualPageResult,
        VisualParseError,
        _canonical_visual_page,
    )

    with pytest.raises(VisualParseError, match="span exceeds"):
        _canonical_visual_page(
            VisualPageResult(
                width_pixels=200,
                height_pixels=100,
                blocks=(
                    VisualPageBlock(
                        label="table",
                        content='<table><tr><td colspan="1000000000">x</td></tr></table>',
                        bbox=(10.0, 20.0, 190.0, 90.0),
                        order=0,
                    ),
                ),
            ),
            page_index=1,
            page_width=200.0,
            page_height=100.0,
            profile_id="hybrid-default",
        )


@pytest.mark.parametrize(
    "report_name,expected_mode",
    (
        ("real-paddle-cpu-hybrid.json", "hybrid"),
        ("real-paddle-cpu-paired.json", "paired"),
    ),
)
def test_committed_real_paddle_machine_evidence_passes_checker(
    report_name: str,
    expected_mode: str,
) -> None:
    report_path = ROOT / "services/scientific_document/evidence" / report_name
    assert report_path.is_file(), f"missing exact-head machine evidence: {report_path}"

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["parser_mode"] == expected_mode
    assert payload["golden_set_manifest_id"] == "scientific_document-golden-set"
    assert payload["visual_model_id"] == "PaddleOCR-VL-1.6-0.9B"
    assert payload["visual_model_revision"]
    assert payload["visual_runtime_binding_hash"].startswith("sha256:")
    assert payload["config_hash"].startswith("sha256:")
    assert payload["input_hash"].startswith("sha256:")
    assert payload["output_hash"].startswith("sha256:")
    assert all(case["latency_seconds"] >= 0 for case in payload["cases"])
    assert any(
        case["failure_category"] is None and case["visual_routing_coverage"] > 0
        for case in payload["cases"]
        if case["parser_mode"] == "hybrid"
    )

    checked = _run_checker(report_path, require_local_bundle=True)
    assert checked.returncode == 0, checked.stderr


def test_paired_double_run_identity_ignores_volatile_metrics() -> None:
    """Paired identity must stay stable across runs despite real cost noise.

    Mode-prefixed cost metrics (``native_only_latency`` / ``hybrid_peak_memory``)
    are volatile observations, never identity: they are excluded exactly like
    the bare native-report names.
    """
    from app.schemas.scientific_document_benchmark import (
        benchmark_payload_for_hash,
    )

    first = _paired_report_with_stub()
    second = _paired_report_with_stub()
    assert first.output_hash == second.output_hash

    names = {metric["name"] for metric in benchmark_payload_for_hash(first)["metrics"]}
    assert any(name.startswith("native_only_") for name in names)
    assert not any(
        name == tail or name.endswith(f"_{tail}")
        for name in names
        for tail in ("latency", "peak_memory")
    )
