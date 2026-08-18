"""Canonical ReasoningTrace projection derived from admitted literature relations."""

from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, model_validator

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.literature_relation import (
    LiteratureReasoningTraceCandidate,
    LiteratureRelationsCandidate,
)


_MODEL_CONFIG = ConfigDict(extra="forbid", frozen=True)
_PUBLICATION_SEAL = object()


class ReasoningTracesArtifactContent(BaseModel):
    """Reviewable public traces projected from one admitted Relation candidate."""

    model_config = _MODEL_CONFIG
    __artifact_publication_requires_admission__: ClassVar[bool] = True
    _artifact_publication_seal: object | None = PrivateAttr(default=None)

    kind: Literal["reasoning_traces"] = "reasoning_traces"
    schema_version: Literal["1.0.0"] = "1.0.0"
    relation_output_hash: str
    reasoning_traces: tuple[LiteratureReasoningTraceCandidate, ...]
    input_hash: str
    output_hash: str

    @model_validator(mode="after")
    def validate_commitment(self) -> ReasoningTracesArtifactContent:
        trace_ids = tuple(item.trace_id for item in self.reasoning_traces)
        if len(trace_ids) != len(set(trace_ids)):
            raise ValueError("ReasoningTrace ids must be unique")
        expected = compute_reasoning_traces_output_hash(self)
        if self.output_hash != expected:
            raise ValueError(
                f"output_hash does not match ReasoningTrace projection: {expected}"
            )
        return self

    def __artifact_publication_is_admitted__(self) -> bool:
        return self._artifact_publication_seal is _PUBLICATION_SEAL


def compute_reasoning_traces_output_hash(
    value: ReasoningTracesArtifactContent | dict[str, object],
) -> str:
    payload = (
        value.model_dump(mode="json")
        if isinstance(value, ReasoningTracesArtifactContent)
        else dict(value)
    )
    payload.pop("output_hash", None)
    return compute_canonical_payload_hash(payload)


def build_reasoning_traces_artifact(
    relations: LiteratureRelationsCandidate,
) -> ReasoningTracesArtifactContent:
    """Build the sole trace Artifact shape from an admitted Relation output."""

    if not relations.__artifact_publication_is_admitted__():
        raise ValueError("ReasoningTrace projection requires admitted Relations")
    payload: dict[str, object] = {
        "kind": "reasoning_traces",
        "schema_version": "1.0.0",
        "relation_output_hash": relations.output_hash,
        "reasoning_traces": relations.reasoning_traces,
        "input_hash": compute_canonical_payload_hash(
            {
                "relation_input_hash": relations.input_hash,
                "relation_output_hash": relations.output_hash,
            }
        ),
    }
    payload["output_hash"] = compute_reasoning_traces_output_hash(payload)
    result = ReasoningTracesArtifactContent.model_validate(payload)
    result._artifact_publication_seal = _PUBLICATION_SEAL
    return result


__all__ = [
    "ReasoningTracesArtifactContent",
    "build_reasoning_traces_artifact",
    "compute_reasoning_traces_output_hash",
]
