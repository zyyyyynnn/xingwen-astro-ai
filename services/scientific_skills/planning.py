"""Stable Workflow phase ownership for bounded scientific skills.

The registry descriptor is the single capability-description source; this
module keeps the historical ``scientific_skill_phase`` seam for existing
consumers while delegating to the registry instead of re-listing skill ids.
"""

from __future__ import annotations

from app.schemas.core import ScientificSkillId


def scientific_skill_phase(skill_id: ScientificSkillId) -> str:
    """Return the canonical Run phase that owns one registered skill."""

    from .registry import build_scientific_skill_registry

    return build_scientific_skill_registry().phase_for(skill_id)


__all__ = ["scientific_skill_phase"]
