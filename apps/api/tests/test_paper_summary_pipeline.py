from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import shutil

import pytest
from pydantic import ValidationError

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.artifact_publication import canonical_artifact_content_payload
from app.schemas.enums import PaperDataLevel, SourceMode
from app.schemas.evidence import SourceSnapshotRecord
from app.schemas.paper_collection import PaperCollection, PaperSourcePage
from app.schemas.paper_summary import (
    PaperSummaryBenchmarkEvaluationCase,
    PaperSummaryArtifactContent,
    PaperSummaryEvidenceCandidate,
    PaperSummaryEvidenceLocator,
    PaperSummaryModelOutput,
    PaperSummaryPaperMetadata,
    PaperSummarySourceSnapshotReference,
    PaperSummarySupportStatus,
)
from app.schemas.scientific_document import DocumentParseInput
from app.services.scientific_document.parser import ScientificDocumentParser
from app.schemas.core import ArtifactVersion
from app.workflow.publisher import PublicationAdmissionError, admit_artifact_candidate
from packages.prompts.registry import (
    PromptRegistry,
    PromptRegistryError,
    compute_prompt_content_hash,
)
from services.paper_pipeline.benchmark import load_frozen_benchmark
from services.paper_pipeline.constants import (
    SUMMARY_PARAMETERS_VERSION,
    SUMMARY_PRODUCER_NAME,
    SUMMARY_PRODUCER_VERSION,
)
from services.paper_pipeline.benchmark_runner import PaperCollectionBenchmarkRunner
from services.paper_pipeline.sources.base import (
    RawSourceRecord,
    SourceSearchResult,
)
from services.paper_pipeline.summary import (
    PaperSummaryPipeline,
    build_document_evidence_candidates,
)
from services.paper_pipeline.summary_benchmark import evaluate_paper_summaries


FIXED_TIME = datetime(2026, 7, 26, 8, 30, tzinfo=timezone.utc)
ROOT = Path(__file__).parents[3]
SAFE_PARAMETERS = {
    "temperature": 0,
    "max_output_tokens": 2048,
    "response_format": "json_schema",
}


class SummaryFixtureAdapter:
    source_id = "crossref"
    adapter_name = "paper_summary_fixture"
    adapter_version = "1.0.0"

    def search(self, query, *, source_mode, data_level):  # type: ignore[no-untyped-def]
        record = RawSourceRecord(
            source_id="crossref",
            source_record_id="10.1117/12.2232071",
            title="Transiting Exoplanet Survey Satellite",
            authors=("George R. Ricker",),
            year=2015,
            doi="10.1117/12.2232071",
            arxiv_id="1406.0151",
            url="https://doi.org/10.1117/12.2232071",
        )
        records = (record,)
        response_hash = compute_canonical_payload_hash(
            [item.hash_payload() for item in records]
        )
        page = PaperSourcePage(
            page_number=1,
            offset=0,
            requested_rows=query.pagination.page_size,
            returned_rows=1,
            total_results=1,
            attempt_count=1,
            status_code=200,
            retrieved_at=FIXED_TIME,
            request_hash=compute_canonical_payload_hash(
                {"query_hash": query.query_hash, "page": 1}
            ),
            response_hash=response_hash,
        )
        snapshot = SourceSnapshotRecord(
            snapshot_id="snapshot.crossref.summary_fixture",
            source_id="crossref",
            source_type="paper_metadata",
            retrieved_at=FIXED_TIME,
            query=query.normalized_query_string,
            query_hash=query.query_hash,
            source_version_or_etag="crossref.fixture.2026-07-26",
            content_hash=compute_canonical_payload_hash(
                {"query_hash": query.query_hash, "records": [record.hash_payload()]}
            ),
            license_note="Public bibliographic metadata fixture; no restricted full text.",
            request_metadata={
                "adapter_name": self.adapter_name,
                "data_level": data_level.value,
            },
        )
        return SourceSearchResult(
            records=records,
            pages=(page,),
            snapshot=snapshot,
            retry_count=0,
        )


def _collection() -> PaperCollection:
    return PaperCollectionBenchmarkRunner(
        adapter=SummaryFixtureAdapter(), clock=lambda: FIXED_TIME
    ).run(
        scenario_id="search.tess_mission_and_catalogs",
        source_mode=SourceMode.fixture,
        data_level=PaperDataLevel.fixture,
    )


def _evidence(
    collection: PaperCollection,
    *,
    evidence_id: str = "evidence.summary_fixture",
    quote: str = "TESS targets transits around nearby, bright stars.",
    excerpt: str
    | None = "The abstract states that TESS targets transits around nearby, bright stars.",
    claimed_source_version: str | None = None,
) -> PaperSummaryEvidenceCandidate:
    candidate = collection.candidates[0]
    return PaperSummaryEvidenceCandidate(
        evidence_id=evidence_id,
        paper_id=candidate.canonical_paper_id,
        candidate_id=candidate.candidate_id,
        source_id=candidate.raw.source_id,
        source_record_id=candidate.raw.source_record_id,
        source_snapshot_id=candidate.raw.source_snapshot_id,
        claimed_source_version=claimed_source_version,
        locator=PaperSummaryEvidenceLocator(
            kind="paper_text",
            source_url=candidate.raw.url,
            section="abstract",
            paragraph=1,
            text_range="sentence 1",
        ),
        quote_or_value=quote,
        accessible_excerpt=excerpt,
    )


def _model_output(
    *,
    evidence_id: str = "evidence.summary_fixture",
    limitation_evidence_ids: tuple[str, ...] = (),
) -> str:
    payload = {
        "background": {
            "section_kind": "background",
            "overview": {
                "statement_id": "summary_statement.background",
                "item_kind": "objective",
                "text": "Establish the TESS mission scope for nearby bright stars.",
                "evidence_ids": [evidence_id],
            },
            "items": [],
        },
        "methodology": {
            "section_kind": "methodology",
            "overview": None,
            "items": [],
        },
        "dataset": {
            "section_kind": "dataset",
            "overview": None,
            "items": [],
        },
        "experiments": {
            "section_kind": "experiments",
            "overview": None,
            "items": [
                {
                    "statement_id": "summary_statement.experiment_result",
                    "item_kind": "result",
                    "text": "TESS targets nearby bright stars for transit observations.",
                    "evidence_ids": [evidence_id],
                }
            ],
        },
        "discussion": {
            "section_kind": "discussion",
            "overview": None,
            "items": [],
        },
        "limitations": {
            "section_kind": "limitations",
            "overview": None,
            "items": [
                {
                    "statement_id": "summary_statement.limitation",
                    "item_kind": "limitation",
                    "text": "The provided excerpt does not establish observed mission yield.",
                    "evidence_ids": list(limitation_evidence_ids),
                }
            ],
        },
        "research_questions": {
            "section_kind": "research_questions",
            "overview": None,
            "items": [],
        },
        "evidence_ids": sorted({evidence_id, *limitation_evidence_ids}),
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _admit(
    collection: PaperCollection,
    model_response: str,
    evidence: tuple[PaperSummaryEvidenceCandidate, ...],
):
    return PaperSummaryPipeline(clock=lambda: FIXED_TIME).admit(
        paper_collection=collection,
        paper_collection_version_id="artifact_version.paper_collection.fixture",
        paper_id=collection.selected_paper_ids[0],
        model_response=model_response,
        model_name="qwen.fixture.1",
        parameters=SAFE_PARAMETERS,
        evidence_candidates=evidence,
    )


def _document_summary_fixture():  # type: ignore[no-untyped-def]
    content = (
        "# Transit Search\n\n"
        "We remove flagged cadences before fitting the transit.\n\n"
        "## References\n\n"
        "Reference text must not become summary Evidence.\n"
    ).encode()
    content_hash = "sha256:" + sha256(content).hexdigest()
    parsed = ScientificDocumentParser().parse_document(
        DocumentParseInput(
            research_input_id="research-input.paper-1",
            content_hash=content_hash,
            source_type="upload",
            mime_type="text/markdown",
            filename="transit-search.md",
            input_bytes=content,
        )
    )
    snapshot = PaperSummarySourceSnapshotReference(
        source_snapshot_id="source-snapshot.paper-1",
        source_id="research-input",
        source_version=content_hash,
        content_hash=content_hash,
    )
    paper = PaperSummaryPaperMetadata(
        paper_id="paper.uploaded-transit-search",
        title="Transit Search",
    )
    evidence = build_document_evidence_candidates(
        document_parse=parsed,
        document_parse_id="document-parse.paper-1",
        paper_id=paper.paper_id,
        source_id=snapshot.source_id,
        source_record_id="transit-search.md",
        source_snapshot_id=snapshot.source_snapshot_id,
    )
    return parsed, snapshot, paper, evidence


def test_document_parse_enters_seven_section_summary_with_block_evidence() -> None:
    parsed, snapshot, paper, evidence = _document_summary_fixture()
    paragraph = next(
        item
        for item in evidence
        if item.quote_or_value.startswith("We remove flagged")
    )

    result = PaperSummaryPipeline(clock=lambda: FIXED_TIME).admit_document(
        document_parse=parsed,
        document_parse_id="document-parse.paper-1",
        source_snapshot=snapshot,
        paper=paper,
        model_response=_model_output(evidence_id=paragraph.evidence_id),
        model_name="qwen.fixture.1",
        parameters=SAFE_PARAMETERS,
        evidence_candidates=evidence,
        run_id="run.document-summary",
    )

    assert result.summary is not None
    summary = result.summary
    assert summary.schema_version == "3.0.0"
    assert summary.benchmark is None
    assert summary.input_versions.collection is None
    assert summary.input_versions.document_parses[0].canonical_output_hash == (
        parsed.canonical_output_hash
    )
    admitted = next(
        item for item in summary.evidence if item.evidence_id == paragraph.evidence_id
    )
    assert admitted.status is PaperSummarySupportStatus.supported
    assert admitted.locator.document_locator is not None
    assert admitted.locator.document_locator.block_id is not None
    assert all("Reference text" not in item.quote_or_value for item in evidence)


def test_document_summary_rejects_unpinned_document_locator_as_evidence() -> None:
    parsed, snapshot, paper, evidence = _document_summary_fixture()
    paragraph = evidence[0]
    tampered = paragraph.model_copy(
        update={
            "locator": paragraph.locator.model_copy(
                update={"document_parse_id": "document-parse.other"}
            )
        }
    )
    result = PaperSummaryPipeline(clock=lambda: FIXED_TIME).admit_document(
        document_parse=parsed,
        document_parse_id="document-parse.paper-1",
        source_snapshot=snapshot,
        paper=paper,
        model_response=_model_output(evidence_id=tampered.evidence_id),
        model_name="qwen.fixture.1",
        parameters=SAFE_PARAMETERS,
        evidence_candidates=(tampered,),
    )

    assert result.summary is not None
    assert result.summary.background.overview is not None
    assert result.summary.background.overview.status is (
        PaperSummarySupportStatus.unverifiable
    )
    assert result.summary.evidence == ()


def test_prompt_registry_resolves_one_hash_pinned_current_definition() -> None:
    registry = PromptRegistry()

    current = registry.get("paper_summary")

    assert current.version == "4.0.0"
    assert current.output_models == ("PaperSummaryModelOutput",)
    assert current.content_hash == (
        "sha256:f5dcc7ba26f1eb1525720bbd332bc73d9bd1ab59d4ad066ff7f37df43d498872"
    )


def test_prompt_registry_rejects_in_place_version_mutation(tmp_path: Path) -> None:
    prompt_root = tmp_path / "prompts"
    shutil.copytree(ROOT / "packages" / "prompts", prompt_root)
    prompt_path = prompt_root / "paper_summary" / "prompt.md"
    prompt_path.write_text(
        prompt_path.read_text(encoding="utf-8") + "\nmutated in place\n",
        encoding="utf-8",
    )

    with pytest.raises(PromptRegistryError, match="immutable prompt content changed"):
        PromptRegistry(prompt_root)


@pytest.mark.parametrize(
    ("field", "replacement", "error"),
    [
        ("input_schema_version: 2.0.0\n", "", "front matter fields"),
        (
            "evidence_required: true\n",
            "evidence_required: required\n",
            "prompt contract metadata",
        ),
    ],
)
def test_prompt_registry_rejects_incomplete_contract_metadata(
    tmp_path: Path,
    field: str,
    replacement: str,
    error: str,
) -> None:
    prompt_root = tmp_path / "prompts"
    shutil.copytree(ROOT / "packages" / "prompts", prompt_root)
    prompt_path = prompt_root / "paper_summary" / "prompt.md"
    prompt_content = prompt_path.read_text(encoding="utf-8").replace(
        field,
        replacement,
        1,
    )
    prompt_path.write_text(prompt_content, encoding="utf-8")
    registry_path = prompt_root / "registry.json"
    registry_payload = json.loads(registry_path.read_text(encoding="utf-8"))
    registry_payload["prompts"]["paper_summary"]["content_hash"] = (
        compute_prompt_content_hash(prompt_content)
    )
    registry_path.write_text(
        json.dumps(registry_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(PromptRegistryError, match=error):
        PromptRegistry(prompt_root)


def test_prompt_registry_hash_matches_utf8_lf_file_bytes() -> None:
    record = PromptRegistry().get("paper_summary")
    prompt_bytes = (ROOT / "packages" / "prompts" / record.path).read_bytes()

    assert not prompt_bytes.startswith(b"\xef\xbb\xbf")
    assert b"\r" not in prompt_bytes
    assert f"sha256:{sha256(prompt_bytes).hexdigest()}" == record.content_hash
    assert (
        compute_prompt_content_hash(prompt_bytes.decode("utf-8")) == record.content_hash
    )


def test_model_output_schema_requires_all_core_fields_without_defaults() -> None:
    with pytest.raises(ValidationError):
        PaperSummaryModelOutput.model_validate({"background": {}})


def test_valid_output_becomes_publisher_ready_summary_with_per_item_evidence() -> None:
    collection = _collection()
    evidence = _evidence(collection)

    result = _admit(collection, _model_output(), (evidence,))

    assert result.admission_status == "accepted"
    assert result.summary is not None
    summary = result.summary
    assert summary.kind == "paper_summary"
    assert summary.paper_id == collection.selected_paper_ids[0]
    assert summary.input_versions.collection is not None
    assert summary.input_versions.collection.output_hash == collection.output_hash
    assert summary.input_versions.source_snapshots[0].source_snapshot_id == (
        collection.source_snapshots[0].snapshot_id
    )
    assert summary.experiments.items[0].status is PaperSummarySupportStatus.supported
    assert summary.limitations.items[0].status is PaperSummarySupportStatus.unsupported
    assert summary.limitations.items[0].validation_code == "evidence.not_provided"
    assert summary.evidence[0].locator.text_range == "sentence 1"
    assert summary.evidence[0].quote_or_value == evidence.quote_or_value
    assert (
        summary.evidence[0].source_record_id
        == collection.candidates[0].raw.source_record_id
    )
    assert (
        summary.producer.prompt_hash
        == PromptRegistry().get("paper_summary").content_hash
    )
    assert summary.producer.parameters_hash.startswith("sha256:")
    assert summary.producer.input_versions == summary.input_versions
    assert summary.producer.output_hash == summary.output_hash
    assert summary.model_dump(mode="json")["kind"] == "paper_summary"


def test_same_versioned_input_model_and_parameters_produce_stable_hashes() -> None:
    collection = _collection()
    evidence = _evidence(collection)
    first = _admit(collection, _model_output(), (evidence,))
    second = _admit(collection, _model_output(), (evidence,))

    assert first.summary is not None and second.summary is not None
    assert first.producer.input_hash == second.producer.input_hash
    assert first.producer.model_response_hash == second.producer.model_response_hash
    assert first.summary.output_hash == second.summary.output_hash
    assert first.summary.summary_id == second.summary.summary_id


def test_evidence_candidate_order_does_not_change_summary_hashes() -> None:
    collection = _collection()
    first_evidence = _evidence(collection)
    second_evidence = _evidence(
        collection,
        evidence_id="evidence.summary_fixture_limitation",
    )
    model_response = _model_output(
        limitation_evidence_ids=(second_evidence.evidence_id,)
    )

    first = _admit(collection, model_response, (first_evidence, second_evidence))
    second = _admit(collection, model_response, (second_evidence, first_evidence))

    assert first.summary is not None and second.summary is not None
    assert first.producer.input_hash == second.producer.input_hash
    assert first.summary.output_hash == second.summary.output_hash


def test_hashes_are_key_order_stable_but_change_with_versioned_inputs() -> None:
    collection = _collection()
    evidence = _evidence(collection)
    pipeline = PaperSummaryPipeline(clock=lambda: FIXED_TIME)
    common = {
        "paper_collection": collection,
        "paper_id": collection.selected_paper_ids[0],
        "model_response": _model_output(),
        "model_name": "qwen.fixture.1",
        "evidence_candidates": (evidence,),
    }
    first = pipeline.admit(
        **common,
        paper_collection_version_id="artifact_version.paper_collection.fixture",
        parameters={"temperature": 0, "max_output_tokens": 2048},
    )
    reordered = pipeline.admit(
        **common,
        paper_collection_version_id="artifact_version.paper_collection.fixture",
        parameters={"max_output_tokens": 2048, "temperature": 0},
    )
    changed_version = pipeline.admit(
        **common,
        paper_collection_version_id="artifact_version.paper_collection.revision_2",
        parameters={"temperature": 0, "max_output_tokens": 2048},
    )

    assert first.summary is not None and reordered.summary is not None
    assert changed_version.summary is not None
    assert first.producer.parameters_hash == reordered.producer.parameters_hash
    assert first.producer.input_hash == reordered.producer.input_hash
    assert first.summary.output_hash == reordered.summary.output_hash
    assert first.producer.input_hash != changed_version.producer.input_hash
    assert first.summary.output_hash != changed_version.summary.output_hash


def test_valid_model_response_hash_is_stable_across_json_key_order() -> None:
    collection = _collection()
    evidence = _evidence(collection)
    payload = json.loads(_model_output())
    reversed_payload = dict(reversed(tuple(payload.items())))

    first = _admit(collection, json.dumps(payload), (evidence,))
    reordered = _admit(collection, json.dumps(reversed_payload), (evidence,))

    assert first.summary is not None and reordered.summary is not None
    assert first.producer.model_response_hash == reordered.producer.model_response_hash
    assert first.summary.output_hash == reordered.summary.output_hash


def test_invalid_json_is_rejected_without_retaining_raw_model_output() -> None:
    collection = _collection()
    malicious = '{"experiments": ["private-chain-of-thought SUPER_SECRET"'

    result = _admit(collection, malicious, ())
    serialized = result.model_dump_json()

    assert result.admission_status == "rejected"
    assert result.failure_stage == "json"
    assert result.producer.status == "rejected"
    assert result.producer.error_code == "paper_summary.json_invalid"
    assert "SUPER_SECRET" not in serialized
    assert "private-chain-of-thought" not in serialized


def test_schema_failure_is_rejected_after_json_parse() -> None:
    collection = _collection()
    schema_invalid = json.dumps(
        {
            "background": {
                "section_kind": "background",
                "overview": None,
                "items": [],
            }
        }
    )

    result = _admit(collection, schema_invalid, ())

    assert result.admission_status == "rejected"
    assert result.failure_stage == "schema"
    assert result.producer.error_code == "paper_summary.schema_invalid"
    assert result.producer.output_hash is None


def test_quote_mismatch_marks_finding_unsupported_instead_of_fact() -> None:
    collection = _collection()
    evidence = _evidence(
        collection, excerpt="The excerpt contains unrelated text only."
    )

    result = _admit(collection, _model_output(), (evidence,))

    assert result.summary is not None
    assert (
        result.summary.experiments.items[0].status
        is PaperSummarySupportStatus.unsupported
    )
    assert (
        result.summary.experiments.items[0].validation_code
        == "evidence.quote_not_found"
    )
    assert result.summary.evidence[0].status is PaperSummarySupportStatus.unsupported


def test_unavailable_source_text_marks_finding_unverifiable() -> None:
    collection = _collection()
    evidence = _evidence(collection, excerpt=None)

    result = _admit(collection, _model_output(), (evidence,))

    assert result.summary is not None
    assert (
        result.summary.experiments.items[0].status
        is PaperSummarySupportStatus.unverifiable
    )
    assert (
        result.summary.evidence[0].validation_code == "evidence.source_text_unavailable"
    )


def test_unknown_evidence_reference_is_unverifiable_and_not_published_as_evidence() -> (
    None
):
    collection = _collection()

    result = _admit(collection, _model_output(), ())

    assert result.summary is not None
    assert (
        result.summary.experiments.items[0].status
        is PaperSummarySupportStatus.unverifiable
    )
    assert result.summary.experiments.items[0].evidence_ids == ()
    assert result.summary.evidence == ()


def test_source_version_conflict_retains_snapshot_version_without_auto_adjudication() -> (
    None
):
    collection = _collection()
    evidence = _evidence(
        collection,
        claimed_source_version="crossref.fixture.stale",
    )

    result = _admit(collection, _model_output(), (evidence,))

    assert result.summary is not None
    summary = result.summary
    assert summary.experiments.items[0].status is PaperSummarySupportStatus.supported
    assert len(summary.source_conflicts) == 1
    conflict = summary.source_conflicts[0]
    assert conflict.claimed_source_version == "crossref.fixture.stale"
    assert conflict.source_snapshot_version == "crossref.fixture.2026-07-26"
    assert conflict.resolution == "source_snapshot_version_retained"
    assert (
        summary.evidence[0].source_snapshot_version == conflict.source_snapshot_version
    )


def test_evidence_cannot_cross_candidate_or_snapshot_provenance() -> None:
    collection = _collection()
    evidence_payload = _evidence(collection).model_dump(mode="json")
    evidence_payload["source_record_id"] = "different-record"
    invalid_evidence = PaperSummaryEvidenceCandidate.model_validate(evidence_payload)

    result = _admit(collection, _model_output(), (invalid_evidence,))

    assert result.summary is not None
    assert (
        result.summary.experiments.items[0].status
        is PaperSummarySupportStatus.unverifiable
    )
    assert result.summary.evidence == ()


def test_evidence_locator_source_url_must_match_the_paper_acquisition_candidate() -> (
    None
):
    collection = _collection()
    payload = _evidence(collection).model_dump(mode="json")
    payload["locator"]["source_url"] = "https://example.invalid/unrelated-paper"
    evidence = PaperSummaryEvidenceCandidate.model_validate(payload)

    result = _admit(collection, _model_output(), (evidence,))

    assert result.summary is not None
    assert (
        result.summary.experiments.items[0].status
        is PaperSummarySupportStatus.unverifiable
    )
    assert result.summary.evidence[0].validation_code == (
        "evidence.source_url_unverifiable"
    )


@pytest.mark.parametrize(
    ("quote_or_value", "expected_status", "expected_code"),
    (
        (
            "Transiting Exoplanet Survey Satellite",
            PaperSummarySupportStatus.supported,
            "evidence.supported",
        ),
        (
            "A different title",
            PaperSummarySupportStatus.unsupported,
            "evidence.value_mismatch",
        ),
    ),
)
def test_metadata_evidence_value_is_checked_against_the_paper_acquisition_record(
    quote_or_value: str,
    expected_status: PaperSummarySupportStatus,
    expected_code: str,
) -> None:
    collection = _collection()
    candidate = collection.candidates[0]
    evidence = PaperSummaryEvidenceCandidate(
        evidence_id="evidence.summary_fixture",
        paper_id=candidate.canonical_paper_id,
        candidate_id=candidate.candidate_id,
        source_id=candidate.raw.source_id,
        source_record_id=candidate.raw.source_record_id,
        source_snapshot_id=candidate.raw.source_snapshot_id,
        locator=PaperSummaryEvidenceLocator(
            kind="paper_metadata",
            source_url=candidate.raw.url,
            metadata_field="title",
        ),
        quote_or_value=quote_or_value,
    )

    result = _admit(collection, _model_output(), (evidence,))

    assert result.summary is not None
    assert result.summary.experiments.items[0].status is expected_status
    assert result.summary.evidence[0].validation_code == expected_code


def test_sensitive_model_parameter_is_rejected_before_execution_record() -> None:
    collection = _collection()

    with pytest.raises(ValueError, match="forbidden"):
        PaperSummaryPipeline(clock=lambda: FIXED_TIME).admit(
            paper_collection=collection,
            paper_collection_version_id="artifact_version.paper_collection.fixture",
            paper_id=collection.selected_paper_ids[0],
            model_response=_model_output(),
            model_name="qwen.fixture.1",
            parameters={"api_key": "must-not-be-stored"},
            evidence_candidates=(),
        )


def test_producer_execution_uses_the_version_constants() -> None:
    collection = _collection()
    result = _admit(collection, _model_output(), (_evidence(collection),))

    assert result.producer.producer_name == SUMMARY_PRODUCER_NAME
    assert result.producer.producer_version == SUMMARY_PRODUCER_VERSION
    assert result.producer.parameters_version == SUMMARY_PARAMETERS_VERSION


def test_published_summary_excludes_accessible_excerpt_and_raw_response() -> None:
    collection = _collection()
    evidence = _evidence(
        collection,
        excerpt=(
            "The abstract states that TESS targets transits around nearby, bright stars. "
            "RESTRICTED_INPUT_SENTINEL"
        ),
    )
    model_response = _model_output()

    result = _admit(collection, model_response, (evidence,))
    serialized = result.model_dump_json()

    assert result.summary is not None
    assert "RESTRICTED_INPUT_SENTINEL" not in serialized
    assert model_response not in serialized
    assert "accessible_excerpt" not in serialized
    assert "chain-of-thought" not in serialized


def test_artifact_version_uses_the_generic_persisted_content_boundary() -> None:
    schema = ArtifactVersion.model_json_schema()
    assert schema["properties"]["content"]["type"] == "object"
    assert PaperSummaryArtifactContent.model_json_schema()["title"] == (
        "PaperSummaryArtifactContent"
    )


def test_paper_benchmark_report_is_reproducible_and_reports_required_metrics() -> None:
    collection = _collection()
    evidence = _evidence(collection)
    admission = _admit(collection, _model_output(), (evidence,))
    benchmark = load_frozen_benchmark()
    benchmark_summary_id = benchmark.paper_summaries[0].summary_id
    case = PaperSummaryBenchmarkEvaluationCase(
        case_id="summary_eval.fixture",
        benchmark_summary_id=benchmark_summary_id,
        admission=admission,
        unsupported_statement_ids=("summary_statement.limitation",),
    )

    report = evaluate_paper_summaries(
        benchmark=benchmark,
        cases=(case,),
        human_review_sample_ids=(benchmark_summary_id,),
    )

    assert report.benchmark_version == "2.0.0"
    assert report.schema_items_valid == 1
    assert report.schema_items_total == 1
    assert report.schema_pass_rate == 1.0
    assert report.evidence_items_supported == 1
    assert report.evidence_items_total == 2
    assert report.evidence_coverage == 0.5
    assert report.unsupported_items_blocked == 1
    assert report.unsupported_items_total == 1
    assert report.unsupported_block_rate == 1.0
    assert report.human_review_sample_ids == (benchmark_summary_id,)
    assert report.input_hash.startswith("sha256:")
    assert report.output_hash.startswith("sha256:")
    assert report.cases[0].input_hash == admission.producer.input_hash


def test_paper_benchmark_reports_not_available_for_empty_evidence_denominator() -> None:
    collection = _collection()
    payload = json.loads(_model_output())
    payload["background"]["overview"] = None
    payload["experiments"]["items"] = []
    payload["limitations"]["items"] = []
    payload["evidence_ids"] = []
    admission = _admit(collection, json.dumps(payload), ())
    benchmark = load_frozen_benchmark()
    benchmark_summary_id = benchmark.paper_summaries[0].summary_id

    report = evaluate_paper_summaries(
        benchmark=benchmark,
        cases=(
            PaperSummaryBenchmarkEvaluationCase(
                case_id="summary_eval.empty_core",
                benchmark_summary_id=benchmark_summary_id,
                admission=admission,
            ),
        ),
        human_review_sample_ids=(benchmark_summary_id,),
    )

    assert report.evidence_items_supported == 0
    assert report.evidence_items_total == 0
    assert report.evidence_coverage is None
    assert report.unsupported_items_total == 0
    assert report.unsupported_block_rate is None


def test_unsafe_markup_is_rejected_by_the_model_output_schema() -> None:
    payload = json.loads(_model_output())
    payload["experiments"]["items"][0]["text"] = "<script>alert(1)</script>"

    with pytest.raises(ValidationError, match="unsafe markup"):
        PaperSummaryModelOutput.model_validate(payload)


def test_output_hash_tampering_fails_summary_schema_validation() -> None:
    collection = _collection()
    result = _admit(collection, _model_output(), (_evidence(collection),))
    assert result.summary is not None
    payload = result.summary.model_dump(mode="json")
    payload["output_hash"] = "sha256:" + "0" * 64

    with pytest.raises(ValidationError, match="output_hash does not match"):
        PaperSummaryArtifactContent.model_validate(payload)


def test_summary_canonical_persisted_payload_preserves_required_nulls() -> None:
    collection = _collection()
    result = _admit(collection, _model_output(), (_evidence(collection),))
    assert result.summary is not None

    payload = canonical_artifact_content_payload(result.summary)

    assert payload["background"]["overview"] is not None
    assert payload["methodology"]["overview"] is None
    assert payload["dataset"]["overview"] is None
    assert PaperSummaryArtifactContent.model_validate(payload) == result.summary

    with pytest.raises(PublicationAdmissionError, match="explicit persisted provenance"):
        admit_artifact_candidate(
            result.summary,
            schema_version=result.summary.schema_version,
            source_snapshot_ids=tuple(
                item.source_snapshot_id
                for item in result.summary.input_versions.source_snapshots
            ),
            evidence_ids=result.summary.evidence_ids,
            evidence_validator=lambda _: None,
            domain_validator=lambda _: None,
            quality_validator=lambda _: None,
        )


def test_intermediate_model_output_cannot_bypass_the_summary_pipeline() -> None:
    model_output = PaperSummaryModelOutput.model_validate_json(_model_output())

    with pytest.raises(PublicationAdmissionError, match="canonical|authoritative"):
        admit_artifact_candidate(
            model_output,
            schema_version="2.0.0",
            source_snapshot_ids=(),
            evidence_ids=model_output.evidence_ids,
            evidence_validator=lambda _: None,
            domain_validator=lambda _: None,
            quality_validator=lambda _: None,
        )


def test_reconstructed_summary_cannot_bypass_pipeline_admission() -> None:
    collection = _collection()
    result = _admit(collection, _model_output(), (_evidence(collection),))
    assert result.summary is not None
    reconstructed = PaperSummaryArtifactContent.model_validate(
        result.summary.model_dump(mode="json")
    )

    with pytest.raises(PublicationAdmissionError, match="cannot bypass"):
        admit_artifact_candidate(
            reconstructed,
            schema_version=reconstructed.schema_version,
            source_snapshot_ids=tuple(
                item.source_snapshot_id
                for item in reconstructed.input_versions.source_snapshots
            ),
            evidence_ids=reconstructed.evidence_ids,
            evidence_validator=lambda _: None,
            domain_validator=lambda _: None,
            quality_validator=lambda _: None,
        )


def test_paper_summary_artifact_version_round_trips_through_json() -> None:
    collection = _collection()
    result = _admit(collection, _model_output(), (_evidence(collection),))
    assert result.summary is not None
    envelope = ArtifactVersion(
        id="artifact_version.paper_summary.fixture",
        artifact_id="artifact.paper_summary.fixture",
        project_id="project.paper_summary.fixture",
        created_by_run_id="run.paper_summary.fixture",
        version_number=1,
        schema_version="3.0.0",
        content=result.summary.model_dump(mode="json"),
        content_hash=result.summary.output_hash,
        input_hash=result.summary.input_hash,
        source_mode=SourceMode.fixture,
        producer={
            "type": "model",
            "name": result.summary.producer.producer_name,
            "version": result.summary.producer.producer_version,
            "model_name": result.summary.producer.model_name,
            "prompt_name": result.summary.producer.prompt_name,
            "prompt_version": result.summary.producer.prompt_version,
            "prompt_hash": result.summary.producer.prompt_hash,
            "parameters_hash": result.summary.producer.parameters_hash,
        },
        source_snapshot_ids=tuple(
            item.source_snapshot_id
            for item in result.summary.input_versions.source_snapshots
        ),
        evidence_ids=result.summary.evidence_ids,
        created_at=FIXED_TIME,
    )

    restored = ArtifactVersion.model_validate_json(envelope.model_dump_json())

    assert restored == envelope
    restored_summary = PaperSummaryArtifactContent.model_validate(restored.content)
    assert restored_summary.output_hash == result.summary.output_hash
