from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.schemas.data_artifacts import (
    AlignmentStatus,
    DataArtifactBuildInput,
    DataArtifactAdmissionSnapshot,
    DatasetArtifactCandidate,
    LimitStatus,
    LimitValue,
    ManifestPins,
    RawSourceRecordReference,
    SourceCollectionArtifactCandidate,
    UncertaintyStatus,
    UncertaintyValue,
    compute_data_artifact_candidate_id,
    compute_data_artifact_canonical_content_hash,
    compute_data_artifact_content_hash,
    compute_data_artifact_input_hash,
    compute_data_artifact_lineage_hash,
    compute_data_artifact_output_hash,
    compute_raw_record_reference_registry_hash,
)
from app.schemas.manifest import NullReason
from app.workflow.publisher import PublicationAdmissionError, admit_artifact_candidate
from app.schemas.source_acquisition import RawDataSourceRecord, compute_raw_data_record_hash
from services.data_pipeline.crossmatch import align_cross_source_records
from services.data_pipeline.crossmatch.benchmark import (
    _scenario_input,
    load_crossmatch_benchmark,
)
from services.data_pipeline.data_artifacts import build_data_artifact_candidates
from services.data_pipeline.data_artifacts import build_data_artifact_candidates as package_entry
from services.data_pipeline.data_artifacts.pipeline import build_data_artifact_candidates as module_entry
from services.data_pipeline.data_artifacts.admission import (
    validate_data_artifact_candidates_against_input,
    validate_data_artifact_domain,
    validate_data_artifact_evidence,
    validate_data_artifact_quality_prerequisites,
)
from services.data_pipeline.data_artifacts.errors import DataArtifactError

from data_artifact_test_support import build_data_publication_bindings, build_input
from types import SimpleNamespace
from app.schemas.data_artifacts import (
    DataArtifactBuildResult,
    FieldDictionaryArtifactCandidate,
)


def _admit(candidate):
    bindings = {}
    if isinstance(candidate, DatasetArtifactCandidate):
        snapshots, evidence = build_data_publication_bindings(candidate)
        bindings = {
            "source_snapshot_bindings": snapshots,
            "evidence_bindings": evidence,
        }
    return admit_artifact_candidate(
        candidate,
        schema_version=candidate.schema_version,
        source_snapshot_ids=candidate.source_snapshot_ids,
        evidence_ids=candidate.evidence_ids,
        evidence_validator=validate_data_artifact_evidence,
        domain_validator=validate_data_artifact_domain,
        quality_validator=validate_data_artifact_quality_prerequisites,
        **bindings,
    )


def test_package_and_module_builder_are_one_import_order_independent_entrypoint() -> None:
    assert package_entry is module_entry


def _input_from_crossmatch(crossmatch_input, *requested_fields: str) -> DataArtifactBuildInput:
    crossmatch_result = align_cross_source_records(crossmatch_input)
    baseline = build_input(*requested_fields)
    pins = ManifestPins(
        case_manifest_id=crossmatch_result.case_manifest_id,
        case_manifest_version=crossmatch_result.case_manifest_version,
        case_manifest_content_hash=crossmatch_result.case_manifest_content_hash,
        field_manifest_id=crossmatch_result.field_manifest_id,
        field_manifest_version=crossmatch_result.field_manifest_version,
        field_manifest_content_hash=crossmatch_result.field_manifest_content_hash,
    )
    unhashed = DataArtifactBuildInput.model_construct(
        manifest_pins=pins,
        requested_fields=requested_fields,
        left_acquisition=crossmatch_input.left,
        right_acquisition=crossmatch_input.right,
        crossmatch_result=crossmatch_result,
        mapping_rule_set=baseline.mapping_rule_set,
        conversion_catalog=baseline.conversion_catalog,
        producer_version=baseline.producer_version,
        quality_constraints_reference=baseline.quality_constraints_reference,
        input_hash="sha256:" + "0" * 64,
    )
    payload = unhashed.model_dump(mode="json")
    payload["input_hash"] = compute_data_artifact_input_hash(unhashed)
    return DataArtifactBuildInput.model_validate(payload)


def _negative_zero_build_input(raw_value: float) -> DataArtifactBuildInput:
    benchmark = load_crossmatch_benchmark()
    scenario = next(
        item for item in benchmark.scenarios if item.scenario_id == "exact_one_to_one"
    )
    source_input = _scenario_input(scenario)

    def add_numeric_column(acquisition):
        records = []
        for record in acquisition.records:
            payload = {
                **record.payload,
                "pl_orbper": raw_value,
                "pl_orbperlim": 0,
            }
            records.append(
                RawDataSourceRecord(
                    source_id=record.source_id,
                    row_key=record.row_key,
                    payload=payload,
                    content_hash=compute_raw_data_record_hash(
                        source_id=record.source_id,
                        row_key=record.row_key,
                        payload=payload,
                    ),
                )
            )
        return acquisition.model_copy(update={"records": tuple(records)})

    mutated = source_input.model_copy(
        update={
            "left": add_numeric_column(source_input.left),
            "right": add_numeric_column(source_input.right),
        }
    )
    return _input_from_crossmatch(mutated, "planet.orbital_period")


def _rehash_candidate_payload(payload: dict) -> dict:
    if payload["kind"] == "dataset":
        payload["canonical_content_hash"] = (
            compute_data_artifact_canonical_content_hash(payload)
        )
        payload["lineage_hash"] = compute_data_artifact_lineage_hash(payload)
    payload["output_hash"] = compute_data_artifact_output_hash(payload)
    identity_hash = payload.get("canonical_content_hash", payload["output_hash"])
    payload["candidate_id"] = compute_data_artifact_candidate_id(
        payload["kind"], identity_hash
    )
    return payload


def _rehash_dataset_payload(payload: dict) -> dict:
    for collection in (
        "source_values",
        "transformation_evidence",
        "selections",
        "conflicts",
        "rows",
    ):
        for item in payload[collection]:
            item["content_hash"] = compute_data_artifact_content_hash(item)
    return _rehash_candidate_payload(payload)


def _replace_public_fields(original, replacement) -> None:
    for field_name in type(original).model_fields:
        object.__setattr__(original, field_name, getattr(replacement, field_name))


def test_public_build_rejects_self_consistent_non_frozen_entity_alignment_result() -> None:
    benchmark = load_crossmatch_benchmark()
    scenario = next(
        item for item in benchmark.scenarios if item.scenario_id == "exact_one_to_one"
    )
    baseline_input = _scenario_input(scenario)
    alternate_capacity = baseline_input.rule_set.capacity.model_copy(
        update={
            "max_candidate_pairs": baseline_input.rule_set.capacity.max_candidate_pairs
            - 1
        }
    )
    alternate_scenario = scenario.model_copy(
        update={"capacity_override": alternate_capacity}
    )
    input_value = _input_from_crossmatch(
        _scenario_input(alternate_scenario),
        "star.tic_id",
    )

    with pytest.raises(DataArtifactError) as exc_info:
        build_data_artifact_candidates(input_value)

    assert exc_info.value.code == "CROSSMATCH_RESULT_MISMATCH"


def test_publisher_replay_rejects_synchronized_dataset_semantic_tamper() -> None:
    result = build_data_artifact_candidates(
        build_input("planet.name", scenario_id="same_tic_host_only")
    )
    original = result.dataset
    payload = original.model_dump(mode="json")
    source_value = next(
        item
        for item in payload["source_values"]
        if item["canonical_field_id"] == "planet.name"
    )
    source_value_id = source_value["source_value_id"]
    forged_value = "Forged Planet c"
    source_value["raw_value"] = forged_value
    source_value["canonical_value"] = forged_value

    evidence = next(
        item
        for item in payload["transformation_evidence"]
        if item["source_value_id"] == source_value_id
    )
    evidence["raw_value"] = forged_value
    evidence["canonical_value"] = forged_value

    outcome_found = False
    for row in payload["rows"]:
        for outcome in row["fields"]:
            if source_value_id in outcome["candidate_source_value_ids"]:
                assert outcome["status"] == "mapped"
                outcome["canonical_value"] = forged_value
                outcome_found = True
    assert outcome_found

    damaged = DatasetArtifactCandidate.model_validate(
        _rehash_dataset_payload(payload)
    )
    _replace_public_fields(original, damaged)

    with pytest.raises(PublicationAdmissionError):
        _admit(original)


def test_publisher_replay_rejects_missing_unused_acquisition_record() -> None:
    result = build_data_artifact_candidates(
        build_input("planet.name", scenario_id="same_tic_host_only")
    )
    original = result.source_collection
    payload = original.model_dump(mode="json")
    left_member = payload["members"][0]
    assert left_member["raw_record_references"]

    dataset_record_keys = {
        (
            value.source_id,
            value.raw_record_row_key,
            value.raw_record_content_hash,
        )
        for value in result.dataset.source_values
    }
    removed = left_member["raw_record_references"][0]
    assert (
        removed["source_id"],
        tuple(tuple(item) for item in removed["row_key"]),
        removed["raw_record_content_hash"],
    ) not in dataset_record_keys

    left_member["raw_record_references"] = left_member["raw_record_references"][1:]
    references = tuple(
        RawSourceRecordReference.model_validate(item)
        for item in left_member["raw_record_references"]
    )
    left_member["raw_record_count"] = len(references)
    left_member["raw_record_reference_registry_hash"] = (
        compute_raw_record_reference_registry_hash(references)
    )
    damaged = SourceCollectionArtifactCandidate.model_validate(
        _rehash_candidate_payload(payload)
    )
    _replace_public_fields(original, damaged)

    with pytest.raises(PublicationAdmissionError):
        _admit(original)


def test_original_candidates_retain_immutable_replay_snapshot() -> None:
    result = build_data_artifact_candidates(build_input("star.tic_id"))

    for candidate in (result.dataset, result.field_dictionary, result.source_collection):
        context = getattr(candidate, "_artifact_publication_context", None)
        assert isinstance(context, DataArtifactAdmissionSnapshot)
        assert context.input_hash == candidate.input_hash
        assert not isinstance(context, DataArtifactBuildInput)
    with pytest.raises(
        PublicationAdmissionError,
        match="Data Quality Evaluation attestation",
    ):
        _admit(result.dataset)


def test_reparsed_candidate_still_cannot_recreate_replay_context() -> None:
    candidate = build_data_artifact_candidates(build_input("star.tic_id")).dataset
    reparsed = DatasetArtifactCandidate.model_validate_json(candidate.model_dump_json())

    assert getattr(reparsed, "_artifact_publication_context", None) is None
    with pytest.raises(PublicationAdmissionError, match="cannot bypass"):
        _admit(reparsed)


def test_six_public_data_artifact_models_round_trip_without_publication_authority() -> None:
    input_value = build_input("star.tic_id")
    result = build_data_artifact_candidates(input_value)
    public_models = (
        input_value,
        result.dataset,
        result.field_dictionary,
        result.source_collection,
        input_value.mapping_rule_set,
        input_value.conversion_catalog,
    )

    reparsed = tuple(
        type(value).model_validate_json(value.model_dump_json())
        for value in public_models
    )
    assert reparsed == public_models
    for candidate in reparsed[1:4]:
        validate_data_artifact_candidates_against_input(candidate, reparsed[0])
        assert getattr(candidate, "_artifact_publication_context", None) is None
        assert not candidate.__artifact_publication_is_admitted__()


@pytest.mark.parametrize("candidate_name", ["dataset", "field_dictionary", "source_collection"])
@pytest.mark.parametrize("mutation", ["context", "payload", "payload_context", "seal"])
def test_publisher_rejects_cross_build_candidate_transplant(candidate_name, mutation) -> None:
    first = build_data_artifact_candidates(build_input("star.tic_id"))
    second = build_data_artifact_candidates(build_input("planet.name"))
    original = getattr(first, candidate_name)
    replacement = getattr(second, candidate_name)
    if mutation in {"payload", "payload_context"}:
        _replace_public_fields(original, replacement)
    if mutation in {"context", "payload_context"}:
        object.__setattr__(
            original,
            "_artifact_publication_context",
            getattr(replacement, "_artifact_publication_context"),
        )
    if mutation == "seal":
        object.__setattr__(
            original,
            "_artifact_publication_seal",
            getattr(replacement, "_artifact_publication_seal"),
        )
    with pytest.raises(PublicationAdmissionError, match="admission|bypass"):
        _admit(original)


def test_publisher_rejects_copy_and_deepcopy_without_publication_identity() -> None:
    candidate = build_data_artifact_candidates(build_input("star.tic_id")).dataset
    for copied in (candidate.model_copy(deep=True), deepcopy(candidate)):
        with pytest.raises(PublicationAdmissionError, match="cannot bypass"):
            _admit(copied)


def test_public_builder_revalidates_constructed_and_corrupted_input() -> None:
    source = build_input("star.tic_id")
    forged = DataArtifactBuildInput.model_construct(
        **{
            field_name: getattr(source, field_name)
            for field_name in DataArtifactBuildInput.model_fields
        }
    )
    object.__setattr__(forged, "input_hash", "sha256:" + "0" * 64)
    with pytest.raises(DataArtifactError) as forged_error:
        build_data_artifact_candidates(forged)
    assert forged_error.value.code == "INPUT_HASH_MISMATCH"

    corrupted = source.model_copy()
    object.__setattr__(corrupted, "requested_fields", ("planet.name",))
    with pytest.raises(DataArtifactError) as corrupted_error:
        build_data_artifact_candidates(corrupted)
    assert corrupted_error.value.code == "INPUT_HASH_MISMATCH"


def _install_broken_assembler(monkeypatch, mutate) -> None:
    import services.data_pipeline.data_artifacts.pipeline as pipeline

    original = pipeline._assemble_data_artifact_candidates

    def broken_assembler(projection):
        result = original(projection)
        mutate(result)
        return result

    monkeypatch.setattr(pipeline, "_assemble_data_artifact_candidates", broken_assembler)


def test_projection_admission_rejects_producer_omitted_source_value(monkeypatch) -> None:
    def mutate(result):
        object.__setattr__(result.dataset, "source_values", result.dataset.source_values[1:])

    _install_broken_assembler(monkeypatch, mutate)
    with pytest.raises(ValueError, match="SourceValue set.*complete domain projection"):
        build_data_artifact_candidates(
            build_input("star.tic_id", scenario_id="same_tic_host_only")
        )


def test_projection_admission_rejects_wrong_winner(monkeypatch) -> None:
    def mutate(result):
        outcome = next(
            outcome
            for row in result.dataset.rows
            for outcome in row.fields
            if outcome.status == "mapped" and len(outcome.candidate_source_value_ids) > 1
        )
        object.__setattr__(
            outcome,
            "selected_source_value_id",
            outcome.candidate_source_value_ids[-1],
        )

    _install_broken_assembler(monkeypatch, mutate)
    with pytest.raises(ValueError, match="Dataset rows.*complete domain projection"):
        build_data_artifact_candidates(
            build_input("star.tic_id", scenario_id="same_tic_host_only")
        )


def test_projection_admission_rejects_wrong_declared_null_reason(monkeypatch) -> None:
    def mutate(result):
        outcome = next(
            outcome
            for row in result.dataset.rows
            for outcome in row.fields
            if outcome.status == "declared_null"
        )
        object.__setattr__(outcome, "reason", NullReason.not_measured)

    _install_broken_assembler(monkeypatch, mutate)
    with pytest.raises(ValueError, match="Dataset rows.*complete domain projection"):
        build_data_artifact_candidates(
            build_input("planet.radius", scenario_id="exact_one_to_one")
        )


def test_projection_admission_rejects_uncertainty_and_limit_drift(monkeypatch) -> None:
    def mutate(result):
        value = result.dataset.source_values[0]
        object.__setattr__(
            value,
            "uncertainty",
            UncertaintyValue(status=UncertaintyStatus.not_applicable),
        )
        object.__setattr__(
            value,
            "limit",
            LimitValue(
                status=LimitStatus.upper_limit,
                raw_flag=1,
                locator=value.limit.locator,
            ),
        )

    _install_broken_assembler(monkeypatch, mutate)
    with pytest.raises(ValueError, match="SourceValue set.*complete domain projection"):
        build_data_artifact_candidates(_negative_zero_build_input(0.0))


def test_projection_admission_rejects_row_alignment_drift(monkeypatch) -> None:
    def mutate(result):
        row = result.dataset.rows[0]
        replacement = (
            AlignmentStatus.rejected
            if row.alignment_status is not AlignmentStatus.rejected
            else AlignmentStatus.accepted
        )
        object.__setattr__(row, "alignment_status", replacement)

    _install_broken_assembler(monkeypatch, mutate)
    with pytest.raises(ValueError, match="Dataset rows.*complete domain projection"):
        build_data_artifact_candidates(build_input("star.tic_id"))


def test_projection_admission_rejects_hidden_conflict(monkeypatch) -> None:
    def mutate(result):
        assert result.dataset.conflicts
        object.__setattr__(result.dataset, "conflicts", ())

    _install_broken_assembler(monkeypatch, mutate)
    with pytest.raises(ValueError, match="Dataset conflict set.*complete domain projection"):
        build_data_artifact_candidates(
            build_input("planet.name", scenario_id="alias_conflict")
        )


def test_dataset_candidate_id_rejects_noncanonical_output_hash_identity() -> None:
    candidate = build_data_artifact_candidates(build_input("star.tic_id")).dataset
    payload = candidate.model_dump(mode="json")
    payload["candidate_id"] = compute_data_artifact_candidate_id(
        payload["kind"], payload["output_hash"]
    )

    with pytest.raises(ValidationError, match="candidate_id.*canonical identity"):
        DatasetArtifactCandidate.model_validate(payload)


def test_dataset_hashes_separate_scientific_semantics_from_raw_lineage() -> None:
    candidate = build_data_artifact_candidates(_negative_zero_build_input(0.0)).dataset
    baseline = candidate.model_dump(mode="json")
    raw_drift = deepcopy(baseline)
    raw_drift["source_values"][0]["raw_value"] = -0.0
    raw_drift["source_values"][0]["raw_record_content_hash"] = "sha256:" + "1" * 64
    raw_drift["rows"][0]["row_id"] = "dataset_row.lineage-drift"
    raw_drift["rows"][0]["crossmatch_logical_key"] = "sha256:" + "2" * 64
    raw_drift["rows"][0]["source_member_ids"] = ["candidate.lineage-drift"]
    raw_drift["rows"][0]["source_snapshot_ids"] = ["snapshot.lineage-drift"]

    assert compute_data_artifact_canonical_content_hash(raw_drift) == (
        candidate.canonical_content_hash
    )
    assert compute_data_artifact_lineage_hash(raw_drift) != candidate.lineage_hash

    scientific_variants = []
    entity_identity = deepcopy(baseline)
    entity_identity["rows"][0]["canonical_row_identity"]["member_entities"][0][
        "identity_values"
    ][0]["normalized_value"] = "different normalized entity"
    scientific_variants.append(entity_identity)

    canonical_value = deepcopy(baseline)
    canonical_value["source_values"][0]["canonical_value"] = "1"
    scientific_variants.append(canonical_value)

    uncertainty = deepcopy(baseline)
    uncertainty["source_values"][0]["uncertainty"].update(
        {
            "status": "complete",
            "canonical_positive": "1",
            "canonical_negative": "2",
        }
    )
    scientific_variants.append(uncertainty)

    limit = deepcopy(baseline)
    limit["source_values"][0]["limit"]["status"] = "upper_limit"
    scientific_variants.append(limit)

    removed_candidate = deepcopy(baseline)
    outcome = next(
        outcome
        for row in removed_candidate["rows"]
        for outcome in row["fields"]
        if outcome["candidate_source_value_ids"]
    )
    outcome["candidate_source_value_ids"] = []
    scientific_variants.append(removed_candidate)

    assert all(
        compute_data_artifact_canonical_content_hash(payload)
        != candidate.canonical_content_hash
        for payload in scientific_variants
    )


def test_dataset_model_strictly_recomputes_lineage_hash() -> None:
    candidate = build_data_artifact_candidates(
        build_input("planet.name", scenario_id="same_tic_host_only")
    ).dataset
    payload = candidate.model_dump(mode="json")
    source_value = payload["source_values"][0]
    source_value["raw_value"] = "raw-lineage-drift"
    source_value["content_hash"] = compute_data_artifact_content_hash(source_value)
    evidence = next(
        item
        for item in payload["transformation_evidence"]
        if item["source_value_id"] == source_value["source_value_id"]
    )
    evidence["raw_value"] = "raw-lineage-drift"
    evidence["content_hash"] = compute_data_artifact_content_hash(evidence)

    with pytest.raises(ValidationError, match="lineage_hash.*complete raw/input lineage"):
        DatasetArtifactCandidate.model_validate(payload)


def test_canonical_hash_covers_selection_null_and_conflict_semantics() -> None:
    selected = build_data_artifact_candidates(
        build_input("star.tic_id", scenario_id="same_tic_host_only")
    ).dataset
    selected_payload = selected.model_dump(mode="json")
    mapped = next(
        outcome
        for row in selected_payload["rows"]
        for outcome in row["fields"]
        if outcome["status"] == "mapped"
        and len(outcome["candidate_source_value_ids"]) > 1
    )
    mapped["selected_source_value_id"] = mapped["candidate_source_value_ids"][-1]
    assert compute_data_artifact_canonical_content_hash(selected_payload) != (
        selected.canonical_content_hash
    )

    declared_null = build_data_artifact_candidates(
        build_input("planet.radius", scenario_id="exact_one_to_one")
    ).dataset
    null_payload = declared_null.model_dump(mode="json")
    null_outcome = next(
        outcome
        for row in null_payload["rows"]
        for outcome in row["fields"]
        if outcome["status"] == "declared_null"
    )
    null_outcome["reason"] = "not_measured"
    assert compute_data_artifact_canonical_content_hash(null_payload) != (
        declared_null.canonical_content_hash
    )

    conflicted = build_data_artifact_candidates(
        build_input("planet.name", scenario_id="alias_conflict")
    ).dataset
    conflict_payload = conflicted.model_dump(mode="json")
    conflict_outcome = next(
        outcome
        for row in conflict_payload["rows"]
        for outcome in row["fields"]
        if outcome.get("conflict_ids")
    )
    conflict_outcome["conflict_ids"] = []
    assert compute_data_artifact_canonical_content_hash(conflict_payload) != (
        conflicted.canonical_content_hash
    )


def test_negative_zero_preserves_raw_provenance_but_not_canonical_dataset_identity() -> None:
    positive = build_data_artifact_candidates(_negative_zero_build_input(0.0))
    negative = build_data_artifact_candidates(_negative_zero_build_input(-0.0))

    assert {
        value.canonical_value for value in positive.dataset.source_values
    } == {"0"}
    assert {
        value.canonical_value for value in negative.dataset.source_values
    } == {"0"}
    assert positive.dataset.canonical_content_hash == negative.dataset.canonical_content_hash
    assert positive.dataset.candidate_id == negative.dataset.candidate_id
    assert tuple(
        row.canonical_row_identity for row in positive.dataset.rows
    ) == tuple(row.canonical_row_identity for row in negative.dataset.rows)
    assert positive.dataset.lineage_hash != negative.dataset.lineage_hash
    assert positive.dataset.output_hash != negative.dataset.output_hash
    assert positive.source_collection.output_hash != negative.source_collection.output_hash
    assert positive.input_hash != negative.input_hash



# --- durable data-artifact semantics moved from the removed review-history suite ---
def _rehash_candidate_payload(payload: dict) -> dict:
    if payload["kind"] == "dataset":
        payload["canonical_content_hash"] = (
            compute_data_artifact_canonical_content_hash(payload)
        )
        payload["lineage_hash"] = compute_data_artifact_lineage_hash(payload)
    payload["output_hash"] = compute_data_artifact_output_hash(payload)
    identity_hash = payload.get("canonical_content_hash", payload["output_hash"])
    payload["candidate_id"] = compute_data_artifact_candidate_id(
        payload["kind"], identity_hash
    )
    return payload


def _refresh_raw_record_registry(member: dict) -> None:
    references = tuple(
        RawSourceRecordReference.model_validate(item)
        for item in member["raw_record_references"]
    )
    member["raw_record_count"] = len(references)
    member["raw_record_reference_registry_hash"] = (
        compute_raw_record_reference_registry_hash(references)
    )


def _rehash_dataset_tree(payload: dict) -> dict:
    for collection in (
        "source_values",
        "transformation_evidence",
        "selections",
        "conflicts",
        "rows",
    ):
        for item in payload[collection]:
            item["content_hash"] = compute_data_artifact_content_hash(item)
    return _rehash_candidate_payload(payload)


def test_dataset_rejects_orphan_source_value_after_synchronized_rehash() -> None:
    candidate = build_data_artifact_candidates(build_input("star.tic_id")).dataset
    payload = candidate.model_dump(mode="json")
    orphan = deepcopy(payload["source_values"][0])
    orphan["source_value_id"] = "source_value.orphan"
    orphan["content_hash"] = compute_data_artifact_content_hash(orphan)
    payload["source_values"].append(orphan)
    _rehash_candidate_payload(payload)

    with pytest.raises(ValidationError, match="source value registry|orphan"):
        DatasetArtifactCandidate.model_validate(payload)


def test_dataset_rejects_evidence_value_drift_after_synchronized_rehash() -> None:
    candidate = build_data_artifact_candidates(build_input("star.tic_id")).dataset
    payload = candidate.model_dump(mode="json")
    payload["transformation_evidence"][0]["raw_value"] = "forged"
    payload["transformation_evidence"][0]["content_hash"] = (
        compute_data_artifact_content_hash(payload["transformation_evidence"][0])
    )
    _rehash_candidate_payload(payload)

    with pytest.raises(ValidationError, match="Evidence.*source value|raw value"):
        DatasetArtifactCandidate.model_validate(payload)


def test_build_result_rejects_cross_candidate_producer_drift() -> None:
    result = build_data_artifact_candidates(build_input("star.tic_id"))
    dictionary_payload = result.field_dictionary.model_dump(mode="json")
    dictionary_payload["producer"]["producer_version"] = "9.9.9"
    _rehash_candidate_payload(dictionary_payload)
    dictionary = FieldDictionaryArtifactCandidate.model_validate(dictionary_payload)
    payload = result.model_dump(mode="json")
    payload["field_dictionary"] = dictionary.model_dump(mode="json")
    payload["output_hash"] = compute_data_artifact_output_hash(payload)

    with pytest.raises(ValidationError, match="producer|candidate.*common"):
        DataArtifactBuildResult.model_validate(payload)


def test_source_collection_json_reparse_preserves_member_bindings() -> None:
    candidate = build_data_artifact_candidates(
        build_input("star.tic_id", scenario_id="truncated_inconclusive")
    ).source_collection

    reparsed = SourceCollectionArtifactCandidate.model_validate_json(
        candidate.model_dump_json()
    )

    assert reparsed.members == candidate.members
    assert reparsed.members[0].completion != reparsed.members[1].completion


def test_source_collection_rejects_license_source_mismatch() -> None:
    candidate = build_data_artifact_candidates(build_input("star.tic_id")).source_collection
    payload = candidate.model_dump(mode="json")
    payload["members"][0]["license_note"] = "forged license binding"
    _rehash_candidate_payload(payload)

    with pytest.raises(ValidationError, match="SourceSnapshot"):
        SourceCollectionArtifactCandidate.model_validate(payload)


def test_dataset_rejects_orphan_evidence_after_synchronized_rehash() -> None:
    candidate = build_data_artifact_candidates(build_input("star.tic_id")).dataset
    payload = candidate.model_dump(mode="json")
    orphan = deepcopy(payload["transformation_evidence"][0])
    orphan["evidence_id"] = "evidence.transformation.orphan"
    payload["transformation_evidence"].append(orphan)
    _rehash_dataset_tree(payload)

    with pytest.raises(ValidationError, match="Evidence references|Evidence registry"):
        DatasetArtifactCandidate.model_validate(payload)


def test_dataset_rejects_conflict_field_and_candidate_set_drift() -> None:
    candidate = build_data_artifact_candidates(
        build_input("system.right_ascension", scenario_id="manual_decision_valid")
    ).dataset
    for mutation in ("field", "candidate_set"):
        payload = candidate.model_dump(mode="json")
        conflict = payload["conflicts"][0]
        if mutation == "field":
            conflict["canonical_field_id"] = "star.tic_id"
        else:
            conflict["source_value_ids"] = conflict["source_value_ids"][:-1]
        _rehash_dataset_tree(payload)

        with pytest.raises(ValidationError, match="conflict"):
            DatasetArtifactCandidate.model_validate(payload)


def test_build_result_rejects_dataset_dictionary_projection_drift() -> None:
    result = build_data_artifact_candidates(build_input("star.tic_id"))
    payload = result.dataset.model_dump(mode="json")
    payload["columns"][0]["field"]["label_en"] = "Forged label"
    dataset = DatasetArtifactCandidate.model_validate(_rehash_dataset_tree(payload))
    build_payload = result.model_dump(mode="json")
    build_payload["dataset"] = dataset.model_dump(mode="json")
    build_payload["output_hash"] = compute_data_artifact_output_hash(build_payload)

    with pytest.raises(ValidationError, match="FieldDictionary definitions"):
        DataArtifactBuildResult.model_validate(build_payload)


def test_dataset_rejects_synchronized_missing_snapshot() -> None:
    result = build_data_artifact_candidates(build_input("star.tic_id"))
    payload = result.dataset.model_dump(mode="json")
    payload["source_snapshot_ids"] = payload["source_snapshot_ids"][:1]
    payload["crossmatch_source_snapshot_ids"] = payload[
        "crossmatch_source_snapshot_ids"
    ][:1]

    with pytest.raises(ValidationError, match="two crossmatch SourceSnapshots"):
        DatasetArtifactCandidate.model_validate(_rehash_dataset_tree(payload))


def test_source_collection_rejects_missing_or_duplicate_member() -> None:
    candidate = build_data_artifact_candidates(build_input("star.tic_id")).source_collection
    for members in (
        candidate.members[:1],
        (candidate.members[0], candidate.members[0]),
    ):
        payload = candidate.model_dump(mode="json")
        payload["members"] = [item.model_dump(mode="json") for item in members]
        payload["source_snapshot_ids"] = sorted(
            {item.source_snapshot_id for item in members}
        )
        _rehash_candidate_payload(payload)
        with pytest.raises(ValidationError, match="left/right|independent"):
            SourceCollectionArtifactCandidate.model_validate(payload)


def test_build_result_rejects_candidate_from_another_build() -> None:
    first = build_data_artifact_candidates(build_input("star.tic_id"))
    second = build_data_artifact_candidates(build_input("planet.name"))
    payload = first.model_dump(mode="json")
    payload["field_dictionary"] = second.field_dictionary.model_dump(mode="json")
    payload["output_hash"] = compute_data_artifact_output_hash(payload)

    with pytest.raises(ValidationError, match="common bindings|requested fields"):
        DataArtifactBuildResult.model_validate(payload)


def test_build_result_json_reparse_cannot_recreate_bundle_seals() -> None:
    result = build_data_artifact_candidates(build_input("star.tic_id"))

    reparsed = DataArtifactBuildResult.model_validate(result.model_dump(mode="json"))
    assert reparsed.dataset.__artifact_publication_is_admitted__() is False
    assert reparsed.field_dictionary.__artifact_publication_is_admitted__() is False
    assert reparsed.source_collection.__artifact_publication_is_admitted__() is False


def test_build_result_rejects_source_collection_missing_used_raw_record() -> None:
    result = build_data_artifact_candidates(build_input("star.tic_id"))
    collection_payload = result.source_collection.model_dump(mode="json")
    collection_payload["members"][0]["raw_record_references"] = []
    _refresh_raw_record_registry(collection_payload["members"][0])
    collection = SourceCollectionArtifactCandidate.model_validate(
        _rehash_candidate_payload(collection_payload)
    )
    payload = result.model_dump(mode="json")
    payload["source_collection"] = collection.model_dump(mode="json")
    payload["output_hash"] = compute_data_artifact_output_hash(payload)

    with pytest.raises(ValidationError, match="raw records"):
        DataArtifactBuildResult.model_validate(payload)


def test_dataset_rejects_orphan_and_missing_conflict_references() -> None:
    candidate = build_data_artifact_candidates(
        build_input("system.right_ascension", scenario_id="manual_decision_valid")
    ).dataset

    orphan_payload = candidate.model_dump(mode="json")
    orphan = deepcopy(orphan_payload["conflicts"][0])
    orphan["conflict_id"] = "conflict.field.orphan"
    orphan_payload["conflicts"].append(orphan)
    _rehash_dataset_tree(orphan_payload)
    with pytest.raises(ValidationError, match="conflict registry.*orphan"):
        DatasetArtifactCandidate.model_validate(orphan_payload)

    missing_payload = candidate.model_dump(mode="json")
    row = next(item for item in missing_payload["rows"] if item["conflict_ids"])
    row["conflict_ids"] = []
    conflicted_outcome = next(item for item in row["fields"] if item.get("conflict_ids"))
    conflicted_outcome["conflict_ids"] = []
    _rehash_dataset_tree(missing_payload)
    with pytest.raises(ValidationError, match="selection status|conflict registry"):
        DatasetArtifactCandidate.model_validate(missing_payload)


def test_publisher_validators_independently_revalidate_damaged_candidate() -> None:
    candidate = build_data_artifact_candidates(build_input("star.tic_id")).dataset
    payload = candidate.model_dump(mode="json")
    payload["transformation_evidence"][0]["raw_value"] = "forged"
    payload["transformation_evidence"][0]["content_hash"] = (
        compute_data_artifact_content_hash(payload["transformation_evidence"][0])
    )
    _rehash_candidate_payload(payload)
    damaged_evidence = candidate.transformation_evidence[0].model_copy(
        update={
            "raw_value": "forged",
            "content_hash": payload["transformation_evidence"][0]["content_hash"],
        }
    )
    damaged = candidate.model_copy(
        update={
            "transformation_evidence": (
                damaged_evidence,
                *candidate.transformation_evidence[1:],
            ),
            "output_hash": payload["output_hash"],
            "candidate_id": payload["candidate_id"],
        }
    )
    context = SimpleNamespace(
        candidate=damaged,
        source_snapshot_ids=tuple(payload["source_snapshot_ids"]),
        evidence_ids=tuple(payload["evidence_ids"]),
    )

    with pytest.raises(
        ValueError, match="Dataset Evidence set.*complete domain projection"
    ):
        validate_data_artifact_evidence(context)
    with pytest.raises(
        ValueError, match="Dataset Evidence set.*complete domain projection"
    ):
        validate_data_artifact_domain(context)
