"""Fail-closed registry for typed scientific skills."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from time import monotonic

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.core import ScientificSkillId

from .types import ScientificSkillRequest, ScientificSkillResult


ScientificSkillHandler = Callable[[ScientificSkillRequest], dict[str, object]]


@dataclass(frozen=True, slots=True)
class ScientificSkillDefinition:
    skill_id: ScientificSkillId
    revision: str
    handler: ScientificSkillHandler


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

    def execute(self, request: ScientificSkillRequest) -> ScientificSkillResult:
        definition = self._definitions.get(request.skill_id)
        if definition is None:
            raise ValueError(f"unregistered scientific skill: {request.skill_id}")
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
    from .modeling import (
        classify_images,
        evaluate_tabular_model,
        forecast_time_series,
    )

    handlers: dict[ScientificSkillId, ScientificSkillHandler] = {
        ScientificSkillId.catalog_crossmatch: run_catalog_crossmatch,
        ScientificSkillId.data_profile: build_data_profile,
        ScientificSkillId.statistical_analysis: analyze_statistics,
        ScientificSkillId.correlation_analysis: analyze_correlations,
        ScientificSkillId.chart_visualization: build_visualization,
        ScientificSkillId.simbad_lookup: query_simbad,
        ScientificSkillId.skyview_fits: retrieve_skyview_fits,
        ScientificSkillId.ephemeris: calculate_ephemeris,
        ScientificSkillId.celestial_events: find_celestial_events,
        ScientificSkillId.fits_image_analysis: analyze_fits_image,
        ScientificSkillId.tabular_machine_learning: evaluate_tabular_model,
        ScientificSkillId.time_series_forecast: forecast_time_series,
        ScientificSkillId.image_classification: classify_images,
        ScientificSkillId.wwt_scene: build_wwt_scene,
    }
    return ScientificSkillRegistry(
        ScientificSkillDefinition(
            skill_id=skill_id,
            revision="1.0.0",
            handler=handler,
        )
        for skill_id, handler in handlers.items()
    )


__all__ = [
    "ScientificSkillDefinition",
    "ScientificSkillRegistry",
    "build_scientific_skill_registry",
]
