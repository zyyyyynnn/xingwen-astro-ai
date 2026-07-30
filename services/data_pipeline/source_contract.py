"""Load the frozen source-column adjudication referenced by the Manifest."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from app.schemas.manifest import SourceDefinition


_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class SourceColumnRuntimeContract:
    snapshot_id: str
    snapshot_version: str
    content_hash: str
    declared_columns: tuple[str, ...]
    live_unavailable_columns: tuple[str, ...]


def load_source_column_runtime_contract(
    source: SourceDefinition,
) -> SourceColumnRuntimeContract:
    reference = source.column_contract
    path = (_REPOSITORY_ROOT / reference.path).resolve()
    if not path.is_relative_to(_REPOSITORY_ROOT):
        raise ValueError("source column contract path escapes the repository")
    payload_bytes = path.read_bytes()
    actual_hash = f"sha256:{sha256(payload_bytes).hexdigest()}"
    if actual_hash != reference.content_hash:
        raise ValueError("source column contract file hash does not match Manifest")
    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError("source column contract is not valid UTF-8 JSON") from None
    if not isinstance(payload, dict):
        raise ValueError("source column contract must be a JSON object")
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
    return SourceColumnRuntimeContract(
        snapshot_id=reference.snapshot_id,
        snapshot_version=reference.snapshot_version,
        content_hash=reference.content_hash,
        declared_columns=source.approved_columns,
        live_unavailable_columns=tuple(
            column for column in source.approved_columns if column in unavailable
        ),
    )


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
