from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from app.schemas.crossmatch import (
    AdjudicationDecision,
    ConfidenceBand,
    ConditionOperator,
    CrossmatchCondition,
    CrossmatchMethod,
    CrossmatchRecord,
    CrossmatchRecordType,
    EntityLevel,
    MatchDecision,
    ReviewerKind,
)
from app.schemas.source_acquisition import (
    DataQueryCursor,
    DataSourceCompletion,
    DataSourceCompletionStatus,
)


def test_data_source_completion_is_a_closed_strict_contract() -> None:
    complete = DataSourceCompletion(status="complete")
    truncated = DataSourceCompletion(
        status="truncated",
        continuation_cursor=DataQueryCursor(tid=123, toi="456.01"),
    )

    assert complete.status is DataSourceCompletionStatus.complete
    assert complete.continuation_cursor is None
    assert truncated.status is DataSourceCompletionStatus.truncated
    assert truncated.continuation_cursor == DataQueryCursor(tid=123, toi="456.01")

    with pytest.raises(ValidationError, match="complete acquisition"):
        DataSourceCompletion(
            status="complete",
            continuation_cursor=DataQueryCursor(tid=123, toi="456.01"),
        )
    with pytest.raises(ValidationError, match="truncated acquisition"):
        DataSourceCompletion(status="truncated")
    with pytest.raises(ValidationError):
        DataSourceCompletion(status="partial")


def test_crossmatch_enums_are_closed_and_manual_review_is_not_a_method() -> None:
    assert set(EntityLevel) == {
        EntityLevel.host_star,
        EntityLevel.planet_candidate,
        EntityLevel.planet_assertion,
    }
    assert set(CrossmatchMethod) == {
        CrossmatchMethod.exact_identifier,
        CrossmatchMethod.curated_entity_alias,
        CrossmatchMethod.coordinate,
        CrossmatchMethod.compound,
    }
    assert set(MatchDecision) == {
        MatchDecision.accepted,
        MatchDecision.rejected,
        MatchDecision.review_required,
        MatchDecision.conflict,
        MatchDecision.inconclusive,
        MatchDecision.unmatched,
    }
    assert set(ConfidenceBand) == {
        ConfidenceBand.high,
        ConfidenceBand.medium,
        ConfidenceBand.low,
        ConfidenceBand.not_applicable,
    }
    with pytest.raises(ValueError):
        CrossmatchMethod("manual_review")
    assert set(AdjudicationDecision) == {
        AdjudicationDecision.accepted,
        AdjudicationDecision.rejected,
        AdjudicationDecision.keep_unresolved,
    }
    assert set(ReviewerKind) == {
        ReviewerKind.human,
        ReviewerKind.benchmark_fixture,
    }


def test_crossmatch_record_json_schema_is_a_discriminated_union() -> None:
    schema = TypeAdapter(CrossmatchRecord).json_schema()

    assert schema["discriminator"]["propertyName"] == "record_type"
    assert set(schema["discriminator"]["mapping"]) == {
        CrossmatchRecordType.paired.value,
        CrossmatchRecordType.unpaired.value,
        CrossmatchRecordType.conflict_group.value,
    }


def test_paired_match_admits_reserved_rejected_decision() -> None:
    # `MatchDecision.rejected` is a reserved Contract value. A structured paired
    # record may carry it and must still pass the record-level schema, but the
    # automatic engine never emits it (see test_crossmatch_benchmark).
    from app.schemas._hashing import compute_canonical_payload_hash
    from app.schemas.crossmatch import PairedMatch, compute_crossmatch_content_hash

    payload = {
        "record_type": "paired",
        "logical_match_key": compute_canonical_payload_hash(
            {
                "record_type": "paired",
                "entity_level": "host_star",
                "left_candidate_ids": ("candidate.left.0",),
                "right_candidate_ids": ("candidate.right.0",),
            }
        ),
        "entity_level": EntityLevel.host_star,
        "topology": "one_to_one",
        "left_candidate_ids": ("candidate.left.0",),
        "right_candidate_ids": ("candidate.right.0",),
        "method": CrossmatchMethod.exact_identifier,
        "decision": MatchDecision.rejected,
        "confidence_band": ConfidenceBand.not_applicable,
        "evidence_ids": ("evidence.host.0",),
    }
    payload["content_hash"] = compute_crossmatch_content_hash(payload)
    record = PairedMatch.model_validate(payload)

    assert record.decision is MatchDecision.rejected
    # A tampered content hash must still fail: reserved value does not bypass
    # reference/consistency validation.
    tampered = dict(payload)
    tampered["content_hash"] = "sha256:" + "0" * 64
    with pytest.raises(ValidationError):
        PairedMatch.model_validate(tampered)


@pytest.mark.parametrize(
    "payload",
    [
        {
            "operator": ConditionOperator.exact,
            "field_id": "star.tic_id",
            "left_value": "123",
            "right_value": "123",
            "separation_arcsec": 0.1,
        },
        {
            "operator": ConditionOperator.curated_alias,
            "field_id": "star.tic_id",
            "left_value": "123",
            "right_value": "123",
            "strict_threshold_arcsec": 1.0,
        },
        {
            "operator": ConditionOperator.source_scope,
        },
    ],
)
def test_crossmatch_condition_rejects_undefined_operator_shapes(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError, match="condition"):
        CrossmatchCondition.model_validate(
            {
                "condition_id": "condition.invalid_shape",
                "rule_reference": "crossmatch-rules",
                **payload,
            }
        )
