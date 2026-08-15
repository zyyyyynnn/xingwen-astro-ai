from __future__ import annotations

import asyncio

import pytest

from app.services.content_storage import (
    ContentRangeNotSatisfiable,
    LocalContentStorage,
    sha256_content_hash,
)


def _collect(read):
    async def collect() -> list[bytes]:
        return [chunk async for chunk in read.chunks]

    return asyncio.run(collect())


def test_local_content_storage_streams_bounded_full_and_range_reads(tmp_path) -> None:
    content = b"x" * (2 * 1024 * 1024 + 17)
    content_hash = sha256_content_hash(content)
    storage = LocalContentStorage(tmp_path / "cas")
    asyncio.run(storage.store(content, content_hash))

    full = asyncio.run(storage.open_read(content_hash))
    assert full is not None
    full_chunks = _collect(full)
    assert b"".join(full_chunks) == content
    assert full.content_length == len(content)
    assert max(map(len, full_chunks)) <= 1024 * 1024

    ranged = asyncio.run(
        storage.open_read(content_hash, range_header="bytes=1048570-1048580")
    )
    assert ranged is not None
    assert ranged.start == 1_048_570
    assert ranged.end == 1_048_580
    assert ranged.total_size == len(content)
    assert b"".join(_collect(ranged)) == content[1_048_570:1_048_581]

    suffix = asyncio.run(storage.open_read(content_hash, range_header="bytes=-5"))
    assert suffix is not None
    assert suffix.start == len(content) - 5
    assert suffix.end == len(content) - 1
    assert b"".join(_collect(suffix)) == content[-5:]


def test_local_content_storage_rejects_invalid_or_unsatisfiable_ranges(
    tmp_path,
) -> None:
    content = b"0123456789"
    content_hash = sha256_content_hash(content)
    storage = LocalContentStorage(tmp_path / "cas")
    asyncio.run(storage.store(content, content_hash))

    for value in ("items=0-1", "bytes=0-1,2-3", "bytes=10-", "bytes=-0"):
        with pytest.raises(ContentRangeNotSatisfiable) as exc_info:
            asyncio.run(storage.open_read(content_hash, range_header=value))
        assert exc_info.value.total_size == len(content)


def test_local_content_storage_reports_missing_blob_without_opening_a_stream(
    tmp_path,
) -> None:
    storage = LocalContentStorage(tmp_path / "cas")

    assert (
        asyncio.run(storage.open_read("sha256:" + "a" * 64, range_header="bytes=0-1"))
        is None
    )
