from __future__ import annotations

from types import SimpleNamespace
from typing import cast

from app.schemas.enums import ClaimType
from app.schemas.literature_claim import LiteratureClaimCandidate, LiteratureClaimStatus
from services.paper_pipeline.relation_pairing import (
    select_literature_relation_model_policy,
)


def _claim(index: int, *, shared_object: bool) -> LiteratureClaimCandidate:
    return cast(
        LiteratureClaimCandidate,
        SimpleNamespace(
            claim_id=f"claim.{index:03d}",
            status=LiteratureClaimStatus.accepted,
            evidence_ids=(f"evidence.{index:03d}",),
            objects=("transiting exoplanets" if shared_object else f"object {index}",),
            metric=None,
            unit=None,
            claim_type=ClaimType.finding,
        ),
    )


def test_relation_model_policy_is_bounded_and_deterministic() -> None:
    claims = tuple(_claim(index, shared_object=True) for index in range(12))

    first = select_literature_relation_model_policy(claims, max_pairs=24)
    second = select_literature_relation_model_policy(reversed(claims), max_pairs=24)

    assert first == second
    assert len(first.pairs) == 24


def test_relation_model_policy_prioritizes_shared_declared_objects() -> None:
    claims = (
        _claim(1, shared_object=True),
        _claim(2, shared_object=True),
        _claim(3, shared_object=False),
    )

    policy = select_literature_relation_model_policy(claims, max_pairs=2)

    assert {(pair.source_claim_id, pair.target_claim_id) for pair in policy.pairs} == {
        ("claim.001", "claim.002"),
        ("claim.002", "claim.001"),
    }
