"""Validated execution boundary for scientific skills."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.core import (
    ContentHash,
    Identifier,
    JsonValue,
    ScientificSkillId,
    UtcDateTime,
)


MODEL_CONFIG = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
NonEmptyString = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)
]


class ScientificSkillBudget(BaseModel):
    model_config = MODEL_CONFIG

    timeout_seconds: int = Field(default=30, ge=1, le=120)
    max_input_rows: int = Field(default=10_000, ge=1, le=100_000)
    max_output_rows: int = Field(default=2_000, ge=1, le=10_000)
    max_input_bytes: int = Field(default=32 * 1024 * 1024, ge=1, le=128 * 1024 * 1024)
    max_output_bytes: int = Field(default=16 * 1024 * 1024, ge=1, le=64 * 1024 * 1024)


class ScientificSourceReference(BaseModel):
    model_config = MODEL_CONFIG

    source_snapshot_id: Identifier
    content_hash: ContentHash
    source_id: Identifier | None = None
    query_hash: ContentHash | None = None
    retrieved_at: UtcDateTime | None = None


class ScientificSkillRequest(BaseModel):
    model_config = MODEL_CONFIG

    request_id: Identifier
    project_id: Identifier
    run_id: Identifier
    skill_id: ScientificSkillId
    parameters: dict[str, JsonValue]
    source_references: tuple[ScientificSourceReference, ...]
    budget: ScientificSkillBudget = ScientificSkillBudget()

    @model_validator(mode="after")
    def validate_request(self) -> Self:
        if len(self.parameters) > 64:
            raise ValueError("scientific skill parameters exceed the bounded key count")
        if len(self.source_references) != len(
            {item.source_snapshot_id for item in self.source_references}
        ):
            raise ValueError("scientific skill source references must be unique")
        return self

    @property
    def input_hash(self) -> str:
        return compute_canonical_payload_hash(self.model_dump(mode="json"))


class ScientificSkillResult(BaseModel):
    model_config = MODEL_CONFIG

    request_id: Identifier
    skill_id: ScientificSkillId
    skill_revision: str
    status: Literal["completed", "partial", "unsupported"]
    output: dict[str, JsonValue]
    source_snapshot_ids: tuple[Identifier, ...]
    warnings: tuple[NonEmptyString, ...] = ()
    input_hash: ContentHash
    output_hash: ContentHash

    @model_validator(mode="after")
    def validate_hashes(self) -> Self:
        expected = compute_canonical_payload_hash(self.output)
        if self.output_hash != expected:
            raise ValueError(f"scientific skill output_hash mismatch: {expected}")
        return self


__all__ = [
    "ScientificSkillBudget",
    "ScientificSkillRequest",
    "ScientificSkillResult",
    "ScientificSourceReference",
]
