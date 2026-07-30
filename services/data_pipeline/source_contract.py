"""Load versioned source-column contracts used by acquisition adapters."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from app.schemas.manifest import SourceDefinition


_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_PS_RUNTIME_SCHEMA_CONTRACT_PATH = (
    _REPOSITORY_ROOT
    / "services"
    / "data_pipeline"
    / "manifests"
    / "exoplanet_host_star"
    / "source-evidence"
    / "nasa-exoplanet-archive"
    / "2026-07-30"
    / "ps-runtime-schema-contract.v1.json"
)
_ALLOWED_DATATYPE_CATEGORIES = frozenset({"string", "integer", "number"})


@dataclass(frozen=True)
class SourceColumnRuntimeContract:
    snapshot_id: str
    snapshot_version: str
    content_hash: str
    declared_columns: tuple[str, ...]
    live_unavailable_columns: tuple[str, ...]
    runtime_schema_contract_id: str
    runtime_schema_contract_version: str
    runtime_schema_contract_content_hash: str
    selected_column_categories: tuple[tuple[str, str], ...]

    def expected_category(self, column_name: str) -> str:
        try:
            return dict(self.selected_column_categories)[column_name]
        except KeyError:
            raise ValueError(
                f"runtime schema contract does not define selected column: {column_name}"
            ) from None


def load_source_column_runtime_contract(
    source: SourceDefinition,
) -> SourceColumnRuntimeContract:
    reference = source.column_contract
    payload, actual_hash = _load_json_contract(
        (_REPOSITORY_ROOT / reference.path).resolve(),
        "source column contract",
    )
    if actual_hash != reference.content_hash:
        raise ValueError("source column contract file hash does not match Manifest")
    if (
        payload.get("snapshot_id") != reference.snapshot_id
        or payload.get("snapshot_version") != reference.snapshot_version
    ):
        raise ValueError("source column contract identity does not match Manifest")

    table_contract = _table_contract(payload, source.source_id)
    expected_table_contract = {
        "source_id": source.source_id,
        "source_table": source.source_table,
        "approved_columns": list(source.approved_columns),
        "row_key_fields": list(source.row_key_fields),
        "reference_columns": list(source.reference_columns),
        "provenance_columns": list(source.provenance_columns),
    }
    if table_contract != expected_table_contract:
        raise ValueError("source column contract disagrees with Field Manifest")

    unavailable = {
        decision["column_name"]
        for decision in _critical_decisions(payload)
        if decision.get("source_table") == source.source_table
        and str(decision.get("live_tap_schema", "")).startswith("absent_")
        and decision.get("decision") == "retain"
    }
    if not unavailable.issubset(source.approved_columns):
        raise ValueError("source adjudication marks an undeclared column unavailable")
    live_unavailable_columns = tuple(
        column for column in source.approved_columns if column in unavailable
    )
    selected_columns = tuple(
        column for column in source.approved_columns if column not in unavailable
    )

    runtime_payload, runtime_hash = _load_json_contract(
        _runtime_schema_contract_path(source),
        "runtime schema contract",
    )
    runtime_contract_id = runtime_payload.get("schema_id")
    runtime_contract_version = runtime_payload.get("schema_version")
    if not isinstance(runtime_contract_id, str) or not runtime_contract_id:
        raise ValueError("runtime schema contract has invalid schema_id")
    if not isinstance(runtime_contract_version, str) or not runtime_contract_version:
        raise ValueError("runtime schema contract has invalid schema_version")
    if (
        runtime_payload.get("source_id") != source.source_id
        or runtime_payload.get("source_table") != source.source_table
    ):
        raise ValueError("runtime schema contract identity does not match source")
    raw_categories = runtime_payload.get("datatype_categories")
    if not isinstance(raw_categories, dict) or any(
        not isinstance(column, str)
        or not isinstance(category, str)
        or category not in _ALLOWED_DATATYPE_CATEGORIES
        for column, category in raw_categories.items()
    ):
        raise ValueError("runtime schema contract has invalid datatype categories")
    if set(raw_categories) != set(selected_columns):
        raise ValueError("runtime schema contract columns do not match live query")

    return SourceColumnRuntimeContract(
        snapshot_id=reference.snapshot_id,
        snapshot_version=reference.snapshot_version,
        content_hash=reference.content_hash,
        declared_columns=source.approved_columns,
        live_unavailable_columns=live_unavailable_columns,
        runtime_schema_contract_id=runtime_contract_id,
        runtime_schema_contract_version=runtime_contract_version,
        runtime_schema_contract_content_hash=runtime_hash,
        selected_column_categories=tuple(
            (column, raw_categories[column]) for column in selected_columns
        ),
    )


def _runtime_schema_contract_path(source: SourceDefinition) -> Path:
    if source.source_id != "nasa_exoplanet_archive.ps":
        raise ValueError(
            f"no runtime schema contract is registered for source: {source.source_id}"
        )
    return _PS_RUNTIME_SCHEMA_CONTRACT_PATH


def _load_json_contract(path: Path, label: str) -> tuple[dict[str, Any], str]:
    resolved = path.resolve()
    if not resolved.is_relative_to(_REPOSITORY_ROOT):
        raise ValueError(f"{label} path escapes the repository")
    payload_bytes = resolved.read_bytes()
    actual_hash = f"sha256:{sha256(payload_bytes).hexdigest()}"
    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError(f"{label} is not valid UTF-8 JSON") from None
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return payload, actual_hash


def _table_contract(payload: dict[str, Any], source_id: str) -> dict[str, Any]:
    contracts = payload.get("table_contracts")
    if not isinstance(contracts, list):
        raise ValueError("source column contract is missing table_contracts")
    matches = [
        contract
        for contract in contracts
        if isinstance(contract, dict) and contract.get("source_id") == source_id
    ]
    if len(matches) != 1:
        raise ValueError("source column contract must define the source exactly once")
    return matches[0]


def _critical_decisions(payload: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    decisions = payload.get("critical_column_decisions")
    if not isinstance(decisions, list) or any(
        not isinstance(decision, dict) for decision in decisions
    ):
        raise ValueError("source column contract has invalid critical decisions")
    return tuple(decisions)
