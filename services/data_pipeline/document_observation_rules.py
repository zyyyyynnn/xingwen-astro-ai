"""Load and authenticate the frozen Document Observation RuleSet."""

from __future__ import annotations

from pathlib import Path

from app.schemas.document_observation_rules import (
    DocumentObservationRuleSet,
    compute_document_observation_configuration_hash,
)
from app.schemas.manifest import ManifestBundle

from .constants import (
    FROZEN_CASE_MANIFEST_CONTENT_HASH,
    FROZEN_CASE_MANIFEST_VERSION,
    FROZEN_FIELD_MANIFEST_CONTENT_HASH,
    FROZEN_FIELD_MANIFEST_VERSION,
)


DEFAULT_RULE_SET_PATH = (
    Path(__file__).resolve().parent
    / "manifests"
    / "exoplanet_host_star"
    / "document-observation-rules"
    / "document-observation-rules.json"
)


def load_document_observation_rule_set(
    path: Path = DEFAULT_RULE_SET_PATH,
) -> DocumentObservationRuleSet:
    """Parse one versioned RuleSet; model validation includes its self-hash."""

    return DocumentObservationRuleSet.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def require_frozen_document_observation_rule_set(
    candidate: DocumentObservationRuleSet,
) -> DocumentObservationRuleSet:
    """Reject caller rules even when a caller recomputed a modified self-hash."""

    frozen = load_document_observation_rule_set()
    if candidate != frozen:
        raise ValueError(
            "caller document observation RuleSet is not the frozen repository RuleSet"
        )
    return frozen


def verify_rule_set_pins(
    rules: DocumentObservationRuleSet, *, manifests: ManifestBundle
) -> None:
    """Bind the RuleSet to the frozen Case/Field Manifest pair."""

    expected_pins = {
        "case_manifest_version": FROZEN_CASE_MANIFEST_VERSION,
        "case_manifest_content_hash": FROZEN_CASE_MANIFEST_CONTENT_HASH,
        "field_manifest_version": FROZEN_FIELD_MANIFEST_VERSION,
        "field_manifest_content_hash": FROZEN_FIELD_MANIFEST_CONTENT_HASH,
    }
    actual_pins = {
        "case_manifest_version": rules.case_manifest_version,
        "case_manifest_content_hash": rules.case_manifest_content_hash,
        "field_manifest_version": rules.field_manifest_version,
        "field_manifest_content_hash": rules.field_manifest_content_hash,
    }
    if actual_pins != expected_pins:
        raise ValueError(
            "document observation RuleSet disagrees with the frozen manifests"
        )
    if (
        rules.case_manifest_version != manifests.case_manifest.manifest_version
        or rules.case_manifest_content_hash != manifests.case_manifest.content_hash
        or rules.field_manifest_version != manifests.field_manifest.manifest_version
        or rules.field_manifest_content_hash != manifests.field_manifest.content_hash
    ):
        raise ValueError("document observation RuleSet pins disagree with loaded manifests")
    expected_hash = compute_document_observation_configuration_hash(
        rules.model_dump(mode="json", exclude={"configuration_hash"})
    )
    if rules.configuration_hash != expected_hash:
        raise ValueError("document observation RuleSet configuration hash is invalid")


__all__ = [
    "DEFAULT_RULE_SET_PATH",
    "load_document_observation_rule_set",
    "require_frozen_document_observation_rule_set",
    "verify_rule_set_pins",
]
