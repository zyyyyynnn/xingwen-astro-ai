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
from datetime import datetime, timezone
from pathlib import Path
from pydantic import ValidationError

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.core import (
    RepairCheckpointContext,
    RepairDecisionInput,
    RepairRuleSetReference,
)
from app.schemas.crossmatch import (
    CrossmatchInput,
    CrossmatchResult,
    ReviewerKind,
    compute_crossmatch_input_hash,
)
from app.schemas.enums import SourceMode
from app.schemas.scientific_data_integration_benchmark import (
    SCHEMA_VERSION,
    ConversionProbe,
    IntegrationCase,
    IntegrationCaseCategory,
    IntegrationCaseResult,
    RepairAdjudication,
    ScientificDataIntegrationBenchmarkManifest,
    ScientificDataIntegrationReport,
    SourceRetrievalExpectation,
    compute_integration_manifest_content_hash,
    compute_integration_report_hash,
)
from app.schemas.scientific_document_benchmark import (
    BenchmarkMetricStatus,
    BenchmarkMetricValue,
)
from app.schemas.source_acquisition import DataSourceDataLevel
from app.workflow.steps.data_steps import (
    assess_repair_resolution,
    build_repair_manual_review_decision,
    derive_repair_defects,
    validate_repair_checkpoint,
)

from services.data_pipeline.crossmatch.benchmark import (
    _validation_error_code,
    build_crossmatch_scenario_input,
    load_crossmatch_benchmark,
)
from services.data_pipeline.crossmatch.engine import align_cross_source_records
from services.data_pipeline.crossmatch.errors import CrossmatchError
from services.data_pipeline.crossmatch.policy import load_crossmatch_rule_set
from services.data_pipeline.data_artifacts.conversion import (
    convert_decimal_value,
    resolve_conversion_rule,
    serialize_decimal,
)
from services.data_pipeline.data_artifacts.errors import DataArtifactError
from services.data_pipeline.data_artifacts.policy import load_unit_conversion_catalog
from services.data_pipeline.data_artifacts.projection import canonicalize_source_value
from services.data_pipeline.manifest import load_frozen_manifest_bundle
from services.data_pipeline.query import normalize_toi_query
from services.data_pipeline.sources.base import DataSourceAcquisitionResult
from services.data_pipeline.sources.nasa_exoplanet_archive import (
    NasaExoplanetArchiveAdapter,
)
from services.data_pipeline.sources.nasa_planetary_systems import (
    NasaPlanetarySystemsSupplementalAdapter,
)
from services.data_pipeline.sources.recorded import (
    DEFAULT_RECORDED_TOI_FIXTURE_PATH,
    RecordedNasaToiFixture,
    RecordedNasaToiTransport,
)
from services.data_pipeline.sources.supplemental_recorded import (
    DEFAULT_RECORDED_PS_FIXTURE_PATH,
    RecordedNasaPsFixture,
    RecordedNasaPsTransport,
)
from services.data_pipeline.supplemental_query import (
    normalize_ps_supplemental_query,
)

HERE = Path(__file__).resolve().parent
DEFAULT_MANIFEST_PATH = (
    HERE
    / "benchmarks"
    / "exoplanet_host_star"
    / "scientific-data-integration-benchmark.json"
)

PRODUCER_NAME = "scientific_integration_benchmark"
EVALUATION_VERSION = "2.1.0"


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


def _acquired_source_rows(
    acquisitions: dict[str, DataSourceAcquisitionResult],
) -> set[tuple[str, tuple[tuple[str, str], ...]]]:
    return {
        (side, tuple(record.row_key))
        for side, acquisition in acquisitions.items()
        for record in acquisition.records
    }


def _acquire_frozen_source_rows() -> dict[str, DataSourceAcquisitionResult]:
    """Replay the existing pinned TOI/PS transports through production adapters."""

    manifests = load_frozen_manifest_bundle()

    def fixed_clock() -> datetime:
        return datetime(2026, 8, 25, tzinfo=timezone.utc)

    toi_fixture = RecordedNasaToiFixture.model_validate_json(
        DEFAULT_RECORDED_TOI_FIXTURE_PATH.read_text(encoding="utf-8")
    )
    toi_query = normalize_toi_query(
        manifests,
        page_size=toi_fixture.pagination.page_size,
        max_pages=toi_fixture.pagination.max_pages,
        record_limit=toi_fixture.pagination.record_limit,
    )
    toi_result = NasaExoplanetArchiveAdapter(
        transport=RecordedNasaToiTransport(toi_fixture, query=toi_query),
        clock=fixed_clock,
        sleeper=lambda _: None,
    ).acquire(
        toi_query,
        source_mode=SourceMode.fixture,
        data_level=DataSourceDataLevel.recorded_response,
    )

    ps_fixture = RecordedNasaPsFixture.model_validate_json(
        DEFAULT_RECORDED_PS_FIXTURE_PATH.read_text(encoding="utf-8")
    )
    ps_query = normalize_ps_supplemental_query(
        manifests,
        tic_ids=ps_fixture.input_values,
        page_size=ps_fixture.pagination.page_size,
        max_pages=ps_fixture.pagination.max_pages,
        record_limit=ps_fixture.pagination.record_limit,
    )
    ps_result = NasaPlanetarySystemsSupplementalAdapter(
        transport=RecordedNasaPsTransport(ps_fixture, query=ps_query),
        clock=fixed_clock,
        sleeper=lambda _: None,
    ).acquire(
        ps_query,
        source_mode=SourceMode.fixture,
        data_level=DataSourceDataLevel.recorded_response,
    )
    return {"left": toi_result, "right": ps_result}


def _retrieval_expectation_is_observed(
    expectation: SourceRetrievalExpectation,
    acquisitions: dict[str, DataSourceAcquisitionResult],
) -> bool:
    acquisition = acquisitions[expectation.side]
    snapshot = acquisition.snapshot
    fixture = snapshot.request_metadata.get("fixture")
    if not isinstance(fixture, dict):
        return False
    return (
        snapshot.source_id == expectation.source_id
        and snapshot.snapshot_id == expectation.source_snapshot_id
        and snapshot.content_hash == expectation.source_snapshot_content_hash
        and snapshot.query_hash == expectation.query_hash
        and fixture.get("fixture_id") == expectation.fixture_id
        and fixture.get("content_hash") == expectation.fixture_content_hash
        and any(
            record.source_id == expectation.source_id
            and tuple(record.row_key) == tuple(expectation.row_key)
            for record in acquisition.records
        )
    )


def audit_crossmatch_evidence_closure(
    input_value: CrossmatchInput,
    result: CrossmatchResult,
) -> tuple[int, int, tuple[str, ...]]:
    """Resolve every Evidence locator to its frozen Snapshot and raw record."""

    acquisitions = {"left": input_value.left, "right": input_value.right}
    candidates = {candidate.candidate_id: candidate for candidate in result.candidates}
    covered = 0
    failures: list[str] = []

    for evidence in result.evidence:
        closed = True
        for side, candidate_id, locators in (
            ("left", evidence.left_candidate_id, evidence.left_locators),
            ("right", evidence.right_candidate_id, evidence.right_locators),
        ):
            acquisition = acquisitions[side]
            snapshot = acquisition.snapshot
            candidate = candidates.get(candidate_id)
            records = {tuple(record.row_key): record for record in acquisition.records}
            if candidate is None or candidate.side.value != side:
                closed = False
                continue
            reference = candidate.source_record
            for locator in locators:
                record = records.get(tuple(locator.row_key))
                if (
                    locator.side.value != side
                    or locator.source_snapshot_id != snapshot.snapshot_id
                    or locator.source_id != snapshot.source_id
                    or locator.query_hash != snapshot.query_hash
                    or reference.source_snapshot_id != locator.source_snapshot_id
                    or reference.source_snapshot_content_hash != snapshot.content_hash
                    or reference.source_id != locator.source_id
                    or reference.query_hash != locator.query_hash
                    or tuple(reference.row_key) != tuple(locator.row_key)
                    or record is None
                    or record.source_id != locator.source_id
                    or record.content_hash != reference.record_content_hash
                    or locator.raw_field not in record.payload
                ):
                    closed = False
        if closed:
            covered += 1
        else:
            failures.append(evidence.evidence_id)
    return covered, len(result.evidence), tuple(failures)


def _conflict_observations(result) -> set[tuple]:
    candidates = {
        candidate.candidate_id: (
            candidate.side.value,
            tuple(candidate.source_record.row_key),
        )
        for candidate in result.candidates
    }
    observations: set[tuple] = set()
    for record in result.records:
        if getattr(record, "record_type", None) != "conflict_group":
            continue
        left = tuple(
            sorted(candidates[value][1] for value in record.left_candidate_ids)
        )
        right = tuple(
            sorted(candidates[value][1] for value in record.right_candidate_ids)
        )
        observations.add((record.conflict_code, left, right))
    return observations


def _run_alignment(scenario):
    try:
        input_value = build_crossmatch_scenario_input(scenario)
        result = align_cross_source_records(input_value)
    except CrossmatchError as error:
        return None, None, error.code, None
    except ValidationError as error:
        return None, None, _validation_error_code(error), None
    return input_value, result, None, None


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
    except Exception:  # noqa: BLE001 - unexpected execution failure is not recovery
        return "execution_failed", None
    if probe.expects_rejection:
        return "unexpected_success", None
    status = (
        "matched" if serialized == probe.expected_value else f"mismatch:{serialized}"
    )
    return status, None


def _evaluate_field_value_adjudications(
    case: IntegrationCase,
) -> tuple[IntegrationCaseResult | None, int, int]:
    if not case.field_value_adjudications:
        return None, 0, 0
    bundle = load_frozen_manifest_bundle()
    catalog = load_unit_conversion_catalog()
    conversion_versions = {
        rule.rule_id: rule.rule_version
        for rule in bundle.field_manifest.conversion_rules
    }
    matched = 0
    failures: list[str] = []
    observed: list[dict[str, str]] = []
    for adjudication in case.field_value_adjudications:
        field = next(
            (
                value
                for value in bundle.field_manifest.fields
                if value.field_id == adjudication.field_id
            ),
            None,
        )
        if field is None:
            failures.append(f"unknown field {adjudication.field_id}")
            continue
        alias = next(
            (
                value
                for value in field.source_aliases
                if value.source_id == adjudication.source_id
                and value.source_table == adjudication.source_table
                and value.raw_field == adjudication.raw_field
            ),
            None,
        )
        if alias is None:
            failures.append(
                f"missing frozen alias {adjudication.field_id}:"
                f"{adjudication.source_id}:{adjudication.raw_field}"
            )
            continue
        try:
            actual = canonicalize_source_value(
                adjudication.raw_value,
                field,
                alias,
                catalog,
                bundle,
                conversion_versions,
            )
        except DataArtifactError as error:
            failures.append(f"{adjudication.field_id} failed with {error.code}")
            continue
        observed.append(
            {
                "field_id": adjudication.field_id,
                "canonical_value": actual,
                "canonical_unit": field.canonical_unit,
            }
        )
        if actual == adjudication.expected_canonical_value:
            matched += 1
        else:
            failures.append(
                f"{adjudication.field_id} expected "
                f"{adjudication.expected_canonical_value}, got {actual}"
            )
    return (
        IntegrationCaseResult(
            case_id=f"{case.case_id}.field_value",
            category=case.category,
            status="passed" if not failures else "failed",
            observed={"field_values": observed},
            failure_detail="; ".join(failures) or None,
        ),
        matched,
        len(case.field_value_adjudications),
    )


def _evaluate_repair_probe(
    case: IntegrationCase,
    *,
    input_value: CrossmatchInput,
    before_result,
) -> tuple[IntegrationCaseResult, object, int, int, int, int]:
    manifests = load_frozen_manifest_bundle()
    rules = load_crossmatch_rule_set()
    defects = derive_repair_defects(before_result, manifests=manifests)
    context = RepairCheckpointContext(
        rule_set=RepairRuleSetReference(
            rule_set_id=rules.rule_set_id,
            rule_set_version=rules.version,
            rule_set_content_hash=rules.content_hash,
        ),
        source_input_hash=input_value.source_input_hash,
        before_output_hash=before_result.output_hash,
        defects=defects,
    )
    validate_repair_checkpoint(
        context,
        defects=defects,
        rules=rules,
        source_input_hash=input_value.source_input_hash,
        before_output_hash=before_result.output_hash,
    )

    failures: list[str] = []
    decision_inputs: list[RepairDecisionInput] = []
    manual_decisions = []
    adjudication_by_defect: dict[str, RepairAdjudication] = {}
    for adjudication in case.repair_adjudications:
        matching = [
            defect
            for defect in defects
            if defect.conflict_code == adjudication.conflict_code
        ]
        if len(matching) != 1:
            failures.append(
                f"repair truth expected one {adjudication.conflict_code} defect, "
                f"observed {len(matching)}"
            )
            continue
        defect = matching[0]
        decision = RepairDecisionInput(
            defect_id=defect.defect_id,
            action=adjudication.action,
            rationale=adjudication.rationale,
        )
        decision_inputs.append(decision)
        adjudication_by_defect[defect.defect_id] = adjudication
        manual_decisions.append(
            build_repair_manual_review_decision(
                decision,
                defect=defect,
                checkpoint_id=f"benchmark-{case.case_id}",
                decided_at=adjudication.adjudicated_at,
                source_input_hash=input_value.source_input_hash,
                rules=rules,
                adjudicated_by="frozen_adjudicated_corpus",
                reviewer_kind=ReviewerKind.benchmark_fixture,
            )
        )

    payload = input_value.model_dump(mode="json")
    payload["manual_review_decisions"] = tuple(
        value.model_dump(mode="json") for value in manual_decisions
    )
    payload["input_hash"] = compute_crossmatch_input_hash(payload)
    repaired_input = CrossmatchInput.model_validate(payload)
    repaired_result = align_cross_source_records(repaired_input)
    assessment = assess_repair_resolution(
        decisions=tuple(decision_inputs),
        before_defects=defects,
        crossmatch=repaired_result,
    )
    resolved = set(assessment.resolved_defect_ids)
    repair_success_num = repair_success_den = 0
    false_repair_num = false_repair_den = 0
    for defect_id, adjudication in adjudication_by_defect.items():
        expected_resolved = adjudication.expected_resolution == "resolved"
        actually_resolved = defect_id in resolved
        if expected_resolved:
            repair_success_den += 1
            repair_success_num += int(actually_resolved)
        else:
            false_repair_den += 1
            false_repair_num += int(actually_resolved)
        if expected_resolved != actually_resolved:
            failures.append(
                f"{defect_id} expected {adjudication.expected_resolution}, got "
                f"{'resolved' if actually_resolved else 'unresolved'}"
            )
    if assessment.status == "false_repair":
        failures.append("production repair assessment reported false_repair")
    return (
        IntegrationCaseResult(
            case_id=case.case_id,
            category=case.category,
            status="passed" if not failures else "failed",
            observed={
                "checkpoint_validated": True,
                "decision_count": len(decision_inputs),
                "expected_resolution": case.repair_adjudications[0].expected_resolution,
                "repair_status": assessment.status,
                "resolved_defect_ids": list(assessment.resolved_defect_ids),
                "unresolved_defect_ids": list(assessment.unresolved_defect_ids),
            },
            input_hash=repaired_input.input_hash,
            output_hash=repaired_result.output_hash,
            failure_detail="; ".join(failures) or None,
        ),
        repaired_result,
        repair_success_num,
        repair_success_den,
        false_repair_num,
        false_repair_den,
    )


def evaluate(
    manifest: ScientificDataIntegrationBenchmarkManifest,
) -> ScientificDataIntegrationReport:
    crossmatch = load_crossmatch_benchmark()
    scenarios = {s.scenario_id: s for s in crossmatch.scenarios}
    load_unit_conversion_catalog()  # fail fast on catalog drift
    retrieval_acquisitions = _acquire_frozen_source_rows()

    case_results: list[IntegrationCaseResult] = []
    retrieval_num = retrieval_den = 0
    tp = predicted = expected_pairs_total = 0
    unit_matched = unit_total = 0
    conflict_num = conflict_den = 0
    repair_num = repair_den = 0
    false_repair_num = false_repair_den = 0
    evidence_num = evidence_den = 0.0
    stable = stability_den = 0
    recovery_num = recovery_den = 0
    field_value_num = field_value_den = 0

    for case in manifest.cases:
        if case.scenario_id is not None:
            scenario = scenarios.get(case.scenario_id)
            if scenario is None:
                raise RuntimeError(
                    f"case {case.case_id} references unknown scenario {case.scenario_id}"
                )
            input_value, result, observed_code, _ = _run_alignment(scenario)
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

            assert input_value is not None
            evaluated_result = result
            if case.category == IntegrationCaseCategory.repair_probe:
                (
                    repair_result,
                    evaluated_result,
                    repaired,
                    repair_total,
                    false_repairs,
                    no_repair_total,
                ) = _evaluate_repair_probe(
                    case,
                    input_value=input_value,
                    before_result=result,
                )
                repair_num += repaired
                repair_den += repair_total
                false_repair_num += false_repairs
                false_repair_den += no_repair_total
                case_results.append(repair_result)
            else:
                observed_pairs = _accepted_pairs(result)
                observed_codes = _conflict_codes(result)
                observed_conflicts = _conflict_observations(result)
                truth_pairs = {
                    (tuple(pair.left_row_key), tuple(pair.right_row_key))
                    for pair in case.expected_accepted_pairs
                }
                pair_failure = None
                if truth_pairs != observed_pairs:
                    pair_failure = (
                        f"pairs mismatch: expected={sorted(truth_pairs)} "
                        f"observed={sorted(observed_pairs)}"
                    )

                conflict_failures: list[str] = []
                expected_positive_conflicts: set[tuple] = set()
                for adjudication in case.conflict_adjudications:
                    expected_conflict = (
                        adjudication.conflict_code,
                        tuple(sorted(adjudication.left_row_keys)),
                        tuple(sorted(adjudication.right_row_keys)),
                    )
                    detected = expected_conflict in observed_conflicts
                    conflict_den += 1
                    if detected == adjudication.expected_detected:
                        conflict_num += 1
                    else:
                        conflict_failures.append(
                            f"conflict {expected_conflict} expected detected="
                            f"{adjudication.expected_detected}, got {detected}"
                        )
                    if adjudication.expected_detected:
                        expected_positive_conflicts.add(expected_conflict)
                unexpected_conflicts = observed_conflicts - expected_positive_conflicts
                if unexpected_conflicts:
                    conflict_failures.append(
                        "unexpected conflict observations: "
                        f"{sorted(unexpected_conflicts)}"
                    )

                retrieved_rows = _acquired_source_rows(retrieval_acquisitions)
                retrieval_failures: list[str] = []
                for expectation in case.source_retrieval_expectations:
                    retrieval_den += 1
                    expected = (expectation.side, tuple(expectation.row_key))
                    if _retrieval_expectation_is_observed(
                        expectation,
                        retrieval_acquisitions,
                    ):
                        retrieval_num += 1
                    else:
                        retrieval_failures.append(
                            f"source row not retrieved: {expected}"
                        )

                identity_failures: list[str] = []
                candidates_by_key: dict[tuple, list] = {}
                for candidate in result.candidates:
                    key = (
                        candidate.side.value,
                        tuple(candidate.source_record.row_key),
                    )
                    candidates_by_key.setdefault(key, []).append(candidate)
                for expectation in case.identity_expectations:
                    key = (expectation.side, tuple(expectation.row_key))
                    values = {
                        value.field_id: value.normalized_value
                        for candidate in candidates_by_key.get(key, ())
                        for value in candidate.identity_values
                    }
                    actual = values.get(expectation.field_id)
                    if actual != expectation.expected_normalized_value:
                        identity_failures.append(
                            f"{key}:{expectation.field_id} expected "
                            f"{expectation.expected_normalized_value}, got {actual}"
                        )

                failures = (
                    ([pair_failure] if pair_failure is not None else [])
                    + conflict_failures
                    + retrieval_failures
                    + identity_failures
                )
                status = "passed" if not failures else "failed"
                case_results.append(
                    IntegrationCaseResult(
                        case_id=case.case_id,
                        category=case.category,
                        status=status,
                        observed={
                            "accepted_pair_count": len(observed_pairs),
                            "conflict_codes": sorted(observed_codes),
                            "retrieved_source_rows": len(retrieved_rows),
                            "retrieval_source_snapshot_ids": sorted(
                                acquisition.snapshot.snapshot_id
                                for acquisition in retrieval_acquisitions.values()
                            ),
                        },
                        input_hash=input_value.input_hash,
                        output_hash=result.output_hash,
                        failure_detail="; ".join(failures) or None,
                    )
                )

                if case.category == IntegrationCaseCategory.integration:
                    predicted += len(observed_pairs)
                    expected_pairs_total += len(truth_pairs)
                    tp += len(observed_pairs & truth_pairs)

            closure_num, closure_den, closure_failures = (
                audit_crossmatch_evidence_closure(input_value, evaluated_result)
            )
            evidence_num += closure_num
            evidence_den += closure_den
            if closure_failures:
                current = case_results[-1]
                detail = f"evidence locator closure failed: {list(closure_failures)}"
                case_results[-1] = current.model_copy(
                    update={
                        "status": "failed",
                        "failure_detail": "; ".join(
                            value for value in (current.failure_detail, detail) if value
                        ),
                    }
                )

            rerun_input, rerun, _, _ = _run_alignment(scenario)
            reproduced_result = rerun
            if (
                rerun_input is not None
                and rerun is not None
                and case.category == IntegrationCaseCategory.repair_probe
            ):
                _, reproduced_result, _, _, _, _ = _evaluate_repair_probe(
                    case,
                    input_value=rerun_input,
                    before_result=rerun,
                )
            if reproduced_result is not None:
                stability_den += 1
                if reproduced_result.output_hash == evaluated_result.output_hash:
                    stable += 1

            if case_results and case_results[-1].case_id == case.case_id:
                case_results[-1] = case_results[-1].model_copy(
                    update={
                        "reproduced_output_hash": (
                            reproduced_result.output_hash
                            if reproduced_result is not None
                            else None
                        )
                    }
                )

        field_result, matched_fields, total_fields = (
            _evaluate_field_value_adjudications(case)
        )
        if field_result is not None:
            field_value_num += matched_fields
            field_value_den += total_fields
            case_results.append(field_result)

        probe_results, p_matched, p_total, r_matched, r_total = (
            _evaluate_conversion_probes(case)
        )
        unit_matched += p_matched
        unit_total += p_total
        recovery_num += r_matched
        recovery_den += r_total
        case_results.extend(probe_results)

    def _metric(name: str, num: float, den: float) -> BenchmarkMetricValue:
        if den <= 0:
            raise RuntimeError(f"metric {name} has no frozen adjudication denominator")
        return BenchmarkMetricValue(
            name=name,
            status=BenchmarkMetricStatus.measured,
            numerator=num,
            denominator=den,
            rate=num / den,
            empty_behavior="fail_closed_without_adjudication",
            version=EVALUATION_VERSION,
        )

    precision = tp / predicted if predicted else None
    recall = tp / expected_pairs_total if expected_pairs_total else None
    metrics = (
        _metric("source_retrieval_completeness", retrieval_num, retrieval_den),
        _metric("field_value_correctness", field_value_num, field_value_den),
        BenchmarkMetricValue(
            name="entity_alignment_precision",
            status=BenchmarkMetricStatus.measured,
            numerator=tp,
            denominator=predicted,
            rate=precision,
            empty_behavior="report_zero_rate",
            version=EVALUATION_VERSION,
        ),
        BenchmarkMetricValue(
            name="entity_alignment_recall",
            status=BenchmarkMetricStatus.measured,
            numerator=tp,
            denominator=expected_pairs_total,
            rate=recall,
            empty_behavior="report_zero_rate",
            version=EVALUATION_VERSION,
        ),
        _metric("unit_normalization_success", unit_matched, unit_total),
        _metric("conflict_detection", conflict_num, conflict_den),
        _metric("repair_success", repair_num, repair_den),
        _metric("false_repair_rate", false_repair_num, false_repair_den),
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
        metric_formulas=manifest.metric_formulas,
        inconclusive_policy=manifest.inconclusive_policy,
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
        f"- inconclusive handling: {report.inconclusive_policy}",
        "",
        "| metric | formula | status | numerator | denominator | rate |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for metric in report.metrics:
        rate = "" if metric.rate is None else f"{metric.rate:.4f}"
        lines.append(
            f"| {metric.name} | {report.metric_formulas[metric.name]} | "
            f"{metric.status.value} | "
            f"{_fmt(metric.numerator)} | {_fmt(metric.denominator)} | {rate} |"
        )
    retrieval_snapshots = sorted(
        {
            str(snapshot_id)
            for case in report.cases
            for snapshot_id in (
                case.observed.get("retrieval_source_snapshot_ids", [])
                if isinstance(
                    case.observed.get("retrieval_source_snapshot_ids", []), list
                )
                else []
            )
        }
    )
    evidence_metric = next(
        metric for metric in report.metrics if metric.name == "evidence_coverage"
    )
    lines.extend(
        [
            "",
            "## Acquisition and Evidence Closure",
            "",
            "- source retrieval: existing TOI/PS production adapters over their "
            "hash-pinned Recorded transports",
            "- frozen retrieval SourceSnapshots: "
            + ", ".join(f"`{value}`" for value in retrieval_snapshots),
            "- Evidence closure: each audited CrossmatchEvidence resolves both "
            "locator sides through source_snapshot_id + source_id + query_hash + "
            "row_key + raw_field to the case acquisition records",
            f"- closed Evidence: {_fmt(evidence_metric.numerator)} / "
            f"{_fmt(evidence_metric.denominator)}",
        ]
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
