from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from services.reference_integration.build_mavis_adoption_ledger import (
    ALLOWED_ADOPTION_STATES,
    ALLOWED_CAPABILITY_FAMILIES,
    ALLOWED_EXCLUSION_REASONS,
    EXPECTED_CASE_COUNT,
    SCHEMA_VERSION,
    SOURCE_PROJECT,
    WWT_TOOL_CAPABILITIES,
    build_ledger,
)
from services.scientific_skills.wwt_capabilities import WWT_CAPABILITY_MATRIX

LEDGER_PATH = Path("services/reference_integration/mavis_adoption_ledger.json")
REFERENCE_ROOT = Path(
    os.environ.get("MAVIS_REFERENCE_ROOT", r"E:\xingwen-astro-ai-reference")
)


def _load_ledger() -> dict[str, Any]:
    assert LEDGER_PATH.is_file(), f"Ledger file not found at {LEDGER_PATH.resolve()}"
    content = LEDGER_PATH.read_text(encoding="utf-8")
    return json.loads(content)


def test_ledger_case_count_and_uniqueness() -> None:
    ledger = _load_ledger()
    cases = ledger["cases"]

    assert ledger["schema_version"] == SCHEMA_VERSION
    assert ledger["source_project"] == SOURCE_PROJECT
    assert ledger["generated_from_count"] == EXPECTED_CASE_COUNT
    assert ledger["summary"]["total_cases"] == EXPECTED_CASE_COUNT
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


def test_ledger_source_files_sha256_and_source_set_hash() -> None:
    ledger = _load_ledger()
    cases = ledger["cases"]

    # Recompute source_set_hash from cases
    sorted_cases = sorted(cases, key=lambda c: c["source_path"])
    hash_lines = [f"{c['source_path']}:{c['source_sha256']}\n" for c in sorted_cases]
    recalculated_hash = hashlib.sha256("".join(hash_lines).encode("utf-8")).hexdigest()
    assert ledger["source_set_hash"] == recalculated_hash, (
        "Top-level source_set_hash does not match recalculated hash"
    )

    # If reference root is available on disk, verify each source file bytes sha256
    if REFERENCE_ROOT.is_dir():
        for case in cases:
            source_file = REFERENCE_ROOT / case["source_path"]
            assert source_file.is_file(), f"Source file does not exist: {source_file}"
            actual_sha256 = hashlib.sha256(source_file.read_bytes()).hexdigest()
            assert actual_sha256 == case["source_sha256"], (
                f"Source sha256 mismatch for {case['case_id']}: "
                f"expected {case['source_sha256']}, got {actual_sha256}"
            )


def test_ledger_summary_counts_consistency() -> None:
    ledger = _load_ledger()
    cases = ledger["cases"]
    summary = ledger["summary"]

    assert summary["total_cases"] == len(cases)

    # Verify state counts
    computed_state_counts = {state: 0 for state in ALLOWED_ADOPTION_STATES}
    computed_cap_counts = {cap: 0 for cap in ALLOWED_CAPABILITY_FAMILIES}
    computed_excl_counts = {reason: 0 for reason in ALLOWED_EXCLUSION_REASONS}

    for case in cases:
        computed_state_counts[case["adoption_state"]] += 1
        for cap in case["capability_families"]:
            computed_cap_counts[cap] += 1
        for reason in case["exclusion_reasons"]:
            computed_excl_counts[reason] += 1

    assert summary["by_adoption_state"] == computed_state_counts
    assert summary["by_capability_family"] == computed_cap_counts
    assert summary["by_exclusion_reason"] == computed_excl_counts
    assert sum(computed_state_counts.values()) == EXPECTED_CASE_COUNT


def test_ledger_controlled_enums_and_contract_rules() -> None:
    ledger = _load_ledger()
    cases = ledger["cases"]

    assert ledger["allowed_capability_families"] == ALLOWED_CAPABILITY_FAMILIES
    assert ledger["allowed_adoption_states"] == ALLOWED_ADOPTION_STATES
    assert ledger["allowed_exclusion_reasons"] == ALLOWED_EXCLUSION_REASONS
    assert ledger["wwt_capability_matrix"] == {
        capability: dict(disposition)
        for capability, disposition in sorted(WWT_CAPABILITY_MATRIX.items())
    }
    assert set(WWT_TOOL_CAPABILITIES.values()).issubset(WWT_CAPABILITY_MATRIX)

    for case in cases:
        case_id = case["case_id"]

        # Capabilities
        caps = case["capability_families"]
        assert isinstance(caps, list) and len(caps) > 0, (
            f"Empty capabilities in {case_id}"
        )
        assert caps == sorted(list(set(caps))), (
            f"Capabilities not sorted or deduped in {case_id}"
        )
        for cap in caps:
            assert cap in ALLOWED_CAPABILITY_FAMILIES, (
                f"Invalid capability '{cap}' in {case_id}"
            )

        # Adoption state
        state = case["adoption_state"]
        assert state in ALLOWED_ADOPTION_STATES, (
            f"Invalid adoption state '{state}' in {case_id}"
        )
        # Cannot be implemented_verified without live run evidence
        assert state != "implemented_verified", (
            f"Case {case_id} cannot be marked implemented_verified without live evidence"
        )

        # Exclusion reasons
        reasons = case["exclusion_reasons"]
        assert isinstance(reasons, list)
        for r in reasons:
            assert r in ALLOWED_EXCLUSION_REASONS, (
                f"Invalid exclusion reason '{r}' in {case_id}"
            )

        # Target surfaces and verification gates
        surfaces = case["target_xingwen_surfaces"]
        gates = case["verification_gates"]
        assert isinstance(surfaces, list) and len(surfaces) > 0, (
            f"Empty targets in {case_id}"
        )
        assert isinstance(gates, list) and len(gates) > 0, f"Empty gates in {case_id}"

        if state == "implemented_unverified":
            for surface in surfaces:
                assert ":" in surface or surface.endswith(".tsx"), (
                    f"Surface must reference file:symbol or UI file: {surface} in {case_id}"
                )
        if any(capability.startswith("wwt_") for capability in caps):
            assert state == "implemented_unverified", (
                f"Case {case_id} has a contract and standard Renderer path but "
                "must remain unverified until terminal Live and visual evidence exist"
            )


def test_ledger_sanitization_no_secrets_paths_or_prompt_dumps() -> None:
    ledger = _load_ledger()

    # Top-level should have no timestamp keys
    forbidden_keys = {"generated_at", "timestamp", "created_at", "updated_at"}
    for key in forbidden_keys:
        assert key not in ledger, (
            f"Forbidden non-deterministic key '{key}' found at root"
        )

    raw_json = json.dumps(ledger, ensure_ascii=False)

    # No hardcoded absolute personal paths
    for forbidden_path_sub in [
        r"C:\\Users\\",
        r"E:\\xingwen-astro-ai-reference",
        r"/home/",
        r"/Users/",
    ]:
        assert forbidden_path_sub not in raw_json, (
            f"Absolute path '{forbidden_path_sub}' leaked into ledger JSON"
        )

    # No credentials or API keys
    for secret_sub in ["9b09f0f3ad6c7f652661b342c2f6fd76", "api_key="]:
        assert secret_sub not in raw_json, (
            f"Secret/credential '{secret_sub}' leaked into ledger JSON"
        )

    # Concise goal bounded length
    for case in ledger["cases"]:
        goal = case["concise_goal"]
        assert isinstance(goal, str) and 5 <= len(goal) <= 120, (
            f"Goal for case {case['case_id']} is not concise (length={len(goal)}): {goal}"
        )


def test_build_script_check_mode() -> None:
    if not REFERENCE_ROOT.is_dir():
        return

    # Direct function build match
    built = build_ledger(REFERENCE_ROOT)
    existing = _load_ledger()
    assert built == existing, (
        "build_ledger() output differs from mavis_adoption_ledger.json on disk"
    )

    # CLI check mode
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
