"""Targeted document data admission tests.

Covers the pure extraction pipeline (raw candidate → typed observation),
field/entity resolution authority, authorization, determinism, Dataset
selection semantics, quality observation mapping, and a real PostgreSQL
provenance-closure case that proves the persisted SourceSnapshot reuse.
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.source_acquisition import (
    RawDataSourceRecord,
    compute_raw_data_record_hash,
)
from app.schemas.core import (
    DocumentSourcePolicy,
    ResearchContract,
    ResearchContractInput,
    compute_research_contract_content_hash,
)
from app.schemas.data_artifacts import (
    DataArtifactBuildInput,
    DataSourceSnapshotProjection,
    DeclaredNullValue,
    DocumentObservationAdmissionCode,
    DocumentObservationAdmissionStatus,
    CrossmatchDataArtifactAuthority,
    CrossmatchRowAuthority,
    LimitStatus,
    MappedCanonicalValue,
    SourceValueCandidate,
    TypedDocumentObservation,
    UnresolvedCanonicalValue,
    compute_data_artifact_content_hash,
    compute_data_artifact_input_hash,
)
from app.schemas.data_quality import (
    DataQualityEvaluationInput,
    DataQualityEvaluationResult,
    DocumentParseQualityStatus,
    compute_data_quality_input_hash,
)
from app.schemas.scientific_document import (
    DocumentBBox,
    DocumentBlock,
    DocumentBlockKind,
    DocumentParseCandidate,
    DocumentParseProfile,
    DocumentParseQuality,
    DocumentPage,
    DocumentTable,
    DocumentTableCell,
    ParserBackend,
)
from app.services.content_storage import LocalContentStorage, sha256_content_hash
from services.data_pipeline.crossmatch import align_cross_source_records
from services.data_pipeline.crossmatch.benchmark import (
    _scenario_input,
    load_crossmatch_benchmark,
)
from services.data_pipeline.data_artifacts.pipeline import (
    build_data_artifact_candidates,
)
from services.data_pipeline.data_artifacts.policy import (
    load_unit_conversion_catalog,
)
from services.data_pipeline.data_quality import evaluate_data_quality
from services.data_pipeline.data_quality.policy import (
    load_frozen_quality_rule_set,
)
from services.data_pipeline.document_observation_rules import (
    load_document_observation_rule_set,
)
from services.data_pipeline.document_observations import (
    DocumentObservationError,
    PersistedDocumentContext,
    _EntityIndex,
    extract_document_observations,
)
from services.data_pipeline.manifest import load_frozen_manifest_bundle

from data_artifact_test_support import build_input

NOW = datetime(2026, 8, 12, 8, 0, tzinfo=UTC)
BUNDLE = load_frozen_manifest_bundle()
RULES = load_document_observation_rule_set()
CATALOG = load_unit_conversion_catalog()

INPUT_ID = uuid4()
PARSE_ID = uuid4()
SNAPSHOT_ID = uuid4()
INPUT_CONTENT_HASH = "sha256:" + "a" * 64
PARSE_INPUT_HASH = compute_canonical_payload_hash({"profile": "native-default"})
CANONICAL_OUTPUT_HASH = "sha256:" + "d" * 64
CONFIG_HASH = "sha256:" + "c" * 64
QUERY_HASH = compute_canonical_payload_hash({"research_input_id": str(INPUT_ID)})

HEADER_ROW = ("star.tic_id", "Teff [K]", "star.radius [R_sun]")
REQUESTED_FIELDS = (
    "star.tic_id",
    "star.effective_temperature",
    "star.radius",
)


@pytest.fixture(scope="module")
def crossmatch():
    benchmark = load_crossmatch_benchmark()
    scenario = next(
        item for item in benchmark.scenarios if item.scenario_id == "exact_one_to_one"
    )
    return align_cross_source_records(_scenario_input(scenario))


@pytest.fixture(scope="module")
def host_token(crossmatch) -> str:
    return next(
        value.normalized_value
        for candidate in crossmatch.candidates
        if candidate.entity_level.value == "host_star"
        for value in candidate.identity_values
        if value.field_id == "star.tic_id"
    )


def _context() -> PersistedDocumentContext:
    return PersistedDocumentContext(
        research_input_id=str(INPUT_ID),
        document_parse_id=str(PARSE_ID),
        source_snapshot_id=str(SNAPSHOT_ID),
    )


def _projection() -> DataSourceSnapshotProjection:
    return DataSourceSnapshotProjection(
        snapshot_id=f"research-input.{INPUT_ID}",
        source_id=f"research_input:{INPUT_ID}",
        source_type="research_input_upload",
        retrieved_at=NOW,
        query={"research_input_id": str(INPUT_ID)},
        query_hash=QUERY_HASH,
        content_hash=INPUT_CONTENT_HASH,
        license_note="user-provided upload",
    )


def _cell(cell_id: str, row: int, column: int, text: str) -> DocumentTableCell:
    return DocumentTableCell(
        cell_id=cell_id,
        row_index=row,
        column_index=column,
        text=text,
        quality=DocumentParseQuality.accepted,
    )


def _parse(
    body_rows: list[tuple[str, ...]],
    *,
    header: tuple[str, ...] = HEADER_ROW,
) -> DocumentParseCandidate:
    header_cells = []
    for column, label in enumerate(header):
        header_cells.append(
            DocumentTableCell(
                cell_id=f"h-{column}",
                row_index=0,
                column_index=column,
                text=label,
                is_header=True,
                quality=DocumentParseQuality.accepted,
            )
        )
    rows = [tuple(header_cells)]
    for index, values in enumerate(body_rows, start=1):
        rows.append(
            tuple(
                _cell(f"c-{index}-{column}", index, column, text)
                for column, text in enumerate(values)
            )
        )
    block = DocumentBlock(
        block_id="doc-table-block",
        page_index=0,
        reading_order=0,
        kind=DocumentBlockKind.table,
        bbox=DocumentBBox(x1=10, y1=20, x2=500, y2=200),
        text="observation table",
        quality=DocumentParseQuality.accepted,
        parser_backend=ParserBackend.native,
        parser_profile_id="native-default",
    )
    return DocumentParseCandidate(
        parse_id="document-parse-fixture",
        research_input_id=str(INPUT_ID),
        content_hash=INPUT_CONTENT_HASH,
        profile=DocumentParseProfile(
            parser_profile_id="native-default",
            parser_profile_version="1.0.0",
            native_backend="docling-parse",
            routing_policy_id="native-only",
            resource_policy_id="cpu",
            configuration_hash=CONFIG_HASH,
        ),
        native_engine="docling-parse",
        native_engine_version="7.11.0",
        config_hash=CONFIG_HASH,
        canonical_output_hash=CANONICAL_OUTPUT_HASH,
        pages=(
            DocumentPage(
                page_index=0,
                width_points=612,
                height_points=792,
                block_ids=("doc-table-block",),
            ),
        ),
        blocks=(block,),
        tables=(
            DocumentTable(
                table_id="observations-table",
                page_index=0,
                block_id="doc-table-block",
                row_count=len(rows),
                column_count=len(header),
                rows=tuple(rows),
                quality=DocumentParseQuality.accepted,
            ),
        ),
        overall_quality=DocumentParseQuality.accepted,
        created_at=NOW,
    )


def _table_quality_parse(
    host_token: str,
    *,
    table_quality: DocumentParseQuality = DocumentParseQuality.accepted,
    entity_header_quality: DocumentParseQuality = DocumentParseQuality.accepted,
    value_header_quality: DocumentParseQuality = DocumentParseQuality.accepted,
    entity_quality: DocumentParseQuality = DocumentParseQuality.accepted,
    value_quality: DocumentParseQuality = DocumentParseQuality.accepted,
    value_header: str = "Teff [K]",
) -> DocumentParseCandidate:
    parse = _parse([(host_token, "5600")], header=("star.tic_id", value_header))
    table = parse.tables[0]
    header_row = list(table.rows[0])
    header_row[0] = header_row[0].model_copy(
        update={"quality": entity_header_quality}
    )
    header_row[1] = header_row[1].model_copy(
        update={"quality": value_header_quality}
    )
    body_row = list(table.rows[1])
    body_row[0] = body_row[0].model_copy(update={"quality": entity_quality})
    body_row[1] = body_row[1].model_copy(update={"quality": value_quality})
    table = table.model_copy(
        update={
            "quality": table_quality,
            "rows": (tuple(header_row), tuple(body_row)),
        }
    )
    return parse.model_copy(update={"tables": (table,)})


def _extract(
    body_rows: list[tuple[str, ...]],
    crossmatch,
    *,
    policy: DocumentSourcePolicy = DocumentSourcePolicy.research_input,
    capability: bool = True,
    requested: tuple[str, ...] = REQUESTED_FIELDS,
    header: tuple[str, ...] = HEADER_ROW,
):
    return extract_document_observations(
        parse=_parse(body_rows, header=header),
        context=_context(),
        snapshot_projection=_projection(),
        contract_policy=policy,
        case_capability=capability,
        requested_fields=requested,
        manifests=BUNDLE,
        crossmatch=crossmatch,
        rules=RULES,
    )


def t_shared_alias_batch(crossmatch, entity_token: str):
    """One 'Mass' column spanning planet+star domains with no matching entity."""

    return _extract(
        [(entity_token, "1.10")],
        crossmatch,
        requested=("star.tic_id", "star.mass", "planet.mass"),
        header=("star.tic_id", "Mass"),
    )


def _outcome_for(batch, code) -> list:
    return [item for item in batch.outcomes if item.code is code]


def _accepted_for(batch, field_id: str):
    return [item for item in batch.accepted if item.canonical_field_id == field_id]


def test_table_extraction_admits_typed_observations_with_locator_closure(
    crossmatch, host_token
) -> None:
    parse = _parse([(host_token, "5600 ± 50 K", "1.20")])
    batch = extract_document_observations(
        parse=parse,
        context=_context(),
        snapshot_projection=_projection(),
        contract_policy=DocumentSourcePolicy.research_input,
        case_capability=True,
        requested_fields=REQUESTED_FIELDS,
        manifests=BUNDLE,
        crossmatch=crossmatch,
        rules=RULES,
    )

    assert len(batch.raw_candidates) == 2
    assert all(item.candidate_id.startswith("cand.") for item in batch.raw_candidates)
    assert batch.producer_output_summary["accepted_count"] == 2
    assert all(
        cell.bbox is None
        for row in parse.tables[0].rows
        for cell in row
    )
    assert all(
        item.document_locator.bbox == parse.blocks[0].bbox
        for item in batch.accepted
    )
    teff = _accepted_for(batch, "star.effective_temperature")
    radius = _accepted_for(batch, "star.radius")
    assert len(teff) == 1 and len(radius) == 1
    paired_key = next(
        record.logical_match_key
        for record in crossmatch.records
        if record.record_type == "paired"
    )
    assert teff[0].crossmatch_logical_key == paired_key
    assert teff[0].parsed_scalar == Decimal("5600")
    assert teff[0].uncertainty_positive_raw == Decimal("50")
    assert teff[0].uncertainty_negative_raw == Decimal("50")
    assert teff[0].source_unit == "kelvin"
    assert teff[0].persisted_source_snapshot_id == str(SNAPSHOT_ID)
    assert radius[0].parsed_scalar == Decimal("1.2")

    from app.services.document_parse_store import validate_document_locator

    for observation in batch.accepted:
        validate_document_locator(parse, observation.document_locator)


@pytest.mark.parametrize(
    (
        "table_quality",
        "entity_header_quality",
        "value_header_quality",
        "entity_quality",
        "value_quality",
        "value_header",
        "expected_quality",
        "expected_code",
        "expected_status",
        "expected_raw_quality",
    ),
    [
        (
            DocumentParseQuality.accepted,
            DocumentParseQuality.accepted,
            DocumentParseQuality.accepted,
            DocumentParseQuality.accepted,
            DocumentParseQuality.accepted,
            "Teff [K]",
            DocumentParseQuality.accepted,
            None,
            None,
            None,
        ),
        (
            DocumentParseQuality.partial,
            DocumentParseQuality.accepted,
            DocumentParseQuality.accepted,
            DocumentParseQuality.accepted,
            DocumentParseQuality.accepted,
            "Teff [K]",
            DocumentParseQuality.partial,
            None,
            None,
            None,
        ),
        (
            DocumentParseQuality.accepted,
            DocumentParseQuality.partial,
            DocumentParseQuality.accepted,
            DocumentParseQuality.accepted,
            DocumentParseQuality.accepted,
            "Teff [K]",
            DocumentParseQuality.partial,
            None,
            None,
            None,
        ),
        (
            DocumentParseQuality.accepted,
            DocumentParseQuality.accepted,
            DocumentParseQuality.partial,
            DocumentParseQuality.accepted,
            DocumentParseQuality.accepted,
            "Teff [K]",
            DocumentParseQuality.partial,
            None,
            None,
            None,
        ),
        (
            DocumentParseQuality.accepted,
            DocumentParseQuality.accepted,
            DocumentParseQuality.accepted,
            DocumentParseQuality.partial,
            DocumentParseQuality.accepted,
            "Teff [K]",
            DocumentParseQuality.partial,
            None,
            None,
            None,
        ),
        (
            DocumentParseQuality.accepted,
            DocumentParseQuality.accepted,
            DocumentParseQuality.accepted,
            DocumentParseQuality.accepted,
            DocumentParseQuality.partial,
            "Teff [K]",
            DocumentParseQuality.partial,
            None,
            None,
            None,
        ),
        (
            DocumentParseQuality.accepted,
            DocumentParseQuality.accepted,
            DocumentParseQuality.unsupported,
            DocumentParseQuality.accepted,
            DocumentParseQuality.accepted,
            "Teff [K]",
            None,
            None,
            None,
            None,
        ),
        (
            DocumentParseQuality.accepted,
            DocumentParseQuality.unsupported,
            DocumentParseQuality.accepted,
            DocumentParseQuality.accepted,
            DocumentParseQuality.accepted,
            "Teff [K]",
            None,
            None,
            None,
            None,
        ),
        (
            DocumentParseQuality.accepted,
            DocumentParseQuality.accepted,
            DocumentParseQuality.accepted,
            DocumentParseQuality.accepted,
            DocumentParseQuality.accepted,
            "Unknown field",
            None,
            DocumentObservationAdmissionCode.document_field_unresolved,
            DocumentObservationAdmissionStatus.review_required,
            DocumentParseQuality.accepted,
        ),
        (
            DocumentParseQuality.accepted,
            DocumentParseQuality.accepted,
            DocumentParseQuality.partial,
            DocumentParseQuality.accepted,
            DocumentParseQuality.accepted,
            "Unknown field",
            None,
            DocumentObservationAdmissionCode.document_field_unresolved,
            DocumentObservationAdmissionStatus.review_required,
            DocumentParseQuality.partial,
        ),
    ],
)
def test_table_observation_quality_propagates_from_all_regions(
    crossmatch,
    host_token,
    table_quality,
    entity_header_quality,
    value_header_quality,
    entity_quality,
    value_quality,
    value_header,
    expected_quality,
    expected_code,
    expected_status,
    expected_raw_quality,
) -> None:
    parse = _table_quality_parse(
        host_token,
        table_quality=table_quality,
        entity_header_quality=entity_header_quality,
        value_header_quality=value_header_quality,
        entity_quality=entity_quality,
        value_quality=value_quality,
        value_header=value_header,
    )
    batch = extract_document_observations(
        parse=parse,
        context=_context(),
        snapshot_projection=_projection(),
        contract_policy=DocumentSourcePolicy.research_input,
        case_capability=True,
        requested_fields=REQUESTED_FIELDS,
        manifests=BUNDLE,
        crossmatch=crossmatch,
        rules=RULES,
    )
    observations = _accepted_for(batch, "star.effective_temperature")
    if expected_code is not None:
        assert batch.accepted == ()
        assert len(batch.raw_candidates) == 1
        assert batch.raw_candidates[0].parse_quality is expected_raw_quality
        assert len(batch.outcomes) == 1
        assert batch.outcomes[0].code is expected_code
        assert batch.outcomes[0].status is expected_status
    elif expected_quality is None:
        assert observations == []
        assert batch.raw_candidates == ()
        assert batch.outcomes == ()
    else:
        assert len(observations) == 1
        assert observations[0].parse_quality is expected_quality


def test_body_row_cannot_be_promoted_to_table_header(
    crossmatch, host_token
) -> None:
    parse = _parse(
        [
            ("star.tic_id", "Teff [K]"),
            (host_token, "5600"),
        ]
    )
    table = parse.tables[0]
    header_row = list(table.rows[0])
    header_row[0] = header_row[0].model_copy(
        update={"quality": DocumentParseQuality.unsupported}
    )
    parse = parse.model_copy(
        update={
            "tables": (
                table.model_copy(
                    update={
                        "rows": (
                            tuple(header_row),
                            *table.rows[1:],
                        )
                    }
                ),
            )
        }
    )

    assert parse.tables[0].rows[0][0].is_header is True
    assert parse.tables[0].rows[1][0].is_header is False
    batch = extract_document_observations(
        parse=parse,
        context=_context(),
        snapshot_projection=_projection(),
        contract_policy=DocumentSourcePolicy.research_input,
        case_capability=True,
        requested_fields=REQUESTED_FIELDS,
        manifests=BUNDLE,
        crossmatch=crossmatch,
        rules=RULES,
    )

    assert batch.raw_candidates == ()
    assert batch.accepted == ()
    assert batch.outcomes == ()


def _rehash_source_value_payload(payload: dict) -> dict:
    payload["content_hash"] = compute_data_artifact_content_hash(payload)
    return payload


def _structured_source_value_payload() -> dict:
    dataset = build_data_artifact_candidates(build_input("star.tic_id")).dataset
    source_value = next(
        item
        for item in dataset.source_values
        if item.origin.kind == "structured_database"
    )
    return source_value.model_dump(mode="json")


def _document_source_value_payload() -> dict:
    baseline = build_input("planet.mass")
    logical_key = next(
        row.row_authority.logical_key
        for row in build_data_artifact_candidates(baseline).dataset.rows
        if isinstance(row.row_authority, CrossmatchRowAuthority)
        and any(field.canonical_field_id == "planet.mass" for field in row.fields)
    )
    result = build_data_artifact_candidates(
        _with_documents(
            baseline,
            [
                _observation(
                    index=1,
                    field_id="planet.mass",
                    logical_key=logical_key,
                    scalar="1.5",
                    unit="earth_mass",
                )
            ],
        )
    )
    source_value = next(
        item
        for item in result.dataset.source_values
        if item.origin.kind == "document_research_input"
    )
    return source_value.model_dump(mode="json")


def test_structured_applicable_limit_requires_database_provenance() -> None:
    payload = _structured_source_value_payload()
    payload["limit"] = {
        "status": LimitStatus.upper_limit.value,
        "raw_flag": None,
        "locator": None,
    }
    with pytest.raises(
        ValidationError, match="structured applicable limit requires database flag"
    ):
        SourceValueCandidate.model_validate(_rehash_source_value_payload(payload))


def test_structured_applicable_limit_accepts_database_provenance() -> None:
    payload = _structured_source_value_payload()
    payload["limit"] = {
        "status": LimitStatus.upper_limit.value,
        "raw_flag": 0,
        "locator": payload["evidence_locator"],
    }
    SourceValueCandidate.model_validate(_rehash_source_value_payload(payload))


def test_document_applicable_limit_remains_semantic_only() -> None:
    payload = _document_source_value_payload()
    payload["limit"] = {
        "status": LimitStatus.upper_limit.value,
        "raw_flag": None,
        "locator": None,
    }
    SourceValueCandidate.model_validate(_rehash_source_value_payload(payload))


def test_document_applicable_limit_rejects_database_provenance() -> None:
    payload = _document_source_value_payload()
    structured_locator = _structured_source_value_payload()["evidence_locator"]
    payload["limit"] = {
        "status": LimitStatus.upper_limit.value,
        "raw_flag": 0,
        "locator": structured_locator,
    }
    with pytest.raises(
        ValidationError, match="document limit must carry semantic status"
    ):
        SourceValueCandidate.model_validate(_rehash_source_value_payload(payload))


@pytest.mark.parametrize(
    ("raw_text", "expectation"),
    [
        ("5200", {"scalar": Decimal("5200")}),
        (
            "5600 ± 30",
            {
                "scalar": Decimal("5600"),
                "positive": Decimal("30"),
                "negative": Decimal("30"),
            },
        ),
        (
            "5600 +60/-40",
            {
                "scalar": Decimal("5600"),
                "positive": Decimal("60"),
                "negative": Decimal("40"),
            },
        ),
        ("< 5400", {"scalar": Decimal("5400"), "limit": "upper_limit"}),
        ("> 5800", {"scalar": Decimal("5800"), "limit": "lower_limit"}),
        ("--", {"null": "not_measured"}),
    ],
)
def test_scalar_semantics_are_parsed_exactly_once(
    crossmatch, host_token, raw_text, expectation
) -> None:
    batch = _extract([(host_token, raw_text, "--")], crossmatch)

    observations = _accepted_for(batch, "star.effective_temperature")
    if expectation.get("null") == "not_measured":
        assert len(observations) == 1
        assert observations[0].null_status is not None
        assert observations[0].parsed_scalar is None
        return
    assert len(observations) == 1
    observation = observations[0]
    assert observation.parsed_scalar == expectation["scalar"]
    assert observation.null_status is None
    limit = expectation.get("limit")
    assert (observation.limit_status.value if observation.limit_status else None) == (
        limit or "not_applicable"
    )
    if "positive" in expectation:
        assert observation.uncertainty_positive_raw == expectation["positive"]
        assert observation.uncertainty_negative_raw == expectation["negative"]


def test_invalid_number_rejects_and_unknown_unit_reviews(
    crossmatch, host_token
) -> None:
    batch = _extract([(host_token, "abc", "--")], crossmatch)
    rejected = _outcome_for(
        batch, DocumentObservationAdmissionCode.document_value_invalid
    )
    assert len(rejected) == 1
    assert rejected[0].status is DocumentObservationAdmissionStatus.rejected
    assert not _accepted_for(batch, "star.effective_temperature")

    unknown_unit = _extract([(host_token, "5600 Zorp", "--")], crossmatch)
    reviewed = _outcome_for(
        unknown_unit, DocumentObservationAdmissionCode.document_unit_unresolved
    )
    assert len(reviewed) == 1
    assert reviewed[0].status is DocumentObservationAdmissionStatus.review_required


def test_unknown_table_header_keeps_raw_candidate_for_review(
    crossmatch, host_token
) -> None:
    batch = _extract(
        [(host_token, "1.2")],
        crossmatch,
        requested=("star.tic_id",),
        header=("star.tic_id", "unregistered.scientific_field"),
    )

    assert len(batch.raw_candidates) == 1
    assert batch.accepted == ()
    assert len(batch.outcomes) == 1
    assert batch.outcomes[0].code is (
        DocumentObservationAdmissionCode.document_field_unresolved
    )
    assert (
        batch.outcomes[0].status is DocumentObservationAdmissionStatus.review_required
    )


def test_signed_scalar_and_dimensioned_missing_unit_are_fail_closed(
    crossmatch, host_token
) -> None:
    signed = _extract(
        [(host_token, "-0.15 dex")],
        crossmatch,
        requested=("star.tic_id", "star.metallicity"),
        header=("star.tic_id", "star.metallicity"),
    )
    assert signed.accepted[0].parsed_scalar == Decimal("-0.15")
    assert signed.accepted[0].source_unit == "dex"

    missing_unit = _extract(
        [(host_token, "5600")],
        crossmatch,
        requested=("star.tic_id", "star.effective_temperature"),
        header=("star.tic_id", "star.effective_temperature"),
    )
    assert missing_unit.accepted == ()
    assert missing_unit.outcomes[0].code is (
        DocumentObservationAdmissionCode.document_unit_unresolved
    )
    assert (
        missing_unit.outcomes[0].status
        is DocumentObservationAdmissionStatus.review_required
    )


def _text_parse(
    text: str,
    *,
    kind: DocumentBlockKind = DocumentBlockKind.paragraph,
    quality: DocumentParseQuality = DocumentParseQuality.accepted,
) -> DocumentParseCandidate:
    base = _parse([])
    block = DocumentBlock(
        block_id="doc-text-block",
        page_index=0,
        reading_order=1,
        kind=kind,
        bbox=DocumentBBox(x1=20, y1=220, x2=580, y2=260),
        text=text,
        quality=quality,
        parser_backend=ParserBackend.native,
        parser_profile_id="native-default",
    )
    return base.model_copy(
        update={
            "pages": (
                base.pages[0].model_copy(update={"block_ids": ("doc-text-block",)}),
            ),
            "blocks": (block,),
            "tables": (),
        }
    )


@pytest.mark.parametrize("kind", [DocumentBlockKind.paragraph, DocumentBlockKind.list])
def test_text_observation_patterns_admit_multiple_and_preserve_geometry(
    crossmatch, host_token, kind
) -> None:
    parse = _text_parse(
        f"star.effective_temperature = 5600 K for {host_token}; "
        f"star.radius = 1.2 R_sun for {host_token}",
        kind=kind,
    )
    batch = extract_document_observations(
        parse=parse,
        context=_context(),
        snapshot_projection=_projection(),
        contract_policy=DocumentSourcePolicy.research_input,
        case_capability=True,
        requested_fields=REQUESTED_FIELDS + ("star.radius",),
        manifests=BUNDLE,
        crossmatch=crossmatch,
        rules=RULES,
    )

    assert len(batch.raw_candidates) == 2
    assert {item.canonical_field_id for item in batch.accepted} == {
        "star.effective_temperature",
        "star.radius",
    }
    assert all(
        item.document_locator.bbox == parse.blocks[0].bbox for item in batch.accepted
    )
    assert all(item.document_locator.reading_order == 1 for item in batch.accepted)
    assert all(item.document_locator.text_span is not None for item in batch.accepted)


def test_text_unknown_field_missing_unit_partial_and_unsupported_are_explicit(
    crossmatch, host_token
) -> None:
    reviewed = extract_document_observations(
        parse=_text_parse(
            f"unregistered.scientific_field = 5600 K for {host_token}; "
            f"star.effective_temperature = 5600 for {host_token}",
            quality=DocumentParseQuality.partial,
        ),
        context=_context(),
        snapshot_projection=_projection(),
        contract_policy=DocumentSourcePolicy.research_input,
        case_capability=True,
        requested_fields=REQUESTED_FIELDS,
        manifests=BUNDLE,
        crossmatch=crossmatch,
        rules=RULES,
    )
    assert len(reviewed.raw_candidates) == 2
    assert {item.code for item in reviewed.outcomes} == {
        DocumentObservationAdmissionCode.document_field_unresolved,
        DocumentObservationAdmissionCode.document_unit_unresolved,
    }
    assert all(
        item.status is DocumentObservationAdmissionStatus.review_required
        for item in reviewed.outcomes
    )

    unsupported = extract_document_observations(
        parse=_text_parse(
            f"star.effective_temperature = 5600 K for {host_token}",
            quality=DocumentParseQuality.unsupported,
        ),
        context=_context(),
        snapshot_projection=_projection(),
        contract_policy=DocumentSourcePolicy.research_input,
        case_capability=True,
        requested_fields=REQUESTED_FIELDS,
        manifests=BUNDLE,
        crossmatch=crossmatch,
        rules=RULES,
    )
    assert unsupported.raw_candidates == ()
    assert unsupported.accepted == ()


def test_field_resolution_authority(crossmatch, host_token) -> None:
    # Registered document alias exact.
    alias_batch = _extract([(host_token, "5100", "--")], crossmatch)
    assert _accepted_for(alias_batch, "star.effective_temperature")

    canonical_parse = _parse([(host_token, "5100", "--")])
    rebuilt_header = list(canonical_parse.tables[0].rows[0])
    rebuilt_header[1] = rebuilt_header[1].model_copy(
        update={"text": "star.effective_temperature [K]"}
    )
    rebuilt_rows = [tuple(rebuilt_header), *canonical_parse.tables[0].rows[1:]]
    canonical_parse = canonical_parse.model_copy(
        update={
            "tables": (
                canonical_parse.tables[0].model_copy(
                    update={"rows": tuple(rebuilt_rows)}
                ),
            )
        }
    )
    canonical_batch = extract_document_observations(
        parse=canonical_parse,
        context=_context(),
        snapshot_projection=_projection(),
        contract_policy=DocumentSourcePolicy.research_input,
        case_capability=True,
        requested_fields=REQUESTED_FIELDS,
        manifests=BUNDLE,
        crossmatch=crossmatch,
        rules=RULES,
    )
    assert _accepted_for(canonical_batch, "star.effective_temperature")

    # An unregistered header label maps nothing for that column while every
    # registered column still resolves deterministically.
    unknown_batch = _extract([(host_token, "5100", "--")], crossmatch)
    assert not any(
        item.canonical_field_id == "star.luminosity" for item in unknown_batch.accepted
    )
    assert _accepted_for(unknown_batch, "star.effective_temperature")

    # A shared label spanning two object domains stays ambiguous while the
    # entity token matches nothing; the ladder reviews instead of choosing.
    shared = t_shared_alias_batch(crossmatch, "TIC 404")
    reviewed = [
        item
        for item in shared.outcomes
        if item.code is DocumentObservationAdmissionCode.document_field_ambiguous
    ]
    assert reviewed
    assert reviewed[0].status is DocumentObservationAdmissionStatus.review_required


def test_entity_resolution_requires_exact_unique_frozen_row(
    crossmatch, host_token
) -> None:
    unresolved = _extract([("TIC 404", "5100", "--")], crossmatch)
    reviewed = _outcome_for(
        unresolved,
        DocumentObservationAdmissionCode.document_entity_unresolved,
    )
    assert len(reviewed) >= 1
    assert reviewed[0].status is DocumentObservationAdmissionStatus.review_required

    index = _EntityIndex(crossmatch=crossmatch)
    index._keys_by_token["TIC 101"] = {
        "sha256:" + "1" * 64,
        "sha256:" + "2" * 64,
    }
    index._objects_by_token["TIC 101"] = {"star"}
    key, status = index.exact_unique_match("TIC 101", "star")
    assert key is None and status == "ambiguous"


def test_disabled_policy_rejects_every_document_value(crossmatch, host_token) -> None:
    batch = _extract(
        [(host_token, "5100", "5600 K")],
        crossmatch,
        policy=DocumentSourcePolicy.disabled,
    )
    assert batch.accepted == ()
    assert batch.outcomes
    assert all(
        outcome.status is DocumentObservationAdmissionStatus.rejected
        and outcome.code is DocumentObservationAdmissionCode.document_source_disabled
        for outcome in batch.outcomes
    )


def test_missing_case_capability_rejects(crossmatch, host_token) -> None:
    batch = _extract([(host_token, "5100", "--")], crossmatch, capability=False)
    assert batch.accepted == ()
    assert all(
        outcome.code
        is DocumentObservationAdmissionCode.document_source_capability_unsupported
        for outcome in batch.outcomes
    )


def test_context_mismatch_fails_closed(crossmatch) -> None:
    from services.data_pipeline.document_observations import (
        PersistedDocumentContext as Ctx,
    )

    parse = _parse([("TIC 101", "5100", "--")])
    wrong_context = Ctx(
        research_input_id=str(uuid4()),
        document_parse_id=str(PARSE_ID),
        source_snapshot_id=str(SNAPSHOT_ID),
    )
    with pytest.raises(DocumentObservationError):
        extract_document_observations(
            parse=parse,
            context=wrong_context,
            snapshot_projection=_projection(),
            contract_policy=DocumentSourcePolicy.research_input,
            case_capability=True,
            requested_fields=REQUESTED_FIELDS,
            manifests=BUNDLE,
            crossmatch=crossmatch,
            rules=RULES,
        )


def test_determinism_and_sensitivity(crossmatch, host_token) -> None:
    first = _extract([(host_token, "5100", "--")], crossmatch)
    second = _extract([(host_token, "5100", "--")], crossmatch)
    assert [item.candidate_id for item in first.raw_candidates] == [
        item.candidate_id for item in second.raw_candidates
    ]
    assert first.producer_output_summary == second.producer_output_summary

    changed = _extract([(host_token, "5200", "--")], crossmatch)
    assert changed.raw_candidates[0].candidate_id != (
        first.raw_candidates[0].candidate_id
    )


# ---------------------------------------------------------------------------
# Dataset projection integration (selection/conflict semantics)
# ---------------------------------------------------------------------------


def _observation(
    *,
    index: int,
    field_id: str,
    logical_key: str,
    scalar: str,
    unit: str,
) -> TypedDocumentObservation:
    research_input_id = uuid4()
    return TypedDocumentObservation(
        observation_id=f"obs.test-{index}",
        raw_candidate_id=f"cand.test-{index}",
        research_input_id=str(research_input_id),
        document_parse_id=str(uuid4()),
        persisted_source_snapshot_id=str(uuid4()),
        pipeline_source_snapshot=DataSourceSnapshotProjection(
            snapshot_id=f"research-input.{research_input_id}",
            source_id=f"research_input:{research_input_id}",
            source_type="research_input_upload",
            retrieved_at=NOW,
            query={"research_input_id": str(research_input_id)},
            query_hash=compute_canonical_payload_hash(
                {"research_input_id": str(research_input_id)}
            ),
            content_hash=INPUT_CONTENT_HASH,
            license_note="user-provided upload",
        ),
        document_locator=__import__(
            "app.schemas.scientific_document", fromlist=["DocumentLocator"]
        ).DocumentLocator(page_index=0, block_id="b"),
        parse_quality=DocumentParseQuality.accepted,
        canonical_field_id=field_id,
        crossmatch_logical_key=logical_key,
        raw_value=scalar,
        raw_text=scalar,
        parsed_scalar=Decimal(scalar),
        source_unit=unit,
    )


def _with_documents(
    baseline: DataArtifactBuildInput, documents
) -> DataArtifactBuildInput:
    assert isinstance(baseline.authority, CrossmatchDataArtifactAuthority)
    unhashed = DataArtifactBuildInput.model_construct(
        manifest_pins=baseline.manifest_pins,
        requested_fields=baseline.requested_fields,
        authority=baseline.authority.model_copy(
            update={"document_observations": tuple(documents)}
        ),
        mapping_rule_set=baseline.mapping_rule_set,
        conversion_catalog=baseline.conversion_catalog,
        producer_version=baseline.producer_version,
        quality_constraints_reference=baseline.quality_constraints_reference,
        input_hash="sha256:" + "0" * 64,
    )
    payload = unhashed.model_dump(mode="json")
    payload["input_hash"] = compute_data_artifact_input_hash(unhashed)
    return DataArtifactBuildInput.model_validate(payload)


def _structured_orbital_baseline() -> DataArtifactBuildInput:
    """Baseline with a real structured planet.orbital_period value on both sides."""

    benchmark = load_crossmatch_benchmark()
    scenario = next(
        item for item in benchmark.scenarios if item.scenario_id == "exact_one_to_one"
    )
    crossmatch_input = _scenario_input(scenario)

    def add_measurement(acquisition):
        records = []
        for record in acquisition.records:
            payload = {
                **record.payload,
                "pl_orbper": 1.0,
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

    injected = crossmatch_input.model_copy(
        update={
            "left": add_measurement(crossmatch_input.left),
            "right": add_measurement(crossmatch_input.right),
        }
    )
    return (
        _baseline_from_injected(injected)
    )


def _baseline_from_injected(crossmatch_input) -> DataArtifactBuildInput:
    from app.schemas.data_artifacts import ManifestPins
    from services.data_pipeline.crossmatch import align_cross_source_records as align
    from services.data_pipeline.data_artifacts.policy import (
        load_mapping_rule_set,
    )

    result = align(crossmatch_input)
    pins = ManifestPins(
        case_manifest_id=result.case_manifest_id,
        case_manifest_version=result.case_manifest_version,
        case_manifest_content_hash=result.case_manifest_content_hash,
        field_manifest_id=result.field_manifest_id,
        field_manifest_version=result.field_manifest_version,
        field_manifest_content_hash=result.field_manifest_content_hash,
    )
    mapping = load_mapping_rule_set()
    unhashed = DataArtifactBuildInput.model_construct(
        manifest_pins=pins,
        requested_fields=("planet.orbital_period",),
        authority=CrossmatchDataArtifactAuthority(
            left_acquisition=crossmatch_input.left,
            right_acquisition=crossmatch_input.right,
            crossmatch_result=result,
            document_observations=(),
        ),
        mapping_rule_set=mapping,
        conversion_catalog=CATALOG,
        producer_version=mapping.producer_version,
        quality_constraints_reference="research_contract.quality_constraints.fixture",
        input_hash="sha256:" + "0" * 64,
    )
    payload = unhashed.model_dump(mode="json")
    payload["input_hash"] = compute_data_artifact_input_hash(unhashed)
    return DataArtifactBuildInput.model_validate(payload)


def _paired_row(dataset):
    return next(
        row
        for row in dataset.rows
        if isinstance(row.row_authority, CrossmatchRowAuthority)
        and row.row_authority.alignment_status.value == "accepted"
    )


def test_structured_source_wins_and_document_conflict_is_retained() -> None:
    baseline = _structured_orbital_baseline()
    without_documents = build_data_artifact_candidates(baseline)
    row = next(
        item
        for item in without_documents.dataset.rows
        if any(
            field.canonical_field_id == "planet.orbital_period" for field in item.fields
        )
    )
    outcome = next(
        item
        for item in row.fields
        if item.canonical_field_id == "planet.orbital_period"
    )
    assert isinstance(outcome, MappedCanonicalValue)
    structured_value = outcome.canonical_value
    document_value = str(Decimal(structured_value) * 2)

    documents = [
        _observation(
            index=0,
            field_id="planet.orbital_period",
            logical_key=row.row_authority.logical_key,
            scalar=document_value,
            unit="day",
        )
    ]
    result = build_data_artifact_candidates(_with_documents(baseline, documents))
    merged = next(
        field
        for row in result.dataset.rows
        for field in row.fields
        if field.canonical_field_id == "planet.orbital_period"
    )
    assert isinstance(merged, MappedCanonicalValue)
    selected = result.dataset.source_values[
        [
            index
            for index, item in enumerate(result.dataset.source_values)
            if item.source_value_id == merged.selected_source_value_id
        ][0]
    ]
    assert isinstance(selected.origin.kind, str) and selected.origin.kind == (
        "structured_database"
    )
    assert selected.canonical_value == structured_value
    document_values = [
        item
        for item in result.dataset.source_values
        if getattr(item.origin, "kind", "") == "document_research_input"
    ]
    assert document_values and any(
        item.source_snapshot_id == documents[0].pipeline_source_snapshot.snapshot_id
        for item in document_values
    )
    assert merged.conflict_ids, "structured/document disagreement must be retained"


def test_document_fills_structured_missing_value() -> None:
    baseline = build_input("planet.mass", "star.effective_temperature")
    without_documents = build_data_artifact_candidates(baseline)
    row = next(
        item
        for item in without_documents.dataset.rows
        if any(
            isinstance(field, DeclaredNullValue)
            and field.reason.value == "not_in_source"
            for field in item.fields
        )
    )
    target = next(
        item
        for item in row.fields
        if isinstance(item, DeclaredNullValue) and item.reason.value == "not_in_source"
    )
    field_id = target.canonical_field_id
    unit = "earth_mass" if field_id == "planet.mass" else "kelvin"
    documents = [
        _observation(
            index=1,
            field_id=field_id,
            logical_key=row.row_authority.logical_key,
            scalar="1.5" if unit == "earth_mass" else "5600",
            unit=unit,
        )
    ]
    result = build_data_artifact_candidates(_with_documents(baseline, documents))
    merged = next(
        field
        for row in result.dataset.rows
        for field in row.fields
        if field.canonical_field_id == field_id
    )
    assert isinstance(merged, MappedCanonicalValue)
    assert merged.selected_source_value_id is not None
    winner = next(
        item
        for item in result.dataset.source_values
        if item.source_value_id == merged.selected_source_value_id
    )
    assert winner.origin.kind == "document_research_input"


def _document_pair(field_id: str, unit: str, scalars: list[str]):
    baseline = build_input(field_id)
    without_documents = build_data_artifact_candidates(baseline)
    row = next(
        item
        for item in without_documents.dataset.rows
        if any(field.canonical_field_id == field_id for field in item.fields)
    )
    documents = [
        _observation(
            index=index + 10,
            field_id=field_id,
            logical_key=row.row_authority.logical_key,
            scalar=value,
            unit=unit,
        )
        for index, value in enumerate(scalars)
    ]
    return baseline, documents


def test_equal_document_values_form_consensus_without_winner() -> None:
    baseline, documents = _document_pair("planet.mass", "earth_mass", ["1.5", "1.50"])
    result = build_data_artifact_candidates(_with_documents(baseline, documents))
    merged = next(
        field
        for row in result.dataset.rows
        for field in row.fields
        if field.canonical_field_id == "planet.mass"
    )
    assert isinstance(merged, MappedCanonicalValue)
    assert merged.selected_source_value_id is None
    assert merged.canonical_value == "1.5"
    assert not merged.conflict_ids
    selection = next(
        item
        for item in result.dataset.selections
        if item.selection_id == merged.selection_id
    )
    assert selection.selected_source_value_id is None
    assert selection.reason.startswith("equal admitted document values")


def test_conflicting_documents_without_structured_value_stay_unresolved() -> None:
    baseline, documents = _document_pair("planet.mass", "earth_mass", ["1.5", "2.5"])
    result = build_data_artifact_candidates(_with_documents(baseline, documents))
    unresolved = next(
        field
        for row in result.dataset.rows
        for field in row.fields
        if field.canonical_field_id == "planet.mass"
    )
    assert isinstance(unresolved, UnresolvedCanonicalValue)
    assert unresolved.conflict_ids
    conflict = next(
        item
        for item in result.dataset.conflicts
        if item.conflict_id == unresolved.conflict_ids[0]
    )
    assert conflict.source_value_ids == tuple(
        sorted(unresolved.candidate_source_value_ids)
    )


# ---------------------------------------------------------------------------
# Quality observation mapping and denominator regression
# ---------------------------------------------------------------------------


def _quality_contract(*requested: str) -> ResearchContract:
    payload = dict(
        research_goal="Integrate admitted document observations into datasets",
        target_objects=["exoplanet_candidate", "host_star"],
        data_requirements={
            "unit_policy": "canonical",
            "document_source_policy": "research_input",
        },
        requested_fields=list(requested),
        source_scope={"allowed_sources": ["nasa_exoplanet_archive", "esa_gaia_dr3"]},
        paper_search_scope={"max_candidates": 20},
        output_requirements=["dataset"],
        evidence_requirements={},
        quality_constraints={},
    )
    contract_input = ResearchContractInput.model_validate(payload)
    return ResearchContract(
        id="rc-document-test",
        project_id="proj-document-test",
        version=1,
        created_from_draft_id="rcd-document-test",
        created_at=NOW,
        content_hash=compute_research_contract_content_hash(contract_input),
        **payload,
    )


def _evaluate(baseline: DataArtifactBuildInput, contract: ResearchContract):
    build_result = build_data_artifact_candidates(baseline)
    quality_payload = {
        "data_artifact_input": baseline,
        "dataset_candidate": build_result.dataset,
        "field_dictionary_candidate": build_result.field_dictionary,
        "source_collection_candidate": build_result.source_collection,
        "research_contract": contract,
        "quality_rule_set": load_frozen_quality_rule_set(),
    }
    unhashed = DataQualityEvaluationInput.model_construct(
        **quality_payload,
        input_hash="sha256:" + "0" * 64,
    )
    quality_payload["input_hash"] = compute_data_quality_input_hash(unhashed)
    evaluation = evaluate_data_quality(
        DataQualityEvaluationInput.model_validate(quality_payload)
    )
    assert isinstance(evaluation, DataQualityEvaluationResult)
    return build_result, evaluation


def test_document_sources_never_change_structured_denominator() -> None:
    contract = _quality_contract("planet.mass")
    baseline = build_input("planet.mass")
    _, plain = _evaluate(baseline, contract)
    _, with_documents = _evaluate(
        _with_documents(
            baseline,
            [
                _observation(
                    index=21,
                    field_id="planet.mass",
                    logical_key=next(
                        row.row_authority.logical_key
                        for row in build_data_artifact_candidates(baseline).dataset.rows
                        if any(
                            field.canonical_field_id == "planet.mass"
                            for field in row.fields
                        )
                    ),
                    scalar="1.5",
                    unit="earth_mass",
                )
            ],
        ),
        contract,
    )

    def scope(result):
        metric = result.dataset_result.source_scope_completeness
        return (metric.numerator, metric.denominator)

    assert scope(plain)[1] == 2
    assert scope(plain) == scope(with_documents)
    assert with_documents.document_parse_observation.status is (
        DocumentParseQualityStatus.complete
    )
    assert plain.document_parse_observation.status is (
        DocumentParseQualityStatus.not_applicable
    )


def test_partial_and_unsupported_parse_observations_map_independently() -> None:
    from app.schemas.data_quality import DocumentParseQualityObservation

    partial = DocumentParseQualityObservation(
        status=DocumentParseQualityStatus.partial,
        research_input_ids=(str(INPUT_ID),),
        document_parse_ids=(str(PARSE_ID),),
    )
    unsupported = DocumentParseQualityObservation(
        status=DocumentParseQualityStatus.unsupported,
        research_input_ids=(str(INPUT_ID),),
        document_parse_ids=(str(PARSE_ID),),
    )
    assert partial.status is DocumentParseQualityStatus.partial
    assert unsupported.status is DocumentParseQualityStatus.unsupported
    with pytest.raises(ValidationError):
        DocumentParseQualityObservation(
            status=DocumentParseQualityStatus.not_applicable,
            research_input_ids=(str(INPUT_ID),),
        )


# ---------------------------------------------------------------------------
# Real PostgreSQL provenance closure
# ---------------------------------------------------------------------------

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


@pytest.fixture(scope="module")
def postgres_engine():
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL is not configured")
    from db_bootstrap import reset_current_schema
    from app.db.session import create_engine_from_url

    assert "test" in TEST_DATABASE_URL.rsplit("/", 1)[-1].lower(), (
        "refusing non-test database"
    )
    reset_current_schema(TEST_DATABASE_URL)
    engine = create_engine_from_url(TEST_DATABASE_URL)
    yield engine
    engine.dispose()
    reset_current_schema(TEST_DATABASE_URL)


def test_postgres_document_provenance_closes_on_persisted_snapshot(
    postgres_engine,
) -> None:
    from sqlalchemy import select

    from app.db.models import (
        ArtifactVersionModel,
        DocumentParseModel,
        EvidenceModel,
        ProducerExecutionModel,
        ResearchInputBindingModel,
        ResearchInputContentModel,
        ResearchInputModel,
        ResearchArtifactModel,
        ResearchRunModel,
        RunStepModel,
        SourceSnapshotModel,
        StepAttemptModel,
    )
    from app.db.session import session_factory
    from app.services.document_data_admission import (
        DocumentDataAdmissionService,
        DocumentParseSelectionAmbiguousError,
    )
    from app.services.document_parse_store import (
        DocumentParseRepository,
        DocumentParseService,
        PersistDocumentParseRequest,
        validate_document_locator,
    )
    from app.services.artifacts import ArtifactReadService
    from app.services.data_artifacts import DataArtifactReadService
    from app.workflow.publisher import ArtifactPublisher
    from app.workflow.step_publication import RunStepContext, StepPublicationFactory
    from app.workflow.store import PersistentWorkflowStore
    from authoring_test_support import (
        build_contract_draft,
        build_research_contract as build_contract_model,
        build_research_project,
        persist_authoring_models,
    )

    factory = session_factory(postgres_engine)
    ids = {
        name: uuid4()
        for name in (
            "project",
            "contract",
            "run",
            "run_b",
            "step",
            "attempt",
            "producer",
            "input",
            "input_b",
            "draft",
            "cleaning_step",
            "artifact",
        )
    }
    import pathlib
    import tempfile

    tmp = pathlib.Path(tempfile.mkdtemp(prefix="doc-admission-cas-"))
    storage = LocalContentStorage(tmp / "cas")
    pdf_bytes = b"%PDF-1.7\nadmission fixture\n"
    pdf_hash = sha256_content_hash(pdf_bytes)
    storage_ref = asyncio.run(storage.store(pdf_bytes, pdf_hash))

    project = build_research_project(
        project_id=ids["project"],
        session_id="owner",
        name="document admission",
        case_key="exoplanet_host_star",
        created_at=NOW,
        updated_at=NOW,
    )
    draft = build_contract_draft(
        project, draft_id=ids["draft"], created_at=NOW, updated_at=NOW
    )
    contract_payload = {
        "research_goal": "Integrate admitted document observations into datasets",
        "target_objects": ["exoplanet_candidate", "host_star"],
        "data_requirements": {
            "unit_policy": "canonical",
            "document_source_policy": "research_input",
        },
        "requested_fields": list(REQUESTED_FIELDS),
        "source_scope": {
            "allowed_sources": ["nasa_exoplanet_archive", "esa_gaia_dr3"]
        },
        "paper_search_scope": {"max_candidates": 20},
        "output_requirements": ["dataset"],
        "evidence_requirements": {},
        "quality_constraints": {},
    }
    contract_content_hash = compute_research_contract_content_hash(contract_payload)
    contract_model = build_contract_model(
        project,
        draft,
        contract_id=ids["contract"],
        content_hash=contract_content_hash,
        content=contract_payload,
        created_at=NOW,
    )
    with factory() as session, session.begin():
        persist_authoring_models(
            session, project=project, draft=draft, contract=contract_model
        )
    with factory() as session, session.begin():
        session.add_all(
            [
                ResearchRunModel(
                    id=ids["run"],
                    project_id=ids["project"],
                    contract_id=ids["contract"],
                    execution_mode="live",
                    status="cleaning_data",
                    progress=50,
                    derivation_kind="original",
                    cache_policy="disabled",
                    latest_event_sequence=0,
                    revision=1,
                    idempotency_key=f"run-{ids['run']}",
                    request_hash="sha256:" + "b" * 64,
                ),
                ResearchRunModel(
                    id=ids["run_b"],
                    project_id=ids["project"],
                    contract_id=ids["contract"],
                    execution_mode="live",
                    status="completed",
                    progress=100,
                    derivation_kind="original",
                    cache_policy="disabled",
                    latest_event_sequence=0,
                    revision=1,
                    idempotency_key=f"run-{ids['run_b']}",
                    request_hash="sha256:" + "c" * 64,
                ),
            ]
        )
    with factory() as session, session.begin():
        step = RunStepModel(
            id=ids["step"],
            run_id=ids["run"],
            position=0,
            key="parse_document",
            label="Parse document",
            enter_status="planning",
            success_status="fetching_data",
            max_attempts=1,
            status="completed",
            progress=100,
        )
        cleaning_step = RunStepModel(
            id=ids["cleaning_step"],
            run_id=ids["run"],
            position=1,
            key="cleaning_data",
            label="Clean data",
            enter_status="cleaning_data",
            success_status="completed",
            max_attempts=1,
            status="pending",
            progress=0,
        )
        attempt = StepAttemptModel(
            id=ids["attempt"],
            run_step_id=ids["step"],
            attempt_number=1,
            idempotency_key="parse-attempt",
            status="completed",
            retryable=False,
            started_at=NOW,
            finished_at=NOW,
        )
        content = ResearchInputContentModel(
            project_id=ids["project"],
            content_hash=pdf_hash,
            storage_ref=storage_ref,
            mime_type="application/pdf",
            size_bytes=len(pdf_bytes),
            created_at=NOW,
        )
        session.add_all([step, cleaning_step, attempt, content])
    with factory() as session, session.begin():
        input_row = ResearchInputModel(
            id=ids["input"],
            session_id="owner",
            project_id=ids["project"],
            type="pdf",
            source_type="upload",
            content_hash=pdf_hash,
            filename="paper.pdf",
            status="accepted",
            source_snapshot_id=None,
            created_at=NOW,
        )
        producer = ProducerExecutionModel(
            id=ids["producer"],
            run_id=ids["run"],
            run_step_id=ids["step"],
            step_attempt_id=ids["attempt"],
            step_key="parse_document",
            idempotency_key="parse-producer",
            lease_generation=1,
            producer_type="algorithm",
            producer_name="hybrid-document-parser",
            producer_version="1.0.0",
            parameters={"profile": "native-default"},
            parameters_hash=compute_canonical_payload_hash(
                {"profile": "native-default"}
            ),
            input_hash=PARSE_INPUT_HASH,
            output_hash=CANONICAL_OUTPUT_HASH,
            status="completed",
            started_at=NOW,
            finished_at=NOW,
            latency_ms=12,
        )
        input_b_row = ResearchInputModel(
            id=ids["input_b"],
            session_id="owner",
            project_id=ids["project"],
            type="pdf",
            source_type="upload",
            content_hash=pdf_hash,
            filename="paper-b.pdf",
            status="accepted",
            source_snapshot_id=None,
            created_at=NOW,
        )
        session.add_all([input_row, input_b_row, producer])
    with factory() as session, session.begin():
        session.add_all(
            [
                ResearchInputBindingModel(
                    input_id=ids["input"],
                    project_id=ids["project"],
                    contract_draft_id=ids["draft"],
                    bound_at=NOW,
                ),
                ResearchInputBindingModel(
                    input_id=ids["input_b"],
                    project_id=ids["project"],
                    run_id=ids["run_b"],
                    bound_at=NOW,
                ),
                ResearchArtifactModel(
                    id=ids["artifact"],
                    project_id=ids["project"],
                    kind="dataset",
                    title="Document admission dataset",
                    logical_key=f"dataset.document-{ids['artifact']}",
                    created_at=NOW,
                ),
            ]
        )

    repository = DocumentParseRepository(factory)
    service = DocumentParseService(repository, storage)
    parse = _parse(
        [
            (
                next(
                    value.normalized_value
                    for candidate in align_cross_source_records(
                        _scenario_input(
                            next(
                                item
                                for item in load_crossmatch_benchmark().scenarios
                                if item.scenario_id == "exact_one_to_one"
                            )
                        )
                    ).candidates
                    if candidate.entity_level.value == "host_star"
                    for value in candidate.identity_values
                    if value.field_id == "star.tic_id"
                ),
                "5600 ± 50 K",
                "1.20",
            )
        ]
    )
    table = parse.tables[0]
    body_row = list(table.rows[1])
    for column, (x1, x2) in enumerate(((20, 100), (110, 220), (230, 330))):
        body_row[column] = body_row[column].model_copy(
            update={"bbox": DocumentBBox(x1=x1, y1=30, x2=x2, y2=45)}
        )
    parse = parse.model_copy(
        update={
            "tables": (
                table.model_copy(update={"rows": (table.rows[0], tuple(body_row))}),
            )
        }
    )
    # The persisted parse must bind the seeded ResearchInput identity and its
    # immutable uploaded content identity.
    parse = parse.model_copy(
        update={
            "research_input_id": str(ids["input"]),
            "content_hash": pdf_hash,
        }
    )
    record = asyncio.run(
        service.persist(
            PersistDocumentParseRequest(
                project_id=ids["project"],
                run_id=ids["run"],
                run_step_id=ids["step"],
                producer_execution_id=ids["producer"],
                parse_input_hash=PARSE_INPUT_HASH,
                candidate=parse,
            )
        )
    )

    contract = ResearchContract(
        id="rc-" + str(ids["contract"]),
        project_id=str(ids["project"]),
        version=1,
        created_from_draft_id=str(ids["draft"]),
        created_at=NOW,
        content_hash=contract_content_hash,
        **contract_payload,
    )

    admission = DocumentDataAdmissionService(
        factory=factory,
        document_parses=service,
        manifests=BUNDLE,
    )
    crossmatch = align_cross_source_records(
        _scenario_input(
            next(
                item
                for item in load_crossmatch_benchmark().scenarios
                if item.scenario_id == "exact_one_to_one"
            )
        )
    )
    plan = asyncio.run(
        admission.prepare(
            project_id=ids["project"],
            run_id=ids["run"],
            contract=contract,
            crossmatch=crossmatch,
        )
    )
    assert plan is not None
    assert {item.research_input_id for item in plan.prepared_inputs} == {ids["input"]}

    from dataclasses import replace

    from app.workflow.publisher import admit_artifact_candidate
    from services.data_pipeline.data_artifacts.admission import (
        validate_data_artifact_domain,
        validate_data_artifact_evidence,
    )
    from services.data_pipeline.data_artifacts.pipeline import (
        build_data_artifact_candidates,
    )
    from services.data_pipeline.data_artifacts.projection import (
        derive_document_snapshot_bindings,
    )
    from services.data_pipeline.data_quality import (
        admit_data_artifact_quality,
        build_data_quality_publication_validator,
        evaluate_data_quality,
    )
    from services.data_pipeline.data_quality.policy import load_frozen_quality_rule_set

    workflow = PersistentWorkflowStore(factory)
    lease = workflow.acquire_lease(
        ids["run"],
        owner="document-admission-e2e",
        lease_duration=timedelta(minutes=5),
        expected_status="cleaning_data",
        expected_revision=1,
    )
    attempt = workflow.begin_step(
        ids["run"],
        step_key="cleaning_data",
        attempt_idempotency_key="document-admission-cleaning-attempt",
        token=lease.token,
        generation=lease.generation,
        expected_status="cleaning_data",
        expected_revision=lease.revision,
        public_message="Admit document observations and publish the Dataset",
    )
    context = RunStepContext(
        run_id=ids["run"],
        project_id=ids["project"],
        session_id="owner",
        contract=contract,
        artifacts={"dataset": ids["artifact"]},
        versions={},
    )
    publications = StepPublicationFactory(factory=factory)
    document_execution = publications.start_producer(
        context,
        step_key="cleaning_data",
        operation_key="data_artifact:document_observations",
        producer_type="algorithm",
        producer_name=plan.producer_name,
        producer_version=plan.producer_version,
        input_hash=plan.producer_input_hash,
        parameters=plan.producer_parameters,
        attempt=attempt,
        lease=lease,
    )
    batch = admission.execute(plan)
    publications.finish_producer(
        document_execution.id,
        status="completed",
        output_hash=batch.producer_output_hash,
    )
    assert batch.accepted, "seeded table must admit at least one observation"

    # The application batch exposes a stable rejected-region summary rather
    # than silently dropping an unsupported table.
    unsupported_payload = plan.prepared_inputs[0].candidate.model_dump(mode="json")
    unsupported_table = dict(unsupported_payload["tables"][0])
    unsupported_table["quality"] = DocumentParseQuality.unsupported.value
    unsupported_table["rows"] = []
    unsupported_payload["tables"] = [unsupported_table]
    validated_candidate = DocumentParseCandidate.model_validate(unsupported_payload)
    assert validated_candidate.tables[0].quality is DocumentParseQuality.unsupported
    assert validated_candidate.tables[0].rows == ()
    unsupported_plan = replace(
        plan,
        prepared_inputs=(
            replace(plan.prepared_inputs[0], candidate=validated_candidate),
        ),
    )
    unsupported_batch = admission.execute(unsupported_plan)
    unsupported_regions = unsupported_batch.producer_output_summary[
        "unsupported_regions"
    ]
    assert len(unsupported_regions) == 1
    assert unsupported_regions[0]["status"] == "rejected"
    assert unsupported_regions[0]["code"] == "DOCUMENT_PARSE_UNSUPPORTED"
    assert unsupported_regions[0]["raw_candidate_id"].startswith(
        "document.parse.unsupported."
    )
    assert unsupported_batch.raw_candidates == ()
    assert unsupported_batch.accepted == ()
    assert admission.execute(unsupported_plan).producer_output_summary[
        "unsupported_regions"
    ] == unsupported_regions

    # The single persisted upload SourceSnapshot is reused, never duplicated.
    bindings = {
        item.pipeline_snapshot_id: str(item.persisted_source_snapshot_id)
        for item in batch.accepted
    }
    assert len(bindings) == 1
    persisted_binding = next(iter(bindings.values()))
    assert UUID(persisted_binding) == record.source_snapshot_id
    with factory() as session:
        rows = tuple(
            session.scalars(
                select(SourceSnapshotModel).where(
                    SourceSnapshotModel.project_id == ids["project"],
                    SourceSnapshotModel.source_id == f"research_input:{ids['input']}",
                )
            )
        )
    assert len(rows) == 1
    assert str(rows[0].id) == persisted_binding

    # Locator closure against the persisted canonical parse.
    stored_parse = asyncio.run(
        service.get_candidate(project_id=ids["project"], document_parse_id=record.id)
    )
    for observation in batch.accepted:
        validate_document_locator(stored_parse, observation.document_locator)

    # Determinism of the persisted-provenance producer identities.
    again_plan = asyncio.run(
        admission.prepare(
            project_id=ids["project"],
            run_id=ids["run"],
            contract=contract,
            crossmatch=crossmatch,
        )
    )
    assert again_plan is not None
    again = admission.execute(again_plan)
    assert again_plan.producer_input_hash == plan.producer_input_hash
    assert again.producer_input_hash == batch.producer_input_hash
    assert again.producer_output_hash == batch.producer_output_hash

    data_input = _with_documents(build_input(*REQUESTED_FIELDS), batch.accepted)
    data_execution = publications.start_producer(
        context,
        step_key="cleaning_data",
        operation_key="data_artifact:dataset",
        producer_type="algorithm",
        producer_name="data-artifact-dataset",
        producer_version=data_input.producer_version,
        input_hash=data_input.input_hash,
        parameters={},
        attempt=attempt,
        lease=lease,
    )
    build_result = build_data_artifact_candidates(data_input)
    quality_payload = {
        "data_artifact_input": data_input,
        "dataset_candidate": build_result.dataset,
        "field_dictionary_candidate": build_result.field_dictionary,
        "source_collection_candidate": build_result.source_collection,
        "research_contract": contract,
        "quality_rule_set": load_frozen_quality_rule_set(),
    }
    quality_unhashed = DataQualityEvaluationInput.model_construct(
        **quality_payload,
        input_hash="sha256:" + "0" * 64,
    )
    quality_payload["input_hash"] = compute_data_quality_input_hash(quality_unhashed)
    quality_input = DataQualityEvaluationInput.model_validate(quality_payload)
    quality_result = evaluate_data_quality(quality_input)
    assert isinstance(quality_result, DataQualityEvaluationResult)
    assert quality_result.contract_gate.overall_status.value == "pass"
    quality_checks = {
        item.observation_key: item.result.value
        for item in quality_result.contract_gate.checks
    }
    assert quality_checks["candidate.source_scope_allowed"] == "pass"
    assert quality_checks["candidate.document_source_authorized"] == "pass"
    quality_admission = admit_data_artifact_quality(
        build_result=build_result,
        evaluation_input=quality_input,
        evaluation_result=quality_result,
    )

    assert isinstance(data_input.authority, CrossmatchDataArtifactAuthority)
    publications.ensure_source_snapshots(
        context,
        (
            data_input.authority.left_acquisition.snapshot,
            data_input.authority.right_acquisition.snapshot,
        ),
    )
    document_snapshot_bindings = derive_document_snapshot_bindings(data_input)
    source_bindings, evidence_bindings = publications.data_bindings(
        context,
        kind="dataset",
        candidate=build_result.dataset,
        snapshot_bindings_override=document_snapshot_bindings,
    )
    admitted = admit_artifact_candidate(
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
        source_snapshot_bindings=source_bindings,
        evidence_bindings=evidence_bindings,
    )
    publications.finish_producer(
        data_execution.id,
        status="completed",
        input_hash=data_input.input_hash,
        output_hash=admitted.content_hash,
    )
    publication = publications.publication(
        context,
        kind="dataset",
        candidate=admitted,
        producer_execution_id=data_execution.id,
        artifact_id=ids["artifact"],
    )
    published = ArtifactPublisher(factory).publish_step_outputs(
        ids["run"],
        step_key="cleaning_data",
        attempt_id=attempt.attempt_id,
        token=lease.token,
        generation=lease.generation,
        expected_status=attempt.run_status,
        expected_revision=attempt.run_revision,
        publications=(publication,),
        public_message="Document-backed Dataset published with quality and provenance",
    )
    assert published.status == "completed"
    assert len(published.versions) == 1
    version_id = published.versions[0].id

    with factory() as session:
        document_execution_row = session.get(
            ProducerExecutionModel, document_execution.id
        )
        data_execution_row = session.get(ProducerExecutionModel, data_execution.id)
        assert document_execution_row is not None
        assert document_execution_row.status == "completed"
        assert document_execution_row.producer_name == plan.producer_name
        assert document_execution_row.producer_version == plan.producer_version
        assert document_execution_row.input_hash == plan.producer_input_hash
        assert document_execution_row.output_hash == batch.producer_output_hash
        assert data_execution_row is not None
        assert data_execution_row.status == "completed"
        assert data_execution_row.input_hash == data_input.input_hash
        assert data_execution_row.output_hash == admitted.content_hash

        version_row = session.get(ArtifactVersionModel, version_id)
        assert version_row is not None
        assert version_row.artifact_id == ids["artifact"]
        assert version_row.source_mode == "live"
        assert set(version_row.source_snapshot_ids) == set(
            str(item) for item in admitted.source_snapshot_ids
        )
        assert str(record.source_snapshot_id) in version_row.source_snapshot_ids
        assert f"research-input.{ids['input']}" not in version_row.source_snapshot_ids
        evidence_rows = tuple(
            session.scalars(
                select(EvidenceModel).where(
                    EvidenceModel.artifact_version_id == version_id,
                    EvidenceModel.project_id == ids["project"],
                )
            )
        )
        document_evidence = next(
            item
            for item in evidence_rows
            if item.locator.get("kind") == "document_observation"
        )
        assert document_evidence.source_snapshot_id == record.source_snapshot_id
        assert document_evidence.locator["research_input_id"] == str(ids["input"])
        assert document_evidence.locator["document_parse_id"] == str(record.id)
        assert document_evidence.locator["raw_candidate_id"]
        document_locator = document_evidence.locator["document_locator"]
        assert document_locator["page_index"] == 0
        assert document_locator["block_id"] == "doc-table-block"
        assert document_locator["table_id"] == "observations-table"
        assert document_locator["cell_id"] in {"c-1-1", "c-1-2"}
        assert document_locator["bbox"] in (
            {"x1": 110.0, "y1": 30.0, "x2": 220.0, "y2": 45.0},
            {"x1": 230.0, "y1": 30.0, "x2": 330.0, "y2": 45.0},
        )
        snapshots = tuple(
            session.scalars(
                select(SourceSnapshotModel).where(
                    SourceSnapshotModel.project_id == ids["project"],
                )
            )
        )
        assert {item.source_id for item in snapshots} == {
            str(data_input.authority.left_acquisition.snapshot.source_id),
            str(data_input.authority.right_acquisition.snapshot.source_id),
            f"research_input:{ids['input']}",
        }
        assert len(snapshots) == 3

    artifact_reads = ArtifactReadService(factory)
    dataset_reads = DataArtifactReadService(artifact_reads)
    version_read = artifact_reads.get_version(
        version_id=str(version_id), session_id="owner", full_content=True
    )
    data_read = dataset_reads.get_dataset(
        version_id=str(version_id), session_id="owner"
    )
    upload_snapshot = next(
        item
        for item in data_read.source_snapshots
        if item.source_id == f"research_input:{ids['input']}"
    )
    assert upload_snapshot.source_type == "research_input_upload"
    assert upload_snapshot.query == {"research_input_id": str(ids["input"])}
    assert upload_snapshot.query_hash == compute_canonical_payload_hash(
        upload_snapshot.query
    )
    assert upload_snapshot.content_hash == pdf_hash
    assert upload_snapshot.license_note == "user-provided upload"
    assert upload_snapshot.source_version_or_etag is None
    assert upload_snapshot.cache_version is None
    assert upload_snapshot.request_metadata["ingestion_source"] == "upload"
    assert data_read.quality_projection.overall_status == "pass"
    assert version_read.source_snapshot_ids == tuple(
        item.id for item in data_read.source_snapshots
    )

    document_value = next(
        item
        for item in data_read.dataset.source_values
        if item.origin.kind == "document_research_input"
    )
    source_observation = next(
        item
        for item in batch.accepted
        if item.raw_candidate_id == document_value.origin.raw_candidate_id
    )
    assert document_value.source_snapshot_id == f"research-input.{ids['input']}"
    assert document_value.raw_value == source_observation.raw_value
    assert document_value.source_unit == source_observation.source_unit
    assert source_observation.parsed_scalar is not None
    assert document_value.origin.research_input_id == str(ids["input"])
    assert document_value.origin.document_parse_id == str(record.id)
    assert document_value.origin.raw_candidate_id == source_observation.raw_candidate_id
    assert document_value.evidence_locator.kind == "document_observation"
    assert document_value.evidence_locator.research_input_id == str(ids["input"])
    assert document_value.evidence_locator.document_parse_id == str(record.id)
    assert document_value.evidence_locator.document_locator.page_index == 0
    assert document_value.evidence_locator.document_locator.table_id == (
        "observations-table"
    )
    assert document_value.evidence_locator.document_locator.cell_id in {
        "c-1-1",
        "c-1-2",
    }
    assert document_value.evidence_locator.document_locator.bbox is not None
    transformation = next(
        item
        for item in data_read.dataset.transformation_evidence
        if item.source_value_id == document_value.source_value_id
    )
    assert transformation.locator == document_value.evidence_locator
    assert transformation.source_unit == document_value.source_unit
    assert transformation.canonical_unit == document_value.canonical_unit
    assert transformation.conversion_rule_id == document_value.conversion_rule_id

    with factory() as session, session.begin():
        stored_row = session.get(DocumentParseModel, record.id)
        assert stored_row is not None
        session.add(
            DocumentParseModel(
                id=uuid4(),
                project_id=stored_row.project_id,
                research_input_id=stored_row.research_input_id,
                source_snapshot_id=stored_row.source_snapshot_id,
                created_by_run_id=stored_row.created_by_run_id,
                run_step_id=stored_row.run_step_id,
                producer_execution_id=stored_row.producer_execution_id,
                candidate_parse_id=f"{stored_row.candidate_parse_id}.duplicate",
                identity_hash=compute_canonical_payload_hash(
                    {"duplicate_of": str(stored_row.id)}
                ),
                schema_version=stored_row.schema_version,
                schema_hash=stored_row.schema_hash,
                input_content_hash=stored_row.input_content_hash,
                parse_input_hash=stored_row.parse_input_hash,
                canonical_output_hash=stored_row.canonical_output_hash,
                payload_content_hash=stored_row.payload_content_hash,
                payload_semantic_hash=stored_row.payload_semantic_hash,
                payload_storage_ref=stored_row.payload_storage_ref,
                parser_profile_id=stored_row.parser_profile_id,
                parser_profile_version=stored_row.parser_profile_version,
                native_engine=stored_row.native_engine,
                native_engine_version=stored_row.native_engine_version,
                visual_engine=stored_row.visual_engine,
                visual_engine_version=stored_row.visual_engine_version,
                visual_model_id=stored_row.visual_model_id,
                visual_model_revision=stored_row.visual_model_revision,
                config_hash=stored_row.config_hash,
                overall_quality=stored_row.overall_quality,
                candidate_created_at=stored_row.candidate_created_at,
            )
        )

    with pytest.raises(DocumentParseSelectionAmbiguousError) as error:
        asyncio.run(
            admission.prepare(
                project_id=ids["project"],
                run_id=ids["run"],
                contract=contract,
                crossmatch=crossmatch,
            )
        )
    assert error.value.code == "DOCUMENT_PARSE_SELECTION_AMBIGUOUS"
