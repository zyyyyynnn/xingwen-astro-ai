"""Deterministic literature/Graph execution for the real browser integration owner."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from collections.abc import Callable, Iterable
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ArtifactVersionModel, ResearchArtifactModel
from app.schemas.enums import LiteratureRelationType, PaperDataLevel, SourceMode
from app.schemas.literature_claim import LiteratureClaimCandidate
from app.schemas.evidence import SourceSnapshotRecord
from app.schemas.literature_relation import (
    LiteratureRelationConfidenceAssessment,
    LiteratureRelationConfidenceStatus,
    LiteratureRelationStatus,
    build_literature_relation_confidence_subject,
)
from app.schemas.manifest import ManifestBundle, load_manifest_bundle
from app.schemas.paper_collection import PaperSourcePage
from app.security import SecurityProblem, canonical_request_hash
from app.services.research import ResearchApplicationService
from app.test_support.integration_model import (
    DeterministicIntegrationModelExecutionPort,
)
from app.workflow.persistent_executor import PersistentWorkflowExecutor
from app.workflow.research_run_worker import ResearchRunWorker
from app.workflow.store import PersistentWorkflowStore
from services.paper_pipeline.constants import (
    FROZEN_BENCHMARK_CONTENT_HASH,
    FROZEN_SCIENTIFIC_PAYLOAD_HASH,
    RELATION_CONFIDENCE_ACCEPTANCE_THRESHOLD,
    RELATION_CONFIDENCE_APPLICABILITY_SCOPE,
    RELATION_CONFIDENCE_CALIBRATION_ID,
    RELATION_CONFIDENCE_CALIBRATION_METHOD,
    RELATION_CONFIDENCE_CALIBRATION_SAMPLE_SIZE,
    RELATION_CONFIDENCE_CALIBRATION_VERSION,
    RELATION_CONFIDENCE_DEFINITION_ID,
    RELATION_CONFIDENCE_DEFINITION_VERSION,
)
from services.paper_pipeline.live_collection import LivePaperCollectionRunner
from services.paper_pipeline.sources.base import (
    NormalizedPaperQuery,
    RawSourceRecord,
    SourceSearchResult,
)

_FIXED_NOW = datetime(2026, 8, 16, 8, 0, 0, tzinfo=UTC)
_SNAPSHOT_ID = "b3456789-2345-4345-a345-23456789abcd"
_REQUIRED_KINDS = frozenset({"literature_claims", "literature_relations", "graph"})


class ResearchResultsBootstrapResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str
    artifact_version_ids: dict[str, str]
    execution_mode: str = "demo_replay"
    source_mode: str = "fixture"


class _IntegrationPaperSource:
    source_id = "crossref"
    adapter_name = "integration_crossref_fixture"
    adapter_version = "1.0.0"

    def search(
        self,
        query: NormalizedPaperQuery,
        *,
        source_mode: SourceMode,
        data_level: PaperDataLevel,
    ) -> SourceSearchResult:
        del source_mode, data_level
        records = (
            RawSourceRecord(
                source_id=self.source_id,
                source_record_id="crossref-integration-0001",
                title="Confirmed transiting planets around nearby host stars",
                authors=("Integration Researcher",),
                year=2024,
                doi="10.9999/integration-0001",
                arxiv_id=None,
                url="https://doi.org/10.9999/integration-0001",
                abstract=None,
            ),
        )
        record_payload = [record.hash_payload() for record in records]
        snapshot = SourceSnapshotRecord(
            snapshot_id=_SNAPSHOT_ID,
            source_id=self.source_id,
            source_type="paper_metadata",
            retrieved_at=_FIXED_NOW,
            query=query.original_query_string,
            query_hash=query.query_hash,
            source_version_or_etag=None,
            content_hash=canonical_request_hash({"records": record_payload}),
            license_note="Deposited metadata; publisher license governs content",
            cache_version=None,
            request_metadata={
                "adapter_name": self.adapter_name,
                "adapter_version": self.adapter_version,
            },
        )
        page = PaperSourcePage(
            page_number=1,
            offset=0,
            requested_rows=20,
            returned_rows=1,
            total_results=1,
            attempt_count=1,
            status_code=200,
            retrieved_at=_FIXED_NOW,
            request_hash=canonical_request_hash({"page": 1}),
            response_hash=canonical_request_hash({"records": record_payload}),
        )
        return SourceSearchResult(
            records=records,
            pages=(page,),
            snapshot=snapshot,
            retry_count=0,
        )


def _accepted_confidence(
    *,
    claim_artifact_version_id: str,
    claims: Iterable[LiteratureClaimCandidate],
) -> dict[str, LiteratureRelationConfidenceAssessment]:
    assessments: dict[str, LiteratureRelationConfidenceAssessment] = {}
    eligible = tuple(sorted(claims, key=lambda claim: claim.claim_id))
    for source in eligible:
        for target in eligible:
            if source.claim_id == target.claim_id:
                continue
            for relation_type in LiteratureRelationType:
                subject = build_literature_relation_confidence_subject(
                    source_claim_artifact_version_id=claim_artifact_version_id,
                    source_claim_id=source.claim_id,
                    target_claim_artifact_version_id=claim_artifact_version_id,
                    target_claim_id=target.claim_id,
                    relation_type=relation_type,
                )
                assessment_id = f"assessment.live_scope.{subject.fingerprint[7:31]}"
                assessments[assessment_id] = LiteratureRelationConfidenceAssessment(
                    assessment_id=assessment_id,
                    subject=subject,
                    decision=LiteratureRelationStatus.accepted,
                    status=LiteratureRelationConfidenceStatus.assessed,
                    score=0.97,
                    definition_id=RELATION_CONFIDENCE_DEFINITION_ID,
                    definition_version=RELATION_CONFIDENCE_DEFINITION_VERSION,
                    calibration_id=RELATION_CONFIDENCE_CALIBRATION_ID,
                    calibration_version=RELATION_CONFIDENCE_CALIBRATION_VERSION,
                    calibration_scientific_payload_hash=FROZEN_SCIENTIFIC_PAYLOAD_HASH,
                    calibration_content_hash=FROZEN_BENCHMARK_CONTENT_HASH,
                    calibration_sample_size=RELATION_CONFIDENCE_CALIBRATION_SAMPLE_SIZE,
                    calibration_method=RELATION_CONFIDENCE_CALIBRATION_METHOD,
                    applicability_scope=RELATION_CONFIDENCE_APPLICABILITY_SCOPE,
                    acceptance_threshold=RELATION_CONFIDENCE_ACCEPTANCE_THRESHOLD,
                    basis=("Deterministic integration reference assessment.",),
                )
    return assessments


def bootstrap_fixture_research_results(
    *,
    session_id: str,
    run_id: str,
    factory: Callable[[], Session],
    research_service: ResearchApplicationService,
    workflow_store: PersistentWorkflowStore,
) -> ResearchResultsBootstrapResult:
    """Execute an owned demo replay through the existing Worker and Publisher."""

    run = research_service.get_run(run_id=run_id, session_id=session_id)
    if run.execution_mode.value != "demo_replay":
        raise SecurityProblem(
            status=409,
            code="BOOTSTRAP_RUN_NOT_DEMO_REPLAY",
            title="Bootstrap requires a demo_replay run",
            detail="Fixture research results require a demo_replay run",
        )
    run_uuid = UUID(run.id)
    existing = _result_versions(factory=factory, run_id=run_uuid)
    if _REQUIRED_KINDS.issubset(existing):
        return ResearchResultsBootstrapResult(
            run_id=run.id,
            artifact_version_ids=existing,
        )
    if existing:
        raise RuntimeError("Integration research result bundle is partially published")

    manifests = _load_manifests()
    model = DeterministicIntegrationModelExecutionPort()
    worker = ResearchRunWorker(
        factory=factory,
        store=workflow_store,
        executor=PersistentWorkflowExecutor(workflow_store),
        manifests=manifests,
        model_port=model,
        requested_model="qwen3.8-max",
        explicit_revision=None,
        paper_collection_runner=LivePaperCollectionRunner(
            adapter=_IntegrationPaperSource(),
            clock=lambda: _FIXED_NOW,
        ),
        relation_confidence_builder=_accepted_confidence,
    )
    asyncio.run(worker.execute_run(run_uuid))

    completed = workflow_store.load_snapshot(run_uuid)
    if completed.status != "completed":
        raise RuntimeError(
            f"Integration research bootstrap did not complete: {completed.status}"
        )
    versions = _result_versions(factory=factory, run_id=run_uuid)
    if not _REQUIRED_KINDS.issubset(versions):
        raise RuntimeError(
            "Integration research bootstrap did not publish its result closure"
        )
    return ResearchResultsBootstrapResult(
        run_id=run.id,
        artifact_version_ids=versions,
    )


def _result_versions(
    *,
    factory: Callable[[], Session],
    run_id: UUID,
) -> dict[str, str]:
    with factory() as session:
        return {
            kind: str(version_id)
            for kind, version_id in session.execute(
                select(ResearchArtifactModel.kind, ArtifactVersionModel.id)
                .join(
                    ArtifactVersionModel,
                    ArtifactVersionModel.artifact_id == ResearchArtifactModel.id,
                )
                .where(ArtifactVersionModel.created_by_run_id == run_id)
                .order_by(ResearchArtifactModel.kind)
            )
        }


def _load_manifests() -> ManifestBundle:
    relative = Path("services/data_pipeline/manifests/exoplanet_host_star")
    for parent in Path(__file__).resolve().parents:
        root = parent / relative
        case_manifest = root / "case-manifest.json"
        field_manifest = root / "field-manifest.json"
        if case_manifest.is_file() and field_manifest.is_file():
            return load_manifest_bundle(case_manifest, field_manifest)
    raise RuntimeError("Integration research manifests are missing")


__all__ = [
    "ResearchResultsBootstrapResult",
    "bootstrap_fixture_research_results",
]
