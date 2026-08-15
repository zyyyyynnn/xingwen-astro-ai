from __future__ import annotations

from io import BytesIO
import os
from urllib.parse import parse_qs
from uuid import uuid4

from astropy.io import fits
from astropy.io.votable import from_table, writeto
from astropy.table import Table
import httpx
import numpy as np
import pytest

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.core import ScientificSkillId, ScientificTaskInput
from app.schemas.enums import UpstreamFailureClass
from app.workflow.scientific_provenance import _produced_sources
from services.data_pipeline.sources.base import SourceFailure
from services.scientific_skills.astro_acquisition import (
    GAIA_TAP_ENDPOINT,
    GaiaTapAdapter,
    MastLightCurveAdapter,
    SdssSpectrumAdapter,
    acquire_and_analyze_mast_light_curve,
    acquire_and_analyze_sdss_spectrum,
    query_gaia_dr3,
)
from services.scientific_skills.astro_series import (
    analyze_light_curve,
    analyze_spectrum,
)
from services.scientific_skills.types import (
    ScientificSkillBudget,
    ScientificSkillRequest,
    ScientificSkillResult,
)


LIVE_ENABLED = os.getenv("XINGWEN_RUN_LIVE_ASTRO_ACQUISITION_TESTS") == "1"
TESS_LIVE_PRODUCT = "tess2020186164531-s0027-0000000261136679-0189-s_lc.fits"


def _request(
    skill_id: ScientificSkillId,
    parameters: dict[str, object],
    *,
    max_input_rows: int = 10_000,
    max_output_rows: int = 2_000,
) -> ScientificSkillRequest:
    return ScientificSkillRequest(
        request_id=str(uuid4()),
        project_id=str(uuid4()),
        run_id=str(uuid4()),
        skill_id=skill_id,
        parameters=parameters,
        source_references=(),
        budget=ScientificSkillBudget(
            timeout_seconds=60,
            max_input_rows=max_input_rows,
            max_output_rows=max_output_rows,
            max_input_bytes=32 * 1024 * 1024,
            max_output_bytes=8 * 1024 * 1024,
        ),
    )


def _sdss_fits() -> bytes:
    size = 64
    columns = [
        fits.Column(name="flux", format="E", array=np.linspace(8.0, 12.0, size)),
        fits.Column(
            name="loglam",
            format="E",
            array=np.log10(np.linspace(4_000.0, 5_000.0, size)),
        ),
        fits.Column(name="ivar", format="E", array=np.full(size, 25.0)),
        fits.Column(name="and_mask", format="J", array=np.zeros(size, dtype=int)),
    ]
    buffer = BytesIO()
    fits.HDUList([fits.PrimaryHDU(), fits.BinTableHDU.from_columns(columns)]).writeto(
        buffer
    )
    return buffer.getvalue()


def _tess_fits() -> bytes:
    size = 512
    times = np.linspace(1_000.0, 1_025.0, size)
    fluxes = 10_000.0 + 150.0 * np.sin(2.0 * np.pi * times / 2.5)
    columns = [
        fits.Column(name="TIME", format="D", array=times),
        fits.Column(name="PDCSAP_FLUX", format="E", array=fluxes),
        fits.Column(name="PDCSAP_FLUX_ERR", format="E", array=np.full(size, 5.0)),
        fits.Column(name="SAP_FLUX", format="E", array=fluxes + 20.0),
        fits.Column(name="SAP_FLUX_ERR", format="E", array=np.full(size, 6.0)),
        fits.Column(name="QUALITY", format="J", array=np.zeros(size, dtype=int)),
    ]
    buffer = BytesIO()
    fits.HDUList([fits.PrimaryHDU(), fits.BinTableHDU.from_columns(columns)]).writeto(
        buffer
    )
    return buffer.getvalue()


def test_gaia_recorded_csv_uses_only_generated_cone_adql() -> None:
    seen_query: dict[str, list[str]] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://gea.esac.esa.int/tap-server/tap/sync"
        assert request.method == "POST"
        seen_query.update(parse_qs(request.content.decode("ascii")))
        return httpx.Response(
            200,
            headers={"content-type": "text/csv", "etag": '"gaia-recorded"'},
            content=(
                b"source_id,ra,dec,phot_g_mean_mag\n"
                b"65214061869072512,56.7529935,24.1081972,18.889612\n"
            ),
            request=request,
        )

    result = GaiaTapAdapter(
        transport=httpx.MockTransport(handler), mode="recorded"
    ).acquire(
        _request(
            ScientificSkillId.gaia_cone_search,
            {
                "ra_degrees": 56.75,
                "dec_degrees": 24.1167,
                "radius_degrees": 0.01,
                "fields": ["source_id", "ra", "dec", "phot_g_mean_mag"],
                "max_results": 2,
            },
        )
    )

    query = seen_query["QUERY"][0]
    assert query.startswith(
        "SELECT TOP 2 source_id,ra,dec,phot_g_mean_mag FROM gaiadr3.gaia_source"
    )
    assert "CIRCLE('ICRS',56.75,24.1167,0.01)" in query
    assert result["rows"] == [
        {
            "source_id": "65214061869072512",
            "ra": 56.7529935,
            "dec": 24.1081972,
            "phot_g_mean_mag": 18.889612,
        }
    ]
    assert result["acquisition"]["source_mode"] == "recorded"
    assert result["acquisition"]["response_content_hash"].startswith("sha256:")
    assert result["acquisition"]["response_uri"] == GAIA_TAP_ENDPOINT


def test_gaia_recorded_votable_is_schema_and_row_bounded() -> None:
    table = Table(
        {
            "source_id": ["123456789012345678"],
            "ra": [12.5],
            "dec": [-20.25],
        }
    )
    buffer = BytesIO()
    writeto(from_table(table), buffer)

    adapter = GaiaTapAdapter(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, content=buffer.getvalue(), request=request
            )
        ),
        mode="recorded",
    )
    result = adapter.acquire(
        _request(
            ScientificSkillId.gaia_cone_search,
            {
                "ra_degrees": 12.5,
                "dec_degrees": -20.25,
                "fields": ["source_id", "ra", "dec"],
                "response_format": "votable",
                "max_results": 1,
            },
        )
    )

    assert result["response_format"] == "votable"
    assert result["rows"][0]["source_id"] == "123456789012345678"


def test_gaia_rejects_arbitrary_fields_redirects_and_oversized_responses() -> None:
    called = False

    def unexpected(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, content=b"", request=request)

    request = _request(
        ScientificSkillId.gaia_cone_search,
        {"ra_degrees": 1.0, "dec_degrees": 2.0, "fields": ["source_id;drop"]},
    )
    with pytest.raises(ValueError, match="unsupported Gaia fields"):
        GaiaTapAdapter(transport=httpx.MockTransport(unexpected)).acquire(request)
    assert called is False

    redirect = httpx.MockTransport(
        lambda request: httpx.Response(
            302,
            headers={"location": "https://evil.example/tap"},
            request=request,
        )
    )
    with pytest.raises(SourceFailure) as redirected:
        GaiaTapAdapter(transport=redirect).acquire(
            _request(
                ScientificSkillId.gaia_cone_search,
                {"ra_degrees": 1.0, "dec_degrees": 2.0},
            )
        )
    assert redirected.value.classification is UpstreamFailureClass.policy_violation

    oversized = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            headers={"content-length": str(9 * 1024 * 1024)},
            content=b"small body",
            request=request,
        )
    )
    with pytest.raises(SourceFailure) as too_large:
        GaiaTapAdapter(transport=oversized).acquire(
            _request(
                ScientificSkillId.gaia_cone_search,
                {"ra_degrees": 1.0, "dec_degrees": 2.0},
            )
        )
    assert too_large.value.code == "ASTRO_HTTP_RESPONSE_TOO_LARGE"


def test_sdss_recorded_fits_returns_existing_spectrum_skill_input() -> None:
    content = _sdss_fits()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == (
            "https://data.sdss.org/sas/dr17/eboss/spectro/redux/v5_13_2/spectra/full/3586/spec-3586-55181-0016.fits"
        )
        return httpx.Response(200, content=content, request=request)

    request = _request(
        ScientificSkillId.spectrum_acquisition,
        {"plate": 3586, "mjd": 55181, "fiber": 16},
    )
    typed = SdssSpectrumAdapter(
        transport=httpx.MockTransport(handler), mode="recorded"
    ).acquire(request)
    acquisition = typed.pop("acquisition")
    analyzed = analyze_spectrum(request.model_copy(update={"parameters": typed}))

    assert len(typed["rows"]) == 64
    assert typed["wavelength_unit"] == "angstrom"
    assert analyzed["sample_count"] == 64
    assert acquisition["source_mode"] == "recorded"
    assert acquisition["response_uri"].endswith("/3586/spec-3586-55181-0016.fits")


def test_mast_recorded_fits_follows_only_the_official_storage_redirect() -> None:
    content = _tess_fits()
    seen_hosts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_hosts.append(request.url.host)
        if request.url.host == "mast.stsci.edu":
            assert request.url.params["uri"] == f"mast:TESS/product/{TESS_LIVE_PRODUCT}"
            return httpx.Response(
                302,
                headers={
                    "location": (
                        "https://stpubdata.s3.us-east-1.amazonaws.com/"
                        f"tess/public/{TESS_LIVE_PRODUCT}"
                    )
                },
                request=request,
            )
        assert request.url.host == "stpubdata.s3.us-east-1.amazonaws.com"
        return httpx.Response(200, content=content, request=request)

    request = _request(
        ScientificSkillId.light_curve_acquisition,
        {"tic_id": 261136679, "sector": 27, "product_filename": TESS_LIVE_PRODUCT},
    )
    typed = MastLightCurveAdapter(
        transport=httpx.MockTransport(handler), mode="recorded"
    ).acquire(request)
    acquisition = typed.pop("acquisition")
    analyzed = analyze_light_curve(request.model_copy(update={"parameters": typed}))

    assert seen_hosts == [
        "mast.stsci.edu",
        "stpubdata.s3.us-east-1.amazonaws.com",
    ]
    assert analyzed["sample_count"] == 512
    assert analyzed["best_period"] == pytest.approx(2.5, rel=0.03)
    assert acquisition["source_mode"] == "recorded"
    assert acquisition["response_uri"].startswith(
        "https://stpubdata.s3.us-east-1.amazonaws.com/tess/public/"
    )


def test_mast_rejects_unlisted_redirect_and_mismatched_product_identity() -> None:
    request = _request(
        ScientificSkillId.light_curve_acquisition,
        {"tic_id": 261136679, "sector": 28, "product_filename": TESS_LIVE_PRODUCT},
    )
    with pytest.raises(ValueError, match="does not match"):
        MastLightCurveAdapter().acquire(request)

    redirect = httpx.MockTransport(
        lambda incoming: httpx.Response(
            302,
            headers={"location": "https://example.org/lightcurve.fits"},
            request=incoming,
        )
    )
    with pytest.raises(SourceFailure) as failure:
        MastLightCurveAdapter(transport=redirect).acquire(
            request.model_copy(
                update={"parameters": request.parameters | {"sector": 27}}
            )
        )
    assert failure.value.classification is UpstreamFailureClass.policy_violation


def test_http_failure_classification_is_retryable_only_when_safe() -> None:
    request = _request(
        ScientificSkillId.spectrum_acquisition,
        {"plate": 3586, "mjd": 55181, "fiber": 16},
    )
    for status, classification, retryable in (
        (429, UpstreamFailureClass.rate_limited, True),
        (503, UpstreamFailureClass.upstream_server, True),
        (404, UpstreamFailureClass.upstream_client, False),
    ):
        adapter = SdssSpectrumAdapter(
            transport=httpx.MockTransport(
                lambda incoming, status=status: httpx.Response(status, request=incoming)
            )
        )
        with pytest.raises(SourceFailure) as failure:
            adapter.acquire(request)
        assert failure.value.classification is classification
        assert failure.value.retryable is retryable

    timeout_adapter = SdssSpectrumAdapter(
        transport=httpx.MockTransport(
            lambda incoming: (_ for _ in ()).throw(
                httpx.ReadTimeout("recorded timeout", request=incoming)
            )
        )
    )
    with pytest.raises(SourceFailure) as timeout:
        timeout_adapter.acquire(request)
    assert timeout.value.classification is UpstreamFailureClass.timeout
    assert timeout.value.retryable is True


def test_registered_acquisition_handlers_reuse_the_existing_analyzers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gaia_request = _request(
        ScientificSkillId.gaia_cone_search,
        {"ra_degrees": 1.0, "dec_degrees": 2.0},
    )
    monkeypatch.setattr(
        GaiaTapAdapter,
        "acquire",
        lambda _self, _request: {"service": "gaia_archive", "rows": []},
    )
    assert query_gaia_dr3(gaia_request)["service"] == "gaia_archive"

    spectrum_request = _request(
        ScientificSkillId.spectrum_acquisition,
        {"plate": 3586, "mjd": 55181, "fiber": 16},
    )
    monkeypatch.setattr(
        SdssSpectrumAdapter,
        "acquire",
        lambda _self, _request: {
            "rows": [
                {"wavelength": 4_000.0 + index, "flux": 10.0 + index / 100}
                for index in range(32)
            ],
            "wavelength_field": "wavelength",
            "flux_field": "flux",
            "object_name": "recorded target",
            "wavelength_unit": "angstrom",
            "flux_unit": "relative_flux",
            "acquisition": {"source_mode": "recorded"},
        },
    )
    assert acquire_and_analyze_sdss_spectrum(spectrum_request)["sample_count"] == 32

    light_curve_request = _request(
        ScientificSkillId.light_curve_acquisition,
        {"tic_id": 261136679, "sector": 27, "product_filename": TESS_LIVE_PRODUCT},
    )
    monkeypatch.setattr(
        MastLightCurveAdapter,
        "acquire",
        lambda _self, _request: {
            "rows": [
                {
                    "time": index / 10,
                    "value": 1.0 + 0.1 * np.sin(2 * np.pi * index / 25),
                }
                for index in range(100)
            ],
            "time_field": "time",
            "value_field": "value",
            "object_name": "recorded target",
            "time_scale": "tdb",
            "time_unit": "day",
            "value_unit": "relative_flux",
            "value_kind": "relative_flux",
            "acquisition": {"source_mode": "recorded"},
        },
    )
    assert (
        acquire_and_analyze_mast_light_curve(light_curve_request)["sample_count"] == 100
    )


@pytest.mark.parametrize(
    ("skill_id", "source_id", "response_uri"),
    [
        (
            ScientificSkillId.gaia_cone_search,
            "esa_gaia_dr3",
            "https://gea.esac.esa.int/tap-server/tap/sync",
        ),
        (
            ScientificSkillId.spectrum_acquisition,
            "sdss_dr17",
            "https://data.sdss.org/sas/dr17/example.fits",
        ),
        (
            ScientificSkillId.light_curve_acquisition,
            "mast_tess",
            "https://stpubdata.s3.us-east-1.amazonaws.com/tess/public/example.fits",
        ),
    ],
)
def test_external_source_snapshot_uses_provider_raw_response_identity(
    skill_id: ScientificSkillId,
    source_id: str,
    response_uri: str,
) -> None:
    response_hash = "sha256:" + "c" * 64
    request = _request(skill_id, {"controlled_parameter": "value"})
    output = {
        "rows": [],
        "acquisition": {
            "source_mode": "live",
            "adapter": "recorded-adapter",
            "adapter_version": "1.0.0",
            "endpoint": response_uri,
            "response_uri": response_uri,
            "status_code": 200,
            "content_length": 128,
            "response_content_hash": response_hash,
            "source_version_or_etag": '"upstream-revision"',
        },
    }
    result = ScientificSkillResult(
        request_id=request.request_id,
        skill_id=skill_id,
        skill_revision="1.0.0",
        status="completed",
        output=output,
        source_snapshot_ids=(),
        input_hash=request.input_hash,
        output_hash=compute_canonical_payload_hash(output),
    )
    sources = _produced_sources(
        task=ScientificTaskInput(
            task_id="task.acquisition",
            skill_id=skill_id,
            parameters=request.parameters,
        ),
        request=request,
        result=result,
    )

    assert len(sources) == 1
    assert sources[0].source_id == source_id
    assert sources[0].content_hash == response_hash
    assert sources[0].source_version_or_etag == '"upstream-revision"'
    assert sources[0].request_metadata["response_uri"] == response_uri
    assert sources[0].request_metadata["adapter_version"] == "1.0.0"


@pytest.mark.live
@pytest.mark.skipif(not LIVE_ENABLED, reason="opt-in live Gaia smoke is disabled")
def test_live_gaia_cone_search() -> None:
    result = query_gaia_dr3(
        _request(
            ScientificSkillId.gaia_cone_search,
            {
                "ra_degrees": 56.75,
                "dec_degrees": 24.1167,
                "radius_degrees": 0.01,
                "fields": ["source_id", "ra", "dec", "phot_g_mean_mag"],
                "max_results": 2,
            },
            max_output_rows=10,
        )
    )
    assert 1 <= result["row_count"] <= 2
    assert result["acquisition"]["source_mode"] == "live"


@pytest.mark.live
@pytest.mark.skipif(not LIVE_ENABLED, reason="opt-in live SDSS smoke is disabled")
def test_live_sdss_spectrum_acquisition() -> None:
    result = acquire_and_analyze_sdss_spectrum(
        _request(
            ScientificSkillId.spectrum_acquisition,
            {"plate": 3586, "mjd": 55181, "fiber": 16},
        )
    )
    assert result["sample_count"] >= 1_000
    assert result["acquisition"]["source_mode"] == "live"


@pytest.mark.live
@pytest.mark.skipif(not LIVE_ENABLED, reason="opt-in live MAST smoke is disabled")
def test_live_mast_tess_light_curve_acquisition() -> None:
    result = acquire_and_analyze_mast_light_curve(
        _request(
            ScientificSkillId.light_curve_acquisition,
            {
                "tic_id": 261136679,
                "sector": 27,
                "product_filename": TESS_LIVE_PRODUCT,
            },
        )
    )
    assert result["sample_count"] >= 1_000
    assert result["acquisition"]["source_mode"] == "live"
