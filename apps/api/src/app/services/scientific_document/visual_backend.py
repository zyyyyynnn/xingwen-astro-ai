"""Construct the configured visual backend for the canonical document parser."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, cast

from .hybrid_parser import PaddleOcrVlClient, VisualPageParserPort

if TYPE_CHECKING:
    from app.config import Settings


def build_visual_parser(settings: Settings) -> VisualPageParserPort | None:
    """Return the one operator-configured visual backend, if present."""

    if settings.PADDLEOCR_VL_BASE_URL is not None:
        return PaddleOcrVlClient(
            base_url=settings.PADDLEOCR_VL_BASE_URL,
            model_revision=cast(str, settings.PADDLEOCR_VL_MODEL_REVISION),
            timeout_seconds=settings.PADDLEOCR_VL_TIMEOUT_SECONDS,
        )
    if settings.PADDLEOCR_VL_LOCAL_BUNDLE is not None:
        from .local_paddle_pipeline import LocalPaddleOcrVlPipeline

        return LocalPaddleOcrVlPipeline(
            bundle_root=Path(settings.PADDLEOCR_VL_LOCAL_BUNDLE)
        )
    return None


__all__ = ["build_visual_parser"]
