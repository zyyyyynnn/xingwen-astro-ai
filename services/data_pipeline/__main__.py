"""Bounded primary source acquisition smoke/replay entrypoint; never advances ResearchRun."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from collections.abc import Sequence

from app.schemas.enums import SourceMode
from app.schemas.source_acquisition import DataSourceDataLevel

from .manifest import load_frozen_manifest_bundle
from .query import normalize_toi_query
from .sources.base import SourceFailure
from .sources.nasa_exoplanet_archive import NasaExoplanetArchiveAdapter
from .sources.recorded import (
    DEFAULT_RECORDED_TOI_FIXTURE_PATH,
    RecordedNasaToiTransport,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the bounded Primary Source Acquisition NASA TOI adapter in live or explicitly recorded "
            "fixture mode. This command does not create or advance a ResearchRun."
        )
    )
    parser.add_argument("--mode", choices=("recorded", "live"), default="recorded")
    parser.add_argument("--page-size", type=int, default=2)
    parser.add_argument("--max-pages", type=int, default=1)
    parser.add_argument("--record-limit", type=int, default=2)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    query = normalize_toi_query(
        load_frozen_manifest_bundle(),
        page_size=args.page_size,
        max_pages=args.max_pages,
        record_limit=args.record_limit,
    )
    if args.mode == "recorded":
        try:
            transport = RecordedNasaToiTransport.from_path(
                DEFAULT_RECORDED_TOI_FIXTURE_PATH,
                query=query,
            )
        except ValueError as exc:
            print(
                "recorded mode must use the fixture pagination profile "
                "(--page-size 2 --max-pages 1 --record-limit 2): "
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
        result = NasaExoplanetArchiveAdapter(
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
