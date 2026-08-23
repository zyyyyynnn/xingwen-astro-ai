"""Canonical hashing for the immutable RevisionPlan execution contract."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from app.security import canonical_request_hash


def compute_revision_plan_hash(
    *,
    project_id: UUID,
    parent_run_id: UUID,
    parent_run_revision: int,
    contract_id: UUID,
    feedback_ids: Sequence[UUID],
    recompute_steps: Sequence[str],
    version_decisions: Sequence[dict[str, Any]],
) -> str:
    """Hash the exact ordered facts frozen for one RevisionPlan."""

    return canonical_request_hash(
        {
            "project_id": str(project_id),
            "parent_run_id": str(parent_run_id),
            "parent_run_revision": parent_run_revision,
            "contract_id": str(contract_id),
            "feedback_ids": [str(item) for item in feedback_ids],
            "recompute_steps": list(recompute_steps),
            "version_decisions": list(version_decisions),
        }
    )


__all__ = ["compute_revision_plan_hash"]
