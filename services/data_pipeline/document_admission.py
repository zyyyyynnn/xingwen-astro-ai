"""Deterministic admission from one raw document candidate to one typed observation."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator

from app.schemas._hashing import (
    compute_canonical_payload_hash,
)
from app.schemas.core import (
    ContentHash,
    DataRequirements,
    DocumentSourcePolicy,
    Identifier,
)
from app.schemas.data_provenance import DocumentDataProvenance
from app.schemas.document_observation import ScientificDocumentObservation
from app.schemas.evidence import SourceSnapshotRecord
from app.schemas.manifest import CaseManifest, FieldManifest, NullReason
from app.schemas.research_input import ResearchInputRef
from app.schemas.scientific_document import (
    DocumentParseQuality,
    ScientificDataExtractionCandidate,
)


MODEL_CONFIG = ConfigDict(extra="forbid", frozen=True)
_NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
_SCALAR = re.compile(rf"^\s*(?P<value>{_NUMBER})\s*$")
_SYMMETRIC = re.compile(rf"^\s*(?P<value>{_NUMBER})\s*±\s*(?P<error>{_NUMBER})\s*$")
_ASYMMETRIC = re.compile(
    rf"^\s*(?P<value>{_NUMBER})\s*\+\s*(?P<positive>{_NUMBER})\s*"
    rf"-\s*(?P<negative>{_NUMBER})\s*$"
)
_LIMIT = re.compile(rf"^\s*(?P<operator>[<>])\s*(?P<value>{_NUMBER})\s*$")
_NULL_TEXT = {
    "not measured": NullReason.not_measured,
    "not_measured": NullReason.not_measured,
}


class DocumentAdmissionCode(StrEnum):
    unauthorized = "DOCUMENT_SOURCE_UNAUTHORIZED"
    provenance_mismatch = "DOCUMENT_PROVENANCE_MISMATCH"
    unknown_field = "DOCUMENT_FIELD_UNKNOWN"
    unknown_unit = "DOCUMENT_UNIT_UNKNOWN"
    invalid_value = "DOCUMENT_VALUE_INVALID"
    row_not_frozen = "DOCUMENT_ROW_NOT_FROZEN"
    unsupported = "DOCUMENT_PARSE_UNSUPPORTED"


class DocumentAdmissionError(ValueError):
    def __init__(self, code: DocumentAdmissionCode, message: str) -> None:
        self.code = code
        super().__init__(message)


class DocumentAdmissionContext(BaseModel):
    model_config = MODEL_CONFIG

    project_id: Identifier
    research_input: ResearchInputRef
    document_parse_id: Identifier
    document_parse_project_id: Identifier
    document_parse_research_input_id: Identifier
    document_parse_input_content_hash: ContentHash
    document_parse_persisted_source_snapshot_id: Identifier
    document_parse_overall_quality: DocumentParseQuality
    persisted_locator_project_id: Identifier
    persisted_locator_document_parse_id: Identifier
    persisted_locator_source_snapshot_id: Identifier
    persisted_locator_hash: ContentHash
    persisted_source_snapshot_id: Identifier
    pipeline_source_snapshot: SourceSnapshotRecord
    frozen_crossmatch_row_ids: tuple[Identifier, ...]

    @model_validator(mode="after")
    def validate_context(self) -> Self:
        if len(self.frozen_crossmatch_row_ids) != len(
            set(self.frozen_crossmatch_row_ids)
        ):
            raise ValueError("frozen crossmatch row IDs must be unique")
        return self


def _decimal_text(value: str) -> str:
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise DocumentAdmissionError(
            DocumentAdmissionCode.invalid_value,
            "document value is not a finite decimal",
        ) from exc
    if not parsed.is_finite():
        raise DocumentAdmissionError(
            DocumentAdmissionCode.invalid_value, "document value is not finite"
        )
    normalized = format(parsed, "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    return "0" if normalized in {"-0", "+0", ""} else normalized


def _parse_raw(candidate: ScientificDataExtractionCandidate):
    if candidate.raw_value is None:
        null_reason = _NULL_TEXT.get((candidate.raw_text or "").strip())
        if null_reason is None:
            raise DocumentAdmissionError(
                DocumentAdmissionCode.invalid_value,
                "document null requires an explicit supported raw null statement",
            )
        return None, None, None, "not_applicable", null_reason
    for pattern, kind in (
        (_SYMMETRIC, "symmetric"),
        (_ASYMMETRIC, "asymmetric"),
        (_LIMIT, "limit"),
        (_SCALAR, "scalar"),
    ):
        match = pattern.fullmatch(candidate.raw_value)
        if match is None:
            continue
        value = _decimal_text(match.group("value"))
        if kind == "symmetric":
            error = _decimal_text(match.group("error"))
            return value, error, error, "measured", None
        if kind == "asymmetric":
            return (
                value,
                _decimal_text(match.group("positive")),
                _decimal_text(match.group("negative")),
                "measured",
                None,
            )
        if kind == "limit":
            status = "upper_limit" if match.group("operator") == "<" else "lower_limit"
            return value, None, None, status, None
        return value, None, None, "measured", None
    raise DocumentAdmissionError(
        DocumentAdmissionCode.invalid_value,
        "document raw value is outside the versioned scalar grammar",
    )


def _resolve_unit(raw_unit: str | None, field_manifest: FieldManifest) -> str:
    if raw_unit is None:
        raise DocumentAdmissionError(
            DocumentAdmissionCode.unknown_unit, "document numeric value requires a unit"
        )
    matches = tuple(
        unit.unit_id
        for unit in field_manifest.units
        if raw_unit in {unit.unit_id, unit.symbol}
    )
    if len(matches) != 1:
        raise DocumentAdmissionError(
            DocumentAdmissionCode.unknown_unit,
            "document unit must exactly match one registered Manifest unit",
        )
    return matches[0]


def _validate_authority(
    candidate: ScientificDataExtractionCandidate,
    context: DocumentAdmissionContext,
    canonical_row_id: str,
    case_manifest: CaseManifest,
    data_requirements: DataRequirements,
) -> None:
    if (
        data_requirements.document_source_policy
        is not DocumentSourcePolicy.research_input
        or case_manifest.document_source_capability
        is not DocumentSourcePolicy.research_input
    ):
        raise DocumentAdmissionError(
            DocumentAdmissionCode.unauthorized,
            "document source is not explicitly authorized",
        )
    if (
        candidate.parse_quality is DocumentParseQuality.unsupported
        or context.document_parse_overall_quality is DocumentParseQuality.unsupported
    ):
        raise DocumentAdmissionError(
            DocumentAdmissionCode.unsupported,
            "unsupported document parse cannot be admitted",
        )
    if canonical_row_id not in context.frozen_crossmatch_row_ids:
        raise DocumentAdmissionError(
            DocumentAdmissionCode.row_not_frozen,
            "document observation must bind a frozen Crossmatch row",
        )
    persisted_snapshot_id = context.persisted_source_snapshot_id
    expected = (
        context.research_input.id,
        context.research_input.content_hash,
        context.document_parse_id,
        persisted_snapshot_id,
        context.pipeline_source_snapshot.snapshot_id,
        context.pipeline_source_snapshot.content_hash,
    )
    actual = (
        candidate.research_input_id,
        candidate.research_input_content_hash,
        candidate.document_parse_id,
        candidate.persisted_source_snapshot_id,
        candidate.pipeline_source_snapshot_id,
        candidate.pipeline_source_snapshot_content_hash,
    )
    locator_hash = compute_canonical_payload_hash(
        candidate.locator.model_dump(mode="json", exclude_none=True)
    )
    if (
        actual != expected
        or context.document_parse_project_id != context.project_id
        or context.document_parse_research_input_id != context.research_input.id
        or context.document_parse_input_content_hash
        != context.research_input.content_hash
        or context.document_parse_persisted_source_snapshot_id != persisted_snapshot_id
        or context.persisted_locator_project_id != context.project_id
        or context.persisted_locator_document_parse_id != context.document_parse_id
        or context.persisted_locator_source_snapshot_id != persisted_snapshot_id
        or context.persisted_locator_hash != locator_hash
        or context.research_input.source_snapshot_id != persisted_snapshot_id
        or context.pipeline_source_snapshot.source_id != "research_input"
        or context.pipeline_source_snapshot.query
        != f"research_input:{context.research_input.id}"
    ):
        raise DocumentAdmissionError(
            DocumentAdmissionCode.provenance_mismatch,
            "document ResearchInput/DocumentParse/SourceSnapshot provenance is not closed",
        )


def admit_scientific_document_candidate(
    *,
    candidate: ScientificDataExtractionCandidate,
    context: DocumentAdmissionContext,
    canonical_row_id: str,
    case_manifest: CaseManifest,
    field_manifest: FieldManifest,
    data_requirements: DataRequirements,
) -> ScientificDocumentObservation:
    _validate_authority(
        candidate, context, canonical_row_id, case_manifest, data_requirements
    )
    if candidate.field_hint is None:
        raise DocumentAdmissionError(
            DocumentAdmissionCode.unknown_field,
            "document candidate requires a field hint",
        )
    try:
        field = field_manifest.resolve_document_field(candidate.field_hint)
    except KeyError as exc:
        raise DocumentAdmissionError(
            DocumentAdmissionCode.unknown_field,
            "document field must be an exact canonical field or registered alias",
        ) from exc
    source_value, positive, negative, limit, null_reason = _parse_raw(candidate)
    source_unit = (
        field.canonical_unit
        if source_value is None and candidate.raw_unit is None
        else _resolve_unit(candidate.raw_unit, field_manifest)
    )
    provenance = DocumentDataProvenance(
        project_id=context.project_id,
        research_input_id=context.research_input.id,
        research_input_content_hash=context.research_input.content_hash,
        document_parse_id=context.document_parse_id,
        persisted_source_snapshot_id=context.persisted_source_snapshot_id,
        pipeline_source_snapshot_id=context.pipeline_source_snapshot.snapshot_id,
        pipeline_query_hash=context.pipeline_source_snapshot.query_hash,
        pipeline_source_snapshot_content_hash=context.pipeline_source_snapshot.content_hash,
        locator=candidate.locator,
        parse_quality=candidate.parse_quality,
    )
    identity_payload = {
        "raw_candidate_id": candidate.candidate_id,
        "canonical_row_id": canonical_row_id,
        "canonical_field_id": field.field_id,
        "provenance": provenance.model_dump(mode="json"),
    }
    observation_id = (
        "document.observation."
        + compute_canonical_payload_hash(identity_payload).split(":", 1)[1][:32]
    )
    payload = {
        "schema_version": "1.0.0",
        "observation_id": observation_id,
        **identity_payload,
        "source_value": source_value,
        "source_unit": source_unit,
        "uncertainty_positive": positive,
        "uncertainty_negative": negative,
        "limit_status": limit,
        "null_reason": null_reason,
        "parse_quality": candidate.parse_quality,
    }
    payload["content_hash"] = compute_canonical_payload_hash(payload)
    return ScientificDocumentObservation.model_validate(payload)


def validate_admitted_document_observation(
    observation: ScientificDocumentObservation,
    *,
    frozen_crossmatch_row_ids: tuple[str, ...] | set[str],
    case_manifest: CaseManifest,
    field_manifest: FieldManifest,
    data_requirements: DataRequirements,
) -> None:
    """Shared C authority used by mapping and quality after raw parsing is complete."""

    if (
        data_requirements.document_source_policy
        is not DocumentSourcePolicy.research_input
        or case_manifest.document_source_capability
        is not DocumentSourcePolicy.research_input
    ):
        raise DocumentAdmissionError(
            DocumentAdmissionCode.unauthorized,
            "document source is not explicitly authorized",
        )
    if observation.parse_quality is DocumentParseQuality.unsupported:
        raise DocumentAdmissionError(
            DocumentAdmissionCode.unsupported,
            "unsupported document parse cannot be admitted",
        )
    if observation.canonical_row_id not in frozen_crossmatch_row_ids:
        raise DocumentAdmissionError(
            DocumentAdmissionCode.row_not_frozen,
            "document observation must bind a frozen Crossmatch row",
        )
    try:
        field = field_manifest.field_by_id(observation.canonical_field_id)
    except KeyError as exc:
        raise DocumentAdmissionError(
            DocumentAdmissionCode.unknown_field,
            "document observation field is absent from the frozen Manifest",
        ) from exc
    if field.field_id != observation.canonical_field_id:
        raise DocumentAdmissionError(
            DocumentAdmissionCode.unknown_field, "field drifted"
        )
    if observation.provenance.parse_quality is not observation.parse_quality:
        raise DocumentAdmissionError(
            DocumentAdmissionCode.provenance_mismatch,
            "document observation parse-quality provenance drifted",
        )


__all__ = [
    "DocumentAdmissionCode",
    "DocumentAdmissionContext",
    "DocumentAdmissionError",
    "admit_scientific_document_candidate",
    "validate_admitted_document_observation",
]
