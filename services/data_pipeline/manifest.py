"""Load the pinned Case/Field Manifest pair."""

from __future__ import annotations

from pathlib import Path

from app.schemas.manifest import ManifestBundle, load_manifest_bundle

from .constants import (
    FROZEN_CASE_MANIFEST_CONTENT_HASH,
    FROZEN_CASE_MANIFEST_PATH,
    FROZEN_CASE_MANIFEST_VERSION,
    FROZEN_FIELD_MANIFEST_CONTENT_HASH,
    FROZEN_FIELD_MANIFEST_PATH,
    FROZEN_FIELD_MANIFEST_VERSION,
)


def load_frozen_manifest_bundle(
    case_manifest_path: Path = FROZEN_CASE_MANIFEST_PATH,
    field_manifest_path: Path = FROZEN_FIELD_MANIFEST_PATH,
) -> ManifestBundle:
    bundle = load_manifest_bundle(case_manifest_path, field_manifest_path)
    expected = {
        "case_manifest_version": FROZEN_CASE_MANIFEST_VERSION,
        "case_manifest_content_hash": FROZEN_CASE_MANIFEST_CONTENT_HASH,
        "field_manifest_version": FROZEN_FIELD_MANIFEST_VERSION,
        "field_manifest_content_hash": FROZEN_FIELD_MANIFEST_CONTENT_HASH,
    }
    actual = {
        "case_manifest_version": bundle.case_manifest.manifest_version,
        "case_manifest_content_hash": bundle.case_manifest.content_hash,
        "field_manifest_version": bundle.field_manifest.manifest_version,
        "field_manifest_content_hash": bundle.field_manifest.content_hash,
    }
    if actual != expected:
        raise ValueError(
            "Primary Source Acquisition manifest pin mismatch; dynamic or modified manifest input is forbidden"
        )
    return bundle
