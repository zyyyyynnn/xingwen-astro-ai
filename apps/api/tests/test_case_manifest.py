from __future__ import annotations

import json
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.schemas.manifest import (
    CaseManifest,
    FieldManifest,
    ManifestBundle,
    compute_content_hash,
    load_manifest_bundle,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
MANIFEST_DIRECTORY = (
    REPOSITORY_ROOT / "services" / "data_pipeline" / "manifests" / "exoplanet_host_star"
)
CASE_MANIFEST_PATH = MANIFEST_DIRECTORY / "case-manifest.json"
FIELD_MANIFEST_PATH = MANIFEST_DIRECTORY / "field-manifest.json"
SOURCE_EVIDENCE_DIRECTORY = (
    MANIFEST_DIRECTORY
    / "source-evidence"
    / "nasa-exoplanet-archive"
    / "2026-07-19"
)
SOURCE_ADJUDICATION_PATH = (
    SOURCE_EVIDENCE_DIRECTORY / "column-adjudications.json"
)

SOURCE_COLUMN_ROLES = (
    "raw_field",
    "positive_error_field",
    "negative_error_field",
    "limit_field",
    "reference_field",
    "provenance_field",
)

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


def _adjudicated_source_contracts() -> dict[str, dict[str, Any]]:
    adjudication = _read_json(SOURCE_ADJUDICATION_PATH)
    return {
        contract["source_id"]: contract
        for contract in adjudication["table_contracts"]
    }


def _source_aliases(payload: dict[str, Any], source_id: str) -> list[dict[str, Any]]:
    return [
        alias
        for field in payload["fields"]
        for alias in field["source_aliases"]
        if alias["source_id"] == source_id
    ]


def _file_sha256(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def test_manifest_bundle_is_valid_and_freezes_the_approved_fields() -> None:
    bundle = load_manifest_bundle(CASE_MANIFEST_PATH, FIELD_MANIFEST_PATH)

    assert bundle.case_manifest.case_id == "exoplanet_host_star"
    assert bundle.field_manifest.case_id == "exoplanet_host_star"
    assert {field.field_id for field in bundle.field_manifest.fields} == APPROVED_FIELD_IDS
    assert set(bundle.case_manifest.default_requested_fields) == APPROVED_FIELD_IDS
    assert len(bundle.field_manifest.fields) == 15


def test_case_manifest_uses_created_at_and_maintained_by() -> None:
    payload = _read_json(CASE_MANIFEST_PATH)

    assert "created_at" in payload
    assert "maintained_by" in payload

    manifest = CaseManifest.model_validate(payload)
    assert manifest.created_at
    assert manifest.maintained_by.module == "data_pipeline"


def test_field_manifest_uses_created_at_and_maintained_by() -> None:
    payload = _read_json(FIELD_MANIFEST_PATH)

    assert "created_at" in payload
    assert "maintained_by" in payload

    manifest = FieldManifest.model_validate(payload)
    assert manifest.created_at
    assert manifest.maintained_by.module == "data_pipeline"


@pytest.mark.parametrize(
    ("manifest_class", "path"),
    [(CaseManifest, CASE_MANIFEST_PATH), (FieldManifest, FIELD_MANIFEST_PATH)],
)
def test_manifest_metadata_contract_rejects_unknown_fields(
    manifest_class: type[Any],
    path: Path,
) -> None:
    payload = _read_json(path)
    payload["unexpected_metadata"] = deepcopy(payload["maintained_by"])

    with pytest.raises(ValidationError) as captured:
        manifest_class.model_validate(_rehash(payload))

    assert ("unexpected_metadata",) in {
        tuple(error["loc"]) for error in captured.value.errors()
    }


@pytest.mark.parametrize("required_field", ["created_at", "maintained_by"])
def test_case_manifest_rejects_missing_audit_metadata(required_field: str) -> None:
    payload = _read_json(CASE_MANIFEST_PATH)
    payload.pop(required_field)

    with pytest.raises(ValidationError) as captured:
        CaseManifest.model_validate(payload)

    assert required_field in str(captured.value)


def test_each_field_contains_the_case_manifest_metadata_contract() -> None:
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


def test_source_definitions_pin_the_adjudicated_column_allowlists() -> None:
    payload = _read_json(FIELD_MANIFEST_PATH)
    adjudicated = _adjudicated_source_contracts()

    for source in payload["sources"]:
        assert "approved_columns" in source
        contract = adjudicated[source["source_id"]]
        assert set(source["approved_columns"]) == set(contract["approved_columns"])
        assert source["row_key_fields"] == contract["row_key_fields"]
        assert source["reference_columns"] == contract["reference_columns"]
        assert source["provenance_columns"] == contract["provenance_columns"]


def test_every_alias_column_exists_in_its_adjudicated_source_allowlist() -> None:
    payload = _read_json(FIELD_MANIFEST_PATH)
    adjudicated = _adjudicated_source_contracts()

    for source_id, contract in adjudicated.items():
        approved_columns = set(contract["approved_columns"])
        for alias in _source_aliases(payload, source_id):
            declared_columns = set(alias["row_key_fields"])
            declared_columns.update(
                alias[role]
                for role in SOURCE_COLUMN_ROLES
                if alias.get(role) is not None
            )
            assert declared_columns <= approved_columns, (
                source_id,
                sorted(declared_columns - approved_columns),
            )


def test_row_keys_match_the_adjudicated_source_tables() -> None:
    payload = _read_json(FIELD_MANIFEST_PATH)

    for source_id, contract in _adjudicated_source_contracts().items():
        expected = tuple(contract["row_key_fields"])
        for alias in _source_aliases(payload, source_id):
            assert tuple(alias["row_key_fields"]) == expected


def test_reference_and_provenance_columns_match_the_adjudicated_sources() -> None:
    payload = _read_json(FIELD_MANIFEST_PATH)

    for source_id, contract in _adjudicated_source_contracts().items():
        aliases = _source_aliases(payload, source_id)
        actual_references = {
            alias["reference_field"]
            for alias in aliases
            if alias.get("reference_field")
        }
        actual_provenance = {
            alias["provenance_field"]
            for alias in aliases
            if alias.get("provenance_field")
        }
        assert actual_references == set(contract["reference_columns"])
        assert actual_provenance == set(contract["provenance_columns"])


@pytest.mark.parametrize(
    "column_role",
    ["raw_field", "row_key_fields", *SOURCE_COLUMN_ROLES[1:]],
)
def test_unapproved_source_columns_are_rejected(column_role: str) -> None:
    payload = _read_json(FIELD_MANIFEST_PATH)
    aliases = [
        alias
        for field in payload["fields"]
        for alias in field["source_aliases"]
        if column_role in alias
    ]
    alias = aliases[0]
    if column_role == "row_key_fields":
        alias[column_role] = ["definitely_not_a_real_source_column"]
    else:
        alias[column_role] = "definitely_not_a_real_source_column"

    with pytest.raises(ValidationError, match="not an approved source column"):
        FieldManifest.model_validate(_rehash(payload))


@pytest.mark.parametrize(
    ("column_role", "expected_message"),
    [
        ("row_key_fields", "row key fields do not match"),
        ("reference_field", "not an approved reference column"),
        ("provenance_field", "not an approved provenance column"),
    ],
)
def test_approved_columns_cannot_be_used_in_the_wrong_source_role(
    column_role: str,
    expected_message: str,
) -> None:
    payload = _read_json(FIELD_MANIFEST_PATH)
    ps_aliases = _source_aliases(payload, "nasa_exoplanet_archive.ps")
    alias = next(item for item in ps_aliases if column_role in item)
    if column_role == "row_key_fields":
        alias[column_role] = ["ra"]
    else:
        alias[column_role] = "ra"

    with pytest.raises(ValidationError, match=expected_message):
        FieldManifest.model_validate(_rehash(payload))


def test_provider_source_ids_resolve_to_the_existing_table_source_definitions() -> None:
    case_payload = _read_json(CASE_MANIFEST_PATH)
    field_payload = _read_json(FIELD_MANIFEST_PATH)

    assert case_payload["allowed_source_ids"] == ["nasa_exoplanet_archive"]
    assert all("provider_source_id" in source for source in field_payload["sources"])
    assert {
        source["provider_source_id"] for source in field_payload["sources"]
    } == set(case_payload["allowed_source_ids"])
    assert all(
        source["source_id"]
        == f'{source["provider_source_id"]}.{source["source_table"]}'
        for source in field_payload["sources"]
    )

    bundle = load_manifest_bundle(CASE_MANIFEST_PATH, FIELD_MANIFEST_PATH)
    expected_table_ids = tuple(
        source["source_id"] for source in field_payload["sources"]
    )
    assert bundle.resolve_source_scope(["nasa_exoplanet_archive"]) == expected_table_ids

    with pytest.raises(ValueError, match="unsupported provider source"):
        bundle.resolve_source_scope(["unsupported_provider"])


def test_source_definitions_pin_the_versioned_adjudication_record() -> None:
    payload = _read_json(FIELD_MANIFEST_PATH)
    adjudication = _read_json(SOURCE_ADJUDICATION_PATH)
    expected_hash = _file_sha256(SOURCE_ADJUDICATION_PATH)

    for source in payload["sources"]:
        assert "column_contract" in source
        reference = source["column_contract"]
        assert reference["snapshot_id"] == adjudication["snapshot_id"]
        assert reference["snapshot_version"] == adjudication["snapshot_version"]
        assert reference["content_hash"] == expected_hash
        assert REPOSITORY_ROOT / reference["path"] == SOURCE_ADJUDICATION_PATH


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


def test_content_hash_normalizes_explicit_and_omitted_defaults() -> None:
    explicit_default = _read_json(FIELD_MANIFEST_PATH)
    omitted_default = deepcopy(explicit_default)
    assert (
        omitted_default["sources"][0].pop("declaration_mode")
        == "metadata_only"
    )

    published_manifest = FieldManifest.model_validate(explicit_default)
    expected_hash = compute_content_hash(explicit_default)

    assert compute_content_hash(omitted_default) == expected_hash
    assert compute_content_hash(published_manifest) == expected_hash


def test_case_manifest_pins_the_exact_field_manifest_version_and_hash() -> None:
    bundle = load_manifest_bundle(CASE_MANIFEST_PATH, FIELD_MANIFEST_PATH)
    reference = bundle.case_manifest.field_manifest

    assert reference.manifest_id == bundle.field_manifest.manifest_id
    assert reference.manifest_version == bundle.field_manifest.manifest_version
    assert reference.content_hash == bundle.field_manifest.content_hash


@pytest.mark.parametrize(
    ("reference_key", "tampered_value", "expected_message"),
    [
        (
            "manifest_version",
            "9.9.9",
            "field manifest version does not match the case reference",
        ),
        (
            "content_hash",
            f"sha256:{'0' * 64}",
            "field manifest hash does not match the case reference",
        ),
    ],
)
def test_bundle_rejects_tampered_field_manifest_reference(
    reference_key: str,
    tampered_value: str,
    expected_message: str,
) -> None:
    case_payload = _read_json(CASE_MANIFEST_PATH)
    case_payload["field_manifest"][reference_key] = tampered_value
    case_manifest = CaseManifest.model_validate(_rehash(case_payload))
    field_manifest = FieldManifest.model_validate(_read_json(FIELD_MANIFEST_PATH))

    with pytest.raises(ValidationError, match=expected_message):
        ManifestBundle(
            case_manifest=case_manifest,
            field_manifest=field_manifest,
        )


def test_bundle_rejects_field_alias_source_not_allowed_by_case() -> None:
    field_payload = _read_json(FIELD_MANIFEST_PATH)
    field_payload["sources"].append(
        {
            "source_id": "review.extra",
            "provider_source_id": "review",
            "provider": "Review fixture",
            "name": "Unapproved review source",
            "source_table": "extra",
            "documentation_url": "https://example.com/review-extra",
            "declaration_mode": "metadata_only",
            "approved_columns": ["review_id", "review_name"],
            "row_key_fields": ["review_id"],
            "reference_columns": [],
            "provenance_columns": [],
            "column_contract": {
                "snapshot_id": "review.extra.columns",
                "snapshot_version": "1.0.0",
                "path": "tests/fixtures/review-extra-columns.json",
                "content_hash": f"sha256:{'0' * 64}",
            },
        }
    )
    planet_name = next(
        field for field in field_payload["fields"] if field["field_id"] == "planet.name"
    )
    planet_name["source_aliases"].append(
        {
            "source_id": "review.extra",
            "source_table": "extra",
            "raw_field": "review_name",
            "source_unit": planet_name["canonical_unit"],
            "conversion_rule_id": "unit.identity",
            "priority": 1,
            "row_key_fields": ["review_id"],
        }
    )
    planet_name["source_priority"].append("review.extra")
    field_manifest = FieldManifest.model_validate(_rehash(field_payload))

    case_payload = _read_json(CASE_MANIFEST_PATH)
    case_payload["allowed_source_ids"] = ["nasa_exoplanet_archive"]
    case_payload["field_manifest"]["content_hash"] = field_manifest.content_hash
    case_manifest = CaseManifest.model_validate(_rehash(case_payload))

    with pytest.raises(ValidationError, match="review.extra"):
        ManifestBundle(
            case_manifest=case_manifest,
            field_manifest=field_manifest,
        )


@pytest.mark.parametrize(
    "manifest_class,path",
    [(CaseManifest, CASE_MANIFEST_PATH), (FieldManifest, FIELD_MANIFEST_PATH)],
)
def test_invalid_schema_version_is_rejected(
    manifest_class: type[Any],
    path: Path,
) -> None:
    payload = _read_json(path)
    payload["schema_version"] = "abc"

    with pytest.raises(ValidationError, match="schema_version"):
        manifest_class.model_validate(payload)


@pytest.mark.parametrize(
    "manifest_class,path",
    [(CaseManifest, CASE_MANIFEST_PATH), (FieldManifest, FIELD_MANIFEST_PATH)],
)
def test_invalid_content_hash_format_is_rejected(
    manifest_class: type[Any],
    path: Path,
) -> None:
    payload = _read_json(path)
    payload["content_hash"] = "not-a-sha256-hash"

    with pytest.raises(ValidationError, match="content_hash"):
        manifest_class.model_validate(payload)


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
    assert "created_at" in field_schema["required"]
    assert "maintained_by" in field_schema["required"]
    assert field_schema["properties"]["fields"]["type"] == "array"
