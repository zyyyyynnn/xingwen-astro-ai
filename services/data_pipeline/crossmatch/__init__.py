"""Public boundary for cross-source entity alignment."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.schemas.crossmatch import CrossmatchInput, CrossmatchResult


def align_cross_source_records(input: CrossmatchInput) -> CrossmatchResult:
    from .engine import align_cross_source_records as align

    return align(input)

__all__ = ["align_cross_source_records"]
