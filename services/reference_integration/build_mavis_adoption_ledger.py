"""Build the MAVIS benchmark case index.

The ledger indexes the current scanned MAVIS case corpus under
``mavis/data/task_benchmark`` as an offline benchmark corpus.  The case count
is decided by the real reference directory scan, never by a hard-coded
baseline.  It is NOT a coverage authority: reference migration coverage is
owned exclusively by ``reference_capability_manifest.json``.  Each case
records what the reference task wanted, its asset tier, the manifest
capability ids it exercises, and the verification requirements; completion
state lives in the manifest.

Tiers are derived from the real snapshot assets:
- ``tier_a``: the case directory contains executed reference code (``code/``).
- ``tier_b``: no code, but partial result assets (``file/`` or ``image/``).
- ``tier_c``: only the converted plan (``divide_task_converted.json``).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "2.1.0"
SOURCE_PROJECT = "mavis"

WWT_TOOL_CAPABILITIES = {
    "add_circle": "annotation_circle",
    "add_image_fits": "fits_layer",
    "add_line": "annotation_line",
    "center_on_coordinates": "center_on_coordinates",
    "change_solarsystem": "track_object",
    "set_time": "fixed_time",
}

ALLOWED_CAPABILITY_FAMILIES = [
    "celestial_body_radius",
    "conjunction",
    "coordinate_resolution",
    "eclipse",
    "ephemeris",
    "fits_image_analysis",
    "gaia_ivoa",
    "geocoding",
    "inferior_conjunction",
    "light_curve",
    "moon_phase",
    "opposition",
    "occultation",
    "planetary_transit",
    "seasonal_event",
    "simbad",
    "skyview_fits",
    "spectrum",
    "superior_conjunction",
    "venus_elongation",
    "wwt_annotation",
    "wwt_fits",
    "wwt_navigation",
    "wwt_solar_system",
    "wwt_time",
]

# Reference capability family -> manifest capability ids (coverage authority).
FAMILY_CAPABILITY_IDS = {
    "celestial_body_radius": ["mavis.astronomy.body_radius"],
    "conjunction": ["mavis.astronomy.celestial_events"],
    "coordinate_resolution": ["mavis.source.simbad_object"],
    "eclipse": [
        "mavis.astronomy.celestial_events",
        "mavis.astronomy.eclipse_geometry",
    ],
    "ephemeris": ["mavis.astronomy.ephemeris"],
    "fits_image_analysis": [
        "mavis.fits.background_estimation",
        "mavis.fits.source_detection",
        "mavis.fits.centroid",
        "mavis.fits.segmentation",
        "mavis.fits.aperture_photometry",
        "mavis.fits.psf_photometry",
    ],
    "gaia_ivoa": ["mavis.source.gaia_cone"],
    "geocoding": ["mavis.observer.geocoding"],
    "inferior_conjunction": ["mavis.astronomy.celestial_events"],
    "light_curve": ["mavis.light_curve.analysis"],
    "moon_phase": ["mavis.astronomy.celestial_events"],
    "opposition": ["mavis.astronomy.celestial_events"],
    "occultation": ["mavis.astronomy.celestial_events"],
    "planetary_transit": ["mavis.astronomy.celestial_events"],
    "seasonal_event": ["mavis.astronomy.celestial_events"],
    "simbad": ["mavis.source.simbad_object", "mavis.source.simbad_region"],
    "skyview_fits": ["mavis.source.skyview_fits"],
    "spectrum": ["mavis.spectrum.analysis"],
    "superior_conjunction": ["mavis.astronomy.celestial_events"],
    "venus_elongation": ["mavis.astronomy.celestial_events"],
    "wwt_annotation": ["mavis.wwt.scene", "mavis.interaction.wwt_annotation"],
    "wwt_fits": ["mavis.wwt.scene", "mavis.interaction.wwt_layers"],
    "wwt_navigation": ["mavis.wwt.scene", "mavis.interaction.wwt_navigation"],
    "wwt_solar_system": ["mavis.wwt.scene", "mavis.interaction.wwt_navigation"],
    "wwt_time": ["mavis.wwt.scene", "mavis.interaction.wwt_time_control"],
}

ALLOWED_TIERS = ["tier_a", "tier_b", "tier_c"]


@dataclass(frozen=True)
class CaseExtraction:
    case_id: str
    source_path: str
    goal: str
    tier: str
    capability_ids: tuple[str, ...]
    required_inputs: tuple[str, ...]
    expected_outputs: tuple[str, ...]
    live_dependencies: tuple[str, ...]
    verification_requirements: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability_ids": list(self.capability_ids),
            "case_id": self.case_id,
            "expected_outputs": list(self.expected_outputs),
            "goal": self.goal,
            "live_dependencies": list(self.live_dependencies),
            "required_inputs": list(self.required_inputs),
            "source_path": self.source_path,
            "tier": self.tier,
            "verification_requirements": list(self.verification_requirements),
        }


def _clean_goal(case_id: str, tasks: list[str]) -> str:
    filtered = [
        t.strip()
        for t in tasks
        if not any(
            t.strip().startswith(b)
            for b in [
                "提供本地的星历表",
                "获取星历表文件地址",
                "获取本地的星历表",
                "获取FITS图像数据地址",
                "提供FITS图像数据地址",
                "获取原始FITS图像数据地址",
                "提供本地原始FIT",
                "获取原始FITS",
            ]
        )
    ]
    if not filtered:
        filtered = [t.strip() for t in tasks if t.strip()]

    raw_text = "；".join(filtered)
    raw_text = raw_text.replace("在地球观测视图下，", "在WWT地球视图下")
    raw_text = raw_text.replace("在地球视角下，", "在WWT地球视角下")
    raw_text = raw_text.replace("在太阳系视图下，", "在WWT太阳系视图下")
    raw_text = raw_text.replace("在地球视图下", "在WWT地球视图下")
    raw_text = raw_text.replace("，展示时每隔1秒跳转到下一个星体", "并按步跳转")
    raw_text = raw_text.replace("，每1秒自动跳转到下一个", "并按步跳转")
    raw_text = raw_text.replace("，每隔1秒跳转到下一个", "并按步跳转")
    raw_text = re.sub(r"；+", "；", raw_text).strip("； ")

    if len(raw_text) > 100:
        raw_text = raw_text[:97] + "..."
    if not raw_text:
        raw_text = f"MAVIS 基准测试案例 {case_id}"
    return raw_text


def _read_referenced_case_code(
    *,
    case_dir: Path,
    ref_root: Path,
    references: list[str],
) -> str:
    data_root = (ref_root / "mavis" / "data").resolve()
    mavis_root = (ref_root / "mavis").resolve()
    candidates = {
        (mavis_root / Path(reference.replace("\\", "/"))).resolve()
        for reference in references
    }
    candidates.update(path.resolve() for path in (case_dir / "code").glob("*.py"))
    chunks: list[str] = []
    for candidate in sorted(candidates):
        if not candidate.is_relative_to(data_root):
            continue
        if not candidate.is_file():
            continue
        chunks.append(candidate.read_text(encoding="utf-8"))
    return "\n".join(chunks)


def _resolve_tier(case_dir: Path) -> str:
    if (case_dir / "code").is_dir():
        return "tier_a"
    if (case_dir / "file").is_dir() or (case_dir / "image").is_dir():
        return "tier_b"
    return "tier_c"


def parse_benchmark_case(case_id: str, case_dir: Path, ref_root: Path) -> CaseExtraction:
    conv_file = case_dir / "divide_task_converted.json"
    if not conv_file.is_file():
        raise FileNotFoundError(f"Missing {conv_file}")

    source_path = (
        conv_file.relative_to(ref_root).as_posix()
        if conv_file.is_relative_to(ref_root)
        else f"mavis/data/task_benchmark/{case_id}/divide_task_converted.json"
    )

    try:
        steps = json.loads(conv_file.read_text(encoding="utf-8"))
    except Exception as error:
        raise ValueError(f"Failed to parse JSON in {conv_file}: {error}") from error

    if not isinstance(steps, list) or not steps:
        raise ValueError(f"Empty or non-list steps in {conv_file}")

    tools: list[str] = []
    agents: list[str] = []
    tasks: list[str] = []
    code_references: list[str] = []

    for step in steps:
        if not isinstance(step, dict):
            raise ValueError(f"Step is not a dict in {conv_file}")
        agent = step.get("agent", "")
        if agent:
            agents.append(str(agent))
        for t in step.get("tools", []):
            tools.append(str(t))
        for task in step.get("task", []):
            tasks.append(str(task))
        for code_reference in step.get("代码", []):
            code_references.append(str(code_reference))

    code_text = _read_referenced_case_code(
        case_dir=case_dir,
        ref_root=ref_root,
        references=code_references,
    )
    code_calls = set(re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(", code_text))
    tool_set = set(tools) | code_calls
    task_text = " ".join(tasks)

    caps: set[str] = set()
    req_inputs: set[str] = set()
    exp_outputs: set[str] = set()
    live_deps: set[str] = set()
    gates: list[str] = [
        "contract_schema_validation",
        "parameter_boundary_check",
    ]

    # 1. Ephemeris & planetary events
    if "getEphemeris" in tool_set or "skyfield.api.load.at.observe" in tool_set:
        caps.add("ephemeris")
        req_inputs.add("ephemeris_kernel")
        exp_outputs.add("ephemeris_coordinates")
        live_deps.add("skyfield_de421")

    if any(k in task_text for k in ["冲日", "冲"]):
        caps.update({"opposition", "ephemeris"})
        req_inputs.update(["ephemeris_kernel", "target_name", "time_range"])
        exp_outputs.add("celestial_events_list")
        live_deps.add("skyfield_de421")
        gates.append("ephemeris_precision_check")

    if any(k in task_text for k in ["合日", "上合", "下合", "掩", "凌日", "合"]):
        caps.update({"conjunction", "ephemeris"})
        req_inputs.update(["ephemeris_kernel", "target_name", "time_range"])
        exp_outputs.add("celestial_events_list")
        live_deps.add("skyfield_de421")
        gates.append("ephemeris_precision_check")
        if "上合" in task_text or "is_strict_superior_conjunction_event" in tool_set:
            caps.add("superior_conjunction")
        if "下合" in task_text or "is_strict_inferior_conjunction_event" in tool_set:
            caps.add("inferior_conjunction")
        if "掩" in task_text or "is_strict_conjunctions_event" in tool_set:
            caps.add("occultation")
        if "凌日" in task_text:
            caps.add("planetary_transit")

    if (
        any(k in task_text for k in ["日食", "月食", "食"])
        or "calculate_eclipse" in tool_set
        or "skyfield.eclipselib.lunar_eclipses" in tool_set
    ):
        caps.update({"eclipse", "ephemeris"})
        req_inputs.update(["ephemeris_kernel", "time_range"])
        exp_outputs.add("celestial_events_list")
        live_deps.add("skyfield_de421")
        gates.append("ephemeris_precision_check")

    if "大距" in task_text or "find_venus_elongations" in tool_set:
        caps.add("venus_elongation")
        req_inputs.update(["ephemeris_kernel", "time_range"])
        exp_outputs.add("celestial_events_list")
        live_deps.add("skyfield_de421")

    if "月相" in task_text or "moon_phase" in tool_set:
        caps.update({"ephemeris", "moon_phase"})
        req_inputs.update(["ephemeris_kernel", "time_range"])
        exp_outputs.add("celestial_events_list")
        live_deps.add("skyfield_de421")

    if any(k in task_text for k in ["春分", "夏至", "秋分", "冬至"]):
        caps.update({"ephemeris", "seasonal_event"})
        req_inputs.update(["ephemeris_kernel", "time_range"])
        exp_outputs.add("celestial_events_list")
        live_deps.add("skyfield_de421")

    if "get_celestial_body_radius" in tool_set:
        caps.add("celestial_body_radius")
        req_inputs.add("target_name")
        exp_outputs.add("celestial_body_radius")

    if "getLatLongByCityName" in tool_set or any(
        k in task_text for k in ["贵阳", "北京", "经纬度", "观测点"]
    ):
        caps.add("geocoding")
        req_inputs.add("location_name")

    # 2. Simbad & object queries
    if any(t.startswith("Simbad.") for t in tool_set):
        caps.add("simbad")
        live_deps.add("simbad_tap_service")
        gates.append("simbad_mock_fixture_test")
        if "Simbad.query_object" in tool_set:
            caps.add("coordinate_resolution")
            req_inputs.add("target_name")
            exp_outputs.add("simbad_source_collection")
        if (
            "Simbad.query_region" in tool_set
            or "Simbad.add_votable_fields" in tool_set
            or "Simbad.query_objectids" in tool_set
        ):
            req_inputs.update(["ra_degrees", "dec_degrees", "radius_degrees"])
            exp_outputs.add("simbad_source_collection")

    # 3. FITS & photometry
    if (
        "getFits" in tool_set
        or "astropy.io.fits" in tool_set
        or "astropy.visualization" in tool_set
    ):
        caps.add("skyview_fits")
        live_deps.add("skyview_service")
        gates.append("fits_header_validation")
        req_inputs.add("fits_data")
        exp_outputs.add("fits_image_artifact")

    if any(t.startswith("photutils.") for t in tool_set):
        caps.update({"fits_image_analysis", "skyview_fits"})
        req_inputs.add("fits_data")
        exp_outputs.add("fits_photometry_report")
        gates.append("photometry_flux_tolerance_check")

    # “光谱双星” is an object class queried from SIMBAD, not a spectral request.
    if "光谱" in task_text and "光谱双星" not in task_text:
        caps.add("spectrum")
        exp_outputs.add("spectrum_artifact")
    if "光变" in task_text:
        caps.add("light_curve")
        exp_outputs.add("light_curve_artifact")

    # 4. WWT scenes
    if "WWT" in agents or any(
        t in tool_set
        for t in [
            "center_on_coordinates",
            "set_time",
            "add_image_fits",
            "add_circle",
            "add_line",
            "change_solarsystem",
        ]
    ):
        exp_outputs.add("wwt_scene_spec")
        gates.append("wwt_scene_spec_validation")

        if "center_on_coordinates" in tool_set:
            caps.add("wwt_navigation")
            req_inputs.update(["view.center.ra_hours", "view.center.dec_degrees"])
        if "set_time" in tool_set:
            caps.add("wwt_time")
            req_inputs.add("time.observed_at")
        if "add_image_fits" in tool_set:
            caps.add("wwt_fits")
            req_inputs.add("fits_layers[].content_address")
        if "add_circle" in tool_set or "add_line" in tool_set:
            caps.add("wwt_annotation")
            req_inputs.add("annotations")
        if "change_solarsystem" in tool_set:
            caps.add("wwt_solar_system")
            req_inputs.add("view.target")
        for tool_name, capability in WWT_TOOL_CAPABILITIES.items():
            if tool_name in tool_set:
                gates.append(f"wwt_{capability}_renderer")

    if not caps:
        caps.add("ephemeris")

    if not live_deps:
        live_deps.add("none")

    for family in caps:
        if family not in ALLOWED_CAPABILITY_FAMILIES:
            raise ValueError(f"Unknown capability family {family} in case {case_id}")

    capability_ids: set[str] = set()
    for family in caps:
        capability_ids.update(FAMILY_CAPABILITY_IDS[family])

    return CaseExtraction(
        case_id=case_id,
        source_path=source_path,
        goal=_clean_goal(case_id, tasks),
        tier=_resolve_tier(case_dir),
        capability_ids=tuple(sorted(capability_ids)),
        required_inputs=tuple(sorted(req_inputs)),
        expected_outputs=tuple(sorted(exp_outputs)),
        live_dependencies=tuple(sorted(live_deps)),
        verification_requirements=tuple(dict.fromkeys(gates)),
    )


def build_ledger(reference_root: Path) -> dict[str, Any]:
    bench_dir = reference_root / "mavis" / "data" / "task_benchmark"
    if not bench_dir.is_dir():
        raise FileNotFoundError(
            f"Benchmark directory not found: {bench_dir}. "
            "Please specify a valid --reference-root."
        )

    case_dirs = sorted(
        [d for d in bench_dir.iterdir() if d.is_dir()], key=lambda p: p.name
    )
    if not case_dirs:
        raise ValueError(
            f"Expected at least one benchmark case in {bench_dir}, found none"
        )

    cases: list[CaseExtraction] = []
    seen_ids: set[str] = set()
    for c_dir in case_dirs:
        case_id = c_dir.name
        if case_id in seen_ids:
            raise ValueError(f"Duplicate case_id found: {case_id}")
        seen_ids.add(case_id)
        cases.append(parse_benchmark_case(case_id, c_dir, reference_root))

    cases.sort(key=lambda c: c.case_id)

    hash_lines = [f"{c.source_path}\n" for c in cases]
    source_set_hash = hashlib.sha256("".join(hash_lines).encode("utf-8")).hexdigest()

    tier_counts = {tier: 0 for tier in ALLOWED_TIERS}
    for case in cases:
        tier_counts[case.tier] += 1

    return {
        "allowed_capability_families": ALLOWED_CAPABILITY_FAMILIES,
        "allowed_tiers": ALLOWED_TIERS,
        "by_tier": tier_counts,
        "case_count": len(cases),
        "cases": [c.to_dict() for c in cases],
        "generated_from_count": len(cases),
        "schema_version": SCHEMA_VERSION,
        "source_project": SOURCE_PROJECT,
        "source_set_hash": source_set_hash,
    }


def serialize_ledger_json(data: dict[str, Any]) -> str:
    encoded = json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True)
    return encoded + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the MAVIS benchmark case index")
    parser.add_argument(
        "--reference-root",
        type=Path,
        default=None,
        help=(
            "Path to reference repository root "
            "(defaults to the MAVIS_REFERENCE_ROOT environment variable)"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("services/reference_integration/mavis_adoption_ledger.json"),
        help="Path to output the benchmark case index JSON",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check existing ledger file against generated data without writing",
    )

    args = parser.parse_args()

    reference_root = args.reference_root
    if reference_root is None:
        env_root = os.environ.get("MAVIS_REFERENCE_ROOT")
        if not env_root:
            print(
                "ERROR: --reference-root or the MAVIS_REFERENCE_ROOT environment "
                "variable must point at the reference repository root"
            )
            return 2
        reference_root = Path(env_root)

    try:
        ledger_data = build_ledger(reference_root)
        new_content = serialize_ledger_json(ledger_data)
    except Exception as error:
        print(f"ERROR: Failed to build MAVIS benchmark case index: {error}")
        return 1

    if args.check:
        if not args.output.is_file():
            print(f"ERROR: Output file does not exist for check: {args.output}")
            return 1
        existing_content = args.output.read_bytes().decode("utf-8")
        if existing_content != new_content:
            print(
                f"ERROR: Benchmark case index on disk does not match built index at {args.output}"
            )
            return 1
        print(
            f"CHECK OK: MAVIS benchmark case index is consistent"
            f" ({ledger_data['case_count']} cases, tiers={ledger_data['by_tier']})."
        )
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(new_content.encode("utf-8"))
    print(
        f"SUCCESS: Generated MAVIS benchmark case index with"
        f" {ledger_data['case_count']} cases to {args.output}"
    )
    print(f"Tiers: {ledger_data['by_tier']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
