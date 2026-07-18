from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.schemas.manifest import (
    CaseManifest,
    FieldManifest,
    compute_content_hash,
    load_manifest_bundle,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
MANIFEST_DIRECTORY = (
    REPOSITORY_ROOT / "services" / "data_pipeline" / "manifests" / "exoplanet_host_star"
)
CASE_MANIFEST_PATH = MANIFEST_DIRECTORY / "case-manifest.v1.json"
FIELD_MANIFEST_PATH = MANIFEST_DIRECTORY / "field-manifest.v1.json"

APPROVED_FIELD_IDS = {
    "planet.toi_id",
    "planet.name",
    "planet.disposition",
    "star.tic_id",
    "star.gaia_dr3_id",
    "star.name",
    "system.right_ascension",
    "system.declination",
    "planet.orbital_period",
    "planet.radius",
    "planet.mass",
    "star.effective_temperature",
    "star.metallicity",
    "star.radius",
    "star.mass",
}


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _rehash(payload: dict[str, Any]) -> dict[str, Any]:
    payload["content_hash"] = compute_content_hash(payload)
    return payload


def test_manifest_bundle_is_valid_and_freezes_the_approved_fields() -> None:
    bundle = load_manifest_bundle(CASE_MANIFEST_PATH, FIELD_MANIFEST_PATH)

    assert bundle.case_manifest.case_id == "exoplanet_host_star"
    assert bundle.field_manifest.case_id == "exoplanet_host_star"
    assert {field.field_id for field in bundle.field_manifest.fields} == APPROVED_FIELD_IDS
    assert set(bundle.case_manifest.default_requested_fields) == APPROVED_FIELD_IDS
    assert len(bundle.field_manifest.fields) == 15


def test_each_field_contains_the_c01_metadata_contract() -> None:
    manifest = load_manifest_bundle(CASE_MANIFEST_PATH, FIELD_MANIFEST_PATH).field_manifest

    for field in manifest.fields:
        assert field.meaning_zh.strip()
        assert field.label_en.strip()
        assert field.data_type
        assert field.canonical_unit
        assert field.source_aliases
        assert field.source_priority
        assert field.conflict_resolution_strategy
        assert field.conflict_resolution_rule_version
        assert isinstance(field.required, bool)
        assert isinstance(field.nullable, bool)
        assert field.null_policy
        assert field.limit_policy
        assert field.uncertainty_policy
        assert isinstance(field.object_identity_key, bool)
        assert isinstance(field.crossmatch_key, bool)
        assert field.evidence_locator_rule_id
        assert field.transformation_rule_version
        assert field.quality_metric_inputs


def test_canonical_ids_are_separate_from_nasa_source_aliases() -> None:
    manifest = load_manifest_bundle(CASE_MANIFEST_PATH, FIELD_MANIFEST_PATH).field_manifest
    aliases = {
        alias.raw_field
        for field in manifest.fields
        for alias in field.source_aliases
    }

    assert APPROVED_FIELD_IDS.isdisjoint(aliases)
    assert "pl_rade" in aliases
    assert manifest.field_by_id("planet.radius").source_aliases_for(
        "nasa_exoplanet_archive.toi"
    )[0].raw_field == "pl_rade"


def test_source_alias_cannot_reuse_a_canonical_field_id() -> None:
    payload = _read_json(FIELD_MANIFEST_PATH)
    radius_field = next(
        field for field in payload["fields"] if field["field_id"] == "planet.radius"
    )
    radius_field["source_aliases"][0]["raw_field"] = "planet.radius"

    with pytest.raises(ValidationError, match="source alias must not use canonical field id"):
        FieldManifest.model_validate(_rehash(payload))


def test_duplicate_canonical_field_ids_are_rejected() -> None:
    payload = _read_json(FIELD_MANIFEST_PATH)
    payload["fields"][1]["field_id"] = payload["fields"][0]["field_id"]

    with pytest.raises(ValidationError, match="duplicate canonical field id"):
        FieldManifest.model_validate(_rehash(payload))


def test_duplicate_aliases_within_one_source_table_are_rejected() -> None:
    payload = _read_json(FIELD_MANIFEST_PATH)
    first_alias = deepcopy(payload["fields"][1]["source_aliases"][0])
    payload["fields"][1]["source_aliases"].append(first_alias)

    with pytest.raises(ValidationError, match="duplicate source alias"):
        FieldManifest.model_validate(_rehash(payload))


def test_the_same_raw_alias_is_allowed_for_distinct_source_tables() -> None:
    manifest = load_manifest_bundle(CASE_MANIFEST_PATH, FIELD_MANIFEST_PATH).field_manifest
    radius_aliases = manifest.field_by_id("planet.radius").source_aliases
    pl_rade_scopes = {
        (alias.source_id, alias.source_table)
        for alias in radius_aliases
        if alias.raw_field == "pl_rade"
    }

    assert len(pl_rade_scopes) >= 2


def test_unknown_units_are_rejected() -> None:
    payload = _read_json(FIELD_MANIFEST_PATH)
    payload["fields"][0]["canonical_unit"] = "unregistered_unit"

    with pytest.raises(ValidationError, match="unregistered canonical unit"):
        FieldManifest.model_validate(_rehash(payload))


def test_incompatible_source_and_canonical_units_are_rejected() -> None:
    payload = _read_json(FIELD_MANIFEST_PATH)
    radius_field = next(
        field for field in payload["fields"] if field["field_id"] == "planet.radius"
    )
    radius_field["source_aliases"][0]["source_unit"] = "kelvin"

    with pytest.raises(ValidationError, match="incompatible unit quantity kinds"):
        FieldManifest.model_validate(_rehash(payload))


def test_non_numeric_fields_cannot_declare_measurement_uncertainty() -> None:
    payload = _read_json(FIELD_MANIFEST_PATH)
    tic_field = next(
        field for field in payload["fields"] if field["field_id"] == "star.tic_id"
    )
    tic_field["source_aliases"][0]["positive_error_field"] = "tiderr1"
    tic_field["source_aliases"][0]["negative_error_field"] = "tiderr2"
    tic_field["uncertainty_policy"] = {
        "rule_version": "1.0.0",
        "mode": "asymmetric_source_errors",
        "preserve_asymmetric_errors": True,
    }

    with pytest.raises(ValidationError, match="non-numeric field"):
        FieldManifest.model_validate(_rehash(payload))


def test_nasa_companion_columns_are_pinned_to_the_correct_source_tables() -> None:
    manifest = load_manifest_bundle(CASE_MANIFEST_PATH, FIELD_MANIFEST_PATH).field_manifest
    period = manifest.field_by_id("planet.orbital_period")
    period_aliases = {alias.source_id: alias for alias in period.source_aliases}

    assert period_aliases["nasa_exoplanet_archive.toi"].limit_field == "pl_orbperlim"
    assert period_aliases["nasa_exoplanet_archive.ps"].reference_field == "pl_refname"
    assert (
        period_aliases["nasa_exoplanet_archive.pscomppars"].reference_field
        == "pl_orbper_reflink"
    )

    right_ascension = manifest.field_by_id("system.right_ascension")
    ps_ra = right_ascension.source_aliases_for("nasa_exoplanet_archive.ps")[0]
    assert (ps_ra.positive_error_field, ps_ra.negative_error_field) == (
        "raerr1",
        "raerr2",
    )
    assert ps_ra.reference_field == "sy_refname"


@pytest.mark.parametrize(
    "manifest_class,path",
    [(CaseManifest, CASE_MANIFEST_PATH), (FieldManifest, FIELD_MANIFEST_PATH)],
)
def test_schema_version_is_required(manifest_class: type[Any], path: Path) -> None:
    payload = _read_json(path)
    payload.pop("schema_version")

    with pytest.raises(ValidationError):
        manifest_class.model_validate(_rehash(payload))


def test_content_hash_is_stable_and_detects_tampering() -> None:
    payload = _read_json(FIELD_MANIFEST_PATH)
    expected_hash = payload["content_hash"]
    reversed_payload = dict(reversed(payload.items()))

    assert compute_content_hash(payload) == expected_hash
    assert compute_content_hash(reversed_payload) == expected_hash

    payload["description"] = f'{payload["description"]} changed'
    with pytest.raises(ValidationError, match="content_hash does not match"):
        FieldManifest.model_validate(payload)


def test_case_manifest_pins_the_exact_field_manifest_version_and_hash() -> None:
    bundle = load_manifest_bundle(CASE_MANIFEST_PATH, FIELD_MANIFEST_PATH)
    reference = bundle.case_manifest.field_manifest

    assert reference.manifest_id == bundle.field_manifest.manifest_id
    assert reference.manifest_version == bundle.field_manifest.manifest_version
    assert reference.content_hash == bundle.field_manifest.content_hash


def test_requested_fields_accept_only_canonical_manifest_ids() -> None:
    bundle = load_manifest_bundle(CASE_MANIFEST_PATH, FIELD_MANIFEST_PATH)

    assert bundle.validate_requested_fields(
        ["planet.radius", "star.effective_temperature"]
    ) == ("planet.radius", "star.effective_temperature")

    with pytest.raises(ValueError, match="unsupported requested field"):
        bundle.validate_requested_fields(["pl_rade"])

    with pytest.raises(ValueError, match="unsupported requested field"):
        bundle.validate_requested_fields(["planet.unknown"])

    with pytest.raises(ValueError, match="at least one"):
        bundle.validate_requested_fields([])


def test_manifest_models_export_machine_readable_json_schema() -> None:
    case_schema = CaseManifest.model_json_schema()
    field_schema = FieldManifest.model_json_schema()

    assert "schema_version" in case_schema["required"]
    assert "fields" in field_schema["required"]
    assert field_schema["properties"]["fields"]["type"] == "array"
