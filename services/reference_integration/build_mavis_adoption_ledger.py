"""Build and validate the MAVIS 160-case migration adoption ledger.

This script parses all 160 benchmark cases from the MAVIS reference project,
extracts minimal necessary facts, maps them to xingwen-astro-ai capabilities,
computes deterministic hashes, and produces/checks the machine-readable ledger.
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

from services.scientific_skills.wwt_capabilities import WWT_CAPABILITY_MATRIX


SCHEMA_VERSION = "1.1.0"
SOURCE_PROJECT = "mavis"
EXPECTED_CASE_COUNT = 160

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
    "weather",
    "wwt_annotation",
    "wwt_fits",
    "wwt_navigation",
    "wwt_solar_system",
    "wwt_time",
]

ALLOWED_ADOPTION_STATES = [
    "excluded",
    "implemented_unverified",
    "implemented_verified",
    "planned",
]

ALLOWED_EXCLUSION_REASONS = [
    "arbitrary_python_execution",
    "browser_remote_control_websocket",
    "hardcoded_credentials",
    "hardcoded_personal_paths",
    "legacy_sse_transport",
    "recursive_self_correction",
    "screenshot_polling",
]


@dataclass(frozen=True)
class CaseExtraction:
    case_id: str
    source_path: str
    source_sha256: str
    concise_goal: str
    capability_families: list[str]
    required_inputs: list[str]
    expected_outputs: list[str]
    live_dependencies: list[str]
    reference_runtime_mechanisms: list[str]
    target_xingwen_surfaces: list[str]
    adoption_state: str
    exclusion_reasons: list[str]
    verification_gates: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "adoption_state": self.adoption_state,
            "capability_families": self.capability_families,
            "case_id": self.case_id,
            "concise_goal": self.concise_goal,
            "exclusion_reasons": self.exclusion_reasons,
            "expected_outputs": self.expected_outputs,
            "live_dependencies": self.live_dependencies,
            "reference_runtime_mechanisms": self.reference_runtime_mechanisms,
            "required_inputs": self.required_inputs,
            "source_path": self.source_path,
            "source_sha256": self.source_sha256,
            "target_xingwen_surfaces": self.target_xingwen_surfaces,
            "verification_gates": self.verification_gates,
        }


def _clean_concise_goal(case_id: str, tasks: list[str]) -> str:
    # Filter out pure boilerplate data acquisition phrases
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
    # Normalize common view descriptions
    raw_text = raw_text.replace("在地球观测视图下，", "在WWT地球视图下")
    raw_text = raw_text.replace("在地球视角下，", "在WWT地球视角下")
    raw_text = raw_text.replace("在太阳系视图下，", "在WWT太阳系视图下")
    raw_text = raw_text.replace("在地球视图下", "在WWT地球视图下")
    raw_text = raw_text.replace("，展示时每隔1秒跳转到下一个星体", "并按步跳转")
    raw_text = raw_text.replace("，每1秒自动跳转到下一个", "并按步跳转")
    raw_text = raw_text.replace("，每隔1秒跳转到下一个", "并按步跳转")

    # Clean whitespace and multiple semicolons
    raw_text = re.sub(r"；+", "；", raw_text).strip("； ")

    if len(raw_text) > 100:
        raw_text = raw_text[:97] + "..."
    if not raw_text:
        raw_text = f"MAVIS 基准测试案例 {case_id}"
    return raw_text


def _read_referenced_case_code(
    *,
    case_id: str,
    case_dir: Path,
    ref_root: Path,
    references: list[str],
) -> str:
    """Read only code explicitly referenced by one benchmark case.

    ``divide_task_converted.json`` often lists environment helpers such as
    ``getEphemeris`` while the referenced source contains the scientifically
    relevant call (for example ``get_celestial_body_radius``).  Confining reads
    to the MAVIS data tree keeps capability extraction auditable and prevents a
    malformed reference from escaping the source corpus.  Some MAVIS cases
    intentionally or accidentally reuse code from another case directory, so
    confinement to ``case_dir`` would reject source that the reference runtime
    itself resolves.
    """

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
            raise ValueError(
                f"Code reference escapes MAVIS data tree for {case_id}: {candidate}"
            )
        if not candidate.is_file():
            # Some converted records reference transient ``data/task`` output
            # that is not part of the retained benchmark source.  The case's
            # own ``code/*.py`` files remain the authoritative reusable source.
            continue
        chunks.append(candidate.read_text(encoding="utf-8"))
    return "\n".join(chunks)


def parse_benchmark_case(
    case_id: str, case_dir: Path, ref_root: Path
) -> CaseExtraction:
    conv_file = case_dir / "divide_task_converted.json"
    if not conv_file.is_file():
        raise FileNotFoundError(f"Missing {conv_file}")

    raw_bytes = conv_file.read_bytes()
    source_sha256 = hashlib.sha256(raw_bytes).hexdigest()
    source_path = (
        conv_file.relative_to(ref_root).as_posix()
        if conv_file.is_relative_to(ref_root)
        else f"mavis/data/task_benchmark/{case_id}/divide_task_converted.json"
    )

    try:
        steps = json.loads(raw_bytes.decode("utf-8"))
    except Exception as error:
        raise ValueError(f"Failed to parse JSON in {conv_file}: {error}") from error

    if not isinstance(steps, list) or not steps:
        raise ValueError(f"Empty or non-list steps in {conv_file}")

    tools: list[str] = []
    agents: list[str] = []
    tasks: list[str] = []
    code_references: list[str] = []
    has_file_intro = False
    has_code_file = False

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
        if step.get("文件介绍"):
            has_file_intro = True
        for code_reference in step.get("代码", []):
            code_references.append(str(code_reference))
        if step.get("代码"):
            has_code_file = True

    code_text = _read_referenced_case_code(
        case_id=case_id,
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
    ref_mechs: set[str] = {
        "arbitrary_python_execution",
        "recursive_self_correction",
    }
    excl_reasons: set[str] = {
        "arbitrary_python_execution",
        "recursive_self_correction",
    }
    targets: list[str] = []
    gates: list[str] = [
        "contract_schema_validation",
        "parameter_boundary_check",
    ]

    # 1. Ephemeris & Planets
    if "getEphemeris" in tool_set or "skyfield.api.load.at.observe" in tool_set:
        caps.add("ephemeris")
        req_inputs.add("ephemeris_kernel")
        exp_outputs.add("ephemeris_coordinates")
        live_deps.add("skyfield_de421")
        targets.append("services/scientific_skills/astronomy.py:calculate_ephemeris")

    if any(k in task_text for k in ["冲日", "冲"]):
        caps.add("opposition")
        caps.add("ephemeris")
        req_inputs.update(["ephemeris_kernel", "target_name", "time_range"])
        exp_outputs.add("celestial_events_list")
        live_deps.add("skyfield_de421")
        targets.append("services/scientific_skills/astronomy.py:find_celestial_events")
        gates.append("ephemeris_precision_check")

    if any(k in task_text for k in ["合日", "上合", "下合", "掩", "凌日", "合"]):
        caps.add("conjunction")
        caps.add("ephemeris")
        req_inputs.update(["ephemeris_kernel", "target_name", "time_range"])
        exp_outputs.add("celestial_events_list")
        live_deps.add("skyfield_de421")
        targets.append("services/scientific_skills/astronomy.py:find_celestial_events")
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
        caps.add("eclipse")
        caps.add("ephemeris")
        req_inputs.update(["ephemeris_kernel", "time_range"])
        exp_outputs.add("celestial_events_list")
        live_deps.add("skyfield_de421")
        targets.append("services/scientific_skills/astronomy.py:find_celestial_events")
        gates.append("ephemeris_precision_check")

    if "大距" in task_text or "find_venus_elongations" in tool_set:
        caps.add("venus_elongation")
        req_inputs.update(["ephemeris_kernel", "time_range"])
        exp_outputs.add("celestial_events_list")
        live_deps.add("skyfield_de421")
        targets.append("services/scientific_skills/astronomy.py:find_celestial_events")

    if "月相" in task_text or "moon_phase" in tool_set:
        caps.update({"ephemeris", "moon_phase"})
        req_inputs.update(["ephemeris_kernel", "time_range"])
        exp_outputs.add("celestial_events_list")
        live_deps.add("skyfield_de421")
        targets.append("services/scientific_skills/astronomy.py:find_celestial_events")

    if any(k in task_text for k in ["春分", "夏至", "秋分", "冬至"]):
        caps.update({"ephemeris", "seasonal_event"})
        req_inputs.update(["ephemeris_kernel", "time_range"])
        exp_outputs.add("celestial_events_list")
        live_deps.add("skyfield_de421")
        targets.append("services/scientific_skills/astronomy.py:find_celestial_events")

    if "get_celestial_body_radius" in tool_set:
        caps.add("celestial_body_radius")
        req_inputs.add("target_name")
        exp_outputs.add("celestial_body_radius")
        targets.append(
            "services/scientific_skills/astronomy.py:get_celestial_body_radius"
        )

    if "getLatLongByCityName" in tool_set or any(
        k in task_text for k in ["贵阳", "北京", "经纬度", "观测点"]
    ):
        caps.add("geocoding")
        req_inputs.add("location_name")
        live_deps.add("nominatim_openstreetmap")
        targets.append("services/scientific_skills/astronomy.py:_observer_coordinates")
        excl_reasons.add("hardcoded_credentials")
        ref_mechs.add("hardcoded_credentials")

    # 2. Simbad & Objects
    if any(t.startswith("Simbad.") for t in tool_set):
        caps.add("simbad")
        live_deps.add("simbad_tap_service")
        targets.append("services/scientific_skills/astronomy.py:query_simbad")
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

    # 3. FITS & Photometry
    if (
        "getFits" in tool_set
        or "astropy.io.fits" in tool_set
        or "astropy.visualization" in tool_set
    ):
        caps.add("skyview_fits")
        live_deps.add("skyview_service")
        targets.append("services/scientific_skills/astronomy.py:retrieve_skyview_fits")
        gates.append("fits_header_validation")
        req_inputs.add("fits_data")
        exp_outputs.add("fits_image_artifact")

    if any(t.startswith("photutils.") for t in tool_set):
        caps.add("fits_image_analysis")
        caps.add("skyview_fits")
        req_inputs.add("fits_data")
        exp_outputs.add("fits_photometry_report")
        targets.append("services/scientific_skills/astronomy.py:analyze_fits_image")
        gates.append("photometry_flux_tolerance_check")

    # “光谱双星” is an astronomical object class queried from SIMBAD; it is
    # not a request for wavelength/flux acquisition or spectral analysis.
    if "光谱" in task_text and "光谱双星" not in task_text:
        caps.add("spectrum")
        exp_outputs.add("spectrum_artifact")
    if "光变" in task_text:
        caps.add("light_curve")
        exp_outputs.add("light_curve_artifact")

    # 4. WWT Visualization
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
        ref_mechs.add("browser_remote_control_websocket")
        excl_reasons.add("browser_remote_control_websocket")
        targets.append("services/scientific_skills/astronomy.py:build_wwt_scene")
        targets.append(
            "apps/api/src/app/schemas/scientific_skills.py:WwtSceneVisualizationSpec"
        )
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

    if (
        has_file_intro
        or has_code_file
        or "data/task_benchmark" in str(steps)
        or "data/output" in str(steps)
    ):
        ref_mechs.add("hardcoded_personal_paths")
        excl_reasons.add("hardcoded_personal_paths")

    if "WWT" in agents:
        ref_mechs.add("screenshot_polling")
        excl_reasons.add("screenshot_polling")

    if not caps:
        caps.add("ephemeris")

    if not live_deps:
        live_deps.add("none")

    # Planned vs Implemented unverified
    is_planned = False
    if "spectrum" in caps or "light_curve" in caps or "gaia_ivoa" in caps:
        is_planned = True
    required_wwt_capabilities = {
        capability
        for tool_name, capability in WWT_TOOL_CAPABILITIES.items()
        if tool_name in tool_set
    }
    if any(
        WWT_CAPABILITY_MATRIX[capability]["renderer"] == "unsupported"
        for capability in required_wwt_capabilities
    ):
        is_planned = True

    adoption_state = "planned" if is_planned else "implemented_unverified"

    # Validation of fields
    for c in caps:
        if c not in ALLOWED_CAPABILITY_FAMILIES:
            raise ValueError(f"Unknown capability family {c} in case {case_id}")
    for r in excl_reasons:
        if r not in ALLOWED_EXCLUSION_REASONS:
            raise ValueError(f"Unknown exclusion reason {r} in case {case_id}")
    if adoption_state not in ALLOWED_ADOPTION_STATES:
        raise ValueError(f"Unknown adoption state {adoption_state} in case {case_id}")
    if not targets:
        raise ValueError(f"Empty target surfaces in case {case_id}")
    if not gates:
        raise ValueError(f"Empty verification gates in case {case_id}")

    concise_goal = _clean_concise_goal(case_id, tasks)

    return CaseExtraction(
        case_id=case_id,
        source_path=source_path,
        source_sha256=source_sha256,
        concise_goal=concise_goal,
        capability_families=sorted(caps),
        required_inputs=sorted(req_inputs),
        expected_outputs=sorted(exp_outputs),
        live_dependencies=sorted(live_deps),
        reference_runtime_mechanisms=sorted(ref_mechs),
        target_xingwen_surfaces=sorted(list(dict.fromkeys(targets))),
        adoption_state=adoption_state,
        exclusion_reasons=sorted(excl_reasons),
        verification_gates=sorted(list(dict.fromkeys(gates))),
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
    if len(case_dirs) != EXPECTED_CASE_COUNT:
        raise ValueError(
            f"Expected exactly {EXPECTED_CASE_COUNT} benchmark cases in {bench_dir}, "
            f"found {len(case_dirs)}"
        )

    cases: list[CaseExtraction] = []
    seen_ids: set[str] = set()
    seen_paths: set[str] = set()

    for c_dir in case_dirs:
        case_id = c_dir.name
        if case_id in seen_ids:
            raise ValueError(f"Duplicate case_id found: {case_id}")
        seen_ids.add(case_id)

        case = parse_benchmark_case(case_id, c_dir, reference_root)
        if case.source_path in seen_paths:
            raise ValueError(f"Duplicate source_path found: {case.source_path}")
        seen_paths.add(case.source_path)
        cases.append(case)

    # Sort cases stably by case_id
    cases.sort(key=lambda c: c.case_id)

    # Calculate source_set_hash
    hash_lines = [f"{c.source_path}:{c.source_sha256}\n" for c in cases]
    source_set_hash = hashlib.sha256("".join(hash_lines).encode("utf-8")).hexdigest()

    # Calculate summary counts
    state_counts: dict[str, int] = {state: 0 for state in ALLOWED_ADOPTION_STATES}
    cap_counts: dict[str, int] = {cap: 0 for cap in ALLOWED_CAPABILITY_FAMILIES}
    excl_counts: dict[str, int] = {reason: 0 for reason in ALLOWED_EXCLUSION_REASONS}

    for c in cases:
        state_counts[c.adoption_state] += 1
        for cap in c.capability_families:
            cap_counts[cap] += 1
        for reason in c.exclusion_reasons:
            excl_counts[reason] += 1

    summary = {
        "by_adoption_state": state_counts,
        "by_capability_family": cap_counts,
        "by_exclusion_reason": excl_counts,
        "total_cases": len(cases),
    }

    return {
        "allowed_adoption_states": ALLOWED_ADOPTION_STATES,
        "allowed_capability_families": ALLOWED_CAPABILITY_FAMILIES,
        "allowed_exclusion_reasons": ALLOWED_EXCLUSION_REASONS,
        "cases": [c.to_dict() for c in cases],
        "generated_from_count": len(cases),
        "schema_version": SCHEMA_VERSION,
        "source_project": SOURCE_PROJECT,
        "source_set_hash": source_set_hash,
        "summary": summary,
        "wwt_capability_matrix": {
            capability: dict(disposition)
            for capability, disposition in sorted(WWT_CAPABILITY_MATRIX.items())
        },
    }


def serialize_ledger_json(data: dict[str, Any]) -> str:
    # Deterministic JSON serialization: 2 space indent, sorted keys, UTF-8 LF
    encoded = json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True)
    return encoded + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build or check MAVIS adoption ledger")
    parser.add_argument(
        "--reference-root",
        type=Path,
        default=Path(
            os.environ.get("MAVIS_REFERENCE_ROOT", r"E:\xingwen-astro-ai-reference")
        ),
        help="Path to reference repository root",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("services/reference_integration/mavis_adoption_ledger.json"),
        help="Path to output adoption ledger JSON",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check existing ledger file against generated data without writing",
    )

    args = parser.parse_args()

    try:
        ledger_data = build_ledger(args.reference_root)
        new_content = serialize_ledger_json(ledger_data)
    except Exception as error:
        print(f"ERROR: Failed to build MAVIS adoption ledger: {error}")
        return 1

    if args.check:
        if not args.output.is_file():
            print(f"ERROR: Output file does not exist for check: {args.output}")
            return 1
        existing_content = args.output.read_bytes().decode("utf-8")
        if existing_content != new_content:
            print(
                f"ERROR: Adoption ledger on disk does not match built ledger at {args.output}"
            )
            return 1
        print(
            f"CHECK OK: Adoption ledger is consistent ({ledger_data['generated_from_count']} cases, hash={ledger_data['source_set_hash'][:8]})."
        )
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(new_content.encode("utf-8"))
    print(
        f"SUCCESS: Generated MAVIS adoption ledger with {ledger_data['generated_from_count']} cases to {args.output}"
    )
    print(f"Source set hash: {ledger_data['source_set_hash']}")
    print(f"Summary by state: {ledger_data['summary']['by_adoption_state']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
