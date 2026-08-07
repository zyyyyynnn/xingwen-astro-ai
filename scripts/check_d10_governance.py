"""D-10 scientific-document-parsing governance gate (machine-enforced).

Extends the repository foundation checks with the D-10 adoption boundary. It is
a SEPARATE scanner (not a fork of ``check_foundation.py``) so the D-10 gate can
evolve independently. It machine-detects the prohibited patterns from D-10 #34:

- production code importing ``docs/references`` (reference-after-rewrite source)
- unapproved parser/vendor packages imported in the production parser area
- floating / range model versions for APPROVED packages (``latest`` / ``main`` /
  ``master`` / ``nightly`` / ``dev`` / ``HEAD`` / ``>=`` / ``<`` / ``~`` / ``^``)
- model weight files tracked in git
- canonical schema modules importing/depending on vendor types
- unmanifested vendored third-party source files

Scanning uses the ``ast`` module for import detection (robust against comments,
docstrings and string literals) and applies the manifest-driven approved-package
allowlist. The adoption manifest is also validated with its Pydantic contract so
the gate's OWN data cannot drift.
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Production parser area: where a D-11 adapter may later live. Imports of
# unapproved vendor packages here are hard-blocked.
PRODUCTION_PARSER_AREA = (
    "apps/api/src/app/services/scientific_document",
    "services/scientific_document",
)

# Canonical schema modules must never import vendor packages.
CANONICAL_SCHEMA_MODULES = ("apps/api/src/app/schemas/scientific_document.py",)

# Reference-after-rewrite: production code must not import docs/references.
REFERENCE_DIR = "docs/references"

# Floating model/revision tokens that must never appear as a pinned version.
FLOATING_VERSION_TOKENS = {"latest", "main", "master", "nightly", "dev", "head", "*"}

# Characters that denote a version RANGE (not an exact pin).
RANGE_CHARS = (">", "<", "~", "^", "!", "|")

# Model weight extensions that must never be committed.
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

VENDORED_MARKERS = ("__vendored__", "vendored_source")

ADOPTION_MANIFEST = ROOT / "services" / "scientific_document" / "upstream_adoption.json"


def tracked_files() -> list[str]:
    completed = subprocess.run(
        ["git", "ls-files", "-co", "--exclude-standard"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [line for line in completed.stdout.splitlines() if line]


def _is_production_py(relative: str) -> bool:
    normalized = relative.replace("\\", "/")
    if not normalized.endswith(".py"):
        return False
    # Exclude test suites: they may contain intentional prohibited-looking
    # literals as NEGATIVE test samples. Only production code is gated.
    if "/tests/" in f"/{normalized}" or normalized.startswith("tests/"):
        return False
    return True


def _is_governance_config(relative: str) -> bool:
    normalized = relative.replace("\\", "/").lower()
    return normalized.endswith((".json", ".toml", ".yaml", ".yml"))


def _imported_roots(tree: ast.AST) -> list[str]:
    """Return the dotted root module names imported by a parsed module (AST)."""
    roots: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.append(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                roots.append(node.module.split(".")[0])
    return roots


def load_adoption_manifest():
    """Load + validate the adoption manifest via its Pydantic contract."""
    from services.scientific_document.adoption_contract import (
        UpstreamAdoptionManifest,
        load_adoption_manifest as _load,
    )

    return _load(ADOPTION_MANIFEST)


def approved_package_roots() -> set[str]:
    """Lower-cased approved import roots from the manifest (approved only).

    Both the PyPI/hyphenated name (``docling-parse``) and the import root
    (``docling_parse``) are accepted, since Python import roots use underscores
    while the manifest records the package's distribution name.
    """
    try:
        manifest = load_adoption_manifest()
    except Exception:
        return set()
    roots: set[str] = set()
    for entry in manifest.entries:
        if entry.adoption_status.value != "approved":
            continue
        for value in (entry.package, entry.model_id, entry.model_resolved_id):
            if value:
                roots.add(value.lower())
                roots.add(value.lower().replace("-", "_"))
    return roots


def check_reference_imports(tracked: list[str]) -> list[str]:
    errors: list[str] = []
    for relative in tracked:
        normalized = relative.replace("\\", "/")
        if not _is_production_py(normalized):
            continue
        if "/docs/references/" in f"/{normalized}" or normalized.startswith("docs/references/"):
            continue  # reference files themselves are allowed; only imports are
        path = ROOT / normalized
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="strict"))
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        for root in _imported_roots(tree):
            if root == "docs" and _imports_docs_references(tree):
                errors.append(f"production code imports docs.references: {normalized}")
    return errors


def _imports_docs_references(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module == "docs.references" or node.module.startswith("docs.references."):
                return True
    return False


def check_unapproved_parser_imports(tracked: list[str]) -> list[str]:
    approved = approved_package_roots()
    # Only these vendor-parser families are policed. Standard library, project
    # modules (``app``/``services``), and non-parser tooling (``fpdf``/``PIL``)
    # are out of scope. A policed family is allowed iff it is an APPROVED entry
    # in services/scientific_document/upstream_adoption.json (manifest-driven,
    # exact-version authorization — F2/F3).
    vendor_families = (
        "docling_parse",
        "paddleocr",
        "paddle",
        "mineru",
        "grobid",
        "pp_structure",
    )
    errors: list[str] = []
    for relative in tracked:
        normalized = relative.replace("\\", "/")
        if not _is_production_py(normalized):
            continue
        if not normalized.startswith(PRODUCTION_PARSER_AREA):
            continue
        path = ROOT / normalized
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="strict"))
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        for root in _imported_roots(tree):
            if root not in vendor_families:
                continue
            if root.lower() in approved:
                continue
            errors.append(
                f"unapproved vendor import '{root}' in production parser area: "
                f"{normalized} (must be an approved entry in upstream_adoption.json)"
            )
    return errors


def check_floating_versions(tracked: list[str]) -> list[str]:
    errors: list[str] = []
    # The key is quoted in JSON (``"model_revision": "latest"``), so an optional
    # closing quote is allowed between the key and the separator.
    pattern = re.compile(
        r"(model_revision|pipeline_version|revision|version|package_version|release_tag)"
        r"\"?\s*[:=]\s*[\"']?\s*(latest|main|master|nightly|dev|head)\b",
        re.IGNORECASE,
    )
    for relative in tracked:
        normalized = relative.replace("\\", "/")
        if not _is_governance_config(normalized):
            continue
        # Only scan adoption/config files for floating versions.
        if "scientific_document" not in normalized and "adoption" not in normalized:
            continue
        path = ROOT / normalized
        try:
            text = path.read_text(encoding="utf-8", errors="strict")
        except (OSError, UnicodeDecodeError):
            continue
        for match in pattern.finditer(text):
            errors.append(
                f"floating model/revision token in {normalized}: {match.group(0)!r}"
            )
    return errors


def check_exact_pinned_versions(tracked: list[str]) -> list[str]:
    """Approved packages must be pinned EXACTLY (no range) in config/manifest."""
    errors: list[str] = []
    # Key may be quoted in JSON; value is a quoted string.
    pattern = re.compile(
        r"(package_version|model_revision|pipeline_version|release_tag)"
        r"\"?\s*[:=]\s*[\"']([^\"']+)[\"']"
    )
    for relative in tracked:
        normalized = relative.replace("\\", "/")
        if not _is_governance_config(normalized):
            continue
        if "scientific_document" not in normalized and "adoption" not in normalized:
            continue
        path = ROOT / normalized
        try:
            text = path.read_text(encoding="utf-8", errors="strict")
        except (OSError, UnicodeDecodeError):
            continue
        for match in pattern.finditer(text):
            value = match.group(2).strip().lower()
            if any(tok in value for tok in FLOATING_VERSION_TOKENS):
                continue  # handled by check_floating_versions
            if any(ch in match.group(2) for ch in RANGE_CHARS):
                errors.append(
                    f"version range not allowed for approved package in {normalized}: "
                    f"{match.group(1)}={match.group(2)!r} (pin exact version)"
                )
    return errors


def check_model_weights(tracked: list[str]) -> list[str]:
    errors: list[str] = []
    for relative in tracked:
        normalized = relative.replace("\\", "/")
        lowered = normalized.lower()
        if lowered.endswith(MODEL_WEIGHT_SUFFIXES):
            errors.append(f"model weight file tracked in git: {normalized}")
    return errors


def check_canonical_vendor_leakage(tracked: list[str]) -> list[str]:
    errors: list[str] = []
    vendor_identifiers = (
        r"\bpaddle\b",
        r"\bdocling\b",
        r"\bmineru\b",
        r"\bgrobid\b",
        r"\bpp[-_]?structure\b",
    )
    combined = re.compile("|".join(vendor_identifiers), re.IGNORECASE)
    for relative in CANONICAL_SCHEMA_MODULES:
        normalized = relative.replace("\\", "/")
        path = ROOT / normalized
        if not path.is_file():
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="strict"))
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    imported = (alias.name or "")
                    if combined.search(imported):
                        errors.append(
                            f"canonical schema imports vendor module: {normalized}: {imported}"
                        )
    return errors


def check_unmanifested_vendored_source(tracked: list[str]) -> list[str]:
    """Fail if any tracked file carries a vendored-source marker without being
    listed in the adoption manifest. D-10 currently permits NO vendored source,
    so any such marker is rejected (F5)."""
    errors: list[str] = []
    for relative in tracked:
        normalized = relative.replace("\\", "/").lower()
        if any(marker in normalized for marker in VENDORED_MARKERS):
            errors.append(f"vendored-source marker without manifest entry: {relative}")
    return errors


def main() -> int:
    tracked = tracked_files()
    errors: list[str] = []
    errors += check_reference_imports(tracked)
    errors += check_unapproved_parser_imports(tracked)
    errors += check_floating_versions(tracked)
    errors += check_exact_pinned_versions(tracked)
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
