"""Shared single-source projection and admission before Artifact assembly."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.core import ResearchContract, validate_research_contract_content_hash
from app.schemas.data_artifacts import ManifestPins, DatabaseCellLocator
from app.schemas.data_quality import QualityMetricScope
from app.schemas.manifest import FieldDefinition, SourceAlias
from app.schemas.source_acquisition import compute_raw_data_record_hash
from app.schemas.source_table import (
    SourceTableAdmission,
    SourceTableCellAdmission,
    compute_source_table_input_hash,
    compute_source_table_output_hash,
)
from services.data_pipeline.crossmatch.identity import (
    normalize_gaia_dr3_id,
    normalize_sky_coordinate,
)
from services.data_pipeline.data_artifacts.policy import (
    load_mapping_rule_set,
    load_unit_conversion_catalog,
)
from services.data_pipeline.data_artifacts.projection import canonicalize_source_value
from services.data_pipeline.data_quality.contract_gate import (
    aggregate_gate_status,
    evaluate_metric_constraint,
)
from services.data_pipeline.data_quality.formulas import execute_metric
from services.data_pipeline.data_quality.policy import (
    load_frozen_quality_evaluation_plan,
    load_frozen_quality_rule_set,
)
from services.data_pipeline.manifest import load_frozen_manifest_bundle


GAIA_SOURCE_ID = "esa_gaia_dr3.gaiadr3.gaia_source"


@dataclass(frozen=True, slots=True)
class SourceFieldContract:
    raw_field: str
    canonical_field_id: str
    label_zh: str
    source_unit: str
    canonical_unit: str
    value_kind: Literal["identifier", "number"]
    schema_datatypes: frozenset[str]
    schema_unit: str | None


def gaia_source_contract() -> tuple[SourceFieldContract, ...]:
    """Derive the Gaia TAP allowlist from the frozen Field Manifest."""

    bundle = load_frozen_manifest_bundle()
    source = next(
        item
        for item in bundle.field_manifest.sources
        if item.source_id == GAIA_SOURCE_ID
    )
    units = {unit.unit_id: unit for unit in bundle.field_manifest.units}
    aliases: dict[str, tuple[FieldDefinition, SourceAlias]] = {}
    for field in bundle.field_manifest.fields:
        for alias in field.source_aliases_for(source.source_id):
            if alias.raw_field in aliases:
                raise ValueError("Gaia source column maps to multiple canonical fields")
            aliases[alias.raw_field] = (field, alias)
    if set(aliases) != set(source.approved_columns):
        raise ValueError("Gaia Manifest aliases do not close approved columns")
    return tuple(
        SourceFieldContract(
            raw_field=raw_field,
            canonical_field_id=aliases[raw_field][0].field_id,
            label_zh=aliases[raw_field][0].meaning_zh,
            source_unit=aliases[raw_field][1].source_unit,
            canonical_unit=aliases[raw_field][0].canonical_unit,
            value_kind=(
                "identifier" if raw_field in source.row_key_fields else "number"
            ),
            schema_datatypes=(
                frozenset({"long", "bigint"})
                if raw_field in source.row_key_fields
                else frozenset({"double", "float", "real"})
            ),
            schema_unit=(units[aliases[raw_field][1].source_unit].symbol or None),
        )
        for raw_field in source.approved_columns
    )


def admit_source_table(
    *,
    source_id: str,
    fields: Sequence[str],
    rows: Sequence[Mapping[str, object]],
    result_status: Literal["complete", "empty", "truncated"],
    source_snapshot_id: str,
    source_snapshot_content_hash: str,
    query_hash: str,
    retrieved_at: datetime,
    evidence_scope_id: str,
    contract: ResearchContract,
) -> SourceTableAdmission:
    """Map and gate one source table through existing immutable policies."""

    validate_research_contract_content_hash(contract)
    bundle = load_frozen_manifest_bundle()
    source = next(
        (item for item in bundle.field_manifest.sources if item.source_id == source_id),
        None,
    )
    if source is None:
        raise ValueError("source table is outside the frozen Field Manifest")
    units = {unit.unit_id: unit for unit in bundle.field_manifest.units}
    allowed_tables = set(
        bundle.resolve_source_scope(contract.source_scope.allowed_sources)
    )
    if source_id not in allowed_tables:
        raise ValueError("source table is outside the ResearchContract source scope")
    selected_fields = tuple(fields)
    if (
        not selected_fields
        or selected_fields[0] != source.row_key_fields[0]
        or len(selected_fields) != len(set(selected_fields))
        or not set(selected_fields) <= set(source.approved_columns)
    ):
        raise ValueError("source-table fields are not an ordered approved projection")
    if (result_status == "empty") != (not rows):
        raise ValueError("source-table result status disagrees with its rows")

    field_registry: dict[str, tuple[FieldDefinition, SourceAlias]] = {}
    for field in bundle.field_manifest.fields:
        for alias in field.source_aliases_for(source_id):
            field_registry[alias.raw_field] = (field, alias)
    if any(raw_field not in field_registry for raw_field in selected_fields):
        raise ValueError("source-table field has no canonical Manifest alias")

    mapping_rules = load_mapping_rule_set()
    conversion_catalog = load_unit_conversion_catalog()
    quality_rules = load_frozen_quality_rule_set()
    plan = load_frozen_quality_evaluation_plan()
    expected_manifest_identity = (
        bundle.case_manifest.case_id,
        bundle.case_manifest.manifest_version,
        bundle.case_manifest.content_hash,
        bundle.field_manifest.manifest_id,
        bundle.field_manifest.manifest_version,
        bundle.field_manifest.content_hash,
    )
    if (
        mapping_rules.case_manifest_id,
        mapping_rules.case_manifest_version,
        mapping_rules.case_manifest_content_hash,
        mapping_rules.field_manifest_id,
        mapping_rules.field_manifest_version,
        mapping_rules.field_manifest_content_hash,
    ) != expected_manifest_identity:
        raise ValueError("MappingRuleSet is not pinned to the frozen manifests")
    if (
        conversion_catalog.field_manifest_id,
        conversion_catalog.field_manifest_version,
        conversion_catalog.field_manifest_content_hash,
    ) != expected_manifest_identity[3:]:
        raise ValueError("ConversionCatalog is not pinned to the frozen Field Manifest")
    if (
        quality_rules.case_manifest_id,
        quality_rules.case_manifest_version,
        quality_rules.case_manifest_content_hash,
        quality_rules.field_manifest_id,
        quality_rules.field_manifest_version,
        quality_rules.field_manifest_content_hash,
    ) != expected_manifest_identity:
        raise ValueError("Quality RuleSet is not pinned to the frozen manifests")

    conversion_versions = {
        rule.rule_id: rule.rule_version
        for rule in bundle.field_manifest.conversion_rules
    }
    columns = [
        {
            "raw_field": raw_field,
            "canonical_field_id": field_registry[raw_field][0].field_id,
            "label_zh": field_registry[raw_field][0].meaning_zh,
            "source_unit": field_registry[raw_field][1].source_unit,
            "canonical_unit": field_registry[raw_field][0].canonical_unit,
            "source_unit_symbol": units[field_registry[raw_field][1].source_unit].symbol
            or None,
            "canonical_unit_symbol": units[
                field_registry[raw_field][0].canonical_unit
            ].symbol
            or None,
        }
        for raw_field in selected_fields
    ]
    admitted_rows: list[dict[str, object]] = []
    cells: list[dict[str, object]] = []
    identities: set[str] = set()
    for raw_row in rows:
        if set(raw_row) != set(selected_fields):
            raise ValueError("source-table row disagrees with the selected fields")
        raw_payload = {field: raw_row[field] for field in selected_fields}
        identity = normalize_gaia_dr3_id(raw_payload[source.row_key_fields[0]])
        if identity in identities:
            raise ValueError("source-table contains duplicate source identities")
        identities.add(identity)
        if "ra" in selected_fields or "dec" in selected_fields:
            if "ra" not in selected_fields or "dec" not in selected_fields:
                raise ValueError(
                    "source-table ICRS coordinates must be selected as a pair"
                )
            coordinate = normalize_sky_coordinate(raw_payload["ra"], raw_payload["dec"])
        else:
            coordinate = None
        raw_identity = str(raw_payload[source.row_key_fields[0]]).strip()
        row_key = ((source.row_key_fields[0], raw_identity),)
        record_hash = compute_raw_data_record_hash(
            source_id=source_id,
            row_key=row_key,
            payload=raw_payload,
        )
        row_id = (
            "source_row."
            + compute_canonical_payload_hash(
                {"source_id": source_id, "identity": identity}
            ).removeprefix("sha256:")[:24]
        )
        row_values: dict[str, str | None] = {}
        row_evidence_ids: list[str] = []
        for raw_field in selected_fields:
            field, alias = field_registry[raw_field]
            raw_value = raw_payload[raw_field]
            canonical_value: str | None
            if raw_value is None:
                if raw_field == source.row_key_fields[0] or not field.nullable:
                    raise ValueError("source-table non-nullable field is null")
                canonical_value = None
            elif raw_field == source.row_key_fields[0]:
                canonical_value = identity
            else:
                normalized_raw = raw_value
                if raw_field == "ra" and coordinate is not None:
                    normalized_raw = coordinate.right_ascension
                elif raw_field == "dec" and coordinate is not None:
                    normalized_raw = coordinate.declination
                canonical_value = canonicalize_source_value(
                    normalized_raw,
                    field,
                    alias,
                    conversion_catalog,
                    bundle,
                    conversion_versions,
                )
            locator = DatabaseCellLocator(
                source_role="single",
                source_snapshot_id=source_snapshot_id,
                source_snapshot_content_hash=source_snapshot_content_hash,
                source_id=source_id,
                query_hash=query_hash,
                row_key=row_key,
                raw_record_content_hash=record_hash,
                raw_field=raw_field,
            )
            evidence_id = str(
                uuid5(
                    NAMESPACE_URL,
                    f"xingwen:source-cell:{evidence_scope_id}:"
                    + compute_canonical_payload_hash(
                        {
                            "canonical_field_id": field.field_id,
                            "locator": locator.model_dump(mode="json"),
                        }
                    ),
                )
            )
            row_values[field.field_id] = canonical_value
            row_evidence_ids.append(evidence_id)
            cells.append(
                {
                    "row_id": row_id,
                    "canonical_field_id": field.field_id,
                    "raw_value": raw_value,
                    "canonical_value": canonical_value,
                    "canonical_unit": field.canonical_unit,
                    "evidence_id": evidence_id,
                    "locator": locator.model_dump(mode="json"),
                }
            )
        admitted_rows.append(
            {
                "row_id": row_id,
                "canonical_identity": identity,
                "values": row_values,
                "evidence_ids": row_evidence_ids,
            }
        )

    incomplete_source = result_status != "complete"
    unit_applicable = sum(
        cell["canonical_value"] is not None and cell["canonical_unit"] != "none"
        for cell in cells
    )
    metric_inputs = (
        (
            "source_scope_completeness",
            {
                "dataset.complete_source_count": int(
                    result_status == "complete" and bool(admitted_rows)
                ),
                "dataset.required_source_count": 1,
            },
        ),
        (
            "dataset_unit_consistency",
            {
                "dataset.unit_consistent_assertion_count": unit_applicable,
                "dataset.unit_applicable_assertion_count": unit_applicable,
            },
        ),
        (
            "dataset_evidence_coverage",
            {
                "dataset.evidence_count": len(cells),
                "dataset.evidence_applicable_count": len(cells),
            },
        ),
    )
    metrics = tuple(
        execute_metric(
            plan,
            metric_id=metric_id,
            scope=QualityMetricScope.dataset,
            target_id=f"source_table:{source_snapshot_id}",
            observations=observations,
            incomplete_source=incomplete_source,
            input_locator="source_table.cells",
        )
        for metric_id, observations in metric_inputs
    )
    checks = []
    for metric in metrics:
        binding = next(
            item for item in plan.gate_bindings if item.metric_id is metric.metric_id
        )
        checks.append(
            evaluate_metric_constraint(
                contract,
                constraint_id=binding.constraint_id,
                contract_path=binding.contract_path,
                observation_key=binding.observation_key,
                metric=metric,
                operator=binding.operator,
                rule_binding_version=binding.rule_binding_version,
                input_locator=binding.input_locator,
                not_applicable_result=binding.not_applicable_result,
            )
        )

    payload: dict[str, object] = {
        "kind": "source_table_admission",
        "schema_version": "1.0.0",
        "admission_id": "source_table.pending",
        "source_id": source_id,
        "source_table": source.source_table,
        "source_result_status": result_status,
        "source_snapshot_id": source_snapshot_id,
        "source_snapshot_content_hash": source_snapshot_content_hash,
        "query_hash": query_hash,
        "retrieved_at": retrieved_at.isoformat().replace("+00:00", "Z"),
        "evidence_scope_id": evidence_scope_id,
        "manifest_pins": ManifestPins(
            case_manifest_id=bundle.case_manifest.case_id,
            case_manifest_version=bundle.case_manifest.manifest_version,
            case_manifest_content_hash=bundle.case_manifest.content_hash,
            field_manifest_id=bundle.field_manifest.manifest_id,
            field_manifest_version=bundle.field_manifest.manifest_version,
            field_manifest_content_hash=bundle.field_manifest.content_hash,
        ).model_dump(mode="json"),
        "mapping_rule_set_id": mapping_rules.rule_set_id,
        "mapping_rule_set_version": mapping_rules.version,
        "mapping_rule_set_content_hash": mapping_rules.content_hash,
        "conversion_catalog_id": conversion_catalog.catalog_id,
        "conversion_catalog_version": conversion_catalog.version,
        "conversion_catalog_content_hash": conversion_catalog.content_hash,
        "quality_rule_set_id": quality_rules.rule_set_id,
        "quality_rule_set_version": quality_rules.version,
        "quality_rule_set_content_hash": quality_rules.content_hash,
        "research_contract_id": contract.id,
        "research_contract_version": contract.version,
        "research_contract_content_hash": contract.content_hash,
        "columns": columns,
        "rows": admitted_rows,
        "cells": cells,
        "metrics": [metric.model_dump(mode="json") for metric in metrics],
        "checks": [check.model_dump(mode="json") for check in checks],
        "overall_status": aggregate_gate_status(tuple(checks)),
        "input_hash": "sha256:" + "0" * 64,
        "output_hash": "sha256:" + "0" * 64,
    }
    payload["input_hash"] = compute_source_table_input_hash(payload)
    payload["output_hash"] = compute_source_table_output_hash(payload)
    payload["admission_id"] = (
        "source_table." + str(payload["output_hash"]).removeprefix("sha256:")[:24]
    )
    return SourceTableAdmission.model_validate(payload)


def replay_source_table_admission(
    admission: SourceTableAdmission,
    *,
    contract: ResearchContract,
) -> SourceTableAdmission:
    """Rebuild an attestation from raw cells using the current frozen policies."""

    fields = tuple(column.raw_field for column in admission.columns)
    row_ids = tuple(row.row_id for row in admission.rows)
    if len(row_ids) != len(set(row_ids)):
        raise ValueError("source-table admission contains duplicate row ids")
    cells_by_row: dict[str, list[SourceTableCellAdmission]] = {
        row_id: [] for row_id in row_ids
    }
    for cell in admission.cells:
        if cell.row_id not in cells_by_row:
            raise ValueError("source-table cell references an undeclared row")
        cells_by_row[cell.row_id].append(cell)

    raw_rows: list[dict[str, object]] = []
    for row_id in row_ids:
        row_cells = cells_by_row[row_id]
        raw_values = {cell.locator.raw_field: cell.raw_value for cell in row_cells}
        if len(row_cells) != len(fields) or set(raw_values) != set(fields):
            raise ValueError("source-table row cells do not close the admitted columns")
        raw_rows.append({field: raw_values[field] for field in fields})

    replayed = admit_source_table(
        source_id=admission.source_id,
        fields=fields,
        rows=raw_rows,
        result_status=admission.source_result_status,
        source_snapshot_id=admission.source_snapshot_id,
        source_snapshot_content_hash=admission.source_snapshot_content_hash,
        query_hash=admission.query_hash,
        retrieved_at=admission.retrieved_at,
        evidence_scope_id=admission.evidence_scope_id,
        contract=contract,
    )
    if replayed.model_dump(mode="json") != admission.model_dump(mode="json"):
        raise ValueError("source-table admission drifted from current frozen policies")
    return replayed


__all__ = [
    "GAIA_SOURCE_ID",
    "SourceFieldContract",
    "admit_source_table",
    "gaia_source_contract",
    "replay_source_table_admission",
]
