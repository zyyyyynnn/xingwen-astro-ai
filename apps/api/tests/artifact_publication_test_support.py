"""Real canonical ArtifactVersion publication helpers for PostgreSQL tests."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    ResearchArtifactModel,
    ResearchContractModel,
    ResearchProjectModel,
)
from app.schemas.core import (
    ResearchContract,
    ResearchContractInput,
    compute_research_contract_content_hash,
)
from app.schemas.manifest import load_manifest_bundle
from app.services.research import CANONICAL_RUN_STEPS, ResearchApplicationService
from app.test_support.bootstrap import (
    bootstrap_fixture_artifacts,
    build_fixture_dataset_publication,
)
from app.workflow.publisher import AdmittedArtifactCandidate
from app.workflow.store import PersistentWorkflowStore
from authoring_test_support import build_contract_draft, build_research_contract


def publish_reference_dataset(
    *,
    factory: Callable[[], Session],
    project: ResearchProjectModel,
) -> UUID:
    """Publish a canonical quality-admitted Dataset in an isolated fixture Run."""

    with factory() as session:
        existing = session.scalar(
            select(ResearchArtifactModel).where(
                ResearchArtifactModel.project_id == project.id,
                ResearchArtifactModel.logical_key == "dataset.primary",
            )
        )
        if existing is not None:
            if existing.latest_version_id is None:
                raise AssertionError(
                    "The canonical Dataset Artifact exists without a published version"
                )
            return existing.latest_version_id

    contract_input = _reference_contract_input()
    content = contract_input.model_dump(mode="json")
    draft = build_contract_draft(project, content=content)
    contract = build_research_contract(
        project,
        draft,
        contract_id=uuid4(),
        content_hash=compute_research_contract_content_hash(contract_input),
        content=content,
    )
    with factory() as session, session.begin():
        contract.version = (
            session.scalar(
                select(func.coalesce(func.max(ResearchContractModel.version), 0)).where(
                    ResearchContractModel.project_id == project.id
                )
            )
            or 0
        ) + 1
        session.add(draft)
        session.flush()
        session.add(contract)

    workflow = PersistentWorkflowStore(factory)
    run = workflow.create_run(
        project_id=project.id,
        contract_id=contract.id,
        execution_mode="demo_replay",
        idempotency_key=f"reference-dataset-run-{uuid4()}",
        request_hash="sha256:" + "d" * 64,
        steps=CANONICAL_RUN_STEPS,
    )
    manifest_root = (
        Path(__file__).resolve().parents[3]
        / "services"
        / "data_pipeline"
        / "manifests"
        / "exoplanet_host_star"
    )
    service = ResearchApplicationService(
        factory=factory,
        workflow_store=workflow,
        manifests=load_manifest_bundle(
            manifest_root / "case-manifest.json",
            manifest_root / "field-manifest.json",
        ),
    )
    published = bootstrap_fixture_artifacts(
        session_id=project.session_id,
        run_id=str(run.id),
        factory=factory,
        research_service=service,
        workflow_store=workflow,
    )
    return UUID(published.artifact_version_id)


def build_reference_dataset_candidate(*, run_id: UUID) -> AdmittedArtifactCandidate:
    contract_input = _reference_contract_input()
    contract = ResearchContract(
        **contract_input.model_dump(mode="json"),
        id=str(uuid4()),
        project_id=str(uuid4()),
        version=1,
        content_hash=compute_research_contract_content_hash(contract_input),
        created_from_draft_id=str(uuid4()),
        created_at=datetime.now(UTC),
    )
    return build_fixture_dataset_publication(
        contract=contract,
        run_id=str(run_id),
    ).candidate


def _reference_contract_input() -> ResearchContractInput:
    return ResearchContractInput.model_validate(
        {
            "research_goal": "Publish a deterministic exoplanet host-star reference dataset",
            "target_objects": ["exoplanet_candidate", "host_star"],
            "data_requirements": {"unit_policy": "canonical"},
            "requested_fields": ["planet.toi_id", "star.tic_id"],
            "source_scope": {"allowed_sources": ["nasa_exoplanet_archive"]},
            "paper_search_scope": {"year_from": 2015, "max_candidates": 20},
            "output_requirements": ["dataset", "field_dictionary", "graph"],
            "evidence_requirements": {"require_locator": True},
            "quality_constraints": {"source_completeness_min": 1.0},
        }
    )


__all__ = ["build_reference_dataset_candidate", "publish_reference_dataset"]
