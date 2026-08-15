from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.config import settings
from app.main import create_app
from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.core import (
    ArtifactVersionDetail,
    ResearchArtifactDetail,
    SourceSnapshotDetail,
)
from app.schemas.scientific_artifact_api import ScientificArtifactRead
from app.schemas.scientific_skills import (
    VisualizationArtifactContent,
    scientific_artifact_output_hash,
)
from app.security import SecurityProblem
from app.services.content_storage import (
    ContentRangeNotSatisfiable,
    ContentRead,
    ContentStorageError,
    sha256_content_hash,
)
from services.scientific_skills.demo_fixture import build_scientific_fixture_document


NOW = datetime(2026, 8, 14, 8, 0, tzinfo=UTC)


def _fixture_version(kind: str = "analysis_report") -> ArtifactVersionDetail:
    entry = next(
        item
        for item in build_scientific_fixture_document()["entries"]
        if item["version"]["content"]["kind"] == kind
    )
    return ArtifactVersionDetail.model_validate(entry["version"])


class _Artifacts:
    def __init__(
        self,
        version: ArtifactVersionDetail,
        *,
        artifact_kind: str | None = None,
    ) -> None:
        self.version = version
        self.artifact_kind = artifact_kind or str(version.content["kind"])

    def get_version(
        self, *, version_id: str, session_id: str, full_content: bool = False
    ) -> ArtifactVersionDetail:
        assert full_content is True
        if session_id != "owner" or version_id != self.version.id:
            raise SecurityProblem(
                status=404,
                code="ARTIFACT_VERSION_NOT_FOUND",
                title="Resource not found",
                detail="Resource not found",
            )
        return self.version

    def get_artifact(
        self, *, artifact_id: str, session_id: str
    ) -> ResearchArtifactDetail:
        if session_id != "owner" or artifact_id != self.version.artifact_id:
            raise SecurityProblem(
                status=404,
                code="ARTIFACT_NOT_FOUND",
                title="Resource not found",
                detail="Resource not found",
            )
        return ResearchArtifactDetail(
            id=self.version.artifact_id,
            project_id=self.version.project_id,
            kind=self.artifact_kind,
            title="Scientific artifact",
            logical_key="scientific.primary",
            created_at=self.version.created_at,
            latest_version_id=self.version.id,
            versions=(),
        )


class _ContentStorage:
    def __init__(self, content: dict[str, bytes] | None = None) -> None:
        self.content = content or {}

    async def retrieve(self, content_hash: str) -> bytes | None:
        return self.content.get(content_hash)

    async def open_read(
        self, content_hash: str, *, range_header: str | None = None
    ) -> ContentRead | None:
        content = self.content.get(content_hash)
        if content is None:
            return None
        start, end = _range_bounds(range_header, len(content))

        async def chunks():
            for offset in range(start, end + 1, 3):
                yield content[offset : min(offset + 3, end + 1)]

        return ContentRead(
            start=start,
            end=end,
            total_size=len(content),
            chunks=chunks(),
        )


class _FailingContentStorage(_ContentStorage):
    async def open_read(
        self, content_hash: str, *, range_header: str | None = None
    ) -> ContentRead | None:
        raise ContentStorageError("storage unavailable")


def _range_bounds(range_header: str | None, total_size: int) -> tuple[int, int]:
    if range_header is None:
        return (0, total_size - 1) if total_size else (0, -1)
    value = range_header.removeprefix("bytes=")
    first, last = value.split("-", maxsplit=1)
    if not first:
        length = min(int(last), total_size)
        if length <= 0 or total_size == 0:
            raise ContentRangeNotSatisfiable(total_size=total_size)
        return total_size - length, total_size - 1
    start = int(first)
    end = min(int(last), total_size - 1) if last else total_size - 1
    if start >= total_size or end < start:
        raise ContentRangeNotSatisfiable(total_size=total_size)
    return start, end


def _client(
    artifacts: _Artifacts,
    *,
    storage: _ContentStorage | None = None,
) -> TestClient:
    app = create_app()
    app.state.artifact_read_service = artifacts  # type: ignore[assignment]
    app.state.content_storage = storage or _ContentStorage()
    owner, credential, _ = app.state.session_service.create(now=datetime.now(UTC))
    app.state.session_service.store.put(replace(owner, id="owner"))
    client = TestClient(app)
    client.cookies.set(settings.SESSION_COOKIE_NAME, credential, path="/api")
    return client


def _fits_version(content: bytes) -> ArtifactVersionDetail:
    base = _fixture_version("visualization")
    content_hash = sha256_content_hash(content)
    payload = deepcopy(base.content)
    payload.update(
        {
            "visualization_id": "visualization.fits",
            "title": "Project-owned FITS image",
            "spec": {
                "mode": "fits_image",
                "source_snapshot_id": "snapshot.fits",
                "content_ref": f"memory/{content_hash.removeprefix('sha256:')}",
                "content_hash": content_hash,
                "stretch": "sqrt",
                "color_map": "gray",
            },
            "source_snapshot_ids": ["snapshot.fits"],
            "output_hash": "sha256:" + "0" * 64,
        }
    )
    draft = VisualizationArtifactContent.model_validate(
        payload,
        context={"skip_scientific_output_hash_validation": True},
    )
    payload["output_hash"] = scientific_artifact_output_hash(draft)
    scientific = VisualizationArtifactContent.model_validate(payload)
    content_payload = scientific.model_dump(mode="json")
    version_hash = compute_canonical_payload_hash(content_payload)
    snapshot = SourceSnapshotDetail(
        id="snapshot.fits",
        source_id="skyview",
        source_type="fixture",
        retrieved_at=NOW,
        query={"position": "Andromeda Galaxy"},
        query_hash="sha256:" + "e" * 64,
        content_hash=content_hash,
        license_note="Fixture FITS content.",
        request_metadata={},
    )
    execution = base.producer_execution.model_copy(update={"output_hash": version_hash})
    return base.model_copy(
        update={
            "schema_version": scientific.schema_version,
            "content": content_payload,
            "content_hash": version_hash,
            "source_snapshot_ids": (snapshot.id,),
            "source_snapshots": (snapshot,),
            "producer_execution": execution,
        }
    )


def test_scientific_artifact_endpoint_returns_current_typed_read() -> None:
    version = _fixture_version()
    response = _client(_Artifacts(version)).get(
        f"/api/artifact-versions/{version.id}/scientific"
    )

    assert response.status_code == 200
    read = ScientificArtifactRead.model_validate(response.json()["data"])
    assert read.artifact_version_id == version.id
    assert read.content.kind.value == "analysis_report"
    assert response.headers["cache-control"] == "no-store"


def test_scientific_artifact_endpoint_rejects_hash_drift_and_wrong_kind() -> None:
    version = _fixture_version()
    tampered = version.model_copy(
        update={"content": {**version.content, "title": "Tampered"}}
    )
    response = _client(_Artifacts(tampered)).get(
        f"/api/artifact-versions/{version.id}/scientific"
    )
    assert response.status_code == 409
    assert response.json()["code"] == "SCIENTIFIC_ARTIFACT_INTEGRITY"

    response = _client(_Artifacts(version, artifact_kind="dataset")).get(
        f"/api/artifact-versions/{version.id}/scientific"
    )
    assert response.status_code == 409
    assert response.json()["code"] == "ARTIFACT_KIND_MISMATCH"


def test_scientific_artifact_endpoint_requires_owner_session() -> None:
    version = _fixture_version()
    app = create_app()
    app.state.artifact_read_service = _Artifacts(version)  # type: ignore[assignment]
    assert (
        TestClient(app)
        .get(f"/api/artifact-versions/{version.id}/scientific")
        .status_code
        == 401
    )

    other, credential, _ = app.state.session_service.create(now=datetime.now(UTC))
    app.state.session_service.store.put(replace(other, id="other"))
    client = TestClient(app)
    client.cookies.set(settings.SESSION_COOKIE_NAME, credential, path="/api")
    response = client.get(f"/api/artifact-versions/{version.id}/scientific")
    assert response.status_code == 404
    assert response.json()["code"] == "ARTIFACT_VERSION_NOT_FOUND"


def test_scientific_content_endpoint_serves_only_declared_content_hash() -> None:
    content = b"SIMPLE  =                    T"
    version = _fits_version(content)
    content_hash = sha256_content_hash(content)
    client = _client(
        _Artifacts(version),
        storage=_ContentStorage({content_hash: content}),
    )

    response = client.get(
        f"/api/artifact-versions/{version.id}/scientific/content/{content_hash}"
    )
    assert response.status_code == 200
    assert response.content == content
    assert response.headers["content-type"].startswith("application/fits")
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["content-length"] == str(len(content))
    assert response.headers["cache-control"] == ("private, immutable, max-age=31536000")

    undeclared = "sha256:" + "f" * 64
    response = client.get(
        f"/api/artifact-versions/{version.id}/scientific/content/{undeclared}"
    )
    assert response.status_code == 404
    assert response.json()["code"] == "SCIENTIFIC_CONTENT_NOT_FOUND"


def test_scientific_content_endpoint_streams_single_byte_ranges() -> None:
    content = b"0123456789"
    version = _fits_version(content)
    content_hash = sha256_content_hash(content)
    client = _client(
        _Artifacts(version),
        storage=_ContentStorage({content_hash: content}),
    )

    response = client.get(
        f"/api/artifact-versions/{version.id}/scientific/content/{content_hash}",
        headers={"Range": "bytes=2-5"},
    )
    assert response.status_code == 206
    assert response.content == b"2345"
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["content-range"] == "bytes 2-5/10"
    assert response.headers["content-length"] == "4"

    response = client.get(
        f"/api/artifact-versions/{version.id}/scientific/content/{content_hash}",
        headers={"Range": "bytes=-3"},
    )
    assert response.status_code == 206
    assert response.content == b"789"
    assert response.headers["content-range"] == "bytes 7-9/10"

    response = client.get(
        f"/api/artifact-versions/{version.id}/scientific/content/{content_hash}",
        headers={"Range": "bytes=8-999"},
    )
    assert response.status_code == 206
    assert response.content == b"89"
    assert response.headers["content-range"] == "bytes 8-9/10"


def test_scientific_content_endpoint_rejects_unsatisfiable_range() -> None:
    content = b"0123456789"
    version = _fits_version(content)
    content_hash = sha256_content_hash(content)
    client = _client(
        _Artifacts(version),
        storage=_ContentStorage({content_hash: content}),
    )

    response = client.get(
        f"/api/artifact-versions/{version.id}/scientific/content/{content_hash}",
        headers={"Range": "bytes=99-"},
    )
    assert response.status_code == 416
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["content-range"] == "bytes */10"
    assert response.json()["code"] == "SCIENTIFIC_CONTENT_RANGE_NOT_SATISFIABLE"


def test_scientific_content_endpoint_fails_closed_on_storage_error() -> None:
    content = b"0123456789"
    version = _fits_version(content)
    content_hash = sha256_content_hash(content)
    client = _client(
        _Artifacts(version),
        storage=_FailingContentStorage({content_hash: content}),
    )

    response = client.get(
        f"/api/artifact-versions/{version.id}/scientific/content/{content_hash}"
    )
    assert response.status_code == 409
    assert response.json()["code"] == "SCIENTIFIC_ARTIFACT_INTEGRITY"


def test_scientific_content_endpoint_checks_ownership_before_opening_range() -> None:
    content = b"0123456789"
    version = _fits_version(content)
    content_hash = sha256_content_hash(content)
    app = create_app()
    app.state.artifact_read_service = _Artifacts(version)  # type: ignore[assignment]
    app.state.content_storage = _ContentStorage({content_hash: content})
    other, credential, _ = app.state.session_service.create(now=datetime.now(UTC))
    app.state.session_service.store.put(replace(other, id="other"))
    client = TestClient(app)
    client.cookies.set(settings.SESSION_COOKIE_NAME, credential, path="/api")

    response = client.get(
        f"/api/artifact-versions/{version.id}/scientific/content/{content_hash}",
        headers={"Range": "bytes=0-1"},
    )
    assert response.status_code == 404
    assert response.json()["code"] == "ARTIFACT_VERSION_NOT_FOUND"
