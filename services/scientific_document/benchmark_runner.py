"""Reproducible Scientific Document Parsing benchmark runner.

One runner, three explicit modes over the same frozen Golden Set:

- ``native-only``  production parser profile without a configured visual service;
- ``hybrid``       the production ``HybridScientificDocumentParser`` wired to a real
                   ``PaddleOcrVlClient`` visual backend (fail-closed: refuses to run
                   without a configured backend instead of silently degrading);
- ``paired``       native-only and hybrid passes over the identical manifest in one
                   comparable ``BenchmarkReport``.

Fail-closed rules:
- a committed fixture that is missing is a benchmark error, never a skip;
- fixture bytes must match the manifest ``content_hash`` exactly;
- the Golden Set content hash covers the complete manifest content except the
  volatile ``generated_at`` timestamp, including every entry and annotation;
- metrics never claim a capability was measured when it was not;
- hybrid/paired reports always carry complete visual provenance, and latency is
  a real monotonic ``time.perf_counter()`` measurement, never an estimate;
- memory is labelled with its true observation boundary (Python heap via
  ``tracemalloc``), never passed off as process RSS or GPU memory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import tracemalloc
from dataclasses import dataclass
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
    BenchmarkDeviceStatus,
    BenchmarkMemoryBasis,
    BenchmarkMetricStatus,
    BenchmarkMetricValue,
    BenchmarkParserMode,
    BenchmarkReport,
    GoldenSetEntry,
    GoldenSetManifest,
    compute_benchmark_report_hash,
)
from app.services.scientific_document.hybrid_parser import (
    HybridScientificDocumentParser,
    PaddleOcrVlClient,
    VisualPageParserPort,
    native_engine_identity,
)

HERE = Path(__file__).resolve().parent
FIXTURES_DIR = HERE / "fixtures"
GOLDEN_SET = HERE / "golden_set.json"
SCHEMA_VERSION = "1.2.0"

_NATIVE_ENGINE, _NATIVE_VERSION = native_engine_identity()


def _config_hash(visual: VisualPageParserPort | None) -> ContentHash:
    payload = {
        "schema_version": SCIENTIFIC_DOCUMENT_SCHEMA_VERSION,
        "schema_hash": compute_scientific_document_schema_hash(),
        "native_engine": _NATIVE_ENGINE,
        "native_version": _NATIVE_VERSION,
        "visual_engine": visual.engine_version if visual is not None else None,
        "visual_model_id": visual.model_id if visual is not None else None,
        "visual_model_revision": (
            visual.model_revision if visual is not None else None
        ),
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
    """Return whitespace-normalized case-folded text for anchor checks."""
    text = " ".join(block.text or "" for block in candidate.blocks)
    return " ".join(text.casefold().split())


def _text_anchor_recovery(anchors: list[str], observed: str) -> float | None:
    if not anchors:
        return None
    recovered = sum(1 for anchor in anchors if anchor in observed)
    return recovered / len(anchors)


def _block_recovery(
    candidate: DocumentParseCandidate, entry: GoldenSetEntry
) -> float | None:
    """Recover manually selected critical textual anchors for one parse.

    The defensible cross-mode block metric is the fraction of manually selected
    critical textual anchors present in the recovered text layer of THIS mode.
    Structural table/formula/figure recovery needs adjudicated structural ground
    truth and is reported separately.
    """
    if entry.expected is None or not entry.expected.critical_headings:
        return None
    anchors = [
        " ".join(anchor.casefold().split())
        for anchor in entry.expected.critical_headings
    ]
    return _text_anchor_recovery(anchors, _normalized_text(candidate))


def _scientific_value_recovery(
    candidate: DocumentParseCandidate, entry: GoldenSetEntry
) -> float | None:
    """Fraction of annotated scientific value strings recovered verbatim."""
    if entry.expected is None or not entry.expected.selected_scientific_values:
        return None
    values = [
        " ".join(value.casefold().split())
        for value in entry.expected.selected_scientific_values
    ]
    return _text_anchor_recovery(values, _normalized_text(candidate))


def _locator_validity(candidate: DocumentParseCandidate) -> float | None:
    """Measure whether recovered blocks carry usable page geometry."""
    if not candidate.blocks:
        return None
    valid = sum(1 for block in candidate.blocks if block.bbox is not None)
    return valid / len(candidate.blocks)


def _reading_order_error(candidate: DocumentParseCandidate) -> float | None:
    """Adjacent-pair inversion rate over blocks that declare a reading order.

    For each page, consecutive blocks carrying a non-null ``reading_order`` are
    compared; the metric is inverted adjacent pairs over all adjacent pairs. A
    parse without ordered blocks reports ``None`` (nothing was measurable).
    """
    by_page: dict[int, list[int]] = {}
    for block in candidate.blocks:
        if block.reading_order is not None:
            by_page.setdefault(block.page_index, []).append(block.reading_order)
    pairs = 0
    inversions = 0
    for orders in by_page.values():
        for left, right in zip(orders, orders[1:]):
            pairs += 1
            if right < left:
                inversions += 1
    if pairs == 0:
        return None
    return inversions / pairs


def _routing_coverages(
    candidate: DocumentParseCandidate,
) -> tuple[float, float]:
    """Page-level routing outcome: pages touched by each backend / total pages."""
    pages = len(candidate.pages)
    if pages == 0:
        return 0.0, 0.0
    native_pages = {
        block.page_index
        for block in candidate.blocks
        if block.parser_backend.value == "native"
    }
    visual_pages = {
        block.page_index
        for block in candidate.blocks
        if block.parser_backend.value == "visual"
    }
    return len(native_pages) / pages, len(visual_pages) / pages


@dataclass(frozen=True, slots=True)
class _CaseObservation:
    candidate: DocumentParseCandidate | None
    latency_seconds: float
    peak_memory_bytes: int | None
    failure_category: str | None


def _observe_case(
    request: DocumentParseInput, parser: HybridScientificDocumentParser
) -> _CaseObservation:
    """Execute one parse twice: timed pass, then heap-boundary pass.

    The first pass records real monotonic latency without tracing overhead. The
    second pass re-parses under ``tracemalloc`` to observe the Python heap peak;
    both passes must agree on the deterministic canonical output hash or the
    case is marked as a nondeterministic failure.
    """
    started = time.perf_counter()
    try:
        candidate = parser.parse_document(request)
    except Exception as error:  # noqa: BLE001 - benchmark records the failure
        latency = time.perf_counter() - started
        return _CaseObservation(
            candidate=None,
            latency_seconds=latency,
            peak_memory_bytes=None,
            failure_category=f"{type(error).__name__}: {error}",
        )
    latency = time.perf_counter() - started

    tracemalloc.start()
    try:
        traced = parser.parse_document(request)
        _, traced_peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    if traced.canonical_output_hash != candidate.canonical_output_hash:
        return _CaseObservation(
            candidate=candidate,
            latency_seconds=latency,
            peak_memory_bytes=None,
            failure_category="nondeterministic_parse",
        )
    return _CaseObservation(
        candidate=candidate,
        latency_seconds=latency,
        peak_memory_bytes=int(traced_peak),
        failure_category=None,
    )


def _failed_case(
    entry_id: str,
    input_hash: str,
    observation: _CaseObservation,
    mode: BenchmarkParserMode,
) -> BenchmarkCaseResult:
    return BenchmarkCaseResult(
        entry_id=entry_id,
        parser_mode=mode,
        document_parse_id=f"{entry_id}-failed",
        overall_quality="unsupported",
        native_routing_coverage=None,
        visual_routing_coverage=None,
        evidence_locator_validity=None,
        accepted_count=0,
        partial_count=0,
        unsupported_count=0,
        latency_seconds=max(observation.latency_seconds, 0.0),
        peak_memory_bytes=observation.peak_memory_bytes,
        peak_memory_basis=(
            BenchmarkMemoryBasis.python_heap_tracemalloc
            if observation.peak_memory_bytes is not None
            else None
        ),
        cpu_result=True,
        gpu_result=False,
        gpu_status=BenchmarkDeviceStatus.not_run,
        failure_category=observation.failure_category,
        input_hash=input_hash,
        output_hash=compute_canonical_payload_hash(
            {
                "entry_id": entry_id,
                "parser_mode": mode.value,
                "failure_category": observation.failure_category,
            }
        ),
    )


def _fixture_bytes(entry: GoldenSetEntry) -> tuple[Path, bytes, str]:
    pdf = FIXTURES_DIR / f"golden_{entry.entry_id.removeprefix('gs-')}.pdf"
    if not pdf.is_file():
        raise RuntimeError(
            f"fixture entry {entry.entry_id} claims committed PDF but file is missing: {pdf}"
        )
    content = pdf.read_bytes()
    actual_hash = _sha256_bytes(content)
    if entry.content_hash is None:
        raise RuntimeError(
            f"fixture entry {entry.entry_id} has no content_hash; manifest drift"
        )
    if actual_hash != entry.content_hash:
        raise RuntimeError(
            f"fixture {entry.entry_id} content_hash mismatch: "
            f"manifest={entry.content_hash} actual={actual_hash}"
        )
    return pdf, content, actual_hash


def _run_pass(
    mode: BenchmarkParserMode, visual_parser: VisualPageParserPort | None
) -> tuple[list[BenchmarkCaseResult], GoldenSetManifest, ContentHash, ContentHash]:
    if mode == BenchmarkParserMode.hybrid and visual_parser is None:
        raise RuntimeError(
            "hybrid benchmark requires a configured visual backend "
            "(set PADDLEOCR_VL_BASE_URL and PADDLEOCR_VL_MODEL_REVISION); "
            "refusing to label a degraded run as hybrid"
        )
    parser = HybridScientificDocumentParser(visual_parser=visual_parser)
    manifest = _load_golden_manifest()

    cases: list[BenchmarkCaseResult] = []
    for entry in manifest.entries:
        if entry.data_type != BenchmarkDataType.fixture:
            # Restricted/local-only publications are not fetched by CI.
            continue
        pdf, content, actual_hash = _fixture_bytes(entry)
        request = DocumentParseInput(
            research_input_id=entry.entry_id,
            content_hash=actual_hash,
            source_type="upload",
            mime_type="application/pdf",
            filename=pdf.name,
            input_bytes=content,
        )
        observation = _observe_case(request, parser)
        candidate = observation.candidate
        if candidate is None:
            cases.append(_failed_case(entry.entry_id, actual_hash, observation, mode))
            continue

        quality = candidate.overall_quality.value
        native_coverage, visual_coverage = _routing_coverages(candidate)
        cases.append(
            BenchmarkCaseResult(
                entry_id=entry.entry_id,
                parser_mode=mode,
                document_parse_id=candidate.parse_id,
                overall_quality=quality,
                native_routing_coverage=native_coverage,
                visual_routing_coverage=visual_coverage,
                block_recovery=_block_recovery(candidate, entry),
                scientific_value_recovery=_scientific_value_recovery(
                    candidate, entry
                ),
                reading_order_error=_reading_order_error(candidate),
                table_structure_recovery=None,
                formula_recovery=None,
                figure_caption_linkage=None,
                evidence_locator_validity=_locator_validity(candidate),
                accepted_count=sum(
                    1
                    for block in candidate.blocks
                    if block.quality.value == "accepted"
                ),
                partial_count=sum(
                    1
                    for block in candidate.blocks
                    if block.quality.value == "partial"
                ),
                unsupported_count=sum(
                    1
                    for block in candidate.blocks
                    if block.quality.value == "unsupported"
                ),
                latency_seconds=max(observation.latency_seconds, 0.0),
                peak_memory_bytes=observation.peak_memory_bytes,
                peak_memory_basis=(
                    BenchmarkMemoryBasis.python_heap_tracemalloc
                    if observation.peak_memory_bytes is not None
                    else None
                ),
                cpu_result=True,
                gpu_result=False,
                gpu_status=BenchmarkDeviceStatus.not_run,
                input_hash=actual_hash,
                output_hash=candidate.canonical_output_hash,
            )
        )

    if not cases:
        raise RuntimeError("benchmark produced zero fixture cases")
    return cases, manifest, _expected_annotation_hash(manifest), _manifest_content_hash(manifest)


def _mean_measured(
    values: list[float | None],
) -> tuple[BenchmarkMetricStatus, float, float]:
    measured = [value for value in values if value is not None]
    if not measured:
        return BenchmarkMetricStatus.not_run, 0.0, 0.0
    return BenchmarkMetricStatus.measured, sum(measured), float(len(measured))


def _latency_mean(cases: list[BenchmarkCaseResult]) -> float:
    measured = [case.latency_seconds for case in cases if case.latency_seconds is not None]
    if not measured:
        raise RuntimeError("cases must carry measured latency")
    return sum(measured) / len(measured)


def _memory_mean(cases: list[BenchmarkCaseResult]) -> tuple[BenchmarkMetricStatus, float, float]:
    measured = [
        float(case.peak_memory_bytes)
        for case in cases
        if case.peak_memory_bytes is not None
    ]
    if not measured:
        return BenchmarkMetricStatus.not_run, 0.0, 0.0
    return BenchmarkMetricStatus.measured, sum(measured) / len(measured), 1.0


def _mode_quality_metrics(
    prefix: str, cases: list[BenchmarkCaseResult]
) -> tuple[BenchmarkMetricValue, ...]:
    total = float(len(cases))
    accepted = sum(1 for case in cases if case.overall_quality == "accepted")
    partial = sum(1 for case in cases if case.overall_quality == "partial")
    unsupported = sum(1 for case in cases if case.overall_quality == "unsupported")
    block_status, block_num, block_den = _mean_measured(
        [case.block_recovery for case in cases]
    )
    value_status, value_num, value_den = _mean_measured(
        [case.scientific_value_recovery for case in cases]
    )
    order_status, order_num, order_den = _mean_measured(
        [case.reading_order_error for case in cases]
    )
    memory_status, memory_num, memory_den = _memory_mean(cases)
    return (
        _metric(
            f"{prefix}accepted_rate", BenchmarkMetricStatus.measured, accepted, total
        ),
        _metric(
            f"{prefix}partial_rate", BenchmarkMetricStatus.measured, partial, total
        ),
        _metric(
            f"{prefix}unsupported_rate",
            BenchmarkMetricStatus.measured,
            unsupported,
            total,
        ),
        _metric(f"{prefix}block_recovery", block_status, block_num, block_den),
        _metric(
            f"{prefix}scientific_value_recovery",
            value_status,
            value_num,
            value_den,
        ),
        _metric(f"{prefix}reading_order_error", order_status, order_num, order_den),
        _metric(
            f"{prefix}latency",
            BenchmarkMetricStatus.measured,
            round(_latency_mean(cases), 9),
            1.0,
        ),
        _metric(
            f"{prefix}peak_memory",
            memory_status,
            memory_num,
            memory_den,
        ),
    )


def _report_input_hash(
    manifest: GoldenSetManifest,
    expected_annotation_hash: ContentHash,
    config_hash: ContentHash,
    *,
    modes: tuple[str, ...],
) -> ContentHash:
    return compute_canonical_payload_hash(
        {
            "modes": list(modes),
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


def _build_report(
    *,
    report_id: str,
    parser_mode: BenchmarkParserMode,
    cases: list[BenchmarkCaseResult],
    metrics: tuple[BenchmarkMetricValue, ...],
    manifest: GoldenSetManifest,
    expected_annotation_hash: ContentHash,
    config_hash: ContentHash,
    visual_parser: VisualPageParserPort | None,
) -> BenchmarkReport:
    report = BenchmarkReport(
        report_id=report_id,
        schema_version=SCHEMA_VERSION,
        parser_mode=parser_mode,
        golden_set_manifest_id=manifest.manifest_id,
        golden_set_version=manifest.version,
        golden_set_content_hash=_manifest_content_hash(manifest),
        expected_annotation_hash=expected_annotation_hash,
        native_engine=_NATIVE_ENGINE,
        native_engine_version=_NATIVE_VERSION,
        visual_engine=(
            (
                "PaddleOCR-VL layout-parsing service"
                if isinstance(visual_parser, PaddleOcrVlClient)
                else "PaddleOCRVL official in-process pipeline (verified local bundle)"
            )
            if visual_parser is not None
            else None
        ),
        visual_engine_version=(
            visual_parser.engine_version if visual_parser is not None else None
        ),
        visual_model_id=visual_parser.model_id if visual_parser is not None else None,
        visual_model_revision=(
            visual_parser.model_revision if visual_parser is not None else None
        ),
        config_hash=config_hash,
        metrics=metrics,
        cases=tuple(cases),
        input_hash=_report_input_hash(
            manifest,
            expected_annotation_hash,
            config_hash,
            modes=(parser_mode.value,),
        ),
        output_hash="sha256:" + "0" * 64,
        created_at=datetime.now(timezone.utc).replace(microsecond=0),
    )
    return report.model_copy(
        update={"output_hash": compute_benchmark_report_hash(report)}
    )


def run_native_only() -> BenchmarkReport:
    """Native-only profile: no visual backend configured or claimed."""
    cases, manifest, annotation_hash, _ = _run_pass(
        BenchmarkParserMode.native_only, visual_parser=None
    )
    locator_status, locator_num, locator_den = _mean_measured(
        [case.evidence_locator_validity for case in cases]
    )
    native_cases = [c for c in cases if c.parser_mode == BenchmarkParserMode.native_only]
    native_routing = sum(
        (case.native_routing_coverage or 0.0) for case in native_cases
    ) / float(len(native_cases))
    metrics = (
        *_mode_quality_metrics("", native_cases),
        _metric(
            "native_routing_coverage", BenchmarkMetricStatus.measured, native_routing, 1.0
        ),
        _metric("visual_routing_coverage", BenchmarkMetricStatus.not_applicable),
        _metric(
            "evidence_locator_validity", locator_status, locator_num, locator_den
        ),
        _metric("table_structure_recovery", BenchmarkMetricStatus.unsupported),
        _metric("formula_recovery", BenchmarkMetricStatus.unsupported),
        _metric("figure_caption_linkage", BenchmarkMetricStatus.unsupported),
    )
    return _build_report(
        report_id="scientific_document-native-benchmark",
        parser_mode=BenchmarkParserMode.native_only,
        cases=cases,
        metrics=metrics,
        manifest=manifest,
        expected_annotation_hash=annotation_hash,
        config_hash=_config_hash(None),
        visual_parser=None,
    )


def visual_parser_from_settings() -> VisualPageParserPort:
    """Build the real production visual backend from environment settings.

    Two mutually exclusive operator paths, both real and fail-closed:

    - ``PADDLEOCR_VL_BASE_URL`` + ``PADDLEOCR_VL_MODEL_REVISION``: the official
      PaddleOCR-VL layout-parsing HTTP service;
    - ``PADDLEOCR_VL_LOCAL_BUNDLE``: the approved in-process official
      ``PaddleOCRVL`` pipeline against a content-addressed bundle that must
      fully verify against the committed asset manifest first.

    A hybrid/paired benchmark refuses to start without one of them rather than
    silently degrading and mislabeling the result.
    """
    from app.config import settings

    base_url = settings.PADDLEOCR_VL_BASE_URL
    bundle_root = settings.PADDLEOCR_VL_LOCAL_BUNDLE
    if base_url is not None:
        if settings.PADDLEOCR_VL_MODEL_REVISION is None:
            raise RuntimeError(
                "hybrid/paired benchmark requires a configured visual backend: "
                "PADDLEOCR_VL_BASE_URL needs PADDLEOCR_VL_MODEL_REVISION"
            )
        return PaddleOcrVlClient(
            base_url=base_url,
            model_revision=settings.PADDLEOCR_VL_MODEL_REVISION,
            timeout_seconds=settings.PADDLEOCR_VL_TIMEOUT_SECONDS,
        )
    if bundle_root is not None:
        from app.services.scientific_document.local_paddle_pipeline import (
            LocalPaddleOcrVlPipeline,
        )
        from services.scientific_document.model_asset_contract import (
            ModelAssetContractError,
        )

        try:
            return LocalPaddleOcrVlPipeline(bundle_root=Path(bundle_root))
        except ModelAssetContractError as error:
            raise RuntimeError(
                f"hybrid/paired benchmark visual backend rejected the "
                f"configured bundle: {error}"
            ) from error
    raise RuntimeError(
        "hybrid/paired benchmark requires a configured visual backend: set "
        "PADDLEOCR_VL_BASE_URL + PADDLEOCR_VL_MODEL_REVISION (official HTTP "
        "service) or PADDLEOCR_VL_LOCAL_BUNDLE (verified official model "
        "bundle for the in-process pipeline)"
    )


def run_hybrid() -> BenchmarkReport:
    """Real hybrid profile through the production parser and visual client."""
    visual = visual_parser_from_settings()
    cases, manifest, annotation_hash, _ = _run_pass(
        BenchmarkParserMode.hybrid, visual_parser=visual
    )
    hybrid_cases = [c for c in cases if c.parser_mode == BenchmarkParserMode.hybrid]
    locator_status, locator_num, locator_den = _mean_measured(
        [case.evidence_locator_validity for case in cases]
    )
    native_routing = sum(
        (case.native_routing_coverage or 0.0) for case in hybrid_cases
    ) / float(len(hybrid_cases))
    visual_routing = sum(
        (case.visual_routing_coverage or 0.0) for case in hybrid_cases
    ) / float(len(hybrid_cases))
    metrics = (
        *_mode_quality_metrics("", hybrid_cases),
        _metric(
            "native_routing_coverage", BenchmarkMetricStatus.measured, native_routing, 1.0
        ),
        _metric(
            "visual_routing_coverage", BenchmarkMetricStatus.measured, visual_routing, 1.0
        ),
        _metric(
            "evidence_locator_validity", locator_status, locator_num, locator_den
        ),
        _metric("table_structure_recovery", BenchmarkMetricStatus.unsupported),
        _metric("formula_recovery", BenchmarkMetricStatus.unsupported),
        _metric("figure_caption_linkage", BenchmarkMetricStatus.unsupported),
    )
    return _build_report(
        report_id="scientific_document-hybrid-benchmark",
        parser_mode=BenchmarkParserMode.hybrid,
        cases=cases,
        metrics=metrics,
        manifest=manifest,
        expected_annotation_hash=annotation_hash,
        config_hash=_config_hash(visual),
        visual_parser=visual,
    )


def run_paired() -> BenchmarkReport:
    """Paired compare: identical manifest through native-only then real hybrid."""
    visual = visual_parser_from_settings()
    native_cases, manifest, annotation_hash, _ = _run_pass(
        BenchmarkParserMode.native_only, visual_parser=None
    )
    hybrid_cases, _, _, _ = _run_pass(
        BenchmarkParserMode.hybrid, visual_parser=visual
    )
    cases = [*native_cases, *hybrid_cases]
    locator_status, locator_num, locator_den = _mean_measured(
        [case.evidence_locator_validity for case in cases]
    )
    native_only_cases = [
        c for c in cases if c.parser_mode == BenchmarkParserMode.native_only
    ]
    hybrid_only_cases = [
        c for c in cases if c.parser_mode == BenchmarkParserMode.hybrid
    ]
    visual_routing = sum(
        (case.visual_routing_coverage or 0.0) for case in hybrid_only_cases
    ) / float(len(hybrid_only_cases))
    metrics = (
        *_mode_quality_metrics("native_only_", native_only_cases),
        *_mode_quality_metrics("hybrid_", hybrid_only_cases),
        _metric(
            "visual_routing_coverage", BenchmarkMetricStatus.measured, visual_routing, 1.0
        ),
        _metric(
            "evidence_locator_validity", locator_status, locator_num, locator_den
        ),
        _metric("table_structure_recovery", BenchmarkMetricStatus.unsupported),
        _metric("formula_recovery", BenchmarkMetricStatus.unsupported),
        _metric("figure_caption_linkage", BenchmarkMetricStatus.unsupported),
    )
    return _build_report(
        report_id="scientific_document-paired-benchmark",
        parser_mode=BenchmarkParserMode.paired,
        cases=cases,
        metrics=metrics,
        manifest=manifest,
        expected_annotation_hash=annotation_hash,
        # The paired identity pins BOTH configurations; the hash covers the
        # visual identity because the hybrid half executed against it.
        config_hash=_config_hash(visual),
        visual_parser=visual,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run the Scientific Document Parsing Contract benchmark "
            "(native-only, hybrid, or paired compare over one frozen Golden Set)."
        )
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--mode",
        choices=("native-only", "hybrid", "paired"),
        default="native-only",
        help=(
            "native-only runs without a visual backend; hybrid requires a real "
            "configured PaddleOCR-VL service; paired emits both passes in one report"
        ),
    )
    args = parser.parse_args()
    if args.mode == "native-only":
        report = run_native_only()
    elif args.mode == "hybrid":
        report = run_hybrid()
    else:
        report = run_paired()
    content = report.model_dump_json(indent=2) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content, encoding="utf-8")
    else:
        print(content, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
