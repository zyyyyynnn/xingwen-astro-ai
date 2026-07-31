from __future__ import annotations

from datetime import datetime, timezone
import json

import pytest
from pydantic import ValidationError

from app.schemas.crossmatch import (
    AdjudicationDecision,
    ConfidenceBand,
    ConflictGroup,
    CrossmatchInput,
    CrossmatchMethod,
    CrossmatchResult,
    CrossmatchRuleSet,
    CrossmatchSourceInput,
    EntityLevel,
    ManualReviewDecision,
    MatchDecision,
    MatchTopology,
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
from services.data_pipeline.constants import (
    FROZEN_CASE_MANIFEST_CONTENT_HASH,
    FROZEN_CASE_MANIFEST_VERSION,
    FROZEN_FIELD_MANIFEST_CONTENT_HASH,
    FROZEN_FIELD_MANIFEST_VERSION,
)
from services.data_pipeline.crossmatch import align_cross_source_records
from services.data_pipeline.crossmatch import engine as crossmatch_engine
from services.data_pipeline.crossmatch.errors import (
    CrossmatchCapacityError,
    CrossmatchError,
)
from services.data_pipeline.crossmatch.policy import (
    DEFAULT_SOURCE_POLICY_PATH,
    load_crossmatch_rule_set,
    load_entity_alias_catalog,
)


def raw_record(
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


def toi_record(
    toi: str,
    *,
    tic_id: int | str | None,
    ra: object = 10.0,
    dec: object = 20.0,
) -> RawDataSourceRecord:
    return raw_record(
        "nasa_exoplanet_archive.toi",
        (("toi", toi),),
        {
            "toi": toi,
            "tid": tic_id,
            "ra": ra,
            "dec": dec,
        },
    )


def ps_record(
    planet_name: str,
    reference: str,
    *,
    tic_id: int | str | None,
    gaia_id: int | str | None = None,
    hostname: str | None = None,
    ra: object = 10.0,
    dec: object = 20.0,
) -> RawDataSourceRecord:
    return raw_record(
        "nasa_exoplanet_archive.ps",
        (("pl_name", planet_name), ("pl_refname", reference)),
        {
            "pl_name": planet_name,
            "pl_refname": reference,
            "tic_id": tic_id,
            "gaia_dr3_id": gaia_id,
            "hostname": hostname,
            "ra": ra,
            "dec": dec,
        },
    )


def source_input(
    source_id: str,
    records: tuple[RawDataSourceRecord, ...],
    *,
    completion_status: str = "complete",
    source_mode: SourceMode = SourceMode.fixture,
    data_level: DataSourceDataLevel = DataSourceDataLevel.fixture,
) -> CrossmatchSourceInput:
    is_toi = source_id.endswith(".toi")
    cursor = None
    if completion_status == "truncated":
        cursor = (
            DataQueryCursor(tid=999, toi="999.01")
            if is_toi
            else SupplementalDataQueryCursor(
                pl_name="Continuation",
                pl_refname="Reference",
            )
        )
    return CrossmatchSourceInput(
        source_mode=source_mode,
        data_level=data_level,
        records=records,
        snapshot=SourceSnapshotRecord(
            snapshot_id=(
                "snapshot.crossmatch_toi"
                if is_toi
                else "snapshot.crossmatch_ps"
            ),
            source_id=source_id,
            source_type="database",
            retrieved_at=datetime(2026, 7, 30, tzinfo=timezone.utc),
            query="synthetic C-08 benchmark input",
            query_hash="sha256:" + ("1" if is_toi else "2") * 64,
            content_hash="sha256:" + ("3" if is_toi else "4") * 64,
            license_note="Synthetic benchmark fixture; not scientific ground truth.",
            request_metadata={
                "source_mode": source_mode.value,
                "data_level": data_level.value,
            },
        ),
        completion=DataSourceCompletion(
            status=completion_status,
            continuation_cursor=cursor,
        ),
    )


def crossmatch_input(
    left_records: tuple[RawDataSourceRecord, ...],
    right_records: tuple[RawDataSourceRecord, ...],
    *,
    left_completion: str = "complete",
    right_completion: str = "complete",
    rule_set: CrossmatchRuleSet | None = None,
    left_source_mode: SourceMode = SourceMode.fixture,
    left_data_level: DataSourceDataLevel = DataSourceDataLevel.fixture,
    right_source_mode: SourceMode = SourceMode.fixture,
    right_data_level: DataSourceDataLevel = DataSourceDataLevel.fixture,
) -> CrossmatchInput:
    payload = {
        "case_manifest_id": "exoplanet_host_star",
        "case_manifest_version": FROZEN_CASE_MANIFEST_VERSION,
        "case_manifest_content_hash": FROZEN_CASE_MANIFEST_CONTENT_HASH,
        "field_manifest_id": "exoplanet_host_star.fields",
        "field_manifest_version": FROZEN_FIELD_MANIFEST_VERSION,
        "field_manifest_content_hash": FROZEN_FIELD_MANIFEST_CONTENT_HASH,
        "rule_set": (rule_set or load_crossmatch_rule_set()).model_dump(mode="json"),
        "alias_catalog": load_entity_alias_catalog().model_dump(mode="json"),
        "source_policy": json.loads(
            DEFAULT_SOURCE_POLICY_PATH.read_text(encoding="utf-8")
        ),
        "left": source_input(
            "nasa_exoplanet_archive.toi",
            left_records,
            completion_status=left_completion,
            source_mode=left_source_mode,
            data_level=left_data_level,
        ).model_dump(mode="json"),
        "right": source_input(
            "nasa_exoplanet_archive.ps",
            right_records,
            completion_status=right_completion,
            source_mode=right_source_mode,
            data_level=right_data_level,
        ).model_dump(mode="json"),
        "manual_review_decisions": [],
    }
    payload["source_input_hash"] = compute_crossmatch_source_input_hash(payload)
    payload["input_hash"] = compute_crossmatch_input_hash(payload)
    return CrossmatchInput.model_validate(payload)


def rehash_result_payload(payload: dict[str, object]) -> None:
    payload["content_hash"] = compute_crossmatch_content_hash(payload)
    payload["output_hash"] = payload["content_hash"]
    payload["result_id"] = (
        f"crossmatch.{str(payload['content_hash']).removeprefix('sha256:')[:24]}"
    )


def rule_set_with_capacity(
    *,
    max_left_records: int,
    max_right_records: int,
    max_candidate_pairs: int,
) -> CrossmatchRuleSet:
    payload = load_crossmatch_rule_set().model_dump(mode="json")
    payload["capacity"] = {
        "max_left_records": max_left_records,
        "max_right_records": max_right_records,
        "max_candidate_pairs": max_candidate_pairs,
    }
    payload["content_hash"] = compute_crossmatch_content_hash(payload)
    return CrossmatchRuleSet.model_validate(payload)


@pytest.mark.parametrize(
    ("source_mode", "data_level"),
    [
        (SourceMode.fixture, DataSourceDataLevel.fixture),
        (SourceMode.fixture, DataSourceDataLevel.recorded_response),
        (SourceMode.live, DataSourceDataLevel.live_result),
    ],
)
def test_crossmatch_contract_accepts_origins_allowed_by_frozen_source_policy(
    source_mode: SourceMode,
    data_level: DataSourceDataLevel,
) -> None:
    input_value = crossmatch_input(
        (toi_record("90.01", tic_id=90),),
        (ps_record("Policy b", "Reference", tic_id=90),),
        left_source_mode=source_mode,
        left_data_level=data_level,
    )

    allowed = {
        origin.source_mode: set(origin.data_levels)
        for origin in input_value.source_policy.allowed_origins
    }
    assert data_level in allowed[source_mode]


@pytest.mark.parametrize(
    ("source_mode", "data_level"),
    [
        (SourceMode.fixture, DataSourceDataLevel.seed),
        (SourceMode.live, DataSourceDataLevel.fixture),
        (SourceMode.fixture, DataSourceDataLevel.live_result),
    ],
)
def test_crossmatch_contract_rejects_origins_absent_from_frozen_source_policy(
    source_mode: SourceMode,
    data_level: DataSourceDataLevel,
) -> None:
    with pytest.raises(ValidationError, match="frozen SourcePolicy"):
        crossmatch_input(
            (toi_record("91.01", tic_id=91),),
            (ps_record("Policy c", "Reference", tic_id=91),),
            left_source_mode=source_mode,
            left_data_level=data_level,
        )


def paired_records(result) -> list[PairedMatch]:
    return [record for record in result.records if isinstance(record, PairedMatch)]


def conflict_records(result) -> list[ConflictGroup]:
    return [record for record in result.records if isinstance(record, ConflictGroup)]


def test_same_tic_matches_only_host_and_preserves_planet_assertions() -> None:
    result = align_cross_source_records(
        crossmatch_input(
            (toi_record("100.01", tic_id=123),),
            (
                ps_record("Planet b", "Reference A", tic_id="TIC 123"),
                ps_record("Planet b", "Reference B", tic_id="123"),
            ),
        )
    )

    host_match = next(
        record
        for record in paired_records(result)
        if record.entity_level is EntityLevel.host_star
    )
    assert host_match.method is CrossmatchMethod.exact_identifier
    assert host_match.decision is MatchDecision.accepted
    assert host_match.topology is MatchTopology.one_to_many
    assert all(
        record.entity_level is EntityLevel.host_star
        for record in paired_records(result)
    )

    assertions = [
        candidate
        for candidate in result.candidates
        if candidate.entity_level is EntityLevel.planet_assertion
    ]
    assert len(assertions) == 2
    assert {candidate.source_record.row_key for candidate in assertions} == {
        (("pl_name", "Planet b"), ("pl_refname", "Reference A")),
        (("pl_name", "Planet b"), ("pl_refname", "Reference B")),
    }
    assert all(
        isinstance(record, UnpairedRecord)
        for record in result.records
        if record.entity_level
        in {EntityLevel.planet_candidate, EntityLevel.planet_assertion}
    )
    assert result.metrics.matched_group_count == 1
    assert result.metrics.unmatched_left_record_count == 1
    assert result.metrics.unmatched_right_record_count == 2
    assert result.metrics.one_to_many_count == 1
    assert result.metrics.method_distribution.exact_identifier == 2
    assert result.metrics.confidence_distribution.high == 2
    assert result.metrics.error_example_references

    evidence = next(
        item for item in result.evidence if item.evidence_id in host_match.evidence_ids
    )
    assert evidence.left_locators[0].source_snapshot_id == (
        result.left_source_snapshot.snapshot_id
    )
    assert evidence.right_locators[0].source_snapshot_id == (
        result.right_source_snapshot.snapshot_id
    )
    assert evidence.rule_set_content_hash == result.rule_set_content_hash


@pytest.mark.parametrize(
    ("left_count", "right_count", "expected"),
    [
        (1, 1, MatchTopology.one_to_one),
        (1, 2, MatchTopology.one_to_many),
        (2, 1, MatchTopology.many_to_one),
        (2, 2, MatchTopology.many_to_many),
    ],
)
def test_exact_identifier_topologies_are_explicit(
    left_count: int,
    right_count: int,
    expected: MatchTopology,
) -> None:
    left = tuple(
        toi_record(f"200.{index + 1:02d}", tic_id=222)
        for index in range(left_count)
    )
    right = tuple(
        ps_record("Planet Two b", f"Reference {index}", tic_id="TIC 222")
        for index in range(right_count)
    )

    result = align_cross_source_records(crossmatch_input(left, right))

    host_match = next(
        record
        for record in paired_records(result)
        if record.entity_level is EntityLevel.host_star
    )
    assert host_match.topology is expected
    assert len(host_match.left_candidate_ids) == left_count
    assert len(host_match.right_candidate_ids) == right_count


def test_coordinate_only_candidate_requires_review() -> None:
    result = align_cross_source_records(
        crossmatch_input(
            (toi_record("300.01", tic_id=None, ra=359.99975, dec=45.0),),
            (
                ps_record(
                    "Coordinate Planet b",
                    "Reference",
                    tic_id=None,
                    ra=0.00025,
                    dec=45.0,
                ),
            ),
        )
    )

    coordinate_match = next(
        record
        for record in paired_records(result)
        if record.entity_level is EntityLevel.host_star
    )
    assert coordinate_match.method is CrossmatchMethod.coordinate
    assert coordinate_match.decision is MatchDecision.review_required
    assert coordinate_match.confidence_band is ConfidenceBand.low
    assert result.metrics.ambiguous_group_count == 1
    assert result.metrics.manual_review_required_count == 1
    assert result.metrics.method_distribution.coordinate == 1
    assert result.metrics.confidence_distribution.low == 1


def test_curated_alias_plus_host_identifier_is_compound_planet_match() -> None:
    result = align_cross_source_records(
        crossmatch_input(
            (toi_record("700.01", tic_id=700),),
            (
                ps_record(
                    "Planet Seven b",
                    "Reference",
                    tic_id="TIC 700",
                ),
            ),
        )
    )

    planet_match = next(
        record
        for record in paired_records(result)
        if record.entity_level is EntityLevel.planet_candidate
    )
    assert planet_match.method is CrossmatchMethod.compound
    assert planet_match.decision is MatchDecision.accepted


def test_conflicting_curated_aliases_form_reviewable_conflict_group() -> None:
    result = align_cross_source_records(
        crossmatch_input(
            (toi_record("900.01", tic_id=900),),
            (
                ps_record("Planet Nine b", "Reference B", tic_id="TIC 900"),
                ps_record("Planet Nine c", "Reference C", tic_id="TIC 900"),
            ),
        )
    )

    alias_conflict = next(
        record
        for record in conflict_records(result)
        if record.entity_level is EntityLevel.planet_candidate
    )
    assert alias_conflict.method is CrossmatchMethod.compound
    assert alias_conflict.decision is MatchDecision.conflict
    assert alias_conflict.conflict_code == "crossmatch.alias_conflict"


@pytest.mark.parametrize(
    ("opposite_completion", "expected"),
    [
        ("complete", MatchDecision.unmatched),
        ("truncated", MatchDecision.inconclusive),
        ("unknown", MatchDecision.inconclusive),
    ],
)
def test_no_candidate_semantics_follow_opposite_source_completion(
    opposite_completion: str,
    expected: MatchDecision,
) -> None:
    result = align_cross_source_records(
        crossmatch_input(
            (toi_record("400.01", tic_id=444),),
            (),
            right_completion=opposite_completion,
        )
    )

    assert result.records
    assert all(
        isinstance(record, UnpairedRecord) and record.decision is expected
        for record in result.records
    )
    if expected is MatchDecision.unmatched:
        assert result.metrics.unmatched_rate.numerator == len(result.records)
        assert result.metrics.inconclusive_record_count == 0
    else:
        assert result.metrics.unmatched_rate.numerator == 0
        assert result.metrics.inconclusive_record_count == len(result.records)


def test_crossmatch_rejects_capacity_excess_without_truncating() -> None:
    input_value = crossmatch_input(
        (
            toi_record("500.01", tic_id=500),
            toi_record("500.02", tic_id=500),
        ),
        (ps_record("Planet Five b", "Reference", tic_id="TIC 500"),),
        rule_set=rule_set_with_capacity(
            max_left_records=1,
            max_right_records=1,
            max_candidate_pairs=1,
        ),
    )

    with pytest.raises(CrossmatchCapacityError) as error:
        align_cross_source_records(input_value)

    assert error.value.code == "CROSSMATCH_CAPACITY_EXCEEDED"


def test_capacity_allows_raw_record_counts_at_both_limits() -> None:
    result = align_cross_source_records(
        crossmatch_input(
            (
                toi_record("510.01", tic_id=510),
                toi_record("511.01", tic_id=511),
            ),
            (
                ps_record("Limit b", "Reference 1", tic_id=510),
                ps_record("Limit c", "Reference 2", tic_id=511),
            ),
            rule_set=rule_set_with_capacity(
                max_left_records=2,
                max_right_records=2,
                max_candidate_pairs=9,
            ),
        )
    )

    assert result.metrics.left_record_count == 2
    assert result.metrics.right_record_count == 2


def test_capacity_allows_eligible_candidate_pairs_at_exact_limit() -> None:
    result = align_cross_source_records(
        crossmatch_input(
            (
                toi_record("520.01", tic_id=520),
                toi_record("521.01", tic_id=521),
            ),
            (ps_record("Exact limit b", "Reference", tic_id=520),),
            rule_set=rule_set_with_capacity(
                max_left_records=2,
                max_right_records=1,
                max_candidate_pairs=4,
            ),
        )
    )

    assert result.metrics.left_candidate_count == 4
    assert result.metrics.right_candidate_count == 2


def test_capacity_rejects_eligible_candidate_pairs_over_limit_by_one() -> None:
    input_value = crossmatch_input(
        (toi_record("530.01", tic_id=530),),
        (ps_record("Over limit b", "Reference", tic_id=530),),
        rule_set=rule_set_with_capacity(
            max_left_records=1,
            max_right_records=1,
            max_candidate_pairs=1,
        ),
    )

    with pytest.raises(CrossmatchCapacityError) as error:
        align_cross_source_records(input_value)

    assert error.value.code == "CROSSMATCH_CAPACITY_EXCEEDED"


def test_capacity_counts_both_entity_level_comparison_spaces() -> None:
    input_value = crossmatch_input(
        (
            toi_record("540.01", tic_id=540),
            toi_record("541.01", tic_id=541),
        ),
        (
            ps_record("Double layer b", "Reference 1", tic_id=540),
            ps_record("Double layer c", "Reference 2", tic_id=541),
        ),
        rule_set=rule_set_with_capacity(
            max_left_records=2,
            max_right_records=2,
            max_candidate_pairs=4,
        ),
    )

    with pytest.raises(CrossmatchCapacityError) as error:
        align_cross_source_records(input_value)

    assert error.value.code == "CROSSMATCH_CAPACITY_EXCEEDED"


def test_capacity_failure_precedes_any_matching_loop(monkeypatch) -> None:
    match_calls = 0

    def record_match_call(*args, **kwargs):
        nonlocal match_calls
        match_calls += 1
        return None

    monkeypatch.setattr(
        crossmatch_engine,
        "_match_host_candidates",
        record_match_call,
    )
    input_value = crossmatch_input(
        (toi_record("550.01", tic_id=550),),
        (ps_record("No partial b", "Reference", tic_id=550),),
        rule_set=rule_set_with_capacity(
            max_left_records=1,
            max_right_records=1,
            max_candidate_pairs=1,
        ),
    )

    with pytest.raises(CrossmatchCapacityError):
        align_cross_source_records(input_value)

    assert match_calls == 0


def test_capacity_decision_is_stable_under_input_reordering() -> None:
    left = (
        toi_record("560.01", tic_id=560),
        toi_record("561.01", tic_id=561),
    )
    right = (
        ps_record("Reorder b", "Reference 1", tic_id=560),
        ps_record("Reorder c", "Reference 2", tic_id=561),
    )
    rule_set = rule_set_with_capacity(
        max_left_records=2,
        max_right_records=2,
        max_candidate_pairs=7,
    )

    for left_records, right_records in (
        (left, right),
        (tuple(reversed(left)), tuple(reversed(right))),
    ):
        with pytest.raises(CrossmatchCapacityError) as error:
            align_cross_source_records(
                crossmatch_input(
                    left_records,
                    right_records,
                    rule_set=rule_set,
                )
            )
        assert error.value.code == "CROSSMATCH_CAPACITY_EXCEEDED"


def test_crossmatch_order_identity_and_hash_are_stable_under_input_reordering() -> None:
    left = (
        toi_record("600.01", tic_id=600),
        toi_record("601.01", tic_id=601),
    )
    right = (
        ps_record("Planet Six b", "Reference 1", tic_id="TIC 600"),
        ps_record("Planet Six c", "Reference 2", tic_id="TIC 601"),
    )

    first = align_cross_source_records(crossmatch_input(left, right))
    second = align_cross_source_records(
        crossmatch_input(tuple(reversed(left)), tuple(reversed(right)))
    )

    assert first == second
    assert first.content_hash == second.content_hash
    assert all(
        record.logical_match_key != record.content_hash
        for record in first.records
        if isinstance(record, PairedMatch | ConflictGroup)
    )
    assert all(
        identity.normalization_rule_version == "1.0.0"
        for candidate in first.candidates
        for identity in candidate.identity_values
    )
    assert [record.record_type for record in first.records] == [
        record.record_type for record in second.records
    ]


def test_coordinate_evidence_records_both_thresholds_and_confidence_effect() -> None:
    result = align_cross_source_records(
        crossmatch_input(
            (toi_record("605.01", tic_id=None, ra=10.0, dec=20.0),),
            (
                ps_record(
                    "Coordinate Evidence b",
                    "Reference",
                    tic_id=None,
                    ra=10.00025,
                    dec=20.0,
                ),
            ),
        )
    )
    evidence = next(
        item
        for item in result.evidence
        if item.method is CrossmatchMethod.coordinate
    )
    condition = next(
        item
        for item in evidence.conditions
        if item.separation_arcsec is not None
    )

    assert condition.strict_threshold_arcsec == 1.0
    assert condition.manual_review_threshold_arcsec == 2.0
    assert evidence.confidence == 0.7
    assert evidence.confidence_band is ConfidenceBand.medium


def test_coordinate_threshold_change_changes_decision_evidence_and_output_hash() -> None:
    left = (toi_record("607.01", tic_id=None, ra=10.0, dec=20.0),)
    right = (
        ps_record(
            "Threshold Change b",
            "Reference",
            tic_id=None,
            ra=10.00025,
            dec=20.0,
        ),
    )
    original = align_cross_source_records(crossmatch_input(left, right))
    rule_payload = load_crossmatch_rule_set().model_dump(mode="json")
    rule_payload["coordinate"]["strict_separation_arcsec"] = 0.5
    rule_payload["content_hash"] = compute_crossmatch_content_hash(rule_payload)
    changed = align_cross_source_records(
        crossmatch_input(
            left,
            right,
            rule_set=CrossmatchRuleSet.model_validate(rule_payload),
        )
    )

    original_edge = next(
        edge
        for edge in original.candidate_edges
        if edge.method is CrossmatchMethod.coordinate
    )
    changed_edge = next(
        edge
        for edge in changed.candidate_edges
        if edge.method is CrossmatchMethod.coordinate
    )
    assert original_edge.confidence_band is ConfidenceBand.medium
    assert changed_edge.confidence_band is ConfidenceBand.low
    assert original.output_hash != changed.output_hash


def test_source_input_rejects_duplicate_rows_hashes_and_source_mismatch() -> None:
    record = toi_record("610.01", tic_id=610)
    valid = source_input("nasa_exoplanet_archive.toi", (record,))
    duplicate_payload = valid.model_dump(mode="json")
    duplicate_payload["records"] = [
        record.model_dump(mode="json"),
        record.model_dump(mode="json"),
    ]

    with pytest.raises(ValidationError, match="duplicate row key"):
        CrossmatchSourceInput.model_validate(duplicate_payload)

    wrong_source_payload = valid.model_dump(mode="json")
    wrong_source_payload["records"] = [
        ps_record(
            "Wrong Source b",
            "Reference",
            tic_id="TIC 610",
        ).model_dump(mode="json")
    ]
    with pytest.raises(ValidationError, match="source snapshot"):
        CrossmatchSourceInput.model_validate(wrong_source_payload)


def test_crossmatch_rejects_reversed_primary_and_supplemental_sources() -> None:
    original = crossmatch_input(
        (toi_record("615.01", tic_id=615),),
        (ps_record("Reversed b", "Reference", tic_id="TIC 615"),),
    )
    payload = original.model_dump(mode="json")
    payload["left"], payload["right"] = payload["right"], payload["left"]
    payload["source_input_hash"] = compute_crossmatch_source_input_hash(payload)
    payload["input_hash"] = compute_crossmatch_input_hash(payload)
    reversed_input = CrossmatchInput.model_validate(payload)

    with pytest.raises(CrossmatchError) as error:
        align_cross_source_records(reversed_input)

    assert error.value.code == "CROSSMATCH_SOURCE_CONTRACT_MISMATCH"


def test_crossmatch_input_hash_binds_snapshots_records_and_rules() -> None:
    left = (toi_record("620.01", tic_id=620),)
    right = (ps_record("Hash Planet b", "Reference", tic_id="TIC 620"),)
    original = crossmatch_input(left, right)

    changed_snapshot_payload = original.model_dump(mode="json")
    changed_snapshot_payload["left"]["snapshot"]["query_hash"] = "sha256:" + "a" * 64
    changed_snapshot_payload["source_input_hash"] = (
        compute_crossmatch_source_input_hash(changed_snapshot_payload)
    )
    changed_snapshot_payload["input_hash"] = compute_crossmatch_input_hash(
        changed_snapshot_payload
    )
    changed_snapshot = CrossmatchInput.model_validate(changed_snapshot_payload)

    changed_record = crossmatch_input(
        (toi_record("620.01", tic_id=621),),
        right,
    )

    changed_rule_payload = original.rule_set.model_dump(mode="json")
    changed_rule_payload["coordinate"]["strict_separation_arcsec"] = 0.5
    changed_rule_payload["content_hash"] = compute_crossmatch_content_hash(
        changed_rule_payload
    )
    changed_rule = crossmatch_input(
        left,
        right,
        rule_set=CrossmatchRuleSet.model_validate(changed_rule_payload),
    )

    assert len(
        {
            original.input_hash,
            changed_snapshot.input_hash,
            changed_record.input_hash,
            changed_rule.input_hash,
        }
    ) == 4

    tampered = original.model_dump(mode="json")
    tampered["source_input_hash"] = "sha256:" + "f" * 64
    with pytest.raises(ValidationError, match="source_input_hash"):
        CrossmatchInput.model_validate(tampered)


def test_crossmatch_result_rejects_output_tampering() -> None:
    result = align_cross_source_records(
        crossmatch_input(
            (toi_record("630.01", tic_id=630),),
            (ps_record("Hash Output b", "Reference", tic_id="TIC 630"),),
        )
    )
    tampered = result.model_dump(mode="json")
    tampered["metrics"]["left_record_count"] = 2

    with pytest.raises(ValidationError, match="content_hash"):
        CrossmatchResult.model_validate(tampered)


def test_crossmatch_result_rejects_rehashed_snapshot_reference_mismatch() -> None:
    result = align_cross_source_records(
        crossmatch_input(
            (toi_record("635.01", tic_id=635),),
            (ps_record("Bound Output b", "Reference", tic_id="TIC 635"),),
        )
    )
    tampered = result.model_dump(mode="json")
    candidate = tampered["candidates"][0]
    candidate["source_record"]["source_snapshot_id"] = (
        result.right_source_snapshot.snapshot_id
    )
    candidate["content_hash"] = compute_crossmatch_content_hash(candidate)
    tampered["content_hash"] = compute_crossmatch_content_hash(tampered)
    tampered["output_hash"] = tampered["content_hash"]
    tampered["result_id"] = (
        f"crossmatch.{tampered['content_hash'].removeprefix('sha256:')[:24]}"
    )

    with pytest.raises(ValidationError, match="Snapshot"):
        CrossmatchResult.model_validate(tampered)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("row_key", [["toi", "different-row"]]),
        ("raw_field", "unrelated_raw_field"),
    ],
)
def test_crossmatch_result_rejects_rehashed_evidence_locator_tampering(
    field: str,
    value: object,
) -> None:
    result = align_cross_source_records(
        crossmatch_input(
            (toi_record("636.01", tic_id=636),),
            (ps_record("Locator Bound b", "Reference", tic_id="TIC 636"),),
        )
    )
    tampered = result.model_dump(mode="json")
    evidence = tampered["evidence"][0]
    evidence["left_locators"][0][field] = value
    evidence["content_hash"] = compute_crossmatch_content_hash(evidence)
    rehash_result_payload(tampered)

    with pytest.raises(ValidationError, match="Evidence locator disagrees with candidate"):
        CrossmatchResult.model_validate(tampered)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("decision", MatchDecision.accepted.value),
        ("logical_match_key", "sha256:" + "a" * 64),
    ],
)
def test_crossmatch_result_rejects_rehashed_record_semantic_tampering(
    field: str,
    value: str,
) -> None:
    result = align_cross_source_records(
        crossmatch_input(
            (toi_record("637.01", tic_id=None, ra=10.0, dec=20.0),),
            (
                ps_record(
                    "Semantic Review b",
                    "Reference",
                    tic_id=None,
                    ra=10.00025,
                    dec=20.0,
                ),
            ),
        )
    )
    tampered = result.model_dump(mode="json")
    record = next(
        item
        for item in tampered["records"]
        if item["record_type"] == "paired"
        and item["entity_level"] == EntityLevel.host_star.value
    )
    record[field] = value
    if field == "decision":
        record["method"] = CrossmatchMethod.exact_identifier.value
    record["content_hash"] = compute_crossmatch_content_hash(record)
    rehash_result_payload(tampered)

    with pytest.raises(ValidationError, match="record semantics disagree"):
        CrossmatchResult.model_validate(tampered)


def test_crossmatch_result_rejects_rehashed_conflict_evidence_omission() -> None:
    result = align_cross_source_records(
        crossmatch_input(
            (toi_record("900.01", tic_id=900),),
            (
                ps_record("Planet Nine b", "Reference B", tic_id="TIC 900"),
                ps_record("Planet Nine c", "Reference C", tic_id="TIC 900"),
            ),
        )
    )
    tampered = result.model_dump(mode="json")
    record = next(
        item
        for item in tampered["records"]
        if item["record_type"] == "conflict_group"
        and item["entity_level"] == EntityLevel.planet_candidate.value
    )
    assert len(record["evidence_ids"]) > 1
    record["evidence_ids"] = record["evidence_ids"][:-1]
    record["content_hash"] = compute_crossmatch_content_hash(record)
    rehash_result_payload(tampered)

    with pytest.raises(ValidationError, match="record semantics disagree"):
        CrossmatchResult.model_validate(tampered)


def test_manual_review_decision_is_auditable_and_preserves_automatic_status() -> None:
    automatic_input = crossmatch_input(
        (toi_record("640.01", tic_id=None, ra=10.0, dec=20.0),),
        (
            ps_record(
                "Review Planet b",
                "Reference",
                tic_id=None,
                ra=10.00025,
                dec=20.0,
            ),
        ),
    )
    automatic = align_cross_source_records(automatic_input)
    target = next(
        record
        for record in paired_records(automatic)
        if record.decision is MatchDecision.review_required
    )
    decision_payload = {
        "schema_version": "1.0.0",
        "decision_id": "review.fixture.coordinate_640",
        "logical_match_key": target.logical_match_key,
        "adjudication": AdjudicationDecision.accepted,
        "adjudicated_by": "benchmark-reviewer",
        "reviewer_kind": ReviewerKind.benchmark_fixture,
        "adjudication_rule_or_actor": "benchmark.expected_decision",
        "adjudicated_at": "2026-07-30T00:00:00Z",
        "rationale": "Synthetic benchmark adjudication; not a human scientific review.",
        "source_input_hash": automatic_input.source_input_hash,
        "rule_set_id": automatic_input.rule_set.rule_set_id,
        "rule_set_version": automatic_input.rule_set.version,
        "rule_set_content_hash": automatic_input.rule_set.content_hash,
        "left_candidate_ids": list(target.left_candidate_ids),
        "right_candidate_ids": list(target.right_candidate_ids),
        "evidence_ids": list(target.evidence_ids),
    }
    decision_payload["content_hash"] = compute_crossmatch_content_hash(
        decision_payload
    )
    decision = ManualReviewDecision.model_validate(decision_payload)
    reviewed_payload = automatic_input.model_dump(mode="json")
    reviewed_payload["manual_review_decisions"] = [
        decision.model_dump(mode="json")
    ]
    reviewed_payload["input_hash"] = compute_crossmatch_input_hash(reviewed_payload)
    reviewed_input = CrossmatchInput.model_validate(reviewed_payload)

    reviewed = align_cross_source_records(reviewed_input)
    reviewed_target = next(
        record
        for record in paired_records(reviewed)
        if record.logical_match_key == target.logical_match_key
    )

    assert reviewed_target.decision is MatchDecision.review_required
    assert reviewed_target.adjudication is AdjudicationDecision.accepted
    assert reviewed_target.manual_decision_id == decision.decision_id
    assert reviewed_target.manual_decision_content_hash == decision.content_hash
    assert reviewed.metrics.manual_adjudication_count == 1
    assert reviewed.input_hash != automatic.input_hash
    assert reviewed.output_hash != automatic.output_hash


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("source_input_hash", "manual decision input hash"),
        ("rule_set_content_hash", "manual decision RuleSet hash"),
    ],
)
def test_stale_manual_review_decision_is_rejected(
    field: str,
    message: str,
) -> None:
    base = crossmatch_input(
        (toi_record("650.01", tic_id=None),),
        (ps_record("Stale Review b", "Reference", tic_id=None),),
    )
    decision_payload = {
        "schema_version": "1.0.0",
        "decision_id": "review.fixture.stale",
        "logical_match_key": "sha256:" + "1" * 64,
        "adjudication": "keep_unresolved",
        "adjudicated_by": "benchmark-reviewer",
        "reviewer_kind": "benchmark_fixture",
        "adjudication_rule_or_actor": "benchmark.expected_decision",
        "adjudicated_at": "2026-07-30T00:00:00Z",
        "rationale": "Synthetic stale-binding rejection case.",
        "source_input_hash": base.source_input_hash,
        "rule_set_id": base.rule_set.rule_set_id,
        "rule_set_version": base.rule_set.version,
        "rule_set_content_hash": base.rule_set.content_hash,
        "left_candidate_ids": ["candidate.left.stale"],
        "right_candidate_ids": ["candidate.right.stale"],
        "evidence_ids": ["evidence.stale"],
    }
    decision_payload[field] = "sha256:" + "f" * 64
    decision_payload["content_hash"] = compute_crossmatch_content_hash(
        decision_payload
    )
    payload = base.model_dump(mode="json")
    payload["manual_review_decisions"] = [decision_payload]
    payload["input_hash"] = compute_crossmatch_input_hash(payload)

    with pytest.raises(ValidationError, match=message):
        CrossmatchInput.model_validate(payload)


def test_manual_review_candidate_binding_mismatch_is_rejected() -> None:
    automatic_input = crossmatch_input(
        (toi_record("660.01", tic_id=None, ra=10.0, dec=20.0),),
        (
            ps_record(
                "Bound Review b",
                "Reference",
                tic_id=None,
                ra=10.00025,
                dec=20.0,
            ),
        ),
    )
    automatic = align_cross_source_records(automatic_input)
    target = next(record for record in paired_records(automatic))
    decision_payload = {
        "schema_version": "1.0.0",
        "decision_id": "review.fixture.bad_binding",
        "logical_match_key": target.logical_match_key,
        "adjudication": "rejected",
        "adjudicated_by": "benchmark-reviewer",
        "reviewer_kind": "benchmark_fixture",
        "adjudication_rule_or_actor": "benchmark.expected_decision",
        "adjudicated_at": "2026-07-30T00:00:00Z",
        "rationale": "Synthetic invalid candidate binding.",
        "source_input_hash": automatic_input.source_input_hash,
        "rule_set_id": automatic_input.rule_set.rule_set_id,
        "rule_set_version": automatic_input.rule_set.version,
        "rule_set_content_hash": automatic_input.rule_set.content_hash,
        "left_candidate_ids": ["candidate.left.wrong"],
        "right_candidate_ids": list(target.right_candidate_ids),
        "evidence_ids": list(target.evidence_ids),
    }
    decision_payload["content_hash"] = compute_crossmatch_content_hash(
        decision_payload
    )
    payload = automatic_input.model_dump(mode="json")
    payload["manual_review_decisions"] = [decision_payload]
    payload["input_hash"] = compute_crossmatch_input_hash(payload)
    reviewed_input = CrossmatchInput.model_validate(payload)

    with pytest.raises(CrossmatchError) as error:
        align_cross_source_records(reviewed_input)

    assert error.value.code == "CROSSMATCH_MANUAL_DECISION_BINDING_MISMATCH"


def _coordinate_separation_arcsec(ra_left: float, ra_right: float, dec: float) -> float:
    result = align_cross_source_records(
        crossmatch_input(
            (toi_record("900.01", tic_id=None, ra=ra_left, dec=dec),),
            (
                ps_record(
                    "Separation Probe b",
                    "Reference",
                    tic_id=None,
                    ra=ra_right,
                    dec=dec,
                ),
            ),
        )
    )
    condition = next(
        item
        for evidence in result.evidence
        if evidence.method is CrossmatchMethod.coordinate
        for item in evidence.conditions
        if item.separation_arcsec is not None
    )
    return condition.separation_arcsec


def _rule_set_with_coordinate(
    *, strict: float, manual_review: float
) -> CrossmatchRuleSet:
    rule_payload = load_crossmatch_rule_set().model_dump(mode="json")
    rule_payload["coordinate"]["strict_separation_arcsec"] = strict
    rule_payload["coordinate"]["manual_review_separation_arcsec"] = manual_review
    rule_payload["content_hash"] = compute_crossmatch_content_hash(rule_payload)
    return CrossmatchRuleSet.model_validate(rule_payload)


def test_identifier_match_within_manual_tolerance_is_not_coordinate_conflict() -> None:
    separation = _coordinate_separation_arcsec(10.0, 10.00025, 20.0)
    # Place the manual-review threshold just below the real separation so the
    # value falls inside the shared isclose window (abs_tol=1e-7) and also
    # strictly exceeds the threshold: the pre-fix coordinate_conflict branch.
    rule_set = _rule_set_with_coordinate(
        strict=separation - 5e-7,
        manual_review=separation - 5e-8,
    )
    result = align_cross_source_records(
        crossmatch_input(
            (toi_record("901.01", tic_id=901, ra=10.0, dec=20.0),),
            (
                ps_record(
                    "Tolerant Host b",
                    "Reference",
                    tic_id="TIC 901",
                    ra=10.00025,
                    dec=20.0,
                ),
            ),
            rule_set=rule_set,
        )
    )

    host_match = next(
        record
        for record in paired_records(result)
        if record.entity_level is EntityLevel.host_star
    )
    assert host_match.method is CrossmatchMethod.exact_identifier
    assert host_match.decision is MatchDecision.accepted
    assert conflict_records(result) == []
    coordinate_condition = next(
        item
        for evidence in result.evidence
        if evidence.method is CrossmatchMethod.exact_identifier
        for item in evidence.conditions
        if item.separation_arcsec is not None
    )
    assert (
        coordinate_condition.operator.value == "angular_separation_lte"
    )


def test_strict_band_uses_shared_tolerance_at_boundary() -> None:
    separation = _coordinate_separation_arcsec(10.0, 10.00025, 20.0)
    # Strict threshold just below separation: with the shared tolerance the
    # value is still treated as strict (medium), not review (low).
    rule_set = _rule_set_with_coordinate(
        strict=separation - 5e-8,
        manual_review=separation + 1.0,
    )
    result = align_cross_source_records(
        crossmatch_input(
            (toi_record("902.01", tic_id=None, ra=10.0, dec=20.0),),
            (
                ps_record(
                    "Strict Boundary b",
                    "Reference",
                    tic_id=None,
                    ra=10.00025,
                    dec=20.0,
                ),
            ),
            rule_set=rule_set,
        )
    )

    coordinate_match = next(
        record
        for record in paired_records(result)
        if record.entity_level is EntityLevel.host_star
    )
    assert coordinate_match.method is CrossmatchMethod.coordinate
    assert coordinate_match.decision is MatchDecision.review_required
    assert coordinate_match.confidence_band is ConfidenceBand.medium


def _edge(left_id: str, right_id: str, decision: MatchDecision) -> object:
    from app.schemas.crossmatch import CandidateEdge

    payload = {
        "edge_id": f"edge.crossmatch_{left_id}_{right_id}",
        "logical_match_key": "sha256:" + "a" * 64,
        "entity_level": EntityLevel.host_star,
        "left_candidate_id": left_id,
        "right_candidate_id": right_id,
        "method": CrossmatchMethod.exact_identifier,
        "decision": decision,
        "confidence": 1.0 if decision is MatchDecision.accepted else 0.0,
        "confidence_band": (
            ConfidenceBand.high
            if decision is MatchDecision.accepted
            else ConfidenceBand.not_applicable
        ),
        "condition_ids": (f"condition.{left_id}_{right_id}",),
        "evidence_ids": (f"evidence.{left_id}_{right_id}",),
    }
    return CandidateEdge.model_validate(crossmatch_engine._with_hash(payload))


def test_record_logical_key_is_namespaced_by_record_type() -> None:
    # Two edge-disjoint host components that both span the same candidate sets
    # (left {L0,L1,L2}, right {R0,R1,R2,R3}): one accepted spanning tree and one
    # conflict spanning tree. Pre-fix the record logical keys collided.
    accepted = [
        _edge("candidate.left.0", "candidate.right.0", MatchDecision.accepted),
        _edge("candidate.left.0", "candidate.right.2", MatchDecision.accepted),
        _edge("candidate.left.1", "candidate.right.0", MatchDecision.accepted),
        _edge("candidate.left.1", "candidate.right.3", MatchDecision.accepted),
        _edge("candidate.left.2", "candidate.right.1", MatchDecision.accepted),
        _edge("candidate.left.2", "candidate.right.3", MatchDecision.accepted),
    ]
    conflict = [
        _edge("candidate.left.0", "candidate.right.1", MatchDecision.conflict),
        _edge("candidate.left.0", "candidate.right.3", MatchDecision.conflict),
        _edge("candidate.left.1", "candidate.right.1", MatchDecision.conflict),
        _edge("candidate.left.1", "candidate.right.2", MatchDecision.conflict),
        _edge("candidate.left.2", "candidate.right.0", MatchDecision.conflict),
        _edge("candidate.left.2", "candidate.right.2", MatchDecision.conflict),
    ]

    records = crossmatch_engine._records_from_edges(
        accepted + conflict, conflict_codes={}
    )

    paired = [record for record in records if isinstance(record, PairedMatch)]
    conflicts = [record for record in records if isinstance(record, ConflictGroup)]
    assert len(paired) == 1
    assert len(conflicts) == 1
    paired_record = paired[0]
    conflict_record = conflicts[0]

    # Same entity level and identical left/right candidate projections.
    assert paired_record.entity_level is conflict_record.entity_level
    assert set(paired_record.left_candidate_ids) == set(
        conflict_record.left_candidate_ids
    )
    assert set(paired_record.right_candidate_ids) == set(
        conflict_record.right_candidate_ids
    )
    # The fix: record-type namespacing keeps their logical keys distinct.
    assert paired_record.logical_match_key != conflict_record.logical_match_key

    # A decision map keyed by logical_match_key (as _apply_manual_decisions builds)
    # routes a conflict-group decision only to the conflict group.
    decisions = {conflict_record.logical_match_key: object()}
    assert decisions.get(conflict_record.logical_match_key) is not None
    assert decisions.get(paired_record.logical_match_key) is None


def test_blank_identifier_values_are_treated_as_missing_not_invalid() -> None:
    # Whitespace-only identifier fields must be skipped as missing rather than
    # raising CROSSMATCH_INVALID_IDENTIFIER; coordinates still drive the match.
    result = align_cross_source_records(
        crossmatch_input(
            (toi_record("905.01", tic_id="   ", ra=10.0, dec=20.0),),
            (
                ps_record(
                    "Blank Identifier b",
                    "Reference",
                    tic_id="   ",
                    ra=10.00025,
                    dec=20.0,
                ),
            ),
        )
    )

    host_match = next(
        record
        for record in paired_records(result)
        if record.entity_level is EntityLevel.host_star
    )
    assert host_match.method is CrossmatchMethod.coordinate
    assert host_match.decision is MatchDecision.review_required
