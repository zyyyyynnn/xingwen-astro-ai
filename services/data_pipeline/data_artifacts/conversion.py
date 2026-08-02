"""Deterministic Decimal unit conversions bound to the versioned catalog."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN, localcontext
from functools import lru_cache
import math

from app.schemas.data_artifacts import (
    DataArtifactErrorCode,
    UnitConversionCatalog,
)

from .errors import DataArtifactError


def decimal_from_source(value: object) -> Decimal:
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
        converted = Decimal(str(value))
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
    return converted


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
    source = decimal_from_source(value)
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
    if rule_id == "unit.identity.v1":
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
        return source * rule.factor


def serialize_decimal(value: Decimal) -> str:
    if not value.is_finite():
        raise DataArtifactError(
            DataArtifactErrorCode.non_finite_numeric_value,
            "canonical numeric value must be finite",
        )
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


@lru_cache(maxsize=32)
def _catalog_index(catalog: UnitConversionCatalog):
    return {rule.rule_id: rule for rule in catalog.rules}


__all__ = ["convert_decimal_value", "decimal_from_source", "serialize_decimal"]
