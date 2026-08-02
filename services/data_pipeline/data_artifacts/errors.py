"""Stable local C-04 errors; HTTP upstream failures are deliberately separate."""

from __future__ import annotations

from app.schemas.data_artifacts import DataArtifactErrorCode


class DataArtifactError(RuntimeError):
    def __init__(
        self,
        code: DataArtifactErrorCode | str,
        message: str,
        *,
        cause: BaseException | None = None,
    ) -> None:
        self.code = DataArtifactErrorCode(code).value
        self.cause = cause
        super().__init__(message)
