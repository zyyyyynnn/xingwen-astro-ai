"""Single-pass C-05 observations over already-admitted C-04/C-08 data."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from app.schemas.crossmatch import (
    CandidateEdge,
    ConflictGroup,
    CrossmatchResult,
    PairedMatch,
    ConfidenceBand,
    MatchDecision,
)
from app.schemas.data_artifacts import (
    DatasetArtifactCandidate,
    DatasetRow,
    DeclaredNullValue,
    FieldConflictRecord,
    MappedCanonicalValue,
    SourceValueCandidate,
    UnresolvedCanonicalValue,
)
from app.schemas.manifest import FieldDefinition, ManifestBundle


@dataclass(frozen=True)
class FieldObservation:
    field: FieldDefinition
    row_ids: tuple[str, ...]
    applicable_count: int
    mapped_count: int
    declared_null_count: int
    unresolved_count: int
    null_reasons: tuple[tuple[str, int], ...]
    provenance_numerator: int
    evidence_numerator: int
    unit_numerator: int
    unit_denominator: int
    conflict_cell_count: int
    same_source_conflict_cell_count: int
    cross_source_conflict_cell_count: int
    source_snapshot_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class RowObservation:
    row: DatasetRow
    mapped_count: int
    declared_null_count: int
    unresolved_count: int
    provenance_numerator: int
    evidence_numerator: int
    unit_numerator: int
    unit_denominator: int
    conflict_count: int
    low_confidence: bool | None
    review_required: bool | None
    inconclusive: bool | None


@dataclass(frozen=True)
class DatasetObservation:
    row_count: int
    field_count: int
    applicable_cell_count: int
    mapped_count: int
    declared_null_count: int
    unresolved_count: int
    null_reasons: tuple[tuple[str, int], ...]
    provenance_numerator: int
    evidence_numerator: int
    evidence_denominator: int
    unit_numerator: int
    unit_denominator: int
    same_source_conflict_cell_count: int
    cross_source_conflict_cell_count: int
    source_scope_numerator: int
    source_scope_denominator: int
    source_scope_insufficient: bool
    crossmatch_metrics: Any
    crossmatch_record_count: int
    validation_integrity: bool


@dataclass(frozen=True)
class QualityObservationBundle:
    fields: tuple[FieldObservation, ...]
    rows: tuple[RowObservation, ...]
    dataset: DatasetObservation


def observe_quality(
    candidate: DatasetArtifactCandidate,
    crossmatch_result: CrossmatchResult,
    manifests: ManifestBundle,
) -> QualityObservationBundle:
    field_by_id = {column.field.field_id: column.field for column in candidate.columns}
    source_values = {item.source_value_id: item for item in candidate.source_values}
    evidence = {item.evidence_id: item for item in candidate.transformation_evidence}
    conflicts = {item.conflict_id: item for item in candidate.conflicts}
    records_by_key = {
        record.logical_match_key: record
        for record in crossmatch_result.records
        if isinstance(record, (PairedMatch, ConflictGroup))
    }
    edges_by_record_key: dict[str, tuple[CandidateEdge, ...]] = {}
    for record_key, record in records_by_key.items():
        edges_by_record_key[record_key] = tuple(
            edge
            for edge in crossmatch_result.candidate_edges
            if edge.logical_match_key == record_key or edge.edge_id in record.evidence_ids
        )

    field_observations = tuple(
        _observe_field(
            field_by_id[field_id],
            candidate.rows,
            source_values,
            evidence,
            conflicts,
            candidate.source_snapshot_ids,
            candidate.evidence_ids,
        )
        for field_id in candidate.requested_fields
    )
    row_observations = tuple(
        _observe_row(
            row,
            source_values,
            evidence,
            conflicts,
            records_by_key,
            edges_by_record_key,
            candidate.source_snapshot_ids,
            field_by_id,
        )
        for row in candidate.rows
    )

    total_null_reasons = Counter(
        reason
        for observation in field_observations
        for reason, count in observation.null_reasons
        for _ in range(count)
    )
    metrics = crossmatch_result.metrics
    source_members = (crossmatch_result.left_completion, crossmatch_result.right_completion)
    source_scope_insufficient = any(item.status.value != "complete" for item in source_members)
    mapped_evidence = sum(item.evidence_numerator for item in field_observations)
    mapped = sum(item.mapped_count for item in field_observations)
    audited_evidence_numerator = metrics.evidence_coverage.numerator
    audited_evidence_denominator = metrics.evidence_coverage.denominator
    dataset_observation = DatasetObservation(
        row_count=len(candidate.rows),
        field_count=len(candidate.columns),
        applicable_cell_count=sum(item.applicable_count for item in field_observations),
        mapped_count=mapped,
        declared_null_count=sum(item.declared_null_count for item in field_observations),
        unresolved_count=sum(item.unresolved_count for item in field_observations),
        null_reasons=tuple(sorted(total_null_reasons.items())),
        provenance_numerator=sum(item.provenance_numerator for item in field_observations),
        evidence_numerator=mapped_evidence + audited_evidence_numerator,
        evidence_denominator=mapped + audited_evidence_denominator,
        unit_numerator=sum(item.unit_numerator for item in field_observations),
        unit_denominator=sum(item.unit_denominator for item in field_observations),
        same_source_conflict_cell_count=sum(
            item.same_source_conflict_cell_count for item in field_observations
        ),
        cross_source_conflict_cell_count=sum(
            item.cross_source_conflict_cell_count for item in field_observations
        ),
        source_scope_numerator=sum(item.status.value == "complete" for item in source_members),
        source_scope_denominator=len(source_members),
        source_scope_insufficient=source_scope_insufficient,
        crossmatch_metrics=metrics,
        crossmatch_record_count=len(crossmatch_result.records),
        validation_integrity=True,
    )
    return QualityObservationBundle(
        fields=field_observations,
        rows=row_observations,
        dataset=dataset_observation,
    )


def _observe_field(
    field: FieldDefinition,
    rows: tuple[DatasetRow, ...],
    source_values: dict[str, SourceValueCandidate],
    evidence: dict[str, Any],
    conflicts: dict[str, FieldConflictRecord],
    source_snapshot_ids: tuple[str, ...],
    evidence_ids: tuple[str, ...],
) -> FieldObservation:
    cells = [
        (row, outcome)
        for row in rows
        if field.field_id in row.projected_field_ids
        for outcome in row.fields
        if outcome.canonical_field_id == field.field_id
    ]
    null_reasons: Counter[str] = Counter()
    mapped_count = declared_null_count = unresolved_count = 0
    provenance_numerator = evidence_numerator = 0
    unit_numerator = unit_denominator = 0
    conflict_cell_count = same_source_conflict_cell_count = cross_source_conflict_cell_count = 0
    used_evidence: set[str] = set()
    for row, outcome in cells:
        if isinstance(outcome, MappedCanonicalValue):
            mapped_count += 1
            source_items = [source_values[item] for item in outcome.candidate_source_value_ids]
            evidence_items = [evidence[item] for item in outcome.transformation_evidence_ids]
            provenance_ok = bool(source_items) and all(
                item.evidence_locator.source_snapshot_id in source_snapshot_ids
                and item.evidence_locator.source_snapshot_content_hash
                for item in source_items
            )
            evidence_ok = provenance_ok and bool(evidence_items) and all(
                item.locator.source_snapshot_id in source_snapshot_ids
                and item.evidence_id in evidence_ids
                for item in evidence_items
            )
            provenance_numerator += provenance_ok
            evidence_numerator += evidence_ok
            used_evidence.update(outcome.transformation_evidence_ids)
            non_null_source_items = [item for item in source_items if item.canonical_value is not None]
            if "unit_consistency" in {item.value for item in field.quality_metric_inputs}:
                unit_denominator += len(non_null_source_items)
                unit_numerator += sum(
                    item.canonical_unit == field.canonical_unit
                    for item in non_null_source_items
                )
            conflict_ids = tuple(outcome.conflict_ids)
        elif isinstance(outcome, DeclaredNullValue):
            declared_null_count += 1
            null_reasons[outcome.reason.value] += 1
            conflict_ids = ()
        elif isinstance(outcome, UnresolvedCanonicalValue):
            unresolved_count += 1
            conflict_ids = tuple(outcome.conflict_ids)
        else:
            raise ValueError("unsupported C-04 canonical outcome")
        if conflict_ids:
            conflict_cell_count += 1
            scopes = {conflicts[item].conflict_scope for item in conflict_ids}
            same_source_conflict_cell_count += "same_source" in scopes
            cross_source_conflict_cell_count += "cross_source" in scopes
    return FieldObservation(
        field=field,
        row_ids=tuple(row.row_id for row, _ in cells),
        applicable_count=len(cells),
        mapped_count=mapped_count,
        declared_null_count=declared_null_count,
        unresolved_count=unresolved_count,
        null_reasons=tuple(sorted(null_reasons.items())),
        provenance_numerator=provenance_numerator,
        evidence_numerator=evidence_numerator,
        unit_numerator=unit_numerator,
        unit_denominator=unit_denominator,
        conflict_cell_count=conflict_cell_count,
        same_source_conflict_cell_count=same_source_conflict_cell_count,
        cross_source_conflict_cell_count=cross_source_conflict_cell_count,
        source_snapshot_ids=source_snapshot_ids,
        evidence_ids=tuple(sorted(used_evidence)),
    )


def _observe_row(
    row: DatasetRow,
    source_values: dict[str, SourceValueCandidate],
    evidence: dict[str, Any],
    conflicts: dict[str, FieldConflictRecord],
    records_by_key: dict[str, Any],
    edges_by_record_key: dict[str, tuple[CandidateEdge, ...]],
    source_snapshot_ids: tuple[str, ...],
    field_by_id: dict[str, FieldDefinition],
) -> RowObservation:
    mapped_count = declared_null_count = unresolved_count = 0
    provenance_numerator = evidence_numerator = 0
    unit_numerator = unit_denominator = 0
    conflict_count = 0
    for outcome in row.fields:
        if isinstance(outcome, MappedCanonicalValue):
            mapped_count += 1
            source_items = [source_values[item] for item in outcome.candidate_source_value_ids]
            evidence_items = [evidence[item] for item in outcome.transformation_evidence_ids]
            provenance_ok = bool(source_items) and all(
                item.evidence_locator.source_snapshot_id in source_snapshot_ids
                for item in source_items
            )
            evidence_ok = provenance_ok and bool(evidence_items) and all(
                item.locator.source_snapshot_id in source_snapshot_ids for item in evidence_items
            )
            provenance_numerator += provenance_ok
            evidence_numerator += evidence_ok
            field = field_by_id[outcome.canonical_field_id]
            if "unit_consistency" in {item.value for item in field.quality_metric_inputs}:
                non_null_source_items = [
                    item for item in source_items if item.canonical_value is not None
                ]
                unit_denominator += len(non_null_source_items)
                unit_numerator += sum(
                    item.canonical_unit == field.canonical_unit
                    for item in non_null_source_items
                )
            conflict_count += bool(outcome.conflict_ids)
        elif isinstance(outcome, DeclaredNullValue):
            declared_null_count += 1
        elif isinstance(outcome, UnresolvedCanonicalValue):
            unresolved_count += 1
            conflict_count += len(outcome.conflict_ids) > 0
    record = records_by_key.get(row.crossmatch_logical_key)
    edges = edges_by_record_key.get(row.crossmatch_logical_key, ())
    is_paired_or_conflict = record is not None
    low_confidence = (
        any(edge.confidence_band is ConfidenceBand.low for edge in edges)
        if is_paired_or_conflict
        else None
    )
    review_required = (
        row.alignment_status.value in {"review_required", "conflict"}
        or (
            isinstance(record, PairedMatch)
            and record.decision is MatchDecision.review_required
            and record.adjudication is None
        )
        or isinstance(record, ConflictGroup)
        if is_paired_or_conflict
        else None
    )
    inconclusive = (
        row.alignment_status.value == "inconclusive"
        if row.crossmatch_record_type == "unpaired"
        else None
    )
    return RowObservation(
        row=row,
        mapped_count=mapped_count,
        declared_null_count=declared_null_count,
        unresolved_count=unresolved_count,
        provenance_numerator=provenance_numerator,
        evidence_numerator=evidence_numerator,
        unit_numerator=unit_numerator,
        unit_denominator=unit_denominator,
        conflict_count=conflict_count,
        low_confidence=low_confidence,
        review_required=review_required,
        inconclusive=inconclusive,
    )


__all__ = ["DatasetObservation", "FieldObservation", "QualityObservationBundle", "RowObservation", "observe_quality"]
