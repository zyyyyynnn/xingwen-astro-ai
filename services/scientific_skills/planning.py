"""Stable Workflow phase ownership for bounded scientific skills."""

from __future__ import annotations

from app.schemas.core import ScientificSkillId


SCIENTIFIC_SKILL_PHASES: dict[ScientificSkillId, str] = {
    ScientificSkillId.simbad_lookup: "acquiring_observations",
    ScientificSkillId.skyview_fits: "acquiring_observations",
    ScientificSkillId.ephemeris: "acquiring_observations",
    ScientificSkillId.celestial_events: "acquiring_observations",
    ScientificSkillId.gaia_cone_search: "acquiring_observations",
    ScientificSkillId.vizier_tap: "acquiring_observations",
    ScientificSkillId.spectrum_acquisition: "acquiring_observations",
    ScientificSkillId.light_curve_acquisition: "acquiring_observations",
    ScientificSkillId.catalog_crossmatch: "analyzing_data",
    ScientificSkillId.data_profile: "analyzing_data",
    ScientificSkillId.statistical_analysis: "analyzing_data",
    ScientificSkillId.correlation_analysis: "analyzing_data",
    ScientificSkillId.clustering_analysis: "analyzing_data",
    ScientificSkillId.anomaly_detection: "analyzing_data",
    ScientificSkillId.fits_image_analysis: "analyzing_data",
    ScientificSkillId.spectrum_analysis: "analyzing_data",
    ScientificSkillId.light_curve_analysis: "analyzing_data",
    ScientificSkillId.tabular_machine_learning: "training_models",
    ScientificSkillId.time_series_classification: "training_models",
    ScientificSkillId.time_series_forecast: "training_models",
    ScientificSkillId.image_classification: "training_models",
    ScientificSkillId.model_inference: "analyzing_data",
    ScientificSkillId.chart_visualization: "building_visualizations",
    ScientificSkillId.wwt_scene: "building_visualizations",
}


def scientific_skill_phase(skill_id: ScientificSkillId) -> str:
    """Return the canonical Run phase that owns one registered skill."""

    return SCIENTIFIC_SKILL_PHASES[skill_id]


__all__ = ["SCIENTIFIC_SKILL_PHASES", "scientific_skill_phase"]
