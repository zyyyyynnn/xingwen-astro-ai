"""Single-pass Data Quality Evaluation observations over already-admitted Data Artifact/Cross-source Entity Alignment data."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field as dataclass_field
from typing import Any

from app.schemas.crossmatch import (
    ConfidenceBand,
    CrossmatchResult,
    PairedMatch,
    resolve_crossmatch_record_edge_components,
)
from app.schemas.data_artifacts import (
    CrossmatchArtifactAuthority,
    CrossmatchRowAuthority,
    DatasetArtifactCandidate,
    DatasetRow,
    DeclaredNullValue,
    FieldConflictRecord,
    MappedCanonicalValue,
    SourceTableArtifactAuthority,
    SourceTableRowAuthority,
    SourceValueCandidate,
    UnresolvedCanonicalValue,
)
from app.schemas.manifest import FieldDefinition, ManifestBundle
from app.schemas.source_table import SourceTableAdmission


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
    unit_consistent_assertion_count: int
    unit_applicable_assertion_count: int
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
    unit_consistent_assertion_count: int
    unit_applicable_assertion_count: int
    conflict_count: int
    low_confidence: bool | None
    confidence_applicable: bool
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
    unit_consistent_assertion_count: int
    unit_applicable_assertion_count: int
    same_source_conflict_cell_count: int
    cross_source_conflict_cell_count: int
    source_scope_numerator: int
    source_scope_denominator: int
    source_scope_insufficient: bool
    record_metrics: Any
    alignment_record_count: int
    validation_integrity: bool


@dataclass(frozen=True)
class QualityObservationBundle:
    fields: tuple[FieldObservation, ...]
    rows: tuple[RowObservation, ...]
    dataset: DatasetObservation


@dataclass
class _FieldAccumulator:
    field: FieldDefinition
    row_ids: list[str] = dataclass_field(default_factory=list)
    applicable_count: int = 0
    mapped_count: int = 0
    declared_null_count: int = 0
    unresolved_count: int = 0
    null_reasons: Counter[str] = dataclass_field(default_factory=Counter)
    provenance_numerator: int = 0
    evidence_numerator: int = 0
    unit_consistent_assertion_count: int = 0
    unit_applicable_assertion_count: int = 0
    conflict_cell_count: int = 0
    same_source_conflict_cell_count: int = 0
    cross_source_conflict_cell_count: int = 0
    evidence_ids: set[str] = dataclass_field(default_factory=set)


@dataclass(frozen=True)
class _MetricCounts:
    numerator: int
    denominator: int


@dataclass(frozen=True)
class SourceTableRecordMetrics:
    """Empty alignment metrics for a SourceTable that has no pairwise join."""

    match_coverage: _MetricCounts = _MetricCounts(0, 0)
    evidence_coverage: _MetricCounts = _MetricCounts(0, 0)
    low_confidence_count: int = 0
    candidate_pair_count: int = 0
    manual_review_required_count: int = 0
    paired_group_count: int = 0
    conflict_group_count: int = 0
    inconclusive_record_count: int = 0


def observe_quality(
    candidate: DatasetArtifactCandidate,
    crossmatch_result: CrossmatchResult | None,
    manifests: ManifestBundle,
    *,
    source_table_admission: SourceTableAdmission | None = None,
) -> QualityObservationBundle:
    """Aggregate every Data Artifact outcome once into field, row and dataset counters."""

    field_by_id = {column.field.field_id: column.field for column in candidate.columns}
    field_accumulators = {
        field_id: _FieldAccumulator(field=field_by_id[field_id])
        for field_id in candidate.requested_fields
    }
    unit_fields = {
        field_id
        for field_id, field in field_by_id.items()
        if "unit_consistency" in {item.value for item in field.quality_metric_inputs}
    }
    source_values = {item.source_value_id: item for item in candidate.source_values}
    evidence = {item.evidence_id: item for item in candidate.transformation_evidence}
    conflicts = {item.conflict_id: item for item in candidate.conflicts}
    source_snapshot_ids = set(candidate.source_snapshot_ids)
    retained_evidence_ids = set(candidate.evidence_ids)

    edge_components = (
        resolve_crossmatch_record_edge_components(crossmatch_result)
        if crossmatch_result is not None
        else {}
    )
    paired_records = (
        {
            record.logical_match_key: record
            for record in crossmatch_result.records
            if isinstance(record, PairedMatch)
        }
        if crossmatch_result is not None
        else {}
    )

    dataset_null_reasons: Counter[str] = Counter()
    dataset_applicable_count = 0
    dataset_mapped_count = 0
    dataset_declared_null_count = 0
    dataset_unresolved_count = 0
    dataset_provenance_count = 0
    dataset_evidence_count = 0
    dataset_unit_consistent_assertion_count = 0
    dataset_unit_applicable_assertion_count = 0
    dataset_same_source_conflict_count = 0
    dataset_cross_source_conflict_count = 0
    row_observations: list[RowObservation] = []

    for row in candidate.rows:
        row_mapped_count = 0
        row_declared_null_count = 0
        row_unresolved_count = 0
        row_provenance_count = 0
        row_evidence_count = 0
        row_unit_consistent_assertion_count = 0
        row_unit_applicable_assertion_count = 0
        row_conflict_count = 0

        for outcome in row.fields:
            field_id = outcome.canonical_field_id
            field = field_by_id[field_id]
            accumulator = field_accumulators[field_id]
            accumulator.row_ids.append(row.row_id)
            accumulator.applicable_count += 1
            dataset_applicable_count += 1

            conflict_ids: tuple[str, ...]
            if isinstance(outcome, MappedCanonicalValue):
                source_items = [
                    source_values[item] for item in outcome.candidate_source_value_ids
                ]
                evidence_items = [
                    evidence[item] for item in outcome.transformation_evidence_ids
                ]
                provenance_ok = bool(source_items) and all(
                    item.evidence_locator.source_snapshot_id in source_snapshot_ids
                    and item.evidence_locator.source_snapshot_content_hash
                    for item in source_items
                )
                evidence_ok = provenance_ok and bool(evidence_items) and all(
                    item.locator.source_snapshot_id in source_snapshot_ids
                    and item.evidence_id in retained_evidence_ids
                    for item in evidence_items
                )
                non_null_source_items = (
                    [item for item in source_items if item.canonical_value is not None]
                    if field_id in unit_fields
                    else []
                )
                unit_applicable_assertion_count = len(non_null_source_items)
                unit_consistent_assertion_count = sum(
                    item.canonical_unit == field.canonical_unit
                    for item in non_null_source_items
                )

                accumulator.mapped_count += 1
                accumulator.provenance_numerator += provenance_ok
                accumulator.evidence_numerator += evidence_ok
                accumulator.unit_applicable_assertion_count += (
                    unit_applicable_assertion_count
                )
                accumulator.unit_consistent_assertion_count += (
                    unit_consistent_assertion_count
                )
                accumulator.evidence_ids.update(outcome.transformation_evidence_ids)
                row_mapped_count += 1
                row_provenance_count += provenance_ok
                row_evidence_count += evidence_ok
                row_unit_applicable_assertion_count += unit_applicable_assertion_count
                row_unit_consistent_assertion_count += unit_consistent_assertion_count
                dataset_mapped_count += 1
                dataset_provenance_count += provenance_ok
                dataset_evidence_count += evidence_ok
                dataset_unit_applicable_assertion_count += unit_applicable_assertion_count
                dataset_unit_consistent_assertion_count += unit_consistent_assertion_count
                conflict_ids = tuple(outcome.conflict_ids)
            elif isinstance(outcome, DeclaredNullValue):
                reason = outcome.reason.value
                accumulator.declared_null_count += 1
                accumulator.null_reasons[reason] += 1
                row_declared_null_count += 1
                dataset_declared_null_count += 1
                dataset_null_reasons[reason] += 1
                conflict_ids = ()
            elif isinstance(outcome, UnresolvedCanonicalValue):
                accumulator.unresolved_count += 1
                row_unresolved_count += 1
                dataset_unresolved_count += 1
                conflict_ids = tuple(outcome.conflict_ids)
            else:
                raise ValueError("unsupported Data Artifact canonical outcome")

            if conflict_ids:
                scopes = {conflicts[item].conflict_scope for item in conflict_ids}
                same_source = "same_source" in scopes
                cross_source = "cross_source" in scopes
                accumulator.conflict_cell_count += 1
                accumulator.same_source_conflict_cell_count += same_source
                accumulator.cross_source_conflict_cell_count += cross_source
                row_conflict_count += 1
                dataset_same_source_conflict_count += same_source
                dataset_cross_source_conflict_count += cross_source

        if (
            crossmatch_result is not None
            and isinstance(row.row_authority, CrossmatchRowAuthority)
        ):
            paired_record = paired_records.get(row.row_authority.logical_key)
            confidence_applicable = (
                paired_record is not None
                and row.row_authority.logical_key in edge_components
                and paired_record.confidence_band
                in {ConfidenceBand.high, ConfidenceBand.medium, ConfidenceBand.low}
            )
            low_confidence = (
                paired_record.confidence_band is ConfidenceBand.low
                if confidence_applicable
                else None
            )
            is_adjudicable = row.row_authority.record_type in {
                "paired",
                "conflict_group",
            }
            review_required = (
                row.row_authority.alignment_status.value
                in {"review_required", "conflict"}
                if is_adjudicable
                else None
            )
            inconclusive = (
                row.row_authority.alignment_status.value == "inconclusive"
                if row.row_authority.record_type == "unpaired"
                else None
            )
        else:
            if not isinstance(row.row_authority, SourceTableRowAuthority):
                raise ValueError("unsupported Dataset row authority")
            confidence_applicable = False
            low_confidence = None
            review_required = None
            inconclusive = None
        row_observations.append(
            RowObservation(
                row=row,
                mapped_count=row_mapped_count,
                declared_null_count=row_declared_null_count,
                unresolved_count=row_unresolved_count,
                provenance_numerator=row_provenance_count,
                evidence_numerator=row_evidence_count,
                unit_consistent_assertion_count=row_unit_consistent_assertion_count,
                unit_applicable_assertion_count=row_unit_applicable_assertion_count,
                conflict_count=row_conflict_count,
                low_confidence=low_confidence,
                confidence_applicable=confidence_applicable,
                review_required=review_required,
                inconclusive=inconclusive,
            )
        )

    field_observations = tuple(
        _freeze_field_observation(
            field_accumulators[field_id],
            source_snapshot_ids=candidate.source_snapshot_ids,
        )
        for field_id in candidate.requested_fields
    )
    if crossmatch_result is not None:
        metrics = crossmatch_result.metrics
        source_members = (
            crossmatch_result.left_completion,
            crossmatch_result.right_completion,
        )
        source_scope_numerator = sum(
            item.status.value == "complete" for item in source_members
        )
        source_scope_denominator = len(source_members)
        alignment_record_count = len(crossmatch_result.records)
    else:
        if not isinstance(candidate.authority, SourceTableArtifactAuthority):
            raise ValueError("SourceTable quality observation requires SourceTable authority")
        if source_table_admission is None:
            raise ValueError("SourceTable quality observation requires its input admission")
        metrics = SourceTableRecordMetrics()
        source_scope_numerator = int(
            source_table_admission.source_result_status
            == "complete"
        )
        source_scope_denominator = 1
        alignment_record_count = 0
    source_scope_insufficient = source_scope_numerator != source_scope_denominator
    dataset_observation = DatasetObservation(
        row_count=len(candidate.rows),
        field_count=len(candidate.columns),
        applicable_cell_count=dataset_applicable_count,
        mapped_count=dataset_mapped_count,
        declared_null_count=dataset_declared_null_count,
        unresolved_count=dataset_unresolved_count,
        null_reasons=tuple(sorted(dataset_null_reasons.items())),
        provenance_numerator=dataset_provenance_count,
        evidence_numerator=dataset_evidence_count + metrics.evidence_coverage.numerator,
        evidence_denominator=dataset_mapped_count + metrics.evidence_coverage.denominator,
        unit_consistent_assertion_count=dataset_unit_consistent_assertion_count,
        unit_applicable_assertion_count=dataset_unit_applicable_assertion_count,
        same_source_conflict_cell_count=dataset_same_source_conflict_count,
        cross_source_conflict_cell_count=dataset_cross_source_conflict_count,
        source_scope_numerator=source_scope_numerator,
        source_scope_denominator=source_scope_denominator,
        source_scope_insufficient=source_scope_insufficient,
        record_metrics=metrics,
        alignment_record_count=alignment_record_count,
        validation_integrity=True,
    )
    return QualityObservationBundle(
        fields=field_observations,
        rows=tuple(row_observations),
        dataset=dataset_observation,
    )


def _freeze_field_observation(
    item: _FieldAccumulator,
    *,
    source_snapshot_ids: tuple[str, ...],
) -> FieldObservation:
    return FieldObservation(
        field=item.field,
        row_ids=tuple(item.row_ids),
        applicable_count=item.applicable_count,
        mapped_count=item.mapped_count,
        declared_null_count=item.declared_null_count,
        unresolved_count=item.unresolved_count,
        null_reasons=tuple(sorted(item.null_reasons.items())),
        provenance_numerator=item.provenance_numerator,
        evidence_numerator=item.evidence_numerator,
        unit_consistent_assertion_count=item.unit_consistent_assertion_count,
        unit_applicable_assertion_count=item.unit_applicable_assertion_count,
        conflict_cell_count=item.conflict_cell_count,
        same_source_conflict_cell_count=item.same_source_conflict_cell_count,
        cross_source_conflict_cell_count=item.cross_source_conflict_cell_count,
        source_snapshot_ids=source_snapshot_ids,
        evidence_ids=tuple(sorted(item.evidence_ids)),
    )


def field_metric_observations(item: FieldObservation) -> dict[str, int | bool]:
    return {
        "field.mapped_count": item.mapped_count,
        "field.applicable_count": item.applicable_count,
        "field.declared_null_count": item.declared_null_count,
        "field.missing_count": item.declared_null_count + item.unresolved_count,
        "field.unresolved_count": item.unresolved_count,
        "field.provenance_count": item.provenance_numerator,
        "field.evidence_count": item.evidence_numerator,
        "field.unit_consistent_assertion_count": item.unit_consistent_assertion_count,
        "field.unit_applicable_assertion_count": item.unit_applicable_assertion_count,
        "field.same_source_conflict_count": item.same_source_conflict_cell_count,
        "field.cross_source_conflict_count": item.cross_source_conflict_cell_count,
    }


def row_metric_observations(item: RowObservation) -> dict[str, int | bool]:
    is_crossmatch = isinstance(item.row.row_authority, CrossmatchRowAuthority)
    is_adjudicable = is_crossmatch and item.row.row_authority.record_type in {
        "paired",
        "conflict_group",
    }
    is_unpaired = is_crossmatch and item.row.row_authority.record_type == "unpaired"
    return {
        "row.mapped_count": item.mapped_count,
        "row.applicable_field_count": len(item.row.projected_field_ids),
        "row.missing_count": item.declared_null_count + item.unresolved_count,
        "row.unresolved_count": item.unresolved_count,
        "row.provenance_count": item.provenance_numerator,
        "row.evidence_count": item.evidence_numerator,
        "row.unit_consistent_assertion_count": item.unit_consistent_assertion_count,
        "row.unit_applicable_assertion_count": item.unit_applicable_assertion_count,
        "row.conflict_count": item.conflict_count,
        "row.low_confidence_flag": bool(item.low_confidence),
        "row.review_required_flag": bool(item.review_required),
        "row.inconclusive_flag": bool(item.inconclusive),
        "row.confidence_applicable_record_count": int(item.confidence_applicable),
        "row.adjudicable_record_count": int(is_adjudicable),
        "row.unpaired_record_count": int(is_unpaired),
    }


def dataset_metric_observations(item: DatasetObservation) -> dict[str, int | bool]:
    metrics = item.record_metrics
    return {
        "dataset.mapped_count": item.mapped_count,
        "dataset.applicable_cell_count": item.applicable_cell_count,
        "dataset.missing_count": item.declared_null_count + item.unresolved_count,
        "dataset.unresolved_count": item.unresolved_count,
        "dataset.provenance_count": item.provenance_numerator,
        "dataset.evidence_count": item.evidence_numerator,
        "dataset.evidence_applicable_count": item.evidence_denominator,
        "dataset.unit_consistent_assertion_count": item.unit_consistent_assertion_count,
        "dataset.unit_applicable_assertion_count": item.unit_applicable_assertion_count,
        "dataset.same_source_conflict_count": item.same_source_conflict_cell_count,
        "dataset.cross_source_conflict_count": item.cross_source_conflict_cell_count,
        "dataset.object_match_count": metrics.match_coverage.numerator,
        "dataset.object_candidate_count": metrics.match_coverage.denominator,
        "dataset.low_confidence_edge_count": metrics.low_confidence_count,
        "dataset.candidate_edge_count": metrics.candidate_pair_count,
        "dataset.review_required_record_count": metrics.manual_review_required_count,
        "dataset.adjudicable_record_count": (
            metrics.paired_group_count + metrics.conflict_group_count
        ),
        "dataset.inconclusive_record_count": metrics.inconclusive_record_count,
        "dataset.crossmatch_record_count": item.alignment_record_count,
        "dataset.complete_source_count": item.source_scope_numerator,
        "dataset.required_source_count": item.source_scope_denominator,
        "dataset.validation_pass_count": int(item.validation_integrity),
        "dataset.validation_check_count": 1,
    }


__all__ = [
    "DatasetObservation",
    "FieldObservation",
    "QualityObservationBundle",
    "RowObservation",
    "dataset_metric_observations",
    "field_metric_observations",
    "observe_quality",
    "row_metric_observations",
]
