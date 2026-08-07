"""Reproducible D-10 Scientific Document Parsing benchmark runner.

Runs the benchmark-only native baseline (docling-parse) over the committed
Golden Set fixtures and emits a versioned, hashed ``BenchmarkReport``. Hybrid
mode is reserved: the result structure exists but real hybrid runs belong to
D-11. Native-only is the only mode executed here.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.core import ContentHash, Identifier
from app.schemas.scientific_document import (
    SCIENTIFIC_DOCUMENT_SCHEMA_VERSION,
    compute_scientific_document_schema_hash,
)
from app.schemas.scientific_document_benchmark import (
    BenchmarkCaseResult,
    BenchmarkDataType,
    BenchmarkMetricValue,
    BenchmarkParserMode,
    BenchmarkReport,
    compute_benchmark_report_hash,
)
from app.services.scientific_document.native_baseline import (
    native_engine_identity,
    parse_native_baseline,
)
from app.services.scientific_document.ports import ParseRequest

HERE = Path(__file__).resolve().parent
FIXTURES_DIR = HERE / "fixtures"
GOLDEN_SET = HERE / "golden_set.json"
SCHEMA_VERSION = "1.0.0"

_NATIVE_ENGINE, _NATIVE_VERSION = native_engine_identity()

_CONFIG_HASH_INPUT = {
    "schema_version": SCIENTIFIC_DOCUMENT_SCHEMA_VERSION,
    "schema_hash": compute_scientific_document_schema_hash(),
    "native_engine": _NATIVE_ENGINE,
}


def _config_hash() -> ContentHash:
    return compute_canonical_payload_hash(_CONFIG_HASH_INPUT)


def _load_golden() -> object:
    import json

    return json.loads(GOLDEN_SET.read_text(encoding="utf-8"))


def run_native_only() -> BenchmarkReport:
    golden = _load_golden()
    config_hash = _config_hash()
    cases: list[BenchmarkCaseResult] = []
    accepted = partial = unsupported = 0
    for entry in golden["entries"]:
        if entry["data_type"] != BenchmarkDataType.fixture.value:
            # Restricted/local-only entries are not parsed by CI (no PDF).
            continue
        pdf = FIXTURES_DIR / f"golden_{entry['entry_id'].removeprefix('gs-')}.pdf"
        if not pdf.is_file():
            continue
        content = pdf.read_bytes()
        content_hash = "sha256:" + __import__("hashlib").sha256(content).hexdigest()
        request = ParseRequest(
            research_input_id=entry["entry_id"],
            content_hash=content_hash,
            source_type="upload",
            mime_type="application/pdf",
            filename=pdf.name,
            input_bytes=content,
        )
        candidate = parse_native_baseline(request, config_hash=config_hash)
        q = candidate.overall_quality.value
        if q == "accepted":
            accepted += 1
        elif q == "partial":
            partial += 1
        else:
            unsupported += 1
        cases.append(
            BenchmarkCaseResult(
                entry_id=entry["entry_id"],
                parser_mode=BenchmarkParserMode.native_only,
                document_parse_id=candidate.parse_id,
                overall_quality=q,
                native_routing_coverage=1.0 if q != "unsupported" else 0.0,
                accepted_count=accepted if q == "accepted" else 0,
                partial_count=partial if q == "partial" else 0,
                unsupported_count=unsupported if q == "unsupported" else 0,
                cpu_result=True,
                gpu_result=False,
                input_hash=content_hash,
                output_hash=candidate.canonical_output_hash,
            )
        )
    total = max(len(cases), 1)
    metrics = (
        BenchmarkMetricValue(
            name="accepted_rate",
            numerator=accepted,
            denominator=total,
            rate=accepted / total,
            version=SCHEMA_VERSION,
        ),
        BenchmarkMetricValue(
            name="partial_rate",
            numerator=partial,
            denominator=total,
            rate=partial / total,
            version=SCHEMA_VERSION,
        ),
        BenchmarkMetricValue(
            name="unsupported_rate",
            numerator=unsupported,
            denominator=total,
            rate=unsupported / total,
            version=SCHEMA_VERSION,
        ),
        BenchmarkMetricValue(
            name="native_routing_coverage",
            numerator=sum(1 for c in cases if c.native_routing_coverage),
            denominator=total,
            rate=sum(1 for c in cases if c.native_routing_coverage) / total,
            version=SCHEMA_VERSION,
        ),
    )
    report = BenchmarkReport(
        report_id="d10-native-benchmark",
        schema_version=SCHEMA_VERSION,
        parser_mode=BenchmarkParserMode.native_only,
        golden_set_manifest_id=golden["manifest_id"],
        golden_set_version=golden["version"],
        native_engine=_NATIVE_ENGINE,
        native_engine_version=_NATIVE_VERSION,
        config_hash=config_hash,
        metrics=metrics,
        cases=tuple(cases),
        input_hash=compute_canonical_payload_hash(
            {"golden": golden["manifest_id"], "config": config_hash}
        ),
        output_hash="sha256:" + "0" * 64,
        created_at=datetime.now(timezone.utc).replace(microsecond=0),
    )
    report = report.model_copy(
        update={
            "output_hash": compute_benchmark_report_hash(report),
        }
    )
    return report


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
