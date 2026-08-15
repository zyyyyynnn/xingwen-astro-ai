"""Fail-closed registry for typed scientific skills.

``ScientificSkillDefinition`` is the single capability-description source for
one skill: its workflow phase, accepted and produced kinds, parameter model,
and workload class.  Downstream modules (planning, benchmarks, schemas) read
descriptors from here instead of re-listing skill ids by hand.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from time import monotonic
from typing import Literal

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.core import ScientificSkillId

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
    parameter_model: tuple[SkillParameterDescriptor, ...] = field(default=())
    workload_class: WorkloadClass = "cpu_light"
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


def _p(
    name: str,
    kind: ParameterKind,
    *,
    required: bool = False,
    description: str = "",
) -> SkillParameterDescriptor:
    return SkillParameterDescriptor(
        name=name, kind=kind, required=required, description=description
    )


_ACQUISITION = ("celestial_source_table",)
_ROWS = ("tabular_rows",)


_DESCRIPTORS: dict[ScientificSkillId, dict[str, object]] = {
    ScientificSkillId.catalog_crossmatch: {
        "phase": "analyzing_data",
        "accepted_input_kinds": ("crossmatch_input",),
        "produced_artifact_kinds": ("aligned_source_records",),
        "parameter_model": (_p("crossmatch_input", "rows", required=True),),
        "workload_class": "cpu_heavy",
    },
    ScientificSkillId.data_profile: {
        "phase": "analyzing_data",
        "accepted_input_kinds": _ROWS,
        "produced_artifact_kinds": ("analysis_report",),
        "parameter_model": (_p("rows", "rows", required=True),),
        "workload_class": "cpu_light",
    },
    ScientificSkillId.statistical_analysis: {
        "phase": "analyzing_data",
        "accepted_input_kinds": _ROWS,
        "produced_artifact_kinds": ("analysis_report",),
        "parameter_model": (
            _p("rows", "rows", required=True),
            _p("fields", "string_list"),
            _p("hypothesis_tests", "rows"),
            _p("alpha", "number"),
        ),
        "workload_class": "cpu_light",
    },
    ScientificSkillId.correlation_analysis: {
        "phase": "analyzing_data",
        "accepted_input_kinds": _ROWS,
        "produced_artifact_kinds": ("analysis_report",),
        "parameter_model": (
            _p("rows", "rows", required=True),
            _p("fields", "string_list", required=True),
            _p("method", "string"),
        ),
        "workload_class": "cpu_light",
    },
    ScientificSkillId.clustering_analysis: {
        "phase": "analyzing_data",
        "accepted_input_kinds": _ROWS,
        "produced_artifact_kinds": ("analysis_report", "visualization"),
        "parameter_model": (
            _p("rows", "rows", required=True),
            _p("feature_fields", "string_list", required=True),
            _p("algorithm", "string"),
            _p("cluster_count", "integer"),
            _p("eps", "number"),
            _p("min_samples", "integer"),
            _p("random_seed", "integer"),
        ),
        "workload_class": "cpu_heavy",
    },
    ScientificSkillId.anomaly_detection: {
        "phase": "analyzing_data",
        "accepted_input_kinds": _ROWS,
        "produced_artifact_kinds": ("analysis_report", "visualization"),
        "parameter_model": (
            _p("rows", "rows", required=True),
            _p("feature_fields", "string_list", required=True),
            _p("algorithm", "string"),
            _p("contamination", "number"),
            _p("z_threshold", "number"),
            _p("random_seed", "integer"),
        ),
        "workload_class": "cpu_heavy",
    },
    ScientificSkillId.chart_visualization: {
        "phase": "building_visualizations",
        "accepted_input_kinds": _ROWS,
        "produced_artifact_kinds": ("visualization",),
        "parameter_model": (
            _p("rows", "rows", required=True),
            _p("x_field", "string", required=True),
            _p("y_field", "string", required=True),
            _p("mark", "string"),
            _p("title", "string"),
            _p("series_label", "string"),
        ),
        "workload_class": "cpu_light",
    },
    ScientificSkillId.simbad_lookup: {
        "phase": "acquiring_observations",
        "accepted_input_kinds": ("target_name", "sky_coordinates"),
        "produced_artifact_kinds": _ACQUISITION,
        "parameter_model": (
            _p("target", "string"),
            _p("ra_degrees", "number"),
            _p("dec_degrees", "number"),
            _p("radius_degrees", "number"),
        ),
        "workload_class": "network",
    },
    ScientificSkillId.skyview_fits: {
        "phase": "acquiring_observations",
        "accepted_input_kinds": ("sky_coordinates",),
        "produced_artifact_kinds": ("fits_image",),
        "parameter_model": (
            _p("ra_degrees", "number"),
            _p("dec_degrees", "number"),
            _p("radius_degrees", "number"),
            _p("survey", "string"),
        ),
        "workload_class": "network",
    },
    ScientificSkillId.ephemeris: {
        "phase": "acquiring_observations",
        "accepted_input_kinds": ("target_name", "time_range"),
        "produced_artifact_kinds": ("ephemeris_coordinates",),
        "parameter_model": (
            _p("target", "string"),
            _p("observed_at", "string"),
            _p("latitude_degrees", "number"),
            _p("longitude_degrees", "number"),
        ),
        "workload_class": "cpu_light",
    },
    ScientificSkillId.celestial_events: {
        "phase": "acquiring_observations",
        "accepted_input_kinds": ("target_name", "time_range"),
        "produced_artifact_kinds": ("celestial_events_list",),
        "parameter_model": (
            _p("event_type", "string"),
            _p("target", "string"),
            _p("start_at", "string"),
            _p("end_at", "string"),
            _p("latitude_degrees", "number"),
            _p("longitude_degrees", "number"),
        ),
        "workload_class": "cpu_light",
    },
    ScientificSkillId.gaia_cone_search: {
        "phase": "acquiring_observations",
        "accepted_input_kinds": ("sky_coordinates",),
        "produced_artifact_kinds": _ACQUISITION,
        "parameter_model": (
            _p("ra_degrees", "number", required=True),
            _p("dec_degrees", "number", required=True),
            _p("radius_degrees", "number", required=True),
        ),
        "workload_class": "network",
    },
    ScientificSkillId.vizier_tap: {
        "phase": "acquiring_observations",
        "accepted_input_kinds": ("sky_coordinates",),
        "produced_artifact_kinds": _ACQUISITION,
        "parameter_model": (
            _p("catalog", "string", required=True),
            _p("ra_degrees", "number", required=True),
            _p("dec_degrees", "number", required=True),
            _p("radius_degrees", "number", required=True),
        ),
        "workload_class": "network",
    },
    ScientificSkillId.fits_image_analysis: {
        "phase": "analyzing_data",
        "accepted_input_kinds": ("fits_image",),
        "produced_artifact_kinds": ("analysis_report",),
        "parameter_model": (
            _p("content_hash", "string", required=True),
            _p("operation", "string", required=True),
            _p("x", "number"),
            _p("y", "number"),
            _p("radius", "number"),
            _p("threshold", "number"),
            _p("background", "number"),
        ),
        "workload_class": "memory_heavy",
    },
    ScientificSkillId.spectrum_analysis: {
        "phase": "analyzing_data",
        "accepted_input_kinds": ("spectrum_series",),
        "produced_artifact_kinds": ("analysis_report", "visualization"),
        "parameter_model": (
            _p("wavelengths", "rows", required=True),
            _p("fluxes", "rows", required=True),
        ),
        "workload_class": "cpu_light",
    },
    ScientificSkillId.spectrum_acquisition: {
        "phase": "acquiring_observations",
        "accepted_input_kinds": ("sky_coordinates",),
        "produced_artifact_kinds": ("spectrum_series", "analysis_report"),
        "parameter_model": (
            _p("ra_degrees", "number", required=True),
            _p("dec_degrees", "number", required=True),
        ),
        "workload_class": "network",
    },
    ScientificSkillId.light_curve_analysis: {
        "phase": "analyzing_data",
        "accepted_input_kinds": ("light_curve_series",),
        "produced_artifact_kinds": ("analysis_report", "visualization"),
        "parameter_model": (
            _p("times", "rows", required=True),
            _p("values", "rows", required=True),
        ),
        "workload_class": "cpu_light",
    },
    ScientificSkillId.light_curve_acquisition: {
        "phase": "acquiring_observations",
        "accepted_input_kinds": ("target_name",),
        "produced_artifact_kinds": ("light_curve_series", "analysis_report"),
        "parameter_model": (_p("target", "string", required=True),),
        "workload_class": "network",
    },
    ScientificSkillId.tabular_machine_learning: {
        "phase": "training_models",
        "accepted_input_kinds": _ROWS,
        "produced_artifact_kinds": ("model_evaluation", "model_artifact"),
        "parameter_model": (
            _p("rows", "rows", required=True),
            _p("feature_fields", "string_list", required=True),
            _p("target_field", "string", required=True),
            _p("task_kind", "string"),
            _p("algorithm", "string"),
            _p("split_strategy", "string"),
            _p("group_field", "string"),
            _p("entity_field", "string"),
            _p("time_field", "string"),
            _p("test_fraction", "number"),
            _p("random_seed", "integer"),
            _p("cv_folds", "integer"),
        ),
        "workload_class": "cpu_heavy",
    },
    ScientificSkillId.time_series_classification: {
        "phase": "training_models",
        "accepted_input_kinds": ("time_series_rows",),
        "produced_artifact_kinds": ("model_evaluation", "model_artifact"),
        "parameter_model": (
            _p("rows", "rows", required=True),
            _p("series_fields", "string_list", required=True),
            _p("target_field", "string", required=True),
            _p("algorithm", "string"),
            _p("test_fraction", "number"),
            _p("random_seed", "integer"),
            _p("cv_folds", "integer"),
        ),
        "workload_class": "cpu_heavy",
    },
    ScientificSkillId.time_series_forecast: {
        "phase": "training_models",
        "accepted_input_kinds": ("time_series_rows",),
        "produced_artifact_kinds": ("model_evaluation", "model_artifact"),
        "parameter_model": (
            _p("rows", "rows", required=True),
            _p("time_field", "string", required=True),
            _p("target_field", "string", required=True),
            _p("test_fraction", "number"),
            _p("random_seed", "integer"),
        ),
        "workload_class": "cpu_heavy",
    },
    ScientificSkillId.image_classification: {
        "phase": "training_models",
        "accepted_input_kinds": ("image_dataset",),
        "produced_artifact_kinds": ("model_evaluation", "model_artifact"),
        "parameter_model": (
            _p("image_bundle_hash", "string", required=True),
            _p("test_fraction", "number"),
            _p("random_seed", "integer"),
        ),
        "workload_class": "memory_heavy",
    },
    ScientificSkillId.model_inference: {
        "phase": "analyzing_data",
        "accepted_input_kinds": ("model_artifact", "tabular_rows"),
        "produced_artifact_kinds": ("analysis_report",),
        "parameter_model": (
            _p("model_artifact_hash", "string", required=True),
            _p("rows", "rows", required=True),
        ),
        "workload_class": "cpu_light",
    },
    ScientificSkillId.wwt_scene: {
        "phase": "building_visualizations",
        "accepted_input_kinds": ("sky_coordinates", "fits_image", "source_table"),
        "produced_artifact_kinds": ("wwt_scene_spec",),
        "parameter_model": (
            _p("mode", "string"),
            _p("ra_degrees", "number"),
            _p("dec_degrees", "number"),
            _p("field_of_view_degrees", "number"),
        ),
        "workload_class": "cpu_light",
    },
}


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

    missing = set(handlers) - set(_DESCRIPTORS)
    if missing:
        raise ValueError(f"skills without descriptors: {sorted(map(str, missing))}")
    extra = set(_DESCRIPTORS) - set(handlers)
    if extra:
        raise ValueError(f"descriptors without handlers: {sorted(map(str, extra))}")

    return ScientificSkillRegistry(
        ScientificSkillDefinition(
            skill_id=skill_id,
            revision="1.1.0",
            handler=handler,
            **_DESCRIPTORS[skill_id],  # type: ignore[arg-type]
        )
        for skill_id, handler in handlers.items()
    )


__all__ = [
    "ScientificSkillDefinition",
    "ScientificSkillRegistry",
    "SkillParameterDescriptor",
    "build_scientific_skill_registry",
]
