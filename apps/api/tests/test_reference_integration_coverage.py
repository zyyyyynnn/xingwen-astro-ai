"""Semantic validation of the reference capability coverage Authority."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from services.reference_integration.build_reference_capability_manifest import (
    MANIFEST_PATH,
    REPO_ROOT,
    compute_reference_digests,
    reference_source_paths,
)
from services.reference_integration.reference_capability_manifest import (
    ALLOWED_CATEGORIES,
    ALLOWED_REFERENCES,
    load_manifest,
    parse_capability,
)

LEDGER_PATH = Path(__file__).resolve().parents[3] / (
    "services/reference_integration/mavis_adoption_ledger.json"
)
EXPECTED_MAVIS_CASES = 160


@pytest.fixture(scope="module")
def manifest() -> object:
    return load_manifest(MANIFEST_PATH)


@pytest.fixture(scope="module")
def raw_capabilities() -> list[dict]:
    raw = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return raw["capabilities"]


def test_capability_ids_are_globally_unique(raw_capabilities):
    ids = [item["capability_id"] for item in raw_capabilities]
    assert len(ids) == len(set(ids))


def test_references_are_limited_to_the_three_projects(raw_capabilities):
    assert {item["reference"] for item in raw_capabilities} <= set(ALLOWED_REFERENCES)


def test_categories_are_limited_to_the_three_axes(raw_capabilities):
    assert {item["category"] for item in raw_capabilities} <= set(ALLOWED_CATEGORIES)


def test_ineligible_capabilities_must_be_rejected(raw_capabilities):
    for item in raw_capabilities:
        if not item["eligible"]:
            assert item["disposition"] == "rejected", item["capability_id"]


def test_rejected_capabilities_need_objective_exclusion_reason(raw_capabilities):
    for item in raw_capabilities:
        if item["disposition"] == "rejected":
            assert not item["eligible"], item["capability_id"]
            assert item.get("exclusion_reason"), item["capability_id"]


def test_eligible_capabilities_cannot_be_rejected(raw_capabilities):
    for item in raw_capabilities:
        if item["eligible"]:
            assert item["disposition"] in {"adopted", "replaced"}, item["capability_id"]


def test_implemented_capabilities_own_real_files(manifest):
    for capability in manifest.capabilities:
        if capability.implementation_state == "implemented":
            assert capability.xingwen_owners, capability.capability_id
            for owner in capability.xingwen_owners:
                assert (REPO_ROOT / owner).exists(), (
                    f"{capability.capability_id}: {owner}"
                )


def test_integration_pending_never_counts_as_completed(manifest):
    for capability in manifest.capabilities:
        if capability.implementation_state == "integration_pending":
            assert not capability.completed, capability.capability_id


def test_every_reference_is_independently_scorable_on_all_axes(manifest):
    for reference in ALLOWED_REFERENCES:
        for category in ALLOWED_CATEGORIES:
            eligible = manifest.eligible_count(reference, category)
            implemented = manifest.implemented_count(reference, category)
            assert eligible > 0, f"{reference}/{category}"
            assert 0 <= implemented <= eligible, f"{reference}/{category}"


def test_coverage_percent_matches_counts(manifest):
    for reference in ALLOWED_REFERENCES:
        for category in ALLOWED_CATEGORIES:
            eligible = manifest.eligible_count(reference, category)
            implemented = manifest.implemented_count(reference, category)
            assert manifest.coverage_percent(reference, category) == pytest.approx(
                implemented * 100.0 / eligible
            )


def test_mavis_ledger_capability_ids_exist_in_manifest(manifest):
    ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    known = manifest.capability_ids("mavis")
    referenced = {
        capability_id
        for case in ledger["cases"]
        for capability_id in case["capability_ids"]
    }
    unknown = referenced - known
    assert not unknown, f"ledger references unknown capabilities: {sorted(unknown)}"


def test_mavis_ledger_covers_all_160_cases():
    ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    assert ledger["case_count"] == EXPECTED_MAVIS_CASES
    case_ids = [case["case_id"] for case in ledger["cases"]]
    assert len(case_ids) == len(set(case_ids)) == EXPECTED_MAVIS_CASES
    assert ledger["by_tier"]["tier_a"] + ledger["by_tier"]["tier_b"] + ledger[
        "by_tier"
    ]["tier_c"] == EXPECTED_MAVIS_CASES


def test_reference_sources_exist_under_reference_root(manifest):
    reference_root = Path(r"E:\xingwen-astro-ai-reference")
    if not reference_root.is_dir():
        pytest.skip("reference root is not available in this environment")
    for reference, sources in reference_source_paths(manifest).items():
        for relative in sources:
            assert (reference_root / relative).is_file(), (
                f"{reference}: {relative}"
            )


def test_snapshot_digests_are_per_reference_not_per_capability(manifest, raw_capabilities):
    for item in raw_capabilities:
        assert "source_sha256" not in item, item["capability_id"]
        assert "sha256" not in item, item["capability_id"]
    assert set(manifest.reference_snapshot_digests) <= set(ALLOWED_REFERENCES)


def test_builder_check_is_deterministic():
    import os

    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT)
    result = subprocess.run(
        [
            sys.executable,
            str(
                REPO_ROOT
                / "services/reference_integration/build_reference_capability_manifest.py"
            ),
            "--check",
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env=env,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_invalid_capabilities_are_rejected():
    base = {
        "reference": "inosum",
        "category": "function",
        "capability_id": "inosum.paper.test_capability",
        "reference_sources": ["inosum/Auto_doc_analysis_summarize.py"],
        "disposition": "adopted",
        "implementation_state": "implemented",
        "eligible": True,
        "xingwen_owners": ["services/paper_pipeline/summary.py"],
        "verification": ["unit"],
    }
    parse_capability(dict(base), index=0)

    with pytest.raises(ValueError, match="unknown reference"):
        parse_capability({**base, "reference": "unknown"}, index=1)
    with pytest.raises(ValueError, match="unknown category"):
        parse_capability({**base, "category": "diagram"}, index=2)
    with pytest.raises(ValueError, match="forbidden fragment"):
        parse_capability(
            {**base, "capability_id": "inosum.paper.capability_v1"}, index=3
        )
    with pytest.raises(ValueError, match="namespaced"):
        parse_capability(
            {**base, "capability_id": "autoastro.paper.chunking"}, index=4
        )
    with pytest.raises(ValueError, match="must be rejected with an"):
        parse_capability(
            {**base, "eligible": False, "disposition": "adopted"}, index=5
        )
    with pytest.raises(ValueError, match="requires exclusion_reason"):
        parse_capability(
            {
                **base,
                "eligible": False,
                "disposition": "rejected",
            },
            index=6,
        )
    with pytest.raises(ValueError, match="must list xingwen_owners"):
        parse_capability({**base, "xingwen_owners": []}, index=7)
    with pytest.raises(ValueError, match="must list verification"):
        parse_capability({**base, "verification": []}, index=8)
    with pytest.raises(ValueError, match="rejected but eligible"):
        parse_capability(
            {**base, "eligible": True, "disposition": "rejected"}, index=9
        )


def test_builder_digests_cover_all_reference_sources(manifest):
    reference_root = Path(r"E:\xingwen-astro-ai-reference")
    if not reference_root.is_dir():
        pytest.skip("reference root is not available in this environment")
    digests = compute_reference_digests(manifest, reference_root)
    assert set(digests) == set(reference_source_paths(manifest))
    for reference, digest in digests.items():
        assert digest == manifest.reference_snapshot_digests[reference], reference
