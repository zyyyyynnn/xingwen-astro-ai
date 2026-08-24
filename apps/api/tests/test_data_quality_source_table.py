from __future__ import annotations

import pytest

from app.schemas.data_artifacts import (
    DataArtifactBuildInput,
    SourceTableDataArtifactAuthority,
    compute_data_artifact_input_hash,
)
from app.schemas.data_quality import (
    DataQualityEvaluationInput,
    DataQualityEvaluationRejected,
    DataQualityEvaluationResult,
    QualityErrorCode,
    QualityMetricStatus,
    compute_data_quality_input_hash,
)
from app.schemas.evidence import SourceSnapshotRecord
from app.workflow.publisher import admit_artifact_candidate
from services.scientific_skills.astro_acquisition import GAIA_CACHE_VERSION
from services.data_pipeline.data_artifacts import build_data_artifact_candidates
from services.data_pipeline.data_artifacts.admission import (
    validate_data_artifact_domain,
    validate_data_artifact_evidence,
)
from services.data_pipeline.data_quality.admission import (
    admit_data_artifact_quality,
    build_data_quality_publication_validator,
)
from services.data_pipeline.data_artifacts.policy import (
    load_mapping_rule_set,
    load_unit_conversion_catalog,
)
from services.data_pipeline.data_quality import evaluate_data_quality
from services.data_pipeline.data_quality.policy import load_frozen_quality_rule_set

from data_artifact_test_support import build_data_publication_bindings
from test_source_table_admission import RETRIEVED_AT, _admit, _contract


def _source_table_data_input(
    admission=None,
    *,
    requested_fields=None,
) -> DataArtifactBuildInput:
    admission = admission or _admit(requested_fields=requested_fields)
    mapping_rule_set = load_mapping_rule_set()
    conversion_catalog = load_unit_conversion_catalog()
    snapshot = SourceSnapshotRecord(
        snapshot_id=admission.source_snapshot_id,
        source_id=admission.source_id,
        source_type="gaia_tap",
        retrieved_at=admission.retrieved_at,
        query="SELECT source_id,ra,dec,teff_gspphot FROM gaiadr3.gaia_source",
        query_hash=admission.query_hash,
        source_version_or_etag=None,
        content_hash=admission.source_snapshot_content_hash,
        license_note="ESA Gaia archive data",
        cache_version=GAIA_CACHE_VERSION,
        request_metadata={"mode": "fixture"},
    )
    authority = SourceTableDataArtifactAuthority(
        source_snapshot=snapshot,
        source_table_admission=admission,
    )
    unhashed = DataArtifactBuildInput.model_construct(
        manifest_pins=admission.manifest_pins,
        requested_fields=tuple(
            requested_fields
            or (column.canonical_field_id for column in admission.columns)
        ),
        authority=authority,
        mapping_rule_set=mapping_rule_set,
        conversion_catalog=conversion_catalog,
        producer_version=mapping_rule_set.producer_version,
        quality_constraints_reference="research_contract.quality_constraints.gaia",
        input_hash="sha256:" + "0" * 64,
    )
    return DataArtifactBuildInput.model_validate(
        {
            **unhashed.model_dump(mode="json"),
            "input_hash": compute_data_artifact_input_hash(unhashed),
        }
    )


def _quality_input(
    data_input: DataArtifactBuildInput,
    build_result=None,
    *,
    contract=None,
) -> DataQualityEvaluationInput:
    build_result = build_result or build_data_artifact_candidates(data_input)
    rules = load_frozen_quality_rule_set()
    contract = contract or _contract()
    unhashed = DataQualityEvaluationInput.model_construct(
        data_artifact_input=data_input,
        dataset_candidate=build_result.dataset,
        field_dictionary_candidate=build_result.field_dictionary,
        source_collection_candidate=build_result.source_collection,
        research_contract=contract,
        quality_rule_set=rules,
        input_hash="sha256:" + "0" * 64,
    )
    return DataQualityEvaluationInput.model_validate(
        {
            "data_artifact_input": data_input,
            "dataset_candidate": build_result.dataset,
            "field_dictionary_candidate": build_result.field_dictionary,
            "source_collection_candidate": build_result.source_collection,
            "research_contract": contract,
            "quality_rule_set": rules,
            "input_hash": compute_data_quality_input_hash(unhashed),
        }
    )


def test_source_table_enters_quality_without_constructing_crossmatch_result() -> None:
    quality_input = _quality_input(_source_table_data_input())

    result = evaluate_data_quality(quality_input)

    assert isinstance(result, DataQualityEvaluationResult)
    assert result.input_references.authority.authority_kind == "source_table"
    assert result.contract_gate.overall_status.value == "pass"
    assert result.dataset_result.completeness.value == 1
    assert result.dataset_result.evidence_coverage.value == 1
    assert (
        result.dataset_result.object_match_coverage.status
        is QualityMetricStatus.not_applicable
    )
    assert all(
        item.authority.authority_kind == "source_table" for item in result.row_results
    )


def test_source_table_projects_requested_fields_from_an_acquisition_superset() -> None:
    requested_fields = ("system.right_ascension",)
    data_input = _source_table_data_input(requested_fields=requested_fields)
    build_result = build_data_artifact_candidates(data_input)

    assert build_result.dataset.requested_fields == requested_fields
    assert (
        tuple(column.field.field_id for column in build_result.dataset.columns)
        == requested_fields
    )
    assert build_result.field_dictionary.requested_fields == requested_fields
    assert build_result.dataset.rows[0].projected_field_ids == requested_fields
    assert build_result.dataset.rows[
        0
    ].row_authority.canonical_row_identity.canonical_identity.startswith("Gaia DR3 ")
    assert "star.gaia_dr3_id" not in build_result.dataset.requested_fields
    assert len(build_result.dataset.evidence_ids) == 1
    assert (
        len(
            build_result.source_collection.source_table_sources[0].raw_record_references
        )
        == 1
    )

    quality_result = evaluate_data_quality(
        _quality_input(
            data_input,
            build_result,
            contract=_contract(requested_fields=requested_fields),
        )
    )
    assert isinstance(quality_result, DataQualityEvaluationResult)
    assert quality_result.dataset_result.field_count == 1
    assert quality_result.dataset_result.applicable_cell_count == 1
    assert quality_result.dataset_result.evidence_coverage.value == 1

    for candidate in (
        build_result.dataset,
        build_result.field_dictionary,
        build_result.source_collection,
    ):
        assert "source_table_admission" not in candidate.authority.model_dump(
            mode="json"
        )
    assert (
        "source_table_admission"
        not in build_result.source_collection.source_table_sources[0].model_dump(
            mode="json"
        )
    )


def test_source_table_scientific_identity_excludes_retrieval_lineage() -> None:
    first = build_data_artifact_candidates(_source_table_data_input(_admit()))
    second = build_data_artifact_candidates(
        _source_table_data_input(
            _admit(
                source_snapshot_id="00000000-0000-0000-0000-000000000222",
                source_snapshot_content_hash="sha256:" + "c" * 64,
                query_hash="sha256:" + "d" * 64,
                retrieved_at=RETRIEVED_AT.replace(second=4),
                evidence_scope_id="request.gaia.retried",
            )
        )
    )

    assert first.dataset.canonical_content_hash == second.dataset.canonical_content_hash
    assert first.dataset.candidate_id == second.dataset.candidate_id
    assert first.dataset.lineage_hash != second.dataset.lineage_hash
    assert first.dataset.authority.admission_id != second.dataset.authority.admission_id
    assert first.dataset.source_snapshot_ids != second.dataset.source_snapshot_ids


def test_source_table_quality_rejects_admission_transplant_to_another_contract() -> (
    None
):
    data_input = _source_table_data_input()
    build_result = build_data_artifact_candidates(data_input)
    quality_input = _quality_input(
        data_input,
        build_result,
        contract=_contract(contract_id="contract.gaia.other"),
    )

    result = evaluate_data_quality(quality_input)

    assert isinstance(result, DataQualityEvaluationRejected)
    assert result.error_code is QualityErrorCode.QUALITY_RESEARCH_CONTRACT_MISMATCH


def test_source_table_quality_rejects_incomplete_admission_before_evaluation() -> None:
    with pytest.raises(ValueError, match="complete source"):
        _source_table_data_input(_admit(result_status="truncated"))


def test_source_table_candidates_close_existing_quality_and_publisher_admission() -> (
    None
):
    data_input = _source_table_data_input()
    build_result = build_data_artifact_candidates(data_input)
    quality_input = _quality_input(data_input, build_result)
    quality_result = evaluate_data_quality(quality_input)
    assert isinstance(quality_result, DataQualityEvaluationResult)
    quality_admission = admit_data_artifact_quality(
        build_result=build_result,
        evaluation_input=quality_input,
        evaluation_result=quality_result,
    )
    candidates = (
        build_result.dataset,
        build_result.field_dictionary,
        build_result.source_collection,
    )
    assert all(
        candidate.authority.authority_kind == "source_table" for candidate in candidates
    )
    assert build_result.dataset.rows[0].row_authority.authority_kind == "source_table"
    assert build_result.field_dictionary.field_definitions
    source_member = build_result.source_collection.source_table_sources[0]
    assert source_member.member_kind == "source_table"
    assert source_member.admission_id == build_result.dataset.authority.admission_id
    assert source_member.source_table == build_result.dataset.authority.source_table
    assert (
        source_member.admission_output_hash
        == build_result.dataset.authority.admission_output_hash
    )
    assert all(
        reference.source_id == build_result.dataset.authority.source_id
        for reference in source_member.raw_record_references
    )

    snapshots, evidence = build_data_publication_bindings(build_result.dataset)
    admitted = []
    for candidate in candidates:
        published = admit_artifact_candidate(
            candidate,
            schema_version=candidate.schema_version,
            source_snapshot_ids=candidate.source_snapshot_ids,
            evidence_ids=candidate.evidence_ids,
            evidence_validator=validate_data_artifact_evidence,
            domain_validator=validate_data_artifact_domain,
            quality_validator=build_data_quality_publication_validator(
                quality_admission,
                candidate_kind=candidate.kind,
            ),
            source_snapshot_bindings=snapshots,
            evidence_bindings=evidence,
            data_provenance_candidate=build_result.dataset,
        )
        admitted.append(published)

    assert [item.content["kind"] for item in admitted] == [
        "dataset",
        "field_dictionary",
        "source_collection",
    ]
    assert [item.content["candidate_id"] for item in admitted] == [
        candidate.candidate_id for candidate in candidates
    ]
