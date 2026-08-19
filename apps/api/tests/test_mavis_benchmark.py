"""The MAVIS benchmark evaluator reports honest verification levels."""

from __future__ import annotations

import json
from pathlib import Path

from services.reference_integration.mavis_benchmark import (
    evaluate_case,
    evaluate_mavis_benchmark,
)
from services.reference_integration.reference_capability_manifest import (
    load_manifest,
)

LEDGER_PATH = (
    Path(__file__).resolve().parents[3]
    / "services/reference_integration/mavis_adoption_ledger.json"
)
MANIFEST_PATH = (
    Path(__file__).resolve().parents[3]
    / "services/reference_integration/reference_capability_manifest.json"
)


def _registered_skills() -> frozenset[str]:
    from app.schemas.core import ScientificSkillId

    return frozenset(item.value for item in ScientificSkillId)


def _ledger_case_count() -> int:
    ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    return len(ledger["cases"])


def test_every_ledger_case_is_evaluated() -> None:
    case_count = _ledger_case_count()
    assert case_count >= 1
    summary = evaluate_mavis_benchmark(LEDGER_PATH)
    # The evaluated count must equal the ledger case count; no fixed baseline.
    assert summary["case_count"] == case_count
    total_by_tier = sum(
        bucket["total"] for bucket in summary["by_tier"].values()
    )
    assert total_by_tier == case_count
    ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    for tier, bucket in summary["by_tier"].items():
        expected_total = sum(
            1 for case in ledger["cases"] if case["tier"] == tier
        )
        assert bucket["total"] == expected_total


def test_browser_and_live_capabilities_are_pending_not_verified() -> None:
    summary = evaluate_mavis_benchmark(LEDGER_PATH)
    checks = summary["checks"]
    assert checks["wwt_browser_rendering"]["pending"] > 0
    assert checks["wwt_browser_rendering"]["passed"] == 0
    assert checks["live_provider"]["pending"] > 0
    assert checks["live_provider"]["passed"] == 0


def test_offline_checks_cover_every_case() -> None:
    case_count = _ledger_case_count()
    summary = evaluate_mavis_benchmark(LEDGER_PATH)
    for check in ("planning_semantics", "capability_mapping", "parameter_contract"):
        assert summary["checks"][check]["passed"] == case_count
        assert summary["checks"][check]["failed"] == 0


def test_unknown_capability_fails_mapping() -> None:
    manifest = load_manifest(MANIFEST_PATH)
    case = {
        "case_id": "XXXX",
        "tier": "tier_c",
        "goal": "在WWT太阳系视图下展示木星",
        "capability_ids": ["mavis.astronomy.ephemeris", "mavis.does.not_exist"],
        "required_inputs": [],
        "expected_outputs": [],
    }
    result = evaluate_case(
        case,
        manifest_capability_ids=manifest.capability_ids("mavis"),
        registered_skills=_registered_skills(),
    )
    by_name = {item.check: item.status for item in result.checks}
    assert by_name["capability_mapping"] == "failed"
    assert not result.passed


def test_missing_skill_fails_parameter_contract() -> None:
    manifest = load_manifest(MANIFEST_PATH)
    case = {
        "case_id": "YYYY",
        "tier": "tier_a",
        "goal": "计算金星大距",
        "capability_ids": ["mavis.astronomy.celestial_events"],
        "required_inputs": ["ephemeris_kernel"],
        "expected_outputs": ["celestial_events_list"],
    }
    result = evaluate_case(
        case,
        manifest_capability_ids=manifest.capability_ids("mavis"),
        registered_skills=frozenset({"ephemeris"}),
    )
    by_name = {item.check: item.status for item in result.checks}
    assert by_name["parameter_contract"] == "failed"
    assert not result.passed


def test_plan_only_case_reports_planning_semantics() -> None:
    manifest = load_manifest(MANIFEST_PATH)
    case = {
        "case_id": "ZZZZ",
        "tier": "tier_c",
        "goal": "获取火星冲日时间",
        "capability_ids": ["mavis.astronomy.celestial_events"],
        "required_inputs": ["ephemeris_kernel", "time_range"],
        "expected_outputs": ["celestial_events_list"],
    }
    result = evaluate_case(
        case,
        manifest_capability_ids=manifest.capability_ids("mavis"),
        registered_skills=_registered_skills(),
    )
    assert result.passed
    assert {item.check for item in result.checks} >= {
        "planning_semantics",
        "capability_mapping",
        "parameter_contract",
    }
