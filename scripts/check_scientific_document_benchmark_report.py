"""Validate a produced Scientific Document Parsing Contract benchmark report artifact (fail-closed).

Checks that the benchmark genuinely ran with no silent skips:
- the report parses as a Scientific Document Parsing Contract ``BenchmarkReport``;
- ``output_hash`` self-verifies (deterministic payload);
- at least one case ran (no silent skip / empty report);
- every fixture case carries a real ``output_hash`` and ``input_hash``;
- declared metrics include the measured coverage metrics;
- hybrid/paired reports carry complete visual provenance, at least one really
  executed (latency-measured) hybrid case, and measured routing/latency
  metrics — a self-declared hybrid measurement without them fails closed;
- device claims never infer a GPU result from a CPU run.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from app.schemas.scientific_document_benchmark import (
    BenchmarkDeviceStatus,
    BenchmarkMetricStatus,
    BenchmarkParserMode,
    BenchmarkReport,
)


def _measured_metric(report: BenchmarkReport, name: str) -> bool:
    return any(
        metric.name == name and metric.status == BenchmarkMetricStatus.measured
        for metric in report.metrics
    )


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: check_scientific_document_benchmark_report.py <report.json>", file=sys.stderr)
        return 2
    path = Path(sys.argv[1])
    if not path.is_file():
        print(f"benchmark report missing: {path}", file=sys.stderr)
        return 1
    data = json.loads(path.read_text(encoding="utf-8"))
    report = BenchmarkReport.model_validate(data)  # raises if output_hash mismatches

    errors: list[str] = []
    if len(report.cases) == 0:
        errors.append("benchmark report has zero cases (silent skip?)")
    for case in report.cases:
        if not case.output_hash.startswith("sha256:"):
            errors.append(f"case {case.entry_id} missing output_hash")
        if not case.input_hash.startswith("sha256:"):
            errors.append(f"case {case.entry_id} missing input_hash")
        if case.gpu_result and case.gpu_status != BenchmarkDeviceStatus.run:
            errors.append(
                f"case {case.entry_id} claims gpu_result without gpu_status=run"
            )
        if case.peak_memory_bytes is not None and case.peak_memory_basis is None:
            errors.append(
                f"case {case.entry_id} reports memory without its observation basis"
            )

    if report.parser_mode == BenchmarkParserMode.native_only:
        metric_names = {m.name for m in report.metrics}
        for required in ("accepted_rate", "native_routing_coverage"):
            if required not in metric_names:
                errors.append(f"benchmark report missing metric {required}")
    else:
        # A self-declared visual execution must prove it happened: complete
        # provenance, at least one executed (latency-measured) hybrid case, and
        # measured coverage plus latency metrics. Anything less fails closed.
        if (
            not report.visual_engine
            or not report.visual_model_id
            or not report.visual_model_revision
        ):
            errors.append(
                f"{report.parser_mode.value} report lacks visual provenance"
            )
        hybrid_cases = [
            case
            for case in report.cases
            if case.parser_mode == BenchmarkParserMode.hybrid
        ]
        executed_hybrid = [
            case for case in hybrid_cases if case.latency_seconds is not None
        ]
        if not executed_hybrid:
            errors.append(
                f"{report.parser_mode.value} report has no latency-measured "
                "hybrid case; visual execution is unproven"
            )
        if report.parser_mode == BenchmarkParserMode.paired:
            if not _measured_metric(report, "native_only_accepted_rate") or (
                not _measured_metric(report, "hybrid_accepted_rate")
            ):
                errors.append(
                    "paired report missing per-mode accepted_rate metrics"
                )
            if not _measured_metric(report, "hybrid_latency"):
                errors.append("paired report missing measured hybrid_latency metric")
        else:
            if not _measured_metric(report, "accepted_rate"):
                errors.append("hybrid report missing measured accepted_rate metric")
            if not _measured_metric(report, "latency"):
                errors.append("hybrid report missing measured latency metric")
        if not _measured_metric(report, "visual_routing_coverage"):
            errors.append(
                f"{report.parser_mode.value} report missing measured "
                "visual_routing_coverage metric"
            )

    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1

    executed = sum(1 for case in report.cases if case.latency_seconds is not None)
    print(
        f"Scientific Document Parsing Contract benchmark report valid: "
        f"{len(report.cases)} cases ({report.parser_mode.value}, "
        f"{executed} latency-measured), output_hash={report.output_hash}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
