"""D-10 Scientific Document Parsing governance gate.

The gate is intentionally stdlib-only so Foundation CI can run it before the
API environment is installed. It enforces the mechanically checkable part of
D-10 governance; the human review checklist remains authoritative for intent
such as reference-after-rewrite.
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
        raise RuntimeError(f"cannot load D-10 adoption manifest: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("entries"), list):
        raise RuntimeError("D-10 adoption manifest must contain an entries array")
    return data


def approved_package_roots() -> set[str]:
    """Return import roots for approved package distributions only."""
    try:
        data = _load_adoption_json()
    except RuntimeError:
        return set()
    roots: set[str] = set()
    for entry in data["entries"]:
        if entry.get("adoption_status") != "approved":
            continue
        package = entry.get("package")
        if isinstance(package, str) and package.strip():
            roots.add(package.strip().lower().replace("-", "_"))
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
                    f"{normalized} (must map to adoption_status=approved)"
                )
    return errors


def check_floating_versions(tracked: list[str]) -> list[str]:
    """Detect obvious floating version tokens in D-10 config files."""
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
    """Approved D-10 package/model version-bearing config must be exact."""
    errors: list[str] = []
    pattern = re.compile(
        r"(package_version|model_revision|pipeline_version|release_tag|paddlepaddle_version)"
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
    """Validate critical manifest invariants without third-party dependencies."""
    errors: list[str] = []
    try:
        data = _load_adoption_json()
    except RuntimeError as exc:
        return [str(exc)]

    capabilities: set[str] = set()
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
        if package and not entry.get("package_version"):
            errors.append(f"approved capability {capability} missing package_version")
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
    return errors


def check_model_weights(tracked: list[str]) -> list[str]:
    errors: list[str] = []
    for relative in tracked:
        normalized = _normalized(relative).lower()
        if normalized.endswith(MODEL_WEIGHT_SUFFIXES):
            errors.append(f"model weight file tracked in git: {relative}")
    return errors


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
    """D-10 currently permits no vendored parser source at all."""
    errors: list[str] = []
    for relative in tracked:
        normalized = _normalized(relative).lower()
        parts = set(Path(normalized).parts)
        if parts & VENDORED_PATH_SEGMENTS or any(marker in normalized for marker in VENDORED_MARKERS):
            errors.append(f"vendored parser source is not approved by D-10: {relative}")
    return errors


def main() -> int:
    tracked = tracked_files()
    errors: list[str] = []
    errors += check_reference_imports(tracked)
    errors += check_unapproved_parser_imports(tracked)
    errors += check_floating_versions(tracked)
    errors += check_exact_pinned_versions(tracked)
    errors += check_adoption_manifest_integrity()
    errors += check_model_weights(tracked)
    errors += check_canonical_vendor_leakage(tracked)
    errors += check_unmanifested_vendored_source(tracked)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("D-10 governance gate passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
