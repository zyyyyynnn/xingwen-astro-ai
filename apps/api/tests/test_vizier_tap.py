from __future__ import annotations

from collections.abc import Sequence
from io import BytesIO
from urllib.parse import parse_qs
from uuid import uuid4

from astropy.io.votable import from_table, writeto
from astropy.table import Table
import httpx
import pytest

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.core import ResearchContractInput, ScientificSkillId, ScientificTaskInput
from app.schemas.enums import UpstreamFailureClass
from app.schemas.scientific_skills import AnalysisReportArtifactContent
from app.workflow.scientific_provenance import _produced_sources
from services.data_pipeline.sources.base import SourceFailure
from services.scientific_skills import (
    ScientificInputBinding,
    ScientificSkillDefinition,
    ScientificSkillRegistry,
    ScientificSourceReference,
    ScientificStepAdapter,
)
from services.scientific_skills.astro_acquisition import (
    VIZIER_TAP_ENDPOINT,
    VizierTapAdapter,
    query_vizier_tap,
)
from services.scientific_skills.registry import build_scientific_skill_registry
from services.scientific_skills.types import (
    ScientificSkillBudget,
    ScientificSkillRequest,
    ScientificSkillResult,
)


class _MemoryStorage:
    async def store(self, content: bytes, content_hash: str) -> str:
        raise AssertionError(f"VizieR should not produce binary content: {content_hash}")

    async def retrieve(self, content_hash: str) -> bytes | None:
        return None

    def exists(self, content_hash: str) -> bool:
        return False


class _SourceRecorder:
    async def record(self, **_: object) -> tuple[ScientificSourceReference, ...]:
        return (
            ScientificSourceReference(
                source_snapshot_id="snapshot.vizier",
                content_hash="sha256:" + "a" * 64,
            ),
        )


def _request(
    parameters: dict[str, object],
    *,
    max_output_rows: int = 2_000,
    max_output_bytes: int = 8 * 1024 * 1024,
) -> ScientificSkillRequest:
    return ScientificSkillRequest(
        request_id=str(uuid4()),
        project_id=str(uuid4()),
        run_id=str(uuid4()),
        skill_id=ScientificSkillId.vizier_tap,
        parameters=parameters,
        source_references=(),
        budget=ScientificSkillBudget(
            timeout_seconds=30,
            max_output_rows=max_output_rows,
            max_output_bytes=max_output_bytes,
        ),
    )


def test_recorded_csv_uses_only_allowlisted_manifest_and_records_provider_identity() -> None:
    seen: dict[str, list[str]] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == httpx.URL(VIZIER_TAP_ENDPOINT)
        assert request.method == "POST"
        seen.update(parse_qs(request.content.decode("ascii")))
        return httpx.Response(
            200,
            headers={"etag": '"vizier-recorded"'},
            content=(
                b"Source,RA_ICRS,DE_ICRS,Plx\n"
                b"2546034966433885568,0.00943691398,-8.9684879E-4,1.8188\n"
            ),
            request=request,
        )

    result = VizierTapAdapter(
        transport=httpx.MockTransport(handler), mode="recorded"
    ).acquire(
        _request(
            {
                "catalog_id": "gaia_dr3",
                "table_id": "gaiadr3",
                "ra_degrees": 0,
                "dec_degrees": 0,
                "radius_degrees": 0.01,
                "fields": [
                    "source_id",
                    "ra_degrees",
                    "dec_degrees",
                    "parallax_mas",
                ],
                "max_results": 2,
            }
        )
    )

    query = seen["QUERY"][0]
    assert query.startswith(
        'SELECT TOP 2 "Source","RA_ICRS","DE_ICRS","Plx" '
        'FROM "I/355/gaiadr3"'
    )
    assert "CIRCLE('ICRS',0,0,0.01)" in query
    assert "JOIN" not in query.upper()
    assert "https://" not in query
    assert result["rows"] == [
        {
            "source_id": "2546034966433885568",
            "ra_degrees": 0.00943691398,
            "dec_degrees": -8.9684879e-4,
            "parallax_mas": 1.8188,
        }
    ]
    acquisition = result["acquisition"]
    assert acquisition["source_mode"] == "recorded"
    assert acquisition["provider_uri"] == VIZIER_TAP_ENDPOINT
    assert acquisition["provider_revision"] == "1.0.0"
    assert acquisition["etag"] == '"vizier-recorded"'
    assert acquisition["raw_content_hash"].startswith("sha256:")
    assert result["provider_uri"] == VIZIER_TAP_ENDPOINT


def test_recorded_votable_is_typed_and_deterministic() -> None:
    table = Table(
        {
            "Source": ["123456789012345678"],
            "RA_ICRS": [12.5],
            "DE_ICRS": [-20.25],
        }
    )
    buffer = BytesIO()
    writeto(from_table(table), buffer)
    content = buffer.getvalue()

    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, content=content, request=request)
    )
    parameters = {
        "ra_degrees": 12.5,
        "dec_degrees": -20.25,
        "radius_degrees": 0.1,
        "fields": ["source_id", "ra_degrees", "dec_degrees"],
        "response_format": "votable",
    }
    first = VizierTapAdapter(transport=transport, mode="recorded").acquire(
        _request(parameters)
    )
    second = VizierTapAdapter(transport=transport, mode="recorded").acquire(
        _request(parameters)
    )

    assert first == second
    assert first["rows"] == [
        {"source_id": "123456789012345678", "ra_degrees": 12.5, "dec_degrees": -20.25}
    ]


def test_recorded_2mass_manifest_uses_its_own_axes_order_and_units() -> None:
    seen: dict[str, list[str]] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(parse_qs(request.content.decode("ascii")))
        return httpx.Response(
            200,
            content=(
                b"2MASS,RAJ2000,DEJ2000,Jmag,Hmag,Kmag\n"
                b"\"00000229-0000029 \",0.009564,-8.27E-4,16.422,16.112,15.21\n"
            ),
            request=request,
        )

    result = VizierTapAdapter(
        transport=httpx.MockTransport(handler), mode="recorded"
    ).acquire(
        _request(
            {
                "catalog_id": "twomass_psc",
                "ra_degrees": 0,
                "dec_degrees": 0,
                "radius_degrees": 0.01,
            }
        )
    )

    query = seen["QUERY"][0]
    assert 'FROM "II/246/out"' in query
    assert 'POINT(\'ICRS\',"RAJ2000","DEJ2000")' in query
    assert 'ORDER BY "2MASS"' in query
    assert result["rows"] == [
        {
            "source_id": "00000229-0000029",
            "ra_degrees": 0.009564,
            "dec_degrees": -8.27e-4,
            "j_mag": 16.422,
            "h_mag": 16.112,
            "k_mag": 15.21,
        }
    ]


def test_provenance_recorder_projection_uses_raw_hash_etag_and_provider_metadata() -> None:
    output = {
        "service": "vizier_tap",
        "rows": [{"source_id": "123", "ra_degrees": 1.0}],
        "acquisition": {
            "provider_uri": VIZIER_TAP_ENDPOINT,
            "provider_revision": "1.0.0",
            "etag": '"etag-1"',
            "raw_content_hash": "sha256:" + "a" * 64,
            "response_content_hash": "sha256:" + "a" * 64,
            "source_version_or_etag": '"etag-1"',
        },
    }
    result = ScientificSkillResult(
        request_id="request.vizier",
        skill_id=ScientificSkillId.vizier_tap,
        skill_revision="1.0.0",
        status="completed",
        output=output,
        source_snapshot_ids=(),
        input_hash="sha256:" + "b" * 64,
        output_hash=compute_canonical_payload_hash(output),
    )
    task = ScientificTaskInput(
        task_id="task.vizier",
        skill_id=ScientificSkillId.vizier_tap,
        parameters={"catalog_id": "gaia_dr3"},
    )

    sources = _produced_sources(task=task, request=_request(task.parameters), result=result)

    assert len(sources) == 1
    assert sources[0].source_id == "vizier_tap"
    assert sources[0].source_type == "remote_catalog_service"
    assert sources[0].content_hash == "sha256:" + "a" * 64
    assert sources[0].source_version_or_etag == '"etag-1"'
    assert sources[0].request_metadata == {
        "provider_uri": VIZIER_TAP_ENDPOINT,
        "provider_revision": "1.0.0",
        "etag": '"etag-1"',
        "raw_content_hash": "sha256:" + "a" * 64,
    }


def test_registry_contains_vizier_skill_and_handler_is_not_dynamic() -> None:
    registry = build_scientific_skill_registry()

    assert ScientificSkillId.vizier_tap in registry.skill_ids
    assert registry.revision_for(ScientificSkillId.vizier_tap) == "1.0.0"
    assert query_vizier_tap.__module__ == "services.scientific_skills.astro_acquisition"


@pytest.mark.anyio
async def test_step_adapter_publishes_vizier_as_catalog_analysis_with_source_snapshot() -> None:
    def fake_vizier(_: ScientificSkillRequest) -> dict[str, object]:
        return {
            "service": "vizier_tap",
            "catalog_id": "twomass_psc",
            "qualified_table": "II/246/out",
            "rows": [{"source_id": "00000229-0000029", "j_mag": 16.422}],
            "acquisition": {
                "provider_uri": VIZIER_TAP_ENDPOINT,
                "provider_revision": "1.0.0",
                "raw_content_hash": "sha256:" + "b" * 64,
            },
        }

    registry = ScientificSkillRegistry(
        [
            ScientificSkillDefinition(
                skill_id=ScientificSkillId.vizier_tap,
                revision="1.0.0",
                handler=fake_vizier,
            )
        ]
    )
    adapter = ScientificStepAdapter(
        registry,
        content_storage=_MemoryStorage(),
        source_recorder=_SourceRecorder(),
    )
    contract = ResearchContractInput.model_validate({
        "research_goal": "Execute one catalog observation",
        "target_objects": ["host_star"],
        "data_requirements": {},
        "requested_fields": ["star.mass"],
        "source_scope": {"allowed_sources": ["nasa_exoplanet_archive"]},
        "paper_search_scope": {},
        "scientific_tasks": [
            {
                "task_id": "task.vizier",
                "skill_id": "vizier_tap",
                "parameters": {"catalog_id": "twomass_psc"},
                "input_refs": [],
            }
        ],
        "output_requirements": ["analysis_report"],
        "evidence_requirements": {},
        "quality_constraints": {},
    })

    async def resolve(_: ScientificTaskInput) -> Sequence[ScientificInputBinding]:
        return ()

    output = await adapter.execute(
        task_id="task.vizier",
        project_id=str(uuid4()),
        run_id=str(uuid4()),
        contract=contract,
        resolve_inputs=resolve,
    )

    candidate = output.artifact_candidates[0]
    assert isinstance(candidate, AnalysisReportArtifactContent)
    assert candidate.source_snapshot_ids == ("snapshot.vizier",)
    assert candidate.result_blocks[0].representation == "catalog"
    assert candidate.result_blocks[0].payload["catalog_id"] == "twomass_psc"


@pytest.mark.parametrize(
    "parameters",
    [
        {"catalog_id": "not-allowlisted", "ra_degrees": 0, "dec_degrees": 0},
        {"table_id": "arbitrary", "ra_degrees": 0, "dec_degrees": 0},
        {"ra_degrees": 360, "dec_degrees": 0},
        {"ra_degrees": 0, "dec_degrees": 91},
        {"ra_degrees": 0, "dec_degrees": 0, "radius_degrees": 5.1},
        {"ra_degrees": 0, "dec_degrees": 0, "response_format": "json"},
        {"ra_degrees": 0, "dec_degrees": 0, "fields": ["RA_ICRS"]},
    ],
)
def test_vizier_rejects_unbounded_or_non_allowlisted_input(
    parameters: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        VizierTapAdapter(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(500, request=request)
            )
        ).acquire(_request(parameters))


def test_vizier_rejects_schema_drift_and_response_budget_overflow() -> None:
    bad_schema = httpx.MockTransport(
        lambda request: httpx.Response(
            200, content=b"Source,Wrong\n123,1\n", request=request
        )
    )
    with pytest.raises(SourceFailure) as schema_error:
        VizierTapAdapter(transport=bad_schema).acquire(
            _request({"ra_degrees": 0, "dec_degrees": 0, "fields": ["source_id", "ra_degrees"]})
        )
    assert schema_error.value.classification is UpstreamFailureClass.invalid_response
    assert schema_error.value.code == "VIZIER_TAP_SCHEMA_DRIFT"

    oversized = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            headers={"content-length": "64"},
            content=b"Source\n" + b"1" * 64,
            request=request,
        )
    )
    with pytest.raises(SourceFailure) as size_error:
        VizierTapAdapter(transport=oversized).acquire(
            _request(
                {"ra_degrees": 0, "dec_degrees": 0, "fields": ["source_id"]},
                max_output_bytes=32,
            )
        )
    assert size_error.value.code == "ASTRO_HTTP_RESPONSE_TOO_LARGE"


def test_vizier_rejects_cross_origin_redirect_and_timeout() -> None:
    redirect = httpx.MockTransport(
        lambda request: httpx.Response(
            302,
            headers={"location": "https://example.invalid/tap/sync"},
            request=request,
        )
    )
    with pytest.raises(SourceFailure) as redirect_error:
        VizierTapAdapter(transport=redirect).acquire(
            _request({"ra_degrees": 0, "dec_degrees": 0})
        )
    assert redirect_error.value.classification is UpstreamFailureClass.policy_violation
    assert redirect_error.value.code == "ASTRO_HTTP_ORIGIN_POLICY_VIOLATION"

    timeout = httpx.MockTransport(
        lambda request: (_ for _ in ()).throw(
            httpx.ReadTimeout("recorded timeout", request=request)
        )
    )
    with pytest.raises(SourceFailure) as timeout_error:
        VizierTapAdapter(transport=timeout).acquire(
            _request({"ra_degrees": 0, "dec_degrees": 0})
        )
    assert timeout_error.value.classification is UpstreamFailureClass.timeout
    assert timeout_error.value.code == "ASTRO_HTTP_TIMEOUT"
