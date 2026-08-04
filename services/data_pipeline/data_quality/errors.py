"""Stable, non-HTTP errors for C-05 evaluation and admission."""

from __future__ import annotations

from app.schemas.data_quality import QualityErrorCode, QualityFailureStage


class DataQualityError(ValueError):
    def __init__(
        self,
        code: QualityErrorCode,
        message: str,
        *,
        stage: QualityFailureStage,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.stage = stage
        self.cause = cause


__all__ = ["DataQualityError"]
