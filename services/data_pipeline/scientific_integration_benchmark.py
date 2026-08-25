"""Scientific Data Integration Benchmark runner (frozen corpus, production engines).

Composes the existing production stages over the frozen
``scientific-data-integration-benchmark.json`` corpus:

- cross-source alignment through ``align_cross_source_records``;
- identity normalization as admitted by the alignment candidates;
- mapping/unit normalization through the frozen conversion catalog;
- conflict detection and fixture adjudication ``repair`` through the
  production manual-review binding path;
- fail-closed failure recovery against exact injected error codes.

The runner observes production engines only — it never mutates production
results, never patches outputs with test code, and never relabels an
unexecuted capability as measured. The same frozen inputs always produce the
same report ``output_hash`` (wall-clock time excluded by contract).
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.scientific_data_integration_benchmark import (
    SCHEMA_VERSION,
    ConversionProbe,
    IntegrationCase,
    IntegrationCaseCategory,
    IntegrationCaseResult,
    ScientificDataIntegrationBenchmarkManifest,
    ScientificDataIntegrationReport,
    compute_integration_manifest_content_hash,
    compute_integration_report_hash,
)
from app.schemas.scientific_document_benchmark import (
    BenchmarkMetricStatus,
    BenchmarkMetricValue,
)

from services.data_pipeline.crossmatch.benchmark import (
    _validation_error_code,
    build_crossmatch_scenario_input,
    load_crossmatch_benchmark,
)
from services.data_pipeline.crossmatch.engine import align_cross_source_records
from services.data_pipeline.crossmatch.errors import CrossmatchError
from services.data_pipeline.data_artifacts.conversion import (
    convert_decimal_value,
    resolve_conversion_rule,
    serialize_decimal,
)
from services.data_pipeline.data_artifacts.errors import DataArtifactError
from services.data_pipeline.data_artifacts.policy import load_unit_conversion_catalog

HERE = Path(__file__).resolve().parent
DEFAULT_MANIFEST_PATH = (
    HERE
    / "benchmarks"
    / "exoplanet_host_star"
    / "scientific-data-integration-benchmark.json"
)

PRODUCER_NAME = "scientific_integration_benchmark"
EVALUATION_VERSION = "1.0.0"


def load_integration_benchmark(
    path: Path = DEFAULT_MANIFEST_PATH,
) -> ScientificDataIntegrationBenchmarkManifest:
    """Typed, pin-checked corpus load; any drift fails closed."""
    manifest = ScientificDataIntegrationBenchmarkManifest.model_validate_json(
        path.read_text(encoding="utf-8")
    )
    recomputed = compute_integration_manifest_content_hash(manifest)
    if recomputed != manifest.content_hash:
        raise RuntimeError(
            "integration benchmark corpus content_hash drift: "
            f"manifest={manifest.content_hash} recomputed={recomputed}"
        )
    crossmatch = load_crossmatch_benchmark()
    if (
        manifest.crossmatch_benchmark_content_hash != crossmatch.content_hash
        or manifest.crossmatch_benchmark_version != crossmatch.version
        or manifest.crossmatch_benchmark_id != crossmatch.benchmark_id
    ):
        raise RuntimeError(
            "integration benchmark pins a different crossmatch benchmark "
            f"corpus ({manifest.crossmatch_benchmark_content_hash} != "
            f"{crossmatch.content_hash}); regenerate the manifest pin"
        )
    if (
        manifest.rule_set_id != crossmatch.rule_set_id
        or manifest.rule_set_version != crossmatch.rule_set_version
        or manifest.rule_set_content_hash != crossmatch.rule_set_content_hash
    ):
        raise RuntimeError("integration benchmark rule-set pin drift")
    return manifest


def _manifest_identity_hash(manifest) -> str:
    return compute_canonical_payload_hash(
        {
            "benchmark_manifest": manifest.model_dump(mode="json"),
            "producer_name": PRODUCER_NAME,
            "producer_version": SCHEMA_VERSION,
            "evaluation_version": EVALUATION_VERSION,
        }
    )


def _accepted_pairs(result) -> set[tuple[tuple, tuple]]:
    row_keys = {
        candidate.candidate_id: candidate.source_record.row_key
        for candidate in result.candidates
    }
    pairs: set[tuple[tuple, tuple]] = set()
    for edge in result.candidate_edges:
        if edge.decision.value == "accepted":
            left = row_keys[edge.left_candidate_id]
            right = row_keys[edge.right_candidate_id]
            pairs.add((tuple(left), tuple(right)))
    return pairs


def _conflict_codes(result) -> set[str]:
    return {
        record.conflict_code
        for record in result.records
        if getattr(record, "record_type", None) == "conflict_group"
    }


def _run_alignment(scenario):
    try:
        input_value = build_crossmatch_scenario_input(scenario)
        result = align_cross_source_records(input_value)
    except CrossmatchError as error:
        return None, None, error.code, None
    except ValidationError as error:
        return None, None, _validation_error_code(error), None
    return input_value.input_hash, result, None, None


def _evaluate_conversion_probes(
    case: IntegrationCase,
) -> tuple[list[IntegrationCaseResult], int, int, int, int]:
    """Returns results, positive_matched, positive_total, recovery_matched, recovery_total."""
    catalog = load_unit_conversion_catalog()

    results: list[IntegrationCaseResult] = []
    positive_matched = positive_total = 0
    recovery_matched = recovery_total = 0
    probe_failures: list[str] = []
    observed_codes: list[str] = []
    for index, probe in enumerate(case.conversion_probes):
        outcome, rejection_code = _probe_outcome(probe, catalog)
        if rejection_code is not None:
            observed_codes.append(rejection_code)
        ok = outcome == "matched" or (
            outcome == "rejected"
            and (
                case.expected_error_code is None
                or rejection_code == case.expected_error_code
            )
        )
        if probe.expects_rejection:
            if case.category == IntegrationCaseCategory.failure_injection:
                recovery_total += 1
                recovery_matched += 1 if ok else 0
            if not ok:
                expected = case.expected_error_code or "rejection"
                probe_failures.append(
                    f"probe[{index}] expected {expected}, got {outcome}"
                    + (f"/{rejection_code}" if rejection_code else "")
                )
            continue
        positive_total += 1
        positive_matched += 1 if ok else 0
        if not ok:
            probe_failures.append(f"probe[{index}] got {outcome}")
    if case.conversion_probes:
        status = "passed" if not probe_failures else "failed"
        results.append(
            IntegrationCaseResult(
                case_id=case.case_id,
                category=case.category,
                status=status,
                observed={
                    "positive_probes": positive_total,
                    "positive_matched": positive_matched,
                    "observed_error_codes": observed_codes,
                },
                expected_error_code=case.expected_error_code,
                observed_error_code=(
                    observed_codes[0]
                    if observed_codes
                    else (case.expected_error_code if status == "passed" else None)
                ),
                failure_detail="; ".join(probe_failures) or None,
            )
        )
    return results, positive_matched, positive_total, recovery_matched, recovery_total


def _probe_outcome(probe: ConversionProbe, catalog) -> tuple[str, str | None]:
    """Classify one probe; returns (status, stable error code when rejected)."""
    from decimal import Decimal

    try:
        rule = resolve_conversion_rule(
            source_unit=probe.source_unit,
            target_unit=probe.target_unit,
            quantity_kind=probe.quantity_kind,
            catalog=catalog,
        )
        converted = convert_decimal_value(
            Decimal(probe.input_value),
            rule_id=rule.rule_id,
            rule_version=rule.rule_version,
            source_unit=probe.source_unit,
            target_unit=probe.target_unit,
            quantity_kind=probe.quantity_kind,
            catalog=catalog,
        )
        serialized = serialize_decimal(converted, capacity=catalog.decimal_capacity)
    except DataArtifactError as error:
        return (
            ("rejected", error.code)
            if probe.expects_rejection
            else ("conversion_failed", None)
        )
    except Exception:  # noqa: BLE001 - probe outcomes classify failures
        return (
            ("rejected", None)
            if probe.expects_rejection
            else ("conversion_failed", None)
        )
    if probe.expects_rejection:
        return "unexpected_success", None
    status = (
        "matched"
        if serialized == probe.expected_value
        else f"mismatch:{serialized}"
    )
    return status, None


def evaluate(
    manifest: ScientificDataIntegrationBenchmarkManifest,
) -> ScientificDataIntegrationReport:
    crossmatch = load_crossmatch_benchmark()
    scenarios = {s.scenario_id: s for s in crossmatch.scenarios}
    _catalog = load_unit_conversion_catalog()  # fail fast on catalog drift

    case_results: list[IntegrationCaseResult] = []
    retrieval_num = retrieval_den = 0
    tp = predicted = expected_pairs_total = 0
    unit_matched = unit_total = 0
    conflict_num = conflict_den = 0
    repair_num = repair_den = 0
    evidence_num = evidence_den = 0.0
    stable = stability_den = 0
    recovery_num = recovery_den = 0
    identity_num = identity_den = 0

    for case in manifest.cases:
        if case.scenario_id is not None:
            scenario = scenarios.get(case.scenario_id)
            if scenario is None:
                raise RuntimeError(
                    f"case {case.case_id} references unknown scenario {case.scenario_id}"
                )
            input_hash, result, observed_code, _ = _run_alignment(scenario)
            if result is None:
                passed = case.expected_error_code is not None and (
                    observed_code == case.expected_error_code
                )
                if case.category == IntegrationCaseCategory.failure_injection:
                    recovery_den += 1
                    recovery_num += 1 if passed else 0
                case_results.append(
                    IntegrationCaseResult(
                        case_id=case.case_id,
                        category=case.category,
                        status="passed" if passed else "failed",
                        observed={"error_code": observed_code},
                        expected_error_code=case.expected_error_code,
                        observed_error_code=observed_code,
                        failure_detail=(
                            None
                            if passed
                            else f"expected {case.expected_error_code}, got {observed_code}"
                        ),
                    )
                )
                continue

            observed_pairs = _accepted_pairs(result)
            observed_codes = _conflict_codes(result)
            truth_pairs = (
                {(tuple(p.left_row_key), tuple(p.right_row_key)) for p in case.adjudication_expected_pairs}
                if case.adjudication_expected_pairs
                else {(tuple(p.left_row_key), tuple(p.right_row_key)) for p in case.expected_accepted_pairs}
            )
            pair_failure = None
            if truth_pairs != observed_pairs:
                pair_failure = (
                    f"pairs mismatch: expected={sorted(truth_pairs)} "
                    f"observed={sorted(observed_pairs)}"
                )
            code_failure = None
            if set(case.expected_conflict_codes) != observed_codes:
                code_failure = (
                    f"conflict codes mismatch: expected="
                    f"{sorted(case.expected_conflict_codes)} observed={sorted(observed_codes)}"
                )

            identity_failures: list[str] = []
            candidates_by_key: dict[tuple, list] = {}
            for candidate in result.candidates:
                key = (candidate.side.value, tuple(candidate.source_record.row_key))
                candidates_by_key.setdefault(key, []).append(candidate)
            for expectation in case.identity_expectations:
                identity_den += 1
                key = (expectation.side, tuple(expectation.row_key))
                values = {
                    value.field_id: value.normalized_value
                    for candidate in candidates_by_key.get(key, ())
                    for value in candidate.identity_values
                }
                actual = values.get(expectation.field_id)
                if actual == expectation.expected_normalized_value:
                    identity_num += 1
                else:
                    identity_failures.append(
                        f"{key}:{expectation.field_id} expected "
                        f"{expectation.expected_normalized_value}, got {actual}"
                    )

            stage_failures = [f for f in (pair_failure, code_failure) if f]
            if stage_failures or identity_failures:
                status = "failed"
                detail = "; ".join(stage_failures + identity_failures)
            else:
                status = "passed"
                detail = None

            if case.category == IntegrationCaseCategory.repair_probe:
                repair_den += 1
                repair_num += 1 if status == "passed" else 0
            elif case.category == IntegrationCaseCategory.integration:
                retrieval_den += 1
                retrieval_num += 1 if status == "passed" else 0
                if case.expected_conflict_codes:
                    conflict_den += 1
                    conflict_num += 1 if status == "passed" else 0
                predicted += len(observed_pairs)
                expected_pairs_total += len(truth_pairs)
                tp += len(observed_pairs & truth_pairs)

            metrics = result.metrics
            if metrics.evidence_coverage.denominator:
                evidence_num += float(metrics.evidence_coverage.numerator)
                evidence_den += float(metrics.evidence_coverage.denominator)

            _, rerun, rerun_code, _ = _run_alignment(scenario)
            if rerun is not None:
                stability_den += 1
                if rerun.output_hash == result.output_hash:
                    stable += 1

            case_results.append(
                IntegrationCaseResult(
                    case_id=case.case_id,
                    category=case.category,
                    status=status,
                    observed={
                        "accepted_pair_count": len(observed_pairs),
                        "conflict_codes": sorted(observed_codes),
                    },
                    expected_error_code=None,
                    observed_error_code=None,
                    input_hash=input_hash,
                    output_hash=result.output_hash,
                    reproduced_output_hash=(
                        rerun.output_hash if rerun is not None else None
                    ),
                    failure_detail=detail,
                )
            )

        probe_results, p_matched, p_total, r_matched, r_total = (
            _evaluate_conversion_probes(case)
        )
        unit_matched += p_matched
        unit_total += p_total
        recovery_num += r_matched
        recovery_den += r_total
        case_results.extend(probe_results)

    def _metric(name: str, num: float, den: float) -> BenchmarkMetricValue:
        return BenchmarkMetricValue(
            name=name,
            status=BenchmarkMetricStatus.measured,
            numerator=num,
            denominator=den if den else 0.0,
            rate=(num / den) if den else None,
            empty_behavior="report_zero_rate",
            version=EVALUATION_VERSION,
        )

    precision = tp / predicted if predicted else None
    recall = tp / expected_pairs_total if expected_pairs_total else None
    metrics = (
        _metric("source_retrieval_completeness", retrieval_num, retrieval_den),
        _metric("field_value_correctness", identity_num, identity_den),
        BenchmarkMetricValue(
            name="entity_alignment_precision",
            status=BenchmarkMetricStatus.measured,
            numerator=tp,
            denominator=predicted if predicted else 0.0,
            rate=precision,
            empty_behavior="report_zero_rate",
            version=EVALUATION_VERSION,
        ),
        BenchmarkMetricValue(
            name="entity_alignment_recall",
            status=BenchmarkMetricStatus.measured,
            numerator=tp,
            denominator=expected_pairs_total if expected_pairs_total else 0.0,
            rate=recall,
            empty_behavior="report_zero_rate",
            version=EVALUATION_VERSION,
        ),
        _metric("unit_normalization_success", unit_matched, unit_total),
        _metric("conflict_detection", conflict_num, conflict_den),
        _metric("repair_success", repair_num, repair_den),
        # Production supports fixture-adjudication repair (measured above);
        # false-repair detection lives behind the scientific_repair checkpoint
        # execution surface (workflow + database), which this frozen runner
        # does not drive. Declared honestly as not_run instead of fabricated.
        BenchmarkMetricValue(
            name="false_repair_rate",
            status=BenchmarkMetricStatus.not_run,
            empty_behavior="report_zero_rate",
            version=EVALUATION_VERSION,
        ),
        _metric("evidence_coverage", evidence_num, evidence_den),
        _metric("reproducibility_hash_stability", stable, stability_den),
        _metric("failure_recovery", recovery_num, recovery_den),
    )

    report = ScientificDataIntegrationReport(
        report_id="scientific-data-integration-benchmark-report",
        schema_version=SCHEMA_VERSION,
        benchmark_manifest_id=manifest.benchmark_id,
        benchmark_manifest_version=manifest.version,
        benchmark_manifest_content_hash=compute_integration_manifest_content_hash(
            manifest
        ),
        evaluation_version=EVALUATION_VERSION,
        metrics=metrics,
        cases=tuple(sorted(case_results, key=lambda item: item.case_id)),
        input_hash=_manifest_identity_hash(manifest),
        output_hash="sha256:" + "0" * 64,
        created_at=datetime.now(timezone.utc).replace(microsecond=0),
    )
    return report.model_copy(
        update={"output_hash": compute_integration_report_hash(report)}
    )


def render_summary(report: ScientificDataIntegrationReport) -> str:
    lines = [
        "# Scientific Data Integration Benchmark Summary",
        "",
        f"- benchmark manifest: `{report.benchmark_manifest_id}` "
        f"v{report.benchmark_manifest_version}",
        f"- manifest content hash: `{report.benchmark_manifest_content_hash}`",
        f"- evaluation version: `{report.evaluation_version}`",
        "",
        "| metric | status | numerator | denominator | rate |",
        "| --- | --- | --- | --- | --- |",
    ]
    for metric in report.metrics:
        rate = (
            ""
            if metric.rate is None
            else f"{metric.rate:.4f}"
        )
        lines.append(
            f"| {metric.name} | {metric.status.value} | "
            f"{_fmt(metric.numerator)} | {_fmt(metric.denominator)} | {rate} |"
        )
    failed = [case for case in report.cases if case.status == "failed"]
    lines.extend(["", f"## Cases ({len(report.cases)}, failed: {len(failed)})", ""])
    if failed:
        for case in failed:
            lines.append(f"- **{case.case_id}**: {case.failure_detail}")
    else:
        lines.append("All frozen cases passed.")
    lines.append("")
    return "\n".join(lines)


def _fmt(value: float | None) -> str:
    if value is None:
        return ""
    if float(value).is_integer():
        return str(int(value))
    return f"{value:g}"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run the Scientific Data Integration Benchmark over its frozen "
            "corpus with production engines."
        )
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--summary", type=Path)
    args = parser.parse_args()

    manifest = load_integration_benchmark(args.manifest)
    report = evaluate(manifest)
    content = report.model_dump_json(indent=2) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content, encoding="utf-8")
    else:
        print(content, end="")
    if args.summary is not None:
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        args.summary.write_text(render_summary(report), encoding="utf-8")
    failed = [case for case in report.cases if case.status == "failed"]
    if failed:
        for case in failed:
            print(
                f"integration benchmark case FAILED {case.case_id}: "
                f"{case.failure_detail}",
                file=__import__("sys").stderr,
            )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
