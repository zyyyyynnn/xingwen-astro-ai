"""Export or stale-check the sole current versionless ``/api`` OpenAPI document."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.contracts.current import create_current_contract_app


def render_openapi() -> str:
    return json.dumps(
        create_current_contract_app().openapi(),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    expected = render_openapi()
    if args.check:
        if not args.output.exists():
            print(f"missing: {args.output}", file=sys.stderr)
            return 1
        if args.output.read_text(encoding="utf-8") != expected:
            print(f"stale: {args.output}", file=sys.stderr)
            return 1
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(expected, encoding="utf-8")
    print(f"exported OpenAPI 3.1 contract to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
