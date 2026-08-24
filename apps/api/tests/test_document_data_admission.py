from __future__ import annotations

from datetime import UTC, datetime
from importlib import import_module
from uuid import NAMESPACE_URL, uuid5

import pytest
from pydantic import ValidationError

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.core import DataRequirements
from app.schemas.core import ResearchContract, compute_research_contract_content_hash
from app.schemas.data_artifacts import (
    DataArtifactBuildInput,
    compute_data_artifact_input_hash,
)
from app.schemas.evidence import SourceSnapshotRecord
from app.schemas.research_input import ResearchInputRef
from app.schemas.scientific_document import (
    DocumentLocator,
    DocumentParseQuality,
    ScientificDataExtractionCandidate,
)
from services.data_pipeline.manifest import load_frozen_manifest_bundle
from services.data_pipeline.data_artifacts import build_data_artifact_candidates
from data_artifact_test_support import build_input


def load_case_manifest():
    return load_frozen_manifest_bundle().case_manifest


def load_field_manifest():
    return load_frozen_manifest_bundle().field_manifest


def _uuid(name: str) -> str:
    return str(uuid5(NAMESPACE_URL, name))


def _hash(seed: str) -> str:
    import hashlib

    return f"sha256:{hashlib.sha256(seed.encode()).hexdigest()}"


def _admission_api():
    try:
        return import_module("services.data_pipeline.document_admission")
    except ModuleNotFoundError:
        pytest.fail("document admission boundary is missing")


def _candidate(
    raw_value: str | None,
    *,
    raw_unit: str | None = "K",
    raw_text: str | None = None,
    field_hint: str = "T_eff",
    quality: DocumentParseQuality = DocumentParseQuality.accepted,
    candidate_id: str = "document.candidate.teff",
) -> ScientificDataExtractionCandidate:
    return ScientificDataExtractionCandidate(
        candidate_id=candidate_id,
        raw_value=raw_value,
        raw_unit=raw_unit,
        raw_text=raw_text,
        field_hint=field_hint,
        object_hint="TOI-700",
        research_input_id=_uuid("research-input"),
        research_input_content_hash=_hash("pdf"),
        pipeline_source_snapshot_id="document.snapshot.logical",
        pipeline_source_snapshot_content_hash=_hash("snapshot"),
        persisted_source_snapshot_id=_uuid("source-snapshot"),
        document_parse_id=_uuid("document-parse"),
        parse_quality=quality,
        locator=DocumentLocator(page_index=0, block_id="block.teff"),
        created_at=datetime(2026, 8, 1, tzinfo=UTC),
    )


def _context(
    api,
    *,
    frozen_row_ids: tuple[str, ...] = ("dataset.row.toi700",),
    locator: DocumentLocator | None = None,
):
    locator = locator or DocumentLocator(page_index=0, block_id="block.teff")
    research_input = ResearchInputRef(
        id=_uuid("research-input"),
        type="pdf",
        source_type="upload",
        content_hash=_hash("pdf"),
        filename="paper.pdf",
        mime_type="application/pdf",
        size_bytes=100,
        created_at=datetime(2026, 8, 1, tzinfo=UTC),
        source_snapshot_id=_uuid("source-snapshot"),
    )
    snapshot = SourceSnapshotRecord(
        snapshot_id="document.snapshot.logical",
        source_id="research_input",
        source_type="document_parse",
        retrieved_at=datetime(2026, 8, 1, tzinfo=UTC),
        query="research_input:" + research_input.id,
        query_hash=_hash("query"),
        content_hash=_hash("snapshot"),
        license_note="user supplied research input",
        request_metadata={"source_mode": "fixture", "data_level": "frozen"},
    )
    return api.DocumentAdmissionContext(
        project_id=_uuid("project"),
        research_input=research_input,
        document_parse_id=_uuid("document-parse"),
        document_parse_project_id=_uuid("project"),
        document_parse_research_input_id=research_input.id,
        document_parse_input_content_hash=research_input.content_hash,
        document_parse_persisted_source_snapshot_id=_uuid("source-snapshot"),
        document_parse_overall_quality="accepted",
        persisted_locator_project_id=_uuid("project"),
        persisted_locator_document_parse_id=_uuid("document-parse"),
        persisted_locator_source_snapshot_id=_uuid("source-snapshot"),
        persisted_locator_hash=compute_canonical_payload_hash(
            locator.model_dump(mode="json", exclude_none=True)
        ),
        persisted_source_snapshot_id=_uuid("source-snapshot"),
        pipeline_source_snapshot=snapshot,
        frozen_crossmatch_row_ids=frozen_row_ids,
    )


def test_document_source_policy_is_required_and_explicit() -> None:
    with pytest.raises(ValidationError):
        DataRequirements(unit_policy="canonical")

    assert (
        DataRequirements(
            unit_policy="canonical", document_source_policy="research_input"
        ).document_source_policy
        == "research_input"
    )
    assert (
        DataRequirements(
            unit_policy="canonical", document_source_policy="disabled"
        ).document_source_policy
        == "disabled"
    )


def test_manifest_is_the_only_document_field_alias_authority() -> None:
    case_manifest = load_case_manifest()
    field_manifest = load_field_manifest()

    assert case_manifest.document_source_capability == "research_input"
    assert (
        field_manifest.resolve_document_field("star.effective_temperature").field_id
        == "star.effective_temperature"
    )
    assert (
        field_manifest.resolve_document_field("T_eff").field_id
        == "star.effective_temperature"
    )
    with pytest.raises(KeyError):
        field_manifest.resolve_document_field("teff")


@pytest.mark.parametrize(
    ("raw_value", "expected_value", "positive", "negative", "limit", "null_reason"),
    (
        ("5772", "5772", None, None, "measured", None),
        ("5772 ± 50", "5772", "50", "50", "measured", None),
        ("5772 +50 -40", "5772", "50", "40", "measured", None),
        ("< 1.2", "1.2", None, None, "upper_limit", None),
        ("> 1.2", "1.2", None, None, "lower_limit", None),
        (None, None, None, None, "not_applicable", "not_measured"),
    ),
)
def test_raw_document_semantics_are_parsed_once_into_typed_observation(
    raw_value: str | None,
    expected_value: str | None,
    positive: str | None,
    negative: str | None,
    limit: str,
    null_reason: str | None,
) -> None:
    api = _admission_api()
    observation = api.admit_scientific_document_candidate(
        candidate=_candidate(
            raw_value,
            raw_unit=None if raw_value is None else "K",
            raw_text="not measured" if raw_value is None else None,
        ),
        context=_context(api),
        canonical_row_id="dataset.row.toi700",
        case_manifest=load_case_manifest(),
        field_manifest=load_field_manifest(),
        data_requirements=DataRequirements(
            unit_policy="canonical", document_source_policy="research_input"
        ),
    )

    assert observation.canonical_field_id == "star.effective_temperature"
    assert observation.source_value == expected_value
    assert observation.source_unit == "kelvin"
    assert observation.uncertainty_positive == positive
    assert observation.uncertainty_negative == negative
    assert observation.limit_status == limit
    assert observation.null_reason == null_reason
    assert observation.provenance.kind == "document"
    assert observation.provenance.document_parse_id == _uuid("document-parse")
    assert observation.content_hash.startswith("sha256:")


@pytest.mark.parametrize(
    "mutation", ("disabled", "case", "parse", "snapshot", "locator", "row")
)
def test_document_admission_fails_closed_on_unauthorized_or_mismatched_closure(
    mutation: str,
) -> None:
    api = _admission_api()
    candidate = _candidate("5772")
    context = _context(api)
    case_manifest = load_case_manifest()
    requirements = DataRequirements(
        unit_policy="canonical", document_source_policy="research_input"
    )
    row_id = "dataset.row.toi700"

    if mutation == "disabled":
        requirements = requirements.model_copy(
            update={"document_source_policy": "disabled"}
        )
    elif mutation == "case":
        case_manifest = case_manifest.model_copy(
            update={"document_source_capability": "disabled"}
        )
    elif mutation == "parse":
        context = context.model_copy(update={"document_parse_id": _uuid("wrong-parse")})
    elif mutation == "snapshot":
        context = context.model_copy(
            update={"persisted_source_snapshot_id": _uuid("wrong-snapshot")}
        )
    elif mutation == "locator":
        context = context.model_copy(
            update={"persisted_locator_hash": _hash("wrong-locator")}
        )
    else:
        row_id = "dataset.row.unknown"

    with pytest.raises(api.DocumentAdmissionError):
        api.admit_scientific_document_candidate(
            candidate=candidate,
            context=context,
            canonical_row_id=row_id,
            case_manifest=case_manifest,
            field_manifest=load_field_manifest(),
            data_requirements=requirements,
        )


def test_partial_readable_is_admitted_but_unsupported_is_rejected() -> None:
    api = _admission_api()
    partial = api.admit_scientific_document_candidate(
        candidate=_candidate("5772", quality=DocumentParseQuality.partial),
        context=_context(api),
        canonical_row_id="dataset.row.toi700",
        case_manifest=load_case_manifest(),
        field_manifest=load_field_manifest(),
        data_requirements=DataRequirements(
            unit_policy="canonical", document_source_policy="research_input"
        ),
    )
    assert partial.parse_quality == "partial"

    with pytest.raises(api.DocumentAdmissionError):
        api.admit_scientific_document_candidate(
            candidate=_candidate("5772", quality=DocumentParseQuality.unsupported),
            context=_context(api),
            canonical_row_id="dataset.row.toi700",
            case_manifest=load_case_manifest(),
            field_manifest=load_field_manifest(),
            data_requirements=DataRequirements(
                unit_policy="canonical", document_source_policy="research_input"
            ),
        )


def _observation_for(
    row_id: str,
    *,
    field: str,
    value: str,
    unit: str,
    seed: str,
    quality: DocumentParseQuality = DocumentParseQuality.accepted,
):
    api = _admission_api()
    locator = DocumentLocator(page_index=0, block_id=f"block.{seed}")
    return api.admit_scientific_document_candidate(
        candidate=_candidate(
            value,
            raw_unit=unit,
            field_hint=field,
            quality=quality,
            candidate_id=f"document.candidate.{seed}",
        ).model_copy(update={"locator": locator}),
        context=_context(api, frozen_row_ids=(row_id,), locator=locator),
        canonical_row_id=row_id,
        case_manifest=load_case_manifest(),
        field_manifest=load_field_manifest(),
        data_requirements=DataRequirements(
            unit_policy="canonical", document_source_policy="research_input"
        ),
    )


def _with_documents(
    base: DataArtifactBuildInput, *observations
) -> DataArtifactBuildInput:
    ordered = tuple(
        sorted(
            observations,
            key=lambda item: (
                item.canonical_row_id,
                item.canonical_field_id,
                item.observation_id,
            ),
        )
    )
    unhashed = base.model_copy(
        update={
            "data_requirements": DataRequirements(
                unit_policy="canonical", document_source_policy="research_input"
            ),
            "document_observations": ordered,
            "input_hash": "sha256:" + "0" * 64,
        }
    )
    payload = unhashed.model_dump(mode="json")
    payload["input_hash"] = compute_data_artifact_input_hash(unhashed)
    return DataArtifactBuildInput.model_validate(payload)


def _accepted_row(dataset):
    return next(row for row in dataset.rows if row.alignment_status == "accepted")


def test_document_supplements_missing_structured_value_without_changing_crossmatch_scope() -> (
    None
):
    base = build_input("star.effective_temperature")
    baseline = build_data_artifact_candidates(base)
    row_id = _accepted_row(baseline.dataset).row_id
    observation = _observation_for(
        row_id,
        field="star.effective_temperature",
        value="5772 ± 50",
        unit="K",
        seed="supplement",
        quality=DocumentParseQuality.partial,
    )

    result = build_data_artifact_candidates(_with_documents(base, observation))
    row = next(item for item in result.dataset.rows if item.row_id == row_id)
    outcome = next(
        item
        for item in row.fields
        if item.canonical_field_id == "star.effective_temperature"
    )
    retained = {item.source_value_id: item for item in result.dataset.source_values}

    assert outcome.status == "mapped"
    assert retained[outcome.selected_source_value_id].provenance.kind == "document"
    assert len(result.dataset.crossmatch_source_snapshot_ids) == 2
    assert len(result.dataset.source_snapshot_ids) == 3
    assert len(result.source_collection.crossmatch_sources) == 2
    assert len(result.source_collection.supplemental_document_sources) == 1


def test_valid_structured_value_has_priority_over_document_value() -> None:
    base = build_input("star.tic_id")
    baseline = build_data_artifact_candidates(base)
    row_id = _accepted_row(baseline.dataset).row_id
    observation = _observation_for(
        row_id, field="star.tic_id", value="999999", unit="none", seed="priority"
    )

    result = build_data_artifact_candidates(_with_documents(base, observation))
    row = next(item for item in result.dataset.rows if item.row_id == row_id)
    outcome = next(
        item for item in row.fields if item.canonical_field_id == "star.tic_id"
    )
    retained = {item.source_value_id: item for item in result.dataset.source_values}

    assert retained[outcome.selected_source_value_id].provenance.kind == "structured"
    assert any(
        retained[item].provenance.kind == "document"
        for item in outcome.candidate_source_value_ids
    )


def test_identical_document_values_share_outcome_and_retain_every_provenance() -> None:
    base = build_input("star.effective_temperature")
    row_id = _accepted_row(build_data_artifact_candidates(base).dataset).row_id
    observations = (
        _observation_for(
            row_id,
            field="star.effective_temperature",
            value="5772",
            unit="K",
            seed="same-a",
        ),
        _observation_for(
            row_id,
            field="star.effective_temperature",
            value="5772.0",
            unit="kelvin",
            seed="same-b",
        ),
    )
    first = build_data_artifact_candidates(
        _with_documents(base, *reversed(observations))
    )
    second = build_data_artifact_candidates(_with_documents(base, *observations))
    row = next(item for item in first.dataset.rows if item.row_id == row_id)
    outcome = next(
        item
        for item in row.fields
        if item.canonical_field_id == "star.effective_temperature"
    )

    assert outcome.status == "mapped"
    assert len(outcome.candidate_source_value_ids) == 2
    assert not outcome.conflict_ids
    assert first.output_hash == second.output_hash


def test_document_only_conflict_retains_values_without_scientific_winner() -> None:
    base = build_input("star.effective_temperature")
    row_id = _accepted_row(build_data_artifact_candidates(base).dataset).row_id
    first = _observation_for(
        row_id,
        field="star.effective_temperature",
        value="5772",
        unit="K",
        seed="conflict-a",
    )
    second = _observation_for(
        row_id,
        field="star.effective_temperature",
        value="6000",
        unit="K",
        seed="conflict-b",
    )

    result = build_data_artifact_candidates(_with_documents(base, first, second))
    row = next(item for item in result.dataset.rows if item.row_id == row_id)
    outcome = next(
        item
        for item in row.fields
        if item.canonical_field_id == "star.effective_temperature"
    )

    assert outcome.status == "unresolved"
    assert len(outcome.candidate_source_value_ids) == 2
    assert outcome.conflict_ids
    assert not any(
        item.dataset_row_id == row_id
        and item.canonical_field_id == "star.effective_temperature"
        for item in result.dataset.selections
    )


def test_partial_parse_quality_is_observed_without_changing_crossmatch_completeness() -> (
    None
):
    from services.data_pipeline.data_quality import evaluate_data_quality
    from test_data_quality_pipeline import _contract, make_quality_input

    base = build_input("star.effective_temperature")
    baseline_quality_input, _ = make_quality_input(
        "star.effective_temperature", data_input=base
    )
    baseline_quality = evaluate_data_quality(baseline_quality_input)
    row_id = _accepted_row(build_data_artifact_candidates(base).dataset).row_id
    observation = _observation_for(
        row_id,
        field="star.effective_temperature",
        value="5772",
        unit="K",
        seed="quality-partial",
        quality=DocumentParseQuality.partial,
    )
    document_input = _with_documents(base, observation)
    contract_payload = _contract("star.effective_temperature").model_dump(mode="json")
    contract_payload["data_requirements"]["document_source_policy"] = "research_input"
    contract_payload["content_hash"] = compute_research_contract_content_hash(
        contract_payload
    )
    contract = ResearchContract.model_validate(contract_payload)
    quality_input, _ = make_quality_input(
        "star.effective_temperature", data_input=document_input, contract=contract
    )

    result = evaluate_data_quality(quality_input)

    assert result.kind == "data_quality"
    assert result.document_parse_quality_observations[0].parse_quality == "partial"
    assert (
        result.dataset_result.source_scope_completeness
        == baseline_quality.dataset_result.source_scope_completeness
    )


def test_publisher_materializes_closed_document_provenance() -> None:
    from test_data_artifact_api import _service_for_dataset
    from app.workflow.publisher import admit_artifact_candidate
    from services.data_pipeline.data_artifacts.admission import (
        validate_data_artifact_domain,
        validate_data_artifact_evidence,
    )
    from services.data_pipeline.data_quality import (
        admit_data_artifact_quality,
        build_data_quality_publication_validator,
        evaluate_data_quality,
    )
    from data_artifact_test_support import build_data_publication_bindings
    from test_data_quality_pipeline import _contract, make_quality_input

    base = build_input("star.tic_id")
    row_id = _accepted_row(build_data_artifact_candidates(base).dataset).row_id
    observation = _observation_for(
        row_id,
        field="star.tic_id",
        value="999999",
        unit="none",
        seed="publisher",
    )
    data_input = _with_documents(base, observation)
    contract_payload = _contract("star.tic_id").model_dump(mode="json")
    contract_payload["data_requirements"]["document_source_policy"] = "research_input"
    contract_payload["content_hash"] = compute_research_contract_content_hash(
        contract_payload
    )
    contract = ResearchContract.model_validate(contract_payload)
    quality_input, build_result = make_quality_input(
        "star.tic_id", data_input=data_input, contract=contract
    )
    quality_result = evaluate_data_quality(quality_input)
    quality_admission = admit_data_artifact_quality(
        build_result=build_result,
        evaluation_input=quality_input,
        evaluation_result=quality_result,
    )
    snapshots, evidence = build_data_publication_bindings(build_result.dataset)

    published = admit_artifact_candidate(
        build_result.dataset,
        schema_version=build_result.dataset.schema_version,
        source_snapshot_ids=build_result.dataset.source_snapshot_ids,
        evidence_ids=build_result.dataset.evidence_ids,
        evidence_validator=validate_data_artifact_evidence,
        domain_validator=validate_data_artifact_domain,
        quality_validator=build_data_quality_publication_validator(
            quality_admission, candidate_kind="dataset"
        ),
        source_snapshot_bindings=snapshots,
        evidence_bindings=evidence,
    )
    document_value = next(
        item
        for item in published.content["source_values"]
        if item["provenance"]["kind"] == "document"
    )

    assert document_value["provenance"]["persisted_source_snapshot_id"] == _uuid(
        "source-snapshot"
    )
    assert document_value["provenance"]["document_parse_id"] == _uuid("document-parse")
    assert document_value["provenance"]["locator"]["block_id"] == "block.publisher"

    read_service, version_id = _service_for_dataset(build_result.dataset)
    read_service._artifacts.version = read_service._artifacts.version.model_copy(
        update={"content": published.content}
    )
    read = read_service.get_dataset(version_id=version_id, session_id="session-1")
    persisted_document_value = next(
        item
        for item in read.dataset.source_values
        if item.provenance.kind == "document"
    )
    assert persisted_document_value.provenance.persisted_source_snapshot_id == _uuid(
        "source-snapshot"
    )
    assert persisted_document_value.provenance.document_parse_id == _uuid(
        "document-parse"
    )
