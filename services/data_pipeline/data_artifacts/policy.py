"""Load the frozen Versioned Data Artifact execution policies with full hash validation."""

from __future__ import annotations

from pathlib import Path

from app.schemas.data_artifacts import MappingRuleSet, UnitConversionCatalog


_RULE_ROOT = (
    Path(__file__).resolve().parents[1]
    / "manifests"
    / "exoplanet_host_star"
    / "mapping-rules"
)
DEFAULT_MAPPING_RULE_SET_PATH = _RULE_ROOT / "mapping-rules.json"
DEFAULT_UNIT_CONVERSION_CATALOG_PATH = _RULE_ROOT / "unit-conversions.json"


def load_mapping_rule_set(
    path: Path = DEFAULT_MAPPING_RULE_SET_PATH,
) -> MappingRuleSet:
    return MappingRuleSet.model_validate_json(path.read_text(encoding="utf-8"))


def load_unit_conversion_catalog(
    path: Path = DEFAULT_UNIT_CONVERSION_CATALOG_PATH,
) -> UnitConversionCatalog:
    return UnitConversionCatalog.model_validate_json(path.read_text(encoding="utf-8"))


__all__ = [
    "DEFAULT_MAPPING_RULE_SET_PATH",
    "DEFAULT_UNIT_CONVERSION_CATALOG_PATH",
    "load_mapping_rule_set",
    "load_unit_conversion_catalog",
]
