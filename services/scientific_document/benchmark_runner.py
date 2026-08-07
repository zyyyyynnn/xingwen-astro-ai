"""Reproducible D-10 Scientific Document Parsing benchmark runner.

Runs the benchmark-only native baseline (docling-parse) over the committed
Golden Set fixtures and emits a versioned, hashed ``BenchmarkReport``. Hybrid
mode is reserved: the result structure exists but real hybrid runs belong to
D-11. Native-only is the only mode executed here.

Fail-closed rules (D-10 E2/E3):
- A fixture entry that claims a committed PDF but whose file is missing is a
  benchmark ERROR, not a silent skip.
- The actual sha256 of the fixture bytes MUST equal the manifest content_hash;
  any mismatch is a benchmark ERROR.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.core import ContentHash
from app.schemas.scientific_document import (
    SCIENTIFIC_DOCUMENT_SCHEMA_VERSION,
    compute_scientific_document_schema_hash,
)
from app.schemas.scientific_document_benchmark import (
    BenchmarkCaseResult,
    BenchmarkDataType,
    BenchmarkMetricStatus,
    BenchmarkMetricValue,
    BenchmarkParserMode,
    BenchmarkReport,
    GoldenSetManifest,
    compute_benchmark_report_hash,
)
from app.services.scientific_document.native_baseline import (
    native_engine_identity,
    parse_native_baseline,
)

HERE = Path(__file__).resolve().parent
FIXTURES_DIR = HERE / "fixtures"
GOLDEN_SET = HERE / "golden_set.json"
SCHEMA_VERSION = "1.1.0"

_NATIVE_ENGINE, _NATIVE_VERSION = native_engine_identity()


def _config_hash() -> ContentHash:
    payload = {
        "schema_version": SCIENTIFIC_DOCUMENT_SCHEMA_VERSION,
        "schema_hash": compute_scientific_document_schema_hash(),
        "native_engine": _NATIVE_ENGINE,
        "native_version": _NATIVE_VERSION,
    }
    return compute_canonical_payload_hash(payload)


def _load_golden_manifest() -> GoldenSetManifest:
    """Strongly-typed load: fail closed on any manifest drift."""
    data = json.loads(GOLDEN_SET.read_text(encoding="utf-8"))
    return GoldenSetManifest.model_validate(data)


def _expected_annotation_hash(manifest: GoldenSetManifest) -> ContentHash:
    payload = {
        e.entry_id: (e.expected.model_dump(mode="json") if e.expected else None)
        for e in manifest.entries
    }
    return compute_canonical_payload_hash(payload)


def _sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _metric(
    name: str,
    status: BenchmarkMetricStatus,
    numerator: float,
    denominator: float,
    version: str,
) -> BenchmarkMetricValue:
    """Build a metric with ``rate`` computed explicitly (deterministic, no warning)."""
    rate = (numerator / denominator) if denominator > 0 else None
    return BenchmarkMetricValue(
        name=name,
        status=status,
        numerator=numerator,
        denominator=denominator,
        rate=rate,
        version=version,
    )


def run_native_only() -> BenchmarkReport:
    manifest = _load_golden_manifest()
    config_hash = _config_hash()
    expected_annotation_hash = _expected_annotation_hash(manifest)

    cases: list[BenchmarkCaseResult] = []
    accepted = partial = unsupported = 0  # aggregate tallies (separate from per-case)
    for entry in manifest.entries:
        if entry.data_type != BenchmarkDataType.fixture:
            # Restricted/local-only entries are NOT parsed by CI (no PDF).
            continue
        if entry.content_hash is None:
            raise RuntimeError(
                f"fixture entry {entry.entry_id} has no content_hash; manifest drift"
            )
        pdf = FIXTURES_DIR / f"golden_{entry.entry_id.removeprefix('gs-')}.pdf"
        if not pdf.is_file():
            raise RuntimeError(
                f"fixture entry {entry.entry_id} claims committed PDF but file is missing: {pdf}"
            )
        content = pdf.read_bytes()
        actual_hash = _sha256_bytes(content)
        if actual_hash != entry.content_hash:
            raise RuntimeError(
                f"fixture {entry.entry_id} content_hash mismatch: "
                f"manifest={entry.content_hash} actual={actual_hash}"
            )

        from app.schemas.scientific_document import DocumentParseInput

        request = DocumentParseInput(
            research_input_id=entry.entry_id,
            content_hash=actual_hash,
            source_type="upload",
            mime_type="application/pdf",
            filename=pdf.name,
            input_bytes=content,
        )
        candidate = parse_native_baseline(request, config_hash=config_hash)

        q = candidate.overall_quality.value
        case_accepted = sum(
            1 for b in candidate.blocks if b.quality.value == "accepted"
        )
        case_partial = sum(
            1 for b in candidate.blocks if b.quality.value == "partial"
        )
        case_unsupported = sum(
            1 for b in candidate.blocks if b.quality.value == "unsupported"
        )
        if q == "accepted":
            accepted += 1
        elif q == "partial":
            partial += 1
        else:
            unsupported += 1

        # Native-only born-digital parser recovers text blocks but NOT tables,
        # formulas or figures structurally -> declare those capabilities explicitly.
        cases.append(
            BenchmarkCaseResult(
                entry_id=entry.entry_id,
                parser_mode=BenchmarkParserMode.native_only,
                document_parse_id=candidate.parse_id,
                overall_quality=q,
                native_routing_coverage=1.0 if q != "unsupported" else 0.0,
                block_recovery=(
                    case_accepted / max(len(candidate.blocks), 1)
                    if candidate.blocks
                    else 0.0
                ),
                table_structure_recovery=None,
                formula_recovery=None,
                figure_caption_linkage=None,
                evidence_locator_validity=(
                    1.0 if candidate.blocks and all(b.bbox is not None for b in candidate.blocks) else 0.0
                ),
                accepted_count=case_accepted,
                partial_count=case_partial,
                unsupported_count=case_unsupported,
                cpu_result=True,
                gpu_result=False,
                input_hash=actual_hash,
                output_hash=candidate.canonical_output_hash,
            )
        )

    total = max(len(cases), 1)
    metrics = (
        _metric("accepted_rate", BenchmarkMetricStatus.measured, accepted, total, SCHEMA_VERSION),
        _metric("partial_rate", BenchmarkMetricStatus.measured, partial, total, SCHEMA_VERSION),
        _metric("unsupported_rate", BenchmarkMetricStatus.measured, unsupported, total, SCHEMA_VERSION),
        _metric(
            "native_routing_coverage",
            BenchmarkMetricStatus.measured,
            sum(1 for c in cases if (c.native_routing_coverage or 0) > 0),
            total,
            SCHEMA_VERSION,
        ),
        _metric("table_structure_recovery", BenchmarkMetricStatus.unsupported, 0.0, 0.0, SCHEMA_VERSION),
        _metric("formula_recovery", BenchmarkMetricStatus.unsupported, 0.0, 0.0, SCHEMA_VERSION),
        _metric("figure_caption_linkage", BenchmarkMetricStatus.unsupported, 0.0, 0.0, SCHEMA_VERSION),
    )

    input_hash = compute_canonical_payload_hash(
        {
            "golden_set_manifest_id": manifest.manifest_id,
            "golden_set_version": manifest.version,
            "golden_set_content_hash": _manifest_content_hash(manifest),
            "expected_annotation_hash": expected_annotation_hash,
            "config_hash": config_hash,
            "schema_version": SCIENTIFIC_DOCUMENT_SCHEMA_VERSION,
            "schema_hash": compute_scientific_document_schema_hash(),
            "native_engine": _NATIVE_ENGINE,
            "native_version": _NATIVE_VERSION,
        }
    )

    report = BenchmarkReport(
        report_id="d10-native-benchmark",
        schema_version=SCHEMA_VERSION,
        parser_mode=BenchmarkParserMode.native_only,
        golden_set_manifest_id=manifest.manifest_id,
        golden_set_version=manifest.version,
        golden_set_content_hash=_manifest_content_hash(manifest),
        expected_annotation_hash=expected_annotation_hash,
        native_engine=_NATIVE_ENGINE,
        native_engine_version=_NATIVE_VERSION,
        config_hash=config_hash,
        metrics=metrics,
        cases=tuple(cases),
        input_hash=input_hash,
        output_hash="sha256:" + "0" * 64,
        created_at=datetime.now(timezone.utc).replace(microsecond=0),
    )
    # Self-verifying hash: recompute and store; the model validator re-checks it.
    report = report.model_copy(
        update={"output_hash": compute_benchmark_report_hash(report)}
    )
    return report


def _manifest_content_hash(manifest: GoldenSetManifest) -> ContentHash:
    return compute_canonical_payload_hash(
        manifest.model_dump(mode="json", exclude={"generated_at", "entries"})
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the D-10 native benchmark.")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = run_native_only()
    content = report.model_dump_json(indent=2) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content, encoding="utf-8")
    else:
        print(content, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
