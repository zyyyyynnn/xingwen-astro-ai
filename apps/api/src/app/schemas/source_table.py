"""Typed admission attestation for one independently acquired source table."""

from __future__ import annotations

from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ._hashing import compute_canonical_payload_hash
from .core import ContentHash, Identifier, JsonValue, SemanticVersion, UtcDateTime
from .data_artifact_primitives import DatabaseCellLocator, ManifestPins
from .data_quality_primitives import (
    QualityConstraintResult,
    QualityGateStatus,
    QualityMetricResult,
)


MODEL_CONFIG = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
NonEmptyString = Annotated[str, Field(min_length=1)]


class SourceTableColumnAdmission(BaseModel):
    model_config = MODEL_CONFIG

    raw_field: NonEmptyString
    canonical_field_id: Identifier
    label_zh: NonEmptyString
    source_unit: Identifier
    canonical_unit: Identifier
    conversion_rule_id: Identifier
    conversion_rule_version: SemanticVersion
    source_unit_symbol: str | None = None
    canonical_unit_symbol: str | None = None


class SourceTableCellAdmission(BaseModel):
    model_config = MODEL_CONFIG

    row_id: Identifier
    canonical_field_id: Identifier
    raw_value: JsonValue | None
    canonical_value: str | None
    canonical_unit: Identifier
    evidence_id: Identifier
    locator: DatabaseCellLocator


class SourceTableRowAdmission(BaseModel):
    model_config = MODEL_CONFIG

    row_id: Identifier
    canonical_identity: NonEmptyString
    values: dict[Identifier, str | None]
    evidence_ids: tuple[Identifier, ...]


class SourceTableAdmission(BaseModel):
    """Hash-closed mapping, quality and Evidence result for one source table."""

    model_config = MODEL_CONFIG

    kind: Literal["source_table_admission"] = "source_table_admission"
    schema_version: Literal["2.0.0"] = "2.0.0"
    admission_id: Identifier
    source_id: Identifier
    source_table: NonEmptyString
    source_result_status: Literal["complete", "empty", "truncated"]
    source_snapshot_id: Identifier
    source_snapshot_content_hash: ContentHash
    query_hash: ContentHash
    retrieved_at: UtcDateTime
    evidence_scope_id: Identifier
    manifest_pins: ManifestPins
    mapping_rule_set_id: Identifier
    mapping_rule_set_version: NonEmptyString
    mapping_rule_set_content_hash: ContentHash
    conversion_catalog_id: Identifier
    conversion_catalog_version: NonEmptyString
    conversion_catalog_content_hash: ContentHash
    quality_rule_set_id: Identifier
    quality_rule_set_version: NonEmptyString
    quality_rule_set_content_hash: ContentHash
    research_contract_id: Identifier
    research_contract_version: int = Field(ge=1)
    research_contract_content_hash: ContentHash
    columns: tuple[SourceTableColumnAdmission, ...] = Field(min_length=1)
    rows: tuple[SourceTableRowAdmission, ...] = ()
    cells: tuple[SourceTableCellAdmission, ...] = ()
    metrics: tuple[QualityMetricResult, ...] = Field(min_length=3, max_length=3)
    checks: tuple[QualityConstraintResult, ...] = Field(min_length=3, max_length=3)
    overall_status: QualityGateStatus
    input_hash: ContentHash
    output_hash: ContentHash

    @model_validator(mode="after")
    def validate_closure(self) -> Self:
        raw_fields = tuple(column.raw_field for column in self.columns)
        canonical_fields = tuple(column.canonical_field_id for column in self.columns)
        if len(raw_fields) != len(set(raw_fields)) or len(canonical_fields) != len(
            set(canonical_fields)
        ):
            raise ValueError("source-table columns must be unique")
        row_ids = tuple(row.row_id for row in self.rows)
        if len(row_ids) != len(set(row_ids)):
            raise ValueError("source-table rows must be unique")
        cell_registry = {
            (cell.row_id, cell.canonical_field_id): cell for cell in self.cells
        }
        if len(cell_registry) != len(self.cells) or set(cell_registry) != {
            (row_id, field_id) for row_id in row_ids for field_id in canonical_fields
        }:
            raise ValueError("source-table cells do not close rows and columns")
        for row in self.rows:
            if set(row.values) != set(canonical_fields):
                raise ValueError("source-table row values must close the columns")
            row_cells = tuple(
                cell_registry[(row.row_id, field_id)] for field_id in canonical_fields
            )
            if tuple(cell.canonical_value for cell in row_cells) != tuple(
                row.values[field_id] for field_id in canonical_fields
            ):
                raise ValueError("source-table row values disagree with cells")
            if row.evidence_ids != tuple(cell.evidence_id for cell in row_cells):
                raise ValueError("source-table row Evidence does not close its cells")
        if len({cell.evidence_id for cell in self.cells}) != len(self.cells):
            raise ValueError("source-table cell Evidence identities must be unique")
        for cell in self.cells:
            locator = cell.locator
            if (
                locator.source_role != "single"
                or locator.source_snapshot_id != self.source_snapshot_id
                or locator.source_snapshot_content_hash
                != self.source_snapshot_content_hash
                or locator.source_id != self.source_id
                or locator.query_hash != self.query_hash
            ):
                raise ValueError("source-table locator disagrees with its snapshot")
        expected_metrics = {
            "source_scope_completeness",
            "dataset_unit_consistency",
            "dataset_evidence_coverage",
        }
        if {metric.metric_id.value for metric in self.metrics} != expected_metrics:
            raise ValueError("source-table quality metric set is incomplete")
        if {
            check.metric_id.value for check in self.checks if check.metric_id
        } != expected_metrics:
            raise ValueError("source-table Contract checks do not bind every metric")
        expected_status = (
            QualityGateStatus.fail
            if any(check.result is QualityGateStatus.fail for check in self.checks)
            else QualityGateStatus.insufficient
            if any(
                check.result is QualityGateStatus.insufficient for check in self.checks
            )
            else QualityGateStatus.pass_
        )
        if self.overall_status is not expected_status:
            raise ValueError("source-table quality status does not close its checks")
        expected_input = compute_source_table_input_hash(self)
        if self.input_hash != expected_input:
            raise ValueError(f"source-table input_hash mismatch: {expected_input}")
        expected_output = compute_source_table_output_hash(self)
        if self.output_hash != expected_output:
            raise ValueError(f"source-table output_hash mismatch: {expected_output}")
        expected_id = f"source_table.{expected_output.removeprefix('sha256:')[:24]}"
        if self.admission_id != expected_id:
            raise ValueError("source-table admission_id is not output-bound")
        return self


def compute_source_table_input_hash(
    value: SourceTableAdmission | dict[str, Any],
) -> str:
    payload = (
        value.model_dump(mode="json")
        if isinstance(value, SourceTableAdmission)
        else dict(value)
    )
    return compute_canonical_payload_hash(
        {
            "source_id": payload["source_id"],
            "source_table": payload["source_table"],
            "source_result_status": payload["source_result_status"],
            "source_snapshot_id": payload["source_snapshot_id"],
            "source_snapshot_content_hash": payload["source_snapshot_content_hash"],
            "query_hash": payload["query_hash"],
            "retrieved_at": payload["retrieved_at"],
            "evidence_scope_id": payload["evidence_scope_id"],
            "manifest_pins": payload["manifest_pins"],
            "mapping_rule_set_content_hash": payload["mapping_rule_set_content_hash"],
            "conversion_catalog_content_hash": payload[
                "conversion_catalog_content_hash"
            ],
            "quality_rule_set_content_hash": payload["quality_rule_set_content_hash"],
            "research_contract_id": payload["research_contract_id"],
            "research_contract_version": payload["research_contract_version"],
            "research_contract_content_hash": payload["research_contract_content_hash"],
            "columns": payload["columns"],
            "raw_cells": [
                {
                    "row_id": cell["row_id"],
                    "canonical_field_id": cell["canonical_field_id"],
                    "raw_value": cell["raw_value"],
                    "locator": cell["locator"],
                }
                for cell in payload["cells"]
            ],
        }
    )


def compute_source_table_output_hash(
    value: SourceTableAdmission | dict[str, Any],
) -> str:
    payload = (
        value.model_dump(mode="json")
        if isinstance(value, SourceTableAdmission)
        else dict(value)
    )
    payload.pop("admission_id", None)
    payload.pop("output_hash", None)
    return compute_canonical_payload_hash(payload)

__all__ = [
    "SourceTableAdmission",
    "SourceTableCellAdmission",
    "SourceTableColumnAdmission",
    "SourceTableRowAdmission",
    "compute_source_table_input_hash",
    "compute_source_table_output_hash",
]
