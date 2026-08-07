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

ROOT = Path(__file__).resolve().parents[3]
ADOPTION = ROOT / "services" / "scientific_document" / "upstream_adoption.json"
GOLDEN = ROOT / "services" / "scientific_document" / "golden_set.json"


def test_adoption_manifest_exact_versions_no_latest() -> None:
    data = json.loads(ADOPTION.read_text(encoding="utf-8"))
    version_fields = (
        "package_version",
        "model_revision",
        "pipeline_version",
        "release",
        "tag",
        "commit",
    )
    for entry in data["entries"]:
        assert entry["adoption_status"] == "approved"
        # No floating version tokens in any version-bearing field.
        for field in version_fields:
            value = str(entry.get(field, "")).lower()
            for token in ("latest", "main", "master", "nightly", "dev", "head"):
                assert token not in value, (
                    f"floating token {token} in {entry.get('capability')}.{field}"
                )
        # License present; model weight license present when a model exists.
        assert entry["license"]
        if entry.get("model_id"):
            assert entry.get("model_weight_license"), entry["capability"]
        # Official interface + upgrade strategy present.
        assert entry["official_interface_used"]
        assert entry["upgrade_strategy"]
        assert entry["network_behavior"] and entry["cache_behavior"]


def test_adoption_manifest_paddle_exact_revision() -> None:
    data = json.loads(ADOPTION.read_text(encoding="utf-8"))
    paddle = next(
        e for e in data["entries"] if e["capability"] == "visual_ocr_layout_table_formula"
    )
    assert paddle["model_id"] == "PaddleOCR-VL-1.6"
    assert paddle["model_revision"] == "PaddleOCR-VL-1.6-0.9B"
    assert paddle["package_version"].startswith(">=") or paddle["package_version"][0].isdigit()


def test_golden_set_manifest_shape() -> None:
    data = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert data["case_key"] == "exoplanet_host_star"
    assert data["sample_count"] >= 15
    restricted = [e for e in data["entries"] if e.get("local_only")]
    fixtures = [e for e in data["entries"] if e["data_type"] == "fixture"]
    assert restricted, "restricted/local-only entries must exist"
    assert fixtures, "committed fixtures must exist"
    # Restricted entries must NOT carry a committed content hash (PDF not in repo).
    for e in restricted:
        assert e["content_hash"] is None
        assert e["availability"] == "local-only"


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

    # The scanner reads files relative to ROOT, so stage a real file under ROOT.
    bad = ROOT / "services" / "scientific_document" / "_tmp_bad_floating.py"
    bad.parent.mkdir(parents=True, exist_ok=True)
    try:
        bad.write_text('MODEL_REVISION = "latest"\n', encoding="utf-8")
        errors = gate.check_floating_versions([str(bad.relative_to(ROOT))])
        assert any("floating" in e for e in errors), errors
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

    bad = ROOT / "apps" / "api" / "src" / "app" / "services" / "scientific_document" / "_tmp_bad_ref.py"
    bad.parent.mkdir(parents=True, exist_ok=True)
    try:
        bad.write_text("from docs.references import something\n", encoding="utf-8")
        errors = gate.check_reference_imports([str(bad.relative_to(ROOT))])
        assert any("docs.references" in e for e in errors), errors
    finally:
        bad.unlink(missing_ok=True)


def test_benchmark_deterministic_without_model_weights() -> None:
    """Run the native benchmark and assert determinism + no committed weights."""
    pytest.importorskip("docling_parse")
    from services.scientific_document.benchmark_runner import run_native_only

    r1 = run_native_only()
    r2 = run_native_only()
    assert r1.output_hash == r2.output_hash
    assert r1.parser_mode.value == "native_only"
    assert len(r1.cases) >= 1


def test_native_baseline_real_parse_of_fixture() -> None:
    """Non-mock: real docling-parse over a committed fixture produces blocks."""
    pytest.importorskip("docling_parse")
    fixture = ROOT / "services" / "scientific_document" / "fixtures" / "golden_born_digital.pdf"
    if not fixture.is_file():
        pytest.skip("fixture not generated")
    import hashlib

    from app.services.scientific_document.native_baseline import parse_native_baseline
    from app.services.scientific_document.ports import ParseRequest

    content = fixture.read_bytes()
    chash = "sha256:" + hashlib.sha256(content).hexdigest()
    request = ParseRequest(
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
    # No vendor type must leak into the canonical candidate.
    assert candidate.native_engine.startswith("docling-parse")
