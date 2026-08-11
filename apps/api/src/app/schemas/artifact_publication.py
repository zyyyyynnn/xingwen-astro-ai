"""Canonical persisted Artifact content registry.

The Publisher and generic read boundary share this registry so a production
ArtifactVersion cannot be written or returned under a second, compact content
shape. Imports stay local to avoid making ``core`` depend on every pipeline
schema at module-import time.
"""

from __future__ import annotations

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

    canonical_types: dict[str, type[BaseModel]] = {
        "dataset": DatasetArtifactCandidate,
        "field_dictionary": FieldDictionaryArtifactCandidate,
        "source_collection": SourceCollectionArtifactCandidate,
        "paper_collection": PaperCollection,
        "paper_summary": PaperSummaryArtifactContent,
        "literature_claims": LiteratureClaimsCandidate,
        "literature_relations": LiteratureRelationsCandidate,
        "graph": GraphArtifactCandidate,
        "export": ExportArtifactContent,
    }
    normalized = normalize_artifact_kind(kind)
    return canonical_types.get(normalized) if normalized is not None else None


__all__ = ["canonical_artifact_content_model", "normalize_artifact_kind"]
