"""Reproducible Scientific Document Parsing benchmark runner.

Runs the benchmark-only native baseline (docling-parse) over the committed
Golden Set fixtures and emits a hashed ``BenchmarkReport``. The report contract
also carries hybrid provenance; this runner never claims a hybrid execution.

Fail-closed rules:
- a committed fixture that is missing is a benchmark error, never a skip;
- fixture bytes must match the manifest ``content_hash`` exactly;
- the Golden Set content hash covers the complete manifest content except the
  volatile ``generated_at`` timestamp, including every entry and annotation;
- metrics never claim a capability was measured when it was not.
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
    DocumentParseCandidate,
    DocumentParseInput,
    compute_scientific_document_schema_hash,
)
from app.schemas.scientific_document_benchmark import (
    BenchmarkCaseResult,
    BenchmarkDataType,
    BenchmarkMetricStatus,
    BenchmarkMetricValue,
    BenchmarkParserMode,
    BenchmarkReport,
    GoldenSetEntry,
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
    """Strongly typed load: fail closed on any manifest drift."""
    data = json.loads(GOLDEN_SET.read_text(encoding="utf-8"))
    return GoldenSetManifest.model_validate(data)


def _expected_annotation_hash(manifest: GoldenSetManifest) -> ContentHash:
    payload = {
        e.entry_id: (e.expected.model_dump(mode="json") if e.expected else None)
        for e in manifest.entries
    }
    return compute_canonical_payload_hash(payload)


def _manifest_content_hash(manifest: GoldenSetManifest) -> ContentHash:
    """Hash the complete non-volatile Golden Set manifest.

    ``generated_at`` is execution metadata and is intentionally excluded. Every
    entry (source/provenance/license/content hash/coverage/annotation) remains in
    the payload, so any meaningful Golden Set change changes this hash.
    """
    return compute_canonical_payload_hash(
        manifest.model_dump(mode="json", exclude={"generated_at"})
    )


def _sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _metric(
    name: str,
    status: BenchmarkMetricStatus,
    numerator: float = 0.0,
    denominator: float = 0.0,
    version: str = SCHEMA_VERSION,
) -> BenchmarkMetricValue:
    """Build one metric without conflating unmeasured capabilities with zero."""
    rate = (numerator / denominator) if denominator > 0 else None
    return BenchmarkMetricValue(
        name=name,
        status=status,
        numerator=numerator,
        denominator=denominator,
        rate=rate,
        version=version,
    )


def _normalized_text(candidate: DocumentParseCandidate) -> str:
    """Return whitespace-normalized case-folded native text for anchor checks."""
    text = " ".join(block.text or "" for block in candidate.blocks)
    return " ".join(text.casefold().split())


def _block_recovery(candidate: DocumentParseCandidate, entry: GoldenSetEntry) -> float | None:
    """Recover manually selected textual block anchors for the native baseline.

    Scientific Document Parsing Contract does not pretend the word-level native probe performs semantic layout
    classification. For native-only, the defensible block metric is therefore
    the fraction of manually selected critical textual anchors that are present
    in the recovered text layer. Structural table/formula/figure recovery is
    reported separately as unsupported.
    """
    if entry.expected is None or not entry.expected.critical_headings:
        return None
    observed = _normalized_text(candidate)
    anchors = [" ".join(anchor.casefold().split()) for anchor in entry.expected.critical_headings]
    recovered = sum(1 for anchor in anchors if anchor in observed)
    return recovered / len(anchors)


def _locator_validity(candidate: DocumentParseCandidate) -> float | None:
    """Measure whether recovered native blocks carry usable page geometry."""
    if not candidate.blocks:
        return None
    valid = sum(1 for block in candidate.blocks if block.bbox is not None)
    return valid / len(candidate.blocks)


def _mean_measured(values: list[float | None]) -> tuple[BenchmarkMetricStatus, float, float]:
    measured = [value for value in values if value is not None]
    if not measured:
        return BenchmarkMetricStatus.not_run, 0.0, 0.0
    return BenchmarkMetricStatus.measured, sum(measured), float(len(measured))


def run_native_only() -> BenchmarkReport:
    manifest = _load_golden_manifest()
    config_hash = _config_hash()
    expected_annotation_hash = _expected_annotation_hash(manifest)
    manifest_hash = _manifest_content_hash(manifest)

    cases: list[BenchmarkCaseResult] = []
    accepted = partial = unsupported = 0

    for entry in manifest.entries:
        if entry.data_type != BenchmarkDataType.fixture:
            # Restricted/local-only publications are not fetched by CI.
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

        request = DocumentParseInput(
            research_input_id=entry.entry_id,
            content_hash=actual_hash,
            source_type="upload",
            mime_type="application/pdf",
            filename=pdf.name,
            input_bytes=content,
        )
        candidate = parse_native_baseline(request, config_hash=config_hash)

        quality = candidate.overall_quality.value
        case_accepted = sum(
            1 for block in candidate.blocks if block.quality.value == "accepted"
        )
        case_partial = sum(
            1 for block in candidate.blocks if block.quality.value == "partial"
        )
        case_unsupported = sum(
            1 for block in candidate.blocks if block.quality.value == "unsupported"
        )

        if quality == "accepted":
            accepted += 1
        elif quality == "partial":
            partial += 1
        else:
            unsupported += 1

        cases.append(
            BenchmarkCaseResult(
                entry_id=entry.entry_id,
                parser_mode=BenchmarkParserMode.native_only,
                document_parse_id=candidate.parse_id,
                overall_quality=quality,
                native_routing_coverage=1.0 if quality != "unsupported" else 0.0,
                visual_routing_coverage=0.0,
                block_recovery=_block_recovery(candidate, entry),
                reading_order_error=None,
                table_structure_recovery=None,
                formula_recovery=None,
                figure_caption_linkage=None,
                evidence_locator_validity=_locator_validity(candidate),
                accepted_count=case_accepted,
                partial_count=case_partial,
                unsupported_count=case_unsupported,
                latency_seconds=None,
                peak_memory_bytes=None,
                cpu_result=True,
                gpu_result=False,
                input_hash=actual_hash,
                output_hash=candidate.canonical_output_hash,
            )
        )

    if not cases:
        raise RuntimeError("native benchmark produced zero fixture cases")

    total = float(len(cases))
    block_status, block_num, block_den = _mean_measured(
        [case.block_recovery for case in cases]
    )
    locator_status, locator_num, locator_den = _mean_measured(
        [case.evidence_locator_validity for case in cases]
    )

    metrics = (
        _metric("accepted_rate", BenchmarkMetricStatus.measured, accepted, total),
        _metric("partial_rate", BenchmarkMetricStatus.measured, partial, total),
        _metric("unsupported_rate", BenchmarkMetricStatus.measured, unsupported, total),
        _metric(
            "native_routing_coverage",
            BenchmarkMetricStatus.measured,
            sum((case.native_routing_coverage or 0.0) for case in cases),
            total,
        ),
        _metric("visual_routing_coverage", BenchmarkMetricStatus.not_applicable),
        _metric("block_recovery", block_status, block_num, block_den),
        _metric("reading_order_error", BenchmarkMetricStatus.not_run),
        _metric("table_structure_recovery", BenchmarkMetricStatus.unsupported),
        _metric("formula_recovery", BenchmarkMetricStatus.unsupported),
        _metric("figure_caption_linkage", BenchmarkMetricStatus.unsupported),
        _metric("evidence_locator_validity", locator_status, locator_num, locator_den),
        _metric("latency", BenchmarkMetricStatus.not_run),
        _metric("peak_memory", BenchmarkMetricStatus.not_run),
    )

    input_hash = compute_canonical_payload_hash(
        {
            "golden_set_manifest_id": manifest.manifest_id,
            "golden_set_version": manifest.version,
            "golden_set_content_hash": manifest_hash,
            "expected_annotation_hash": expected_annotation_hash,
            "config_hash": config_hash,
            "schema_version": SCIENTIFIC_DOCUMENT_SCHEMA_VERSION,
            "schema_hash": compute_scientific_document_schema_hash(),
            "native_engine": _NATIVE_ENGINE,
            "native_version": _NATIVE_VERSION,
        }
    )

    report = BenchmarkReport(
        report_id="scientific_document-native-benchmark",
        schema_version=SCHEMA_VERSION,
        parser_mode=BenchmarkParserMode.native_only,
        golden_set_manifest_id=manifest.manifest_id,
        golden_set_version=manifest.version,
        golden_set_content_hash=manifest_hash,
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
    return report.model_copy(
        update={"output_hash": compute_benchmark_report_hash(report)}
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Scientific Document Parsing Contract native benchmark.")
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
