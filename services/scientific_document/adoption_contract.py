"""Validation rules for the scientific-document upstream adoption manifest.

``upstream_adoption.json`` is the single source of truth for which upstream
packages and Python import roots are approved for Scientific Document Parsing.
Production parser code may consume only ``approved`` entries. Unknown keys are
rejected so a typo cannot silently weaken the contract.
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
ADOPTION_MANIFEST_ID = "scientific_document-upstream-adoption"
ADOPTION_SCHEMA_VERSION = "4.0.0"
_VISUAL_COMPONENT_EXECUTION_POLICY = {
    "use_layout_detection": True,
    "use_doc_orientation_classify": False,
    "use_doc_unwarping": False,
    "use_chart_recognition": False,
    "use_seal_recognition": False,
    "use_ocr_for_image_block": False,
}
_VISUAL_PADDLEX_EXTRAS = ("genai-client", "ocr")


class RuntimeProfile(BaseModel):
    """One exact, independently admitted Paddle runtime profile."""

    model_config = ConfigDict(**_ADOPTION_CONFIG)

    profile_id: NonEmptyString
    distribution: NonEmptyString
    version: NonEmptyString
    device: NonEmptyString
    status: AdoptionStatus
    probe_evidence: NonEmptyString
    configuration_hash: NonEmptyString
    python_version: NonEmptyString | None = None
    fixture_id: NonEmptyString | None = None
    fixture_sha256: NonEmptyString | None = None
    initialization_completed: bool = False
    predict_executed: bool = False
    result_boundary: NonEmptyString | None = None

    @model_validator(mode="after")
    def validate_profile_evidence(self) -> Self:
        if any(char in self.version for char in _VERSION_RANGE_CHARS):
            raise ValueError("runtime profile version must be exact")
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", self.configuration_hash):
            raise ValueError("runtime profile configuration_hash must be sha256")
        if self.status == AdoptionStatus.approved:
            if self.probe_evidence != "live":
                raise ValueError("approved runtime profile requires live evidence")
            required = (
                self.python_version,
                self.fixture_id,
                self.fixture_sha256,
                self.result_boundary,
            )
            if not all(required) or not self.initialization_completed or not self.predict_executed:
                raise ValueError("approved runtime profile requires complete live probe evidence")
            if not re.fullmatch(r"sha256:[0-9a-f]{64}", str(self.fixture_sha256)):
                raise ValueError("live probe fixture_sha256 must be sha256")
        elif self.probe_evidence != "not_run":
            raise ValueError("non-approved runtime profile must not claim execution evidence")
        return self


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

    paddlex_package: NonEmptyString | None = None
    paddlex_extras: tuple[NonEmptyString, ...] = ()
    paddlex_version: NonEmptyString | None = None

    runtime_backend: NonEmptyString | None = None
    component_execution_policy: dict[str, bool] | None = None
    component_directory_bindings: dict[NonEmptyString, NonEmptyString] | None = None
    model_asset_manifest: NonEmptyString | None = None
    model_asset_bundle_digest: NonEmptyString | None = None
    runtime_directory_binding: NonEmptyString | None = None
    runtime_network_policy: NonEmptyString | None = None
    runtime_download_policy: NonEmptyString | None = None
    provisioning_package: NonEmptyString | None = None
    provisioning_version: NonEmptyString | None = None
    runtime_profiles: tuple[RuntimeProfile, ...] = ()

    @model_validator(mode="after")
    def frozen_versions_only(self) -> Self:
        version_fields = {
            "package_version": self.package_version,
            "model_revision": self.model_revision,
            "pipeline_version": self.pipeline_version,
            "release_tag": self.release_tag,
            "paddlex_version": self.paddlex_version,
            "provisioning_version": self.provisioning_version,
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

            if self.capability == "visual_ocr_layout_table_formula":
                required_visual = {
                    "paddlex_package": self.paddlex_package,
                    "paddlex_extras": self.paddlex_extras,
                    "paddlex_version": self.paddlex_version,
                    "runtime_backend": self.runtime_backend,
                    "component_execution_policy": self.component_execution_policy,
                    "component_directory_bindings": self.component_directory_bindings,
                    "model_asset_manifest": self.model_asset_manifest,
                    "model_asset_bundle_digest": self.model_asset_bundle_digest,
                    "runtime_directory_binding": self.runtime_directory_binding,
                    "runtime_network_policy": self.runtime_network_policy,
                    "runtime_download_policy": self.runtime_download_policy,
                    "provisioning_package": self.provisioning_package,
                    "provisioning_version": self.provisioning_version,
                    "runtime_profiles": self.runtime_profiles,
                }
                missing = sorted(name for name, value in required_visual.items() if not value)
                if missing:
                    raise ValueError(
                        "approved visual capability requires complete asset/runtime identity: "
                        f"{missing}"
                    )
                if self.model_revision is not None:
                    raise ValueError(
                        "visual pipeline identity must come from the complete asset manifest, "
                        "not a single top-level model_revision"
                    )
                if self.model_weight_license is not None:
                    raise ValueError(
                        "visual model license provenance belongs to the asset manifest"
                    )
                if self.paddlex_package != "paddlex":
                    raise ValueError("approved visual capability must pin the paddlex package")
                if self.paddlex_extras != _VISUAL_PADDLEX_EXTRAS:
                    raise ValueError(
                        "approved visual capability must pin the exact paddlex extras "
                        "required by paddleocr[doc-parser]"
                    )
                if self.runtime_backend != "native":
                    raise ValueError("approved visual capability must pin runtime_backend=native")
                if self.component_execution_policy != _VISUAL_COMPONENT_EXECUTION_POLICY:
                    raise ValueError(
                        "approved visual capability must pin the approved minimum "
                        "component execution policy"
                    )
                bindings = self.component_directory_bindings or {}
                if len(set(bindings.values())) != len(bindings):
                    raise ValueError(
                        "visual component_directory_bindings must map each component "
                        "to a distinct vendor constructor parameter"
                    )
                if (
                    self.runtime_directory_binding != "explicit"
                    or self.runtime_network_policy != "disabled"
                    or self.runtime_download_policy != "disabled"
                ):
                    raise ValueError(
                        "approved visual capability must require explicit local directories "
                        "with runtime network/download disabled"
                    )
                profile_ids = [profile.profile_id for profile in self.runtime_profiles]
                if len(profile_ids) != len(set(profile_ids)):
                    raise ValueError("runtime profile ids must be unique")
                if len(profile_ids) != 2 or set(profile_ids) != {"cpu", "gpu"}:
                    raise ValueError("visual capability requires exactly cpu and gpu profiles")
                profiles = {profile.profile_id: profile for profile in self.runtime_profiles}
                cpu = profiles["cpu"]
                gpu = profiles["gpu"]
                if (
                    cpu.distribution != "paddlepaddle"
                    or cpu.device != "cpu"
                    or cpu.status != AdoptionStatus.approved
                    or cpu.probe_evidence != "live"
                ):
                    raise ValueError("visual CPU profile must be approved paddlepaddle live")
                if (
                    gpu.distribution != "paddlepaddle-gpu"
                    or gpu.device != "gpu"
                    or gpu.status != AdoptionStatus.deferred
                    or gpu.probe_evidence != "not_run"
                ):
                    raise ValueError("visual GPU profile must remain deferred and not_run")
                if cpu.version != gpu.version:
                    raise ValueError("visual CPU and GPU profiles must pin the same base version")

        return self


class UpstreamAdoptionManifest(BaseModel):
    """Top-level frozen adoption decision set."""

    model_config = ConfigDict(**_ADOPTION_CONFIG)

    manifest_id: NonEmptyString
    schema_version: NonEmptyString
    case_key: NonEmptyString
    allowed_statuses: tuple[AdoptionStatus, ...]
    consumable_statuses: tuple[AdoptionStatus, ...]
    entries: tuple[AdoptionEntry, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_manifest_policy(self) -> Self:
        if self.manifest_id != ADOPTION_MANIFEST_ID:
            raise ValueError("manifest_id must match the frozen adoption manifest identity")
        if self.schema_version != ADOPTION_SCHEMA_VERSION:
            raise ValueError("schema_version must match the frozen adoption manifest schema")
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

    manifest_path = Path(path)
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest = UpstreamAdoptionManifest.model_validate(data)
    for entry in manifest.entries:
        if (
            entry.capability != "visual_ocr_layout_table_formula"
            or entry.adoption_status != AdoptionStatus.approved
        ):
            continue
        from services.scientific_document.model_asset_contract import load_asset_manifest
        from services.scientific_document.runtime_provenance import (
            compute_runtime_configuration_hash,
        )

        asset_path = manifest_path.parent / str(entry.model_asset_manifest)
        assets = load_asset_manifest(asset_path)
        if assets["bundle_digest"] != entry.model_asset_bundle_digest:
            raise ValueError("visual adoption bundle digest does not match asset manifest")
        asset_roles = {component["role"] for component in assets["components"]}
        bindings = dict(entry.component_directory_bindings or {})
        if set(bindings) != asset_roles:
            raise ValueError(
                "visual component_directory_bindings must cover exactly the asset "
                "component roles"
            )
        for profile in entry.runtime_profiles:
            expected = compute_runtime_configuration_hash(
                assets,
                pipeline_version=str(entry.pipeline_version),
                runtime_backend=str(entry.runtime_backend),
                component_execution_policy=dict(entry.component_execution_policy or {}),
                component_directory_bindings=bindings,
                directory_binding_policy=str(entry.runtime_directory_binding),
                network_policy=str(entry.runtime_network_policy),
                implicit_download_policy=str(entry.runtime_download_policy),
                paddleocr_package=str(entry.package),
                paddleocr_extra=str(entry.package_extra),
                paddleocr_version=str(entry.package_version),
                paddlex_package=str(entry.paddlex_package),
                paddlex_extras=list(entry.paddlex_extras),
                paddlex_version=str(entry.paddlex_version),
                distribution=profile.distribution,
                version=profile.version,
                device=profile.device,
            )
            if profile.configuration_hash != expected:
                raise ValueError(
                    f"visual {profile.profile_id} configuration hash does not match asset identity"
                )
        golden_path = manifest_path.parent / "golden_set.json"
        golden = json.loads(golden_path.read_text(encoding="utf-8"))
        golden_hashes = {
            str(item.get("entry_id")): item.get("content_hash")
            for item in golden.get("entries", [])
            if isinstance(item, dict)
        }
        for profile in entry.runtime_profiles:
            if profile.status != AdoptionStatus.approved or not profile.fixture_id:
                continue
            fixture_id = str(profile.fixture_id)
            if fixture_id not in golden_hashes:
                raise ValueError(
                    f"visual {profile.profile_id} live probe fixture must reference a "
                    "golden set entry"
                )
            if golden_hashes[fixture_id] != profile.fixture_sha256:
                raise ValueError(
                    f"visual {profile.profile_id} fixture_sha256 must equal the golden "
                    "set content hash of the committed fixture bytes"
                )
    return manifest


def collect_approved_packages(manifest: UpstreamAdoptionManifest) -> set[str]:
    """Return exact approved top-level Python import roots."""
    approved: set[str] = set()
    for entry in manifest.entries:
        if entry.adoption_status == AdoptionStatus.approved:
            approved.update(root.lower() for root in entry.import_roots)
    return approved


__all__ = [
    "AdoptionStatus",
    "RuntimeProfile",
    "AdoptionEntry",
    "UpstreamAdoptionManifest",
    "load_adoption_manifest",
    "collect_approved_packages",
]
