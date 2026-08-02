"""Canonical identity projections for C-04 Dataset candidates.

This module operates on serialized contract payloads and does not import the
C-04 Pydantic models. Scientific identity therefore stays independent from
Schema construction and process-local publication admission.
"""

from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from ._hashing import compute_canonical_payload_hash


def _payload(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return deepcopy(value.model_dump(mode="json", exclude_none=True))
    return _drop_none(deepcopy(value))


def _drop_none(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _drop_none(item) for key, item in value.items() if item is not None}
    if isinstance(value, list):
        return [_drop_none(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_drop_none(item) for item in value)
    return value


def _decimal(value: Any) -> str | None:
    if value is None:
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"canonical numeric value is invalid: {value!r}") from exc
    if not number.is_finite():
        raise ValueError("canonical numeric value must be finite")
    if number == 0:
        return "0"
    normalized = format(number.normalize(), "f")
    return normalized.rstrip("0").rstrip(".") if "." in normalized else normalized


def _canonical_uncertainty(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": value.get("status"),
        "canonical_positive": _decimal(value.get("canonical_positive")),
        "canonical_negative": _decimal(value.get("canonical_negative")),
    }


def _canonical_source_value(value: Mapping[str, Any]) -> dict[str, Any]:
    """Project one retained candidate without raw provenance or generated IDs."""

    return {
        "canonical_field_id": value.get("canonical_field_id"),
        "source_id": value.get("source_id"),
        "canonical_value": value.get("canonical_value"),
        "canonical_unit": value.get("canonical_unit"),
        "source_priority": value.get("source_priority"),
        "alias_priority": value.get("alias_priority"),
        "uncertainty": _canonical_uncertainty(value.get("uncertainty", {})),
        "limit_status": value.get("limit", {}).get("status"),
        "null_status": value.get("null_status"),
    }


def _canonical_column(value: Mapping[str, Any]) -> dict[str, Any]:
    field = value.get("field", value)
    excluded = {"source_aliases", "evidence_locator_rule_id"}
    return {key: item for key, item in field.items() if key not in excluded}


def dataset_scientific_projection(value: Any) -> dict[str, Any]:
    """Return the complete C-04 scientific projection used for Dataset identity."""

    payload = _payload(value)
    source_values = {
        item["source_value_id"]: item for item in payload.get("source_values", ())
    }
    selections = {
        item["selection_id"]: item for item in payload.get("selections", ())
    }
    conflicts = {
        item["conflict_id"]: item for item in payload.get("conflicts", ())
    }

    rows: list[dict[str, Any]] = []
    for row in payload.get("rows", ()):
        outcomes: list[dict[str, Any]] = []
        for outcome in row.get("fields", ()):
            candidate_values = [
                _canonical_source_value(source_values[source_value_id])
                for source_value_id in outcome.get("candidate_source_value_ids", ())
            ]
            projected: dict[str, Any] = {
                "canonical_field_id": outcome.get("canonical_field_id"),
                "status": outcome.get("status"),
                "candidates": candidate_values,
            }
            if outcome.get("status") == "mapped":
                selected_id = outcome.get("selected_source_value_id")
                selection = selections.get(outcome.get("selection_id"), {})
                projected.update(
                    {
                        "canonical_value": outcome.get("canonical_value"),
                        "canonical_unit": outcome.get("canonical_unit"),
                        "selected_candidate": _canonical_source_value(
                            source_values[selected_id]
                        ),
                        "selection": {
                            "strategy": selection.get("strategy"),
                            "reason": selection.get("reason"),
                            "candidate_order": candidate_values,
                        },
                    }
                )
            else:
                projected["reason"] = outcome.get("reason")
            projected["conflicts"] = [
                {
                    "scope": conflicts[conflict_id].get("conflict_scope"),
                    "reason": conflicts[conflict_id].get("reason"),
                    "comparison_policy_version": conflicts[conflict_id].get(
                        "comparison_policy_version"
                    ),
                    "candidates": [
                        _canonical_source_value(source_values[source_value_id])
                        for source_value_id in conflicts[conflict_id].get(
                            "source_value_ids", ()
                        )
                    ],
                    "absolute_difference": _decimal(
                        conflicts[conflict_id].get("absolute_difference")
                    ),
                    "relative_denominator": _decimal(
                        conflicts[conflict_id].get("relative_denominator")
                    ),
                    "relative_difference": _decimal(
                        conflicts[conflict_id].get("relative_difference")
                    ),
                }
                for conflict_id in outcome.get("conflict_ids", ())
            ]
            outcomes.append(projected)
        rows.append(
            {
                "crossmatch_record_type": row.get("crossmatch_record_type"),
                "entity_level": row.get("entity_level"),
                "projection_policy_version": row.get("projection_policy_version"),
                "projected_field_ids": row.get("projected_field_ids"),
                "alignment_status": row.get("alignment_status"),
                "fields": outcomes,
            }
        )

    return {
        "schema_version": payload.get("schema_version"),
        "manifest_pins": payload.get("manifest_pins"),
        "mapping_rule_set": {
            "id": payload.get("mapping_rule_set_id"),
            "version": payload.get("mapping_rule_set_version"),
            "content_hash": payload.get("mapping_rule_set_content_hash"),
        },
        "conversion_catalog": {
            "id": payload.get("conversion_catalog_id"),
            "version": payload.get("conversion_catalog_version"),
            "content_hash": payload.get("conversion_catalog_content_hash"),
        },
        "requested_fields": payload.get("requested_fields"),
        "columns": [
            _canonical_column(column) for column in payload.get("columns", ())
        ],
        "quality_metric_input_declarations": payload.get(
            "quality_metric_input_declarations"
        ),
        "quality_constraints_reference": payload.get("quality_constraints_reference"),
        "rows": rows,
    }


def compute_dataset_canonical_content_hash(value: Any) -> str:
    return compute_canonical_payload_hash(dataset_scientific_projection(value))


def dataset_lineage_projection(value: Any) -> dict[str, Any]:
    """Return the complete raw/input/Evidence representation for lineage."""

    payload = _payload(value)
    for key in ("candidate_id", "canonical_content_hash", "lineage_hash", "output_hash"):
        payload.pop(key, None)
    return payload


def compute_dataset_lineage_hash(value: Any) -> str:
    return compute_canonical_payload_hash(dataset_lineage_projection(value))


def compute_dataset_candidate_id(
    kind: str, schema_version: str, canonical_content_hash: str
) -> str:
    digest = compute_canonical_payload_hash(
        {
            "kind": kind,
            "schema_version": schema_version,
            "canonical_content_hash": canonical_content_hash,
        }
    ).removeprefix("sha256:")
    return f"candidate.{kind}.{digest[:24]}"


__all__ = [
    "compute_dataset_candidate_id",
    "compute_dataset_canonical_content_hash",
    "compute_dataset_lineage_hash",
    "dataset_lineage_projection",
    "dataset_scientific_projection",
]
