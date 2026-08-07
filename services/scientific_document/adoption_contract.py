"""Machine-validatable contract for the D-10 upstream adoption manifest.

The manifest (``upstream_adoption.json``) is the single source of truth for
which first-party packages/models are approved for the D-10 Scientific Document
Parsing boundary. Production adapters (D-11) may consume ONLY entries whose
``adoption_status`` is ``approved``. This module enforces the manifest shape and
the D-10 freezing rules (exact versions, immutable model revision, explicit
licenses) so drift fails closed.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.core import CORE_MODEL_CONFIG, NonEmptyString


class AdoptionStatus(StrEnum):
    approved = "approved"
    evaluated_not_adopted = "evaluated_not_adopted"
    deferred = "deferred"
    blocked = "blocked"


_FLOATING_TOKENS = {"latest", "main", "master", "nightly", "dev", "head", "*"}

_VERSION_RANGE_CHARS = (">", "<", "~", "^", "!", "|")


_ADOPTION_CONFIG = {**CORE_MODEL_CONFIG, "extra": "allow"}


class AdoptionEntry(BaseModel):
    model_config = ConfigDict(**_ADOPTION_CONFIG)

    capability: NonEmptyString
    adoption_status: AdoptionStatus
    upstream_repository: NonEmptyString
    license: NonEmptyString
    official_interface_used: NonEmptyString
    upgrade_strategy: NonEmptyString
    network_behavior: NonEmptyString
    cache_behavior: NonEmptyString
    evidence_source: NonEmptyString
    reviewed_by: NonEmptyString

    package: NonEmptyString | None = None
    package_version: NonEmptyString | None = None
    release_tag: NonEmptyString | None = None
    model_repository: NonEmptyString | None = None
    model_id: NonEmptyString | None = None
    model_resolved_id: NonEmptyString | None = None
    model_revision: NonEmptyString | None = None
    pipeline_version: NonEmptyString | None = None
    model_weight_license: NonEmptyString | None = None

    @model_validator(mode="after")
    def frozen_versions_only(self) -> Self:
        # Any version-bearing field must be EXACT (no ranges, no floating token).
        version_fields = [
            self.package_version,
            self.model_revision,
            self.pipeline_version,
            self.release_tag,
        ]
        for value in version_fields:
            if value is None:
                continue
            lowered = value.strip().lower()
            if any(tok in lowered for tok in _FLOATING_TOKENS):
                raise ValueError(
                    f"floating version token forbidden in adoption entry "
                    f"'{self.capability}': {value!r}"
                )
            if any(ch in value for ch in _VERSION_RANGE_CHARS):
                raise ValueError(
                    f"version range forbidden in adoption entry "
                    f"'{self.capability}': {value!r} (pin exact version)"
                )
        # A model capability MUST pin an immutable model revision.
        if self.model_repository is not None:
            if not self.model_revision:
                raise ValueError(
                    f"model capability '{self.capability}' must pin model_revision"
                )
            if self.model_weight_license is None:
                raise ValueError(
                    f"model capability '{self.capability}' must declare model_weight_license"
                )
        return self


class UpstreamAdoptionManifest(BaseModel):
    model_config = ConfigDict(**_ADOPTION_CONFIG)

    manifest_id: NonEmptyString
    schema_version: NonEmptyString
    case_key: NonEmptyString
    entries: tuple[AdoptionEntry, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_capabilities(self) -> Self:
        caps = [e.capability for e in self.entries]
        if len(caps) != len(set(caps)):
            raise ValueError("adoption entries must have unique capabilities")
        return self


def load_adoption_manifest(path: object) -> UpstreamAdoptionManifest:
    """Load and validate the adoption manifest from a ``Path``-like object."""
    import json
    from pathlib import Path

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return UpstreamAdoptionManifest.model_validate(data)


def collect_approved_packages(manifest: UpstreamAdoptionManifest) -> set[str]:
    """Return lower-cased approved import roots (package + model id).

    Only ``approved`` entries contribute. A production adapter's import is
    permitted only when its package/model id is in this set AND carries an exact
    pinned version (enforced separately by ``check_d10_governance``).
    """
    approved: set[str] = set()
    for entry in manifest.entries:
        if entry.adoption_status != AdoptionStatus.approved:
            continue
        if entry.package:
            approved.add(entry.package.lower())
        if entry.model_id:
            approved.add(entry.model_id.lower())
        if entry.model_resolved_id:
            approved.add(entry.model_resolved_id.lower())
    return approved


__all__ = [
    "AdoptionStatus",
    "AdoptionEntry",
    "UpstreamAdoptionManifest",
    "load_adoption_manifest",
    "collect_approved_packages",
]
