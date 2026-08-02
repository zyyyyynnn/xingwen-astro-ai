"""Publisher admission validators for sealed C-04 Artifact candidates."""

from __future__ import annotations

from typing import Protocol

from app.schemas.data_artifacts import (
    DatasetArtifactCandidate,
    FieldDictionaryArtifactCandidate,
    SourceCollectionArtifactCandidate,
    compute_data_artifact_output_hash,
)


Candidate = DatasetArtifactCandidate | FieldDictionaryArtifactCandidate | SourceCollectionArtifactCandidate


class AdmissionContext(Protocol):
    candidate: Candidate
    source_snapshot_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]


def _candidate(context: AdmissionContext) -> Candidate:
    candidate = context.candidate
    if not isinstance(candidate, (DatasetArtifactCandidate, FieldDictionaryArtifactCandidate, SourceCollectionArtifactCandidate)):
        raise ValueError("unsupported C-04 Artifact candidate type")
    return candidate


def validate_data_artifact_evidence(context: AdmissionContext) -> None:
    candidate = _candidate(context)
    if tuple(context.source_snapshot_ids) != candidate.source_snapshot_ids:
        raise ValueError("SourceSnapshot references disagree with candidate")
    if tuple(context.evidence_ids) != candidate.evidence_ids:
        raise ValueError("Evidence references disagree with candidate")
    if isinstance(candidate, DatasetArtifactCandidate):
        evidence_by_id = {item.evidence_id: item for item in candidate.transformation_evidence}
        source_values = {item.source_value_id: item for item in candidate.source_values}
        if len(evidence_by_id) != len(candidate.transformation_evidence):
            raise ValueError("duplicate transformation Evidence")
        if len(source_values) != len(candidate.source_values):
            raise ValueError("duplicate source value")
        for evidence in evidence_by_id.values():
            source_value = source_values.get(evidence.source_value_id)
            if source_value is None or evidence.locator != source_value.evidence_locator:
                raise ValueError("transformation Evidence is not bound to its source value")
            if evidence.evidence_id not in candidate.evidence_ids:
                raise ValueError("transformation Evidence is absent from candidate references")


def validate_data_artifact_domain(context: AdmissionContext) -> None:
    candidate = _candidate(context)
    if candidate.output_hash != compute_data_artifact_output_hash(candidate):
        raise ValueError("candidate output hash mismatch")
    if isinstance(candidate, DatasetArtifactCandidate):
        if candidate.row_count != len(candidate.rows) or candidate.field_count != len(candidate.columns):
            raise ValueError("Dataset dimensions disagree with content")
        source_ids = {item.source_value_id for item in candidate.source_values}
        evidence_ids = {item.evidence_id for item in candidate.transformation_evidence}
        for row in candidate.rows:
            for field in row.fields:
                if not set(field.candidate_source_value_ids) <= source_ids:
                    raise ValueError("Dataset cell refers to an unknown source value")
                if not set(field.transformation_evidence_ids) <= evidence_ids:
                    raise ValueError("Dataset cell refers to unknown Evidence")


def validate_data_artifact_quality_prerequisites(context: AdmissionContext) -> None:
    candidate = _candidate(context)
    if candidate.quality_evaluation_status != "not_evaluated":
        raise ValueError("C-04 must not evaluate C-05 quality")
    if isinstance(candidate, DatasetArtifactCandidate) and not candidate.quality_metric_input_declarations:
        raise ValueError("Dataset must declare its downstream quality inputs")


__all__ = [
    "validate_data_artifact_domain",
    "validate_data_artifact_evidence",
    "validate_data_artifact_quality_prerequisites",
]
