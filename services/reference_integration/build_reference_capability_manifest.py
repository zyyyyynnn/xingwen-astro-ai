r"""Build, check, and report the reference capability coverage manifest.

Usage:
    python services/reference_integration/build_reference_capability_manifest.py \
        --reference-root <reference-root> --check

The manifest JSON is the single coverage denominator for Inosum / AutoAstro /
MAVIS.  ``--check`` verifies semantics, owner existence, reference source
existence, and the per-reference source-set aggregate digests without writing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from services.reference_integration.reference_capability_manifest import (
    ALLOWED_CATEGORIES,
    ALLOWED_REFERENCES,
    ReferenceCapabilityManifest,
    load_manifest,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = Path(__file__).resolve().parent / "reference_capability_manifest.json"


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def reference_source_paths(manifest: ReferenceCapabilityManifest) -> dict[str, set[str]]:
    sources: dict[str, set[str]] = {reference: set() for reference in ALLOWED_REFERENCES}
    for capability in manifest.capabilities:
        sources[capability.reference].update(capability.reference_sources)
    return sources


def compute_reference_digests(
    manifest: ReferenceCapabilityManifest, reference_root: Path
) -> dict[str, str]:
    digests: dict[str, str] = {}
    for reference, paths in reference_source_paths(manifest).items():
        lines: list[str] = []
        for relative in sorted(paths):
            resolved = (reference_root / relative).resolve()
            if not resolved.is_relative_to(reference_root.resolve()):
                raise ValueError(
                    f"{reference} source escapes the reference root: {relative}"
                )
            if not resolved.is_file():
                raise FileNotFoundError(
                    f"{reference} source not found under reference root: {relative}"
                )
            lines.append(f"{relative}:{_file_sha256(resolved)}\n")
        digests[reference] = hashlib.sha256("".join(lines).encode("utf-8")).hexdigest()
    return digests


def check_owners_exist(manifest: ReferenceCapabilityManifest) -> list[str]:
    problems: list[str] = []
    for capability in manifest.capabilities:
        for owner in capability.xingwen_owners:
            candidate = REPO_ROOT / owner
            if not candidate.exists():
                problems.append(f"{capability.capability_id}: missing owner {owner}")
    return problems


def print_report(manifest: ReferenceCapabilityManifest) -> None:
    report = manifest.coverage_report()
    for reference in ALLOWED_REFERENCES:
        print(reference.capitalize())
        for category in ALLOWED_CATEGORIES:
            axis = report[reference][category]
            print(
                f"  {category.capitalize()}:"
                f" {axis['implemented']}/{axis['eligible']}"
                f" = {axis['percent']:.2f}%"
            )
    counts = manifest.state_counts()
    print(f"integration_pending count: {counts['integration_pending']}")
    print(f"missing count: {counts['missing']}")
    print(f"excluded count: {counts['excluded']}")


def run_check(reference_root: Path | None) -> int:
    try:
        manifest = load_manifest(MANIFEST_PATH)
    except (ValueError, json.JSONDecodeError) as error:
        print(f"ERROR: manifest failed validation: {error}")
        return 1

    problems = check_owners_exist(manifest)
    if problems:
        for problem in problems:
            print(f"ERROR: {problem}")
        return 1

    if reference_root is not None:
        if not reference_root.is_dir():
            print(f"ERROR: reference root not found: {reference_root}")
            return 1
        try:
            digests = compute_reference_digests(manifest, reference_root)
        except (ValueError, FileNotFoundError) as error:
            print(f"ERROR: {error}")
            return 1
        for reference, digest in digests.items():
            recorded = manifest.reference_snapshot_digests.get(reference)
            if recorded != digest:
                print(
                    f"ERROR: {reference} reference_snapshot_digest drift: expected"
                    f" {digest}, manifest records {recorded}"
                )
                return 1

    print_report(manifest)
    print("CHECK OK: reference capability manifest is consistent.")
    return 0


def run_write_digests(reference_root: Path) -> int:
    try:
        manifest = load_manifest(MANIFEST_PATH)
        digests = compute_reference_digests(manifest, reference_root)
    except (ValueError, FileNotFoundError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}")
        return 1
    raw = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    raw["reference_snapshot_digests"] = digests
    encoded = json.dumps(raw, indent=2, ensure_ascii=False) + "\n"
    MANIFEST_PATH.write_bytes(encoded.encode("utf-8"))
    print(f"SUCCESS: wrote per-reference snapshot digests to {MANIFEST_PATH}")
    for reference, digest in digests.items():
        print(f"  {reference}: {digest}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build or check the reference capability coverage manifest"
    )
    parser.add_argument(
        "--reference-root",
        type=Path,
        default=None,
        help="Read-only reference root used for source existence and digest checks",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate without writing",
    )
    parser.add_argument(
        "--write-digests",
        action="store_true",
        help="Recompute and write the per-reference source-set aggregate digests",
    )
    args = parser.parse_args(argv)

    if args.write_digests:
        if args.reference_root is None:
            print("ERROR: --write-digests requires --reference-root")
            return 1
        return run_write_digests(args.reference_root)
    return run_check(args.reference_root)


if __name__ == "__main__":
    sys.exit(main())
