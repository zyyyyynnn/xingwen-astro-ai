"""Validate a produced Scientific Document Parsing Contract native benchmark report artifact (fail-closed).

Checks that the benchmark genuinely ran with no silent skips:
- the report parses as a Scientific Document Parsing Contract ``BenchmarkReport``;
- ``output_hash`` self-verifies (deterministic payload);
- at least one case ran (no silent skip / empty report);
- every fixture case carries a real ``output_hash`` and ``input_hash``;
- declared metrics include the measured coverage metrics.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from app.schemas.scientific_document_benchmark import BenchmarkReport


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: check_scientific_document_benchmark_report.py <report.json>", file=sys.stderr)
        return 2
    path = Path(sys.argv[1])
    if not path.is_file():
        print(f"benchmark report missing: {path}", file=sys.stderr)
        return 1
    data = json.loads(path.read_text(encoding="utf-8"))
    report = BenchmarkReport.model_validate(data)  # raises if output_hash mismatches

    errors: list[str] = []
    if len(report.cases) == 0:
        errors.append("benchmark report has zero cases (silent skip?)")
    for case in report.cases:
        if not case.output_hash.startswith("sha256:"):
            errors.append(f"case {case.entry_id} missing output_hash")
        if not case.input_hash.startswith("sha256:"):
            errors.append(f"case {case.entry_id} missing input_hash")

    metric_names = {m.name for m in report.metrics}
    for required in ("accepted_rate", "native_routing_coverage"):
        if required not in metric_names:
            errors.append(f"benchmark report missing metric {required}")

    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(
        f"Scientific Document Parsing Contract benchmark report valid: {len(report.cases)} cases, "
        f"output_hash={report.output_hash}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
