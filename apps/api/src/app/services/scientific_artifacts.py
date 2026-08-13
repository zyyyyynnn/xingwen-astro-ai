"""Domain read boundary for scientific ArtifactVersions."""

from __future__ import annotations

from pydantic import ValidationError

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.core import ArtifactVersionDetail
from app.schemas.scientific_artifact_api import ScientificArtifactRead
from app.schemas.scientific_skills import (
    AnalysisReportArtifactContent,
    ModelEvaluationArtifactContent,
    ScientificArtifactContent,
    VisualizationArtifactContent,
    FitsImageVisualizationSpec,
    WwtSceneVisualizationSpec,
)
from app.security import SecurityProblem
from app.services.artifacts import ArtifactReadService
from app.services.content_storage import ContentStorage


_MODELS = {
    "analysis_report": AnalysisReportArtifactContent,
    "visualization": VisualizationArtifactContent,
    "model_evaluation": ModelEvaluationArtifactContent,
}


class ScientificArtifactReadService:
    def __init__(
        self,
        artifacts: ArtifactReadService,
        content_storage: ContentStorage | None = None,
    ) -> None:
        self._artifacts = artifacts
        self._content_storage = content_storage

    def get_scientific_artifact(
        self, *, version_id: str, session_id: str
    ) -> ScientificArtifactRead:
        version = self._artifacts.get_version(
            version_id=version_id,
            session_id=session_id,
            full_content=True,
        )
        artifact = self._artifacts.get_artifact(
            artifact_id=version.artifact_id,
            session_id=session_id,
        )
        model = _MODELS.get(artifact.kind.value)
        if model is None:
            raise _problem(
                409,
                "ARTIFACT_KIND_MISMATCH",
                "Artifact kind mismatch",
                "The ArtifactVersion is not a scientific Artifact",
            )
        try:
            content = model.model_validate(version.content)
        except ValidationError as exc:
            raise _integrity_problem() from exc
        _validate_publication(version, content)
        return ScientificArtifactRead(
            artifact_version_id=version.id,
            artifact_id=version.artifact_id,
            project_id=version.project_id,
            version_number=version.version_number,
            supersedes_version_id=version.supersedes_version_id,
            source_mode=version.source_mode,
            content_hash=version.content_hash,
            input_hash=version.input_hash,
            created_at=version.created_at,
            content=content,
            producer_execution=version.producer_execution,
            source_snapshots=version.source_snapshots,
            evidence=version.evidence,
        )

    async def get_content(
        self,
        *,
        version_id: str,
        content_hash: str,
        session_id: str,
    ) -> tuple[bytes, str]:
        read = self.get_scientific_artifact(
            version_id=version_id,
            session_id=session_id,
        )
        media_type = _declared_content_media_type(read.content, content_hash)
        if media_type is None:
            raise _problem(
                404,
                "SCIENTIFIC_CONTENT_NOT_FOUND",
                "Scientific content not found",
                "The requested content hash is not declared by this ArtifactVersion",
            )
        if self._content_storage is None:
            raise _problem(
                503,
                "SCIENTIFIC_CONTENT_UNAVAILABLE",
                "Scientific content unavailable",
                "The immutable content store is not configured",
            )
        content = await self._content_storage.retrieve(content_hash)
        if content is None:
            raise _integrity_problem()
        return content, media_type


def _validate_publication(
    version: ArtifactVersionDetail,
    content: ScientificArtifactContent,
) -> None:
    producer = version.producer_execution
    scientific_evidence = {
        item.evidence_id: item for item in content.scientific_evidence
    }
    persisted_evidence = {item.id: item for item in version.evidence}
    if (
        version.schema_version != content.schema_version
        or version.content_hash != compute_canonical_payload_hash(version.content)
        or version.input_hash != content.input_hash
        or version.source_snapshot_ids != content.source_snapshot_ids
        or version.evidence_ids != content.evidence_ids
        or set(version.source_snapshot_ids)
        != {item.id for item in version.source_snapshots}
        or set(version.evidence_ids) != set(persisted_evidence)
        or set(content.evidence_ids) != set(scientific_evidence)
        or producer.run_id != version.created_by_run_id
        or producer.status != "completed"
        or producer.input_hash != content.input_hash
        or producer.output_hash != version.content_hash
        or producer.producer.type != "algorithm"
        or producer.producer.name != "scientific_artifact_assembler"
        or producer.producer.version != "1.0.0"
        or version.producer != producer.producer
    ):
        raise _integrity_problem()
    for evidence_id, declared in scientific_evidence.items():
        persisted = persisted_evidence[evidence_id]
        if (
            persisted.target_type != declared.target_type
            or persisted.target_id != declared.target_id
            or persisted.evidence_type != declared.evidence_type
            or persisted.source_snapshot_id != declared.source_snapshot_id
            or persisted.locator != declared.locator
            or persisted.quote_or_value != declared.quote_or_value
            or persisted.extraction_method != declared.extraction_method
            or persisted.confidence != declared.confidence
            or persisted.is_restricted
        ):
            raise _integrity_problem()


def _declared_content_media_type(
    content: ScientificArtifactContent,
    content_hash: str,
) -> str | None:
    if isinstance(content, VisualizationArtifactContent):
        if (
            isinstance(content.spec, FitsImageVisualizationSpec)
            and content.spec.content_hash == content_hash
        ):
            return "application/fits"
        if isinstance(content.spec, WwtSceneVisualizationSpec) and any(
            layer.content_hash == content_hash for layer in content.spec.fits_layers
        ):
            return "application/fits"
    if (
        isinstance(content, ModelEvaluationArtifactContent)
        and content.model_binary is not None
        and content.model_binary.content_hash == content_hash
    ):
        return content.model_binary.media_type
    return None


def _integrity_problem() -> SecurityProblem:
    return _problem(
        409,
        "SCIENTIFIC_ARTIFACT_INTEGRITY",
        "Scientific Artifact integrity failure",
        "The scientific ArtifactVersion or its provenance is not self-consistent",
    )


def _problem(status: int, code: str, title: str, detail: str) -> SecurityProblem:
    return SecurityProblem(status=status, code=code, title=title, detail=detail)


__all__ = ["ScientificArtifactReadService"]
