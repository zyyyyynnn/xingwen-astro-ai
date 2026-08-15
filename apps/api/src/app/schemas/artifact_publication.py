"""Canonical persisted Artifact content registry.

The Publisher and generic read boundary share this registry so a production
ArtifactVersion cannot be written or returned under a second, compact content
shape. Imports stay local to avoid making ``core`` depend on every pipeline
schema at module-import time.
"""

from __future__ import annotations

import json

from pydantic import BaseModel


def normalize_artifact_kind(value: object) -> str | None:
    normalized = getattr(value, "value", value)
    return normalized if isinstance(normalized, str) and normalized else None


def canonical_artifact_content_model(kind: object) -> type[BaseModel] | None:
    """Return the sole canonical persisted model for one Artifact kind."""

    from app.schemas.core import ExportArtifactContent
    from app.schemas.data_artifacts import (
        DatasetArtifactCandidate,
        FieldDictionaryArtifactCandidate,
        SourceCollectionArtifactCandidate,
    )
    from app.schemas.graph_artifact import GraphArtifactCandidate
    from app.schemas.literature_claim import LiteratureClaimsCandidate
    from app.schemas.literature_relation import LiteratureRelationsCandidate
    from app.schemas.paper_collection import PaperCollection
    from app.schemas.paper_summary import PaperSummaryArtifactContent
    from app.schemas.scientific_skills import (
        AnalysisReportArtifactContent,
        LightCurveArtifactContent,
        ModelArtifactContent,
        ModelEvaluationArtifactContent,
        SpectrumArtifactContent,
        VisualizationArtifactContent,
    )

    canonical_types: dict[str, type[BaseModel]] = {
        "dataset": DatasetArtifactCandidate,
        "field_dictionary": FieldDictionaryArtifactCandidate,
        "source_collection": SourceCollectionArtifactCandidate,
        "analysis_report": AnalysisReportArtifactContent,
        "visualization": VisualizationArtifactContent,
        "spectrum": SpectrumArtifactContent,
        "light_curve": LightCurveArtifactContent,
        "model_evaluation": ModelEvaluationArtifactContent,
        "model_artifact": ModelArtifactContent,
        "paper_collection": PaperCollection,
        "paper_summary": PaperSummaryArtifactContent,
        "literature_claims": LiteratureClaimsCandidate,
        "literature_relations": LiteratureRelationsCandidate,
        "graph": GraphArtifactCandidate,
        "export": ExportArtifactContent,
    }
    normalized = normalize_artifact_kind(kind)
    return canonical_types.get(normalized) if normalized is not None else None


def canonical_artifact_content_payload(candidate: BaseModel) -> dict[str, object]:
    """Serialize canonical content without dropping required nullable fields."""

    kind = normalize_artifact_kind(getattr(candidate, "kind", None))
    expected_model = canonical_artifact_content_model(kind)
    if expected_model is None or type(candidate) is not expected_model:
        raise ValueError("Artifact content does not use its canonical persisted model")
    payload = _prune_optional_nulls(
        candidate.model_dump(mode="json"),
        candidate,
    )
    if not isinstance(payload, dict):
        raise ValueError("Canonical Artifact content must serialize to an object")
    restored = expected_model.model_validate_json(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    )
    if restored.model_dump(mode="json") != candidate.model_dump(mode="json"):
        raise ValueError("Canonical Artifact content is not round-trip stable")
    return payload


def _prune_optional_nulls(serialized: object, source: object) -> object:
    if isinstance(source, BaseModel) and isinstance(serialized, dict):
        result = dict(serialized)
        for field_name, field in type(source).model_fields.items():
            if field_name not in result:
                continue
            value = getattr(source, field_name)
            if value is None and not field.is_required():
                result.pop(field_name)
                continue
            result[field_name] = _prune_optional_nulls(result[field_name], value)
        return result
    if isinstance(source, (list, tuple)) and isinstance(serialized, list):
        return [
            _prune_optional_nulls(item, source[index])
            for index, item in enumerate(serialized)
        ]
    if isinstance(source, dict) and isinstance(serialized, dict):
        return {
            key: _prune_optional_nulls(value, source.get(key))
            for key, value in serialized.items()
        }
    return serialized


__all__ = [
    "canonical_artifact_content_model",
    "canonical_artifact_content_payload",
    "normalize_artifact_kind",
]
