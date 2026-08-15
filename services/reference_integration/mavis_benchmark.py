"""Offline deterministic benchmark evaluator for the MAVIS case corpus.

This is not a workflow: it is a read-only evaluator over the 160-case index
that reports, per case, which verification levels the current implementation
can honestly claim.  Verification levels follow the project's evidence
discipline: ``passed`` means an offline deterministic check ran; capabilities
that need a browser or live network are marked ``browser_pending`` /
``live_pending`` and are never counted as verified here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from services.reference_integration.reference_capability_manifest import (
    load_manifest,
)

LEDGER_PATH = Path(__file__).resolve().parent / "mavis_adoption_ledger.json"
MANIFEST_PATH = Path(__file__).resolve().parent / "reference_capability_manifest.json"

# Manifest capability id prefix -> registered scientific skill.
CAPABILITY_SKILLS = {
    "mavis.astronomy.ephemeris": "ephemeris",
    "mavis.astronomy.celestial_events": "celestial_events",
    "mavis.astronomy.eclipse_geometry": "celestial_events",
    "mavis.astronomy.rise_set_transit": "celestial_events",
    "mavis.astronomy.body_radius": "ephemeris",
    "mavis.source.simbad_object": "simbad_lookup",
    "mavis.source.simbad_region": "simbad_lookup",
    "mavis.source.skyview_fits": "skyview_fits",
    "mavis.source.gaia_cone": "gaia_cone_search",
    "mavis.source.vizier_tap": "vizier_tap",
    "mavis.source.sdss_spectrum": "spectrum_acquisition",
    "mavis.source.mast_light_curve": "light_curve_acquisition",
    "mavis.fits.background_estimation": "fits_image_analysis",
    "mavis.fits.source_detection": "fits_image_analysis",
    "mavis.fits.centroid": "fits_image_analysis",
    "mavis.fits.segmentation": "fits_image_analysis",
    "mavis.fits.aperture_photometry": "fits_image_analysis",
    "mavis.fits.psf_photometry": "fits_image_analysis",
    "mavis.spectrum.analysis": "spectrum_analysis",
    "mavis.light_curve.analysis": "light_curve_analysis",
    "mavis.wwt.scene": "wwt_scene",
    "mavis.observer.geocoding": "ephemeris",
    "mavis.interaction.wwt_navigation": "wwt_scene",
    "mavis.interaction.wwt_time_control": "wwt_scene",
    "mavis.interaction.wwt_layers": "wwt_scene",
    "mavis.interaction.wwt_annotation": "wwt_scene",
    "mavis.interaction.wwt_tour": "wwt_scene",
    "mavis.interaction.wwt_readback": "wwt_scene",
    "mavis.interaction.wwt_png_export": "wwt_scene",
    "mavis.interaction.view_interaction": "wwt_scene",
}

LIVE_CAPABILITY_PREFIXES = (
    "mavis.source.",
)
BROWSER_CAPABILITY_PREFIXES = (
    "mavis.interaction.",
    "mavis.wwt.scene",
)


@dataclass(frozen=True, slots=True)
class BenchmarkCheck:
    check: str
    status: str

    @property
    def passed(self) -> bool:
        return self.status == "passed"


@dataclass(frozen=True, slots=True)
class CaseBenchmark:
    case_id: str
    tier: str
    checks: tuple[BenchmarkCheck, ...]

    @property
    def passed(self) -> bool:
        """A case passes when every offline-deterministic check passed.

        Pending browser/live levels do not fail a case; they are honestly
        reported and never counted as verified.
        """

        required = {
            "planning_semantics",
            "capability_mapping",
            "parameter_contract",
        }
        by_name = {item.check: item for item in self.checks}
        return all(by_name[name].passed for name in required if name in by_name)


def _registered_skill_ids() -> frozenset[str]:
    from app.schemas.core import ScientificSkillId

    return frozenset(item.value for item in ScientificSkillId)


def evaluate_case(
    case: dict[str, object],
    *,
    manifest_capability_ids: frozenset[str],
    registered_skills: frozenset[str],
) -> CaseBenchmark:
    checks: list[BenchmarkCheck] = []

    goal = case.get("goal")
    capability_ids = case.get("capability_ids")
    planning_ok = (
        isinstance(goal, str)
        and bool(goal.strip())
        and isinstance(capability_ids, list)
        and bool(capability_ids)
        and isinstance(case.get("required_inputs"), list)
        and isinstance(case.get("expected_outputs"), list)
    )
    checks.append(
        BenchmarkCheck(
            "planning_semantics", "passed" if planning_ok else "failed"
        )
    )

    mapping_ok = all(
        isinstance(item, str) and item in manifest_capability_ids
        for item in (capability_ids or [])
    )
    checks.append(
        BenchmarkCheck(
            "capability_mapping", "passed" if mapping_ok else "failed"
        )
    )

    contract_ok = all(
        CAPABILITY_SKILLS.get(item) in registered_skills
        for item in (capability_ids or [])
    )
    checks.append(
        BenchmarkCheck(
            "parameter_contract", "passed" if contract_ok else "failed"
        )
    )

    if any(
        isinstance(item, str) and item.startswith(BROWSER_CAPABILITY_PREFIXES)
        for item in (capability_ids or [])
    ):
        checks.append(BenchmarkCheck("wwt_browser_rendering", "browser_pending"))
    if any(
        isinstance(item, str) and item.startswith(LIVE_CAPABILITY_PREFIXES)
        for item in (capability_ids or [])
    ):
        checks.append(BenchmarkCheck("live_provider", "live_pending"))
    return CaseBenchmark(
        case_id=str(case["case_id"]),
        tier=str(case["tier"]),
        checks=tuple(checks),
    )


def evaluate_mavis_benchmark(ledger_path: Path = LEDGER_PATH) -> dict[str, object]:
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    manifest = load_manifest(MANIFEST_PATH)
    manifest_capability_ids = manifest.capability_ids("mavis")
    registered_skills = _registered_skill_ids()

    results = [
        evaluate_case(
            case,
            manifest_capability_ids=manifest_capability_ids,
            registered_skills=registered_skills,
        )
        for case in ledger["cases"]
    ]

    by_tier: dict[str, dict[str, int]] = {
        "tier_a": {"total": 0, "passed": 0},
        "tier_b": {"total": 0, "passed": 0},
        "tier_c": {"total": 0, "passed": 0},
    }
    for result in results:
        bucket = by_tier.setdefault(
            result.tier, {"total": 0, "passed": 0}
        )
        bucket["total"] += 1
        if result.passed:
            bucket["passed"] += 1

    check_counts: dict[str, dict[str, int]] = {}
    for result in results:
        for check in result.checks:
            counter = check_counts.setdefault(
                check.check, {"passed": 0, "failed": 0, "pending": 0}
            )
            if check.status == "passed":
                counter["passed"] += 1
            elif check.status == "failed":
                counter["failed"] += 1
            else:
                counter["pending"] += 1

    return {
        "case_count": len(results),
        "by_tier": by_tier,
        "checks": check_counts,
        "failed_cases": [
            result.case_id for result in results if not result.passed
        ],
    }


__all__ = [
    "BenchmarkCheck",
    "CaseBenchmark",
    "evaluate_case",
    "evaluate_mavis_benchmark",
]
