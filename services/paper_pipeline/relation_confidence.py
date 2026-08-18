"""Production confidence-assessment scope for live literature relations."""

from __future__ import annotations

from collections.abc import Iterable

from app.schemas.literature_claim import LiteratureClaimCandidate, LiteratureClaimStatus
from app.schemas.literature_relation import (
    LiteratureRelationConfidenceAssessment,
    LiteratureRelationConfidenceStatus,
    LiteratureRelationStatus,
    LiteratureRelationType,
    build_literature_relation_confidence_subject,
)

from .constants import (
    FROZEN_BENCHMARK_CONTENT_HASH,
    FROZEN_SCIENTIFIC_PAYLOAD_HASH,
    RELATION_CONFIDENCE_ACCEPTANCE_THRESHOLD,
    RELATION_CONFIDENCE_APPLICABILITY_SCOPE,
    RELATION_CONFIDENCE_CALIBRATION_ID,
    RELATION_CONFIDENCE_CALIBRATION_METHOD,
    RELATION_CONFIDENCE_CALIBRATION_SAMPLE_SIZE,
    RELATION_CONFIDENCE_CALIBRATION_VERSION,
    RELATION_CONFIDENCE_DEFINITION_ID,
    RELATION_CONFIDENCE_DEFINITION_VERSION,
)


def build_live_relation_confidence_assessments(
    *,
    claim_artifact_version_id: str,
    claims: Iterable[LiteratureClaimCandidate],
) -> dict[str, LiteratureRelationConfidenceAssessment]:
    """Declare live relation candidates outside the frozen calibration scope.

    The frozen benchmark can validate the admission implementation but cannot
    supply a calibrated score for an arbitrary live claim pair.  We therefore
    expose a versioned ``not_evaluable`` assessment for each possible directed
    pair and relation type.  The model may select one of these subjects, while
    the deterministic admission boundary keeps it as a review candidate.
    """

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
    assessments: dict[str, LiteratureRelationConfidenceAssessment] = {}
    for source in eligible:
        for target in eligible:
            if source.claim_id == target.claim_id:
                continue
            for relation_type in LiteratureRelationType:
                subject = build_literature_relation_confidence_subject(
                    source_claim_artifact_version_id=claim_artifact_version_id,
                    source_claim_id=source.claim_id,
                    target_claim_artifact_version_id=claim_artifact_version_id,
                    target_claim_id=target.claim_id,
                    relation_type=relation_type,
                )
                assessment_id = f"assessment.live_scope.{subject.fingerprint[7:31]}"
                assessments[assessment_id] = LiteratureRelationConfidenceAssessment(
                    assessment_id=assessment_id,
                    subject=subject,
                    decision=LiteratureRelationStatus.candidate,
                    status=LiteratureRelationConfidenceStatus.not_evaluable,
                    definition_id=RELATION_CONFIDENCE_DEFINITION_ID,
                    definition_version=RELATION_CONFIDENCE_DEFINITION_VERSION,
                    calibration_id=RELATION_CONFIDENCE_CALIBRATION_ID,
                    calibration_version=RELATION_CONFIDENCE_CALIBRATION_VERSION,
                    calibration_scientific_payload_hash=FROZEN_SCIENTIFIC_PAYLOAD_HASH,
                    calibration_content_hash=FROZEN_BENCHMARK_CONTENT_HASH,
                    calibration_sample_size=RELATION_CONFIDENCE_CALIBRATION_SAMPLE_SIZE,
                    calibration_method=RELATION_CONFIDENCE_CALIBRATION_METHOD,
                    applicability_scope=RELATION_CONFIDENCE_APPLICABILITY_SCOPE,
                    acceptance_threshold=RELATION_CONFIDENCE_ACCEPTANCE_THRESHOLD,
                    basis=("实时研究输入不属于冻结关系校准样本，无法给出校准置信分数。",),
                )
    return dict(sorted(assessments.items()))


__all__ = ["build_live_relation_confidence_assessments"]
