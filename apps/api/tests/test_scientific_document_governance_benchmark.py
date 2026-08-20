"""Scientific Document Parsing Contract governance, adoption, Golden Set and benchmark tests."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[3]
ADOPTION = ROOT / "services" / "scientific_document" / "upstream_adoption.json"
GOLDEN = ROOT / "services" / "scientific_document" / "golden_set.json"


def test_local_only_unhashed_entry_cannot_claim_pdf_page_ground_truth() -> None:
    from app.schemas.scientific_document_benchmark import (
        GoldenExpectedAnnotation,
        GoldenSetEntry,
    )

    with pytest.raises(ValidationError):
        GoldenSetEntry(
            entry_id="gs-local",
            case_key="exoplanet_host_star",
            title="Local paper",
            data_type="golden",
            source="restricted-publication",
            doi_or_identifier="arXiv:0000.00000",
            license_note="local-only exact bytes not verified",
            content_hash=None,
            availability="local-only",
            local_only=True,
            expected=GoldenExpectedAnnotation(expected_page_count=7),
        )


def test_committed_golden_manifest_has_no_unverified_page_counts() -> None:
    from app.schemas.scientific_document_benchmark import GoldenSetManifest

    manifest = GoldenSetManifest.model_validate_json(GOLDEN.read_text(encoding="utf-8"))
    for entry in manifest.entries:
        if (
            entry.local_only
            and entry.content_hash is None
            and entry.expected is not None
        ):
            assert entry.expected.expected_page_count is None


def test_golden_builder_and_committed_manifest_are_semantically_aligned() -> None:
    from app.schemas.scientific_document_benchmark import GoldenSetManifest
    from services.scientific_document.build_golden_manifest import build_manifest

    committed = GoldenSetManifest.model_validate_json(
        GOLDEN.read_text(encoding="utf-8")
    )
    rebuilt = build_manifest()
    assert rebuilt.manifest_id == committed.manifest_id
    assert rebuilt.version == committed.version
    assert rebuilt.sample_count == committed.sample_count
    assert rebuilt.entries == committed.entries


def test_metric_rate_must_match_numerator_denominator() -> None:
    from app.schemas.scientific_document_benchmark import (
        BenchmarkMetricStatus,
        BenchmarkMetricValue,
    )

    with pytest.raises(ValidationError):
        BenchmarkMetricValue(
            name="accepted_rate",
            status=BenchmarkMetricStatus.measured,
            numerator=1,
            denominator=2,
            rate=0.9,
            version="1.1.0",
        )

    metric = BenchmarkMetricValue(
        name="accepted_rate",
        status=BenchmarkMetricStatus.measured,
        numerator=1,
        denominator=2,
        rate=0.5,
        version="1.1.0",
    )
    assert metric.rate == 0.5


def test_unmeasured_metric_cannot_smuggle_numeric_result() -> None:
    from app.schemas.scientific_document_benchmark import (
        BenchmarkMetricStatus,
        BenchmarkMetricValue,
    )

    with pytest.raises(ValidationError):
        BenchmarkMetricValue(
            name="formula_recovery",
            status=BenchmarkMetricStatus.unsupported,
            numerator=1,
            denominator=1,
            rate=1.0,
            version="1.1.0",
        )


def test_adoption_manifest_exact_versions_no_latest() -> None:
    data = json.loads(ADOPTION.read_text(encoding="utf-8"))
    version_fields = (
        "package_version",
        "model_revision",
        "pipeline_version",
        "release_tag",
        "paddlex_version",
        "provisioning_version",
    )
    range_chars = (">", "<", "~", "^", "!", "|")
    for entry in data["entries"]:
        assert entry["adoption_status"] == "approved"
        for field in version_fields:
            value = str(entry.get(field, "")).lower()
            for token in ("latest", "main", "master", "nightly", "dev", "head"):
                assert token not in value, (
                    f"floating token {token} in {entry.get('capability')}.{field}"
                )
        for field in version_fields:
            value = str(entry.get(field, ""))
            assert not any(char in value for char in range_chars), (
                f"range version in {entry.get('capability')}.{field}: {value}"
            )
        assert entry["license"]
        if entry.get("model_repository"):
            assert entry.get("model_weight_license"), entry["capability"]
            assert entry.get("model_revision"), entry["capability"]
        assert entry["official_interface_used"]
        assert entry["upgrade_strategy"]
        assert entry["network_behavior"] and entry["cache_behavior"]


def test_adoption_manifest_paddle_exact_revision() -> None:
    data = json.loads(ADOPTION.read_text(encoding="utf-8"))
    paddle = next(
        entry
        for entry in data["entries"]
        if entry["capability"] == "visual_ocr_layout_table_formula"
    )
    assert paddle["package_version"] == "3.6.0"
    assert paddle.get("model_revision") is None
    assets = json.loads(
        (ADOPTION.parent / paddle["model_asset_manifest"]).read_text(encoding="utf-8")
    )
    components = {component["role"]: component for component in assets["components"]}
    assert components["vlm_recognition"]["revision"] == (
        "cdc88f5feff0e4079e75863205053a68358e52f7"
    )
    assert components["vlm_recognition"]["resolved_model_id"] == (
        "PaddleOCR-VL-1.6-0.9B"
    )
    assert components["layout_detection"]["resolved_model_id"] == "PP-DocLayoutV3"


def test_benchmark_contract_preserves_hybrid_shape_without_claiming_execution() -> None:
    from app.schemas.scientific_document_benchmark import (
        BenchmarkCaseResult,
        BenchmarkParserMode,
        BenchmarkReport,
    )

    assert BenchmarkParserMode.hybrid.value == "hybrid"
    assert "visual_routing_coverage" in BenchmarkCaseResult.model_fields
    assert {
        "visual_engine",
        "visual_engine_version",
        "visual_model_id",
        "visual_model_revision",
    } <= set(BenchmarkReport.model_fields)


def test_adoption_contract_validates_and_only_approved_is_consumable() -> None:
    from services.scientific_document.adoption_contract import (
        AdoptionStatus,
        load_adoption_manifest,
    )

    manifest = load_adoption_manifest(ADOPTION)
    assert manifest.schema_version
    assert manifest.consumable_statuses == (AdoptionStatus.approved,)
    assert set(manifest.allowed_statuses) == set(AdoptionStatus)
    assert all(
        entry.adoption_status == AdoptionStatus.approved for entry in manifest.entries
    )


def test_native_parser_identity_matches_adoption_manifest() -> None:
    data = json.loads(ADOPTION.read_text(encoding="utf-8"))
    native = next(
        entry
        for entry in data["entries"]
        if entry["capability"] == "native_born_digital_pdf"
    )
    from app.services.scientific_document.hybrid_parser import native_engine_identity

    engine, version = native_engine_identity()
    assert version == native["package_version"]
    assert engine == f"{native['package']}=={native['package_version']}"


def test_golden_set_manifest_shape() -> None:
    data = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert data["case_key"] == "exoplanet_host_star"
    assert data["sample_count"] >= 15
    restricted = [entry for entry in data["entries"] if entry.get("local_only")]
    fixtures = [entry for entry in data["entries"] if entry["data_type"] == "fixture"]
    assert restricted, "restricted/local-only entries must exist"
    assert fixtures, "committed fixtures must exist"
    for entry in restricted:
        assert entry["content_hash"] is None
        assert entry["availability"] == "local-only"
        assert entry["doi_or_identifier"].startswith("arXiv:"), entry["entry_id"]


def test_golden_set_strongly_validated() -> None:
    from app.schemas.scientific_document_benchmark import GoldenSetManifest

    data = json.loads(GOLDEN.read_text(encoding="utf-8"))
    manifest = GoldenSetManifest.model_validate(data)
    assert manifest.sample_count == len(manifest.entries)
    assert len({entry.entry_id for entry in manifest.entries}) == len(manifest.entries)


def test_golden_manifest_hash_covers_entries() -> None:
    from app.schemas.scientific_document_benchmark import GoldenSetManifest
    from services.scientific_document.benchmark_runner import _manifest_content_hash

    manifest = GoldenSetManifest.model_validate_json(GOLDEN.read_text(encoding="utf-8"))
    original = _manifest_content_hash(manifest)
    first = manifest.entries[0]
    changed_first = first.model_copy(
        update={"license_note": first.license_note + " changed"}
    )
    changed = manifest.model_copy(
        update={"entries": (changed_first, *manifest.entries[1:])}
    )
    assert _manifest_content_hash(changed) != original


def test_governance_gate_passes_on_clean_tree() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "check_scientific_document_governance.py"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_governance_gate_detects_floating_version() -> None:
    import scripts.check_scientific_document_governance as gate

    bad = ROOT / "services" / "scientific_document" / "_tmp_bad_floating.json"
    try:
        bad.write_text('{"x": {"model_revision": "latest"}}', encoding="utf-8")
        errors = gate.check_floating_versions([str(bad.relative_to(ROOT))])
        assert any("floating" in error for error in errors), errors
    finally:
        bad.unlink(missing_ok=True)


def test_governance_gate_detects_range_version_on_approved() -> None:
    import scripts.check_scientific_document_governance as gate

    bad = ROOT / "services" / "scientific_document" / "_tmp_bad_range.json"
    try:
        bad.write_text('{"x": {"package_version": ">=3.6.0"}}', encoding="utf-8")
        errors = gate.check_exact_pinned_versions([str(bad.relative_to(ROOT))])
        assert any("range" in error for error in errors), errors
    finally:
        bad.unlink(missing_ok=True)


def test_governance_gate_detects_model_weights() -> None:
    import scripts.check_scientific_document_governance as gate

    bad = ROOT / "models" / "_tmp_ocr.safetensors"
    bad.parent.mkdir(parents=True, exist_ok=True)
    try:
        bad.write_bytes(b"x")
        errors = gate.check_model_weights([str(bad.relative_to(ROOT))])
        assert any("model weight" in error for error in errors), errors
    finally:
        bad.unlink(missing_ok=True)


def test_governance_gate_detects_from_reference_import() -> None:
    import scripts.check_scientific_document_governance as gate

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
    try:
        bad.write_text("from docs.references import something\n", encoding="utf-8")
        errors = gate.check_reference_imports([str(bad.relative_to(ROOT))])
        assert any("docs.references" in error for error in errors), errors
    finally:
        bad.unlink(missing_ok=True)


def test_governance_gate_detects_direct_reference_import() -> None:
    import scripts.check_scientific_document_governance as gate

    bad = (
        ROOT
        / "apps"
        / "api"
        / "src"
        / "app"
        / "services"
        / "scientific_document"
        / "_tmp_bad_direct_ref.py"
    )
    try:
        bad.write_text("import docs.references.some_parser\n", encoding="utf-8")
        errors = gate.check_reference_imports([str(bad.relative_to(ROOT))])
        assert any("docs.references" in error for error in errors), errors
    finally:
        bad.unlink(missing_ok=True)


def test_benchmark_report_self_verifies_and_cases_local() -> None:
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
        golden_set_manifest_id="scientific_document-golden-set",
        golden_set_version="1.1.0",
        golden_set_content_hash="sha256:" + "c" * 64,
        expected_annotation_hash="sha256:" + "d" * 64,
        native_engine="docling-parse==7.11.0",
        native_engine_version="7.11.0",
        config_hash="sha256:" + "e" * 64,
        metrics=(
            BenchmarkMetricValue(
                name="accepted_rate",
                status="measured",
                numerator=1,
                denominator=1,
                rate=1.0,
                version="1.1.0",
            ),
        ),
        cases=(case,),
        input_hash="sha256:" + "f" * 64,
        output_hash="sha256:" + "0" * 64,
        created_at="2026-08-07T00:00:00Z",
    )
    recomputed = compute_benchmark_report_hash(report)
    report2 = report.model_copy(update={"output_hash": recomputed})
    assert report2.output_hash == recomputed
    assert report2.cases[0].accepted_count == 3


@pytest.mark.scientific_document_native
def test_benchmark_deterministic_without_model_weights() -> None:
    from services.scientific_document.benchmark_runner import run_native_only

    first = run_native_only()
    second = run_native_only()
    assert first.output_hash == second.output_hash
    assert first.input_hash == second.input_hash
    assert first.parser_mode.value == "native_only"
    assert len(first.cases) >= 1


@pytest.mark.scientific_document_native
def test_native_benchmark_reports_truthful_metric_statuses() -> None:
    from services.scientific_document.benchmark_runner import run_native_only

    report = run_native_only()
    metrics = {metric.name: metric for metric in report.metrics}
    assert metrics["block_recovery"].status.value in {"measured", "not_run"}
    assert metrics["reading_order_error"].status.value == "not_run"
    assert metrics["table_structure_recovery"].status.value == "unsupported"
    assert metrics["formula_recovery"].status.value == "unsupported"
    assert metrics["figure_caption_linkage"].status.value == "unsupported"
    assert metrics["latency"].status.value == "not_run"
    assert metrics["peak_memory"].status.value == "not_run"


@pytest.mark.scientific_document_native
def test_native_parser_real_parse_of_fixture() -> None:
    fixture = (
        ROOT
        / "services"
        / "scientific_document"
        / "fixtures"
        / "golden_born_digital.pdf"
    )
    assert fixture.is_file(), "fixture not generated"
    import hashlib

    from app.schemas.scientific_document import DocumentParseInput
    from app.services.scientific_document.hybrid_parser import (
        HybridScientificDocumentParser,
    )

    content = fixture.read_bytes()
    content_hash = "sha256:" + hashlib.sha256(content).hexdigest()
    request = DocumentParseInput(
        research_input_id="gs-born_digital",
        content_hash=content_hash,
        source_type="upload",
        mime_type="application/pdf",
        filename=fixture.name,
        input_bytes=content,
    )
    candidate = HybridScientificDocumentParser().parse_document(request)
    assert candidate.blocks, "native parser must extract real blocks"
    assert candidate.overall_quality.value in {"accepted", "partial"}
    assert candidate.native_engine.startswith("docling-parse")


@pytest.mark.scientific_document_native
def test_native_parser_scanned_fixture_has_no_text_layer() -> None:
    fixture = (
        ROOT
        / "services"
        / "scientific_document"
        / "fixtures"
        / "golden_scanned_like.pdf"
    )
    assert fixture.is_file(), "scanned fixture not generated"
    import hashlib

    from app.schemas.scientific_document import DocumentParseInput
    from app.services.scientific_document.hybrid_parser import (
        HybridScientificDocumentParser,
    )

    content = fixture.read_bytes()
    content_hash = "sha256:" + hashlib.sha256(content).hexdigest()
    request = DocumentParseInput(
        research_input_id="gs-scanned_like",
        content_hash=content_hash,
        source_type="upload",
        mime_type="application/pdf",
        filename=fixture.name,
        input_bytes=content,
    )
    candidate = HybridScientificDocumentParser().parse_document(request)
    assert len(candidate.blocks) == 0
    assert candidate.overall_quality.value == "unsupported"
