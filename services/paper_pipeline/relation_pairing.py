"""Deterministic Claim pairing and comparability policy for literature relations."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.schemas.enums import LiteratureRelationType
from app.schemas.literature_claim import LiteratureClaimCandidate, LiteratureClaimStatus
from app.schemas.literature_relation import LiteratureComparabilityStatus


STRUCTURAL_RELATION_TYPES = frozenset(
    {
        LiteratureRelationType.derived_from,
        LiteratureRelationType.uses_same_dataset,
        LiteratureRelationType.compares_method,
    }
)
NON_STRUCTURAL_RELATION_TYPES = frozenset(LiteratureRelationType).difference(
    STRUCTURAL_RELATION_TYPES
)


@dataclass(frozen=True, slots=True)
class LiteratureRelationPairConstraint:
    """Admission-relevant constraint for one directed Claim pair."""

    source_claim_id: str
    target_claim_id: str
    non_structural_metric_status: LiteratureComparabilityStatus
    non_structural_unit_status: LiteratureComparabilityStatus

    @property
    def non_structural_allowed(self) -> bool:
        return (
            self.non_structural_metric_status
            is not LiteratureComparabilityStatus.incomparable
            and self.non_structural_unit_status
            is not LiteratureComparabilityStatus.incomparable
        )

    def as_model_input(self) -> dict[str, object]:
        return {
            "source_claim_id": self.source_claim_id,
            "target_claim_id": self.target_claim_id,
            "non_structural_allowed": self.non_structural_allowed,
            "non_structural_metric_status": self.non_structural_metric_status.value,
            "non_structural_unit_status": self.non_structural_unit_status.value,
        }


@dataclass(frozen=True, slots=True)
class LiteratureRelationPairingPolicy:
    """Stable pairing universe shared by generation and confidence admission."""

    pairs: tuple[LiteratureRelationPairConstraint, ...]

    def as_model_input(self) -> dict[str, object]:
        return {
            "structural_relation_types": tuple(
                relation_type.value
                for relation_type in LiteratureRelationType
                if relation_type in STRUCTURAL_RELATION_TYPES
            ),
            "non_structural_relation_types": tuple(
                relation_type.value
                for relation_type in LiteratureRelationType
                if relation_type in NON_STRUCTURAL_RELATION_TYPES
            ),
            "pairs": tuple(pair.as_model_input() for pair in self.pairs),
        }


def build_literature_relation_pairing_policy(
    claims: Iterable[LiteratureClaimCandidate],
) -> LiteratureRelationPairingPolicy:
    """Build the stable directed pair universe for admitted Claim candidates."""

    eligible = tuple(
        sorted(
            (
                claim
                for claim in claims
                if claim.status is not LiteratureClaimStatus.rejected
                and claim.evidence_ids
            ),
            key=lambda claim: claim.claim_id,
        )
    )
    pairs: list[LiteratureRelationPairConstraint] = []
    for source in eligible:
        for target in eligible:
            if source.claim_id == target.claim_id:
                continue
            metric_status, unit_status = expected_literature_relation_comparability(
                relation_type=LiteratureRelationType.supports,
                source_metric=source.metric,
                target_metric=target.metric,
                source_unit=source.unit,
                target_unit=target.unit,
            )
            pairs.append(
                LiteratureRelationPairConstraint(
                    source_claim_id=source.claim_id,
                    target_claim_id=target.claim_id,
                    non_structural_metric_status=metric_status,
                    non_structural_unit_status=unit_status,
                )
            )
    return LiteratureRelationPairingPolicy(pairs=tuple(pairs))


def select_literature_relation_model_policy(
    claims: Iterable[LiteratureClaimCandidate],
    *,
    max_pairs: int,
) -> LiteratureRelationPairingPolicy:
    """Select a deterministic, bounded model-facing view of the full pair space.

    Admission still resolves endpoints against the complete frozen Claim
    ArtifactVersion. The provider only needs the strongest reviewable pair
    candidates, not the quadratic Cartesian product and unrelated provenance.
    """

    if not 1 <= max_pairs <= 1_024:
        raise ValueError("max_pairs must be between 1 and 1024")
    eligible = tuple(
        claim
        for claim in claims
        if claim.status is not LiteratureClaimStatus.rejected and claim.evidence_ids
    )
    claims_by_id = {claim.claim_id: claim for claim in eligible}
    full = build_literature_relation_pairing_policy(eligible)

    def rank(pair: LiteratureRelationPairConstraint) -> tuple[object, ...]:
        source = claims_by_id[pair.source_claim_id]
        target = claims_by_id[pair.target_claim_id]
        source_objects = {
            item.strip().casefold() for item in source.objects if item.strip()
        }
        target_objects = {
            item.strip().casefold() for item in target.objects if item.strip()
        }
        shared_object_count = len(source_objects.intersection(target_objects))
        metric_match = (
            source.metric is not None
            and target.metric is not None
            and source.metric.casefold() == target.metric.casefold()
        )
        unit_match = (
            source.unit is not None
            and target.unit is not None
            and source.unit.casefold() == target.unit.casefold()
        )
        same_claim_type = source.claim_type is target.claim_type
        independent_evidence = set(source.evidence_ids).isdisjoint(target.evidence_ids)
        return (
            -shared_object_count,
            -int(metric_match),
            -int(unit_match),
            -int(same_claim_type),
            -int(independent_evidence),
            pair.source_claim_id,
            pair.target_claim_id,
        )

    return LiteratureRelationPairingPolicy(
        pairs=tuple(sorted(full.pairs, key=rank)[:max_pairs])
    )


def expected_literature_relation_comparability(
    *,
    relation_type: LiteratureRelationType,
    source_metric: str | None,
    target_metric: str | None,
    source_unit: str | None,
    target_unit: str | None,
) -> tuple[LiteratureComparabilityStatus, LiteratureComparabilityStatus]:
    """Return the metric/unit contract for one relation type and Claim pair."""

    if relation_type in STRUCTURAL_RELATION_TYPES:
        return (
            LiteratureComparabilityStatus.not_applicable,
            LiteratureComparabilityStatus.not_applicable,
        )
    return (
        _expected_comparability(source_metric, target_metric),
        _expected_comparability(source_unit, target_unit),
    )


def _expected_comparability(
    source: str | None, target: str | None
) -> LiteratureComparabilityStatus:
    if source is None and target is None:
        return LiteratureComparabilityStatus.not_applicable
    if (
        source is not None
        and target is not None
        and source.casefold() == target.casefold()
    ):
        return LiteratureComparabilityStatus.comparable
    return LiteratureComparabilityStatus.incomparable


__all__ = [
    "NON_STRUCTURAL_RELATION_TYPES",
    "STRUCTURAL_RELATION_TYPES",
    "LiteratureRelationPairConstraint",
    "LiteratureRelationPairingPolicy",
    "build_literature_relation_pairing_policy",
    "select_literature_relation_model_policy",
    "expected_literature_relation_comparability",
]
