"""Loader and deterministic evaluator for the frozen Cross-source Entity Alignment benchmark."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from pydantic import ValidationError

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.crossmatch import (
    BenchmarkPsRecord,
    BenchmarkScenarioStatus,
    BenchmarkToiRecord,
    ConflictGroup,
    CrossmatchBenchmarkManifest,
    CrossmatchBenchmarkReport,
    CrossmatchBenchmarkScenario,
    CrossmatchBenchmarkScenarioResult,
    CrossmatchInput,
    CrossmatchRuleSet,
    CrossmatchSide,
    CrossmatchSourceInput,
    EntityLevel,
    ManualReviewDecision,
    MatchDecision,
    PairedMatch,
    ReviewerKind,
    UnpairedRecord,
    compute_crossmatch_content_hash,
    compute_crossmatch_input_hash,
    compute_crossmatch_source_input_hash,
)
from app.schemas.enums import SourceMode
from app.schemas.evidence import SourceSnapshotRecord
from app.schemas.source_acquisition import (
    DataQueryCursor,
    DataSourceCompletion,
    DataSourceDataLevel,
    RawDataSourceRecord,
    SupplementalDataQueryCursor,
    compute_raw_data_record_hash,
)

from ..constants import (
    FROZEN_CASE_MANIFEST_CONTENT_HASH,
    FROZEN_CASE_MANIFEST_VERSION,
    FROZEN_FIELD_MANIFEST_CONTENT_HASH,
    FROZEN_FIELD_MANIFEST_VERSION,
)
from .engine import align_cross_source_records
from .errors import CrossmatchError
from .policy import (
    load_crossmatch_rule_set,
    load_crossmatch_source_policy,
    load_entity_alias_catalog,
)


_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CROSSMATCH_BENCHMARK_PATH = (
    _REPOSITORY_ROOT
    / "services"
    / "data_pipeline"
    / "benchmarks"
    / "exoplanet_host_star"
    / "crossmatch-benchmark.json"
)
_TOI_SOURCE_ID = "nasa_exoplanet_archive.toi"
_PS_SOURCE_ID = "nasa_exoplanet_archive.ps"


def load_crossmatch_benchmark(
    path: Path = DEFAULT_CROSSMATCH_BENCHMARK_PATH,
) -> CrossmatchBenchmarkManifest:
    resolved = path.resolve()
    if not resolved.is_relative_to(_REPOSITORY_ROOT):
        raise ValueError("crossmatch benchmark path escapes the repository")
    try:
        benchmark = CrossmatchBenchmarkManifest.model_validate_json(
            resolved.read_text(encoding="utf-8")
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError("crossmatch benchmark is not valid UTF-8 JSON") from None
    rule_set = load_crossmatch_rule_set()
    if (
        benchmark.rule_set_id != rule_set.rule_set_id
        or benchmark.rule_set_version != rule_set.version
        or benchmark.rule_set_content_hash != rule_set.content_hash
    ):
        raise ValueError("crossmatch benchmark disagrees with frozen RuleSet")
    return benchmark


def build_crossmatch_scenario_input(
    scenario: CrossmatchBenchmarkScenario,
) -> CrossmatchInput:
    """Build one frozen benchmark scenario through the public pipeline boundary."""

    return _scenario_input(scenario)


def evaluate_crossmatch_benchmark(
    benchmark: CrossmatchBenchmarkManifest,
) -> CrossmatchBenchmarkReport:
    results = tuple(_evaluate_scenario(scenario) for scenario in benchmark.scenarios)
    passed_count = sum(
        result.status is BenchmarkScenarioStatus.passed for result in results
    )
    payload = {
        "benchmark_id": benchmark.benchmark_id,
        "benchmark_version": benchmark.version,
        "benchmark_content_hash": benchmark.content_hash,
        "rule_set_content_hash": benchmark.rule_set_content_hash,
        "scenario_count": len(results),
        "passed_count": passed_count,
        "failed_count": len(results) - passed_count,
        "results": [result.model_dump(mode="json") for result in results],
    }
    payload["content_hash"] = compute_crossmatch_content_hash(payload)
    return CrossmatchBenchmarkReport.model_validate(payload)


def _evaluate_scenario(
    scenario: CrossmatchBenchmarkScenario,
) -> CrossmatchBenchmarkScenarioResult:
    expected_error = scenario.expectation.expected_error_code
    try:
        result = align_cross_source_records(_scenario_input(scenario))
    except ValidationError as error:
        observed_error = _validation_error_code(error)
        if observed_error == expected_error:
            return CrossmatchBenchmarkScenarioResult(
                scenario_id=scenario.scenario_id,
                status=BenchmarkScenarioStatus.passed,
                observed_error_code=observed_error,
            )
        return CrossmatchBenchmarkScenarioResult(
            scenario_id=scenario.scenario_id,
            status=BenchmarkScenarioStatus.failed,
            observed_error_code=observed_error,
            failure_reason=(
                f"expected error {expected_error!r}, observed {observed_error!r}"
            ),
        )
    except CrossmatchError as error:
        if error.code == expected_error:
            return CrossmatchBenchmarkScenarioResult(
                scenario_id=scenario.scenario_id,
                status=BenchmarkScenarioStatus.passed,
                observed_error_code=error.code,
            )
        return CrossmatchBenchmarkScenarioResult(
            scenario_id=scenario.scenario_id,
            status=BenchmarkScenarioStatus.failed,
            observed_error_code=error.code,
            failure_reason=(
                f"expected error {expected_error!r}, observed {error.code!r}"
            ),
        )
    if expected_error is not None:
        return CrossmatchBenchmarkScenarioResult(
            scenario_id=scenario.scenario_id,
            status=BenchmarkScenarioStatus.failed,
            result_content_hash=result.content_hash,
            failure_reason=f"expected error {expected_error!r}, observed success",
        )

    observed = _observed_expectation(result)
    expected = scenario.expectation.model_dump(
        mode="json",
        exclude={"expected_error_code"},
        exclude_none=True,
    )
    observed = {
        key: observed[key]
        for key in expected
    }
    if observed != expected:
        return CrossmatchBenchmarkScenarioResult(
            scenario_id=scenario.scenario_id,
            status=BenchmarkScenarioStatus.failed,
            result_content_hash=result.content_hash,
            failure_reason=(
                f"expected {json.dumps(expected, sort_keys=True)}, "
                f"observed {json.dumps(observed, sort_keys=True)}"
            ),
        )
    return CrossmatchBenchmarkScenarioResult(
        scenario_id=scenario.scenario_id,
        status=BenchmarkScenarioStatus.passed,
        result_content_hash=result.content_hash,
    )


def _scenario_input(scenario: CrossmatchBenchmarkScenario) -> CrossmatchInput:
    rule_set = load_crossmatch_rule_set()
    if scenario.capacity_override is not None:
        payload = rule_set.model_dump(mode="json")
        payload["capacity"] = scenario.capacity_override.model_dump(mode="json")
        payload["content_hash"] = compute_crossmatch_content_hash(payload)
        rule_set = CrossmatchRuleSet.model_validate(payload)

    left_records = tuple(_toi_raw_record(record) for record in scenario.left_records)
    right_records = tuple(_ps_raw_record(record) for record in scenario.right_records)
    left_source_payload = _source_input(
        scenario,
        side=CrossmatchSide.left,
        source_id=_TOI_SOURCE_ID,
        records=left_records,
    ).model_dump(mode="json")
    right_source_payload = _source_input(
        scenario,
        side=CrossmatchSide.right,
        source_id=_PS_SOURCE_ID,
        records=right_records,
    ).model_dump(mode="json")
    if scenario.input_fault == "duplicate_record_reference":
        left_source_payload["records"].append(
            dict(left_source_payload["records"][0])
        )
    elif scenario.input_fault == "record_source_mismatch":
        record_payload = left_source_payload["records"][0]
        record_payload["source_id"] = _PS_SOURCE_ID
        record_payload["content_hash"] = compute_raw_data_record_hash(
            source_id=_PS_SOURCE_ID,
            row_key=tuple(
                (str(field), str(value))
                for field, value in record_payload["row_key"]
            ),
            payload=record_payload["payload"],
        )
    payload = {
        "case_manifest_id": "exoplanet_host_star",
        "case_manifest_version": FROZEN_CASE_MANIFEST_VERSION,
        "case_manifest_content_hash": FROZEN_CASE_MANIFEST_CONTENT_HASH,
        "field_manifest_id": "exoplanet_host_star.fields",
        "field_manifest_version": FROZEN_FIELD_MANIFEST_VERSION,
        "field_manifest_content_hash": FROZEN_FIELD_MANIFEST_CONTENT_HASH,
        "rule_set": rule_set.model_dump(mode="json"),
        "alias_catalog": load_entity_alias_catalog().model_dump(mode="json"),
        "source_policy": load_crossmatch_source_policy().model_dump(mode="json"),
        "left": left_source_payload,
        "right": right_source_payload,
        "manual_review_decisions": (),
    }
    payload["source_input_hash"] = compute_crossmatch_source_input_hash(payload)
    payload["input_hash"] = compute_crossmatch_input_hash(payload)
    base_input = CrossmatchInput.model_validate(payload)
    if scenario.manual_adjudication is None:
        return base_input

    automatic = align_cross_source_records(base_input)
    target = next(
        record
        for record in automatic.records
        if isinstance(record, PairedMatch | ConflictGroup)
        and (
            isinstance(record, ConflictGroup)
            or record.decision is MatchDecision.review_required
        )
    )
    decision_payload = {
        "schema_version": "1.0.0",
        "decision_id": f"review.fixture.{scenario.scenario_id}",
        "logical_match_key": target.logical_match_key,
        "adjudication": scenario.manual_adjudication,
        "adjudicated_by": "crossmatch-benchmark",
        "reviewer_kind": ReviewerKind.benchmark_fixture,
        "adjudication_rule_or_actor": "benchmark.expected_decision",
        "adjudicated_at": "2026-07-30T00:00:00Z",
        "rationale": (
            "Synthetic benchmark adjudication; not a human scientific review."
        ),
        "source_input_hash": base_input.source_input_hash,
        "rule_set_id": base_input.rule_set.rule_set_id,
        "rule_set_version": base_input.rule_set.version,
        "rule_set_content_hash": base_input.rule_set.content_hash,
        "left_candidate_ids": list(target.left_candidate_ids),
        "right_candidate_ids": list(target.right_candidate_ids),
        "evidence_ids": list(target.evidence_ids),
    }
    if scenario.manual_binding == "stale_input":
        decision_payload["source_input_hash"] = "sha256:" + "f" * 64
    elif scenario.manual_binding == "stale_rule":
        decision_payload["rule_set_content_hash"] = "sha256:" + "f" * 64
    decision_payload["content_hash"] = compute_crossmatch_content_hash(
        decision_payload
    )
    decision = ManualReviewDecision.model_validate(decision_payload)
    reviewed_payload = base_input.model_dump(mode="json")
    reviewed_payload["manual_review_decisions"] = [
        decision.model_dump(mode="json")
    ]
    reviewed_payload["input_hash"] = compute_crossmatch_input_hash(
        reviewed_payload
    )
    return CrossmatchInput.model_validate(reviewed_payload)


def _source_input(
    scenario: CrossmatchBenchmarkScenario,
    *,
    side: CrossmatchSide,
    source_id: str,
    records: tuple[RawDataSourceRecord, ...],
) -> CrossmatchSourceInput:
    completion_status = (
        scenario.left_completion
        if side is CrossmatchSide.left
        else scenario.right_completion
    )
    if completion_status.value == "truncated":
        cursor = (
            DataQueryCursor(tid=9_999_999, toi="9999999.01")
            if side is CrossmatchSide.left
            else SupplementalDataQueryCursor(
                pl_name="Continuation",
                pl_refname="Reference",
            )
        )
    else:
        cursor = None
    query_hash = compute_canonical_payload_hash(
        {
            "benchmark_scenario_id": scenario.scenario_id,
            "side": side.value,
            "source_id": source_id,
        }
    )
    content_hash = compute_canonical_payload_hash(
        {
            "query_hash": query_hash,
            "record_hashes": [record.content_hash for record in records],
            "completion_status": completion_status.value,
        }
    )
    return CrossmatchSourceInput(
        source_mode=SourceMode.fixture,
        data_level=DataSourceDataLevel.fixture,
        records=records,
        snapshot=SourceSnapshotRecord(
            snapshot_id=(
                f"snapshot.crossmatch_benchmark."
                f"{scenario.scenario_id}.{side.value}"
            ),
            source_id=source_id,
            source_type="database",
            retrieved_at=datetime(2026, 7, 30, tzinfo=timezone.utc),
            query=f"synthetic benchmark scenario {scenario.scenario_id}",
            query_hash=query_hash,
            content_hash=content_hash,
            license_note=(
                "Synthetic benchmark fixture; not scientific ground truth."
            ),
            request_metadata={
                "source_mode": "fixture",
                "data_level": "fixture",
                "benchmark_scenario_id": scenario.scenario_id,
            },
        ),
        completion=DataSourceCompletion(
            status=completion_status,
            continuation_cursor=cursor,
        ),
    )


def _toi_raw_record(record: BenchmarkToiRecord) -> RawDataSourceRecord:
    payload = {
        "toi": record.toi,
        "tid": record.tic_id,
        "ra": record.right_ascension,
        "dec": record.declination,
    }
    return _raw_record(
        _TOI_SOURCE_ID,
        (("toi", record.toi),),
        payload,
    )


def _ps_raw_record(record: BenchmarkPsRecord) -> RawDataSourceRecord:
    payload = {
        "pl_name": record.planet_name,
        "pl_refname": record.reference,
        "tic_id": record.tic_id,
        "gaia_dr3_id": record.gaia_dr3_id,
        "hostname": record.hostname,
        "ra": record.right_ascension,
        "dec": record.declination,
    }
    return _raw_record(
        _PS_SOURCE_ID,
        (
            ("pl_name", record.planet_name),
            ("pl_refname", record.reference),
        ),
        payload,
    )


def _raw_record(
    source_id: str,
    row_key: tuple[tuple[str, str], ...],
    payload: dict[str, object],
) -> RawDataSourceRecord:
    return RawDataSourceRecord(
        source_id=source_id,
        row_key=row_key,
        payload=payload,
        content_hash=compute_raw_data_record_hash(
            source_id=source_id,
            row_key=row_key,
            payload=payload,
        ),
    )


def _observed_expectation(result) -> dict[str, object]:
    paired = [record for record in result.records if isinstance(record, PairedMatch)]
    conflicts = [
        record for record in result.records if isinstance(record, ConflictGroup)
    ]
    unpaired = [
        record for record in result.records if isinstance(record, UnpairedRecord)
    ]
    methods = tuple(
        sorted(
            {
                record.method.value
                for record in (*paired, *conflicts)
            }
        )
    )
    topologies = tuple(
        sorted({record.topology.value for record in paired})
    )
    return {
        "paired_count": len(paired),
        "conflict_group_count": len(conflicts),
        "unmatched_count": sum(
            record.decision is MatchDecision.unmatched for record in unpaired
        ),
        "inconclusive_count": sum(
            record.decision is MatchDecision.inconclusive for record in unpaired
        ),
        "review_required_count": sum(
            record.decision is MatchDecision.review_required for record in paired
        ),
        "manual_adjudication_count": result.metrics.manual_adjudication_count,
        "planet_assertion_count": sum(
            candidate.entity_level is EntityLevel.planet_assertion
            for candidate in result.candidates
        ),
        "methods": list(methods),
        "topologies": list(topologies),
        "conflict_codes": sorted(
            {record.conflict_code for record in conflicts}
        ),
    }


def _validation_error_code(error: ValidationError) -> str:
    message = str(error)
    if "duplicate row key" in message or "duplicate record content hash" in message:
        return "CROSSMATCH_DUPLICATE_RECORD_REFERENCE"
    if "source snapshot" in message:
        return "CROSSMATCH_RECORD_SOURCE_MISMATCH"
    if "manual decision input hash" in message:
        return "CROSSMATCH_MANUAL_DECISION_INPUT_HASH_MISMATCH"
    if "manual decision RuleSet hash" in message:
        return "CROSSMATCH_MANUAL_DECISION_RULE_SET_MISMATCH"
    return "CROSSMATCH_INPUT_VALIDATION_FAILED"
