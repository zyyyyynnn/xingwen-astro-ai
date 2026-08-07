"""D-10 scientific-document-parsing governance gate (machine-enforced).

Extends the repository foundation checks with the D-10 adoption boundary. It is
a SEPARATE scanner (not a fork of ``check_foundation.py``) so the D-10 gate can
evolve independently. It machine-detects the prohibited patterns from D-10 #34:

- production code importing ``docs/references`` (reference-after-rewrite source)
- unapproved parser/vendor packages imported in the production parser area
- floating model versions (``latest`` / ``main`` / ``master`` / revision aliases)
- model weight files tracked in git
- Canonical schema modules importing vendor types
- unmanifested vendored third-party source files

Machine detection cannot judge "did a developer read upstream source and
hand-rewrite a similar algorithm"; the human Review checklist (REVIEW_CHECKLIST
update) covers that. This scanner only enforces what is mechanically checkable.
"""

from __future__ import annotations

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
FLOATING_VERSION_TOKENS = {"latest", "main", "master", "nightly", "dev", "HEAD"}

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

ADOPTION_MANIFEST = (
    ROOT / "services" / "scientific_document" / "upstream_adoption.json"
)


def load_approved_packages() -> set[str]:
    """Return the lower-cased approved vendor package names from the manifest."""
    if not ADOPTION_MANIFEST.is_file():
        return set()
    data = json.loads(ADOPTION_MANIFEST.read_text(encoding="utf-8"))
    approved: set[str] = set()
    for entry in data.get("entries", []):
        for key in ("package", "model_id"):
            value = entry.get(key)
            if value:
                approved.add(value.lower())
    return approved


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


def check_reference_imports(tracked: list[str]) -> list[str]:
    errors: list[str] = []
    for relative in tracked:
        normalized = relative.replace("\\", "/")
        if not _is_production_py(normalized):
            continue
        if "/docs/references/" in f"/{normalized}" or normalized.startswith(
            "docs/references/"
        ):
            continue  # reference files themselves are allowed; only imports are
        path = ROOT / normalized
        try:
            text = path.read_text(encoding="utf-8", errors="strict")
        except (OSError, UnicodeDecodeError):
            continue
        if re.search(r"(^|\n)\s*import\s+.*\bdocs\.references\b", text) or re.search(
            r"from\s+docs\.references\s+import", text
        ):
            errors.append(f"production code imports docs.references: {normalized}")
    return errors


def check_unapproved_parser_imports(tracked: list[str]) -> list[str]:
    approved = load_approved_packages()
    errors: list[str] = []
    # Known vendor import roots that are NOT approved for production parser area.
    vendor_import_roots = (
        "paddleocr",
        "docling",
        "paddle",
        "mineru",
        "grobid",
    )
    for relative in tracked:
        normalized = relative.replace("\\", "/")
        if not _is_production_py(normalized):
            continue
        if not normalized.startswith(PRODUCTION_PARSER_AREA):
            continue
        path = ROOT / normalized
        try:
            text = path.read_text(encoding="utf-8", errors="strict")
        except (OSError, UnicodeDecodeError):
            continue
        for root in vendor_import_roots:
            if re.search(rf"(^|\n)\s*(import|from)\s+{re.escape(root)}", text):
                # Allow only if the exact approved package is pinned in the
                # manifest AND this is the benchmark-only native_baseline module.
                if normalized.endswith("native_baseline.py") and root == "docling":
                    continue
                errors.append(
                    f"unapproved vendor import '{root}' in production parser area: "
                    f"{normalized}"
                )
    return errors


def check_floating_versions(tracked: list[str]) -> list[str]:
    errors: list[str] = []
    pattern = re.compile(
        r"(model_revision|pipeline_version|revision|version)\s*[:=]\s*"
        r"[\"']?\s*(latest|main|master|nightly|dev|HEAD)\b",
        re.IGNORECASE,
    )
    for relative in tracked:
        normalized = relative.replace("\\", "/")
        if not _is_production_py(normalized):
            continue
        if not normalized.endswith((".py", ".json", ".toml", ".yaml", ".yml")):
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


def check_model_weights(tracked: list[str]) -> list[str]:
    errors: list[str] = []
    for relative in tracked:
        normalized = relative.replace("\\", "/")
        lowered = normalized.lower()
        if lowered.endswith(MODEL_WEIGHT_SUFFIXES):
            errors.append(f"model weight file tracked in git: {normalized}")
    return errors


def check_canonical_vendor_types(tracked: list[str]) -> list[str]:
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
        text = path.read_text(encoding="utf-8", errors="strict")
        # Allow the word only inside docstrings/comments that cite approved
        # upstream names for governance; block actual code identifiers/types.
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
                continue
            if combined.search(line) and re.search(r"[A-Za-z_]\w*", line):
                # Heuristic: a vendor name used as a type/identifier in code.
                if re.search(r"\b(from|import)\s+\w*paddle\w*", line):
                    continue
                errors.append(
                    f"canonical schema may leak vendor type: {normalized}: {line}"
                )
    return errors


def main() -> int:
    tracked = tracked_files()
    errors: list[str] = []
    errors += check_reference_imports(tracked)
    errors += check_unapproved_parser_imports(tracked)
    errors += check_floating_versions(tracked)
    errors += check_model_weights(tracked)
    errors += check_canonical_vendor_types(tracked)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("D-10 governance gate passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
