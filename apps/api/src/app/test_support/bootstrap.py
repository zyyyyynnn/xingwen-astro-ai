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
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models import (
    ArtifactVersionModel,
    ResearchArtifactModel,
    SourceSnapshotModel,
)
from app.schemas.core import (
    ArtifactKind,
    ResearchContract,
)
from app.schemas.data_artifacts import (
    CrossmatchArtifactAuthority,
    CrossmatchDataArtifactAuthority,
    DataArtifactBuildInput,
    DataArtifactBuildResult,
    DatasetArtifactCandidate,
    ManifestPins,
    compute_data_artifact_input_hash,
)
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
from app.workflow.step_publication import step_uuid
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


@dataclass(frozen=True, slots=True)
class FixtureArtifactPublication:
    kind: ArtifactKind
    candidate: AdmittedArtifactCandidate
    source_snapshot_bindings: tuple[ArtifactSourceSnapshotBinding, ...]
    evidence_bindings: tuple[ArtifactEvidenceBinding, ...]


@dataclass(frozen=True, slots=True)
class FixtureDataPublicationBundle:
    data_input: DataArtifactBuildInput
    artifacts: tuple[FixtureArtifactPublication, ...]


def build_fixture_dataset_publication(
    *,
    contract: ResearchContract,
    run_id: str,
) -> FixtureDatasetPublication:
    """Build and admit the frozen Dataset against the exact Run Contract."""

    bundle = _build_fixture_data_publication_bundle(contract=contract, run_id=run_id)
    publication = next(
        item for item in bundle.artifacts if item.kind is ArtifactKind.dataset
    )
    return FixtureDatasetPublication(
        data_input=bundle.data_input,
        candidate=publication.candidate,
        source_snapshot_bindings=publication.source_snapshot_bindings,
        evidence_bindings=publication.evidence_bindings,
    )


def _build_fixture_data_publication_bundle(
    *,
    contract: ResearchContract,
    run_id: str,
) -> FixtureDataPublicationBundle:
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
    candidates = {
        ArtifactKind.dataset: build_result.dataset,
        ArtifactKind.field_dictionary: build_result.field_dictionary,
        ArtifactKind.source_collection: build_result.source_collection,
    }
    publications: list[FixtureArtifactPublication] = []
    for kind, artifact_candidate in candidates.items():
        source_snapshot_bindings, evidence_bindings = _publication_bindings(
            run_id=run_id,
            kind=kind,
            candidate=build_result.dataset,
        )
        candidate = admit_artifact_candidate(
            artifact_candidate,
            schema_version=artifact_candidate.schema_version,
            source_snapshot_ids=artifact_candidate.source_snapshot_ids,
            evidence_ids=artifact_candidate.evidence_ids,
            evidence_validator=validate_data_artifact_evidence,
            domain_validator=validate_data_artifact_domain,
            quality_validator=build_data_quality_publication_validator(
                quality_admission,
                candidate_kind=kind.value,
            ),
            source_snapshot_bindings=source_snapshot_bindings,
            evidence_bindings=evidence_bindings,
            data_provenance_candidate=(
                None if kind is ArtifactKind.dataset else build_result.dataset
            ),
        )
        publications.append(
            FixtureArtifactPublication(
                kind=kind,
                candidate=candidate,
                source_snapshot_bindings=source_snapshot_bindings,
                evidence_bindings=evidence_bindings,
            )
        )
    return FixtureDataPublicationBundle(
        data_input=data_input,
        artifacts=tuple(publications),
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
    bundle = _build_fixture_data_publication_bundle(contract=contract, run_id=run.id)
    artifact_ids = {
        publication.kind: step_uuid(
            str(project_id), f"artifact:{publication.kind.value}"
        )
        for publication in bundle.artifacts
    }

    with factory() as session:
        existing_versions = {
            kind: session.scalar(
                select(ArtifactVersionModel)
                .where(
                    ArtifactVersionModel.artifact_id == artifact_id,
                    ArtifactVersionModel.created_by_run_id == run_uuid,
                )
                .limit(1)
            )
            for kind, artifact_id in artifact_ids.items()
        }
        supersedes_version_ids = {
            kind: (
                artifact.latest_version_id
                if (artifact := session.get(ResearchArtifactModel, artifact_id))
                is not None
                else None
            )
            for kind, artifact_id in artifact_ids.items()
        }
    existing_count = sum(value is not None for value in existing_versions.values())
    if existing_count not in {0, len(existing_versions)}:
        raise RuntimeError("Bootstrap data Artifact bundle is only partially published")
    if existing_count == 0:
        published_ids = _publish_fixture_bundle(
            run_id=run.id,
            factory=factory,
            workflow_store=workflow_store,
            run_uuid=run_uuid,
            project_id=project_id,
            artifact_ids=artifact_ids,
            bundle=bundle,
            supersedes_version_ids=supersedes_version_ids,
        )
        with factory() as session:
            existing_versions = {
                kind: session.get(ArtifactVersionModel, version_id)
                for kind, version_id in published_ids.items()
            }
    dataset_version = existing_versions[ArtifactKind.dataset]
    if dataset_version is None:
        raise RuntimeError("Bootstrap publication did not persist an ArtifactVersion")

    return BootstrapResult(
        run_id=run.id,
        artifact_id=str(artifact_ids[ArtifactKind.dataset]),
        artifact_version_id=str(dataset_version.id),
        source_snapshot_ids=tuple(dataset_version.source_snapshot_ids),
        evidence_ids=tuple(dataset_version.evidence_ids),
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
    authority = CrossmatchDataArtifactAuthority(
        left_acquisition=crossmatch_input.left,
        right_acquisition=crossmatch_input.right,
        crossmatch_result=crossmatch_result,
        document_observations=(),
    )
    payload = {
        "manifest_pins": pins.model_dump(mode="json"),
        "requested_fields": requested_fields,
        "authority": authority.model_dump(mode="json"),
        "mapping_rule_set": mapping_rule_set.model_dump(mode="json"),
        "conversion_catalog": conversion_catalog.model_dump(mode="json"),
        "producer_version": mapping_rule_set.producer_version,
        "quality_constraints_reference": "research_contract.quality_constraints.fixture",
    }
    unhashed = DataArtifactBuildInput.model_construct(
        manifest_pins=pins,
        requested_fields=requested_fields,
        authority=authority,
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
    kind: ArtifactKind,
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
    crossmatch_evidence = (
        {item.evidence_id: item for item in candidate.authority.evidence}
        if isinstance(candidate.authority, CrossmatchArtifactAuthority)
        else {}
    )

    evidence_bindings: list[ArtifactEvidenceBinding] = []
    for pipeline_id in candidate.evidence_ids:
        transformation = transformations.get(pipeline_id)
        if transformation is not None:
            target_type = "canonical_field"
            target_id = transformation.canonical_field_id
            pipeline_snapshot_id = transformation.locator.source_snapshot_id
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
                    _seed_uuid(run_id, f"{kind.value}:evidence:{pipeline_id}")
                ),
                persisted_source_snapshot_id=persisted_snapshots[pipeline_snapshot_id],
            )
        )
    return snapshot_bindings, tuple(evidence_bindings)


def _publish_fixture_bundle(
    *,
    run_id: str,
    factory: Callable[[], Session],
    workflow_store: PersistentWorkflowStore,
    run_uuid: UUID,
    project_id: UUID,
    artifact_ids: dict[ArtifactKind, UUID],
    bundle: FixtureDataPublicationBundle,
    supersedes_version_ids: dict[ArtifactKind, UUID | None],
) -> dict[ArtifactKind, UUID]:
    """Drive the frozen Run and publish one coherent Data Artifact bundle."""
    snapshot = workflow_store.load_snapshot(run_uuid)
    if "cleaning_data" not in {step.key for step in snapshot.steps}:
        raise SecurityProblem(
            status=409,
            code="BOOTSTRAP_RUN_PLAN_UNSUPPORTED",
            title="Bootstrap run plan unsupported",
            detail="Fixture data publication requires the cleaning_data RunStep",
        )
    lease = workflow_store.acquire_lease(
        run_uuid,
        owner="real_integration-test-bootstrap",
        lease_duration=timedelta(minutes=5),
        expected_status="queued",
        expected_revision=snapshot.revision,
    )
    with factory() as session, session.begin():
        titles = {
            ArtifactKind.dataset: "Exoplanet host-star dataset",
            ArtifactKind.field_dictionary: "Dataset field dictionary",
            ArtifactKind.source_collection: "Dataset source collection",
        }
        for kind, artifact_id in artifact_ids.items():
            session.execute(
                insert(ResearchArtifactModel)
                .values(
                    id=artifact_id,
                    project_id=project_id,
                    kind=kind.value,
                    title=titles[kind],
                    logical_key=f"{kind.value}.primary",
                )
                .on_conflict_do_nothing(index_elements=("id",))
            )
            artifact = session.get(ResearchArtifactModel, artifact_id)
            if (
                artifact is None
                or artifact.project_id != project_id
                or artifact.kind != kind.value
                or artifact.logical_key != f"{kind.value}.primary"
            ):
                raise RuntimeError(
                    f"Bootstrap {kind.value} artifact identity is not consistent"
                )
        data_input = bundle.data_input
        if not isinstance(
            data_input.authority,
            CrossmatchDataArtifactAuthority,
        ):
            raise RuntimeError("Demo replay bootstrap requires Crossmatch authority")
        for source in (
            data_input.authority.left_acquisition.snapshot,
            data_input.authority.right_acquisition.snapshot,
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

    ledger = ProducerExecutionStore(factory)
    publisher = ArtifactPublisher(factory)
    published_ids: dict[ArtifactKind, UUID] = {}
    current_revision = lease.revision
    current_status = snapshot.status
    for step in snapshot.steps:
        attempt = workflow_store.begin_step(
            run_uuid,
            step_key=step.key,
            attempt_idempotency_key=(
                f"real_integration-bootstrap-attempt-{run_id}-{step.key}"
            ),
            token=lease.token,
            generation=lease.generation,
            expected_status=current_status,
            expected_revision=current_revision,
            public_message=f"Completing deterministic {step.label}",
        )
        publications: tuple[ArtifactPublication, ...] = ()
        if step.key == "cleaning_data":
            outputs: list[ArtifactPublication] = []
            for publication in bundle.artifacts:
                producer_payload = publication.candidate.content.get("producer")
                if not isinstance(producer_payload, dict):
                    raise TypeError(
                        f"Bootstrap {publication.kind.value} candidate is missing producer metadata"
                    )
                execution = ledger.start_producer_execution(
                    ProducerExecutionRequest(
                        run_id=run_uuid,
                        step_key=step.key,
                        attempt_id=attempt.attempt_id,
                        idempotency_key=(
                            "real_integration-bootstrap-producer-"
                            f"{run_id}-{publication.kind.value}"
                        ),
                        producer_type=str(
                            producer_payload.get("producer_type", "algorithm")
                        ),
                        producer_name=str(
                            producer_payload.get(
                                "producer_name",
                                f"data-artifact-{publication.kind.value}",
                            )
                        ),
                        producer_version=str(
                            producer_payload.get("producer_version", "1.0.0")
                        ),
                        input_hash=bundle.data_input.input_hash,
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
                    output_hash=publication.candidate.content_hash,
                )
                outputs.append(
                    ArtifactPublication(
                        artifact_id=artifact_ids[publication.kind],
                        publication_key=(
                            "real_integration-bootstrap-"
                            f"{publication.kind.value}-{run_id}"
                        ),
                        producer_execution_id=execution.id,
                        candidate=publication.candidate,
                        source_mode="fixture",
                        supersedes_version_id=supersedes_version_ids[publication.kind],
                    )
                )
            publications = tuple(outputs)
        result = publisher.publish_step_outputs(
            run_uuid,
            step_key=step.key,
            attempt_id=attempt.attempt_id,
            token=lease.token,
            generation=lease.generation,
            expected_status=attempt.run_status,
            expected_revision=attempt.run_revision,
            publications=publications,
            public_message=(
                "Deterministic demo_replay Data Artifacts published"
                if publications
                else f"Deterministic {step.label} completed"
            ),
        )
        current_status = result.status
        current_revision = result.revision
        if publications:
            kind_by_artifact_id = {
                artifact_id: kind for kind, artifact_id in artifact_ids.items()
            }
            for version in result.versions:
                kind = kind_by_artifact_id.get(version.artifact_id)
                if kind is None:
                    raise RuntimeError(
                        "Bootstrap publisher returned an unknown ResearchArtifact"
                    )
                published_ids[kind] = version.id
    if set(published_ids) != set(artifact_ids):
        raise RuntimeError(
            "Bootstrap did not publish the complete Data Artifact bundle"
        )
    return published_ids
