"""Load and authenticate the frozen C-05 quality RuleSet."""

from __future__ import annotations

from pathlib import Path

from app.schemas.data_quality import DataQualityRuleSet


_RULE_ROOT = (
    Path(__file__).resolve().parents[1]
    / "manifests"
    / "exoplanet_host_star"
    / "quality-rules"
)
DEFAULT_QUALITY_RULE_SET_PATH = _RULE_ROOT / "quality-rules.v1.json"


def load_quality_rule_set(
    path: Path = DEFAULT_QUALITY_RULE_SET_PATH,
) -> DataQualityRuleSet:
    """Parse one versioned RuleSet; model validation includes its self-hash."""

    return DataQualityRuleSet.model_validate_json(path.read_text(encoding="utf-8"))


def load_frozen_quality_rule_set() -> DataQualityRuleSet:
    """Load only the repository-authored C-05 RuleSet."""

    return load_quality_rule_set(DEFAULT_QUALITY_RULE_SET_PATH)


def require_frozen_quality_rule_set(candidate: DataQualityRuleSet) -> DataQualityRuleSet:
    """Reject caller rules even when a caller recomputed a modified self-hash."""

    frozen = load_frozen_quality_rule_set()
    if candidate != frozen:
        raise ValueError("caller quality RuleSet is not the frozen repository RuleSet")
    return frozen


__all__ = [
    "DEFAULT_QUALITY_RULE_SET_PATH",
    "load_frozen_quality_rule_set",
    "load_quality_rule_set",
    "require_frozen_quality_rule_set",
]
