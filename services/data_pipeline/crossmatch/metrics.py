"""Deterministic C-08 processing and traceability metrics."""

from __future__ import annotations

from app.schemas.crossmatch import (
    AdjudicationDecision,
    CandidateEdge,
    ConfidenceBand,
    ConfidenceDistribution,
    ConflictGroup,
    CrossmatchEvidence,
    CrossmatchInput,
    CrossmatchMethod,
    CrossmatchMetrics,
    CrossmatchRecord,
    CrossmatchSide,
    EntityCandidate,
    MatchDecision,
    MatchTopology,
    MethodDistribution,
    PairedMatch,
    RatioMetric,
    UnpairedRecord,
)


def compute_crossmatch_metrics(
    input: CrossmatchInput,
    candidates: tuple[EntityCandidate, ...],
    edges: list[CandidateEdge],
    records: list[CrossmatchRecord],
    evidence: list[CrossmatchEvidence],
) -> CrossmatchMetrics:
    paired = [record for record in records if isinstance(record, PairedMatch)]
    conflicts = [record for record in records if isinstance(record, ConflictGroup)]
    unpaired = [record for record in records if isinstance(record, UnpairedRecord)]
    audited_records = paired + conflicts
    evidence_ids = {item.evidence_id for item in evidence}
    covered = sum(
        1
        for record in audited_records
        if set(record.evidence_ids).issubset(evidence_ids)
        and bool(record.evidence_ids)
    )
    denominator = len(audited_records)
    candidate_count = sum(
        (
            len(record.left_candidate_ids) + len(record.right_candidate_ids)
            if isinstance(record, PairedMatch | ConflictGroup)
            else 1
        )
        for record in records
    )
    accepted_paired = [
        record
        for record in paired
        if record.decision is MatchDecision.accepted
        or record.adjudication is AdjudicationDecision.accepted
    ]
    matched_candidates = sum(
        len(record.left_candidate_ids) + len(record.right_candidate_ids)
        for record in accepted_paired
    )
    conflict_denominator = len(paired) + len(conflicts)
    unmatched_left = sum(
        record.side is CrossmatchSide.left
        and record.decision is MatchDecision.unmatched
        for record in unpaired
    )
    unmatched_right = sum(
        record.side is CrossmatchSide.right
        and record.decision is MatchDecision.unmatched
        for record in unpaired
    )
    unresolved_paired = [
        record
        for record in paired
        if record.decision is MatchDecision.review_required
        and record.adjudication in {None, AdjudicationDecision.keep_unresolved}
    ]
    unresolved_conflicts = [
        record
        for record in conflicts
        if record.adjudication in {None, AdjudicationDecision.keep_unresolved}
    ]
    error_references = sorted(
        {
            *(
                record.logical_match_key
                for record in (*unresolved_paired, *unresolved_conflicts)
            ),
            *(record.content_hash for record in unpaired),
        }
    )[:10]
    return CrossmatchMetrics(
        left_record_count=len(input.left.records),
        right_record_count=len(input.right.records),
        left_candidate_count=sum(
            candidate.side is CrossmatchSide.left for candidate in candidates
        ),
        right_candidate_count=sum(
            candidate.side is CrossmatchSide.right for candidate in candidates
        ),
        candidate_pair_count=len(edges),
        paired_group_count=len(paired),
        matched_group_count=len(accepted_paired),
        ambiguous_group_count=len(unresolved_paired),
        conflict_group_count=len(conflicts),
        unmatched_record_count=unmatched_left + unmatched_right,
        unmatched_left_record_count=unmatched_left,
        unmatched_right_record_count=unmatched_right,
        inconclusive_record_count=sum(
            record.decision is MatchDecision.inconclusive for record in unpaired
        ),
        manual_review_required_count=(
            len(unresolved_paired) + len(unresolved_conflicts)
        ),
        low_confidence_count=sum(
            edge.confidence_band is ConfidenceBand.low for edge in edges
        ),
        manual_adjudication_count=sum(
            record.adjudication is not None
            for record in (*paired, *conflicts)
        ),
        one_to_one_count=sum(
            record.topology is MatchTopology.one_to_one for record in paired
        ),
        one_to_many_count=sum(
            record.topology is MatchTopology.one_to_many for record in paired
        ),
        many_to_one_count=sum(
            record.topology is MatchTopology.many_to_one for record in paired
        ),
        many_to_many_count=sum(
            record.topology is MatchTopology.many_to_many for record in paired
        ),
        confidence_distribution=ConfidenceDistribution(
            high=sum(edge.confidence_band is ConfidenceBand.high for edge in edges),
            medium=sum(
                edge.confidence_band is ConfidenceBand.medium for edge in edges
            ),
            low=sum(edge.confidence_band is ConfidenceBand.low for edge in edges),
            not_applicable=sum(
                edge.confidence_band is ConfidenceBand.not_applicable
                for edge in edges
            ),
        ),
        method_distribution=MethodDistribution(
            exact_identifier=sum(
                edge.method is CrossmatchMethod.exact_identifier for edge in edges
            ),
            curated_entity_alias=sum(
                edge.method is CrossmatchMethod.curated_entity_alias
                for edge in edges
            ),
            coordinate=sum(
                edge.method is CrossmatchMethod.coordinate for edge in edges
            ),
            compound=sum(edge.method is CrossmatchMethod.compound for edge in edges),
        ),
        error_example_references=tuple(error_references),
        match_coverage=RatioMetric(
            numerator=matched_candidates,
            denominator=candidate_count,
            value=(
                matched_candidates / candidate_count if candidate_count else None
            ),
        ),
        conflict_rate=RatioMetric(
            numerator=len(conflicts),
            denominator=conflict_denominator,
            value=(
                len(conflicts) / conflict_denominator
                if conflict_denominator
                else None
            ),
        ),
        unmatched_rate=RatioMetric(
            numerator=unmatched_left + unmatched_right,
            denominator=candidate_count,
            value=(
                (unmatched_left + unmatched_right) / candidate_count
                if candidate_count
                else None
            ),
        ),
        evidence_coverage=RatioMetric(
            numerator=covered,
            denominator=denominator,
            value=covered / denominator if denominator else None,
        ),
    )
