from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from app.schemas.crossmatch import (
    AdjudicationDecision,
    ConfidenceBand,
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
