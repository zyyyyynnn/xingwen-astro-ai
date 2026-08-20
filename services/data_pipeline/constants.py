"""Frozen Product Case Baseline inputs and versioned data-acquisition rules."""

from __future__ import annotations

from pathlib import Path


FROZEN_CASE_MANIFEST_VERSION = "2.0.0"
FROZEN_CASE_MANIFEST_CONTENT_HASH = (
    "sha256:baa4d6c24ff46d25172074fd26c8c692c50e006e643dc7c72b4bc18c90be52bf"
)
FROZEN_FIELD_MANIFEST_VERSION = "2.0.0"
FROZEN_FIELD_MANIFEST_CONTENT_HASH = (
    "sha256:d74d01950e7171aacce8cf660582d5245a2fa84e8bf6948224695740cd3c334e"
)
_MANIFEST_ROOT = Path(__file__).resolve().parent / "manifests" / "exoplanet_host_star"
FROZEN_CASE_MANIFEST_PATH = _MANIFEST_ROOT / "case-manifest.json"
FROZEN_FIELD_MANIFEST_PATH = _MANIFEST_ROOT / "field-manifest.json"

PRODUCER_NAME = "xingwen.data_acquisition"
PRODUCER_VERSION = "1.0.0"
QUERY_NORMALIZATION_VERSION = "1.0.0"
RETRY_POLICY_VERSION = "1.0.0"
SOURCE_POLICY_VERSION = "1.0.0"
SOURCE_POLICY_CONTENT_HASH = (
    "sha256:4ab8fb8837160764f13d2c26d5ed48a67bcd944df020ffbe0a0f57e8b24d4fb1"
)
# Provider and source versions advance together when shared NASA TAP semantics change.
NASA_TAP_ADAPTER_VERSION = "1.1.0"
NASA_PS_SUPPLEMENTAL_ADAPTER_VERSION = "1.1.0"
SUPPLEMENTAL_QUERY_NORMALIZATION_VERSION = "1.1.0"
CROSSMATCH_PRODUCER_NAME = "xingwen.cross_source_alignment"
CROSSMATCH_PRODUCER_VERSION = "2.0.0"
