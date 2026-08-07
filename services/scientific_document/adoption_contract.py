"""Machine-validatable contract for the D-10 upstream adoption manifest.

``upstream_adoption.json`` is the single source of truth for which first-party
packages/models and Python import roots are approved for Scientific Document
Parsing. Production D-11 adapters may consume only ``approved`` entries.
Unknown keys are rejected so a typo cannot silently weaken the contract.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.core import CORE_MODEL_CONFIG, NonEmptyString


class AdoptionStatus(StrEnum):
    approved = "approved"
    evaluated_not_adopted = "evaluated_not_adopted"
    deferred = "deferred"
    blocked = "blocked"


_FLOATING_TOKENS = {"latest", "main", "master", "nightly", "dev", "head", "*"}
_VERSION_RANGE_CHARS = (">", "<", "~", "^", "!", "|")
_SHA40 = re.compile(r"^[0-9a-f]{40}$", re.IGNORECASE)
_ADOPTION_CONFIG = {**CORE_MODEL_CONFIG, "extra": "forbid"}


class AdoptionEntry(BaseModel):
    """One auditable upstream capability decision."""

    model_config = ConfigDict(**_ADOPTION_CONFIG)

    capability: NonEmptyString
    adoption_status: AdoptionStatus
    upstream_repository: NonEmptyString
    license: NonEmptyString
    official_interface_used: NonEmptyString
    explicitly_unused_scope: NonEmptyString
    cpu_behavior: NonEmptyString
    gpu_behavior: NonEmptyString
    network_behavior: NonEmptyString
    model_download_behavior: NonEmptyString
    cache_behavior: NonEmptyString
    offline_behavior: NonEmptyString
    known_risks: NonEmptyString
    upgrade_strategy: NonEmptyString
    evidence_source: NonEmptyString
    reviewed_by: NonEmptyString

    package: NonEmptyString | None = None
    package_extra: NonEmptyString | None = None
    package_version: NonEmptyString | None = None
    import_roots: tuple[NonEmptyString, ...] = ()
    release_tag: NonEmptyString | None = None
    release_date: NonEmptyString | None = None

    model_repository: NonEmptyString | None = None
    model_id: NonEmptyString | None = None
    model_resolved_id: NonEmptyString | None = None
    model_revision: NonEmptyString | None = None
    pipeline_version: NonEmptyString | None = None
    model_weight_license: NonEmptyString | None = None

    paddlepaddle_package: NonEmptyString | None = None
    paddlepaddle_version: NonEmptyString | None = None

    @model_validator(mode="after")
    def frozen_versions_only(self) -> Self:
        version_fields = {
            "package_version": self.package_version,
            "model_revision": self.model_revision,
            "pipeline_version": self.pipeline_version,
            "release_tag": self.release_tag,
            "paddlepaddle_version": self.paddlepaddle_version,
        }
        for field_name, value in version_fields.items():
            if value is None:
                continue
            lowered = value.strip().lower()
            if any(token in lowered for token in _FLOATING_TOKENS):
                raise ValueError(
                    f"floating version token forbidden in '{self.capability}'."
                    f"{field_name}: {value!r}"
                )
            if any(char in value for char in _VERSION_RANGE_CHARS):
                raise ValueError(
                    f"version range forbidden in '{self.capability}'."
                    f"{field_name}: {value!r} (pin exact version)"
                )

        if len(self.import_roots) != len(set(self.import_roots)):
            raise ValueError(f"duplicate import_roots in capability '{self.capability}'")
        for root in self.import_roots:
            if not root.replace("_", "").isalnum() or "." in root:
                raise ValueError(
                    f"import_root must be a top-level Python module name: {root!r}"
                )

        if self.adoption_status == AdoptionStatus.approved:
            if self.package is not None:
                if self.package_version is None:
                    raise ValueError(
                        f"approved package capability '{self.capability}' must pin package_version"
                    )
                if not self.import_roots:
                    raise ValueError(
                        f"approved package capability '{self.capability}' must declare import_roots"
                    )
            if self.model_repository is not None:
                if not self.model_id or not self.model_resolved_id:
                    raise ValueError(
                        f"approved model capability '{self.capability}' must declare "
                        "model_id and model_resolved_id"
                    )
                if not self.model_revision:
                    raise ValueError(
                        f"approved model capability '{self.capability}' must pin model_revision"
                    )
                if self.model_weight_license is None:
                    raise ValueError(
                        f"approved model capability '{self.capability}' must declare "
                        "model_weight_license"
                    )
                if "huggingface.co" in self.model_repository.lower() and not _SHA40.fullmatch(
                    self.model_revision
                ):
                    raise ValueError(
                        f"Hugging Face model capability '{self.capability}' must pin an "
                        "immutable 40-hex commit revision"
                    )
        return self


class UpstreamAdoptionManifest(BaseModel):
    """Top-level frozen adoption decision set."""

    model_config = ConfigDict(**_ADOPTION_CONFIG)

    manifest_id: NonEmptyString
    schema_version: NonEmptyString
    reviewed_at: NonEmptyString
    case_key: NonEmptyString
    allowed_statuses: tuple[AdoptionStatus, ...]
    consumable_statuses: tuple[AdoptionStatus, ...]
    entries: tuple[AdoptionEntry, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_manifest_policy(self) -> Self:
        capabilities = [entry.capability for entry in self.entries]
        if len(capabilities) != len(set(capabilities)):
            raise ValueError("adoption entries must have unique capabilities")
        if set(self.allowed_statuses) != set(AdoptionStatus):
            raise ValueError("allowed_statuses must enumerate every AdoptionStatus exactly")
        if self.consumable_statuses != (AdoptionStatus.approved,):
            raise ValueError("only adoption_status=approved may be consumable")
        return self


def load_adoption_manifest(path: object) -> UpstreamAdoptionManifest:
    """Load and validate the adoption manifest from a Path-like object."""
    import json
    from pathlib import Path

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return UpstreamAdoptionManifest.model_validate(data)


def collect_approved_packages(manifest: UpstreamAdoptionManifest) -> set[str]:
    """Return exact approved top-level Python import roots."""
    approved: set[str] = set()
    for entry in manifest.entries:
        if entry.adoption_status == AdoptionStatus.approved:
            approved.update(root.lower() for root in entry.import_roots)
    return approved


__all__ = [
    "AdoptionStatus",
    "AdoptionEntry",
    "UpstreamAdoptionManifest",
    "load_adoption_manifest",
    "collect_approved_packages",
]
