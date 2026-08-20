"""Fail-closed registry for typed scientific skills.

``ScientificSkillDefinition`` projects the single capability authoring source
(:mod:`app.schemas.scientific_capabilities`) into the runtime registry:
its workflow phase, accepted and produced kinds, parameter model, workload
class and long-term domain flags. Downstream modules (planning, run-plan
compilation, contract admission, benchmarks) read descriptors from that source
instead of re-listing skill ids by hand.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from time import monotonic
from typing import Literal

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.core import ScientificSkillId
from app.schemas.scientific_capabilities import (
    CAPABILITY_DESCRIPTORS,
    CapabilityParameter,
)

from .types import ScientificSkillRequest, ScientificSkillResult


ScientificSkillHandler = Callable[[ScientificSkillRequest], dict[str, object]]
WorkloadClass = Literal["cpu_light", "cpu_heavy", "memory_heavy", "network"]
ParameterKind = Literal[
    "string", "number", "integer", "boolean", "rows", "string_list"
]


@dataclass(frozen=True, slots=True)
class SkillParameterDescriptor:
    name: str
    kind: ParameterKind
    required: bool
    description: str = ""


@dataclass(frozen=True, slots=True)
class ScientificSkillDefinition:
    skill_id: ScientificSkillId
    revision: str
    phase: str
    accepted_input_kinds: tuple[str, ...]
    produced_artifact_kinds: tuple[str, ...]
    label: str = ""
    description: str = ""
    parameter_model: tuple[SkillParameterDescriptor, ...] = field(default=())
    workload_class: WorkloadClass = "cpu_light"
    requires_dataset_prerequisite: bool = False
    produces_source_snapshot: bool = False
    handler: ScientificSkillHandler | None = None


class ScientificSkillRegistry:
    """One deep execution seam hiding algorithms and third-party libraries."""

    def __init__(self, definitions: Iterable[ScientificSkillDefinition]) -> None:
        registry: dict[ScientificSkillId, ScientificSkillDefinition] = {}
        for definition in definitions:
            if definition.skill_id in registry:
                raise ValueError(f"duplicate scientific skill: {definition.skill_id}")
            registry[definition.skill_id] = definition
        self._definitions = registry

    @property
    def skill_ids(self) -> tuple[ScientificSkillId, ...]:
        return tuple(sorted(self._definitions, key=str))

    @property
    def definitions(self) -> tuple[ScientificSkillDefinition, ...]:
        return tuple(self._definitions[skill_id] for skill_id in self.skill_ids)

    def definition_for(self, skill_id: ScientificSkillId) -> ScientificSkillDefinition:
        definition = self._definitions.get(skill_id)
        if definition is None:
            raise ValueError(f"unregistered scientific skill: {skill_id}")
        return definition

    def revision_for(self, skill_id: ScientificSkillId) -> str:
        return self.definition_for(skill_id).revision

    def phase_for(self, skill_id: ScientificSkillId) -> str:
        return self.definition_for(skill_id).phase

    def execute(self, request: ScientificSkillRequest) -> ScientificSkillResult:
        definition = self.definition_for(request.skill_id)
        if definition.handler is None:
            raise ValueError(f"scientific skill has no handler: {request.skill_id}")
        started = monotonic()
        output = definition.handler(request)
        elapsed = monotonic() - started
        if elapsed > request.budget.timeout_seconds:
            raise TimeoutError(
                f"scientific skill exceeded {request.budget.timeout_seconds}s budget"
            )
        if not isinstance(output, dict):
            raise TypeError("scientific skill handler must return an object")
        return ScientificSkillResult(
            request_id=request.request_id,
            skill_id=request.skill_id,
            skill_revision=definition.revision,
            status="completed",
            output=output,
            source_snapshot_ids=tuple(
                item.source_snapshot_id for item in request.source_references
            ),
            input_hash=request.input_hash,
            output_hash=compute_canonical_payload_hash(output),
        )


def _parameter_descriptors(
    parameters: Iterable[CapabilityParameter],
) -> tuple[SkillParameterDescriptor, ...]:
    return tuple(
        SkillParameterDescriptor(
            name=name, kind=kind, required=required, description=description  # type: ignore[arg-type]
        )
        for name, kind, required, description in parameters
    )


def build_scientific_skill_registry() -> ScientificSkillRegistry:
    """Build the production registry; imports stay lazy at this composition root."""

    from .astronomy import (
        analyze_fits_image,
        build_wwt_scene,
        calculate_ephemeris,
        find_celestial_events,
        query_simbad,
        retrieve_skyview_fits,
    )
    from .data_analysis import (
        analyze_correlations,
        analyze_statistics,
        build_data_profile,
        build_visualization,
        run_catalog_crossmatch,
    )
    from .astro_series import analyze_light_curve, analyze_spectrum
    from .astro_acquisition import (
        acquire_and_analyze_mast_light_curve,
        acquire_and_analyze_sdss_spectrum,
        query_gaia_dr3,
        query_vizier_tap,
    )
    from .modeling import (
        classify_images,
        classify_time_series,
        evaluate_tabular_model,
        forecast_time_series,
    )
    from .inference import run_model_inference
    from .unsupervised import detect_anomalies, run_clustering

    handlers: dict[ScientificSkillId, ScientificSkillHandler] = {
        ScientificSkillId.catalog_crossmatch: run_catalog_crossmatch,
        ScientificSkillId.data_profile: build_data_profile,
        ScientificSkillId.statistical_analysis: analyze_statistics,
        ScientificSkillId.correlation_analysis: analyze_correlations,
        ScientificSkillId.clustering_analysis: run_clustering,
        ScientificSkillId.anomaly_detection: detect_anomalies,
        ScientificSkillId.chart_visualization: build_visualization,
        ScientificSkillId.simbad_lookup: query_simbad,
        ScientificSkillId.skyview_fits: retrieve_skyview_fits,
        ScientificSkillId.ephemeris: calculate_ephemeris,
        ScientificSkillId.celestial_events: find_celestial_events,
        ScientificSkillId.gaia_cone_search: query_gaia_dr3,
        ScientificSkillId.vizier_tap: query_vizier_tap,
        ScientificSkillId.fits_image_analysis: analyze_fits_image,
        ScientificSkillId.spectrum_analysis: analyze_spectrum,
        ScientificSkillId.spectrum_acquisition: acquire_and_analyze_sdss_spectrum,
        ScientificSkillId.light_curve_analysis: analyze_light_curve,
        ScientificSkillId.light_curve_acquisition: acquire_and_analyze_mast_light_curve,
        ScientificSkillId.tabular_machine_learning: evaluate_tabular_model,
        ScientificSkillId.time_series_classification: classify_time_series,
        ScientificSkillId.time_series_forecast: forecast_time_series,
        ScientificSkillId.image_classification: classify_images,
        ScientificSkillId.model_inference: run_model_inference,
        ScientificSkillId.wwt_scene: build_wwt_scene,
    }

    descriptor_ids = {skill.value for skill in ScientificSkillId}
    if set(CAPABILITY_DESCRIPTORS) != descriptor_ids:
        missing = descriptor_ids - set(CAPABILITY_DESCRIPTORS)
        extra = set(CAPABILITY_DESCRIPTORS) - descriptor_ids
        raise ValueError(
            "capability descriptors must cover every registered skill exactly: "
            f"missing={sorted(missing)} extra={sorted(extra)}"
        )
    missing = set(handlers) - set(CAPABILITY_DESCRIPTORS)
    if missing:
        raise ValueError(f"skills without descriptors: {sorted(map(str, missing))}")
    extra = set(CAPABILITY_DESCRIPTORS) - set(handlers)
    if extra:
        raise ValueError(f"descriptors without handlers: {sorted(map(str, extra))}")

    return ScientificSkillRegistry(
        ScientificSkillDefinition(
            skill_id=skill_id,
            revision="1.2.0",
            phase=str(descriptor["phase"]),
            label=str(descriptor["label"]),
            description=str(descriptor["description"]),
            accepted_input_kinds=tuple(
                str(kind) for kind in descriptor["accepted_input_kinds"]  # type: ignore[union-attr]
            ),
            produced_artifact_kinds=tuple(
                str(kind) for kind in descriptor["produced_artifact_kinds"]  # type: ignore[union-attr]
            ),
            parameter_model=_parameter_descriptors(
                descriptor["parameters"]  # type: ignore[arg-type]
            ),
            workload_class=descriptor["workload_class"],  # type: ignore[arg-type]
            requires_dataset_prerequisite=bool(
                descriptor["requires_dataset_prerequisite"]
            ),
            produces_source_snapshot=bool(descriptor["produces_source_snapshot"]),
            handler=handler,
        )
        for skill_id, handler in handlers.items()
        for descriptor in (CAPABILITY_DESCRIPTORS[skill_id.value],)
    )


__all__ = [
    "ScientificSkillDefinition",
    "ScientificSkillRegistry",
    "SkillParameterDescriptor",
    "build_scientific_skill_registry",
]
