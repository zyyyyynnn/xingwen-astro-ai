"""Unit tests for the research-input contract.

Covers the schemas, MIME sniffing, filename sanitization, the in-memory
ownership store and the content-addressed storage port — everything that does
not need HTTP or PostgreSQL.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from pydantic import TypeAdapter, ValidationError

from app.schemas.research_input import (
    BindResearchInputRequest,
    CreateResearchInputRequest,
    FILE_INPUT_TYPES,
    ResearchInputCreate,
    ResearchInputType,
)
from app.security import SecurityProblem
from app.services.content_storage import (
    ContentStorageError,
    LocalContentStorage,
    sha256_content_hash,
)
from app.services.research_input_policy import (
    filename_extension_matches,
    sanitize_filename,
    sniff_mime_type,
    validate_declared_mime,
)
from app.services.research_input_store import (
    InMemoryIdempotencyRepository,
    InMemoryResearchInputStore,
    PreparedInput,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _xlsx_bytes() -> bytes:
    from openpyxl import Workbook

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append(("row_id", "temperature"))
    worksheet.append(("star-a", 5100))
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def _parquet_bytes() -> bytes:
    import pyarrow as pa
    import pyarrow.parquet as pq

    output = BytesIO()
    pq.write_table(pa.table({"row_id": ["star-a"], "temperature": [5100]}), output)
    return output.getvalue()


def _xlsx_archive(*, extra_name: str, extra_content: bytes) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr("xl/workbook.xml", "<workbook />")
        archive.writestr(extra_name, extra_content)
    return output.getvalue()


def _zip_bytes() -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("labels.json", b'{"schema_version":"1.0.0","images":[]}')
    return output.getvalue()


def _text_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "type": "text",
        "text_content": "hello research composer",
    }
    payload.update(overrides)
    return payload


# ---- schema composition ----------------------------------------------------


_CREATE_ADAPTER = TypeAdapter(CreateResearchInputRequest)


def test_create_text_input_is_valid_without_extras() -> None:
    request = _CREATE_ADAPTER.validate_python(
        {"project_id": "proj_01", "type": "text", "text_content": "hello"}
    )
    assert request.type is ResearchInputType.text


def test_url_input_requires_url_and_forbids_text_content() -> None:
    with pytest.raises(ValidationError, match=r"url\.url"):
        _CREATE_ADAPTER.validate_python(
            {"project_id": "proj_01", "type": "url", "text_content": "nope"}
        )
    with pytest.raises(ValidationError, match="text_content"):
        _CREATE_ADAPTER.validate_python(
            {
                "project_id": "proj_01",
                "type": "url",
                "url": "https://example.com/data.csv",
                "text_content": "nope",
            }
        )


def test_text_input_forbids_url() -> None:
    with pytest.raises(ValidationError, match=r"text\.text_content"):
        _CREATE_ADAPTER.validate_python({"project_id": "proj_01", "type": "text"})
    with pytest.raises(ValidationError, match=r"text\.url"):
        _CREATE_ADAPTER.validate_python(
            {
                "project_id": "proj_01",
                "type": "text",
                "text_content": "hello",
                "url": "https://example.com",
            }
        )


def test_file_types_forbid_url_and_text_content() -> None:
    for value in (
        "pdf",
        "csv",
        "xlsx",
        "parquet",
        "json",
        "image",
        "image_dataset",
        "fits",
    ):
        with pytest.raises(ValidationError, match="union_tag_invalid"):
            _CREATE_ADAPTER.validate_python(
                {
                    "project_id": "proj_01",
                    "type": value,
                    "url": "https://example.com/file.pdf",
                }
            )
    assert all(
        ResearchInputType(value) in FILE_INPUT_TYPES
        for value in (
            "pdf",
            "csv",
            "xlsx",
            "parquet",
            "json",
            "image",
            "image_dataset",
            "fits",
        )
    )


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        _CREATE_ADAPTER.validate_python(
            {
                "project_id": "proj_01",
                "type": "text",
                "text_content": "x",
                "session_token": "s",
            }
        )


def test_bind_request_expresses_xor_without_a_runtime_validator() -> None:
    adapter = TypeAdapter(BindResearchInputRequest)
    with pytest.raises(ValidationError):
        adapter.validate_python({"project_id": "proj_01"})
    with pytest.raises(ValidationError):
        adapter.validate_python(
            {
                "project_id": "proj_01",
                "contract_draft_id": "draft_01",
                "run_id": "run_01",
            }
        )
    contract = adapter.validate_python(
        {"project_id": "proj_01", "contract_draft_id": "draft_01"}
    )
    assert contract.contract_draft_id == "draft_01"
    assert contract.run_id is None
    run = adapter.validate_python({"project_id": "proj_01", "run_id": "run_01"})
    assert run.run_id == "run_01"
    assert run.contract_draft_id is None


# ---- MIME sniffing ---------------------------------------------------------


def test_sniff_mime_recognizes_magic_bytes() -> None:
    assert sniff_mime_type((FIXTURES / "sample.pdf").read_bytes()) == "application/pdf"
    assert sniff_mime_type((FIXTURES / "sample.png").read_bytes()) == "image/png"
    assert sniff_mime_type(b"\xff\xd8\xff\xe0test") == "image/jpeg"
    assert sniff_mime_type(b"GIF89a...") == "image/gif"
    assert sniff_mime_type(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "image/webp"
    assert sniff_mime_type((FIXTURES / "sample.json").read_bytes()) == "application/json"
    assert sniff_mime_type((FIXTURES / "sample.csv").read_bytes()) == "text/csv"
    assert (
        sniff_mime_type(b"SIMPLE  =                    T" + b" " * 80)
        == "application/fits"
    )
    assert sniff_mime_type(_xlsx_bytes()) == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert sniff_mime_type(_parquet_bytes()) == "application/vnd.apache.parquet"
    assert sniff_mime_type(_zip_bytes()) == "application/zip"
    assert sniff_mime_type(b"just some plain words\n") == "text/plain"


def test_sniff_mime_rejects_binary_and_unknown() -> None:
    assert sniff_mime_type(b"\x00\x01\x02\x03\x04binary") is None
    assert sniff_mime_type(b"") is None


@pytest.mark.parametrize(
    "archive",
    [
        b"PK\x03\x04" + b"../../outside.csv" + b"A" * 128,
        b"\x1f\x8b" + b"A" * 128,
        b"BZh91AY&SY" + b"A" * 128,
        b"7z\xbc\xaf\x27\x1c" + b"A" * 128,
        b"Rar!\x1a\x07\x01\x00" + b"A" * 128,
        b"!<arch>\n" + b"A" * 128,
        b"archive.txt".ljust(257, b"\x00") + b"ustar" + b"A" * 128,
    ],
)
def test_archive_magic_is_rejected_before_any_extraction(archive: bytes) -> None:
    # ResearchInput has no archive type or extraction path. A ZIP-shaped body,
    # including a traversal-like member name, must fail MIME admission instead
    # of reaching any path normalization or decompression behavior.
    assert sniff_mime_type(archive) is None


@pytest.mark.parametrize("case", ["macro", "external", "traversal", "bomb"])
def test_xlsx_admission_rejects_active_external_or_bomb_content(
    case: str,
) -> None:
    member_name, content = {
        "macro": ("xl/vbaProject.bin", b"macro"),
        "external": ("xl/externalLinks/externalLink1.xml", b"external"),
        "traversal": ("../outside.xml", b"traversal"),
        "bomb": ("xl/worksheets/sheet1.xml", b"A" * 1_000_000),
    }[case]
    assert (
        sniff_mime_type(
            _xlsx_archive(extra_name=member_name, extra_content=content)
        )
        is None
    )


def test_validate_declared_mime_requires_type_and_client_agreement() -> None:
    csv = (FIXTURES / "sample.csv").read_bytes()
    sniffed = sniff_mime_type(csv)
    allowed = frozenset({"text/csv", "text/plain", "application/pdf"})
    assert sniffed == "text/csv"
    assert validate_declared_mime(
        declared_type=ResearchInputType.csv,
        sniffed_mime=sniffed,
        client_mime=None,
        allowed_mimes=allowed,
    ) == "text/csv"
    assert (
        validate_declared_mime(
            declared_type=ResearchInputType.pdf,
            sniffed_mime=sniffed,
            client_mime=None,
            allowed_mimes=allowed,
        )
        is None
    )
    assert (
        validate_declared_mime(
            declared_type=ResearchInputType.csv,
            sniffed_mime=sniffed,
            client_mime="text/plain",
            allowed_mimes=allowed,
        )
        is None
    )
    assert (
        validate_declared_mime(
            declared_type=ResearchInputType.csv,
            sniffed_mime=sniffed,
            client_mime=None,
            allowed_mimes=frozenset({"application/pdf"}),
        )
        is None
    )


@pytest.mark.parametrize("markdown_mime", ["text/markdown", "text/x-markdown"])
def test_markdown_uses_declared_semantic_mime_after_utf8_text_sniff(
    markdown_mime: str,
) -> None:
    content = b"# Observations\n\nA bounded Markdown document.\n"
    sniffed = sniff_mime_type(content)
    assert sniffed == "text/plain"
    assert validate_declared_mime(
        declared_type=ResearchInputType.text,
        sniffed_mime=sniffed,
        client_mime=markdown_mime,
        allowed_mimes=frozenset({"text/plain", markdown_mime}),
    ) == markdown_mime
    assert filename_extension_matches("paper.md", markdown_mime)


def test_markdown_declaration_cannot_relabel_non_text_bytes() -> None:
    assert (
        validate_declared_mime(
            declared_type=ResearchInputType.text,
            sniffed_mime="application/pdf",
            client_mime="text/markdown",
            allowed_mimes=frozenset({"text/markdown"}),
        )
        is None
    )


# ---- filename sanitization -------------------------------------------------


def test_sanitize_filename_strips_traversal_and_keeps_basename() -> None:
    assert sanitize_filename("../../etc/passwd.pdf") == "passwd.pdf"
    assert sanitize_filename("..\\..\\windows\\evil.exe") == "evil.exe"
    assert sanitize_filename("a/b/c.csv") == "c.csv"
    assert sanitize_filename("  report  .csv  ") == "report  .csv"


def test_sanitize_filename_rejects_unusable_names() -> None:
    assert sanitize_filename(None) is None
    assert sanitize_filename("") is None
    assert sanitize_filename("   ") is None
    assert sanitize_filename(".") is None
    assert sanitize_filename("..") is None
    assert sanitize_filename("a" * 256) is None
    assert sanitize_filename("\x00\x01\x02evil.pdf") == "evil.pdf"


def test_filename_extension_matches_mime() -> None:
    assert filename_extension_matches("planets.csv", "text/csv") is True
    assert filename_extension_matches("planets.csv", "application/pdf") is False
    assert filename_extension_matches("notes", "text/csv") is True
    assert filename_extension_matches("photo.jpg", "image/jpeg") is True
    assert filename_extension_matches("training.zip", "application/zip") is True
    assert filename_extension_matches("image.fits", "application/fits") is True
    assert filename_extension_matches("image.fit", "application/fits") is True
    assert filename_extension_matches("image.fits", "application/pdf") is False
    assert filename_extension_matches(
        "measurements.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    assert filename_extension_matches(
        "measurements.parquet", "application/vnd.apache.parquet"
    )


# ---- in-memory store -------------------------------------------------------


def _prepared(*, content: bytes = b"abc", **overrides: object) -> PreparedInput:
    prepared: dict[str, object] = {
        "content_hash": sha256_content_hash(content),
        "storage_ref": "aa/aaaaaaaaaaaaaaaa",
        "size_bytes": len(content),
        "mime_type": "text/plain",
        "filename": "notes.txt",
        "source_snapshot": None,
    }
    prepared.update(overrides)
    return PreparedInput(**prepared)  # type: ignore[arg-type]


def test_in_memory_store_scopes_records_to_session_and_project() -> None:
    store = InMemoryResearchInputStore()
    store.register_project(project_id="proj_01", owner_session_id="session_a")
    store.register_project(project_id="proj_02", owner_session_id="session_a")
    store.register_project(project_id="proj_03", owner_session_id="session_b")

    created = store.commit_ingestion(
        session_id="session_a",
        project_id="proj_01",
        payload=ResearchInputCreate(type="text", text_content="hello"),
        prepared=_prepared(),
        idempotency_key="k1",
        lease_token="tok1",
        request_hash="h1",
    )
    assert created.source_type == "text"

    assert store.get(session_id="session_a", input_id=created.id) is not None
    assert store.get(session_id="session_b", input_id=created.id) is None

    refs, _, _ = store.list(session_id="session_a", project_id="proj_01", cursor=None, limit=20)
    assert [ref.id for ref in refs] == [created.id]
    refs_other_project, _, _ = store.list(
        session_id="session_a", project_id="proj_02", cursor=None, limit=20
    )
    assert refs_other_project == ()
    refs_other_session, _, _ = store.list(
        session_id="session_b", project_id="proj_03", cursor=None, limit=20
    )
    assert refs_other_session == ()

    with pytest.raises(SecurityProblem) as exc:
        store.require_owned_project(session_id="session_a", project_id="proj_03")
    assert exc.value.code == "PROJECT_NOT_FOUND"


def test_in_memory_store_same_content_makes_distinct_ingestions() -> None:
    # Content identity (content_hash) is deduped, but ingestion identity is not:
    # the same bytes ingested twice are two immutable ResearchInput rows that
    # share one content blob.
    store = InMemoryResearchInputStore()
    store.register_project(project_id="proj_01", owner_session_id="session_a")
    prepared = _prepared(content=b"same bytes")
    first = store.commit_ingestion(
        session_id="session_a",
        project_id="proj_01",
        payload=ResearchInputCreate(type="text", text_content="same bytes"),
        prepared=prepared,
        idempotency_key="k1",
        lease_token="tok1",
        request_hash="h1",
    )
    second = store.commit_ingestion(
        session_id="session_a",
        project_id="proj_01",
        payload=ResearchInputCreate(type="text", text_content="same bytes"),
        prepared=prepared,
        idempotency_key="k2",
        lease_token="tok2",
        request_hash="h2",
    )
    assert second.id != first.id
    assert second.content_hash == first.content_hash
    refs, _, _ = store.list(session_id="session_a", project_id="proj_01", cursor=None, limit=20)
    assert {ref.id for ref in refs} == {first.id, second.id}


def test_in_memory_store_soft_delete_creates_new_ingestion_on_replay() -> None:
    store = InMemoryResearchInputStore()
    store.register_project(project_id="proj_01", owner_session_id="session_a")
    created = store.commit_ingestion(
        session_id="session_a",
        project_id="proj_01",
        payload=ResearchInputCreate(type="text", text_content="hello"),
        prepared=_prepared(),
        idempotency_key="k1",
        lease_token="tok1",
        request_hash="h1",
    )
    store.delete(session_id="session_a", input_id=created.id)
    assert store.get(session_id="session_a", input_id=created.id) is None
    refs, _, _ = store.list(session_id="session_a", project_id="proj_01", cursor=None, limit=20)
    assert refs == ()
    with pytest.raises(SecurityProblem) as exc:
        store.delete(session_id="session_a", input_id=created.id)
    assert exc.value.code == "RESEARCH_INPUT_NOT_FOUND"

    # A new ingestion under a new key creates a NEW input; it never resurrects
    # or mutates the expired one.
    fresh = store.commit_ingestion(
        session_id="session_a",
        project_id="proj_01",
        payload=ResearchInputCreate(type="text", text_content="hello"),
        prepared=_prepared(),
        idempotency_key="k2",
        lease_token="tok2",
        request_hash="h2",
    )
    assert fresh.id != created.id
    assert fresh.content_hash == created.content_hash
    assert store.get(session_id="session_a", input_id=fresh.id) is not None


def test_in_memory_store_bind_requires_owned_targets() -> None:
    store = InMemoryResearchInputStore()
    store.register_project(project_id="proj_01", owner_session_id="session_a")
    store.register_project(project_id="proj_02", owner_session_id="session_b")
    store.register_contract_draft(draft_id="draft_01", owner_session_id="session_a")
    store.register_run(run_id="run_01", project_id="proj_01")
    store.register_run(run_id="run_02", project_id="proj_02")

    created = store.commit_ingestion(
        session_id="session_a",
        project_id="proj_01",
        payload=ResearchInputCreate(type="text", text_content="hello"),
        prepared=_prepared(),
        idempotency_key="k1",
        lease_token="tok1",
        request_hash="h1",
    )
    store.bind_to_contract(
        session_id="session_a",
        input_id=created.id,
        project_id="proj_01",
        contract_draft_id="draft_01",
    )
    store.bind_to_run(
        session_id="session_a",
        input_id=created.id,
        project_id="proj_01",
        run_id="run_01",
    )
    with pytest.raises(SecurityProblem) as exc:
        store.bind_to_contract(
            session_id="session_a",
            input_id=created.id,
            project_id="proj_01",
            contract_draft_id="draft_missing",
        )
    assert exc.value.code == "RESOURCE_NOT_FOUND"
    with pytest.raises(SecurityProblem) as exc:
        store.bind_to_run(
            session_id="session_a",
            input_id=created.id,
            project_id="proj_01",
            run_id="run_02",
        )
    assert exc.value.code == "RESOURCE_NOT_FOUND"


# ---- idempotency lease state machine --------------------------------------


def _owned_store_and_idempotency() -> tuple[InMemoryResearchInputStore, InMemoryIdempotencyRepository]:
    store = InMemoryResearchInputStore()
    idem = InMemoryIdempotencyRepository(lease_ttl=timedelta(seconds=300))
    store.bind_idempotency(idem)
    store.register_project(project_id="proj_01", owner_session_id="session_a")
    return store, idem


def test_pending_reservation_blocks_distinct_request_under_same_key() -> None:
    store, idem = _owned_store_and_idempotency()
    first = idem.resolve(
        session_id="session_a", project_id="proj_01", idempotency_key="k1", request_hash="h1"
    )
    assert first.reserved is True and first.lease_token is not None

    # An identical request arriving while the lease is still valid must not
    # duplicate the side effect -- it is told to wait (409), not handed a lease.
    with pytest.raises(SecurityProblem) as exc:
        idem.resolve(
            session_id="session_a", project_id="proj_01", idempotency_key="k1", request_hash="h1"
        )
    assert exc.value.code == "IDEMPOTENCY_IN_PROGRESS"


def test_stale_pending_reservation_is_reclaimed_by_another_request() -> None:
    from datetime import datetime, timedelta

    store, idem = _owned_store_and_idempotency()
    old = idem.resolve(
        session_id="session_a", project_id="proj_01", idempotency_key="k1", request_hash="h1"
    )
    assert old.reserved is True and old.lease_token is not None

    # Simulate the lease lapsing, then the *same* request reuses the key.
    class FrozenClock:
        def __init__(self, when: datetime) -> None:
            self._when = when

        def __call__(self) -> datetime:
            return self._when

    idem._clock = FrozenClock(old.lease_expires_at + timedelta(seconds=1))  # type: ignore[attr-defined]
    reclaimed = idem.resolve(
        session_id="session_a", project_id="proj_01", idempotency_key="k1", request_hash="h1"
    )
    assert reclaimed.reserved is True
    assert reclaimed.lease_token is not None
    assert reclaimed.lease_token != old.lease_token


def test_lease_commit_is_token_bound() -> None:
    store, idem = _owned_store_and_idempotency()
    res = idem.resolve(
        session_id="session_a", project_id="proj_01", idempotency_key="k1", request_hash="h1"
    )
    # A stale/foreign token cannot complete or release the reservation.
    with pytest.raises(SecurityProblem):
        idem.complete_reservation(
            session_id="session_a",
            project_id="proj_01",
            idempotency_key="k1",
            lease_token="wrong-token",
            input_id="input_x",
        )
    with pytest.raises(SecurityProblem):
        idem.release(
            session_id="session_a",
            project_id="proj_01",
            idempotency_key="k1",
            lease_token="wrong-token",
        )
    # The rightful owner completes it; afterwards the key is replayable.
    idem.complete_reservation(
        session_id="session_a",
        project_id="proj_01",
        idempotency_key="k1",
        lease_token=res.lease_token,
        input_id="input_x",
    )
    replay = idem.resolve(
        session_id="session_a", project_id="proj_01", idempotency_key="k1", request_hash="h1"
    )
    assert replay.replayed_input_id == "input_x"


def test_ownership_gate_runs_before_any_idempotency_side_effect() -> None:
    # require_owned_project must fail with 404 before a reservation is created,
    # so a probing request leaves no pending row behind.
    store, idem = _owned_store_and_idempotency()
    with pytest.raises(SecurityProblem) as exc:
        store.require_owned_project(session_id="session_a", project_id="foreign")
    assert exc.value.code == "PROJECT_NOT_FOUND"
    assert idem.resolve(
        session_id="session_a", project_id="foreign", idempotency_key="probe", request_hash="h"
    ).reserved is True


def test_cross_source_ingestion_separation_text_and_upload_share_content() -> None:
    # The same bytes arriving via `text` and via `pdf` upload are two ingestions
    # but one content identity -- provenance (source_type) differs, while the
    # content facts (hash/ref/mime/size) are identical because they derive from
    # the bytes.
    store, _idem = _owned_store_and_idempotency()
    payload = b"identical research bytes"
    content_facts = dict(content=payload, mime_type="application/pdf", filename="note.pdf")
    text_ing = store.commit_ingestion(
        session_id="session_a",
        project_id="proj_01",
        payload=ResearchInputCreate(type="text", text_content=payload.decode()),
        prepared=_prepared(**content_facts),
        idempotency_key="kt",
        lease_token="t1",
        request_hash="ht",
    )
    upload_ing = store.commit_ingestion(
        session_id="session_a",
        project_id="proj_01",
        payload=ResearchInputCreate(type="pdf"),
        prepared=_prepared(**content_facts),
        idempotency_key="ku",
        lease_token="t2",
        request_hash="hu",
    )
    assert text_ing.id != upload_ing.id
    assert text_ing.content_hash == upload_ing.content_hash
    assert text_ing.source_type == "text"
    assert upload_ing.source_type == "upload"



def test_local_content_storage_is_content_addressed_and_immutable(
    tmp_path: Path,
) -> None:
    storage = LocalContentStorage(tmp_path)
    content = b"immutable payload"
    content_hash = sha256_content_hash(content)
    hex_value = content_hash.removeprefix("sha256:")
    expected_ref = f"{hex_value[:2]}/{hex_value}"

    assert storage.exists(content_hash) is False
    stored = asyncio.run(storage.store(content, content_hash))
    assert stored == expected_ref
    assert storage.exists(content_hash) is True
    assert asyncio.run(storage.retrieve(content_hash)) == content

    again = asyncio.run(storage.store(content, content_hash))
    assert again == stored

    with pytest.raises(ValueError, match="does not match"):
        asyncio.run(
            storage.store(b"different", sha256_content_hash(b"something else"))
        )


def test_sha256_content_hash_has_canonical_shape() -> None:
    value = sha256_content_hash(b"x")
    assert value.startswith("sha256:")
    assert len(value) == 71


# ---- content storage invariants --------------------------------------------


def test_storage_publish_never_replaces_an_existing_blob(tmp_path: Path) -> None:
    """A published blob is immutable: republishing must not rewrite the file."""

    storage = LocalContentStorage(tmp_path)
    content = b"publish once"
    content_hash = sha256_content_hash(content)
    ref = asyncio.run(storage.store(content, content_hash))

    blob = tmp_path / ref
    inode_before = blob.stat().st_ino
    mtime_before = blob.stat().st_mtime_ns

    assert asyncio.run(storage.store(content, content_hash)) == ref
    assert blob.stat().st_ino == inode_before
    assert blob.stat().st_mtime_ns == mtime_before
    assert blob.read_bytes() == content


def test_storage_concurrent_writers_produce_one_valid_blob(tmp_path: Path) -> None:
    storage = LocalContentStorage(tmp_path)
    content = b"concurrent payload" * 64
    content_hash = sha256_content_hash(content)

    async def run_all() -> list[str]:
        return list(
            await asyncio.gather(
                *(storage.store(content, content_hash) for _ in range(12))
            )
        )

    refs = asyncio.run(run_all())
    assert len(set(refs)) == 1

    blob = tmp_path / refs[0]
    assert blob.read_bytes() == content
    assert sha256_content_hash(blob.read_bytes()) == content_hash
    # Exactly one published blob, and no temp files left behind.
    assert sorted(p.name for p in blob.parent.iterdir()) == [blob.name]


def test_storage_repairs_a_corrupt_final_blob(tmp_path: Path) -> None:
    storage = LocalContentStorage(tmp_path)
    content = b"the real bytes"
    content_hash = sha256_content_hash(content)
    ref = asyncio.run(storage.store(content, content_hash))
    blob = tmp_path / ref

    blob.write_bytes(b"corrupted junk")
    assert sha256_content_hash(blob.read_bytes()) != content_hash

    assert asyncio.run(storage.store(content, content_hash)) == ref
    assert blob.read_bytes() == content
    assert sha256_content_hash(blob.read_bytes()) == content_hash


def test_storage_read_failure_never_deletes_the_blob(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A permission fault is an environment error, not proof of corruption."""

    storage = LocalContentStorage(tmp_path)
    content = b"protected bytes"
    content_hash = sha256_content_hash(content)
    ref = asyncio.run(storage.store(content, content_hash))
    blob = tmp_path / ref

    def deny(self: Path, *args, **kwargs):  # noqa: ANN002, ANN003
        raise PermissionError("read denied")

    monkeypatch.setattr(Path, "open", deny)
    with pytest.raises(ContentStorageError, match="unable to read existing blob"):
        asyncio.run(storage.store(content, content_hash))

    monkeypatch.undo()
    assert blob.is_file()
    assert blob.read_bytes() == content


def test_storage_leaves_no_temp_files_when_publication_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage = LocalContentStorage(tmp_path)
    content = b"never lands"
    content_hash = sha256_content_hash(content)

    def boom(temp: Path, final: Path) -> bool:
        raise OSError("publish failed")

    monkeypatch.setattr(
        "app.services.content_storage._publish_no_replace", boom
    )
    with pytest.raises(OSError, match="publish failed"):
        asyncio.run(storage.store(content, content_hash))

    monkeypatch.undo()
    leftovers = [p.name for p in tmp_path.rglob(".tmp_*")]
    assert leftovers == []


@pytest.mark.parametrize(
    "bad_hash",
    [
        "sha256:" + "A" * 64,
        "sha256:" + "a" * 63,
        "sha256:" + "z" * 64,
        "sha256:../../etc/passwd",
        "a" * 64,
        "",
    ],
)
def test_storage_rejects_malformed_content_hashes(
    tmp_path: Path, bad_hash: str
) -> None:
    storage = LocalContentStorage(tmp_path)
    with pytest.raises((ValueError, ContentStorageError)):
        asyncio.run(storage.store(b"payload", bad_hash))
