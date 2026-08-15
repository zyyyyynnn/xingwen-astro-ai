"""Recorded/unit coverage for the production PaperCollection seam.

These tests deliberately stop at the injected adapter boundary.  They do not
call Crossref or claim Live evidence.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.core import (
    ArtifactKind,
    DataRequirements,
    EvidenceRequirements,
    PaperSearchScope,
    QualityConstraints,
    ResearchContract,
    ResearchContractInput,
    SourceScope,
)
from app.schemas.enums import PaperDataLevel, SourceMode
from app.schemas.evidence import SourceSnapshotRecord
from app.schemas.paper_collection import PaperSearchContractReference, PaperSourcePage
from app.workflow.publisher import PublicationAdmissionError, admit_artifact_candidate
from app.workflow.store import AttemptHandle, LeaseGrant
from app.workflow.paper_collection_search_runtime import (
    PaperCollectionSearchRuntime,
    _ArtifactTarget,
    _SourceAttempt,
    _build_collection,
    _evidence_bindings,
    _source_bindings,
)
from services.paper_pipeline.constants import PRODUCER_VERSION
from services.paper_pipeline.query import normalize_contract_query
from services.paper_pipeline.sources.base import RawSourceRecord, SourceSearchResult


NOW = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)
PROJECT_ID = UUID("a0000000-0000-0000-0000-000000000001")
RUN_ID = UUID("a0000000-0000-0000-0000-000000000002")


def test_paper_search_contract_reference_accepts_numeric_leading_persisted_uuid() -> None:
    reference = PaperSearchContractReference(
        contract_id="00000000-0000-0000-0000-000000000003",
        contract_version=1,
        content_hash="sha256:" + "0" * 64,
    )

    assert reference.contract_id == "00000000-0000-0000-0000-000000000003"


class _RecordedAdapter:
    source_id = "crossref"
    adapter_name = "recorded_crossref"
    adapter_version = "1.0.0"

    def __init__(self, records: tuple[RawSourceRecord, ...]) -> None:
        self.records = records
        self.seen: list[tuple[SourceMode, PaperDataLevel]] = []
        self.events: list[str] = []

    def search(self, query, *, source_mode, data_level):  # type: ignore[no-untyped-def]
        self.events.append("adapter_called")
        self.seen.append((source_mode, data_level))
        records_hash = compute_canonical_payload_hash(
            [record.hash_payload() for record in self.records]
        )
        snapshot = SourceSnapshotRecord(
            snapshot_id="snapshot.crossref.recorded.1",
            source_id=self.source_id,
            source_type="paper_metadata",
            retrieved_at=NOW,
            query=query.normalized_query_string,
            query_hash=query.query_hash,
            content_hash=records_hash,
            license_note="Recorded metadata for unit testing only",
            request_metadata={"adapter_name": self.adapter_name},
        )
        page = PaperSourcePage(
            page_number=1,
            offset=0,
            requested_rows=len(self.records) or 1,
            returned_rows=len(self.records),
            total_results=len(self.records),
            attempt_count=1,
            status_code=200,
            retrieved_at=NOW,
            request_hash=compute_canonical_payload_hash(
                {"query_hash": query.query_hash}
            ),
            response_hash=records_hash,
        )
        return SourceSearchResult(
            records=self.records,
            pages=(page,),
            snapshot=snapshot,
            retry_count=0,
        )


def _contract(
    *, keywords: tuple[str, ...] = ("transiting exoplanet",)
) -> ResearchContract:
    content = ResearchContractInput(
        research_goal="Study transiting exoplanet host stars",
        target_objects=("exoplanet",),
        data_requirements=DataRequirements(),
        requested_fields=("planet.toi_id",),
        source_scope=SourceScope(allowed_sources=("nasa_exoplanet_archive",)),
        paper_search_scope=PaperSearchScope(
            keywords=keywords,
            year_from=2020,
            year_to=2025,
            source_ids=("crossref",),
            max_candidates=2,
        ),
        output_requirements=(ArtifactKind.paper_collection,),
        evidence_requirements=EvidenceRequirements(),
        quality_constraints=QualityConstraints(),
    )
    return ResearchContract(
        **content.model_dump(),
        id="contract.recorded-paper-search",
        project_id=str(PROJECT_ID),
        version=1,
        created_from_draft_id="draft.recorded-paper-search",
        created_at=NOW,
        content_hash=compute_canonical_payload_hash(content.model_dump(mode="json")),
    )


def _records() -> tuple[RawSourceRecord, ...]:
    return (
        RawSourceRecord(
            source_id="crossref",
            source_record_id="doi-1",
            title="Transiting Exoplanet Host Stars",
            authors=("Ada Researcher",),
            year=2024,
            doi="10.1234/example.1",
            arxiv_id=None,
            url="https://doi.org/10.1234/example.1",
        ),
        RawSourceRecord(
            source_id="crossref",
            source_record_id="doi-1-duplicate",
            title="Transiting Exoplanet Host Stars",
            authors=("Ada Researcher",),
            year=2024,
            doi="10.1234/example.1",
            arxiv_id=None,
            url="https://doi.org/10.1234/example.1",
        ),
    )


def _build_recorded_collection():
    contract = _contract()
    adapter = _RecordedAdapter(_records())
    runtime = PaperCollectionSearchRuntime(
        session_factory=lambda: None,  # type: ignore[return-value]
        adapters={"crossref": adapter},
        clock=lambda: NOW,
    )
    normalized = normalize_contract_query(
        contract.paper_search_scope,
        research_goal=contract.research_goal,
        available_source_ids=("crossref",),
    )
    rules = runtime._rules((adapter,), contract.paper_search_scope.max_candidates)
    source_attempt = _SourceAttempt(
        adapter=adapter,
        source_mode=SourceMode.fixture,
        data_level=PaperDataLevel.recorded_response,
        started_at=NOW,
        finished_at=NOW,
        result=adapter.search(
            normalized,
            source_mode=SourceMode.fixture,
            data_level=PaperDataLevel.recorded_response,
        ),
        failure=None,
    )
    collection = _build_collection(
        contract=contract,
        query=normalized,
        rules=rules,
        attempts=(source_attempt,),
        execution_id="producer.recorded-paper-search",
        producer_parameters_hash=compute_canonical_payload_hash({"source": "recorded"}),
        run_id=RUN_ID,
        started_at=NOW,
        finished_at=NOW,
    )
    return runtime, contract, collection


def test_contract_normalization_falls_back_to_research_goal() -> None:
    contract = _contract(keywords=())

    normalized = normalize_contract_query(
        contract.paper_search_scope,
        research_goal=contract.research_goal,
        available_source_ids=("crossref",),
    )

    assert normalized.original_keywords == (contract.research_goal,)
    assert normalized.source_ids == ("crossref",)
    assert normalized.pagination.candidate_limit == 2


def test_paper_source_scope_is_independent_from_astronomy_data_sources() -> None:
    contract = _contract()

    normalized = normalize_contract_query(
        contract.paper_search_scope,
        research_goal=contract.research_goal,
        available_source_ids=("crossref",),
    )

    assert contract.source_scope.allowed_sources == ("nasa_exoplanet_archive",)
    assert normalized.source_ids == ("crossref",)


def test_contract_query_rejects_an_unconfigured_paper_adapter() -> None:
    scope = PaperSearchScope(source_ids=("openalex",))

    with pytest.raises(ValueError, match="not configured: openalex"):
        normalize_contract_query(
            scope,
            research_goal="Study transiting exoplanets",
            available_source_ids=("crossref",),
        )


def test_recorded_collection_reuses_canonicalization_dedupe_and_ranking() -> None:
    _, _, collection = _build_recorded_collection()

    assert len(collection.candidates) == 2
    assert len(collection.duplicate_groups) == 1
    assert collection.selected_paper_ids
    assert collection.metrics.duplicate_candidate_count == 1
    assert collection.producer.producer_version == PRODUCER_VERSION
    assert collection.benchmark is None
    assert collection.research_contract is not None
    assert collection.research_contract.contract_id == "contract.recorded-paper-search"


def test_paper_collection_provenance_bindings_close_candidates() -> None:
    _, _, collection = _build_recorded_collection()
    source_bindings = _source_bindings(PROJECT_ID, collection.source_snapshots)
    evidence_bindings = _evidence_bindings(
        project_id=PROJECT_ID,
        input_hash=collection.input_hash,
        collection=collection,
        source_bindings=source_bindings,
    )

    assert len(source_bindings) == 1
    assert len(evidence_bindings) == len(collection.candidates)
    assert {item.pipeline_source_snapshot_id for item in evidence_bindings} == {
        collection.source_snapshots[0].snapshot_id
    }

    admitted = admit_artifact_candidate(
        collection,
        schema_version=collection.schema_version,
        source_snapshot_ids=collection.source_snapshot_ids,
        evidence_ids=tuple(item.pipeline_evidence_id for item in evidence_bindings),
        evidence_validator=lambda _: None,
        domain_validator=lambda _: None,
        quality_validator=lambda _: None,
        source_snapshot_bindings=source_bindings,
        evidence_bindings=evidence_bindings,
    )

    assert len(admitted.literature_source_snapshot_materializations) == 1
    assert len(admitted.literature_evidence_materializations) == len(
        collection.candidates
    )


def test_live_acquisition_rejects_synthetic_record_before_publication() -> None:
    adapter = _RecordedAdapter(
        (
            RawSourceRecord(
                source_id="crossref",
                source_record_id="synthetic",
                title="Synthetic paper",
                authors=(),
                year=2024,
                doi=None,
                arxiv_id=None,
                url=None,
                synthetic_note="recorded fixture",
            ),
        )
    )
    runtime = PaperCollectionSearchRuntime(
        session_factory=lambda: None,  # type: ignore[return-value]
        adapters={"crossref": adapter},
        clock=lambda: NOW,
    )
    query = normalize_contract_query(
        _contract().paper_search_scope,
        research_goal=_contract().research_goal,
        available_source_ids=("crossref",),
    )

    with pytest.raises(PublicationAdmissionError, match="synthetic"):
        runtime._acquire(
            (adapter,),
            query=query,
            source_mode=SourceMode.live,
            data_level=PaperDataLevel.live_result,
        )


def test_runtime_starts_producer_before_recorded_adapter_and_finishes_with_hash() -> (
    None
):
    contract = _contract()
    adapter = _RecordedAdapter(_records())
    events: list[str] = []

    class _Ledger:
        def start_producer_execution(self, request, **kwargs):  # type: ignore[no-untyped-def]
            events.append("producer_started")
            return SimpleNamespace(
                id=UUID("a0000000-0000-0000-0000-000000000003"),
                parameters_hash=compute_canonical_payload_hash(request.parameters),
            )

        def finish_producer_execution(self, execution_id, **kwargs):  # type: ignore[no-untyped-def]
            events.append(f"producer_{kwargs['status']}")
            return SimpleNamespace(output_hash=kwargs.get("output_hash"))

    runtime = PaperCollectionSearchRuntime(
        session_factory=lambda: None,  # type: ignore[return-value]
        adapters={"crossref": adapter},
        clock=lambda: NOW,
    )
    runtime._producers = _Ledger()
    runtime._persist_source_snapshots = lambda *args: None
    runtime._ensure_artifact_target = lambda **kwargs: _ArtifactTarget(
        artifact_id=UUID("a0000000-0000-0000-0000-000000000004"),
        publication_key="paper-publication",
        supersedes_version_id=None,
    )
    adapter.events = events
    attempt = AttemptHandle(
        run_id=RUN_ID,
        run_step_id=UUID("a0000000-0000-0000-0000-000000000005"),
        attempt_id=UUID("a0000000-0000-0000-0000-000000000006"),
        attempt_number=1,
        run_status="searching_papers",
        run_revision=1,
        event_sequence=1,
    )
    lease = LeaseGrant(
        run_id=RUN_ID,
        token=UUID("a0000000-0000-0000-0000-000000000007"),
        generation=1,
        revision=1,
        expires_at=NOW,
        active_attempt_ids=(attempt.attempt_id,),
    )

    publication = runtime.prepare_publication(
        project_id=PROJECT_ID,
        contract=contract,
        attempt=attempt,
        lease=lease,
        source_mode=SourceMode.fixture,
        data_level=PaperDataLevel.recorded_response,
    )

    assert events == ["producer_started", "adapter_called", "producer_completed"]
    assert publication.candidate.content_hash
    assert publication.producer_execution_id == UUID(
        "a0000000-0000-0000-0000-000000000003"
    )
