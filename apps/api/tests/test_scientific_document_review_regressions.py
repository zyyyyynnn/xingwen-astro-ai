"""Regression tests added by the final Scientific Document Parsing Contract technical review."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.schemas.scientific_document_benchmark import (
    BenchmarkMetricStatus,
    BenchmarkMetricValue,
    GoldenExpectedAnnotation,
    GoldenSetEntry,
    GoldenSetManifest,
)

ROOT = Path(__file__).resolve().parents[3]
GOLDEN = ROOT / "services" / "scientific_document" / "golden_set.json"
ADOPTION = ROOT / "services" / "scientific_document" / "upstream_adoption.json"


def test_local_only_unhashed_entry_cannot_claim_pdf_page_ground_truth() -> None:
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
    manifest = GoldenSetManifest.model_validate_json(GOLDEN.read_text(encoding="utf-8"))
    for entry in manifest.entries:
        if entry.local_only and entry.content_hash is None and entry.expected is not None:
            assert entry.expected.expected_page_count is None


def test_golden_builder_and_committed_manifest_are_semantically_aligned() -> None:
    from services.scientific_document.build_golden_manifest import build_manifest

    committed = GoldenSetManifest.model_validate_json(GOLDEN.read_text(encoding="utf-8"))
    rebuilt = build_manifest()
    assert rebuilt.manifest_id == committed.manifest_id
    assert rebuilt.version == committed.version
    assert rebuilt.sample_count == committed.sample_count
    assert rebuilt.entries == committed.entries


def test_metric_rate_must_match_numerator_denominator() -> None:
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
    with pytest.raises(ValidationError):
        BenchmarkMetricValue(
            name="formula_recovery",
            status=BenchmarkMetricStatus.unsupported,
            numerator=1,
            denominator=1,
            rate=1.0,
            version="1.1.0",
        )


def test_adoption_manifest_declares_exact_import_roots() -> None:
    from services.scientific_document.adoption_contract import (
        collect_approved_packages,
        load_adoption_manifest,
    )

    manifest = load_adoption_manifest(ADOPTION)
    roots = collect_approved_packages(manifest)
    assert roots == {"docling_parse", "paddleocr", "paddle"}


def test_adoption_json_has_no_implicit_import_mapping() -> None:
    data = json.loads(ADOPTION.read_text(encoding="utf-8"))
    for entry in data["entries"]:
        if entry["adoption_status"] == "approved" and entry.get("package"):
            assert entry.get("import_roots"), entry["capability"]
