"""Contract-gated live acquisition of the frozen exoplanet/host-star case.

The confirmed ResearchContract owns the scientific scope: this module fails
closed when the contract's target objects or allowed sources do not cover the
frozen case closure, instead of silently substituting a fixed target set. The
selection policy below is the frozen target-selection boundary for the
supported case; its bounds are explicit and versioned rather than scattered
magic numbers in the step runtime.
"""

from __future__ import annotations

import json
import logging

from app.schemas.core import ResearchContract
from app.schemas.crossmatch import CrossmatchSourceInput
from app.schemas.enums import SourceMode
from app.schemas.manifest import ManifestBundle
from app.schemas.source_acquisition import DataSourceDataLevel

from .query import normalize_toi_query
from .sources.nasa_exoplanet_archive import NasaExoplanetArchiveAdapter
from .sources.nasa_planetary_systems import (
    NasaPlanetarySystemsSupplementalAdapter,
)
from .sources.nasa_tap import NasaTapRequester
from .supplemental_query import normalize_ps_supplemental_query


LOGGER = logging.getLogger(__name__)

#: Frozen target-selection policy for the supported research case: the
#: nearest confirmed planet-host systems, bounded for one live Run.
SELECTION_POLICY_ID = "nearby-confirmed-hosts"
SELECTION_POLICY_VERSION = "1.0.0"
SELECTION_MAX_TARGETS = 20
SELECTION_MAX_DISTANCE_PARSECS = 20

#: Frozen bounded acquisition window shared by both NASA sources.
ACQUISITION_PAGE_SIZE = 100
ACQUISITION_MAX_PAGES = 1
ACQUISITION_RECORD_LIMIT = 100

_TOI_PROVIDER_SOURCE_ID = "nasa_exoplanet_archive"

_DISCOVERY_QUERY = (
    "select distinct top {max_targets} t.tid from toi t join ps p on "
    "p.tic_id = CONCAT('TIC ',CAST(t.tid AS VARCHAR(20))) "
    "where t.tfopwg_disp='CP' and p.default_flag=1 "
    "and p.sy_dist <= {max_distance} order by t.tid"
).format(
    max_targets=SELECTION_MAX_TARGETS,
    max_distance=SELECTION_MAX_DISTANCE_PARSECS,
)


def acquire_case_sources(
    bundle: ManifestBundle,
    contract: ResearchContract,
) -> tuple[CrossmatchSourceInput, CrossmatchSourceInput]:
    """Acquire the frozen case crossmatch inputs gated by the confirmed Contract."""

    _require_contract_scope(bundle, contract)
    tic_ids = discover_nearby_confirmed_tic_ids()
    mode = SourceMode.live
    level = DataSourceDataLevel.live_result
    left_result = NasaExoplanetArchiveAdapter(page_delay_seconds=0).acquire(
        normalize_toi_query(
            bundle,
            page_size=ACQUISITION_PAGE_SIZE,
            max_pages=ACQUISITION_MAX_PAGES,
            record_limit=ACQUISITION_RECORD_LIMIT,
            tic_ids=tic_ids,
            confirmed_only=True,
        ),
        source_mode=mode,
        data_level=level,
    )
    right_result = NasaPlanetarySystemsSupplementalAdapter(
        page_delay_seconds=0
    ).acquire(
        normalize_ps_supplemental_query(
            bundle,
            tic_ids=tic_ids,
            page_size=ACQUISITION_PAGE_SIZE,
            max_pages=ACQUISITION_MAX_PAGES,
            record_limit=ACQUISITION_RECORD_LIMIT,
            default_only=True,
            max_distance_parsecs=SELECTION_MAX_DISTANCE_PARSECS,
        ),
        source_mode=mode,
        data_level=level,
    )
    return (
        CrossmatchSourceInput(
            source_mode=mode,
            data_level=level,
            records=left_result.records,
            snapshot=left_result.snapshot,
            completion=left_result.completion,
        ),
        CrossmatchSourceInput(
            source_mode=mode,
            data_level=level,
            records=right_result.records,
            snapshot=right_result.snapshot,
            completion=right_result.completion,
        ),
    )


def _require_contract_scope(
    bundle: ManifestBundle, contract: ResearchContract
) -> None:
    """Fail closed unless the confirmed Contract covers the frozen case closure."""

    case_roles = {target.role for target in bundle.case_manifest.target_objects}
    contracted_roles = set(contract.target_objects)
    missing_roles = sorted(case_roles - contracted_roles)
    if missing_roles:
        raise ValueError(
            "ResearchContract target objects do not cover the frozen case "
            f"closure; missing: {missing_roles}"
        )
    allowed_providers = set(contract.source_scope.allowed_sources)
    if _TOI_PROVIDER_SOURCE_ID not in allowed_providers:
        raise ValueError(
            "ResearchContract source scope does not allow the frozen case "
            "primary data provider"
        )


def discover_nearby_confirmed_tic_ids() -> tuple[str, ...]:
    """Run the frozen nearby-confirmed-host selection against the NASA TAP service."""

    response, _, _ = NasaTapRequester(
        failure_prefix="NASA_TARGET_DISCOVERY",
        source_label="nasa-nearby-confirmed-hosts",
        logger=LOGGER,
    ).request({"query": _DISCOVERY_QUERY, "format": "json"})
    try:
        payload = json.loads(response.body.decode("utf-8"))
        tic_ids = tuple(
            str(item["tid"])
            for item in payload
            if isinstance(item, dict) and isinstance(item.get("tid"), int)
        )
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError) as error:
        raise ValueError("NASA 目标发现结果无法验证") from error
    if not tic_ids or len(tic_ids) != len(set(tic_ids)):
        raise ValueError("NASA 目标发现未返回唯一的有效 TIC 标识")
    return tic_ids


__all__ = [
    "ACQUISITION_MAX_PAGES",
    "ACQUISITION_PAGE_SIZE",
    "ACQUISITION_RECORD_LIMIT",
    "SELECTION_MAX_DISTANCE_PARSECS",
    "SELECTION_MAX_TARGETS",
    "SELECTION_POLICY_ID",
    "SELECTION_POLICY_VERSION",
    "acquire_case_sources",
    "discover_nearby_confirmed_tic_ids",
]
