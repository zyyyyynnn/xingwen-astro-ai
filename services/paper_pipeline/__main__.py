"""Explicit live-smoke entrypoint for the frozen paper benchmark query."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.schemas.enums import PaperDataLevel, SourceMode

from .pipeline import PaperCollectionPipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the Paper Acquisition Pipeline Crossref metadata search against a frozen benchmark scenario."
        )
    )
    parser.add_argument(
        "--scenario",
        default="search.tess_mission_and_catalogs",
        choices=("search.tess_mission_and_catalogs", "search.host_star_provenance"),
    )
    parser.add_argument("--page-size", type=int, default=20)
    parser.add_argument("--selection-limit", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    collection = PaperCollectionPipeline(timeout_seconds=args.timeout).run(
        scenario_id=args.scenario,
        page_size=args.page_size,
        selection_limit=args.selection_limit,
        source_mode=SourceMode.live,
        data_level=PaperDataLevel.live_result,
    )
    if args.output:
        args.output.write_text(
            collection.model_dump_json(indent=2, exclude_none=True) + "\n",
            encoding="utf-8",
        )
    summary = {
        "scenario_id": collection.benchmark.scenario_id,
        "status": collection.acquisition_run.status,
        "source_mode": collection.source_executions[0].source_mode.value,
        "data_level": collection.source_executions[0].data_level.value,
        "candidate_count": collection.metrics.candidate_count,
        "selected_count": collection.metrics.selected_count,
        "candidate_recall": collection.metrics.candidate_recall,
        "source_failure_count": collection.metrics.source_failure_count,
        "input_hash": collection.input_hash,
        "output_hash": collection.output_hash,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if collection.acquisition_run.status == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
