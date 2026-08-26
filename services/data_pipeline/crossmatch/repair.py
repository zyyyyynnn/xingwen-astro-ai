"""Pure crossmatch repair projection and deterministic revalidation.

The data Pipeline owns these algorithms.  Workflow supplies checkpoint state
and persists the resulting decisions, while benchmarks exercise this same
production surface without importing Workflow orchestration.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.core import (
    RepairCandidateCoordinate,
    RepairCandidateIdentity,
    RepairCandidateSummary,
    RepairCheckpointContext,
    RepairDecisionInput,
    RepairDefect,
    RepairEvidenceFact,
)
from app.schemas.crossmatch import (
    AdjudicationDecision,
    ConflictGroup,
    CrossmatchCondition,
    CrossmatchResult,
    CrossmatchRuleSet,
    EntityCandidate,
    ManualReviewDecision,
    MatchDecision,
    PairedMatch,
    ReviewerKind,
)
from app.schemas.manifest import ManifestBundle


RepairResolutionStatus = Literal["revalidated", "false_repair"]


@dataclass(frozen=True, slots=True)
class RepairResolutionAssessment:
    """Deterministic resolution facts shared by Workflow and benchmark."""

    resolved_defect_ids: tuple[str, ...]
    unresolved_defect_ids: tuple[str, ...]
    status: RepairResolutionStatus


def derive_repair_defects(
    crossmatch: CrossmatchResult, *, manifests: ManifestBundle
) -> tuple[RepairDefect, ...]:
    defects: list[RepairDefect] = []
    evidence_by_id = {item.evidence_id: item for item in crossmatch.evidence}
    candidates_by_id = {item.candidate_id: item for item in crossmatch.candidates}
    field_labels = {
        item.field_id: item.meaning_zh for item in manifests.field_manifest.fields
    }
    source_labels = {
        item.source_id: item.name for item in manifests.field_manifest.sources
    }
    for record in crossmatch.records:
        if isinstance(record, ConflictGroup):
            conflict_code = record.conflict_code
        elif (
            isinstance(record, PairedMatch)
            and record.decision is MatchDecision.review_required
        ):
            conflict_code = "low_confidence_match"
        else:
            continue
        defects.append(
            RepairDefect(
                defect_id=f"repair-{record.logical_match_key[7:31]}",
                logical_match_key=record.logical_match_key,
                conflict_code=conflict_code,
                left_candidates=tuple(
                    _repair_candidate_summary(
                        candidates_by_id[candidate_id],
                        field_labels=field_labels,
                        source_labels=source_labels,
                    )
                    for candidate_id in sorted(record.left_candidate_ids)
                ),
                right_candidates=tuple(
                    _repair_candidate_summary(
                        candidates_by_id[candidate_id],
                        field_labels=field_labels,
                        source_labels=source_labels,
                    )
                    for candidate_id in sorted(record.right_candidate_ids)
                ),
                evidence=tuple(
                    RepairEvidenceFact(
                        evidence_id=item.evidence_id,
                        left_candidate_id=item.left_candidate_id,
                        right_candidate_id=item.right_candidate_id,
                        confidence=item.confidence,
                        summary="；".join(
                            _repair_condition_summary(condition)
                            for condition in item.conditions
                        ),
                    )
                    for item in sorted(
                        (evidence_by_id[value] for value in record.evidence_ids),
                        key=lambda value: value.evidence_id,
                    )
                ),
            )
        )
    return tuple(sorted(defects, key=lambda item: item.defect_id))


def _repair_candidate_summary(
    candidate: EntityCandidate,
    *,
    field_labels: dict[str, str],
    source_labels: dict[str, str],
) -> RepairCandidateSummary:
    entity_labels = {
        "host_star": "宿主恒星",
        "planet_candidate": "行星候选体",
        "planet_assertion": "行星记录",
    }
    coordinate = candidate.coordinate
    return RepairCandidateSummary(
        candidate_id=candidate.candidate_id,
        source_label=source_labels[candidate.source_record.source_id],
        entity_label=entity_labels[candidate.entity_level.value],
        identities=tuple(
            RepairCandidateIdentity(
                label=field_labels[item.field_id],
                value=item.normalized_value,
            )
            for item in candidate.identity_values
        ),
        coordinate=(
            RepairCandidateCoordinate(
                right_ascension_degrees=coordinate.right_ascension,
                declination_degrees=coordinate.declination,
            )
            if coordinate is not None
            else None
        ),
    )


def _repair_condition_summary(condition: CrossmatchCondition) -> str:
    if condition.separation_arcsec is not None:
        return (
            f"角距离 {condition.separation_arcsec:.3f} 角秒；"
            f"自动接受阈值 {condition.strict_threshold_arcsec:.3f} 角秒；"
            f"人工复核阈值 {condition.manual_review_threshold_arcsec:.3f} 角秒"
        )
    labels = {
        "exact": "字段完全一致",
        "curated_alias": "命中受控别名",
        "contradicts": "字段值冲突",
    }
    operator = condition.operator.value
    label = labels.get(operator, "候选匹配条件")
    field = condition.field_id or "标识字段"
    return f"{field}：{condition.left_value} / {condition.right_value}（{label}）"


def validate_repair_checkpoint(
    repair_context: RepairCheckpointContext,
    *,
    defects: tuple[RepairDefect, ...],
    rules: CrossmatchRuleSet,
    source_input_hash: str,
    before_output_hash: str,
) -> None:
    if (
        repair_context.defects != defects
        or repair_context.source_input_hash != source_input_hash
        or repair_context.before_output_hash != before_output_hash
        or repair_context.rule_set.rule_set_id != rules.rule_set_id
        or repair_context.rule_set.rule_set_version != rules.version
        or repair_context.rule_set.rule_set_content_hash != rules.content_hash
    ):
        raise ValueError("科学修复检查点与当前不可变输入或 RuleSet 不一致")


def build_repair_manual_review_decision(
    decision: RepairDecisionInput,
    *,
    defect: RepairDefect,
    checkpoint_id: str,
    decided_at: datetime,
    source_input_hash: str,
    rules: CrossmatchRuleSet,
    adjudicated_by: str = "workspace_user",
    reviewer_kind: ReviewerKind = ReviewerKind.human,
) -> ManualReviewDecision:
    adjudication = AdjudicationDecision(decision.action)
    decision_id = f"{checkpoint_id}.{defect.defect_id}"
    rule_actor = f"{rules.rule_set_id}@{rules.version}"
    left_candidate_ids = tuple(
        sorted(item.candidate_id for item in defect.left_candidates)
    )
    right_candidate_ids = tuple(
        sorted(item.candidate_id for item in defect.right_candidates)
    )
    evidence_ids = tuple(sorted(item.evidence_id for item in defect.evidence))
    hash_payload = {
        "schema_version": "1.0.0",
        "decision_id": decision_id,
        "logical_match_key": defect.logical_match_key,
        "adjudication": adjudication.value,
        "adjudicated_by": adjudicated_by,
        "reviewer_kind": reviewer_kind.value,
        "adjudication_rule_or_actor": rule_actor,
        "adjudicated_at": decided_at.isoformat().replace("+00:00", "Z"),
        "rationale": decision.rationale,
        "source_input_hash": source_input_hash,
        "rule_set_id": rules.rule_set_id,
        "rule_set_version": rules.version,
        "rule_set_content_hash": rules.content_hash,
        "left_candidate_ids": left_candidate_ids,
        "right_candidate_ids": right_candidate_ids,
        "evidence_ids": evidence_ids,
    }
    return ManualReviewDecision(
        decision_id=decision_id,
        logical_match_key=defect.logical_match_key,
        adjudication=adjudication,
        adjudicated_by=adjudicated_by,
        reviewer_kind=reviewer_kind,
        adjudication_rule_or_actor=rule_actor,
        adjudicated_at=decided_at,
        rationale=decision.rationale,
        source_input_hash=source_input_hash,
        rule_set_id=rules.rule_set_id,
        rule_set_version=rules.version,
        rule_set_content_hash=rules.content_hash,
        left_candidate_ids=left_candidate_ids,
        right_candidate_ids=right_candidate_ids,
        evidence_ids=evidence_ids,
        content_hash=compute_canonical_payload_hash(hash_payload),
    )


def assess_repair_resolution(
    *,
    decisions: tuple[RepairDecisionInput, ...],
    before_defects: tuple[RepairDefect, ...],
    crossmatch: CrossmatchResult,
) -> RepairResolutionAssessment:
    """Classify repair output against the submitted adjudications."""
    remaining = {
        item.logical_match_key
        for item in crossmatch.records
        if (
            isinstance(item, ConflictGroup)
            and item.adjudication in {None, AdjudicationDecision.keep_unresolved}
        )
        or (
            isinstance(item, PairedMatch)
            and item.decision is MatchDecision.review_required
            and item.adjudication in {None, AdjudicationDecision.keep_unresolved}
        )
    }
    defects_by_id = {item.defect_id: item for item in before_defects}
    false_repair = False
    resolved: list[str] = []
    unresolved: list[str] = []
    for decision in decisions:
        defect = defects_by_id.get(decision.defect_id)
        if defect is None:
            raise ValueError(
                f"repair decision references unknown defect {decision.defect_id}"
            )
        remains = defect.logical_match_key in remaining
        if remains:
            unresolved.append(defect.defect_id)
        else:
            resolved.append(defect.defect_id)
        if (decision.action == "keep_unresolved") != remains:
            false_repair = True
    return RepairResolutionAssessment(
        resolved_defect_ids=tuple(sorted(resolved)),
        unresolved_defect_ids=tuple(sorted(unresolved)),
        status="false_repair" if false_repair else "revalidated",
    )


__all__ = [
    "RepairResolutionAssessment",
    "assess_repair_resolution",
    "build_repair_manual_review_decision",
    "derive_repair_defects",
    "validate_repair_checkpoint",
]
