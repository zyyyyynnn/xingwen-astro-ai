"""Immutable DocumentParse persistence integration tests.

The PostgreSQL cases skip unless TEST_DATABASE_URL points at an isolated test
database.  Pure identity tests always run.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import os
from pathlib import Path
import threading
from uuid import UUID, uuid4

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import Engine, func, select, update
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.db.models import (
    DocumentParseLocatorModel,
    DocumentParseModel,
    ProducerExecutionModel,
    ResearchInputContentModel,
    ResearchInputModel,
    ResearchRunModel,
    RunStepModel,
    SourceSnapshotModel,
    StepAttemptModel,
)
from app.db.session import create_engine_from_url, session_factory
from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.scientific_document import (
    DocumentBBox,
    DocumentBlock,
    DocumentBlockKind,
    DocumentLocator,
    DocumentPage,
    DocumentParseCandidate,
    DocumentParseProfile,
    DocumentParseQuality,
    DocumentTable,
    DocumentTableCell,
    ParserBackend,
    TextSpan,
)
from app.services.content_storage import LocalContentStorage, sha256_content_hash
from app.services.document_parse_store import (
    DocumentParseIntegrityError,
    DocumentParseNotFoundError,
    DocumentParseRepository,
    DocumentParseService,
    PersistDocumentParseRequest,
    document_parse_identity_hash,
)
from authoring_test_support import (
    build_contract_draft,
    build_research_contract,
    build_research_project,
    persist_authoring_models,
)


def _cas_blob_count(root: Path) -> int:
    """Count published CAS final blobs (excludes `.tmp_*`/`.corrupt_*` temp)."""

    if not root.exists():
        return 0
    return sum(
        1
        for path in root.rglob("*")
        if path.is_file() and not path.name.startswith(".")
    )


def storage_exists(root: Path, content_hash: str) -> bool:
    """Return whether the CAS published a final blob for ``content_hash``."""

    hex_value = content_hash.removeprefix("sha256:")
    return (root / hex_value[:2] / hex_value).is_file()


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
NOW = datetime(2026, 8, 12, 8, 0, tzinfo=UTC)
INPUT_BYTES = b"%PDF-1.7\nDocumentParse fixture\n"
INPUT_HASH = sha256_content_hash(INPUT_BYTES)
PARSE_INPUT_HASH = compute_canonical_payload_hash(
    {"research_input_content_hash": INPUT_HASH, "profile": "native-default"}
)
OUTPUT_HASH = "sha256:" + "d" * 64
CONFIG_HASH = "sha256:" + "c" * 64


def _candidate(
    input_id: UUID, *, parse_id: str = "document-parse-candidate"
) -> DocumentParseCandidate:
    block = DocumentBlock(
        block_id="primary-table-block",
        page_index=0,
        reading_order=0,
        kind=DocumentBlockKind.table,
        bbox=DocumentBBox(x1=10, y1=20, x2=200, y2=120),
        text="Host temperature 5600 K",
        quality=DocumentParseQuality.accepted,
        parser_backend=ParserBackend.native,
        parser_profile_id="native-default",
    )
    cell = DocumentTableCell(
        cell_id="temperature-cell",
        row_index=0,
        column_index=0,
        bbox=DocumentBBox(x1=20, y1=40, x2=100, y2=70),
        text="5600 K",
        quality=DocumentParseQuality.accepted,
    )
    return DocumentParseCandidate(
        parse_id=parse_id,
        research_input_id=str(input_id),
        content_hash=INPUT_HASH,
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
        canonical_output_hash=OUTPUT_HASH,
        pages=(
            DocumentPage(
                page_index=0,
                width_points=612,
                height_points=792,
                block_ids=("primary-table-block",),
            ),
        ),
        blocks=(block,),
        tables=(
            DocumentTable(
                table_id="temperature-table",
                page_index=0,
                block_id="primary-table-block",
                row_count=1,
                column_count=1,
                rows=((cell,),),
                quality=DocumentParseQuality.accepted,
            ),
        ),
        overall_quality=DocumentParseQuality.accepted,
        created_at=NOW,
    )


def test_document_parse_identity_excludes_process_local_parse_id() -> None:
    input_id = uuid4()
    assert document_parse_identity_hash(
        _candidate(input_id, parse_id="worker-alpha"),
        parse_input_hash=PARSE_INPUT_HASH,
    ) == document_parse_identity_hash(
        _candidate(input_id, parse_id="worker-beta"),
        parse_input_hash=PARSE_INPUT_HASH,
    )


def _alembic_config(url: str) -> Config:
    root = Path(__file__).resolve().parents[1]
    config = Config(root / "alembic.ini")
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


@pytest.fixture(scope="module")
def postgres_engine() -> Engine:
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL is not configured")
    assert "test" in TEST_DATABASE_URL.rsplit("/", 1)[-1].lower(), (
        "refusing non-test database"
    )
    config = _alembic_config(TEST_DATABASE_URL)
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    engine = create_engine_from_url(TEST_DATABASE_URL)
    yield engine
    engine.dispose()
    command.downgrade(config, "base")
    command.upgrade(config, "head")


@pytest.fixture
def context(postgres_engine: Engine, tmp_path: Path) -> dict[str, object]:
    factory = session_factory(postgres_engine)
    ids = {
        name: uuid4()
        for name in (
            "project",
            "other_project",
            "contract",
            "run",
            "step",
            "attempt",
            "producer",
            "input",
        )
    }
    storage = LocalContentStorage(tmp_path / "cas")
    storage_ref = asyncio.run(storage.store(INPUT_BYTES, INPUT_HASH))
    project = build_research_project(
        project_id=ids["project"],
        session_id="owner",
        name="Document parse persistence",
        case_key="exoplanet_host_star",
        created_at=NOW,
        updated_at=NOW,
    )
    other_project = build_research_project(
        project_id=ids["other_project"],
        session_id="other",
        name="Other",
        case_key="exoplanet_host_star",
        created_at=NOW,
        updated_at=NOW,
    )
    draft = build_contract_draft(project, created_at=NOW, updated_at=NOW)
    contract = build_research_contract(
        project,
        draft,
        contract_id=ids["contract"],
        content_hash="sha256:" + "a" * 64,
        created_at=NOW,
    )
    with factory() as session, session.begin():
        persist_authoring_models(
            session,
            project=project,
            draft=draft,
            contract=contract,
        )
        session.add(other_project)
    with factory() as session, session.begin():
        session.add(
            ResearchRunModel(
                id=ids["run"],
                project_id=ids["project"],
                contract_id=ids["contract"],
                execution_mode="live",
                status="completed",
                progress=100,
                derivation_kind="original",
                cache_policy="disabled",
                latest_event_sequence=0,
                revision=1,
                idempotency_key=f"run-{ids['run']}",
                request_hash="sha256:" + "b" * 64,
            )
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
            content_hash=INPUT_HASH,
            storage_ref=storage_ref,
            mime_type="application/pdf",
            size_bytes=len(INPUT_BYTES),
            created_at=NOW,
        )
        session.add_all([step, attempt, content])
    with factory() as session, session.begin():
        input_row = ResearchInputModel(
            id=ids["input"],
            session_id="owner",
            project_id=ids["project"],
            type="pdf",
            source_type="upload",
            content_hash=INPUT_HASH,
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
            output_hash=OUTPUT_HASH,
            status="completed",
            started_at=NOW,
            finished_at=NOW,
            latency_ms=12,
        )
        session.add_all([input_row, producer])
    repository = DocumentParseRepository(factory)
    service = DocumentParseService(repository, storage)
    request = PersistDocumentParseRequest(
        project_id=ids["project"],
        run_id=ids["run"],
        run_step_id=ids["step"],
        producer_execution_id=ids["producer"],
        parse_input_hash=PARSE_INPUT_HASH,
        candidate=_candidate(ids["input"]),
    )
    return {
        "factory": factory,
        "ids": ids,
        "service": service,
        "request": request,
    }


def test_persist_reuse_lazy_snapshot_and_locator_validation(
    context: dict[str, object],
) -> None:
    service = context["service"]
    request = context["request"]
    ids = context["ids"]
    factory = context["factory"]
    assert isinstance(service, DocumentParseService)
    assert isinstance(request, PersistDocumentParseRequest)
    assert isinstance(ids, dict)

    first = asyncio.run(service.persist(request))
    replay = asyncio.run(
        service.persist(
            PersistDocumentParseRequest(
                project_id=request.project_id,
                run_id=request.run_id,
                run_step_id=request.run_step_id,
                producer_execution_id=request.producer_execution_id,
                parse_input_hash=request.parse_input_hash,
                candidate=request.candidate.model_copy(
                    update={
                        "parse_id": "another-worker-local-id",
                        "created_at": datetime(2026, 8, 12, 8, 1, tzinfo=UTC),
                    }
                ),
            )
        )
    )
    assert replay.id == first.id
    assert replay.reused is True
    assert not hasattr(first, "payload_storage_ref")
    assert asyncio.run(
        service.get_candidate(
            project_id=request.project_id, document_parse_id=first.id
        )
    ) == request.candidate

    with factory() as session:  # type: ignore[operator]
        input_row = session.get(ResearchInputModel, ids["input"])
        assert input_row is not None
        assert input_row.source_snapshot_id == first.source_snapshot_id
        snapshot = session.get(SourceSnapshotModel, first.source_snapshot_id)
        assert snapshot is not None
        assert snapshot.content_hash == INPUT_HASH
        assert snapshot.query == {"research_input_id": str(ids["input"])}
        assert "content" not in snapshot.request_metadata

    locator = DocumentLocator(
        page_index=0,
        block_id="primary-table-block",
        reading_order=0,
        text_span=TextSpan(start=0, end=4),
        table_id="temperature-table",
        cell_id="temperature-cell",
        bbox=DocumentBBox(x1=20, y1=40, x2=100, y2=70),
    )
    persisted = asyncio.run(
        service.persist_locator(
            project_id=request.project_id,
            document_parse_id=first.id,
            source_snapshot_id=first.source_snapshot_id,
            locator=locator,
        )
    )
    replayed = asyncio.run(
        service.persist_locator(
            project_id=request.project_id,
            document_parse_id=first.id,
            source_snapshot_id=first.source_snapshot_id,
            locator=locator,
        )
    )
    assert replayed.id == persisted.id
    assert replayed.reused is True

    invalid_locators = (
        DocumentLocator(page_index=99),
        DocumentLocator(page_index=0, block_id="missing"),
        DocumentLocator(page_index=0, reading_order=0),
        DocumentLocator(page_index=0, table_id="missing"),
        DocumentLocator(
            page_index=0, table_id="temperature-table", cell_id="missing"
        ),
        DocumentLocator(
            page_index=0,
            table_id="temperature-table",
            bbox=DocumentBBox(x1=300, y1=300, x2=350, y2=350),
        ),
        DocumentLocator(
            page_index=0,
            block_id="primary-table-block",
            text_span=TextSpan(start=0, end=999),
        ),
    )
    for invalid in invalid_locators:
        with pytest.raises(DocumentParseIntegrityError):
            asyncio.run(
                service.persist_locator(
                    project_id=request.project_id,
                    document_parse_id=first.id,
                    source_snapshot_id=first.source_snapshot_id,
                    locator=invalid,
                )
            )

    conflicting_payload = request.candidate.model_dump(mode="json")
    conflicting_payload["blocks"][0]["text"] = "conflicting canonical content"
    with pytest.raises(DocumentParseIntegrityError, match="conflicting immutable"):
        asyncio.run(
            service.persist(
                PersistDocumentParseRequest(
                    project_id=request.project_id,
                    run_id=request.run_id,
                    run_step_id=request.run_step_id,
                    producer_execution_id=request.producer_execution_id,
                    parse_input_hash=request.parse_input_hash,
                    candidate=DocumentParseCandidate.model_validate(
                        conflicting_payload
                    ),
                )
            )
        )


def test_blocker1_same_content_wrong_source_rejects_provenance(
    context: dict[str, object],
) -> None:
    """Case A: same content_hash but a provenance-divergent snapshot must fail.

    A ResearchInput ``A`` (upload) has its ``source_snapshot_id`` hand-pointed at
    an unrelated SourceSnapshot ``B`` that reuses the identical content_hash but
    a different ``source_id`` / ``query`` / ``source_type``. The authoritative
    upload validator must reject reuse and raise ``DocumentParseIntegrityError``.
    """

    service = context["service"]
    request = context["request"]
    ids = context["ids"]
    factory = context["factory"]
    assert isinstance(service, DocumentParseService)
    assert isinstance(request, PersistDocumentParseRequest)
    assert isinstance(ids, dict)

    unrelated_snapshot_id = uuid4()
    with factory() as session, session.begin():  # type: ignore[operator]
        session.add(
            SourceSnapshotModel(
                id=unrelated_snapshot_id,
                project_id=ids["project"],
                source_id="research_input:other-input",
                source_type="research_input_upload",
                retrieved_at=NOW,
                query={"research_input_id": "other-input"},
                query_hash=compute_canonical_payload_hash(
                    {"research_input_id": "other-input"}
                ),
                source_version_or_etag=None,
                content_hash=INPUT_HASH,
                license_note="user-provided upload",
                cache_version=None,
                request_metadata={"ingestion_source": "upload"},
            )
        )
        # Flush the new snapshot before repointing research_input, whose
        # source_snapshot_id is a raw UUID FK (no ORM-level dependency order).
        session.flush()
        input_row = session.get(ResearchInputModel, ids["input"])
        assert input_row is not None
        input_row.source_snapshot_id = unrelated_snapshot_id

    with pytest.raises(DocumentParseIntegrityError):
        asyncio.run(service.persist(request))


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("retrieved_at", datetime(2026, 8, 12, 9, 0, tzinfo=UTC)),
        ("source_version_or_etag", "unexpected-etag"),
        ("cache_version", "unexpected-cache-version"),
        ("license_note", "unexpected-license"),
        ("request_metadata", {"ingestion_source": "upload", "extra": "value"}),
    ),
)
def test_blocker1_rejects_noncanonical_upload_snapshot_metadata(
    context: dict[str, object], field: str, value: object
) -> None:
    service = context["service"]
    request = context["request"]
    ids = context["ids"]
    factory = context["factory"]
    assert isinstance(service, DocumentParseService)
    assert isinstance(request, PersistDocumentParseRequest)
    assert isinstance(ids, dict)

    query = {"research_input_id": str(ids["input"])}
    snapshot_values = {
        "id": uuid4(),
        "project_id": ids["project"],
        "source_id": f"research_input:{ids['input']}",
        "source_type": "research_input_upload",
        "retrieved_at": NOW,
        "query": query,
        "query_hash": compute_canonical_payload_hash(query),
        "source_version_or_etag": None,
        "content_hash": INPUT_HASH,
        "license_note": "user-provided upload",
        "cache_version": None,
        "request_metadata": {"ingestion_source": "upload"},
    }
    snapshot_values[field] = value
    with factory() as session, session.begin():  # type: ignore[operator]
        snapshot = SourceSnapshotModel(**snapshot_values)
        session.add(snapshot)
        session.flush()
        input_row = session.get(ResearchInputModel, ids["input"])
        assert input_row is not None
        input_row.source_snapshot_id = snapshot.id

    with pytest.raises(DocumentParseIntegrityError):
        asyncio.run(service.persist(request))


def test_blocker1_valid_pre_existing_upload_snapshot_reuses(
    context: dict[str, object],
) -> None:
    """Case B: an already-correct upload-backed snapshot must be reused, not duplicated.

    The ResearchInput ``A`` already points at a fully authoritative upload
    SourceSnapshot. ``persist`` must reuse it and create exactly one snapshot.
    """

    service = context["service"]
    request = context["request"]
    ids = context["ids"]
    factory = context["factory"]
    assert isinstance(service, DocumentParseService)
    assert isinstance(request, PersistDocumentParseRequest)
    assert isinstance(ids, dict)

    pre_existing_id = uuid4()
    with factory() as session, session.begin():  # type: ignore[operator]
        session.add(
            SourceSnapshotModel(
                id=pre_existing_id,
                project_id=ids["project"],
                source_id=f"research_input:{ids['input']}",
                source_type="research_input_upload",
                retrieved_at=NOW,
                query={"research_input_id": str(ids["input"])},
                query_hash=compute_canonical_payload_hash(
                    {"research_input_id": str(ids["input"])}
                ),
                source_version_or_etag=None,
                content_hash=INPUT_HASH,
                license_note="user-provided upload",
                cache_version=None,
                request_metadata={"ingestion_source": "upload"},
            )
        )
        # Flush the pre-existing snapshot before repointing research_input.
        session.flush()
        input_row = session.get(ResearchInputModel, ids["input"])
        assert input_row is not None
        input_row.source_snapshot_id = pre_existing_id

    first = asyncio.run(service.persist(request))
    assert first.source_snapshot_id == pre_existing_id
    replay = asyncio.run(
        service.persist(
            PersistDocumentParseRequest(
                project_id=request.project_id,
                run_id=request.run_id,
                run_step_id=request.run_step_id,
                producer_execution_id=request.producer_execution_id,
                parse_input_hash=request.parse_input_hash,
                candidate=request.candidate.model_copy(
                    update={
                        "parse_id": "another-worker-local-id",
                        "created_at": datetime(2026, 8, 12, 8, 1, tzinfo=UTC),
                    }
                ),
            )
        )
    )
    assert replay.id == first.id
    assert replay.reused is True
    with factory() as session:  # type: ignore[operator]
        snapshot_count = session.scalar(
            select(func.count())
            .select_from(SourceSnapshotModel)
            .where(
                SourceSnapshotModel.project_id == ids["project"],
                SourceSnapshotModel.source_type == "research_input_upload",
                SourceSnapshotModel.content_hash == INPUT_HASH,
            )
        )
        assert snapshot_count == 1


def test_blocker2_replay_does_not_orphan_cas_blob(
    context: dict[str, object],
    tmp_path: Path,
) -> None:
    """A successful replay with different parse_id/created_at reuses the CAS blob.

    Only one authoritative DocumentParse row exists and the CAS holds exactly one
    payload blob for the stable (parse_id/created_at-excluded) representation.
    The CAS also stores the unrelated input-content blob, so the final count of
    published blobs is exactly two (1 input + 1 stable parse payload); a replay
    that re-serialized the full candidate would orphan a second, unreachable
    payload blob and push the count to three.
    """

    service = context["service"]
    request = context["request"]
    ids = context["ids"]
    factory = context["factory"]
    assert isinstance(service, DocumentParseService)
    assert isinstance(request, PersistDocumentParseRequest)

    first = asyncio.run(service.persist(request))
    replay = asyncio.run(
        service.persist(
            PersistDocumentParseRequest(
                project_id=request.project_id,
                run_id=request.run_id,
                run_step_id=request.run_step_id,
                producer_execution_id=request.producer_execution_id,
                parse_input_hash=request.parse_input_hash,
                candidate=request.candidate.model_copy(
                    update={
                        "parse_id": "replay-worker-local-id",
                        "created_at": datetime(2026, 8, 12, 9, 0, tzinfo=UTC),
                    }
                ),
            )
        )
    )
    assert replay.id == first.id
    assert replay.reused is True

    with factory() as session:  # type: ignore[operator]
        assert session.scalar(
            select(func.count())
            .select_from(DocumentParseModel)
            .where(DocumentParseModel.project_id == ids["project"])
        ) == 1
    # Exactly one stable parse payload blob (plus the separate input-content blob).
    assert _cas_blob_count(tmp_path / "cas") == 2
    # The stable payload hash is published exactly once.
    assert first.payload_content_hash == replay.payload_content_hash
    assert storage_exists(tmp_path / "cas", first.payload_content_hash)
    # get_candidate still returns the frozen worker-local metadata of the winner.
    winner = asyncio.run(
        service.get_candidate(
            project_id=ids["project"], document_parse_id=first.id
        )
    )
    assert winner.parse_id == request.candidate.parse_id
    assert winner.created_at == request.candidate.created_at


def test_blocker2_concurrent_equivalent_parse_has_single_cas_blob(
    context: dict[str, object],
    tmp_path: Path,
) -> None:
    """Two equivalent logical parses (worker-local id/time differ) -> 1 row, 1 blob."""

    service = context["service"]
    request = context["request"]
    factory = context["factory"]
    assert isinstance(service, DocumentParseService)

    barrier = threading.Barrier(2)
    records = []
    failures = []

    def persist(worker_id: str) -> None:
        try:
            barrier.wait()
            candidate = request.candidate.model_copy(
                update={
                    "parse_id": worker_id,
                    "created_at": datetime(2026, 8, 12, 8, 0, tzinfo=UTC),
                }
            )
            records.append(
                asyncio.run(
                    service.persist(
                        PersistDocumentParseRequest(
                            project_id=request.project_id,
                            run_id=request.run_id,
                            run_step_id=request.run_step_id,
                            producer_execution_id=request.producer_execution_id,
                            parse_input_hash=request.parse_input_hash,
                            candidate=candidate,
                        )
                    )
                )
            )
        except Exception as exc:  # pragma: no cover - asserted below
            failures.append(exc)

    threads = [threading.Thread(target=persist, args=(f"worker-{i}",)) for i in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert failures == []
    assert len(records) == 2
    assert len({record.id for record in records}) == 1
    with factory() as session:  # type: ignore[operator]
        assert session.scalar(
            select(func.count())
            .select_from(DocumentParseModel)
            .where(DocumentParseModel.project_id == request.project_id)
        ) == 1
    # Exactly one stable parse payload blob (plus the separate input-content blob).
    assert _cas_blob_count(tmp_path / "cas") == 2


def test_cross_project_reads_fail_closed_and_rows_are_database_immutable(
    context: dict[str, object],
) -> None:
    service = context["service"]
    request = context["request"]
    ids = context["ids"]
    factory = context["factory"]
    assert isinstance(service, DocumentParseService)
    assert isinstance(request, PersistDocumentParseRequest)
    assert isinstance(ids, dict)
    record = asyncio.run(service.persist(request))

    with pytest.raises(DocumentParseNotFoundError):
        asyncio.run(
            service.get_candidate(
                project_id=ids["other_project"], document_parse_id=record.id
            )
        )

    with pytest.raises(DBAPIError, match="immutable"):
        with factory() as session, session.begin():  # type: ignore[operator]
            session.execute(
                update(DocumentParseModel)
                .where(DocumentParseModel.id == record.id)
                .values(overall_quality="partial")
            )

    locator = DocumentLocator(page_index=0, block_id="primary-table-block")
    persisted_locator = asyncio.run(
        service.persist_locator(
            project_id=request.project_id,
            document_parse_id=record.id,
            source_snapshot_id=record.source_snapshot_id,
            locator=locator,
        )
    )
    with pytest.raises(DBAPIError, match="immutable"):
        with factory() as session, session.begin():  # type: ignore[operator]
            session.execute(
                update(DocumentParseLocatorModel)
                .where(DocumentParseLocatorModel.id == persisted_locator.id)
                .values(locator={"page_index": 99})
            )

    with factory() as session, session.begin():  # type: ignore[operator]
        session.add(
            DocumentParseLocatorModel(
                id=uuid4(),
                project_id=request.project_id,
                document_parse_id=record.id,
                source_snapshot_id=record.source_snapshot_id,
                locator_hash=compute_canonical_payload_hash({"page_index": 0}),
                locator={"page_index": 99},
            )
        )
    with pytest.raises(DocumentParseIntegrityError, match="conflicting immutable"):
        asyncio.run(
            service.persist_locator(
                project_id=request.project_id,
                document_parse_id=record.id,
                source_snapshot_id=record.source_snapshot_id,
                locator=DocumentLocator(page_index=0),
            )
        )

    with factory() as session, session.begin():  # type: ignore[operator]
        other_snapshot = SourceSnapshotModel(
            id=uuid4(),
            project_id=request.project_id,
            source_id="unrelated-snapshot",
            source_type="fixture",
            retrieved_at=NOW,
            query="unrelated",
            query_hash="sha256:" + "8" * 64,
            content_hash="sha256:" + "9" * 64,
            license_note="test",
            request_metadata={},
        )
        session.add(other_snapshot)
        session.flush()
        session.add(
            DocumentParseLocatorModel(
                id=uuid4(),
                project_id=request.project_id,
                document_parse_id=record.id,
                source_snapshot_id=other_snapshot.id,
                locator_hash="sha256:" + "7" * 64,
                locator={"page_index": 0},
            )
        )
        with pytest.raises(IntegrityError):
            session.flush()


def test_different_parser_configuration_creates_new_record(
    context: dict[str, object],
) -> None:
    service = context["service"]
    request = context["request"]
    ids = context["ids"]
    factory = context["factory"]
    assert isinstance(service, DocumentParseService)
    assert isinstance(request, PersistDocumentParseRequest)
    assert isinstance(ids, dict)
    original = asyncio.run(service.persist(request))

    config_hash = "sha256:" + "e" * 64
    output_hash = "sha256:" + "f" * 64
    parse_input_hash = compute_canonical_payload_hash(
        {"research_input_content_hash": INPUT_HASH, "profile": "native-alternate"}
    )
    candidate_payload = request.candidate.model_dump(mode="json")
    candidate_payload.update(
        {
            "parse_id": "document-parse-candidate-alternate",
            "profile": {
                **candidate_payload["profile"],
                "parser_profile_id": "native-alternate",
                "parser_profile_version": "2.0.0",
                "configuration_hash": config_hash,
            },
            "config_hash": config_hash,
            "canonical_output_hash": output_hash,
            "blocks": [
                {**block, "parser_profile_id": "native-alternate"}
                for block in candidate_payload["blocks"]
            ],
        }
    )
    candidate = DocumentParseCandidate.model_validate(candidate_payload)
    producer_id = uuid4()
    with factory() as session, session.begin():  # type: ignore[operator]
        session.add(
            ProducerExecutionModel(
                id=producer_id,
                run_id=ids["run"],
                run_step_id=ids["step"],
                step_attempt_id=ids["attempt"],
                step_key="parse_document",
                idempotency_key=f"parse-producer-{producer_id}",
                lease_generation=1,
                producer_type="algorithm",
                producer_name="hybrid-document-parser",
                producer_version="2.0.0",
                parameters={"profile": "native-alternate"},
                parameters_hash=compute_canonical_payload_hash(
                    {"profile": "native-alternate"}
                ),
                input_hash=parse_input_hash,
                output_hash=output_hash,
                status="completed",
                started_at=NOW,
                finished_at=NOW,
                latency_ms=14,
            )
        )
    changed = asyncio.run(
        service.persist(
            PersistDocumentParseRequest(
                project_id=request.project_id,
                run_id=request.run_id,
                run_step_id=request.run_step_id,
                producer_execution_id=producer_id,
                parse_input_hash=parse_input_hash,
                candidate=candidate,
            )
        )
    )
    assert changed.id != original.id
    assert changed.identity_hash != original.identity_hash


def test_concurrent_same_identity_has_one_authoritative_parse(
    context: dict[str, object],
) -> None:
    service = context["service"]
    request = context["request"]
    factory = context["factory"]
    assert isinstance(service, DocumentParseService)
    assert isinstance(request, PersistDocumentParseRequest)
    barrier = threading.Barrier(2)
    records = []
    failures = []

    def persist() -> None:
        try:
            barrier.wait()
            records.append(asyncio.run(service.persist(request)))
        except Exception as exc:  # pragma: no cover - asserted below
            failures.append(exc)

    threads = [threading.Thread(target=persist) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert failures == []
    assert len(records) == 2
    assert len({record.id for record in records}) == 1
    with factory() as session:  # type: ignore[operator]
        assert session.scalar(
            select(func.count())
            .select_from(DocumentParseModel)
            .where(DocumentParseModel.project_id == request.project_id)
        ) == 1
        assert session.scalar(
            select(func.count())
            .select_from(DocumentParseLocatorModel)
            .where(DocumentParseLocatorModel.project_id == request.project_id)
        ) in {0, 1}
