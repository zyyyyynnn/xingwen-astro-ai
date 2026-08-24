from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5

from app.schemas.data_artifacts import (
    DataArtifactBuildInput,
    DatasetArtifactCandidate,
    ManifestPins,
    compute_data_artifact_input_hash,
)
from app.schemas.core import DataRequirements, DocumentSourcePolicy
from app.workflow.publisher import (
    ArtifactEvidenceBinding,
    ArtifactSourceSnapshotBinding,
)
from services.data_pipeline.crossmatch import align_cross_source_records
from services.data_pipeline.crossmatch.benchmark import (
    _scenario_input,
    load_crossmatch_benchmark,
)
from services.data_pipeline.data_artifacts.policy import (
    load_mapping_rule_set,
    load_unit_conversion_catalog,
)


def build_input(
    *requested_fields: str,
    scenario_id: str = "exact_one_to_one",
) -> DataArtifactBuildInput:
    benchmark = load_crossmatch_benchmark()
    scenario = next(
        item for item in benchmark.scenarios if item.scenario_id == scenario_id
    )
    crossmatch_input = _scenario_input(scenario)
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
        "data_requirements": DataRequirements(
            document_source_policy=DocumentSourcePolicy.disabled,
        ).model_dump(mode="json"),
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
            document_source_policy=DocumentSourcePolicy.disabled,
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


def build_data_publication_bindings(
    candidate: DatasetArtifactCandidate,
) -> tuple[
    tuple[ArtifactSourceSnapshotBinding, ...],
    tuple[ArtifactEvidenceBinding, ...],
]:
    persisted_snapshots = {
        pipeline_id: str(uuid5(NAMESPACE_URL, f"test-source-snapshot:{pipeline_id}"))
        for pipeline_id in candidate.source_snapshot_ids
    }
    for value in candidate.source_values:
        if value.provenance.kind == "document":
            persisted_snapshots[value.provenance.pipeline_source_snapshot_id] = (
                value.provenance.persisted_source_snapshot_id
            )
    snapshots = tuple(
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
            crossmatch = crossmatch_evidence[pipeline_id]
            left_snapshot_ids = {
                item.source_snapshot_id for item in crossmatch.left_locators
            }
            if len(left_snapshot_ids) != 1:
                raise AssertionError("CrossmatchEvidence must have one left Snapshot")
            target_type = "crossmatch"
            target_id = pipeline_id
            pipeline_snapshot_id = next(iter(left_snapshot_ids))
        evidence_bindings.append(
            ArtifactEvidenceBinding(
                target_type=target_type,
                target_id=target_id,
                pipeline_evidence_id=pipeline_id,
                pipeline_source_snapshot_id=pipeline_snapshot_id,
                persisted_evidence_id=str(
                    uuid5(NAMESPACE_URL, f"test-evidence:{pipeline_id}")
                ),
                persisted_source_snapshot_id=persisted_snapshots[pipeline_snapshot_id],
            )
        )
    return snapshots, tuple(evidence_bindings)
