"""Content-addressed contract for Scientific Document visual model assets.

This module is intentionally stdlib-only.  It validates the committed asset
identity and verifies operator-provided model directories before any vendor
runtime is imported or initialized.  Model bytes are represented by exact
file size/SHA-256 digests in the logical asset identity; local directory
names and machine paths are not part of that identity.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path, PurePosixPath
from typing import Any, Mapping


ASSET_MANIFEST_NAME = "visual_model_assets.json"
ASSET_MANIFEST_PATH = Path(__file__).with_name(ASSET_MANIFEST_NAME)
ASSET_MANIFEST_ID = "scientific_document-visual-model-assets"
ASSET_SCHEMA_VERSION = "3.0.0"
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_REQUIRED_ROLES = {"layout_detection", "vlm_recognition"}


class ModelAssetContractError(ValueError):
    """Fail-closed model asset validation error with a stable code."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(f"[{code}] {detail}")


def _fail(code: str, detail: str) -> None:
    raise ModelAssetContractError(code, detail)


def canonical_hash(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _require_object(value: object, where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail("model_asset_manifest_invalid", f"{where} must be an object")
    return value


def _require_text(value: object, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("model_asset_manifest_invalid", f"{where} must be non-empty text")
    return value


def _require_digest(value: object, where: str) -> str:
    text = _require_text(value, where)
    if not _SHA256.fullmatch(text):
        _fail("model_asset_manifest_invalid", f"{where} must be a sha256 digest")
    return text


def normalize_asset_path(value: object) -> str:
    """Return one safe, portable relative asset path or fail closed."""
    text = _require_text(value, "asset file path")
    if "\\" in text or text.startswith("/") or re.match(r"^[A-Za-z]:", text):
        _fail("model_asset_path_invalid", f"non-portable asset path: {text!r}")
    pure = PurePosixPath(text)
    if any(part in {"", ".", ".."} for part in pure.parts) or pure.as_posix() != text:
        _fail("model_asset_path_invalid", f"unsafe asset path: {text!r}")
    return text


def compute_component_asset_digest(files: object) -> str:
    """Hash a normalized, path-sorted file manifest."""
    if not isinstance(files, list) or not files:
        _fail("model_asset_manifest_invalid", "component files must be a non-empty array")
    normalized: list[dict[str, object]] = []
    seen: set[str] = set()
    for index, raw_file in enumerate(files):
        item = _require_object(raw_file, f"files[{index}]")
        if set(item) != {"path", "size", "sha256"}:
            _fail(
                "model_asset_manifest_invalid",
                f"files[{index}] must contain only path, size and sha256",
            )
        path = normalize_asset_path(item.get("path"))
        if path in seen:
            _fail("model_asset_duplicate_path", f"duplicate asset path: {path}")
        seen.add(path)
        size = item.get("size")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            _fail("model_asset_manifest_invalid", f"invalid size for {path}")
        digest = _require_digest(item.get("sha256"), f"sha256 for {path}")
        normalized.append({"path": path, "size": size, "sha256": digest})
    normalized.sort(key=lambda item: str(item["path"]))
    return canonical_hash({"files": normalized})


def _bundle_payload(data: Mapping[str, Any]) -> dict[str, object]:
    components = []
    for component in data["components"]:
        components.append(
            {
                "role": component["role"],
                "model_id": component["model_id"],
                "resolved_model_id": component["resolved_model_id"],
                "official_source": component["official_source"],
                "revision": component.get("revision"),
                "asset_digest": component["asset_digest"],
            }
        )
    components.sort(key=lambda item: str(item["role"]))
    return {"components": components}


def compute_bundle_digest(data: Mapping[str, Any]) -> str:
    """Hash the immutable component graph, source, revision and file identity.

    Manifest format metadata (manifest_id, schema_version) is deliberately
    excluded: renaming the manifest or bumping its schema version never
    changes the content-addressed model bundle identity.
    """
    return canonical_hash(_bundle_payload(data))


def validate_asset_manifest(data: object) -> dict[str, Any]:
    """Strictly validate the complete visual model asset manifest.

    This manifest owns only the immutable model asset identity: the component
    graph, official source, revision, license, exact file inventory and bundle
    digest. Pipeline/runtime policy and package identity are owned by
    ``upstream_adoption.json``.
    """
    manifest = _require_object(data, "visual model asset manifest")
    expected_keys = {
        "manifest_id",
        "schema_version",
        "components",
        "bundle_digest",
    }
    if set(manifest) != expected_keys:
        _fail("model_asset_manifest_invalid", "unexpected or missing top-level fields")
    if manifest["manifest_id"] != ASSET_MANIFEST_ID:
        _fail(
            "model_asset_manifest_invalid",
            "manifest_id must match the frozen asset manifest identity",
        )
    if manifest["schema_version"] != ASSET_SCHEMA_VERSION:
        _fail(
            "model_asset_manifest_invalid",
            "schema_version must match the frozen asset manifest schema",
        )

    raw_components = manifest["components"]
    if not isinstance(raw_components, list) or not raw_components:
        _fail("model_asset_manifest_invalid", "components must be a non-empty array")
    roles: set[str] = set()
    for index, raw_component in enumerate(raw_components):
        component = _require_object(raw_component, f"components[{index}]")
        required = {
            "role",
            "model_id",
            "resolved_model_id",
            "official_source",
            "revision",
            "license",
            "files",
            "asset_digest",
        }
        if set(component) != required:
            _fail("model_asset_manifest_invalid", f"invalid component fields at index {index}")
        role = _require_text(component["role"], f"components[{index}].role")
        if role in roles:
            _fail("model_asset_duplicate_role", f"duplicate component role: {role}")
        roles.add(role)
        _require_text(component["model_id"], f"components[{index}].model_id")
        _require_text(
            component["resolved_model_id"],
            f"components[{index}].resolved_model_id",
        )
        _require_text(component["license"], f"components[{index}].license")
        source = _require_object(component["official_source"], "official_source")
        if role == "vlm_recognition":
            if set(source) != {"type", "repo_id"}:
                _fail(
                    "model_asset_source_invalid",
                    "VLM official_source must contain exactly type and repo_id",
                )
            if source["type"] != "hugging_face_snapshot":
                _fail("model_asset_source_invalid", "VLM must use a Hugging Face snapshot")
            repo_id = _require_text(source["repo_id"], "vlm official_source.repo_id")
            if repo_id != component["model_id"]:
                _fail(
                    "model_asset_source_identity_mismatch",
                    "VLM official_source.repo_id must equal the component model_id",
                )
            revision = component.get("revision")
            if not isinstance(revision, str) or not _SHA40.fullmatch(revision):
                _fail("model_asset_revision_invalid", "VLM revision must be a full 40-hex SHA")
        else:
            if set(source) != {"type", "model_name", "resolved_url"}:
                _fail(
                    "model_asset_source_invalid",
                    "layout official_source must contain exactly type, model_name "
                    "and resolved_url",
                )
            if source["type"] != "paddlex_bos" or component.get("revision") is not None:
                _fail("model_asset_source_invalid", "layout must use the revisionless PaddleX BOS source")
            model_name = _require_text(
                source["model_name"], "layout official_source.model_name"
            )
            _require_text(source["resolved_url"], "layout official_source.resolved_url")
            if (
                model_name != component["model_id"]
                or model_name != component["resolved_model_id"]
            ):
                _fail(
                    "model_asset_source_identity_mismatch",
                    "layout official_source.model_name must equal the component "
                    "model identity",
                )
        expected_digest = compute_component_asset_digest(component["files"])
        if component["asset_digest"] != expected_digest:
            _fail("model_asset_digest_mismatch", f"component digest mismatch: {role}")
    if roles != _REQUIRED_ROLES:
        _fail("model_asset_component_graph_incomplete", "layout and VLM components are required")
    expected_bundle = compute_bundle_digest(manifest)
    if manifest["bundle_digest"] != expected_bundle:
        _fail("model_asset_bundle_mismatch", "bundle digest does not match manifest identity")
    return manifest


def load_asset_manifest(path: Path = ASSET_MANIFEST_PATH) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        _fail("model_asset_manifest_unreadable", type(exc).__name__)
    return validate_asset_manifest(data)


def _stream_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            hasher.update(chunk)
    return "sha256:" + hasher.hexdigest()


def verify_component_directory(component: Mapping[str, Any], root: Path) -> None:
    """Verify one exact local model directory before vendor initialization."""
    if not root.is_absolute():
        _fail("model_asset_directory_invalid", "runtime model directory must be absolute")
    if not root.is_dir() or root.is_symlink():
        _fail("model_asset_directory_invalid", "runtime model directory must be a real directory")
    resolved_root = root.resolve(strict=True)
    expected = {item["path"]: item for item in component["files"]}
    actual: dict[str, Path] = {}
    for current, directories, filenames in os.walk(root, followlinks=False):
        current_path = Path(current)
        for directory in directories:
            child = current_path / directory
            if child.is_symlink():
                _fail("model_asset_symlink_forbidden", "symlink directory in model bundle")
        for filename in filenames:
            child = current_path / filename
            relative = child.relative_to(root).as_posix()
            normalize_asset_path(relative)
            if child.is_symlink() or not child.is_file():
                _fail("model_asset_symlink_forbidden", f"non-regular asset: {relative}")
            try:
                child.resolve(strict=True).relative_to(resolved_root)
            except ValueError:
                _fail("model_asset_path_escape", f"asset escapes bundle root: {relative}")
            actual[relative] = child
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    if missing:
        _fail("model_asset_file_missing", f"missing asset: {missing[0]}")
    if extra:
        _fail("model_asset_file_unexpected", f"unexpected asset: {extra[0]}")
    for relative in sorted(expected):
        path = actual[relative]
        record = expected[relative]
        stat = path.stat()
        if stat.st_size != record["size"]:
            _fail("model_asset_size_mismatch", f"size mismatch: {relative}")
        digest = _stream_sha256(path)
        if digest != record["sha256"]:
            _fail("model_asset_hash_mismatch", f"hash mismatch: {relative}")


def verify_model_bundle(
    manifest: Mapping[str, Any], component_directories: Mapping[str, Path]
) -> str:
    """Verify every component's exact local directory and return bundle identity.

    ``component_directories`` maps the canonical component role to the
    operator-provided directory holding that component's bytes. Vendor
    constructor parameter names are runtime/adapter semantics owned by the
    adoption manifest and never appear here.
    """
    validated = validate_asset_manifest(dict(manifest))
    expected_roles = {component["role"] for component in validated["components"]}
    if set(component_directories) != expected_roles:
        _fail(
            "model_asset_directory_binding_missing",
            "all and only enabled component roles must have explicit directories",
        )
    for component in validated["components"]:
        verify_component_directory(component, Path(component_directories[component["role"]]))
    return validated["bundle_digest"]


__all__ = [
    "ASSET_MANIFEST_ID",
    "ASSET_MANIFEST_NAME",
    "ASSET_MANIFEST_PATH",
    "ASSET_SCHEMA_VERSION",
    "ModelAssetContractError",
    "canonical_hash",
    "compute_bundle_digest",
    "compute_component_asset_digest",
    "load_asset_manifest",
    "normalize_asset_path",
    "validate_asset_manifest",
    "verify_component_directory",
    "verify_model_bundle",
]
