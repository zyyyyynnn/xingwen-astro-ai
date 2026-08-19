"""Machine Authority for the three-reference capability coverage denominator.

The JSON manifest next to this module is the only coverage denominator for the
Inosum / AutoAstro / MAVIS reference migration.  Coverage is computed per
reference and per category (function / presentation / interaction) as

    implemented_count / eligible_count

where ``eligible_count`` counts capabilities with ``eligible=true`` in that
category, and ``implemented_count`` requires ``eligible=true`` plus a
disposition of ``adopted`` or ``replaced`` plus
``implementation_state=implemented`` plus a non-empty
``production_entrypoint`` plus a satisfied user-reachability gate:
capabilities exposed through the workspace must be ``reachable``; function
capabilities that never require direct user operation may be
``not_applicable``.  ``integration_pending`` entries stay in the denominator
and never count as completed coverage.  ``live_state`` is reported alongside
coverage but never participates in the percentage: live verification is a
separate, human-gated fact and must never be inferred from unit tests.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ALLOWED_REFERENCES = ("inosum", "autoastro", "mavis")
ALLOWED_CATEGORIES = ("function", "presentation", "interaction")
ALLOWED_DISPOSITIONS = ("adopted", "replaced", "rejected")
ALLOWED_IMPLEMENTATION_STATES = ("implemented", "integration_pending", "missing")
ALLOWED_VERIFICATION = (
    "contract",
    "unit",
    "component",
    "benchmark",
    "recorded",
    "live",
    "browser",
)
ALLOWED_USER_REACHABILITY = ("reachable", "unreachable", "not_applicable")
ALLOWED_LIVE_STATES = ("verified", "not_verified", "not_applicable")

# Repository-internal owner paths must point at real files; the manifest
# builder enforces this against the repository root.
FORBIDDEN_ID_FRAGMENTS = (
    "capability_v",
    "_v1",
    "_v2",
    "v1.",
    "v2.",
    "old",
    "legacy",
    "phase1",
    "phase2",
    "tmp",
)

SCHEMA_VERSION = "1.1.0"


@dataclass(frozen=True, slots=True)
class ReferenceCapability:
    reference: str
    category: str
    capability_id: str
    reference_sources: tuple[str, ...]
    disposition: str
    implementation_state: str
    eligible: bool
    exclusion_reason: str | None
    xingwen_owners: tuple[str, ...]
    verification: tuple[str, ...]
    production_entrypoint: str | None
    user_reachability: str
    live_state: str
    notes: str

    @property
    def reachability_satisfied(self) -> bool:
        if self.category == "function":
            return self.user_reachability in ("reachable", "not_applicable")
        return self.user_reachability == "reachable"

    @property
    def completed(self) -> bool:
        return (
            self.eligible
            and self.disposition in ("adopted", "replaced")
            and self.implementation_state == "implemented"
            and bool(self.production_entrypoint)
            and self.reachability_satisfied
        )


@dataclass(frozen=True, slots=True)
class ReferenceCapabilityManifest:
    capabilities: tuple[ReferenceCapability, ...]
    reference_snapshot_digests: dict[str, str]

    def eligible_count(self, reference: str, category: str) -> int:
        return sum(
            1
            for item in self.capabilities
            if item.reference == reference
            and item.category == category
            and item.eligible
        )

    def implemented_count(self, reference: str, category: str) -> int:
        return sum(
            1
            for item in self.capabilities
            if item.reference == reference
            and item.category == category
            and item.completed
        )

    def coverage_percent(self, reference: str, category: str) -> float:
        eligible = self.eligible_count(reference, category)
        if eligible == 0:
            raise ValueError(
                f"{reference}/{category} has no eligible capabilities in the denominator"
            )
        return self.implemented_count(reference, category) * 100.0 / eligible

    def state_counts(self) -> dict[str, int]:
        counts = {
            "integration_pending": 0,
            "missing": 0,
            "excluded": 0,
        }
        for item in self.capabilities:
            if not item.eligible:
                counts["excluded"] += 1
            elif item.implementation_state == "integration_pending":
                counts["integration_pending"] += 1
            elif item.implementation_state == "missing":
                counts["missing"] += 1
        return counts

    def coverage_report(self) -> dict[str, dict[str, dict[str, Any]]]:
        report: dict[str, dict[str, dict[str, Any]]] = {}
        for reference in ALLOWED_REFERENCES:
            axes: dict[str, dict[str, Any]] = {}
            for category in ALLOWED_CATEGORIES:
                eligible = self.eligible_count(reference, category)
                implemented = self.implemented_count(reference, category)
                axes[category] = {
                    "eligible": eligible,
                    "implemented": implemented,
                    "percent": round(implemented * 100.0 / eligible, 2)
                    if eligible
                    else None,
                }
            report[reference] = axes
        return report

    def capability_ids(self, reference: str | None = None) -> frozenset[str]:
        return frozenset(
            item.capability_id
            for item in self.capabilities
            if reference is None or item.reference == reference
        )


def _require_string_list(value: Any, field: str, *, allow_empty: bool) -> tuple[str, ...]:
    if not isinstance(value, list) or (
        not value and not allow_empty
    ):
        raise ValueError(f"{field} must be a non-empty array of strings")
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field} must contain only non-empty strings")
    return tuple(item.strip() for item in value)


def parse_capability(raw: Any, *, index: int) -> ReferenceCapability:
    if not isinstance(raw, dict):
        raise ValueError(f"capability #{index} must be an object")
    missing = {
        "reference",
        "category",
        "capability_id",
        "reference_sources",
        "disposition",
        "implementation_state",
        "eligible",
    } - set(raw)
    if missing:
        raise ValueError(
            f"capability #{index} is missing required keys: {sorted(missing)}"
        )
    reference = raw["reference"]
    if reference not in ALLOWED_REFERENCES:
        raise ValueError(f"capability #{index} has an unknown reference: {reference}")
    category = raw["category"]
    if category not in ALLOWED_CATEGORIES:
        raise ValueError(f"capability #{index} has an unknown category: {category}")
    capability_id = raw["capability_id"]
    if not isinstance(capability_id, str) or not capability_id.strip():
        raise ValueError(f"capability #{index} has an empty capability_id")
    capability_id = capability_id.strip()
    if not capability_id.startswith(f"{reference}."):
        raise ValueError(
            f"capability_id {capability_id} must be namespaced under {reference}."
        )
    lowered = capability_id.lower()
    for fragment in FORBIDDEN_ID_FRAGMENTS:
        if fragment in lowered:
            raise ValueError(
                f"capability_id {capability_id} contains the forbidden fragment"
                f" {fragment!r}"
            )
    reference_sources = _require_string_list(
        raw["reference_sources"], f"{capability_id}.reference_sources", allow_empty=False
    )
    disposition = raw["disposition"]
    if disposition not in ALLOWED_DISPOSITIONS:
        raise ValueError(
            f"{capability_id} has an unknown disposition: {disposition}"
        )
    implementation_state = raw["implementation_state"]
    if implementation_state not in ALLOWED_IMPLEMENTATION_STATES:
        raise ValueError(
            f"{capability_id} has an unknown implementation_state:"
            f" {implementation_state}"
        )
    eligible = raw["eligible"]
    if not isinstance(eligible, bool):
        raise ValueError(f"{capability_id}.eligible must be a boolean")
    exclusion_reason = raw.get("exclusion_reason")
    if disposition == "rejected" and eligible:
        # Unsafe reference implementations are recorded as rejected with
        # eligible=false; the user-facing capability itself is tracked as a
        # separate replaced entry.
        raise ValueError(
            f"{capability_id} is rejected but eligible; add a replaced capability"
            " for the user-facing capability instead"
        )
    if disposition != "rejected" and not eligible:
        raise ValueError(
            f"{capability_id} is eligible=false and must be rejected with an"
            " objective exclusion_reason"
        )
    if not eligible:
        if not isinstance(exclusion_reason, str) or not exclusion_reason.strip():
            raise ValueError(
                f"{capability_id} is eligible=false and requires exclusion_reason"
            )
    elif exclusion_reason is not None:
        raise ValueError(
            f"{capability_id} is eligible=true and must not carry exclusion_reason"
        )
    if eligible and implementation_state == "missing" and disposition != "rejected":
        raise ValueError(
            f"{capability_id} is eligible with implementation_state=missing; either"
            " implement it or mark it integration_pending"
        )
    xingwen_owners = _require_string_list(
        raw.get("xingwen_owners", []),
        f"{capability_id}.xingwen_owners",
        allow_empty=True,
    )
    if implementation_state == "implemented" and not xingwen_owners:
        raise ValueError(
            f"{capability_id} is implemented and must list xingwen_owners"
        )
    verification = _require_string_list(
        raw.get("verification", []),
        f"{capability_id}.verification",
        allow_empty=True,
    )
    for item in verification:
        if item not in ALLOWED_VERIFICATION:
            raise ValueError(f"{capability_id} has an unknown verification: {item}")
    if implementation_state == "implemented" and not verification:
        raise ValueError(
            f"{capability_id} is implemented and must list verification evidence"
        )
    if implementation_state == "implemented":
        if category == "function" and not (
            set(verification)
            & {"contract", "unit", "benchmark", "recorded", "live"}
        ):
            raise ValueError(
                f"{capability_id} is an implemented function capability and needs"
                " contract/unit/benchmark/recorded/live verification"
            )
        if category in ("presentation", "interaction") and not (
            set(verification) & {"component", "browser"}
        ):
            raise ValueError(
                f"{capability_id} is an implemented {category} capability and"
                " needs component or browser verification"
            )
    production_entrypoint = raw.get("production_entrypoint")
    if production_entrypoint is not None:
        if not isinstance(production_entrypoint, str) or not production_entrypoint.strip():
            raise ValueError(
                f"{capability_id}.production_entrypoint must be a non-empty"
                " repo-relative path when present"
            )
        production_entrypoint = production_entrypoint.strip()
    user_reachability = raw.get("user_reachability")
    if user_reachability not in ALLOWED_USER_REACHABILITY:
        raise ValueError(
            f"{capability_id} has an unknown user_reachability:"
            f" {user_reachability}"
        )
    live_state = raw.get("live_state")
    if live_state not in ALLOWED_LIVE_STATES:
        raise ValueError(f"{capability_id} has an unknown live_state: {live_state}")
    if implementation_state == "implemented":
        if not production_entrypoint:
            raise ValueError(
                f"{capability_id} is implemented and must declare a"
                " production_entrypoint"
            )
        if user_reachability == "unreachable":
            raise ValueError(
                f"{capability_id} is implemented but unreachable; mark it"
                " integration_pending instead of counting it as completed"
            )
        if category in ("presentation", "interaction") and user_reachability != "reachable":
            raise ValueError(
                f"{capability_id} is an implemented {category} capability and"
                " must be user-reachable"
            )
    notes = raw.get("notes", "")
    if not isinstance(notes, str):
        raise ValueError(f"{capability_id}.notes must be a string")
    return ReferenceCapability(
        reference=reference,
        category=category,
        capability_id=capability_id,
        reference_sources=reference_sources,
        disposition=disposition,
        implementation_state=implementation_state,
        eligible=eligible,
        exclusion_reason=exclusion_reason if not eligible else None,
        xingwen_owners=xingwen_owners,
        verification=verification,
        production_entrypoint=production_entrypoint,
        user_reachability=user_reachability,
        live_state=live_state,
        notes=notes,
    )


def validate_manifest_structure(
    capabilities: tuple[ReferenceCapability, ...],
) -> None:
    seen: set[str] = set()
    for item in capabilities:
        if item.capability_id in seen:
            raise ValueError(f"duplicate capability_id: {item.capability_id}")
        seen.add(item.capability_id)
    for reference in ALLOWED_REFERENCES:
        for category in ALLOWED_CATEGORIES:
            if not any(
                item.reference == reference and item.category == category
                for item in capabilities
            ):
                raise ValueError(
                    f"{reference}/{category} has no capabilities; each reference"
                    " must be scorable on all three axes"
                )


def load_manifest(path: Path) -> ReferenceCapabilityManifest:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("manifest must be a JSON object")
    if raw.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(
            f"manifest schema_version must be {SCHEMA_VERSION}"
        )
    raw_capabilities = raw.get("capabilities")
    if not isinstance(raw_capabilities, list) or not raw_capabilities:
        raise ValueError("manifest capabilities must be a non-empty array")
    capabilities = tuple(
        parse_capability(item, index=index)
        for index, item in enumerate(raw_capabilities)
    )
    validate_manifest_structure(capabilities)
    digests = raw.get("reference_snapshot_digests", {})
    if not isinstance(digests, dict) or set(digests) - set(ALLOWED_REFERENCES):
        raise ValueError("reference_snapshot_digests must map known references")
    return ReferenceCapabilityManifest(
        capabilities=capabilities,
        reference_snapshot_digests={
            key: str(value) for key, value in digests.items()
        },
    )


__all__ = [
    "ALLOWED_CATEGORIES",
    "ALLOWED_DISPOSITIONS",
    "ALLOWED_IMPLEMENTATION_STATES",
    "ALLOWED_LIVE_STATES",
    "ALLOWED_REFERENCES",
    "ALLOWED_USER_REACHABILITY",
    "ALLOWED_VERIFICATION",
    "ReferenceCapability",
    "ReferenceCapabilityManifest",
    "load_manifest",
    "parse_capability",
    "validate_manifest_structure",
]
