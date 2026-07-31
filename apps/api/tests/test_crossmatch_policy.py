from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.schemas.crossmatch import (
    CrossmatchRuleSet,
    EntityAliasCatalog,
    compute_crossmatch_content_hash,
)
from services.data_pipeline.constants import (
    CROSSMATCH_PRODUCER_NAME,
    CROSSMATCH_PRODUCER_VERSION,
    FROZEN_CASE_MANIFEST_CONTENT_HASH,
    FROZEN_CASE_MANIFEST_VERSION,
    FROZEN_FIELD_MANIFEST_CONTENT_HASH,
    FROZEN_FIELD_MANIFEST_VERSION,
    SOURCE_POLICY_VERSION,
)
from services.data_pipeline.crossmatch.policy import (
    DEFAULT_ALIAS_CATALOG_PATH,
    DEFAULT_SOURCE_POLICY_PATH,
    load_crossmatch_rule_set,
    load_entity_alias_catalog,
)
from services.data_pipeline.crossmatch import policy as crossmatch_policy


def test_versioned_crossmatch_policy_pins_all_frozen_inputs() -> None:
    rule_set = load_crossmatch_rule_set()
    catalog = load_entity_alias_catalog()

    assert rule_set.case_manifest_id == "exoplanet_host_star"
    assert rule_set.case_manifest_version == FROZEN_CASE_MANIFEST_VERSION
    assert rule_set.case_manifest_content_hash == FROZEN_CASE_MANIFEST_CONTENT_HASH
    assert rule_set.field_manifest_id == "exoplanet_host_star.fields"
    assert rule_set.field_manifest_version == FROZEN_FIELD_MANIFEST_VERSION
    assert rule_set.field_manifest_content_hash == FROZEN_FIELD_MANIFEST_CONTENT_HASH
    assert rule_set.source_policy_version == SOURCE_POLICY_VERSION
    assert rule_set.producer_name == CROSSMATCH_PRODUCER_NAME
    assert rule_set.producer_version == CROSSMATCH_PRODUCER_VERSION
    assert rule_set.entity_alias_catalog_version == catalog.version
    assert rule_set.entity_alias_catalog_content_hash == catalog.content_hash


def test_frozen_source_policy_is_the_typed_origin_authority() -> None:
    loader = getattr(crossmatch_policy, "load_crossmatch_source_policy", None)

    assert loader is not None
    policy = loader()
    expected = json.loads(DEFAULT_SOURCE_POLICY_PATH.read_text(encoding="utf-8"))

    assert policy.model_dump(mode="json") == expected
    assert {
        origin.source_mode.value: {
            data_level.value for data_level in origin.data_levels
        }
        for origin in policy.allowed_origins
    } == {
        "fixture": {"fixture", "recorded_response"},
        "live": {"live_result"},
    }


def test_alias_catalog_is_explicit_versioned_evidence_not_name_guessing() -> None:
    catalog = load_entity_alias_catalog()

    assert catalog.catalog_id == "exoplanet_host_star.entity_aliases"
    assert catalog.entries
    assert all(entry.rationale.strip() for entry in catalog.entries)
    assert all(
        entry.left_source_id != entry.right_source_id
        for entry in catalog.entries
    )


def test_alias_catalog_rejects_content_tampering() -> None:
    payload = json.loads(DEFAULT_ALIAS_CATALOG_PATH.read_text(encoding="utf-8"))
    payload["entries"][0]["right_value"] = "tampered"

    with pytest.raises(ValidationError, match="content_hash"):
        EntityAliasCatalog.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "removed"),
    [
        ("method_priority", "coordinate"),
        ("supported_entity_levels", "planet_assertion"),
    ],
)
def test_rule_set_requires_complete_closed_method_and_entity_sets(
    field: str,
    removed: str,
) -> None:
    payload = load_crossmatch_rule_set().model_dump(mode="json")
    payload[field].remove(removed)
    payload["content_hash"] = compute_crossmatch_content_hash(payload)

    with pytest.raises(ValidationError, match="must cover every"):
        CrossmatchRuleSet.model_validate(payload)
