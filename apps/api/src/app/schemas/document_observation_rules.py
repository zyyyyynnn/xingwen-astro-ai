"""Typed Document Observation RuleSet for document-derived data admission.

The RuleSet is the single declarative authority for how persisted
``DocumentParseCandidate`` content becomes raw
``ScientificDataExtractionCandidate`` observations and typed admitted values.
It deliberately contains no executable parsing logic and no per-regex hashes:
one ``configuration_hash`` commits to the complete configuration, while field
alias identity stays owned by the Field Manifest.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ._hashing import compute_canonical_payload_hash
from .manifest import ContentHash, Identifier, NonEmptyString, SemanticVersion


MODEL_CONFIG = ConfigDict(extra="forbid", frozen=True)


class LimitTokenDirection(StrEnum):
    upper = "upper"
    lower = "lower"


class LimitToken(BaseModel):
    """One declared limit marker and its scientific direction."""

    model_config = MODEL_CONFIG

    token: NonEmptyString
    direction: LimitTokenDirection


class DeclaredTextPattern(BaseModel):
    """One deterministic text observation pattern.

    The pattern MUST close field label, value, unit and entity context through
    its named groups; a block that cannot close all four never produces an
    accepted observation. Patterns are configuration, not code paths.
    """

    model_config = MODEL_CONFIG

    pattern_id: Identifier
    pattern: NonEmptyString


class DocumentObservationRuleSet(BaseModel):
    """Frozen rules governing document observation extraction and admission."""

    model_config = MODEL_CONFIG

    rule_set_id: Identifier
    schema_version: SemanticVersion
    version: SemanticVersion
    configuration_hash: ContentHash
    producer_name: NonEmptyString
    producer_version: SemanticVersion
    case_manifest_id: Identifier
    case_manifest_version: SemanticVersion
    case_manifest_content_hash: ContentHash
    field_manifest_id: Identifier
    field_manifest_version: SemanticVersion
    field_manifest_content_hash: ContentHash
    #: Allowed: Unicode NFKC, trim, whitespace collapse, casefold. Nothing else.
    field_label_normalization: Literal["nfkc_trim_collapse_casefold"]
    numeric_syntax_version: SemanticVersion
    null_tokens: tuple[NonEmptyString, ...] = Field(min_length=1)
    uncertainty_separators: tuple[NonEmptyString, ...] = Field(min_length=1)
    asymmetric_pattern: NonEmptyString
    numeric_pattern: NonEmptyString
    limit_tokens: tuple[LimitToken, ...] = Field(min_length=1)
    table_header_policy: Literal["exact_canonical_or_registered_alias_only"]
    text_observation_policy: Literal["declared_patterns_only"]
    declared_text_patterns: tuple[DeclaredTextPattern, ...]
    max_observations_per_parse: int = Field(gt=0)
    created_at: date
    maintained_by: NonEmptyString

    @model_validator(mode="after")
    def validate_hash(self) -> Self:
        payload = self.model_dump(mode="json", exclude={"configuration_hash"})
        expected = "sha256:" + compute_canonical_payload_hash(payload).removeprefix(
            "sha256:"
        )
        if self.configuration_hash != expected:
            raise ValueError(
                f"configuration_hash does not match canonical payload: {expected}"
            )
        return self


def compute_document_observation_configuration_hash(
    payload: dict[str, object],
) -> str:
    """Commit to the canonical RuleSet payload (excluding the hash itself)."""

    return "sha256:" + compute_canonical_payload_hash(payload).removeprefix("sha256:")


__all__ = [
    "DeclaredTextPattern",
    "DocumentObservationRuleSet",
    "LimitToken",
    "LimitTokenDirection",
    "compute_document_observation_configuration_hash",
]
