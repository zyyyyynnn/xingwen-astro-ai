"""Export every Pydantic model under ``app.schemas`` as JSON Schema.

The API Pydantic models are the Phase 0 authoring source. Generated contracts
are build artifacts consumed by frontend/type generation tooling later.
"""

from __future__ import annotations

import argparse
import importlib
import inspect
import json
import pkgutil
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel

import app.schemas as schema_package


def discover_models() -> dict[str, type[BaseModel]]:
    models: dict[str, type[BaseModel]] = {}

    for module_info in pkgutil.iter_modules(schema_package.__path__):
        if module_info.name.startswith("_"):
            continue

        module = importlib.import_module(f"{schema_package.__name__}.{module_info.name}")
        for name, candidate in inspect.getmembers(module, inspect.isclass):
            if candidate is BaseModel or not issubclass(candidate, BaseModel):
                continue
            if candidate.__module__ != module.__name__:
                continue
            if name in models:
                previous = models[name]
                raise RuntimeError(
                    f"duplicate schema class name {name}: "
                    f"{previous.__module__} and {candidate.__module__}"
                )
            models[name] = candidate

    return dict(sorted(models.items()))


def render_contracts(models: dict[str, type[BaseModel]]) -> dict[str, str]:
    rendered: dict[str, str] = {}
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "authoring_source": "apps/api/src/app/schemas",
        "models": [],
    }

    for name, model in models.items():
        relative_path = f"json/{name}.schema.json"
        schema = model.model_json_schema()
        rendered[relative_path] = json.dumps(
            schema,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n"
        manifest["models"].append(
            {
                "name": name,
                "module": model.__module__,
                "path": relative_path,
            }
        )

    rendered["manifest.json"] = json.dumps(
        manifest,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"
    return rendered


def write_contracts(output_dir: Path, rendered: dict[str, str]) -> None:
    for relative_path, content in rendered.items():
        target = output_dir / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def check_contracts(output_dir: Path, rendered: dict[str, str]) -> int:
    mismatches: list[str] = []

    for relative_path, expected in rendered.items():
        target = output_dir / relative_path
        if not target.exists():
            mismatches.append(f"missing: {target}")
            continue
        if target.read_text(encoding="utf-8") != expected:
            mismatches.append(f"stale: {target}")

    expected_paths = {output_dir / path for path in rendered}
    json_dir = output_dir / "json"
    if json_dir.exists():
        for existing in json_dir.glob("*.schema.json"):
            if existing not in expected_paths:
                mismatches.append(f"orphan: {existing}")

    if mismatches:
        print("\n".join(mismatches), file=sys.stderr)
        return 1
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("packages/schemas/generated"),
        help="directory receiving manifest.json and json/*.schema.json",
    )
    parser.add_argument(
        "--include",
        action="append",
        default=[],
        metavar="MODEL",
        help="export only the named model; repeat for multiple models",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail when generated files are missing or stale",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    models = discover_models()
    if args.include:
        unknown = sorted(set(args.include) - models.keys())
        if unknown:
            print(f"unknown schema model(s): {', '.join(unknown)}", file=sys.stderr)
            return 2
        models = {name: models[name] for name in sorted(set(args.include))}
    rendered = render_contracts(models)
    if args.check:
        return check_contracts(args.output, rendered)

    write_contracts(args.output, rendered)
    print(f"exported {len(rendered) - 1} schemas to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
