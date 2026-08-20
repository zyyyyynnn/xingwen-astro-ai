from __future__ import annotations

from datetime import UTC, datetime, timedelta
import os
from urllib.parse import parse_qs
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import Engine

from app.db.session import create_engine_from_url, session_factory
from app.schemas.core import ScientificSkillId
from app.schemas.enums import UpstreamFailureClass
from app.workflow.scientific_provenance import DatabaseGaiaTapResponseCache
from authoring_test_support import build_research_project
from db_bootstrap import reset_current_schema
from services.data_pipeline.sources.base import SourceFailure
from services.scientific_skills.astro_acquisition import (
    GAIA_CACHE_VERSION,
    GaiaTapAdapter,
)
from services.scientific_skills.types import (
    ScientificSkillBudget,
    ScientificSkillRequest,
)


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


class MemoryGaiaCache:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], dict[str, object]] = {}

    def get(self, *, project_id: str, query_hash: str) -> dict[str, object] | None:
        return self.values.get((project_id, query_hash))

    def put(
        self,
        *,
        project_id: str,
        query_hash: str,
        payload: dict[str, object],
        retrieved_at: datetime,
    ) -> None:
        assert retrieved_at.tzinfo is not None
        self.values[(project_id, query_hash)] = payload


def _request(*, project_id: str | None = None) -> ScientificSkillRequest:
    return ScientificSkillRequest(
        request_id=str(uuid4()),
        project_id=project_id or str(uuid4()),
        run_id=str(uuid4()),
        skill_id=ScientificSkillId.gaia_cone_search,
        parameters={
            "ra_degrees": 56.75,
            "dec_degrees": 24.1167,
            "radius_degrees": 0.01,
            "fields": ["source_id", "ra", "dec"],
            "max_results": 2,
        },
        source_references=(),
        budget=ScientificSkillBudget(timeout_seconds=30),
    )


def _schema_csv(*, include_ra: bool = True) -> bytes:
    rows = ["column_name,datatype,unit", "dec,double,deg"]
    if include_ra:
        rows.append("ra,double,deg")
    rows.append("source_id,long,")
    return ("\n".join(rows) + "\n").encode()


def test_gaia_preflights_schema_and_reuses_project_scoped_response() -> None:
    queries: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        query = parse_qs(request.content.decode("ascii"))["QUERY"][0]
        queries.append(query)
        if "TAP_SCHEMA.columns" in query:
            return httpx.Response(200, content=_schema_csv(), request=request)
        return httpx.Response(
            200,
            headers={"etag": '"gaia-recorded"'},
            content=(b"source_id,ra,dec\n65214061869072512,56.7529935,24.1081972\n"),
            request=request,
        )

    cache = MemoryGaiaCache()
    request = _request()
    live = GaiaTapAdapter(transport=httpx.MockTransport(handler), cache=cache).acquire(
        request
    )

    assert len(queries) == 2
    assert queries[1].startswith(
        "SELECT TOP 3 source_id,ra,dec FROM gaiadr3.gaia_source"
    )
    assert live["rows"] == [
        {
            "source_id": "65214061869072512",
            "ra": 56.7529935,
            "dec": 24.1081972,
        }
    ]
    assert live["acquisition"]["cache_version"] == GAIA_CACHE_VERSION
    assert live["result_status"] == "complete"
    assert live["truncated"] is False

    def unexpected(_: httpx.Request) -> httpx.Response:
        raise AssertionError("a valid Gaia cache hit must not contact TAP")

    cached = GaiaTapAdapter(
        transport=httpx.MockTransport(unexpected), cache=cache
    ).acquire(_request(project_id=request.project_id))

    assert cached["rows"] == live["rows"]
    assert cached["acquisition"]["source_mode"] == "cached"
    assert cached["acquisition"]["retrieved_at"] == live["acquisition"]["retrieved_at"]


def test_gaia_fetches_one_extra_row_to_report_truncation() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        query = parse_qs(request.content.decode("ascii"))["QUERY"][0]
        if "TAP_SCHEMA.columns" in query:
            return httpx.Response(200, content=_schema_csv(), request=request)
        assert query.startswith(
            "SELECT TOP 3 source_id,ra,dec FROM gaiadr3.gaia_source"
        )
        return httpx.Response(
            200,
            content=(
                b"source_id,ra,dec\n"
                b"1,56.7,24.1\n"
                b"2,56.8,24.2\n"
                b"3,56.9,24.3\n"
            ),
            request=request,
        )

    result = GaiaTapAdapter(transport=httpx.MockTransport(handler)).acquire(_request())

    assert result["row_count"] == 2
    assert [row["source_id"] for row in result["rows"]] == ["1", "2"]
    assert result["truncated"] is True
    assert result["result_status"] == "truncated"

def test_gaia_schema_drift_fails_before_the_data_query() -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(
            200, content=_schema_csv(include_ra=False), request=request
        )

    with pytest.raises(SourceFailure) as failed:
        GaiaTapAdapter(transport=httpx.MockTransport(handler)).acquire(_request())

    assert call_count == 1
    assert failed.value.classification is UpstreamFailureClass.invalid_response
    assert failed.value.code == "GAIA_TAP_SCHEMA_DRIFT"


def test_gaia_accepts_the_official_tap_unit_encoding() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        query = parse_qs(request.content.decode("ascii"))["QUERY"][0]
        if "TAP_SCHEMA.columns" in query:
            return httpx.Response(
                200,
                content=(
                    b"column_name,datatype,unit\n"
                    b"pmra,double,mas.yr**-1\n"
                    b"radial_velocity,float,km.s**-1\n"
                    b"source_id,long,\n"
                ),
                request=request,
            )
        return httpx.Response(
            200,
            content=(b"source_id,pmra,radial_velocity\n65214061869072512,3.25,-18.5\n"),
            request=request,
        )

    request = _request().model_copy(
        update={
            "parameters": {
                "ra_degrees": 56.75,
                "dec_degrees": 24.1167,
                "fields": ["source_id", "pmra", "radial_velocity"],
                "max_results": 1,
            }
        }
    )
    result = GaiaTapAdapter(transport=httpx.MockTransport(handler)).acquire(request)

    assert result["rows"] == [
        {
            "source_id": "65214061869072512",
            "pmra": 3.25,
            "radial_velocity": -18.5,
        }
    ]


def test_gaia_rate_limit_has_a_stable_retryable_failure() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(429, request=request)
    )

    with pytest.raises(SourceFailure) as failed:
        GaiaTapAdapter(transport=transport).acquire(_request())

    assert failed.value.classification is UpstreamFailureClass.rate_limited
    assert failed.value.code == "ASTRO_HTTP_RATE_LIMITED"
    assert failed.value.retryable is True


@pytest.mark.skipif(
    not TEST_DATABASE_URL, reason="TEST_DATABASE_URL is not configured"
)
def test_gaia_cache_is_project_scoped_persistent_and_expires() -> None:
    assert TEST_DATABASE_URL is not None
    assert "test" in TEST_DATABASE_URL.rsplit("/", 1)[-1].lower()
    reset_current_schema(TEST_DATABASE_URL)
    engine: Engine = create_engine_from_url(TEST_DATABASE_URL)
    factory = session_factory(engine)
    project = build_research_project(
        project_id=uuid4(),
        session_id=f"session-{uuid4()}",
        name="Gaia cache test",
        case_key="exoplanet_host_star",
    )
    try:
        with factory() as session, session.begin():
            session.add(project)
        cache = DatabaseGaiaTapResponseCache(factory)
        payload = {"rows": [{"source_id": "1"}]}
        query_hash = "sha256:" + "a" * 64
        cache.put(
            project_id=str(project.id),
            query_hash=query_hash,
            payload=payload,
            retrieved_at=datetime.now(UTC),
        )

        assert cache.get(project_id=str(project.id), query_hash=query_hash) == payload
        assert cache.get(project_id=str(uuid4()), query_hash=query_hash) is None

        expired_hash = "sha256:" + "b" * 64
        cache.put(
            project_id=str(project.id),
            query_hash=expired_hash,
            payload=payload,
            retrieved_at=datetime.now(UTC) - timedelta(hours=1),
        )
        assert cache.get(project_id=str(project.id), query_hash=expired_hash) is None
    finally:
        engine.dispose()
        reset_current_schema(TEST_DATABASE_URL)
