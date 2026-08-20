"""Bounded live astronomy acquisition adapters for registered scientific skills.

The adapters in this module accept only scientific identifiers and numeric query
parameters.  They never accept a URL or free-form ADQL, keep every origin on an
explicit HTTPS allowlist, and return the same typed row inputs consumed by the
existing spectrum and light-curve analysis skills.
"""

from __future__ import annotations

from collections.abc import Mapping
import csv
from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO, StringIO
from hashlib import sha256
from math import isfinite, sqrt
import re
from time import monotonic
from types import MappingProxyType
from typing import Literal, Protocol
from urllib.parse import urljoin, urlsplit

import httpx
import numpy as np

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.enums import UpstreamFailureClass
from services.data_pipeline.source_table import gaia_source_contract
from services.data_pipeline.sources.base import SourceFailure

from .astro_series import analyze_light_curve, analyze_spectrum
from .parameters import (
    optional_integer,
    optional_number,
    optional_string,
    reject_unknown,
    require_number,
    require_string,
    require_string_list,
)
from .types import ScientificSkillRequest


AcquisitionMode = Literal["live", "recorded"]

GAIA_TAP_ENDPOINT = "https://gea.esac.esa.int/tap-server/tap/sync"
VIZIER_TAP_ENDPOINT = "https://tapvizier.cds.unistra.fr/TAPVizieR/tap/sync"
SDSS_DR17_SPECTRA_ROOT = (
    "https://data.sdss.org/sas/dr17/eboss/spectro/redux/v5_13_2/spectra/full/"
)
MAST_DOWNLOAD_ENDPOINT = "https://mast.stsci.edu/api/v0.1/Download/file"
MAST_TESS_STORAGE_ORIGIN = "https://stpubdata.s3.us-east-1.amazonaws.com"

GAIA_ADAPTER_VERSION = "3.0.0"
GAIA_SCHEMA_REVISION = "gaiadr3.gaia_source:2"
GAIA_CACHE_VERSION = f"gaia-tap:{GAIA_ADAPTER_VERSION}:{GAIA_SCHEMA_REVISION}"
VIZIER_TAP_ADAPTER_VERSION = "1.0.0"
SDSS_SPECTRUM_ADAPTER_VERSION = "1.0.0"
MAST_LIGHT_CURVE_ADAPTER_VERSION = "1.0.0"

_GAIA_SOURCE_CONTRACT = MappingProxyType(
    {field.raw_field: field for field in gaia_source_contract()}
)
_GAIA_DEFAULT_FIELDS = tuple(_GAIA_SOURCE_CONTRACT)
_GAIA_SCHEMA_DATATYPES: Mapping[str, frozenset[str]] = MappingProxyType(
    {
        field: contract.schema_datatypes
        for field, contract in _GAIA_SOURCE_CONTRACT.items()
    }
)
_GAIA_SCHEMA_UNITS: Mapping[str, str | None] = MappingProxyType(
    {field: contract.schema_unit for field, contract in _GAIA_SOURCE_CONTRACT.items()}
)


def _column_metadata(
    fields: tuple[str, ...],
    units: Mapping[str, str | None],
) -> list[dict[str, object]]:
    return [
        {
            "field": field,
            "label": field.replace("_", " ").title(),
            "unit": units.get(field),
        }
        for field in fields
    ]


@dataclass(frozen=True, slots=True)
class VizierFieldManifest:
    """One public field alias bound to one immutable VizieR table column."""

    column: str
    value_kind: Literal["identifier", "number", "text"]
    unit: str | None = None


@dataclass(frozen=True, slots=True)
class VizierCatalogManifest:
    """Allowlisted VizieR catalog/table contract, not a free-form ADQL surface."""

    catalog: str
    table: str
    qualified_table: str
    ra_column: str
    dec_column: str
    order_column: str
    fields: Mapping[str, VizierFieldManifest]
    default_fields: tuple[str, ...]


VIZIER_CATALOG_MANIFEST: Mapping[str, VizierCatalogManifest] = MappingProxyType(
    {
        "gaia_dr3": VizierCatalogManifest(
            catalog="I/355",
            table="gaiadr3",
            qualified_table="I/355/gaiadr3",
            ra_column="RA_ICRS",
            dec_column="DE_ICRS",
            order_column="Source",
            fields=MappingProxyType(
                {
                    "source_id": VizierFieldManifest("Source", "identifier"),
                    "ra_degrees": VizierFieldManifest("RA_ICRS", "number", "deg"),
                    "dec_degrees": VizierFieldManifest("DE_ICRS", "number", "deg"),
                    "parallax_mas": VizierFieldManifest("Plx", "number", "mas"),
                    "pm_ra_mas_per_year": VizierFieldManifest(
                        "pmRA", "number", "mas/yr"
                    ),
                    "pm_dec_mas_per_year": VizierFieldManifest(
                        "pmDE", "number", "mas/yr"
                    ),
                    "g_mag": VizierFieldManifest("Gmag", "number", "mag"),
                    "bp_mag": VizierFieldManifest("BPmag", "number", "mag"),
                    "rp_mag": VizierFieldManifest("RPmag", "number", "mag"),
                }
            ),
            default_fields=(
                "source_id",
                "ra_degrees",
                "dec_degrees",
                "parallax_mas",
                "g_mag",
            ),
        ),
        "twomass_psc": VizierCatalogManifest(
            catalog="II/246",
            table="out",
            qualified_table="II/246/out",
            ra_column="RAJ2000",
            dec_column="DEJ2000",
            order_column="2MASS",
            fields=MappingProxyType(
                {
                    "source_id": VizierFieldManifest("2MASS", "text"),
                    "ra_degrees": VizierFieldManifest("RAJ2000", "number", "deg"),
                    "dec_degrees": VizierFieldManifest("DEJ2000", "number", "deg"),
                    "j_mag": VizierFieldManifest("Jmag", "number", "mag"),
                    "h_mag": VizierFieldManifest("Hmag", "number", "mag"),
                    "k_mag": VizierFieldManifest("Kmag", "number", "mag"),
                }
            ),
            default_fields=(
                "source_id",
                "ra_degrees",
                "dec_degrees",
                "j_mag",
                "h_mag",
                "k_mag",
            ),
        ),
    }
)
_TESS_PRODUCT_PATTERN = re.compile(
    r"^tess(?P<timestamp>\d{13})-s(?P<sector>\d{4})-"
    r"(?P<tic>\d{16})-(?P<pipeline>\d{4})-(?P<release>[a-z])_lc\.fits$"
)


@dataclass(frozen=True, slots=True)
class BoundedHttpResponse:
    status_code: int
    headers: Mapping[str, str]
    body: bytes
    url: str


class BoundedHttpClient:
    """Synchronous, injectable HTTP boundary with origin and byte budgets."""

    def __init__(
        self,
        *,
        origin: str,
        transport: httpx.BaseTransport | None = None,
        redirect_origins: tuple[str, ...] = (),
    ) -> None:
        self._origin = _normalized_origin(origin)
        self._redirect_origins = frozenset(
            _normalized_origin(item) for item in redirect_origins
        )
        self._transport = transport

    def request(
        self,
        method: Literal["GET", "POST"],
        path: str,
        *,
        params: Mapping[str, str] | None = None,
        data: Mapping[str, str] | None = None,
        timeout_seconds: float,
        max_bytes: int,
    ) -> BoundedHttpResponse:
        if not path.startswith("/") or path.startswith("//"):
            raise _failure(
                UpstreamFailureClass.policy_violation,
                "ASTRO_HTTP_PATH_POLICY_VIOLATION",
            )
        url = urljoin(f"{self._origin}/", path.removeprefix("/"))
        _require_origin(url, {self._origin})
        redirects = 0
        while True:
            response = self._send(
                method,
                url,
                params=params,
                data=data,
                timeout_seconds=timeout_seconds,
                max_bytes=max_bytes,
            )
            if response.status_code not in {301, 302, 303, 307, 308}:
                return response
            location = response.headers.get("location")
            if redirects or not location:
                raise _failure(
                    UpstreamFailureClass.policy_violation,
                    "ASTRO_HTTP_REDIRECT_POLICY_VIOLATION",
                    status_code=response.status_code,
                )
            target = urljoin(url, location)
            _require_origin(target, self._redirect_origins)
            url = target
            params = None
            data = None
            method = "GET"
            redirects += 1

    def _send(
        self,
        method: Literal["GET", "POST"],
        url: str,
        *,
        params: Mapping[str, str] | None,
        data: Mapping[str, str] | None,
        timeout_seconds: float,
        max_bytes: int,
    ) -> BoundedHttpResponse:
        try:
            with httpx.Client(
                transport=self._transport,
                timeout=timeout_seconds,
                follow_redirects=False,
                headers={"User-Agent": "xingwen-astro-ai/astro-acquisition"},
            ) as client:
                with client.stream(
                    method,
                    url,
                    params=params,
                    data=data,
                ) as response:
                    headers = {
                        key.casefold(): value for key, value in response.headers.items()
                    }
                    _raise_for_status(response.status_code)
                    declared = headers.get("content-length")
                    if declared is not None:
                        try:
                            declared_size = int(declared)
                        except ValueError as exc:
                            raise _failure(
                                UpstreamFailureClass.invalid_response,
                                "ASTRO_HTTP_INVALID_CONTENT_LENGTH",
                                status_code=response.status_code,
                            ) from exc
                        if declared_size < 0 or declared_size > max_bytes:
                            raise _failure(
                                UpstreamFailureClass.invalid_response,
                                "ASTRO_HTTP_RESPONSE_TOO_LARGE",
                                status_code=response.status_code,
                            )
                    chunks: list[bytes] = []
                    total = 0
                    for chunk in response.iter_bytes():
                        total += len(chunk)
                        if total > max_bytes:
                            raise _failure(
                                UpstreamFailureClass.invalid_response,
                                "ASTRO_HTTP_RESPONSE_TOO_LARGE",
                                status_code=response.status_code,
                            )
                        chunks.append(chunk)
                    return BoundedHttpResponse(
                        status_code=response.status_code,
                        headers=headers,
                        body=b"".join(chunks),
                        url=str(response.url),
                    )
        except SourceFailure:
            raise
        except httpx.TimeoutException as exc:
            raise _failure(
                UpstreamFailureClass.timeout,
                "ASTRO_HTTP_TIMEOUT",
                retryable=True,
            ) from exc
        except httpx.RequestError as exc:
            raise _failure(
                UpstreamFailureClass.transport,
                "ASTRO_HTTP_TRANSPORT_FAILED",
                retryable=True,
            ) from exc


class GaiaTapResponseCache(Protocol):
    """Project-scoped cache for one validated Gaia response payload."""

    def get(self, *, project_id: str, query_hash: str) -> dict[str, object] | None: ...

    def put(
        self,
        *,
        project_id: str,
        query_hash: str,
        payload: dict[str, object],
        retrieved_at: datetime,
    ) -> None: ...


class GaiaTapAdapter:
    """Controlled Gaia DR3 cone search; callers cannot submit ADQL."""

    def __init__(
        self,
        *,
        transport: httpx.BaseTransport | None = None,
        mode: AcquisitionMode = "live",
        cache: GaiaTapResponseCache | None = None,
    ) -> None:
        self._client = BoundedHttpClient(
            origin="https://gea.esac.esa.int",
            transport=transport,
        )
        self._mode = mode
        self._cache = cache

    def acquire(self, request: ScientificSkillRequest) -> dict[str, object]:
        reject_unknown(
            request.parameters,
            {
                "ra_degrees",
                "dec_degrees",
                "radius_degrees",
                "fields",
                "max_results",
                "response_format",
            },
        )
        ra = require_number(request.parameters, "ra_degrees")
        dec = require_number(request.parameters, "dec_degrees")
        radius = optional_number(request.parameters, "radius_degrees", default=0.05)
        max_results = optional_integer(
            request.parameters,
            "max_results",
            default=min(200, request.budget.max_output_rows),
            lower=1,
            upper=min(2_000, request.budget.max_output_rows),
        )
        response_format = optional_string(
            request.parameters, "response_format", default="csv"
        )
        if not 0 <= ra < 360 or not -90 <= dec <= 90:
            raise ValueError("Gaia cone center is outside the ICRS coordinate bounds")
        if not 0 < radius <= 1:
            raise ValueError("radius_degrees must be within (0, 1]")
        if response_format not in {"csv", "votable"}:
            raise ValueError("response_format must be csv or votable")
        requested_fields = (
            require_string_list(
                request.parameters, "fields", max_items=len(_GAIA_SOURCE_CONTRACT)
            )
            if "fields" in request.parameters
            else _GAIA_DEFAULT_FIELDS
        )
        fields = tuple(dict.fromkeys(("source_id", *requested_fields)))
        unsupported = tuple(
            field for field in fields if field not in _GAIA_SOURCE_CONTRACT
        )
        if unsupported:
            raise ValueError(f"unsupported Gaia fields: {list(unsupported)}")
        query = _gaia_cone_query(
            ra=ra,
            dec=dec,
            radius=radius,
            fields=fields,
            max_results=max_results + 1,
        )
        upstream_format = "csv" if response_format == "csv" else "votable"
        query_hash = compute_canonical_payload_hash(
            {
                "query": query,
                "response_format": response_format,
                "cache_version": GAIA_CACHE_VERSION,
            }
        )
        cached = (
            self._cache.get(project_id=request.project_id, query_hash=query_hash)
            if self._cache is not None
            else None
        )
        if cached is not None:
            return _cached_gaia_output(
                cached,
                fields=fields,
                response_format=response_format,
                query_hash=query_hash,
            )

        started = monotonic()
        schema_response = self._client.request(
            "POST",
            "/tap-server/tap/sync",
            data={
                "REQUEST": "doQuery",
                "LANG": "ADQL",
                "FORMAT": "csv",
                "QUERY": _gaia_schema_query(fields),
            },
            timeout_seconds=request.budget.timeout_seconds,
            max_bytes=min(request.budget.max_output_bytes, 1024 * 1024),
        )
        _validate_gaia_schema(schema_response.body, fields=fields)
        remaining_seconds = request.budget.timeout_seconds - (monotonic() - started)
        if remaining_seconds <= 0:
            raise _failure(
                UpstreamFailureClass.timeout,
                "GAIA_TAP_TIMEOUT_BUDGET_EXHAUSTED",
                retryable=True,
            )
        response = self._client.request(
            "POST",
            "/tap-server/tap/sync",
            data={
                "REQUEST": "doQuery",
                "LANG": "ADQL",
                "FORMAT": upstream_format,
                "QUERY": query,
            },
            timeout_seconds=remaining_seconds,
            max_bytes=request.budget.max_output_bytes,
        )
        fetched_rows = (
            _parse_gaia_csv(response.body, fields=fields, max_rows=max_results + 1)
            if response_format == "csv"
            else _parse_gaia_votable(
                response.body, fields=fields, max_rows=max_results + 1
            )
        )
        truncated = len(fetched_rows) > max_results
        rows = fetched_rows[:max_results]
        retrieved_at = datetime.now(UTC)
        output = {
            "service": "gaia_archive",
            "data_release": "gaiadr3",
            "coordinate_frame": "ICRS",
            "query_kind": "cone_search",
            "center": {"ra_degrees": ra, "dec_degrees": dec},
            "radius_degrees": radius,
            "fields": list(fields),
            "column_metadata": [
                {
                    "field": field,
                    "label": _GAIA_SOURCE_CONTRACT[field].label_zh,
                    "unit": _GAIA_SOURCE_CONTRACT[field].schema_unit,
                }
                for field in fields
            ],
            "row_count": len(rows),
            "rows": rows,
            "truncated": truncated,
            "result_status": (
                "empty" if not rows else "truncated" if truncated else "complete"
            ),
            "response_format": response_format,
            "acquisition": _acquisition_metadata(
                mode=self._mode,
                adapter="gaia_tap",
                version=GAIA_ADAPTER_VERSION,
                endpoint=GAIA_TAP_ENDPOINT,
                response=response,
            )
            | {
                "cache_version": GAIA_CACHE_VERSION,
                "query_hash": query_hash,
                "retrieved_at": retrieved_at.isoformat(),
                "schema_revision": GAIA_SCHEMA_REVISION,
                "schema_response_content_hash": (
                    f"sha256:{sha256(schema_response.body).hexdigest()}"
                ),
            },
        }
        if self._cache is not None:
            self._cache.put(
                project_id=request.project_id,
                query_hash=query_hash,
                payload=output,
                retrieved_at=retrieved_at,
            )
        return output


class VizierTapAdapter:
    """Controlled TAPVizieR ICRS cone query over an allowlisted catalog.

    The adapter owns one fixed cone-query template. Callers may select only a
    manifest alias and its allowlisted fields; they cannot submit a URL, table
    identifier, join, predicate, or arbitrary ADQL.
    """

    def __init__(
        self,
        *,
        transport: httpx.BaseTransport | None = None,
        mode: AcquisitionMode = "live",
    ) -> None:
        self._client = BoundedHttpClient(
            origin="https://tapvizier.cds.unistra.fr",
            transport=transport,
        )
        self._mode = mode

    def acquire(self, request: ScientificSkillRequest) -> dict[str, object]:
        reject_unknown(
            request.parameters,
            {
                "catalog_id",
                "table_id",
                "ra_degrees",
                "dec_degrees",
                "radius_degrees",
                "fields",
                "max_results",
                "response_format",
            },
        )
        catalog_id = optional_string(
            request.parameters, "catalog_id", default="gaia_dr3"
        )
        if catalog_id is None or catalog_id not in VIZIER_CATALOG_MANIFEST:
            raise ValueError("catalog_id is not allowlisted for TAPVizieR")
        manifest = VIZIER_CATALOG_MANIFEST[catalog_id]
        table_id = optional_string(
            request.parameters, "table_id", default=manifest.table
        )
        if table_id != manifest.table:
            raise ValueError("table_id is not allowlisted for the selected catalog")
        ra = require_number(request.parameters, "ra_degrees")
        dec = require_number(request.parameters, "dec_degrees")
        radius = optional_number(request.parameters, "radius_degrees", default=0.05)
        max_results = optional_integer(
            request.parameters,
            "max_results",
            default=min(200, request.budget.max_output_rows),
            lower=1,
            upper=min(2_000, request.budget.max_output_rows),
        )
        response_format = optional_string(
            request.parameters, "response_format", default="csv"
        )
        if not 0 <= ra < 360 or not -90 <= dec <= 90:
            raise ValueError("VizieR cone center is outside the ICRS coordinate bounds")
        if not 0 < radius <= 5:
            raise ValueError("radius_degrees must be within (0, 5]")
        if response_format not in {"csv", "votable"}:
            raise ValueError("response_format must be csv or votable")
        fields = (
            require_string_list(request.parameters, "fields", max_items=16)
            if "fields" in request.parameters
            else manifest.default_fields
        )
        unsupported = tuple(field for field in fields if field not in manifest.fields)
        if unsupported:
            raise ValueError(f"unsupported VizieR fields: {list(unsupported)}")
        query = _vizier_cone_query(
            manifest=manifest,
            ra=ra,
            dec=dec,
            radius=radius,
            fields=fields,
            max_results=max_results,
        )
        response = self._client.request(
            "POST",
            "/TAPVizieR/tap/sync",
            data={
                "REQUEST": "doQuery",
                "LANG": "ADQL",
                "FORMAT": response_format,
                "QUERY": query,
            },
            timeout_seconds=request.budget.timeout_seconds,
            max_bytes=request.budget.max_output_bytes,
        )
        rows = (
            _parse_vizier_csv(
                response.body,
                manifest=manifest,
                fields=fields,
                max_rows=max_results,
            )
            if response_format == "csv"
            else _parse_vizier_votable(
                response.body,
                manifest=manifest,
                fields=fields,
                max_rows=max_results,
            )
        )
        acquisition = _acquisition_metadata(
            mode=self._mode,
            adapter="vizier_tap",
            version=VIZIER_TAP_ADAPTER_VERSION,
            endpoint=VIZIER_TAP_ENDPOINT,
            response=response,
        ) | {
            "provider_uri": VIZIER_TAP_ENDPOINT,
            "provider_revision": VIZIER_TAP_ADAPTER_VERSION,
            "etag": response.headers.get("etag"),
            "raw_content_hash": f"sha256:{sha256(response.body).hexdigest()}",
        }
        return {
            "service": "vizier_tap",
            "catalog_id": catalog_id,
            "catalog": manifest.catalog,
            "table": manifest.table,
            "qualified_table": manifest.qualified_table,
            "query_kind": "icrs_cone",
            "coordinate_frame": "ICRS",
            "center": {"ra_degrees": ra, "dec_degrees": dec},
            "radius_degrees": radius,
            "fields": list(fields),
            "column_metadata": _column_metadata(
                fields,
                {field: manifest.fields[field].unit for field in fields},
            ),
            "row_count": len(rows),
            "rows": rows,
            "response_format": response_format,
            "provider_uri": VIZIER_TAP_ENDPOINT,
            "provider_revision": VIZIER_TAP_ADAPTER_VERSION,
            "etag": acquisition["source_version_or_etag"],
            "raw_content_hash": acquisition["response_content_hash"],
            "acquisition": acquisition,
        }


class SdssSpectrumAdapter:
    """Fetch and parse one official SDSS DR17 optical spectrum."""

    def __init__(
        self,
        *,
        transport: httpx.BaseTransport | None = None,
        mode: AcquisitionMode = "live",
    ) -> None:
        self._client = BoundedHttpClient(
            origin="https://data.sdss.org",
            transport=transport,
        )
        self._mode = mode

    def acquire(self, request: ScientificSkillRequest) -> dict[str, object]:
        reject_unknown(
            request.parameters,
            {"plate", "mjd", "fiber", "rest_wavelength", "line_sigma"},
        )
        plate = optional_integer(
            request.parameters, "plate", default=0, lower=1, upper=99_999
        )
        mjd = optional_integer(
            request.parameters, "mjd", default=0, lower=40_000, upper=99_999
        )
        fiber = optional_integer(
            request.parameters, "fiber", default=0, lower=1, upper=9_999
        )
        filename = f"spec-{plate:04d}-{mjd:05d}-{fiber:04d}.fits"
        response = self._client.request(
            "GET",
            f"/sas/dr17/eboss/spectro/redux/v5_13_2/spectra/full/{plate:04d}/{filename}",
            timeout_seconds=request.budget.timeout_seconds,
            max_bytes=request.budget.max_input_bytes,
        )
        typed_input = _parse_sdss_spectrum(
            response.body,
            object_name=f"SDSS DR17 {plate}-{mjd}-{fiber}",
            max_rows=request.budget.max_input_rows,
        )
        if "rest_wavelength" in request.parameters:
            typed_input["rest_wavelength"] = require_number(
                request.parameters, "rest_wavelength"
            )
        if "line_sigma" in request.parameters:
            typed_input["line_sigma"] = require_number(request.parameters, "line_sigma")
        typed_input["acquisition"] = _acquisition_metadata(
            mode=self._mode,
            adapter="sdss_dr17_spectrum",
            version=SDSS_SPECTRUM_ADAPTER_VERSION,
            endpoint=SDSS_DR17_SPECTRA_ROOT,
            response=response,
        ) | {
            "plate": plate,
            "mjd": mjd,
            "fiber": fiber,
            "product_filename": filename,
        }
        return typed_input


class MastLightCurveAdapter:
    """Fetch one mission-produced TESS light-curve product from MAST."""

    def __init__(
        self,
        *,
        transport: httpx.BaseTransport | None = None,
        mode: AcquisitionMode = "live",
    ) -> None:
        self._client = BoundedHttpClient(
            origin="https://mast.stsci.edu",
            transport=transport,
            redirect_origins=(MAST_TESS_STORAGE_ORIGIN,),
        )
        self._mode = mode

    def acquire(self, request: ScientificSkillRequest) -> dict[str, object]:
        reject_unknown(
            request.parameters,
            {
                "tic_id",
                "sector",
                "product_filename",
                "flux_kind",
                "sigma_clip",
                "minimum_period",
                "maximum_period",
            },
        )
        tic_id = optional_integer(
            request.parameters,
            "tic_id",
            default=0,
            lower=1,
            upper=9_999_999_999_999_999,
        )
        sector = optional_integer(
            request.parameters, "sector", default=0, lower=1, upper=9_999
        )
        product_filename = require_string(request.parameters, "product_filename")
        match = _TESS_PRODUCT_PATTERN.fullmatch(product_filename)
        if match is None:
            raise ValueError("product_filename is not a mission-produced TESS LC FITS")
        if int(match.group("sector")) != sector or int(match.group("tic")) != tic_id:
            raise ValueError("TESS product identity does not match tic_id and sector")
        flux_kind = optional_string(
            request.parameters, "flux_kind", default="pdcsap_flux"
        )
        if flux_kind not in {"pdcsap_flux", "sap_flux"}:
            raise ValueError("flux_kind must be pdcsap_flux or sap_flux")
        product_uri = f"mast:TESS/product/{product_filename}"
        response = self._client.request(
            "GET",
            "/api/v0.1/Download/file",
            params={"uri": product_uri},
            timeout_seconds=request.budget.timeout_seconds,
            max_bytes=request.budget.max_input_bytes,
        )
        typed_input = _parse_tess_light_curve(
            response.body,
            object_name=f"TIC {tic_id}",
            flux_kind=flux_kind,
            max_rows=request.budget.max_input_rows,
        )
        for key in ("sigma_clip", "minimum_period", "maximum_period"):
            if key in request.parameters:
                typed_input[key] = require_number(request.parameters, key)
        typed_input["acquisition"] = _acquisition_metadata(
            mode=self._mode,
            adapter="mast_tess_light_curve",
            version=MAST_LIGHT_CURVE_ADAPTER_VERSION,
            endpoint=MAST_DOWNLOAD_ENDPOINT,
            response=response,
        ) | {
            "tic_id": str(tic_id),
            "sector": sector,
            "product_uri": product_uri,
            "product_filename": product_filename,
            "flux_kind": flux_kind,
        }
        return typed_input


def query_gaia_dr3(request: ScientificSkillRequest) -> dict[str, object]:
    return GaiaTapAdapter().acquire(request)


def query_vizier_tap(request: ScientificSkillRequest) -> dict[str, object]:
    return VizierTapAdapter().acquire(request)


def acquire_and_analyze_sdss_spectrum(
    request: ScientificSkillRequest,
) -> dict[str, object]:
    typed_input = SdssSpectrumAdapter().acquire(request)
    acquisition = typed_input.pop("acquisition")
    analysis_request = request.model_copy(update={"parameters": typed_input})
    return analyze_spectrum(analysis_request) | {"acquisition": acquisition}


def acquire_and_analyze_mast_light_curve(
    request: ScientificSkillRequest,
) -> dict[str, object]:
    typed_input = MastLightCurveAdapter().acquire(request)
    acquisition = typed_input.pop("acquisition")
    analysis_request = request.model_copy(update={"parameters": typed_input})
    return analyze_light_curve(analysis_request) | {"acquisition": acquisition}


def _gaia_cone_query(
    *,
    ra: float,
    dec: float,
    radius: float,
    fields: tuple[str, ...],
    max_results: int,
) -> str:
    columns = ",".join(fields)
    return (
        f"SELECT TOP {max_results} {columns} FROM gaiadr3.gaia_source "
        "WHERE 1=CONTAINS(POINT('ICRS',ra,dec),"
        f"CIRCLE('ICRS',{ra:.12g},{dec:.12g},{radius:.12g})) "
        "ORDER BY source_id"
    )


def _gaia_schema_query(fields: tuple[str, ...]) -> str:
    selected = ",".join(f"'{field}'" for field in sorted(fields))
    return (
        "SELECT column_name,datatype,unit FROM TAP_SCHEMA.columns "
        "WHERE schema_name='gaiadr3' AND table_name='gaiadr3.gaia_source' "
        f"AND column_name IN ({selected}) ORDER BY column_name"
    )


def _validate_gaia_schema(content: bytes, *, fields: tuple[str, ...]) -> None:
    try:
        text = content.decode("utf-8-sig", errors="strict")
        reader = csv.DictReader(StringIO(text, newline=""), strict=True)
        if reader.fieldnames != ["column_name", "datatype", "unit"]:
            raise _invalid_response("GAIA_TAP_SCHEMA_DRIFT")
        rows = tuple(reader)
    except (UnicodeDecodeError, csv.Error) as exc:
        raise _invalid_response("GAIA_TAP_SCHEMA_DRIFT") from exc
    by_name = {str(row.get("column_name", "")): row for row in rows}
    if len(by_name) != len(rows) or set(by_name) != set(fields):
        raise _invalid_response("GAIA_TAP_SCHEMA_DRIFT")
    for field in fields:
        datatype = str(by_name[field].get("datatype", "")).strip().casefold()
        if datatype not in _GAIA_SCHEMA_DATATYPES[field]:
            raise _invalid_response("GAIA_TAP_SCHEMA_DRIFT")
        expected_unit = _GAIA_SCHEMA_UNITS.get(field)
        actual_unit = str(by_name[field].get("unit", "") or "").strip()
        if expected_unit is not None and actual_unit != expected_unit:
            raise _invalid_response("GAIA_TAP_SCHEMA_DRIFT")


def _cached_gaia_output(
    payload: dict[str, object],
    *,
    fields: tuple[str, ...],
    response_format: str,
    query_hash: str,
) -> dict[str, object]:
    if (
        payload.get("fields") != list(fields)
        or payload.get("response_format") != response_format
    ):
        raise _invalid_response("GAIA_TAP_CACHE_IDENTITY_MISMATCH")
    acquisition = payload.get("acquisition")
    if not isinstance(acquisition, dict):
        raise _invalid_response("GAIA_TAP_CACHE_PAYLOAD_INVALID")
    if (
        acquisition.get("cache_version") != GAIA_CACHE_VERSION
        or acquisition.get("query_hash") != query_hash
    ):
        raise _invalid_response("GAIA_TAP_CACHE_IDENTITY_MISMATCH")
    return {
        **payload,
        "acquisition": {**acquisition, "source_mode": "cached"},
    }


def _vizier_cone_query(
    *,
    manifest: VizierCatalogManifest,
    ra: float,
    dec: float,
    radius: float,
    fields: tuple[str, ...],
    max_results: int,
) -> str:
    """Build the one supported VizieR cone query from manifest values."""

    columns = ",".join(f'"{manifest.fields[field].column}"' for field in fields)
    return (
        f"SELECT TOP {max_results} {columns} "
        f'FROM "{manifest.qualified_table}" '
        f"WHERE 1=CONTAINS(POINT('ICRS',\"{manifest.ra_column}\","
        f'"{manifest.dec_column}"),'
        f"CIRCLE('ICRS',{ra:.12g},{dec:.12g},{radius:.12g})) "
        f'ORDER BY "{manifest.order_column}"'
    )


def _parse_gaia_csv(
    content: bytes, *, fields: tuple[str, ...], max_rows: int
) -> list[dict[str, object]]:
    try:
        text = content.decode("utf-8-sig", errors="strict")
    except UnicodeDecodeError as exc:
        raise _invalid_response("GAIA_TAP_CSV_ENCODING_INVALID") from exc
    reader = csv.DictReader(StringIO(text, newline=""))
    if reader.fieldnames is None or tuple(reader.fieldnames) != fields:
        raise _invalid_response("GAIA_TAP_SCHEMA_DRIFT")
    rows: list[dict[str, object]] = []
    for raw in reader:
        if len(rows) >= max_rows or None in raw:
            raise _invalid_response("GAIA_TAP_ROW_BOUNDARY_VIOLATION")
        rows.append(_coerce_gaia_row(raw, fields))
    return rows


def _parse_vizier_csv(
    content: bytes,
    *,
    manifest: VizierCatalogManifest,
    fields: tuple[str, ...],
    max_rows: int,
) -> list[dict[str, object]]:
    try:
        text = content.decode("utf-8-sig", errors="strict")
    except UnicodeDecodeError as exc:
        raise _invalid_response("VIZIER_TAP_CSV_ENCODING_INVALID") from exc
    field_columns = tuple(manifest.fields[field].column for field in fields)
    try:
        reader = csv.DictReader(StringIO(text, newline=""), strict=True)
        if reader.fieldnames is None or tuple(reader.fieldnames) != field_columns:
            raise _invalid_response("VIZIER_TAP_SCHEMA_DRIFT")
        rows: list[dict[str, object]] = []
        for raw in reader:
            if len(rows) >= max_rows or None in raw:
                raise _invalid_response("VIZIER_TAP_ROW_BOUNDARY_VIOLATION")
            rows.append(
                _coerce_vizier_row(
                    {field: raw.get(manifest.fields[field].column) for field in fields},
                    manifest=manifest,
                    fields=fields,
                )
            )
        return rows
    except csv.Error as exc:
        raise _invalid_response("VIZIER_TAP_CSV_MALFORMED") from exc


def _parse_vizier_votable(
    content: bytes,
    *,
    manifest: VizierCatalogManifest,
    fields: tuple[str, ...],
    max_rows: int,
) -> list[dict[str, object]]:
    try:
        from astropy.io.votable import parse_single_table

        table = parse_single_table(BytesIO(content), verify="exception").to_table(
            use_names_over_ids=True
        )
    except Exception as exc:
        raise _invalid_response("VIZIER_TAP_VOTABLE_INVALID") from exc
    field_columns = tuple(manifest.fields[field].column for field in fields)
    if tuple(table.colnames) != field_columns:
        raise _invalid_response("VIZIER_TAP_SCHEMA_DRIFT")
    if len(table) > max_rows:
        raise _invalid_response("VIZIER_TAP_ROW_BOUNDARY_VIOLATION")
    rows: list[dict[str, object]] = []
    for record in table:
        rows.append(
            _coerce_vizier_row(
                {
                    field: (
                        ""
                        if np.ma.is_masked(record[manifest.fields[field].column])
                        else str(record[manifest.fields[field].column])
                    )
                    for field in fields
                },
                manifest=manifest,
                fields=fields,
            )
        )
    return rows


def _coerce_vizier_row(
    raw: Mapping[str, object],
    *,
    manifest: VizierCatalogManifest,
    fields: tuple[str, ...],
) -> dict[str, object]:
    row: dict[str, object] = {}
    for field in fields:
        value = raw.get(field)
        text = "" if value is None else str(value).strip()
        if not text:
            row[field] = None
            continue
        spec = manifest.fields[field]
        if spec.value_kind == "identifier":
            if not text.isascii() or not text.isdigit() or len(text) > 32:
                raise _invalid_response("VIZIER_TAP_IDENTIFIER_INVALID")
            row[field] = text
            continue
        if spec.value_kind == "text":
            if (
                not text.isascii()
                or len(text) > 128
                or any(ord(character) < 32 for character in text)
            ):
                raise _invalid_response("VIZIER_TAP_TEXT_VALUE_INVALID")
            row[field] = text
            continue
        try:
            number = float(text)
        except ValueError as exc:
            raise _invalid_response("VIZIER_TAP_NUMERIC_VALUE_INVALID") from exc
        if not isfinite(number):
            raise _invalid_response("VIZIER_TAP_NUMERIC_VALUE_INVALID")
        row[field] = number
    return row


def _parse_gaia_votable(
    content: bytes, *, fields: tuple[str, ...], max_rows: int
) -> list[dict[str, object]]:
    try:
        from astropy.io.votable import parse_single_table

        table = parse_single_table(BytesIO(content), verify="exception").to_table(
            use_names_over_ids=True
        )
    except Exception as exc:
        raise _invalid_response("GAIA_TAP_VOTABLE_INVALID") from exc
    if tuple(table.colnames) != fields:
        raise _invalid_response("GAIA_TAP_SCHEMA_DRIFT")
    if len(table) > max_rows:
        raise _invalid_response("GAIA_TAP_ROW_BOUNDARY_VIOLATION")
    rows = []
    for record in table:
        raw = {
            field: ("" if np.ma.is_masked(record[field]) else str(record[field]))
            for field in fields
        }
        rows.append(_coerce_gaia_row(raw, fields))
    return rows


def _coerce_gaia_row(
    raw: Mapping[str, object], fields: tuple[str, ...]
) -> dict[str, object]:
    row: dict[str, object] = {}
    for field in fields:
        value = raw.get(field)
        text = "" if value is None else str(value).strip()
        if not text:
            row[field] = None
            continue
        if _GAIA_SOURCE_CONTRACT[field].value_kind == "identifier":
            if not text.isascii() or not text.isdigit() or len(text) > 32:
                raise _invalid_response("GAIA_TAP_IDENTIFIER_INVALID")
            row[field] = text
            continue
        try:
            number = float(text)
        except ValueError as exc:
            raise _invalid_response("GAIA_TAP_NUMERIC_VALUE_INVALID") from exc
        if not isfinite(number):
            raise _invalid_response("GAIA_TAP_NUMERIC_VALUE_INVALID")
        row[field] = number
    return row


def _parse_sdss_spectrum(
    content: bytes, *, object_name: str, max_rows: int
) -> dict[str, object]:
    try:
        from astropy.io import fits

        with fits.open(
            BytesIO(content),
            mode="readonly",
            memmap=False,
            lazy_load_hdus=False,
        ) as hdus:
            if not 2 <= len(hdus) <= 64 or hdus[1].data is None:
                raise ValueError("missing spectrum table")
            names = frozenset(name.casefold() for name in hdus[1].columns.names)
            required = {"flux", "loglam", "ivar", "and_mask"}
            if not required <= names:
                raise ValueError("spectrum table schema drift")
            data = hdus[1].data
            if len(data) > 100_000:
                raise ValueError("spectrum table exceeds row boundary")
            rows = []
            for raw in data:
                flux = float(raw["flux"])
                loglam = float(raw["loglam"])
                ivar = float(raw["ivar"])
                and_mask = int(raw["and_mask"])
                if (
                    and_mask != 0
                    or not all(isfinite(item) for item in (flux, loglam, ivar))
                    or ivar <= 0
                ):
                    continue
                wavelength = 10.0**loglam
                if not isfinite(wavelength) or wavelength <= 0:
                    continue
                rows.append(
                    {
                        "wavelength": wavelength,
                        "flux": flux,
                        "uncertainty": 1.0 / sqrt(ivar),
                    }
                )
    except (OSError, TypeError, ValueError, IndexError, KeyError) as exc:
        raise _invalid_response("SDSS_SPECTRUM_FITS_INVALID") from exc
    rows = _bounded_sample(rows, max_rows)
    if len(rows) < 8:
        raise _invalid_response("SDSS_SPECTRUM_INSUFFICIENT_VALID_SAMPLES")
    return {
        "rows": rows,
        "wavelength_field": "wavelength",
        "flux_field": "flux",
        "uncertainty_field": "uncertainty",
        "object_name": object_name,
        "wavelength_unit": "angstrom",
        "flux_unit": "1e-17 erg s-1 cm-2 angstrom-1",
    }


def _parse_tess_light_curve(
    content: bytes,
    *,
    object_name: str,
    flux_kind: str,
    max_rows: int,
) -> dict[str, object]:
    flux_column = flux_kind.upper()
    uncertainty_column = f"{flux_column}_ERR"
    try:
        from astropy.io import fits

        with fits.open(
            BytesIO(content),
            mode="readonly",
            memmap=False,
            lazy_load_hdus=False,
        ) as hdus:
            if not 2 <= len(hdus) <= 32 or hdus[1].data is None:
                raise ValueError("missing light-curve table")
            names = frozenset(hdus[1].columns.names)
            if not {"TIME", flux_column, uncertainty_column, "QUALITY"} <= names:
                raise ValueError("light-curve table schema drift")
            data = hdus[1].data
            if len(data) > 2_000_000:
                raise ValueError("light-curve table exceeds row boundary")
            rows = []
            for raw in data:
                time = float(raw["TIME"])
                value = float(raw[flux_column])
                uncertainty = float(raw[uncertainty_column])
                quality = int(raw["QUALITY"])
                if (
                    quality != 0
                    or not all(isfinite(item) for item in (time, value, uncertainty))
                    or uncertainty <= 0
                ):
                    continue
                rows.append({"time": time, "value": value, "uncertainty": uncertainty})
    except (OSError, TypeError, ValueError, IndexError, KeyError) as exc:
        raise _invalid_response("MAST_TESS_LIGHT_CURVE_FITS_INVALID") from exc
    rows = _bounded_sample(rows, max_rows)
    if len(rows) < 8:
        raise _invalid_response("MAST_TESS_INSUFFICIENT_VALID_SAMPLES")
    return {
        "rows": rows,
        "time_field": "time",
        "value_field": "value",
        "uncertainty_field": "uncertainty",
        "object_name": object_name,
        "time_scale": "tdb",
        "time_unit": "BTJD",
        "value_unit": "electron s-1",
        "value_kind": "flux",
    }


def _bounded_sample(
    rows: list[dict[str, object]], limit: int
) -> list[dict[str, object]]:
    if len(rows) <= limit:
        return rows
    indices = sorted({int(index) for index in np.linspace(0, len(rows) - 1, limit)})
    return [rows[index] for index in indices]


def _acquisition_metadata(
    *,
    mode: AcquisitionMode,
    adapter: str,
    version: str,
    endpoint: str,
    response: BoundedHttpResponse,
) -> dict[str, object]:
    return {
        "source_mode": mode,
        "adapter": adapter,
        "adapter_version": version,
        "endpoint": endpoint,
        "response_uri": response.url,
        "status_code": response.status_code,
        "content_length": len(response.body),
        "response_content_hash": f"sha256:{sha256(response.body).hexdigest()}",
        "source_version_or_etag": response.headers.get("etag"),
    }


def _normalized_origin(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise ValueError("astronomy acquisition origins must be credential-free HTTPS")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ValueError("astronomy acquisition origin must not contain a path")
    if parsed.port not in {None, 443}:
        raise ValueError("astronomy acquisition origin must use the default HTTPS port")
    return f"https://{parsed.hostname.casefold()}"


def _require_origin(url: str, allowed: frozenset[str] | set[str]) -> None:
    try:
        origin = _normalized_origin(f"{urlsplit(url).scheme}://{urlsplit(url).netloc}")
    except ValueError as exc:
        raise _failure(
            UpstreamFailureClass.policy_violation,
            "ASTRO_HTTP_ORIGIN_POLICY_VIOLATION",
        ) from exc
    if origin not in allowed:
        raise _failure(
            UpstreamFailureClass.policy_violation,
            "ASTRO_HTTP_ORIGIN_POLICY_VIOLATION",
        )


def _raise_for_status(status_code: int) -> None:
    if status_code in {301, 302, 303, 307, 308} or 200 <= status_code < 300:
        return
    if status_code == 429:
        raise _failure(
            UpstreamFailureClass.rate_limited,
            "ASTRO_HTTP_RATE_LIMITED",
            retryable=True,
            status_code=status_code,
        )
    if status_code >= 500:
        raise _failure(
            UpstreamFailureClass.upstream_server,
            "ASTRO_HTTP_UPSTREAM_SERVER_ERROR",
            retryable=True,
            status_code=status_code,
        )
    raise _failure(
        UpstreamFailureClass.upstream_client,
        "ASTRO_HTTP_UPSTREAM_CLIENT_ERROR",
        status_code=status_code,
    )


def _invalid_response(code: str) -> SourceFailure:
    return _failure(UpstreamFailureClass.invalid_response, code)


def _failure(
    classification: UpstreamFailureClass,
    code: str,
    *,
    retryable: bool = False,
    status_code: int | None = None,
) -> SourceFailure:
    return SourceFailure(
        classification,
        code,
        retryable=retryable,
        status_code=status_code,
    )


__all__ = [
    "BoundedHttpClient",
    "GAIA_CACHE_VERSION",
    "GAIA_SCHEMA_REVISION",
    "GaiaTapAdapter",
    "GaiaTapResponseCache",
    "MastLightCurveAdapter",
    "SdssSpectrumAdapter",
    "VIZIER_CATALOG_MANIFEST",
    "VIZIER_TAP_ADAPTER_VERSION",
    "VIZIER_TAP_ENDPOINT",
    "VizierCatalogManifest",
    "VizierFieldManifest",
    "VizierTapAdapter",
    "acquire_and_analyze_mast_light_curve",
    "acquire_and_analyze_sdss_spectrum",
    "query_gaia_dr3",
    "query_vizier_tap",
]
