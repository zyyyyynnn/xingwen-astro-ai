from __future__ import annotations

import pytest

from app.schemas.data_artifact_identity import (
    dataset_scientific_projection,
    derive_canonical_row_identity,
)


_RECORD = {
    "record_type": "unpaired",
    "entity_level": "planet_assertion",
}


def _member(
    *,
    reference: str = "Reference A",
    planet_name: str = "Assertion Planet b",
    normalized_name: str = "assertion planet b",
    source_entity_key: str = "caller-controlled",
    source_id: str = "nasa_exoplanet_archive.ps",
    include_discriminator: bool = True,
) -> dict[str, object]:
    row_key: list[list[str]] = [["pl_name", planet_name]]
    if include_discriminator:
        row_key.append(["pl_refname", reference])
    return {
        "entity_level": "planet_assertion",
        "identity_values": [
            {
                "field_id": "planet.name",
                "normalized_value": normalized_name,
                "normalization_rule_version": "1.0.0",
                "locator": {"raw_field": "pl_name"},
            }
        ],
        "source_record": {
            "source_id": source_id,
            "row_key": row_key,
            "source_entity_key": source_entity_key,
        },
    }


def _identity(member: dict[str, object]) -> dict[str, object]:
    return derive_canonical_row_identity(
        _RECORD,
        (member,),
        alignment_status="unmatched",
    )


def test_canonical_assertion_identity_ignores_source_entity_key() -> None:
    baseline = _identity(_member(source_entity_key="legitimate-row-key-text"))
    tampered = _identity(_member(source_entity_key="self-consistent-forgery"))

    assert baseline == tampered
    assertion_key = baseline["member_entities"][0]["logical_assertion_key"]
    assert assertion_key == "pl_name=Assertion Planet b|pl_refname=Reference A"
    assert "caller-controlled" not in assertion_key
    assert "self-consistent-forgery" not in assertion_key


def test_canonical_assertion_identity_normalizes_raw_row_key_representation() -> None:
    baseline = _identity(_member())
    representation_drift = _identity(
        _member(
            planet_name="  Assertion   Planet b  ",
            reference="  Reference   A  ",
        )
    )

    assert baseline == representation_drift


def test_canonical_assertion_identity_distinguishes_assertion_discriminator() -> None:
    first = _identity(_member(reference="Reference A"))
    second = _identity(_member(reference="Reference B"))

    assert first != second


def test_canonical_assertion_identity_requires_source_namespace() -> None:
    with pytest.raises(ValueError, match="source namespace"):
        _identity(_member(source_id=""))


def test_canonical_assertion_identity_requires_non_identity_discriminator() -> None:
    with pytest.raises(
        ValueError,
        match="non-identity row-key discriminator",
    ):
        _identity(_member(include_discriminator=False))


def test_dataset_projection_rejects_legacy_top_level_row_identity() -> None:
    with pytest.raises(ValueError, match="typed row_authority"):
        dataset_scientific_projection(
            {
                "rows": [
                    {
                        "canonical_row_identity": {
                            "identity_kind": "source_table",
                            "identity_version": "1.0.0",
                            "source_table_admission_id": "admission_01",
                            "source_table_row_id": "row_01",
                            "canonical_identity": "source-row-01",
                        },
                        "fields": [],
                    }
                ]
            }
        )
