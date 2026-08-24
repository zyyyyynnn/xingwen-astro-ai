"""C-owned typed observations admitted from persisted scientific documents."""

from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, model_validator

from ._hashing import compute_canonical_payload_hash
from .core import ContentHash, Identifier
from .manifest import CanonicalFieldId, NullReason
from .data_provenance import DocumentDataProvenance
from .scientific_document import DocumentParseQuality


DOCUMENT_OBSERVATION_SCHEMA_VERSION = "1.0.0"
MODEL_CONFIG = ConfigDict(extra="forbid", frozen=True)


class ScientificDocumentObservation(BaseModel):
    """One fully typed document value; free text is never parsed downstream."""

    model_config = MODEL_CONFIG

    schema_version: Literal["1.0.0"] = "1.0.0"
    observation_id: Identifier
    raw_candidate_id: Identifier
    canonical_row_id: Identifier
    canonical_field_id: CanonicalFieldId
    source_value: str | None = None
    source_unit: Identifier
    uncertainty_positive: str | None = None
    uncertainty_negative: str | None = None
    limit_status: Literal["measured", "lower_limit", "upper_limit", "not_applicable"]
    null_reason: NullReason | None = None
    parse_quality: DocumentParseQuality
    provenance: DocumentDataProvenance
    content_hash: ContentHash

    @model_validator(mode="after")
    def validate_observation(self) -> Self:
        if (self.source_value is None) != (self.null_reason is not None):
            raise ValueError("document null reason must exactly describe a null value")
        if self.source_value is None and self.limit_status != "not_applicable":
            raise ValueError("null document value cannot carry a scientific limit")
        if self.provenance.parse_quality is not self.parse_quality:
            raise ValueError("document provenance parse quality drifted")
        expected = compute_canonical_payload_hash(
            self.model_dump(mode="json", exclude={"content_hash"})
        )
        if self.content_hash != expected:
            raise ValueError(f"document observation content_hash mismatch: {expected}")
        return self


__all__ = [
    "DOCUMENT_OBSERVATION_SCHEMA_VERSION",
    "DocumentDataProvenance",
    "ScientificDocumentObservation",
]
