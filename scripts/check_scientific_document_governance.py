"""Scientific Document Parsing governance gate.

The gate is stdlib-only so Foundation CI can run before the API environment is
installed. It enforces mechanically checkable Scientific Document Parsing Contract rules; human review remains
required for intent-level checks such as reference-after-rewrite.
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADOPTION_MANIFEST = ROOT / "services" / "scientific_document" / "upstream_adoption.json"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PRODUCTION_PARSER_AREA = (
    "apps/api/src/app/services/scientific_document",
    "services/scientific_document",
)
CANONICAL_SCHEMA_MODULES = (
    "apps/api/src/app/schemas/scientific_document.py",
)
REFERENCE_PREFIX = "docs.references"

FLOATING_VERSION_TOKENS = {"latest", "main", "master", "nightly", "dev", "head", "*"}
RANGE_CHARS = (">", "<", "~", "^", "!", "|")
MODEL_WEIGHT_SUFFIXES = (
    ".bin",
    ".safetensors",
    ".gguf",
    ".onnx",
    ".pt",
    ".pth",
    ".ckpt",
    ".pb",
    ".h5",
    ".tflite",
)
VENDOR_IMPORT_ROOTS = {
    "docling_parse",
    "paddleocr",
    "paddlex",
    "paddle",
    "mineru",
    "grobid",
    "pp_structure",
}
VENDORED_PATH_SEGMENTS = {"vendor", "vendored", "third_party"}
VENDORED_MARKERS = {"__vendored__", "vendored_source"}


def tracked_files() -> list[str]:
    completed = subprocess.run(
        ["git", "ls-files", "-co", "--exclude-standard"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [line for line in completed.stdout.splitlines() if line]


def _normalized(relative: str) -> str:
    return relative.replace("\\", "/")


def _is_production_python(relative: str) -> bool:
    normalized = _normalized(relative)
    if not normalized.endswith(".py"):
        return False
    if "/tests/" in f"/{normalized}" or normalized.startswith("tests/"):
        return False
    return True


def _is_governance_config(relative: str) -> bool:
    return _normalized(relative).lower().endswith((".json", ".toml", ".yaml", ".yml"))


def _parse_python(relative: str) -> ast.AST | None:
    path = ROOT / _normalized(relative)
    try:
        return ast.parse(path.read_text(encoding="utf-8", errors="strict"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return None


def _imported_modules(tree: ast.AST) -> list[str]:
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return modules


def _import_root(module: str) -> str:
    return module.split(".", 1)[0]


def _load_adoption_json() -> dict:
    try:
        data = json.loads(ADOPTION_MANIFEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"cannot load Scientific Document Parsing Contract adoption manifest: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("entries"), list):
        raise RuntimeError("Scientific Document Parsing Contract adoption manifest must contain an entries array")
    return data


def approved_package_roots() -> set[str]:
    """Return explicit approved top-level Python import roots from the manifest."""
    try:
        data = _load_adoption_json()
    except RuntimeError:
        return set()
    roots: set[str] = set()
    for entry in data["entries"]:
        if entry.get("adoption_status") != "approved":
            continue
        for root in entry.get("import_roots", []):
            if isinstance(root, str) and root.strip():
                roots.add(root.strip().lower())
    return roots


def check_reference_imports(tracked: list[str]) -> list[str]:
    errors: list[str] = []
    for relative in tracked:
        if not _is_production_python(relative):
            continue
        normalized = _normalized(relative)
        if normalized.startswith("docs/references/"):
            continue
        tree = _parse_python(relative)
        if tree is None:
            continue
        for module in _imported_modules(tree):
            if module == REFERENCE_PREFIX or module.startswith(f"{REFERENCE_PREFIX}."):
                errors.append(f"production code imports docs.references: {normalized}")
                break
    return errors


def check_unapproved_parser_imports(tracked: list[str]) -> list[str]:
    approved = approved_package_roots()
    errors: list[str] = []
    for relative in tracked:
        if not _is_production_python(relative):
            continue
        normalized = _normalized(relative)
        if not normalized.startswith(PRODUCTION_PARSER_AREA):
            continue
        tree = _parse_python(relative)
        if tree is None:
            continue
        for module in _imported_modules(tree):
            root = _import_root(module).lower()
            if root not in VENDOR_IMPORT_ROOTS:
                continue
            if root not in approved:
                errors.append(
                    f"unapproved vendor import '{root}' in production parser area: "
                    f"{normalized} (must be declared in import_roots of an approved adoption entry)"
                )
    return errors


def check_floating_versions(tracked: list[str]) -> list[str]:
    errors: list[str] = []
    pattern = re.compile(
        r"(model_revision|pipeline_version|revision|version|package_version|release_tag)"
        r"\"?\s*[:=]\s*[\"']?\s*(latest|main|master|nightly|dev|head)\b",
        re.IGNORECASE,
    )
    for relative in tracked:
        normalized = _normalized(relative)
        if not _is_governance_config(normalized):
            continue
        if "scientific_document" not in normalized and "adoption" not in normalized:
            continue
        try:
            text = (ROOT / normalized).read_text(encoding="utf-8", errors="strict")
        except (OSError, UnicodeDecodeError):
            continue
        for match in pattern.finditer(text):
            errors.append(
                f"floating model/revision token in {normalized}: {match.group(0)!r}"
            )
    return errors


def check_exact_pinned_versions(tracked: list[str]) -> list[str]:
    errors: list[str] = []
    pattern = re.compile(
        r"(package_version|model_revision|pipeline_version|release_tag|paddlex_version|provisioning_version)"
        r"\"?\s*[:=]\s*[\"']([^\"']+)[\"']"
    )
    for relative in tracked:
        normalized = _normalized(relative)
        if not _is_governance_config(normalized):
            continue
        if "scientific_document" not in normalized and "adoption" not in normalized:
            continue
        try:
            text = (ROOT / normalized).read_text(encoding="utf-8", errors="strict")
        except (OSError, UnicodeDecodeError):
            continue
        for match in pattern.finditer(text):
            value = match.group(2).strip()
            lowered = value.lower()
            if any(token in lowered for token in FLOATING_VERSION_TOKENS):
                continue
            if any(char in value for char in RANGE_CHARS):
                errors.append(
                    f"version range not allowed in {normalized}: "
                    f"{match.group(1)}={value!r} (pin exact version)"
                )
    return errors


def check_adoption_manifest_integrity() -> list[str]:
    """Validate critical adoption invariants without third-party dependencies."""
    errors: list[str] = []
    try:
        data = _load_adoption_json()
    except RuntimeError as exc:
        return [str(exc)]

    if data.get("manifest_id") != "scientific_document-upstream-adoption":
        errors.append("adoption manifest_id must match the frozen manifest identity")
    if data.get("schema_version") != "4.0.0":
        errors.append("adoption schema_version must match the frozen manifest schema")
    if data.get("consumable_statuses") != ["approved"]:
        errors.append("upstream adoption manifest must allow only approved as consumable")

    capabilities: set[str] = set()
    approved_roots: set[str] = set()
    for index, entry in enumerate(data["entries"]):
        if not isinstance(entry, dict):
            errors.append(f"adoption entry #{index} must be an object")
            continue
        capability = str(entry.get("capability", "")).strip()
        if not capability:
            errors.append(f"adoption entry #{index} missing capability")
            continue
        if capability in capabilities:
            errors.append(f"duplicate adoption capability: {capability}")
        capabilities.add(capability)

        if entry.get("adoption_status") != "approved":
            continue

        package = entry.get("package")
        roots = entry.get("import_roots")
        if package:
            if not entry.get("package_version"):
                errors.append(f"approved capability {capability} missing package_version")
            if not isinstance(roots, list) or not roots:
                errors.append(f"approved capability {capability} missing import_roots")
            else:
                for root in roots:
                    if not isinstance(root, str) or not root.strip():
                        errors.append(f"approved capability {capability} has invalid import_root")
                        continue
                    normalized_root = root.strip().lower()
                    if normalized_root in approved_roots:
                        errors.append(f"approved import_root appears in multiple capabilities: {root}")
                    approved_roots.add(normalized_root)

        if entry.get("model_repository"):
            for field in ("model_id", "model_resolved_id", "model_revision", "model_weight_license"):
                if not entry.get(field):
                    errors.append(f"approved model capability {capability} missing {field}")

        for field in (
            "license",
            "official_interface_used",
            "explicitly_unused_scope",
            "cpu_behavior",
            "gpu_behavior",
            "network_behavior",
            "model_download_behavior",
            "cache_behavior",
            "offline_behavior",
            "known_risks",
            "upgrade_strategy",
            "evidence_source",
        ):
            if not entry.get(field):
                errors.append(f"approved capability {capability} missing {field}")

        if capability == "visual_ocr_layout_table_formula":
            required = {
                "paddlex_package": "paddlex",
                "paddlex_extras": ["genai-client", "ocr"],
                "runtime_backend": "native",
                "component_execution_policy": {
                    "use_layout_detection": True,
                    "use_doc_orientation_classify": False,
                    "use_doc_unwarping": False,
                    "use_chart_recognition": False,
                    "use_seal_recognition": False,
                    "use_ocr_for_image_block": False,
                },
                "runtime_directory_binding": "explicit",
                "runtime_network_policy": "disabled",
                "runtime_download_policy": "disabled",
            }
            for field, expected in required.items():
                if entry.get(field) != expected:
                    errors.append(
                        f"approved visual capability requires {field}={expected!r}"
                    )
            for field in (
                "paddlex_version",
                "provisioning_version",
                "model_asset_manifest",
                "model_asset_bundle_digest",
            ):
                if not entry.get(field):
                    errors.append(f"approved visual capability missing {field}")
            bindings = entry.get("component_directory_bindings")
            if not isinstance(bindings, dict) or not bindings:
                errors.append(
                    "approved visual capability requires non-empty "
                    "component_directory_bindings object"
                )
            else:
                for role, parameter in bindings.items():
                    if not isinstance(role, str) or not role.strip():
                        errors.append("component_directory_bindings key must be non-empty text")
                    if not isinstance(parameter, str) or not parameter.strip():
                        errors.append(
                            f"component_directory_bindings value for {role!r} must be "
                            "non-empty text"
                        )
                values = [
                    value for value in bindings.values() if isinstance(value, str)
                ]
                if len(set(values)) != len(values):
                    errors.append(
                        "component_directory_bindings must map each component to a "
                        "distinct vendor constructor parameter"
                    )
            if entry.get("model_revision") is not None:
                errors.append(
                    "visual pipeline identity must come from the asset manifest, "
                    "not a top-level model_revision"
                )
            profiles = entry.get("runtime_profiles")
            if not isinstance(profiles, list):
                errors.append("approved visual capability missing runtime_profiles")
            else:
                profile_ids = [
                    profile.get("profile_id")
                    for profile in profiles
                    if isinstance(profile, dict)
                ]
                if len(profile_ids) != len(set(profile_ids)):
                    errors.append("visual runtime profile ids must be unique")
                by_id = {
                    profile.get("profile_id"): profile
                    for profile in profiles
                    if isinstance(profile, dict)
                }
                cpu = by_id.get("cpu", {})
                gpu = by_id.get("gpu", {})
                if set(by_id) != {"cpu", "gpu"}:
                    errors.append("visual runtime profiles must be exactly cpu and gpu")
                if not any(profile.get("status") == "approved" for profile in (cpu, gpu)):
                    errors.append("approved visual capability requires a verified runtime")
                if (
                    cpu.get("distribution") != "paddlepaddle"
                    or cpu.get("device") != "cpu"
                ):
                    errors.append("visual CPU profile must use paddlepaddle on cpu")
                if (
                    gpu.get("distribution") != "paddlepaddle-gpu"
                    or gpu.get("device") != "gpu"
                ):
                    errors.append("visual GPU profile must use paddlepaddle-gpu on gpu")
                for profile in (cpu, gpu):
                    approved = profile.get("status") == "approved"
                    if (
                        profile.get("probe_evidence") != ("live" if approved else "not_run")
                        or profile.get("initialization_completed") is not approved
                        or profile.get("predict_executed") is not approved
                        or (
                            approved
                            and not all(
                                profile.get(field) for field in (
                                    "python_version", "fixture_id",
                                    "fixture_sha256", "result_boundary",
                                )
                            )
                        )
                    ):
                        errors.append(
                            f"visual {profile.get('profile_id')} status requires matching independent execution evidence"
                        )
                if cpu.get("version") != gpu.get("version"):
                    errors.append("visual CPU and GPU profiles must pin the same base version")
    return errors


_LOCAL_PATH_PATTERN = re.compile(
    r"(?:\b[A-Za-z]:[\\/]"
    r"|(?:^|[\s\"'(:=])/home/[a-z0-9_-]+/"
    r"|(?:^|[\s\"'(:=])/Users/[a-z0-9_-]+/"
    r"|(?:^|[\s\"'(:=])/mnt/[a-z0-9_-]+/)",
    re.IGNORECASE,
)


def check_local_path_leakage(tracked: list[str]) -> list[str]:
    """Reject absolute machine paths from scientific-document contracts/evidence."""
    errors: list[str] = []
    for relative in tracked:
        normalized = _normalized(relative)
        if "scientific_document" not in normalized and "adoption" not in normalized:
            continue
        if not normalized.lower().endswith((".py", ".json", ".md")):
            continue
        try:
            text = (ROOT / normalized).read_text(encoding="utf-8", errors="strict")
        except (OSError, UnicodeDecodeError):
            continue
        for match in _LOCAL_PATH_PATTERN.finditer(text):
            errors.append(f"machine-local path in scientific-document contract: {normalized}")
            break
    return errors


def check_model_weights(tracked: list[str]) -> list[str]:
    errors: list[str] = []
    for relative in tracked:
        normalized = _normalized(relative).lower()
        if normalized.endswith(MODEL_WEIGHT_SUFFIXES):
            errors.append(f"model weight file tracked in git: {relative}")
    return errors


def check_visual_asset_contract() -> list[str]:
    """Verify asset and runtime-profile identities using only stdlib code."""
    try:
        from services.scientific_document.model_asset_contract import load_asset_manifest
        from services.scientific_document.runtime_provenance import (
            compute_runtime_configuration_hash,
        )

        assets = load_asset_manifest()
        adoption = _load_adoption_json()
        visual = next(
            entry
            for entry in adoption["entries"]
            if entry.get("capability") == "visual_ocr_layout_table_formula"
        )
        if visual.get("model_asset_bundle_digest") != assets["bundle_digest"]:
            return ["visual adoption bundle digest does not match asset contract"]
        asset_roles = {component["role"] for component in assets["components"]}
        bindings = visual.get("component_directory_bindings") or {}
        if set(bindings) != asset_roles:
            return [
                "visual component_directory_bindings must cover exactly the asset "
                "component roles"
            ]
        for profile in visual.get("runtime_profiles", []):
            expected = compute_runtime_configuration_hash(
                assets,
                pipeline_version=str(visual.get("pipeline_version", "")),
                runtime_backend=str(visual.get("runtime_backend", "")),
                component_execution_policy=visual.get("component_execution_policy") or {},
                component_directory_bindings=bindings,
                directory_binding_policy=str(visual.get("runtime_directory_binding", "")),
                network_policy=str(visual.get("runtime_network_policy", "")),
                implicit_download_policy=str(visual.get("runtime_download_policy", "")),
                paddleocr_package=str(visual.get("package", "")),
                paddleocr_extra=str(visual.get("package_extra", "")),
                paddleocr_version=str(visual.get("package_version", "")),
                paddlex_package=str(visual.get("paddlex_package", "")),
                paddlex_extras=list(visual.get("paddlex_extras") or []),
                paddlex_version=str(visual.get("paddlex_version", "")),
                distribution=str(profile.get("distribution", "")),
                version=str(profile.get("version", "")),
                device=str(profile.get("device", "")),
            )
            if profile.get("configuration_hash") != expected:
                return [
                    f"visual {profile.get('profile_id')} configuration hash mismatch"
                ]
        golden_path = ADOPTION_MANIFEST.parent / "golden_set.json"
        try:
            golden = json.loads(golden_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            return [f"cannot load golden set manifest: {exc}"]
        golden_hashes = {
            str(item.get("entry_id")): item.get("content_hash")
            for item in golden.get("entries", [])
            if isinstance(item, dict)
        }
        for profile in visual.get("runtime_profiles", []):
            if not isinstance(profile, dict) or profile.get("status") != "approved":
                continue
            fixture_id = str(profile.get("fixture_id") or "")
            if not fixture_id:
                return [f"visual {profile.get('profile_id')} approved profile missing fixture_id"]
            if fixture_id not in golden_hashes:
                return [
                    f"visual {profile.get('profile_id')} live probe fixture must reference "
                    "a golden set entry"
                ]
            if golden_hashes[fixture_id] != profile.get("fixture_sha256"):
                return [
                    f"visual {profile.get('profile_id')} fixture_sha256 must equal the "
                    "golden set content hash of the committed fixture bytes"
                ]
    except (RuntimeError, StopIteration, ValueError) as exc:
        return [f"visual model asset contract invalid: {exc}"]
    return []


def check_canonical_vendor_leakage(tracked: list[str]) -> list[str]:
    errors: list[str] = []
    for relative in CANONICAL_SCHEMA_MODULES:
        tree = _parse_python(relative)
        if tree is None:
            continue
        for module in _imported_modules(tree):
            if _import_root(module).lower() in VENDOR_IMPORT_ROOTS:
                errors.append(
                    f"canonical schema imports vendor module: {relative}: {module}"
                )
    return errors


def check_unmanifested_vendored_source(tracked: list[str]) -> list[str]:
    """Scientific Document Parsing Contract currently permits no vendored parser source at all."""
    errors: list[str] = []
    for relative in tracked:
        normalized = _normalized(relative).lower()
        parts = set(Path(normalized).parts)
        if parts & VENDORED_PATH_SEGMENTS or any(marker in normalized for marker in VENDORED_MARKERS):
            errors.append(f"vendored parser source is not approved by Scientific Document Parsing Contract: {relative}")
    return errors


def main() -> int:
    tracked = tracked_files()
    errors: list[str] = []
    errors += check_reference_imports(tracked)
    errors += check_unapproved_parser_imports(tracked)
    errors += check_floating_versions(tracked)
    errors += check_exact_pinned_versions(tracked)
    errors += check_adoption_manifest_integrity()
    errors += check_local_path_leakage(tracked)
    errors += check_model_weights(tracked)
    errors += check_visual_asset_contract()
    errors += check_canonical_vendor_leakage(tracked)
    errors += check_unmanifested_vendored_source(tracked)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("Scientific Document Parsing Contract governance gate passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
