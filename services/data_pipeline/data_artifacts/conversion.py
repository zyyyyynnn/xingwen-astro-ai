"""Deterministic Decimal unit conversions bound to the versioned catalog."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN, localcontext
from functools import lru_cache
import math

from app.schemas.data_artifacts import (
    DecimalCapacity,
    DataArtifactErrorCode,
    QuantityKind,
    UnitConversionImplementation,
    UnitConversionCatalog,
)

from .errors import DataArtifactError


@lru_cache(maxsize=1)
def _frozen_decimal_capacity() -> DecimalCapacity:
    from .policy import load_unit_conversion_catalog

    return load_unit_conversion_catalog().decimal_capacity


def _validate_decimal_capacity(
    value: Decimal,
    *,
    source_text: str,
    capacity: DecimalCapacity,
) -> None:
    if len(source_text) > capacity.max_input_text_length:
        raise DataArtifactError(
            DataArtifactErrorCode.capacity_exceeded,
            "numeric input text capacity exceeded",
        )
    digits = value.as_tuple().digits
    exponent = value.as_tuple().exponent
    if (
        len(digits) > capacity.max_significant_digits
        or abs(value.adjusted()) > capacity.max_adjusted_exponent
        or (
            isinstance(exponent, int)
            and max(-exponent, 0) > capacity.max_fractional_scale
        )
    ):
        raise DataArtifactError(
            DataArtifactErrorCode.capacity_exceeded,
            "numeric exponent, precision, or scale capacity exceeded",
        )


def decimal_from_source(
    value: object,
    *,
    capacity: DecimalCapacity | None = None,
) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
        raise DataArtifactError(
            DataArtifactErrorCode.invalid_numeric_value,
            "source value is not a supported numeric scalar",
        )
    if isinstance(value, float) and not math.isfinite(value):
        raise DataArtifactError(
            DataArtifactErrorCode.non_finite_numeric_value,
            "source numeric value must be finite",
        )
    try:
        source_text = str(value)
    except (ValueError, OverflowError) as exc:
        raise DataArtifactError(
            DataArtifactErrorCode.capacity_exceeded,
            "numeric input cannot be represented within bounded text capacity",
            cause=exc,
        ) from exc
    active_capacity = capacity or _frozen_decimal_capacity()
    if len(source_text) > active_capacity.max_input_text_length:
        raise DataArtifactError(
            DataArtifactErrorCode.capacity_exceeded,
            "numeric input text capacity exceeded",
        )
    try:
        converted = Decimal(source_text)
    except InvalidOperation as exc:
        raise DataArtifactError(
            DataArtifactErrorCode.invalid_numeric_value,
            "source numeric value is invalid",
            cause=exc,
        ) from exc
    if not converted.is_finite():
        raise DataArtifactError(
            DataArtifactErrorCode.non_finite_numeric_value,
            "source numeric value must be finite",
        )
    _validate_decimal_capacity(
        converted,
        source_text=source_text,
        capacity=active_capacity,
    )
    return Decimal(0) if converted.is_zero() else converted


def convert_decimal_value(
    value: object,
    *,
    rule_id: str,
    rule_version: str,
    source_unit: str,
    target_unit: str,
    quantity_kind: str,
    catalog: UnitConversionCatalog,
) -> Decimal:
    source = decimal_from_source(value, capacity=catalog.decimal_capacity)
    rule = _catalog_index(catalog).get(rule_id)
    if rule is None:
        raise DataArtifactError(
            DataArtifactErrorCode.unknown_conversion_rule,
            "conversion rule is not present in the frozen catalog",
        )
    if rule.rule_version != rule_version:
        raise DataArtifactError(
            DataArtifactErrorCode.conversion_catalog_mismatch,
            "conversion rule version does not match the frozen catalog",
        )
    if rule.quantity_kind.value not in {"none", quantity_kind}:
        raise DataArtifactError(
            DataArtifactErrorCode.quantity_kind_mismatch,
            "conversion quantity kind does not match the field",
        )
    if rule_id == "unit.identity":
        if source_unit != target_unit:
            raise DataArtifactError(
                DataArtifactErrorCode.incompatible_unit,
                "identity conversion requires identical source and target units",
            )
    elif rule.source_unit != source_unit or rule.target_unit != target_unit:
        raise DataArtifactError(
            DataArtifactErrorCode.incompatible_unit,
            "conversion unit pair does not match the frozen implementation",
        )
    with localcontext() as context:
        context.prec = catalog.precision_digits
        context.rounding = ROUND_HALF_EVEN
        converted = source * rule.factor
    _validate_decimal_capacity(
        converted,
        source_text=str(converted),
        capacity=catalog.decimal_capacity,
    )
    return Decimal(0) if converted.is_zero() else converted


def resolve_conversion_rule(
    *,
    source_unit: str,
    target_unit: str,
    quantity_kind: str | QuantityKind,
    catalog: UnitConversionCatalog,
) -> UnitConversionImplementation:
    """Resolve the unique frozen conversion for one field/unit pair."""

    kind = (
        quantity_kind.value
        if isinstance(quantity_kind, QuantityKind)
        else quantity_kind
    )
    if source_unit == target_unit:
        matches = [rule for rule in catalog.rules if rule.rule_id == "unit.identity"]
        if len(matches) != 1:
            raise DataArtifactError(
                DataArtifactErrorCode.conversion_catalog_mismatch,
                "frozen catalog must contain exactly one identity conversion",
            )
        return matches[0]

    matches = [
        rule
        for rule in catalog.rules
        if rule.source_unit == source_unit
        and rule.target_unit == target_unit
        and rule.quantity_kind.value == kind
    ]
    if len(matches) != 1:
        raise DataArtifactError(
            DataArtifactErrorCode.unknown_conversion_rule,
            "frozen catalog does not contain one unique compatible conversion",
        )
    return matches[0]


def serialize_decimal(
    value: Decimal,
    *,
    capacity: DecimalCapacity | None = None,
) -> str:
    if not value.is_finite():
        raise DataArtifactError(
            DataArtifactErrorCode.non_finite_numeric_value,
            "canonical numeric value must be finite",
        )
    active_capacity = capacity or _frozen_decimal_capacity()
    _validate_decimal_capacity(
        value,
        source_text=str(value),
        capacity=active_capacity,
    )
    if value.is_zero():
        return "0"
    rendered = format(value, "f")
    if len(rendered) > active_capacity.max_plain_string_length:
        raise DataArtifactError(
            DataArtifactErrorCode.capacity_exceeded,
            "plain decimal serialization capacity exceeded",
        )
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


@lru_cache(maxsize=32)
def _catalog_index(catalog: UnitConversionCatalog):
    return {rule.rule_id: rule for rule in catalog.rules}


__all__ = [
    "convert_decimal_value",
    "decimal_from_source",
    "resolve_conversion_rule",
    "serialize_decimal",
]
