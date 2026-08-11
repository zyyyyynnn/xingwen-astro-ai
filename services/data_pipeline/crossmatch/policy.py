"""Load and cross-check the pinned entity-alignment RuleSet and alias catalog."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.crossmatch import (
    CrossmatchRuleSet,
    CrossmatchSourcePolicy,
    EntityAliasCatalog,
)

from ..constants import (
    CROSSMATCH_PRODUCER_NAME,
    CROSSMATCH_PRODUCER_VERSION,
    FROZEN_CASE_MANIFEST_CONTENT_HASH,
    FROZEN_CASE_MANIFEST_VERSION,
    FROZEN_FIELD_MANIFEST_CONTENT_HASH,
    FROZEN_FIELD_MANIFEST_VERSION,
    SOURCE_POLICY_CONTENT_HASH,
    SOURCE_POLICY_VERSION,
)


_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_RULE_ROOT = (
    _REPOSITORY_ROOT
    / "services"
    / "data_pipeline"
    / "manifests"
    / "exoplanet_host_star"
    / "crossmatch-rules"
)
DEFAULT_SOURCE_POLICY_PATH = _RULE_ROOT / "source-policy.json"
DEFAULT_ALIAS_CATALOG_PATH = _RULE_ROOT / "entity-alias-catalog.json"
DEFAULT_CROSSMATCH_RULE_SET_PATH = _RULE_ROOT / "crossmatch-rules.json"


def load_entity_alias_catalog(
    path: Path = DEFAULT_ALIAS_CATALOG_PATH,
) -> EntityAliasCatalog:
    return EntityAliasCatalog.model_validate(_load_versioned_payload(path))


def load_crossmatch_source_policy(
    path: Path = DEFAULT_SOURCE_POLICY_PATH,
) -> CrossmatchSourcePolicy:
    return CrossmatchSourcePolicy.model_validate(_load_versioned_payload(path))


def load_crossmatch_rule_set(
    path: Path = DEFAULT_CROSSMATCH_RULE_SET_PATH,
    *,
    alias_catalog_path: Path = DEFAULT_ALIAS_CATALOG_PATH,
    source_policy_path: Path = DEFAULT_SOURCE_POLICY_PATH,
) -> CrossmatchRuleSet:
    alias_catalog = load_entity_alias_catalog(alias_catalog_path)
    source_policy = load_crossmatch_source_policy(source_policy_path)
    if (
        source_policy.version != SOURCE_POLICY_VERSION
        or source_policy.content_hash != SOURCE_POLICY_CONTENT_HASH
    ):
        raise ValueError(
            "source policy identity does not match frozen acquisition policy"
        )

    rule_set = CrossmatchRuleSet.model_validate(_load_versioned_payload(path))
    expected_pins = {
        "case_manifest_version": FROZEN_CASE_MANIFEST_VERSION,
        "case_manifest_content_hash": FROZEN_CASE_MANIFEST_CONTENT_HASH,
        "field_manifest_version": FROZEN_FIELD_MANIFEST_VERSION,
        "field_manifest_content_hash": FROZEN_FIELD_MANIFEST_CONTENT_HASH,
        "source_policy_version": SOURCE_POLICY_VERSION,
        "source_policy_content_hash": SOURCE_POLICY_CONTENT_HASH,
        "entity_alias_catalog_version": alias_catalog.version,
        "entity_alias_catalog_content_hash": alias_catalog.content_hash,
        "producer_name": CROSSMATCH_PRODUCER_NAME,
        "producer_version": CROSSMATCH_PRODUCER_VERSION,
    }
    actual_pins = {
        key: getattr(rule_set, key)
        for key in expected_pins
    }
    if actual_pins != expected_pins:
        raise ValueError("crossmatch RuleSet disagrees with frozen inputs")
    return rule_set


def _load_versioned_payload(path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    if not resolved.is_relative_to(_REPOSITORY_ROOT):
        raise ValueError("crossmatch policy path escapes the repository")
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError("crossmatch policy is not valid UTF-8 JSON") from None
    if not isinstance(payload, dict):
        raise ValueError("crossmatch policy must be a JSON object")
    declared_hash = payload.get("content_hash")
    canonical_payload = dict(payload)
    canonical_payload.pop("content_hash", None)
    actual_hash = compute_canonical_payload_hash(canonical_payload)
    if declared_hash != actual_hash:
        raise ValueError(f"crossmatch policy content_hash mismatch: {actual_hash}")
    return payload
