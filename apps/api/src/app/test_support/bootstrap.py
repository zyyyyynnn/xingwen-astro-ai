"""Deterministic demo_replay data publication for real integration runs.

The public Authoring Chain keeps this module focused on fixture publication:
(``createResearchProject``, ``createResearchContractDraft``, draft update,
contract confirm, run create) is exercised through the real ``/api``
runtime, so the bootstrap no longer injects Project, ContractDraft, Contract,
Run, credentials or Share tokens. Its only job is publishing the frozen main
case's deterministic ``demo_replay``/``fixture`` Dataset ArtifactVersion + Evidence
onto a session-owned Run through the existing Persistence/Publisher boundary
(the fixture path has no live executor to produce them).

Hard boundaries:

- Only reachable when ``APP_ENV`` is ``test`` or ``integration``; the router is
  never mounted in ``development`` or ``production``.
- Not a Live pipeline: the artifact is published with ``source_mode="fixture"``
  and only onto a Run whose ``execution_mode`` is ``demo_replay``.
- Never returns or logs the session credential, CSRF token, or share token;
  entity ids are derived with ``uuid5`` from the target run id.
- No arbitrary artifact content can be uploaded: the payload is built by the
  frozen data pipeline and is validated by the real data and quality admission
  validators.
- Reuses the real runtime path (ResearchApplicationService ownership check,
  PersistentWorkflowStore, ArtifactPublisher) instead of parallel state.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Callable
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    ArtifactVersionModel,
    ResearchArtifactModel,
    SourceSnapshotModel,
)
from app.schemas.core import (
    ResearchContract,
)
from app.schemas.data_artifacts import (
    DataArtifactBuildInput,
    DataArtifactBuildResult,
    DatasetArtifactCandidate,
    ManifestPins,
    compute_data_artifact_input_hash,
)
from app.schemas.core import DataRequirements, DocumentSourcePolicy
from app.schemas.data_quality import (
    DataQualityEvaluationInput,
    DataQualityEvaluationResult,
    compute_data_quality_input_hash,
)
from app.security import SecurityProblem
from app.services.research import ResearchApplicationService
from services.data_pipeline.crossmatch import (
    align_cross_source_records,
    build_crossmatch_scenario_input,
    load_crossmatch_benchmark,
)
from services.data_pipeline.data_artifacts import build_data_artifact_candidates
from services.data_pipeline.data_artifacts.admission import (
    validate_data_artifact_domain,
    validate_data_artifact_evidence,
)
from services.data_pipeline.data_artifacts.policy import (
    load_mapping_rule_set,
    load_unit_conversion_catalog,
)
from services.data_pipeline.data_quality import (
    admit_data_artifact_quality,
    build_data_quality_publication_validator,
    evaluate_data_quality,
)
from services.data_pipeline.data_quality.policy import load_frozen_quality_rule_set
from app.workflow.publisher import (
    AdmittedArtifactCandidate,
    ArtifactEvidenceBinding,
    ArtifactPublication,
    ArtifactSourceSnapshotBinding,
    ArtifactPublisher,
    ProducerExecutionRequest,
    ProducerExecutionStore,
    admit_artifact_candidate,
)
from app.workflow.store import PersistentWorkflowStore

_NAMESPACE = "https://xingwen.example/test-only-bootstrap"
_SCENARIO_ID = "curated_alias"


def _seed_uuid(run_id: str, entity: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"{_NAMESPACE}/{run_id}/{entity}")


class BootstrapResult(BaseModel):
    """Known ids of the published dataset. Never contains credentials."""

    model_config = ConfigDict(frozen=True)

    run_id: str
    artifact_id: str
    artifact_version_id: str
    source_snapshot_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    execution_mode: str = "demo_replay"
    source_mode: str = "fixture"
    scenario: str = "exoplanet_host_star"


@dataclass(frozen=True, slots=True)
class FixtureDatasetPublication:
    data_input: DataArtifactBuildInput
    candidate: AdmittedArtifactCandidate
    source_snapshot_bindings: tuple[ArtifactSourceSnapshotBinding, ...]
    evidence_bindings: tuple[ArtifactEvidenceBinding, ...]


def build_fixture_dataset_publication(
    *,
    contract: ResearchContract,
    run_id: str,
) -> FixtureDatasetPublication:
    """Build and admit the frozen Dataset against the exact Run Contract."""

    data_input = _build_fixture_data_input(tuple(contract.requested_fields))
    build_result = build_data_artifact_candidates(data_input)
    quality_input = _build_quality_input(
        contract,
        data_input=data_input,
        build_result=build_result,
    )
    quality_result = evaluate_data_quality(quality_input)
    if not isinstance(quality_result, DataQualityEvaluationResult):
        raise SecurityProblem(
            status=422,
            code="BOOTSTRAP_DATA_QUALITY_REJECTED",
            title="Bootstrap data quality rejected",
            detail="The frozen bootstrap dataset did not produce a passing quality result",
        )
    quality_admission = admit_data_artifact_quality(
        build_result=build_result,
        evaluation_input=quality_input,
        evaluation_result=quality_result,
    )
    source_snapshot_bindings, evidence_bindings = _publication_bindings(
        run_id=run_id,
        candidate=build_result.dataset,
    )
    candidate = admit_artifact_candidate(
        build_result.dataset,
        schema_version=build_result.dataset.schema_version,
        source_snapshot_ids=build_result.dataset.source_snapshot_ids,
        evidence_ids=build_result.dataset.evidence_ids,
        evidence_validator=validate_data_artifact_evidence,
        domain_validator=validate_data_artifact_domain,
        quality_validator=build_data_quality_publication_validator(
            quality_admission,
            candidate_kind="dataset",
        ),
        source_snapshot_bindings=source_snapshot_bindings,
        evidence_bindings=evidence_bindings,
    )
    return FixtureDatasetPublication(
        data_input=data_input,
        candidate=candidate,
        source_snapshot_bindings=source_snapshot_bindings,
        evidence_bindings=evidence_bindings,
    )


def bootstrap_fixture_artifacts(
    *,
    session_id: str,
    run_id: str,
    factory: Callable[[], Session],
    research_service: ResearchApplicationService,
    workflow_store: PersistentWorkflowStore,
) -> BootstrapResult:
    """Publish the deterministic fixture version onto ``run_id`` (idempotent).

    The run must already exist, belong to the calling session (ownership is
    checked through the real application boundary, so cross-session runs stay
    a hidden 404) and use ``execution_mode="demo_replay"``.
    """
    run = research_service.get_run(run_id=run_id, session_id=session_id)
    if run.execution_mode.value != "demo_replay":
        raise SecurityProblem(
            status=409,
            code="BOOTSTRAP_RUN_NOT_DEMO_REPLAY",
            title="Bootstrap requires a demo_replay run",
            detail="Fixture artifacts can only be published onto a demo_replay run",
        )

    run_uuid = UUID(run.id)
    project_id = UUID(run.project_id)
    contract = research_service.get_contract(
        contract_id=run.contract_id,
        session_id=session_id,
    )
    publication = build_fixture_dataset_publication(contract=contract, run_id=run.id)
    data_input = publication.data_input
    candidate = publication.candidate
    source_snapshot_bindings = publication.source_snapshot_bindings
    evidence_bindings = publication.evidence_bindings
    artifact_id = _seed_uuid(run.id, "dataset-artifact")

    with factory() as session:
        existing_version = session.scalar(
            select(ArtifactVersionModel)
            .where(ArtifactVersionModel.artifact_id == artifact_id)
            .limit(1)
        )
    if existing_version is None:
        existing_version_id = _publish_fixture_version(
            run_id=run.id,
            factory=factory,
            workflow_store=workflow_store,
            run_uuid=run_uuid,
            project_id=project_id,
            artifact_id=artifact_id,
            data_input=data_input,
            candidate=candidate,
            source_snapshot_bindings=source_snapshot_bindings,
            evidence_bindings=evidence_bindings,
        )
        with factory() as session:
            existing_version = session.get(ArtifactVersionModel, existing_version_id)
    if existing_version is None:
        raise RuntimeError("Bootstrap publication did not persist an ArtifactVersion")

    return BootstrapResult(
        run_id=run.id,
        artifact_id=str(artifact_id),
        artifact_version_id=str(existing_version.id),
        source_snapshot_ids=tuple(existing_version.source_snapshot_ids),
        evidence_ids=tuple(existing_version.evidence_ids),
    )


def _build_fixture_data_input(
    requested_fields: tuple[str, ...],
) -> DataArtifactBuildInput:
    benchmark = load_crossmatch_benchmark()
    scenario = next(
        item for item in benchmark.scenarios if item.scenario_id == _SCENARIO_ID
    )
    crossmatch_input = build_crossmatch_scenario_input(scenario)
    crossmatch_result = align_cross_source_records(crossmatch_input)
    pins = ManifestPins(
        case_manifest_id=crossmatch_result.case_manifest_id,
        case_manifest_version=crossmatch_result.case_manifest_version,
        case_manifest_content_hash=crossmatch_result.case_manifest_content_hash,
        field_manifest_id=crossmatch_result.field_manifest_id,
        field_manifest_version=crossmatch_result.field_manifest_version,
        field_manifest_content_hash=crossmatch_result.field_manifest_content_hash,
    )
    mapping_rule_set = load_mapping_rule_set()
    conversion_catalog = load_unit_conversion_catalog()
    payload = {
        "data_requirements": {
            "unit_policy": "canonical",
            "document_source_policy": "disabled",
        },
        "document_observations": (),
        "manifest_pins": pins.model_dump(mode="json"),
        "requested_fields": requested_fields,
        "left_acquisition": crossmatch_input.left.model_dump(mode="json"),
        "right_acquisition": crossmatch_input.right.model_dump(mode="json"),
        "crossmatch_result": crossmatch_result.model_dump(mode="json"),
        "mapping_rule_set": mapping_rule_set.model_dump(mode="json"),
        "conversion_catalog": conversion_catalog.model_dump(mode="json"),
        "producer_version": mapping_rule_set.producer_version,
        "quality_constraints_reference": "research_contract.quality_constraints.fixture",
    }
    unhashed = DataArtifactBuildInput.model_construct(
        data_requirements=DataRequirements(
            document_source_policy=DocumentSourcePolicy.disabled
        ),
        document_observations=(),
        manifest_pins=pins,
        requested_fields=requested_fields,
        left_acquisition=crossmatch_input.left,
        right_acquisition=crossmatch_input.right,
        crossmatch_result=crossmatch_result,
        mapping_rule_set=mapping_rule_set,
        conversion_catalog=conversion_catalog,
        producer_version=mapping_rule_set.producer_version,
        quality_constraints_reference="research_contract.quality_constraints.fixture",
        input_hash="sha256:" + "0" * 64,
    )
    payload["input_hash"] = compute_data_artifact_input_hash(unhashed)
    return DataArtifactBuildInput.model_validate(payload)


def _build_quality_input(
    contract: ResearchContract,
    *,
    data_input: DataArtifactBuildInput,
    build_result: DataArtifactBuildResult,
) -> DataQualityEvaluationInput:
    quality_rules = load_frozen_quality_rule_set()
    payload = {
        "data_artifact_input": data_input,
        "dataset_candidate": build_result.dataset,
        "field_dictionary_candidate": build_result.field_dictionary,
        "source_collection_candidate": build_result.source_collection,
        "research_contract": contract,
        "quality_rule_set": quality_rules,
        "input_hash": "sha256:" + "0" * 64,
    }
    constructed = DataQualityEvaluationInput.model_construct(**payload)
    payload["input_hash"] = compute_data_quality_input_hash(constructed)
    return DataQualityEvaluationInput.model_validate(payload)


def _publication_bindings(
    *,
    run_id: str,
    candidate: DatasetArtifactCandidate,
) -> tuple[
    tuple[ArtifactSourceSnapshotBinding, ...], tuple[ArtifactEvidenceBinding, ...]
]:
    persisted_snapshots = {
        pipeline_id: str(_seed_uuid(run_id, f"source-snapshot:{pipeline_id}"))
        for pipeline_id in candidate.source_snapshot_ids
    }
    snapshot_bindings = tuple(
        ArtifactSourceSnapshotBinding(
            pipeline_source_snapshot_id=pipeline_id,
            persisted_source_snapshot_id=persisted_snapshots[pipeline_id],
        )
        for pipeline_id in candidate.source_snapshot_ids
    )

    transformations = {
        item.evidence_id: item for item in candidate.transformation_evidence
    }
    crossmatch_evidence = {
        item.evidence_id: item for item in candidate.crossmatch_evidence
    }

    evidence_bindings: list[ArtifactEvidenceBinding] = []
    for pipeline_id in candidate.evidence_ids:
        transformation = transformations.get(pipeline_id)
        if transformation is not None:
            target_type = "canonical_field"
            target_id = transformation.canonical_field_id
            pipeline_snapshot_id = transformation.provenance.pipeline_source_snapshot_id
        else:
            evidence = crossmatch_evidence.get(pipeline_id)
            if evidence is None:
                raise ValueError(
                    f"Bootstrap Evidence {pipeline_id} has no materializable SourceSnapshot"
                )
            target_type = "crossmatch"
            target_id = pipeline_id
            left_snapshot_ids = {
                item.source_snapshot_id for item in evidence.left_locators
            }
            if len(left_snapshot_ids) != 1:
                raise ValueError(
                    f"Bootstrap Evidence {pipeline_id} has ambiguous left provenance"
                )
            pipeline_snapshot_id = next(iter(left_snapshot_ids))
        evidence_bindings.append(
            ArtifactEvidenceBinding(
                target_type=target_type,
                target_id=target_id,
                pipeline_evidence_id=pipeline_id,
                pipeline_source_snapshot_id=pipeline_snapshot_id,
                persisted_evidence_id=str(
                    _seed_uuid(run_id, f"evidence:{pipeline_id}")
                ),
                persisted_source_snapshot_id=persisted_snapshots[pipeline_snapshot_id],
            )
        )
    return snapshot_bindings, tuple(evidence_bindings)


def _publish_fixture_version(
    *,
    run_id: str,
    factory: Callable[[], Session],
    workflow_store: PersistentWorkflowStore,
    run_uuid: UUID,
    project_id: UUID,
    artifact_id: UUID,
    data_input: DataArtifactBuildInput,
    candidate: AdmittedArtifactCandidate,
    source_snapshot_bindings: tuple[ArtifactSourceSnapshotBinding, ...],
    evidence_bindings: tuple[ArtifactEvidenceBinding, ...],
) -> UUID:
    """Drive one workflow step and publish the frozen Dataset candidate."""
    snapshot = workflow_store.load_snapshot(run_uuid)
    lease = workflow_store.acquire_lease(
        run_uuid,
        owner="real_integration-test-bootstrap",
        lease_duration=timedelta(minutes=5),
        expected_status="queued",
        expected_revision=snapshot.revision,
    )
    attempt = workflow_store.begin_step(
        run_uuid,
        step_key="planning",
        attempt_idempotency_key=f"real_integration-bootstrap-attempt-{run_id}",
        token=lease.token,
        generation=lease.generation,
        expected_status="queued",
        expected_revision=lease.revision,
        public_message="Building deterministic demo_replay Dataset",
    )

    with factory() as session, session.begin():
        artifact = session.get(ResearchArtifactModel, artifact_id)
        if artifact is None:
            session.add(
                ResearchArtifactModel(
                    id=artifact_id,
                    project_id=project_id,
                    kind="dataset",
                    title="Exoplanet host-star dataset",
                    logical_key="dataset.primary",
                )
            )
        elif artifact.project_id != project_id or artifact.kind != "dataset":
            raise RuntimeError("Bootstrap Dataset artifact identity is not consistent")
        for source in (
            data_input.left_acquisition.snapshot,
            data_input.right_acquisition.snapshot,
        ):
            source_id = _seed_uuid(run_id, f"source-snapshot:{source.snapshot_id}")
            existing = session.get(SourceSnapshotModel, source_id)
            if existing is None:
                session.add(
                    SourceSnapshotModel(
                        id=source_id,
                        project_id=project_id,
                        source_id=source.source_id,
                        source_type=source.source_type,
                        retrieved_at=source.retrieved_at,
                        query=source.query,
                        query_hash=source.query_hash,
                        source_version_or_etag=source.source_version_or_etag,
                        content_hash=source.content_hash,
                        license_note=source.license_note,
                        cache_version=source.cache_version,
                        request_metadata=source.request_metadata,
                    )
                )
            elif (
                existing.project_id != project_id
                or existing.source_id != source.source_id
                or existing.query_hash != source.query_hash
                or existing.content_hash != source.content_hash
            ):
                raise RuntimeError(
                    "Bootstrap SourceSnapshot identity is not consistent"
                )

    producer_payload = candidate.content.get("producer")
    if not isinstance(producer_payload, dict):
        raise TypeError("Bootstrap Dataset candidate is missing producer metadata")
    ledger = ProducerExecutionStore(factory)
    execution = ledger.start_producer_execution(
        ProducerExecutionRequest(
            run_id=run_uuid,
            step_key="planning",
            attempt_id=attempt.attempt_id,
            idempotency_key=f"real_integration-bootstrap-producer-{run_id}",
            producer_type=str(producer_payload.get("producer_type", "algorithm")),
            producer_name=str(
                producer_payload.get("producer_name", "data-artifact-pipeline")
            ),
            producer_version=str(producer_payload.get("producer_version", "1.0.0")),
            input_hash=data_input.input_hash,
            parameters={"scenario": _SCENARIO_ID},
        ),
        token=lease.token,
        generation=lease.generation,
        expected_status=attempt.run_status,
        expected_revision=attempt.run_revision,
    )
    ledger.finish_producer_execution(
        execution.id,
        status="completed",
        output_hash=candidate.content_hash,
    )
    published = ArtifactPublisher(factory).publish_step_outputs(
        run_uuid,
        step_key="planning",
        attempt_id=attempt.attempt_id,
        token=lease.token,
        generation=lease.generation,
        expected_status=attempt.run_status,
        expected_revision=attempt.run_revision,
        publications=(
            ArtifactPublication(
                artifact_id=artifact_id,
                publication_key=f"real_integration-bootstrap-dataset-{run_id}",
                producer_execution_id=execution.id,
                candidate=candidate,
                source_mode="fixture",
            ),
        ),
        public_message="Deterministic demo_replay Dataset published",
    )
    return published.versions[0].id
