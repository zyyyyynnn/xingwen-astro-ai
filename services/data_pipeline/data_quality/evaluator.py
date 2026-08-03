"""Public C-05 evaluator entry point."""

from __future__ import annotations

import json
from collections import Counter
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ValidationError

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.core import ArtifactKind
from app.schemas.crossmatch import compute_crossmatch_metrics
from app.schemas.data_artifacts import (
    DataArtifactBuildInput,
    DatasetArtifactCandidate,
    FieldDictionaryArtifactCandidate,
    SourceCollectionArtifactCandidate,
    compute_data_artifact_input_hash,
)
from app.schemas.data_quality import (
    DataQualityEvaluationInput,
    DataQualityEvaluationOutcome,
    DataQualityEvaluationRejected,
    DataQualityEvaluationResult,
    DataQualityRuleSet,
    DatasetQualityResult,
    FieldQualityResult,
    QualityAggregateScorePolicy,
    QualityArtifactReference,
    QualityCount,
    QualityErrorCode,
    QualityFailureStage,
    QualityGateStatus,
    QualityInputReferences,
    QualityManifestFieldReference,
    QualityMetricId,
    QualityMetricResult,
    QualityMetricScope,
    QualityMetricStatus,
    QualityProducerReference,
    ResearchContractQualityGate,
    RowQualityResult,
    compute_data_quality_result_id,
    compute_quality_content_hash,
    compute_quality_output_hash,
)
from app.schemas.manifest import ManifestBundle, load_manifest_bundle
from services.data_pipeline.data_artifacts.admission import (
    validate_data_artifact_candidates_against_input,
)
from services.data_pipeline.manifest import load_frozen_manifest_bundle

from .contract_gate import evaluate_contract_gate
from .errors import DataQualityError
from .formulas import make_metric, not_applicable_metric
from .observations import (
    FieldObservation,
    QualityObservationBundle,
    RowObservation,
    observe_quality,
)
from .policy import require_frozen_quality_rule_set


def evaluate_data_quality(
    value: DataQualityEvaluationInput | dict[str, Any],
) -> DataQualityEvaluationOutcome:
    """Revalidate caller input, compute deterministic raw metrics and gate them."""

    input_hash: str | None = None
    try:
        evaluation_input = _reparse_input(value)
        input_hash = evaluation_input.input_hash
        try:
            rules = require_frozen_quality_rule_set(evaluation_input.quality_rule_set)
        except Exception as error:
            raise DataQualityError(
                QualityErrorCode.QUALITY_RULE_SET_MISMATCH,
                "caller quality RuleSet is not the frozen repository RuleSet",
                stage=QualityFailureStage.rule_validation,
                cause=error,
            ) from error
        manifests = load_frozen_manifest_bundle()
        _validate_input_bindings(evaluation_input, manifests, rules)
        observations = observe_quality(
            evaluation_input.dataset_candidate,
            evaluation_input.data_artifact_input.crossmatch_result,
            manifests,
        )
        field_results = _build_field_results(evaluation_input, observations, rules, manifests)
        row_results = _build_row_results(evaluation_input, observations, rules)
        dataset_result = _build_dataset_result(evaluation_input, observations, rules)
        gate = evaluate_contract_gate(
            evaluation_input.research_contract,
            dataset_candidate=evaluation_input.dataset_candidate,
            source_collection_candidate=evaluation_input.source_collection_candidate,
            dataset_result=dataset_result,
            manifests=manifests,
            rules=rules,
        )
        return _build_result(
            evaluation_input,
            rules,
            field_results,
            row_results,
            dataset_result,
            gate,
        )
    except DataQualityError as error:
        return _rejected(error, input_hash=input_hash)
    except (ValidationError, TypeError, ValueError, KeyError) as error:
        return _rejected(
            DataQualityError(
                QualityErrorCode.QUALITY_INPUT_INVALID,
                "quality input failed deterministic validation",
                stage=QualityFailureStage.input_validation,
                cause=error,
            ),
            input_hash=input_hash,
        )


def _reparse_input(value: DataQualityEvaluationInput | dict[str, Any]) -> DataQualityEvaluationInput:
    try:
        if isinstance(value, BaseModel):
            payload = value.model_dump(mode="json")
        else:
            payload = value
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return DataQualityEvaluationInput.model_validate_json(encoded)
    except Exception as error:
        raise DataQualityError(
            QualityErrorCode.QUALITY_INPUT_INVALID,
            "quality input failed JSON/Pydantic revalidation",
            stage=QualityFailureStage.input_validation,
            cause=error,
        ) from error


def _validate_input_bindings(
    value: DataQualityEvaluationInput,
    manifests: ManifestBundle,
    rules: DataQualityRuleSet,
) -> None:
    data_input = value.data_artifact_input
    candidates = (
        value.dataset_candidate,
        value.field_dictionary_candidate,
        value.source_collection_candidate,
    )
    if compute_data_artifact_input_hash(data_input) != data_input.input_hash:
        _fail(QualityErrorCode.QUALITY_C04_CANDIDATE_MISMATCH, QualityFailureStage.c04_validation)
    for candidate in candidates:
        try:
            validate_data_artifact_candidates_against_input(candidate, data_input)
        except Exception as error:
            raise DataQualityError(
                QualityErrorCode.QUALITY_C04_CANDIDATE_MISMATCH,
                "C-04 candidate does not match its immutable build input",
                stage=QualityFailureStage.c04_validation,
                cause=error,
            ) from error
    _validate_candidate_cross_bindings(candidates, data_input)
    expected_pins = (
        rules.case_manifest_id,
        rules.case_manifest_version,
        rules.case_manifest_content_hash,
        rules.field_manifest_id,
        rules.field_manifest_version,
        rules.field_manifest_content_hash,
    )
    actual_pins = (
        data_input.manifest_pins.case_manifest_id,
        data_input.manifest_pins.case_manifest_version,
        data_input.manifest_pins.case_manifest_content_hash,
        data_input.manifest_pins.field_manifest_id,
        data_input.manifest_pins.field_manifest_version,
        data_input.manifest_pins.field_manifest_content_hash,
    )
    if actual_pins != expected_pins:
        _fail(QualityErrorCode.QUALITY_C04_CANDIDATE_MISMATCH, QualityFailureStage.c04_validation)
    result = data_input.crossmatch_result
    recomputed_metrics = compute_crossmatch_metrics(
        result.candidates,
        result.candidate_edges,
        result.records,
        result.evidence,
    )
    if recomputed_metrics != result.metrics:
        _fail(
            QualityErrorCode.QUALITY_CROSSMATCH_METRICS_MISMATCH,
            QualityFailureStage.crossmatch_validation,
        )
    _validate_research_contract(value, manifests)
    _validate_quality_evidence(value)
    _validate_capacity(value, rules)


def _validate_candidate_cross_bindings(
    candidates: tuple[
        DatasetArtifactCandidate,
        FieldDictionaryArtifactCandidate,
        SourceCollectionArtifactCandidate,
    ],
    data_input: DataArtifactBuildInput,
) -> None:
    dataset, field_dictionary, source_collection = candidates
    if any(candidate.quality_evaluation_status != "not_evaluated" for candidate in candidates):
        _fail(QualityErrorCode.QUALITY_C04_CANDIDATE_MISMATCH, QualityFailureStage.c04_validation)
    if tuple(dataset.requested_fields) != tuple(field_dictionary.requested_fields):
        _fail(QualityErrorCode.QUALITY_C04_CANDIDATE_MISMATCH, QualityFailureStage.c04_validation)
    if tuple(column.field for column in dataset.columns) != tuple(field_dictionary.field_definitions):
        _fail(QualityErrorCode.QUALITY_C04_CANDIDATE_MISMATCH, QualityFailureStage.c04_validation)
    if source_collection.source_value_ids != tuple(item.source_value_id for item in dataset.source_values):
        _fail(QualityErrorCode.QUALITY_C04_CANDIDATE_MISMATCH, QualityFailureStage.c04_validation)
    if (
        source_collection.crossmatch_result_id != dataset.crossmatch_result_id
        or source_collection.crossmatch_content_hash != dataset.crossmatch_content_hash
    ):
        _fail(QualityErrorCode.QUALITY_C04_CANDIDATE_MISMATCH, QualityFailureStage.c04_validation)
    if any(candidate.input_hash != data_input.input_hash for candidate in candidates):
        _fail(QualityErrorCode.QUALITY_C04_CANDIDATE_MISMATCH, QualityFailureStage.c04_validation)


def _validate_research_contract(value: DataQualityEvaluationInput, manifests: ManifestBundle) -> None:
    contract = value.research_contract
    dataset = value.dataset_candidate
    try:
        manifests.validate_requested_fields(contract.requested_fields)
        if tuple(sorted(contract.requested_fields)) != tuple(dataset.requested_fields):
            raise ValueError("Contract requested_fields differ from Dataset projection")
        if contract.data_requirements.unit_policy.value != "canonical":
            raise ValueError("only canonical unit policy is admitted")
        if ArtifactKind.dataset not in contract.output_requirements:
            raise ValueError("C-05 requires Dataset in Contract output_requirements")
        manifests.resolve_source_scope(contract.source_scope.allowed_sources)
    except Exception as error:
        raise DataQualityError(
            QualityErrorCode.QUALITY_RESEARCH_CONTRACT_MISMATCH,
            "ResearchContract is outside the frozen C-05 input binding",
            stage=QualityFailureStage.contract_validation,
            cause=error,
        ) from error


def _validate_quality_evidence(value: DataQualityEvaluationInput) -> None:
    dataset = value.dataset_candidate
    source_values = {item.source_value_id: item for item in dataset.source_values}
    evidence = {item.evidence_id: item for item in dataset.transformation_evidence}
    snapshots = set(dataset.source_snapshot_ids)
    try:
        for row in dataset.rows:
            for outcome in row.fields:
                if getattr(outcome, "status", None) != "mapped":
                    continue
                source_items = [source_values[item] for item in outcome.candidate_source_value_ids]
                evidence_items = [evidence[item] for item in outcome.transformation_evidence_ids]
                if not source_items or not evidence_items:
                    raise ValueError("mapped outcome lacks retained SourceValue/Evidence")
                if any(item.evidence_locator.source_snapshot_id not in snapshots for item in source_items):
                    raise ValueError("SourceValue Evidence locator lacks its SourceSnapshot")
                if any(item.locator.source_snapshot_id not in snapshots for item in evidence_items):
                    raise ValueError("Transformation Evidence locator lacks its SourceSnapshot")
                if {item.source_value_id for item in evidence_items} != {
                    item.source_value_id for item in source_items
                }:
                    raise ValueError("mapped outcome does not retain Evidence for every candidate")
        crossmatch_evidence_ids = set(dataset.crossmatch_evidence_ids)
        for record in value.data_artifact_input.crossmatch_result.records:
            if getattr(record, "record_type", None) in {"paired", "conflict_group"}:
                if not set(record.evidence_ids) <= crossmatch_evidence_ids:
                    raise ValueError("audited Crossmatch record lacks Crossmatch Evidence")
    except Exception as error:
        raise DataQualityError(
            QualityErrorCode.QUALITY_EVIDENCE_GAP,
            "required Evidence locator or SourceSnapshot coverage is incomplete",
            stage=QualityFailureStage.evidence_validation,
            cause=error,
        ) from error


def _validate_capacity(value: DataQualityEvaluationInput, rules: DataQualityRuleSet) -> None:
    dataset = value.dataset_candidate
    result = value.data_artifact_input.crossmatch_result
    counts = {
        "rows": len(dataset.rows),
        "fields": len(dataset.columns),
        "cells": sum(len(row.projected_field_ids) for row in dataset.rows),
        "source_values": len(dataset.source_values),
        "evidence": len(dataset.evidence_ids),
        "conflict_references": sum(len(row.conflict_ids) for row in dataset.rows),
        "crossmatch_edges": len(result.candidate_edges),
        "metric_records": len(dataset.rows) * max(1, len(dataset.columns)) * 30,
        "diagnostic_references": len(result.metrics.error_example_references),
    }
    limits = {
        "rows": rules.capacity.max_rows,
        "fields": rules.capacity.max_fields,
        "cells": rules.capacity.max_cells,
        "source_values": rules.capacity.max_source_values,
        "evidence": rules.capacity.max_evidence,
        "conflict_references": rules.capacity.max_conflict_references,
        "crossmatch_edges": rules.capacity.max_crossmatch_edges,
        "metric_records": rules.capacity.max_metric_records,
        "diagnostic_references": rules.capacity.max_diagnostic_references,
    }
    for name, count in counts.items():
        if count > limits[name]:
            raise DataQualityError(
                QualityErrorCode.QUALITY_CAPACITY_EXCEEDED,
                "quality evaluation input exceeds its frozen capacity",
                stage=QualityFailureStage.capacity_preflight,
            )


def _build_field_results(
    value: DataQualityEvaluationInput,
    observations: QualityObservationBundle,
    rules: DataQualityRuleSet,
    manifests: ManifestBundle,
) -> tuple[FieldQualityResult, ...]:
    results: list[FieldQualityResult] = []
    for observation in observations.fields:
        field = observation.field
        declared = {item.value for item in field.quality_metric_inputs}
        prefix = f"dataset.field.{field.field_id}"
        completeness = _declared_metric(
            rules,
            QualityMetricId.field_completeness,
            QualityMetricScope.field,
            field.field_id,
            "completeness" in declared,
            observation.mapped_count,
            observation.applicable_count,
            f"{prefix}.completeness",
        )
        missingness = _declared_metric(
            rules,
            QualityMetricId.field_missingness,
            QualityMetricScope.field,
            field.field_id,
            "missingness" in declared,
            observation.declared_null_count + observation.unresolved_count,
            observation.applicable_count,
            f"{prefix}.missingness",
        )
        unresolved = _declared_metric(
            rules,
            QualityMetricId.field_unresolved_rate,
            QualityMetricScope.field,
            field.field_id,
            "missingness" in declared,
            observation.unresolved_count,
            observation.applicable_count,
            f"{prefix}.unresolved_rate",
        )
        provenance = _declared_metric(
            rules,
            QualityMetricId.field_provenance_coverage,
            QualityMetricScope.field,
            field.field_id,
            "evidence_coverage" in declared,
            observation.provenance_numerator,
            observation.mapped_count,
            f"{prefix}.provenance_coverage",
        )
        evidence = _declared_metric(
            rules,
            QualityMetricId.field_evidence_coverage,
            QualityMetricScope.field,
            field.field_id,
            "evidence_coverage" in declared,
            observation.evidence_numerator,
            observation.mapped_count,
            f"{prefix}.evidence_coverage",
        )
        unit = _declared_metric(
            rules,
            QualityMetricId.field_unit_consistency,
            QualityMetricScope.field,
            field.field_id,
            "unit_consistency" in declared,
            observation.unit_numerator,
            observation.unit_denominator,
            f"{prefix}.unit_consistency",
        )
        same = _declared_metric(
            rules,
            QualityMetricId.field_conflict_rate,
            QualityMetricScope.field,
            field.field_id,
            "conflict" in declared,
            observation.same_source_conflict_cell_count,
            observation.applicable_count,
            f"{prefix}.same_source_conflict_rate",
        )
        cross = _declared_metric(
            rules,
            QualityMetricId.field_conflict_rate,
            QualityMetricScope.field,
            field.field_id,
            "conflict" in declared,
            observation.cross_source_conflict_cell_count,
            observation.applicable_count,
            f"{prefix}.cross_source_conflict_rate",
        )
        payload = {
            "field_id": field.field_id,
            "field_manifest_reference": QualityManifestFieldReference(
                field_id=field.field_id,
                manifest_id=manifests.field_manifest.manifest_id,
                manifest_version=manifests.field_manifest.manifest_version,
                manifest_content_hash=manifests.field_manifest.content_hash,
            ).model_dump(mode="json"),
            "applicable_row_count": observation.applicable_count,
            "mapped_count": observation.mapped_count,
            "declared_null_count": observation.declared_null_count,
            "unresolved_count": observation.unresolved_count,
            "null_reason_distribution": [
                {"key": key, "count": count} for key, count in observation.null_reasons
            ],
            "completeness": completeness.model_dump(mode="json"),
            "missingness": missingness.model_dump(mode="json"),
            "unresolved_rate": unresolved.model_dump(mode="json"),
            "provenance_coverage": provenance.model_dump(mode="json"),
            "evidence_coverage": evidence.model_dump(mode="json"),
            "unit_consistency": unit.model_dump(mode="json"),
            "same_source_conflict_rate": same.model_dump(mode="json"),
            "cross_source_conflict_rate": cross.model_dump(mode="json"),
            "source_snapshot_ids": list(observation.source_snapshot_ids),
            "evidence_ids": list(observation.evidence_ids),
            "row_ids": list(observation.row_ids),
            "rule_references": [rules.rule_set_id, field.field_id],
        }
        results.append(FieldQualityResult(**payload, content_hash=compute_quality_content_hash(payload)))
    return tuple(results)


def _build_row_results(
    value: DataQualityEvaluationInput,
    observations: QualityObservationBundle,
    rules: DataQualityRuleSet,
) -> tuple[RowQualityResult, ...]:
    results: list[RowQualityResult] = []
    for observation in observations.rows:
        row = observation.row
        prefix = f"dataset.row.{row.row_id}"
        metrics = {
            "completeness": _metric_or_na(rules, QualityMetricId.row_completeness, QualityMetricScope.row, row.row_id, observation.mapped_count, len(row.projected_field_ids), f"{prefix}.completeness"),
            "missingness": _metric_or_na(rules, QualityMetricId.row_missingness, QualityMetricScope.row, row.row_id, observation.declared_null_count + observation.unresolved_count, len(row.projected_field_ids), f"{prefix}.missingness"),
            "unresolved_rate": _metric_or_na(rules, QualityMetricId.row_unresolved_rate, QualityMetricScope.row, row.row_id, observation.unresolved_count, len(row.projected_field_ids), f"{prefix}.unresolved_rate"),
            "provenance_coverage": _metric_or_na(rules, QualityMetricId.row_provenance_coverage, QualityMetricScope.row, row.row_id, observation.provenance_numerator, observation.mapped_count, f"{prefix}.provenance_coverage"),
            "evidence_coverage": _metric_or_na(rules, QualityMetricId.row_evidence_coverage, QualityMetricScope.row, row.row_id, observation.evidence_numerator, observation.mapped_count, f"{prefix}.evidence_coverage"),
            "unit_consistency": _metric_or_na(rules, QualityMetricId.row_unit_consistency, QualityMetricScope.row, row.row_id, observation.unit_numerator, observation.unit_denominator, f"{prefix}.unit_consistency"),
            "conflict_rate": _metric_or_na(rules, QualityMetricId.row_conflict_rate, QualityMetricScope.row, row.row_id, observation.conflict_count, len(row.projected_field_ids), f"{prefix}.conflict_rate"),
            "low_confidence": _boolean_metric(rules, QualityMetricId.low_confidence_edge_rate, QualityMetricScope.row, row.row_id, observation.low_confidence, f"{prefix}.low_confidence"),
            "review_required": _boolean_metric(rules, QualityMetricId.review_required_record_rate, QualityMetricScope.row, row.row_id, observation.review_required, f"{prefix}.review_required"),
            "inconclusive": _boolean_metric(rules, QualityMetricId.inconclusive_record_rate, QualityMetricScope.row, row.row_id, observation.inconclusive, f"{prefix}.inconclusive"),
        }
        payload = {
            "row_id": row.row_id,
            "canonical_row_identity": row.canonical_row_identity.model_dump(mode="json"),
            "entity_level": row.entity_level.value,
            "alignment_status": row.alignment_status.value,
            "applicable_field_count": len(row.projected_field_ids),
            "mapped_count": observation.mapped_count,
            "declared_null_count": observation.declared_null_count,
            "unresolved_count": observation.unresolved_count,
            **{key: metric.model_dump(mode="json") for key, metric in metrics.items()},
            "field_ids": list(row.projected_field_ids),
            "conflict_ids": list(row.conflict_ids),
            "evidence_ids": list(row.evidence_ids),
            "source_snapshot_ids": list(row.source_snapshot_ids),
            "crossmatch_logical_key": row.crossmatch_logical_key,
        }
        results.append(RowQualityResult(**payload, content_hash=compute_quality_content_hash(payload)))
    return tuple(results)


def _build_dataset_result(
    value: DataQualityEvaluationInput,
    observations: QualityObservationBundle,
    rules: DataQualityRuleSet,
) -> DatasetQualityResult:
    item = observations.dataset
    prefix = "dataset"
    metrics = {
        "completeness": _metric_or_na(rules, QualityMetricId.dataset_completeness, QualityMetricScope.dataset, "dataset", item.mapped_count, item.applicable_cell_count, f"{prefix}.completeness"),
        "missingness": _metric_or_na(rules, QualityMetricId.dataset_missingness, QualityMetricScope.dataset, "dataset", item.declared_null_count + item.unresolved_count, item.applicable_cell_count, f"{prefix}.missingness"),
        "unresolved_rate": _metric_or_na(rules, QualityMetricId.dataset_unresolved_rate, QualityMetricScope.dataset, "dataset", item.unresolved_count, item.applicable_cell_count, f"{prefix}.unresolved_rate"),
        "provenance_coverage": _metric_or_na(rules, QualityMetricId.dataset_provenance_coverage, QualityMetricScope.dataset, "dataset", item.provenance_numerator, item.mapped_count, f"{prefix}.provenance_coverage"),
        "evidence_coverage": _metric_or_na(rules, QualityMetricId.dataset_evidence_coverage, QualityMetricScope.dataset, "dataset", item.evidence_numerator, item.evidence_denominator, f"{prefix}.evidence_coverage"),
        "unit_consistency": _metric_or_na(rules, QualityMetricId.dataset_unit_consistency, QualityMetricScope.dataset, "dataset", item.unit_numerator, item.unit_denominator, f"{prefix}.unit_consistency"),
        "same_source_conflict_rate": _metric_or_na(rules, QualityMetricId.dataset_same_source_conflict_rate, QualityMetricScope.dataset, "dataset", item.same_source_conflict_cell_count, item.applicable_cell_count, f"{prefix}.same_source_conflict_rate"),
        "cross_source_conflict_rate": _metric_or_na(rules, QualityMetricId.dataset_cross_source_conflict_rate, QualityMetricScope.dataset, "dataset", item.cross_source_conflict_cell_count, item.applicable_cell_count, f"{prefix}.cross_source_conflict_rate"),
        "object_match_coverage": _ratio_from_crossmatch(rules, QualityMetricId.object_match_coverage, item.crossmatch_metrics.match_coverage.numerator, item.crossmatch_metrics.match_coverage.denominator, f"{prefix}.object_match_coverage"),
        "low_confidence_edge_rate": _ratio_from_crossmatch(rules, QualityMetricId.low_confidence_edge_rate, item.crossmatch_metrics.low_confidence_count, item.crossmatch_metrics.candidate_pair_count, f"{prefix}.low_confidence_edge_rate"),
        "review_required_record_rate": _ratio_from_crossmatch(rules, QualityMetricId.review_required_record_rate, item.crossmatch_metrics.manual_review_required_count, item.crossmatch_metrics.paired_group_count + item.crossmatch_metrics.conflict_group_count, f"{prefix}.review_required_record_rate"),
        "inconclusive_record_rate": _ratio_from_crossmatch(rules, QualityMetricId.inconclusive_record_rate, item.crossmatch_metrics.inconclusive_record_count, item.crossmatch_record_count, f"{prefix}.inconclusive_record_rate"),
        "source_scope_completeness": _metric_or_na(rules, QualityMetricId.source_scope_completeness, QualityMetricScope.dataset, "dataset", item.source_scope_numerator, item.source_scope_denominator, f"{prefix}.source_scope_completeness", insufficient=item.source_scope_insufficient),
        "validation_integrity": _ratio_from_crossmatch(rules, QualityMetricId.validation_integrity, 1 if item.validation_integrity else 0, 1, f"{prefix}.validation_integrity"),
    }
    payload = {
        "row_count": item.row_count,
        "field_count": item.field_count,
        "applicable_cell_count": item.applicable_cell_count,
        "mapped_count": item.mapped_count,
        "declared_null_count": item.declared_null_count,
        "unresolved_count": item.unresolved_count,
        "null_reason_distribution": [{"key": key, "count": count} for key, count in item.null_reasons],
        **{key: metric.model_dump(mode="json") for key, metric in metrics.items()},
        "field_result_ids": [field.field.field_id for field in value.dataset_candidate.columns],
        "row_result_ids": [row.row_id for row in value.dataset_candidate.rows],
        "source_snapshot_ids": list(value.dataset_candidate.source_snapshot_ids),
        "evidence_ids": list(value.dataset_candidate.evidence_ids),
        "raw_status_distribution": [
            {"key": key, "count": count}
            for key, count in sorted(Counter(row.alignment_status.value for row in value.dataset_candidate.rows).items())
        ],
    }
    return DatasetQualityResult(**payload, content_hash=compute_quality_content_hash(payload))


def _build_result(
    value: DataQualityEvaluationInput,
    rules: DataQualityRuleSet,
    fields: tuple[FieldQualityResult, ...],
    rows: tuple[RowQualityResult, ...],
    dataset: DatasetQualityResult,
    gate: ResearchContractQualityGate,
) -> DataQualityEvaluationResult:
    dataset_candidate = value.dataset_candidate
    field_candidate = value.field_dictionary_candidate
    source_candidate = value.source_collection_candidate
    candidates = (
        QualityArtifactReference(
            kind="dataset",
            candidate_id=dataset_candidate.candidate_id,
            input_hash=dataset_candidate.input_hash,
            output_hash=dataset_candidate.output_hash,
            canonical_content_hash=dataset_candidate.canonical_content_hash,
            lineage_hash=dataset_candidate.lineage_hash,
        ),
        QualityArtifactReference(
            kind="field_dictionary",
            candidate_id=field_candidate.candidate_id,
            input_hash=field_candidate.input_hash,
            output_hash=field_candidate.output_hash,
        ),
        QualityArtifactReference(
            kind="source_collection",
            candidate_id=source_candidate.candidate_id,
            input_hash=source_candidate.input_hash,
            output_hash=source_candidate.output_hash,
        ),
    )
    input_refs = QualityInputReferences(
        c04_input_hash=value.data_artifact_input.input_hash,
        candidates=candidates,
        crossmatch_result_id=value.data_artifact_input.crossmatch_result.result_id,
        crossmatch_input_hash=value.data_artifact_input.crossmatch_result.input_hash,
        crossmatch_output_hash=value.data_artifact_input.crossmatch_result.output_hash,
        crossmatch_content_hash=value.data_artifact_input.crossmatch_result.content_hash,
        research_contract_id=value.research_contract.id,
        research_contract_version=value.research_contract.version,
        research_contract_content_hash=value.research_contract.content_hash,
        quality_rule_set_id=rules.rule_set_id,
        quality_rule_set_version=rules.version,
        quality_rule_set_content_hash=rules.content_hash,
    )
    rule_reference = QualityArtifactReference(
        kind="quality_rule_set",
        candidate_id=rules.rule_set_id,
        input_hash=rules.content_hash,
        output_hash=rules.content_hash,
    )
    contract_reference = QualityArtifactReference(
        kind="research_contract",
        candidate_id=value.research_contract.id,
        input_hash=value.research_contract.content_hash,
        output_hash=value.research_contract.content_hash,
    )
    payload = {
        "kind": "data_quality",
        "schema_version": "1.0.0",
        "result_id": compute_data_quality_result_id(value.input_hash, rules.content_hash),
        "input_references": input_refs.model_dump(mode="json"),
        "quality_rule_set_reference": rule_reference.model_dump(mode="json"),
        "research_contract_reference": contract_reference.model_dump(mode="json"),
        "field_results": [item.model_dump(mode="json") for item in fields],
        "row_results": [item.model_dump(mode="json") for item in rows],
        "dataset_result": dataset.model_dump(mode="json"),
        "contract_gate": gate.model_dump(mode="json"),
        "aggregate_score": None,
        "aggregate_score_policy": rules.aggregate_score_policy.model_dump(mode="json"),
        "source_snapshot_ids": list(dataset_candidate.source_snapshot_ids),
        "evidence_ids": list(dataset_candidate.evidence_ids),
        "producer": {
            "producer_type": "algorithm",
            "producer_name": rules.producer_name,
            "producer_version": rules.producer_version,
        },
        "input_hash": value.input_hash,
    }
    output_hash = compute_quality_output_hash(payload)
    payload["output_hash"] = output_hash
    payload["content_hash"] = compute_quality_content_hash(payload)
    return DataQualityEvaluationResult(**payload)


def _declared_metric(
    rules: DataQualityRuleSet,
    metric_id: QualityMetricId,
    scope: QualityMetricScope,
    target_id: str,
    declared: bool,
    numerator: int,
    denominator: int,
    locator: str,
) -> QualityMetricResult:
    if not declared:
        return not_applicable_metric(rules, metric_id=metric_id, scope=scope, target_id=target_id, input_locator=locator)
    return _metric_or_na(rules, metric_id, scope, target_id, numerator, denominator, locator)


def _metric_or_na(
    rules: DataQualityRuleSet,
    metric_id: QualityMetricId,
    scope: QualityMetricScope,
    target_id: str,
    numerator: int,
    denominator: int,
    locator: str,
    *,
    insufficient: bool = False,
) -> QualityMetricResult:
    if insufficient:
        return make_metric(
            rules,
            metric_id=metric_id,
            scope=scope,
            target_id=target_id,
            numerator=numerator,
            denominator=denominator,
            status=QualityMetricStatus.insufficient,
            input_locator=locator,
        )
    if denominator <= 0:
        return not_applicable_metric(rules, metric_id=metric_id, scope=scope, target_id=target_id, input_locator=locator)
    return make_metric(
        rules,
        metric_id=metric_id,
        scope=scope,
        target_id=target_id,
        numerator=numerator,
        denominator=denominator,
        input_locator=locator,
    )


def _ratio_from_crossmatch(
    rules: DataQualityRuleSet,
    metric_id: QualityMetricId,
    numerator: int,
    denominator: int,
    locator: str,
) -> QualityMetricResult:
    return _metric_or_na(rules, metric_id, QualityMetricScope.dataset, "dataset", numerator, denominator, locator)


def _boolean_metric(
    rules: DataQualityRuleSet,
    metric_id: QualityMetricId,
    scope: QualityMetricScope,
    target_id: str,
    value: bool | None,
    locator: str,
) -> QualityMetricResult:
    if value is None:
        return not_applicable_metric(rules, metric_id=metric_id, scope=scope, target_id=target_id, input_locator=locator)
    return make_metric(
        rules,
        metric_id=metric_id,
        scope=scope,
        target_id=target_id,
        numerator=int(value),
        denominator=1,
        input_locator=locator,
    )


def _rejected(error: DataQualityError, *, input_hash: str | None) -> DataQualityEvaluationRejected:
    payload: dict[str, Any] = {
        "kind": "data_quality_rejected",
        "schema_version": "1.0.0",
        "failure_stage": error.stage.value,
        "error_code": error.code.value,
        "message": str(error),
        "input_hash": input_hash,
        "rule_set_reference": None,
        "field_results": [],
        "row_results": [],
        "dataset_result": None,
    }
    payload["output_hash"] = compute_quality_output_hash(payload)
    payload["content_hash"] = compute_quality_content_hash(payload)
    return DataQualityEvaluationRejected(**payload)


def _fail(code: QualityErrorCode, stage: QualityFailureStage) -> None:
    raise DataQualityError(code, "C-05 quality validation failed", stage=stage)


__all__ = ["evaluate_data_quality"]
