"""Composition authority for visual runtime profile configuration identity.

This module is the single composition point for the runtime configuration
hash. It binds every frozen fact that changes execution semantics:

- the immutable model asset bundle digest (asset identity layer);
- the adoption-owned pipeline version, runtime backend, component execution
  policy, component directory bindings and directory/network/implicit-
  download policies;
- the exact adopted parser package identity (``paddleocr`` package/extra/
  version and ``paddlex`` package/extras/version);
- the exact Paddle distribution/version/device of one runtime profile.

The configuration hash covers the frozen execution configuration only. Asset
identity and runtime configuration identity are separate layers: the bundle
digest never changes because a runtime policy, device or parser package
changes, while any such change produces a new configuration hash. The Python
version belongs to ``RuntimeProfile`` live probe evidence and is intentionally
excluded until it becomes a frozen runtime contract. Local model directories,
cache paths, usernames, hostnames, timestamps and review metadata are runtime
bindings or process state and never part of this identity.

Stdlib-only so the Foundation governance gate can verify it without the API
environment.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from services.scientific_document.model_asset_contract import (
    canonical_hash,
    validate_asset_manifest,
)


def compute_runtime_configuration_hash(
    asset_manifest: Mapping[str, Any],
    *,
    pipeline_version: str,
    runtime_backend: str,
    component_execution_policy: Mapping[str, bool],
    component_directory_bindings: Mapping[str, str],
    directory_binding_policy: str,
    network_policy: str,
    implicit_download_policy: str,
    paddleocr_package: str,
    paddleocr_extra: str,
    paddleocr_version: str,
    paddlex_package: str,
    paddlex_extras: Sequence[str],
    paddlex_version: str,
    distribution: str,
    version: str,
    device: str,
) -> str:
    """Compose the path-independent configuration identity for one runtime profile."""
    manifest = validate_asset_manifest(dict(asset_manifest))
    return canonical_hash(
        {
            "bundle_digest": manifest["bundle_digest"],
            "pipeline_version": pipeline_version,
            "runtime_backend": runtime_backend,
            "component_execution_policy": dict(component_execution_policy),
            "component_directory_bindings": dict(
                sorted(component_directory_bindings.items())
            ),
            "runtime_policy": {
                "directory_binding": directory_binding_policy,
                "network": network_policy,
                "implicit_download": implicit_download_policy,
            },
            "paddleocr": {
                "package": paddleocr_package,
                "extra": paddleocr_extra,
                "version": paddleocr_version,
            },
            "paddlex": {
                "package": paddlex_package,
                "extras": sorted(paddlex_extras),
                "version": paddlex_version,
            },
            "paddle_runtime": {
                "distribution": distribution,
                "version": version,
                "device": device,
            },
        }
    )


__all__ = ["compute_runtime_configuration_hash"]
