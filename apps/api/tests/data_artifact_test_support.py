from __future__ import annotations

from app.schemas.data_artifacts import (
    DataArtifactBuildInput,
    ManifestPins,
    compute_data_artifact_input_hash,
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
    scenario = next(item for item in benchmark.scenarios if item.scenario_id == scenario_id)
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
