"""Validate a produced Scientific Document Parsing Contract benchmark report artifact (fail-closed).

Checks that the benchmark genuinely ran with no silent skips:
- the report parses as a Scientific Document Parsing Contract ``BenchmarkReport``;
- ``output_hash`` self-verifies (deterministic payload);
- at least one case ran (no silent skip / empty report);
- every fixture case carries a real ``output_hash`` and ``input_hash``;
- declared metrics include the measured coverage metrics;
- paired reports carry complete visual provenance, at least one really
  executed (latency-measured) hybrid case, and measured routing/latency
  metrics — a self-declared hybrid measurement without them fails closed;
- device claims never infer a GPU result from a CPU run.
"""

from __future__ import annotations

from collections import Counter
import json
import sys
from pathlib import Path

from app.schemas.scientific_document_benchmark import (
    BenchmarkDeviceStatus,
    BenchmarkMetricStatus,
    BenchmarkParserMode,
    BenchmarkReportMode,
    BenchmarkReport,
)

_PENDING_OUTPUT_HASH = "sha256:" + "0" * 64
_ROOT = Path(__file__).resolve().parents[1]


def _current_authority_errors(
    report: BenchmarkReport, *, require_local_bundle: bool
) -> list[str]:
    if str(_ROOT) not in sys.path:
        sys.path.insert(0, str(_ROOT))
    from app.services.scientific_document.hybrid_parser import (
        LOCAL_PADDLE_ENGINE_IDENTITY,
        native_engine_identity,
    )
    from services.scientific_document.benchmark_runner import (
        SCHEMA_VERSION,
        _config_hash_from_provenance,
        _expected_annotation_hash,
        _fixture_bytes,
        _load_golden_manifest,
        _manifest_content_hash,
        _report_input_hash,
    )
    from services.scientific_document.model_asset_contract import load_asset_manifest

    errors: list[str] = []
    manifest = _load_golden_manifest()
    expected_annotation_hash = _expected_annotation_hash(manifest)
    expected_manifest_hash = _manifest_content_hash(manifest)
    native_engine, native_version = native_engine_identity()
    if (
        report.schema_version != SCHEMA_VERSION
        or report.golden_set_manifest_id != manifest.manifest_id
        or report.golden_set_version != manifest.version
        or report.golden_set_content_hash != expected_manifest_hash
        or report.expected_annotation_hash != expected_annotation_hash
        or report.native_engine != native_engine
        or report.native_engine_version != native_version
    ):
        errors.append("report does not match the current Golden Set/schema/native pins")

    fixture_entries = {
        entry.entry_id: entry
        for entry in manifest.entries
        if entry.data_type.value == "fixture"
    }
    expected_modes = (
        (BenchmarkParserMode.native_only, BenchmarkParserMode.hybrid)
        if report.parser_mode == BenchmarkReportMode.paired
        else (BenchmarkParserMode.native_only,)
    )
    expected_cases = Counter(
        (entry_id, mode) for entry_id in fixture_entries for mode in expected_modes
    )
    observed_cases = Counter((case.entry_id, case.parser_mode) for case in report.cases)
    if observed_cases != expected_cases:
        errors.append("report case/mode set does not match every committed fixture")
    for entry in fixture_entries.values():
        try:
            _fixture_bytes(entry)
        except RuntimeError as exc:
            errors.append(str(exc))
    for case in report.cases:
        entry = fixture_entries.get(case.entry_id)
        if entry is None or case.input_hash != entry.content_hash:
            errors.append(
                f"case {case.entry_id}/{case.parser_mode.value} input_hash "
                "does not match the current fixture"
            )

    if report.parser_mode == BenchmarkReportMode.paired and (
        require_local_bundle or report.visual_engine == LOCAL_PADDLE_ENGINE_IDENTITY
    ):
        assets = load_asset_manifest()
        vlm = next(
            component
            for component in assets["components"]
            if component["role"] == "vlm_recognition"
        )
        if (
            report.visual_engine != LOCAL_PADDLE_ENGINE_IDENTITY
            or report.visual_engine_version != "1.6"
            or report.visual_model_id != vlm["resolved_model_id"]
            or report.visual_model_revision != vlm["revision"]
            or report.visual_runtime_binding_hash != assets["bundle_digest"]
        ):
            errors.append(
                "paired report does not match the current verified local Paddle bundle"
            )

    expected_config_hash = _config_hash_from_provenance(
        visual_engine=report.visual_engine,
        visual_engine_version=report.visual_engine_version,
        visual_model_id=report.visual_model_id,
        visual_model_revision=report.visual_model_revision,
        visual_runtime_binding_hash=report.visual_runtime_binding_hash,
    )
    if report.config_hash != expected_config_hash:
        errors.append("report config_hash does not match current execution provenance")
    expected_input_hash = _report_input_hash(
        manifest,
        expected_annotation_hash,
        expected_config_hash,
        modes=(report.parser_mode.value,),
    )
    if report.input_hash != expected_input_hash:
        errors.append("report input_hash does not match current frozen inputs")
    return errors


def _measured_metric(report: BenchmarkReport, name: str) -> bool:
    return any(
        metric.name == name and metric.status == BenchmarkMetricStatus.measured
        for metric in report.metrics
    )


def main() -> int:
    if len(sys.argv) < 2 or len(sys.argv) > 3:
        print(
            "usage: check_scientific_document_benchmark_report.py <report.json> "
            "[--require-local-bundle]",
            file=sys.stderr,
        )
        return 2
    require_local_bundle = len(sys.argv) == 3
    if require_local_bundle and sys.argv[2] != "--require-local-bundle":
        print(f"unknown checker option: {sys.argv[2]}", file=sys.stderr)
        return 2
    path = Path(sys.argv[1])
    if not path.is_file():
        print(f"benchmark report missing: {path}", file=sys.stderr)
        return 1
    data = json.loads(path.read_text(encoding="utf-8"))
    report = BenchmarkReport.model_validate(data)  # raises if output_hash mismatches

    errors = _current_authority_errors(
        report, require_local_bundle=require_local_bundle
    )
    if report.output_hash == _PENDING_OUTPUT_HASH:
        errors.append("benchmark report output_hash is still pending")
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

    if report.parser_mode == BenchmarkReportMode.native_only:
        metric_names = {m.name for m in report.metrics}
        for required in ("accepted_rate", "native_routing_coverage"):
            if required not in metric_names:
                errors.append(f"benchmark report missing metric {required}")
    else:
        # The paired visual execution must prove it happened: complete provenance,
        # at least one executed (latency-measured) hybrid case, and measured
        # coverage plus latency metrics. Anything less fails closed.
        if (
            not report.visual_engine
            or not report.visual_model_id
            or not report.visual_model_revision
        ):
            errors.append("paired report lacks visual provenance")
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
                "paired report has no latency-measured hybrid case; "
                "visual execution is unproven"
            )
        successfully_routed = [
            case
            for case in hybrid_cases
            if case.failure_category is None
            and (case.visual_routing_coverage or 0.0) > 0.0
        ]
        if not successfully_routed:
            errors.append(
                "paired report has no hybrid case with successful visual routing"
            )
        if not _measured_metric(report, "native_only_accepted_rate") or (
            not _measured_metric(report, "hybrid_accepted_rate")
        ):
            errors.append("paired report missing per-mode accepted_rate metrics")
        if not _measured_metric(report, "hybrid_latency"):
            errors.append("paired report missing measured hybrid_latency metric")
        if not _measured_metric(report, "visual_routing_coverage"):
            errors.append("paired report missing measured visual_routing_coverage metric")

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
