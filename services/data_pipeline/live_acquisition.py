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
import math
from dataclasses import dataclass
from datetime import datetime, timezone

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.core import ResearchContract
from app.schemas.crossmatch import CrossmatchSourceInput
from app.schemas.enums import SourceMode
from app.schemas.evidence import SourceSnapshotRecord
from app.schemas.manifest import ManifestBundle
from app.schemas.source_acquisition import DataSourceDataLevel

from .query import normalize_toi_query
from .sources.nasa_exoplanet_archive import NasaExoplanetArchiveAdapter
from .sources.nasa_planetary_systems import (
    NasaPlanetarySystemsSupplementalAdapter,
)
from .sources.nasa_tap import NasaTapRequester
from .sources.base import DataSourceAcquisitionResult
from .supplemental_query import normalize_ps_supplemental_query


LOGGER = logging.getLogger(__name__)

#: Frozen target-selection policy for the supported research case: the
#: nearest confirmed planet-host systems, bounded for one live Run.
SELECTION_POLICY_ID = "nearby-confirmed-hosts"
SELECTION_POLICY_VERSION = "1.1.0"
SELECTION_MAX_TARGETS = 20
SELECTION_MAX_DISTANCE_PARSECS = 20

#: Frozen bounded acquisition window shared by both NASA sources.
ACQUISITION_PAGE_SIZE = 100
ACQUISITION_MAX_PAGES = 1
ACQUISITION_RECORD_LIMIT = 100

_TOI_PROVIDER_SOURCE_ID = "nasa_exoplanet_archive"

_DISCOVERY_QUERY = (
    "select t.tid,min(p.sy_dist) as distance_pc from toi t join ps p on "
    "p.tic_id = CONCAT('TIC ',CAST(t.tid AS VARCHAR(20))) "
    "where t.tfopwg_disp='CP' and p.default_flag=1 "
    "and p.sy_dist <= {max_distance} group by t.tid order by distance_pc,t.tid"
).format(
    max_distance=SELECTION_MAX_DISTANCE_PARSECS,
)


@dataclass(frozen=True)
class NearbyHostSelection:
    tic_ids: tuple[str, ...]
    provenance: dict[str, object]


def acquire_case_sources(
    bundle: ManifestBundle,
    contract: ResearchContract,
) -> tuple[CrossmatchSourceInput, CrossmatchSourceInput]:
    """Acquire the frozen case crossmatch inputs gated by the confirmed Contract."""

    _require_contract_scope(bundle, contract)
    selection = select_nearby_confirmed_hosts()
    tic_ids = selection.tic_ids
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
        _selected_source_input(left_result, selection),
        _selected_source_input(right_result, selection),
    )


def _selected_source_input(
    result: DataSourceAcquisitionResult, selection: NearbyHostSelection
) -> CrossmatchSourceInput:
    snapshot = SourceSnapshotRecord.model_validate(
        result.snapshot.model_dump()
        | {
            "request_metadata": result.snapshot.request_metadata
            | {"target_selection": selection.provenance}
        }
    )
    return CrossmatchSourceInput(
        source_mode=SourceMode.live,
        data_level=DataSourceDataLevel.live_result,
        records=result.records,
        snapshot=snapshot,
        completion=result.completion,
    )


def _require_contract_scope(bundle: ManifestBundle, contract: ResearchContract) -> None:
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


def select_nearby_confirmed_hosts() -> NearbyHostSelection:
    """Run the frozen nearby-confirmed-host selection against the NASA TAP service."""

    params = {
        "query": _DISCOVERY_QUERY,
        "format": "json",
        "MAXREC": SELECTION_MAX_TARGETS,
    }
    response, attempts, latency_ms = NasaTapRequester(
        failure_prefix="NASA_TARGET_DISCOVERY",
        source_label="nasa-nearby-confirmed-hosts",
        logger=LOGGER,
    ).request(params)
    try:
        payload = json.loads(response.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("NASA 目标发现结果无法验证") from error
    if not isinstance(payload, list) or not 1 <= len(payload) <= SELECTION_MAX_TARGETS:
        raise ValueError("NASA 目标发现结果未遵守记录边界")
    for item in payload:
        if (
            not isinstance(item, dict)
            or type(item.get("tid")) is not int
            or item["tid"] <= 0
            or type(item.get("distance_pc")) not in (int, float)
            or not math.isfinite(item["distance_pc"])
            or not 0 <= item["distance_pc"] <= SELECTION_MAX_DISTANCE_PARSECS
        ):
            raise ValueError("NASA 目标发现返回无效宿主标识或距离")
    tic_ids = tuple(str(item["tid"]) for item in payload)
    if len(tic_ids) != len(set(tic_ids)):
        raise ValueError("NASA 目标发现未返回唯一的有效 TIC 标识")
    if payload != sorted(payload, key=lambda item: (item["distance_pc"], item["tid"])):
        raise ValueError("NASA 目标发现未按距离与宿主标识稳定排序")
    return NearbyHostSelection(
        tic_ids=tic_ids,
        provenance={
            "policy_id": SELECTION_POLICY_ID,
            "policy_version": SELECTION_POLICY_VERSION,
            "request": params,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "selected_hosts": payload,
            "response_hash": compute_canonical_payload_hash(payload),
            "attempt_count": attempts,
            "latency_ms": latency_ms,
        },
    )


__all__ = [
    "ACQUISITION_MAX_PAGES",
    "ACQUISITION_PAGE_SIZE",
    "ACQUISITION_RECORD_LIMIT",
    "SELECTION_MAX_DISTANCE_PARSECS",
    "SELECTION_MAX_TARGETS",
    "SELECTION_POLICY_ID",
    "SELECTION_POLICY_VERSION",
    "acquire_case_sources",
    "select_nearby_confirmed_hosts",
]
