"""Stable Workflow phase ownership for bounded scientific skills.

The capability authoring source in
:mod:`app.schemas.scientific_capabilities` is the single capability truth;
this module keeps the stable ``scientific_skill_phase`` API for RunPlan
compilation and step execution as a pure projection of it.
"""

from __future__ import annotations

from app.schemas.core import ScientificSkillId
from app.schemas.scientific_capabilities import (
    scientific_skill_phase as _capability_phase,
)


def scientific_skill_phase(skill_id: ScientificSkillId) -> str:
    """Return the canonical Run phase that owns one registered skill."""

    return _capability_phase(skill_id.value)


__all__ = ["scientific_skill_phase"]
