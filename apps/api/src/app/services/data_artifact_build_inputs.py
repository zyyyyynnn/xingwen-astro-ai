"""Immutable PostgreSQL replay authority for DataArtifactBuildInput."""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models import DataArtifactBuildInputRecordModel
from app.schemas.data_artifacts import DataArtifactBuildInput


class DataArtifactBuildInputReplayError(ValueError):
    """Raised when an immutable replay record cannot reproduce its key."""

    code = "DATA_ARTIFACT_BUILD_INPUT_NOT_REPLAYABLE"

    def __init__(self, detail: str) -> None:
        super().__init__(f"{self.code}: {detail}")


class DataArtifactBuildInputRepository:
    """Persist and revalidate one canonical build input per project/hash."""

    def __init__(self, factory: Callable[[], Session]) -> None:
        self._factory = factory

    def put(
        self,
        *,
        project_id: UUID,
        input_value: DataArtifactBuildInput,
    ) -> DataArtifactBuildInput:
        validated = self._canonical(input_value)
        payload = validated.model_dump(mode="json")
        with self._factory() as session, session.begin():
            session.execute(
                insert(DataArtifactBuildInputRecordModel)
                .values(
                    project_id=project_id,
                    input_hash=validated.input_hash,
                    payload=payload,
                )
                .on_conflict_do_nothing(
                    index_elements=("project_id", "input_hash")
                )
            )
            row = session.get(
                DataArtifactBuildInputRecordModel,
                (project_id, validated.input_hash),
            )
            if row is None or row.payload != payload:
                raise DataArtifactBuildInputReplayError(
                    "input_hash is already bound to different canonical content"
                )
        return validated

    def get(
        self,
        *,
        project_id: UUID,
        input_hash: str,
    ) -> DataArtifactBuildInput:
        with self._factory() as session:
            row = session.get(
                DataArtifactBuildInputRecordModel,
                (project_id, input_hash),
            )
            if row is None:
                raise DataArtifactBuildInputReplayError(
                    "no build input exists for the requested project and input_hash"
                )
            try:
                value = DataArtifactBuildInput.model_validate(row.payload)
            except (TypeError, ValueError, ValidationError) as exc:
                raise DataArtifactBuildInputReplayError(
                    "persisted payload is not a valid build input"
                ) from exc
            if value.input_hash != row.input_hash or row.input_hash != input_hash:
                raise DataArtifactBuildInputReplayError(
                    "persisted payload does not reproduce its input_hash key"
                )
            return value

    @staticmethod
    def _canonical(input_value: DataArtifactBuildInput) -> DataArtifactBuildInput:
        try:
            return DataArtifactBuildInput.model_validate_json(
                input_value.model_dump_json()
            )
        except (TypeError, ValueError, ValidationError) as exc:
            raise DataArtifactBuildInputReplayError(
                "build input is not canonically replayable"
            ) from exc


__all__ = [
    "DataArtifactBuildInputReplayError",
    "DataArtifactBuildInputRepository",
]
