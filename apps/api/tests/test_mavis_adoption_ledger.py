"""The MAVIS ledger is a benchmark case index, not a coverage authority."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from services.reference_integration.build_mavis_adoption_ledger import (
    ALLOWED_CAPABILITY_FAMILIES,
    ALLOWED_TIERS,
    EXPECTED_CASE_COUNT,
    SCHEMA_VERSION,
    SOURCE_PROJECT,
    build_ledger,
)

LEDGER_PATH = Path("services/reference_integration/mavis_adoption_ledger.json")
REFERENCE_ROOT = Path(
    os.environ.get("MAVIS_REFERENCE_ROOT", r"E:\xingwen-astro-ai-reference")
)


def _load_ledger() -> dict[str, Any]:
    assert LEDGER_PATH.is_file(), f"Ledger file not found at {LEDGER_PATH.resolve()}"
    return json.loads(LEDGER_PATH.read_text(encoding="utf-8"))


def test_ledger_case_count_and_uniqueness() -> None:
    ledger = _load_ledger()
    cases = ledger["cases"]

    assert ledger["schema_version"] == SCHEMA_VERSION
    assert ledger["source_project"] == SOURCE_PROJECT
    assert ledger["generated_from_count"] == EXPECTED_CASE_COUNT
    assert ledger["case_count"] == EXPECTED_CASE_COUNT
    assert len(cases) == EXPECTED_CASE_COUNT

    seen_ids: set[str] = set()
    seen_paths: set[str] = set()

    for case in cases:
        case_id = case["case_id"]
        source_path = case["source_path"]

        assert isinstance(case_id, str) and len(case_id) >= 2
        assert case_id not in seen_ids, f"Duplicate case_id: {case_id}"
        seen_ids.add(case_id)

        assert isinstance(source_path, str) and source_path.startswith(
            "mavis/data/task_benchmark/"
        )
        assert source_path not in seen_paths, f"Duplicate source_path: {source_path}"
        seen_paths.add(source_path)


def test_ledger_tiers_match_real_assets() -> None:
    ledger = _load_ledger()
    by_tier = ledger["by_tier"]
    assert set(by_tier) == set(ALLOWED_TIERS)
    computed = {tier: 0 for tier in ALLOWED_TIERS}
    for case in ledger["cases"]:
        assert case["tier"] in ALLOWED_TIERS, case["case_id"]
        computed[case["tier"]] += 1
    assert by_tier == computed
    assert sum(computed.values()) == EXPECTED_CASE_COUNT


def test_ledger_no_longer_carries_coverage_state() -> None:
    ledger = _load_ledger()
    raw = json.dumps(ledger, ensure_ascii=False)
    for retired in (
        "implemented_unverified",
        "implemented_verified",
        "adoption_state",
        "source_sha256",
        "exclusion_reasons",
        "target_xingwen_surfaces",
        "reference_runtime_mechanisms",
    ):
        assert retired not in raw, f"ledger still carries coverage state: {retired}"


def test_ledger_capability_ids_reference_families() -> None:
    ledger = _load_ledger()
    assert ledger["allowed_capability_families"] == ALLOWED_CAPABILITY_FAMILIES
    for case in ledger["cases"]:
        capability_ids = case["capability_ids"]
        assert isinstance(capability_ids, list) and capability_ids, case["case_id"]
        assert capability_ids == sorted(set(capability_ids)), case["case_id"]
        assert all(
            capability_id.startswith("mavis.") for capability_id in capability_ids
        ), case["case_id"]


def test_ledger_source_set_hash_is_path_aggregate() -> None:
    ledger = _load_ledger()
    sorted_cases = sorted(ledger["cases"], key=lambda c: c["source_path"])
    hash_lines = [f"{c['source_path']}\n" for c in sorted_cases]
    recalculated = hashlib.sha256("".join(hash_lines).encode("utf-8")).hexdigest()
    assert ledger["source_set_hash"] == recalculated


def test_ledger_sanitization_no_secrets_or_personal_paths() -> None:
    ledger = _load_ledger()

    for key in ("generated_at", "timestamp", "created_at", "updated_at"):
        assert key not in ledger

    raw_json = json.dumps(ledger, ensure_ascii=False)
    for forbidden_path_sub in [
        r"C:\\Users\\",
        r"/home/",
        r"/Users/",
    ]:
        assert forbidden_path_sub not in raw_json
    for secret_sub in ["9b09f0f3ad6c7f652661b342c2f6fd76", "api_key="]:
        assert secret_sub not in raw_json

    for case in ledger["cases"]:
        goal = case["goal"]
        assert isinstance(goal, str) and 5 <= len(goal) <= 120, case["case_id"]


def test_build_script_check_mode() -> None:
    if not REFERENCE_ROOT.is_dir():
        return

    built = build_ledger(REFERENCE_ROOT)
    existing = _load_ledger()
    assert built == existing, (
        "build_ledger() output differs from mavis_adoption_ledger.json on disk"
    )

    cmd = [
        sys.executable,
        "services/reference_integration/build_mavis_adoption_ledger.py",
        "--reference-root",
        str(REFERENCE_ROOT),
        "--output",
        str(LEDGER_PATH),
        "--check",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert result.returncode == 0, (
        f"CLI check mode failed: {result.stdout}\n{result.stderr}"
    )
    assert "CHECK OK" in result.stdout
