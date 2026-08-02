from __future__ import annotations

from decimal import Decimal
import json

import pytest
from pydantic import ValidationError

from services.data_pipeline.data_artifacts.conversion import convert_decimal_value, serialize_decimal
from services.data_pipeline.data_artifacts.errors import DataArtifactError
from services.data_pipeline.data_artifacts.policy import (
    DEFAULT_UNIT_CONVERSION_CATALOG_PATH,
    load_unit_conversion_catalog,
)


def test_frozen_conversion_catalog_is_hash_valid_and_iau_provenanced() -> None:
    catalog = load_unit_conversion_catalog()
    raw = json.loads(DEFAULT_UNIT_CONVERSION_CATALOG_PATH.read_text(encoding="utf-8"))

    assert catalog.catalog_id == "exoplanet_host_star.unit_conversions"
    assert catalog.content_hash.startswith("sha256:")
    assert "IAU 2015 Resolution B3" in catalog.constants_provenance.title
    assert len(catalog.rules) == 3

    raw["rules"][1]["factor"] = "999"
    with pytest.raises(ValidationError, match="factor|content_hash"):
        type(catalog).model_validate(raw)


@pytest.mark.parametrize(
    ("rule_id", "source_unit", "target_unit", "value", "expected"),
    (
        ("unit.identity.v1", "day", "day", "0", "0"),
        (
            "unit.jupiter_radius_to_earth_radius.v1",
            "jupiter_radius",
            "earth_radius",
            "1",
            "11.20898073093868079835687744",
        ),
        (
            "unit.jupiter_mass_to_earth_mass.v1",
            "jupiter_mass",
            "earth_mass",
            "1",
            "317.8284065946747670097671753",
        ),
    ),
)
def test_decimal_conversions_are_deterministic(
    rule_id: str,
    source_unit: str,
    target_unit: str,
    value: str,
    expected: str,
) -> None:
    catalog = load_unit_conversion_catalog()

    converted = convert_decimal_value(
        Decimal(value),
        rule_id=rule_id,
        rule_version="1.0.0",
        source_unit=source_unit,
        target_unit=target_unit,
        quantity_kind=("none" if rule_id == "unit.identity.v1" else "length" if "radius" in rule_id else "mass"),
        catalog=catalog,
    )

    assert format(converted, "f") == expected


@pytest.mark.parametrize("value", (True, "not-a-number", float("nan"), float("inf")))
def test_conversion_rejects_invalid_or_non_finite_values(value: object) -> None:
    with pytest.raises(DataArtifactError) as exc_info:
        convert_decimal_value(
            value,
            rule_id="unit.identity.v1",
            rule_version="1.0.0",
            source_unit="day",
            target_unit="day",
            quantity_kind="time",
            catalog=load_unit_conversion_catalog(),
        )

    assert exc_info.value.code in {
        "INVALID_NUMERIC_VALUE",
        "NON_FINITE_NUMERIC_VALUE",
    }


def test_identity_and_unit_bindings_fail_closed() -> None:
    catalog = load_unit_conversion_catalog()

    with pytest.raises(DataArtifactError) as exc_info:
        convert_decimal_value(
            Decimal("1"),
            rule_id="unit.identity.v1",
            rule_version="1.0.0",
            source_unit="day",
            target_unit="earth_mass",
            quantity_kind="time",
            catalog=catalog,
        )

    assert exc_info.value.code == "INCOMPATIBLE_UNIT"


@pytest.mark.parametrize(
    ("rule_id", "source_unit", "target_unit", "quantity_kind", "code"),
    (
        ("unit.missing.v1", "day", "day", "time", "UNKNOWN_CONVERSION_RULE"),
        ("unit.jupiter_radius_to_earth_radius.v1", "earth_radius", "earth_radius", "length", "INCOMPATIBLE_UNIT"),
        ("unit.jupiter_radius_to_earth_radius.v1", "jupiter_radius", "earth_radius", "mass", "QUANTITY_KIND_MISMATCH"),
    ),
)
def test_conversion_rule_unit_and_quantity_bindings_fail_closed(
    rule_id: str,
    source_unit: str,
    target_unit: str,
    quantity_kind: str,
    code: str,
) -> None:
    with pytest.raises(DataArtifactError) as exc_info:
        convert_decimal_value(
            "1",
            rule_id=rule_id,
            rule_version="1.0.0",
            source_unit=source_unit,
            target_unit=target_unit,
            quantity_kind=quantity_kind,
            catalog=load_unit_conversion_catalog(),
        )

    assert exc_info.value.code == code


def test_decimal_serialization_is_plain_and_repeatable() -> None:
    value = Decimal("317.8284065946747670097671753000")

    assert serialize_decimal(value) == "317.8284065946747670097671753"
    assert serialize_decimal(value) == serialize_decimal(value)
