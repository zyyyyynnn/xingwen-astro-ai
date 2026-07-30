"""Bounded C-07 supplemental acquisition smoke/replay entrypoint."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import json
from pathlib import Path
import sys

from app.schemas.enums import SourceMode
from app.schemas.source_acquisition import DataSourceDataLevel

from .manifest import load_frozen_manifest_bundle
from .sources.base import SourceFailure
from .sources.nasa_planetary_systems import (
    NasaPlanetarySystemsSupplementalAdapter,
)
from .sources.supplemental_recorded import (
    DEFAULT_RECORDED_PS_FIXTURE_PATH,
    RecordedNasaPsTransport,
)
from .supplemental_query import normalize_ps_supplemental_query


DEFAULT_TIC_IDS = ("TIC 219698776",)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the bounded C-07 NASA PS supplemental adapter in live or "
            "explicitly recorded fixture mode. This command does not match "
            "entities or advance a ResearchRun."
        )
    )
    parser.add_argument("--mode", choices=("recorded", "live"), default="recorded")
    parser.add_argument(
        "--tic-id",
        action="append",
        dest="tic_ids",
        help="TIC identifier; repeat for multiple fixed inputs",
    )
    parser.add_argument("--page-size", type=int, default=2)
    parser.add_argument("--max-pages", type=int, default=1)
    parser.add_argument("--record-limit", type=int, default=2)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    query = normalize_ps_supplemental_query(
        load_frozen_manifest_bundle(),
        tic_ids=args.tic_ids or DEFAULT_TIC_IDS,
        page_size=args.page_size,
        max_pages=args.max_pages,
        record_limit=args.record_limit,
    )
    if args.mode == "recorded":
        try:
            transport = RecordedNasaPsTransport.from_path(
                DEFAULT_RECORDED_PS_FIXTURE_PATH,
                query=query,
            )
        except ValueError as exc:
            print(
                "recorded mode must use the captured input and pagination "
                "profile: "
                f"{exc}",
                file=sys.stderr,
            )
            return 2
        source_mode = SourceMode.fixture
        data_level = DataSourceDataLevel.recorded_response
    else:
        transport = None
        source_mode = SourceMode.live
        data_level = DataSourceDataLevel.live_result

    try:
        result = NasaPlanetarySystemsSupplementalAdapter(
            transport=transport,
            timeout_seconds=args.timeout,
        ).acquire(
            query,
            source_mode=source_mode,
            data_level=data_level,
        )
    except SourceFailure as exc:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "failure_class": exc.classification.value,
                    "failure_code": exc.code,
                    "retryable": exc.retryable,
                    "attempt_count": exc.attempt_count,
                    "status_code": exc.status_code,
                    "research_run_advanced": False,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1

    export_payload = {
        "schema_version": "1.0.0",
        "source_mode": source_mode.value,
        "data_level": data_level.value,
        "query": query.model_dump(mode="json"),
        "records": [record.model_dump(mode="json") for record in result.records],
        "pages": [page.model_dump(mode="json") for page in result.pages],
        "snapshot": result.snapshot.model_dump(mode="json"),
        "retry_count": result.retry_count,
        "research_run_advanced": False,
    }
    if args.output is not None:
        args.output.write_text(
            json.dumps(
                export_payload,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    summary = {
        "status": "completed",
        "source_mode": source_mode.value,
        "data_level": data_level.value,
        "record_count": len(result.records),
        "page_count": len(result.pages),
        "retry_count": result.retry_count,
        "input_hash": query.input_hash,
        "query_hash": query.query_hash,
        "snapshot_id": result.snapshot.snapshot_id,
        "content_hash": result.snapshot.content_hash,
        "request_id_status": result.snapshot.request_metadata["request_id_status"],
        "source_version_or_etag_status": result.snapshot.request_metadata[
            "source_version_or_etag_status"
        ],
        "research_run_advanced": False,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
