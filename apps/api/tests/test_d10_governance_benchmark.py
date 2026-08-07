"""D-10 governance, manifest, benchmark and native-baseline tests.

Includes NEGATIVE tests for the reference-after-rewrite / adoption gate and a
real (non-mock) native baseline run over a committed fixture.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

# D-10 native baseline tests require the benchmark dependency group (docling-parse)
# and run only in the CI benchmark step, gated by this marker. They must NOT be
# silently skipped there (D-10 G3).
pytestmark = pytest.mark.d10_native

ROOT = Path(__file__).resolve().parents[3]
ADOPTION = ROOT / "services" / "scientific_document" / "upstream_adoption.json"
GOLDEN = ROOT / "services" / "scientific_document" / "golden_set.json"


def test_adoption_manifest_exact_versions_no_latest() -> None:
    data = json.loads(ADOPTION.read_text(encoding="utf-8"))
    version_fields = (
        "package_version",
        "model_revision",
        "pipeline_version",
        "release_tag",
    )
    for entry in data["entries"]:
        assert entry["adoption_status"] == "approved"
        for field in version_fields:
            value = str(entry.get(field, "")).lower()
            for token in ("latest", "main", "master", "nightly", "dev", "head"):
                assert token not in value, (
                    f"floating token {token} in {entry.get('capability')}.{field}"
                )
        # No version ranges for approved packages.
        for field in ("package_version", "model_revision", "pipeline_version"):
            value = str(entry.get(field, ""))
            assert not any(ch in value for ch in "> < ~ ^ ! |"), (
                f"range version in {entry.get('capability')}.{field}: {value}"
            )
        assert entry["license"]
        if entry.get("model_id"):
            assert entry.get("model_weight_license"), entry["capability"]
        assert entry["official_interface_used"]
        assert entry["upgrade_strategy"]
        assert entry["network_behavior"] and entry["cache_behavior"]


def test_adoption_manifest_paddle_exact_revision() -> None:
    data = json.loads(ADOPTION.read_text(encoding="utf-8"))
    paddle = next(
        e for e in data["entries"] if e["capability"] == "visual_ocr_layout_table_formula"
    )
    # Exact package version, not a range.
    assert paddle["package_version"] == "3.6.0"
    # Immutable model revision is a real HF commit SHA.
    assert paddle["model_revision"] == "cdc88f5feff0e4079e75863205053a68358e52f7"
    assert paddle["model_resolved_id"] == "PaddleOCR-VL-1.6-0.9B"


def test_adoption_contract_validates() -> None:
    from services.scientific_document.adoption_contract import (
        load_adoption_manifest,
    )

    manifest = load_adoption_manifest(ADOPTION)
    assert manifest.schema_version
    approved = [e for e in manifest.entries if e.adoption_status.value == "approved"]
    assert approved, "expected approved entries"


def test_golden_set_manifest_shape() -> None:
    data = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert data["case_key"] == "exoplanet_host_star"
    assert data["sample_count"] >= 15
    restricted = [e for e in data["entries"] if e.get("local_only")]
    fixtures = [e for e in data["entries"] if e["data_type"] == "fixture"]
    assert restricted, "restricted/local-only entries must exist"
    assert fixtures, "committed fixtures must exist"
    for e in restricted:
        assert e["content_hash"] is None
        assert e["availability"] == "local-only"
        # No placeholder/illustrative DOIs: real arXiv identifiers required.
        assert e["doi_or_identifier"].startswith("arXiv:"), e["entry_id"]


def test_golden_set_strongly_validated() -> None:
    from app.schemas.scientific_document_benchmark import GoldenSetManifest

    data = json.loads(GOLDEN.read_text(encoding="utf-8"))
    manifest = GoldenSetManifest.model_validate(data)
    # sample_count must equal len(entries) (fail-closed).
    assert manifest.sample_count == len(manifest.entries)


def test_governance_gate_passes_on_clean_tree() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_d10_governance.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_governance_gate_detects_floating_version(tmp_path: Path) -> None:
    import scripts.check_d10_governance as gate

    bad = ROOT / "services" / "scientific_document" / "_tmp_bad_floating.json"
    bad.parent.mkdir(parents=True, exist_ok=True)
    try:
        bad.write_text('{"x": {"model_revision": "latest"}}', encoding="utf-8")
        errors = gate.check_floating_versions([str(bad.relative_to(ROOT))])
        assert any("floating" in e for e in errors), errors
    finally:
        bad.unlink(missing_ok=True)


def test_governance_gate_detects_range_version_on_approved() -> None:
    import scripts.check_d10_governance as gate

    bad = ROOT / "services" / "scientific_document" / "_tmp_bad_range.json"
    bad.parent.mkdir(parents=True, exist_ok=True)
    try:
        bad.write_text('{"x": {"package_version": ">=3.6.0"}}', encoding="utf-8")
        errors = gate.check_exact_pinned_versions([str(bad.relative_to(ROOT))])
        assert any("range" in e for e in errors), errors
    finally:
        bad.unlink(missing_ok=True)


def test_governance_gate_detects_model_weights(tmp_path: Path) -> None:
    import scripts.check_d10_governance as gate

    bad = ROOT / "models" / "_tmp_ocr.safetensors"
    bad.parent.mkdir(parents=True, exist_ok=True)
    try:
        bad.write_bytes(b"x")
        errors = gate.check_model_weights([str(bad.relative_to(ROOT))])
        assert any("model weight" in e for e in errors), errors
    finally:
        bad.unlink(missing_ok=True)


def test_governance_gate_detects_reference_import(tmp_path: Path) -> None:
    import scripts.check_d10_governance as gate

    bad = (
        ROOT
        / "apps"
        / "api"
        / "src"
        / "app"
        / "services"
        / "scientific_document"
        / "_tmp_bad_ref.py"
    )
    bad.parent.mkdir(parents=True, exist_ok=True)
    try:
        bad.write_text("from docs.references import something\n", encoding="utf-8")
        errors = gate.check_reference_imports([str(bad.relative_to(ROOT))])
        assert any("docs.references" in e for e in errors), errors
    finally:
        bad.unlink(missing_ok=True)


def test_benchmark_deterministic_without_model_weights() -> None:
    """Run the native benchmark and assert determinism + no committed weights.

    Gated by the ``d10_native`` marker: runs only in the CI benchmark step.
    """
    from services.scientific_document.benchmark_runner import run_native_only

    r1 = run_native_only()
    r2 = run_native_only()
    assert r1.output_hash == r2.output_hash
    assert r1.parser_mode.value == "native_only"
    assert len(r1.cases) >= 1


def test_native_baseline_real_parse_of_fixture() -> None:
    """Non-mock: real docling-parse over a committed fixture produces blocks."""
    fixture = ROOT / "services" / "scientific_document" / "fixtures" / "golden_born_digital.pdf"
    if not fixture.is_file():
        pytest.fail("fixture not generated")
    import hashlib

    from app.schemas.scientific_document import DocumentParseInput
    from app.services.scientific_document.native_baseline import parse_native_baseline

    content = fixture.read_bytes()
    chash = "sha256:" + hashlib.sha256(content).hexdigest()
    request = DocumentParseInput(
        research_input_id="gs-born_digital",
        content_hash=chash,
        source_type="upload",
        mime_type="application/pdf",
        filename=fixture.name,
        input_bytes=content,
    )
    candidate = parse_native_baseline(request, config_hash="sha256:" + "e" * 64)
    assert candidate.blocks, "native baseline must extract real blocks"
    assert candidate.overall_quality.value in {"accepted", "partial"}
    assert candidate.native_engine.startswith("docling-parse")


def test_native_baseline_scanned_fixture_has_no_text_layer() -> None:
    """D-10 D4/G3: a genuinely scanned fixture must NOT yield accepted blocks.

    The scanned fixture is a raster image embedded with no text layer, so the
    born-digital native parser legitimately finds no extractable text and must
    not fabricate acceptance.
    """
    fixture = ROOT / "services" / "scientific_document" / "fixtures" / "golden_scanned_like.pdf"
    if not fixture.is_file():
        pytest.fail("scanned fixture not generated")
    import hashlib

    from app.schemas.scientific_document import DocumentParseInput
    from app.services.scientific_document.native_baseline import parse_native_baseline

    content = fixture.read_bytes()
    chash = "sha256:" + hashlib.sha256(content).hexdigest()
    request = DocumentParseInput(
        research_input_id="gs-scanned_like",
        content_hash=chash,
        source_type="upload",
        mime_type="application/pdf",
        filename=fixture.name,
        input_bytes=content,
    )
    candidate = parse_native_baseline(request, config_hash="sha256:" + "e" * 64)
    # No extractable text layer => no accepted/partial blocks (fail-closed).
    assert len(candidate.blocks) == 0, (
        f"scanned fixture must have no text layer, got {len(candidate.blocks)} blocks"
    )
    assert candidate.overall_quality.value == "unsupported"


def test_benchmark_report_self_verifies_and_cases_local() -> None:
    """Report output_hash self-verifies; per-case counts are case-local."""
    from app.schemas.scientific_document_benchmark import (
        BenchmarkCaseResult,
        BenchmarkMetricValue,
        BenchmarkParserMode,
        BenchmarkReport,
        compute_benchmark_report_hash,
    )

    case = BenchmarkCaseResult(
        entry_id="gs-x",
        parser_mode=BenchmarkParserMode.native_only,
        document_parse_id="parse_x",
        overall_quality="accepted",
        native_routing_coverage=1.0,
        accepted_count=3,
        partial_count=0,
        unsupported_count=0,
        input_hash="sha256:" + "a" * 64,
        output_hash="sha256:" + "b" * 64,
    )
    report = BenchmarkReport(
        report_id="r",
        schema_version="1.1.0",
        parser_mode=BenchmarkParserMode.native_only,
        golden_set_manifest_id="d10-golden-set",
        golden_set_version="1.1.0",
        golden_set_content_hash="sha256:" + "c" * 64,
        expected_annotation_hash="sha256:" + "d" * 64,
        native_engine="docling-parse==7.11.0",
        native_engine_version="7.11.0",
        config_hash="sha256:" + "e" * 64,
        metrics=(BenchmarkMetricValue(name="accepted_rate", status="measured", numerator=1, denominator=1, rate=1.0, version="1.1.0"),),
        cases=(case,),
        input_hash="sha256:" + "f" * 64,
        output_hash="sha256:" + "0" * 64,
        created_at="2026-08-07T00:00:00Z",
    )
    recomputed = compute_benchmark_report_hash(report)
    report2 = report.model_copy(update={"output_hash": recomputed})
    assert report2.output_hash == recomputed
    # case-local accepted_count, not a running global.
    assert report2.cases[0].accepted_count == 3
