"""Repository foundation checks used by CI and local validation."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = (
    "README.md",
    "AGENTS.md",
    "DESIGN.md",
    "PRD.md",
    "docker-compose.yml",
    ".env.example",
    "apps/web/package.json",
    "apps/web/pnpm-lock.yaml",
    "apps/api/pyproject.toml",
    "apps/api/uv.lock",
    "docs/architecture/API_CONTRACT.md",
    "docs/architecture/DATA_MODEL.md",
    "docs/architecture/WORKFLOW_DESIGN.md",
    "docs/ai/MODEL_POLICY.md",
    "docs/engineering/TEST_STRATEGY.md",
    "packages/prompts/registry.json",
    "packages/schemas/README.md",
)

FORBIDDEN_NAMES = {
    "package-lock.json",
    "yarn.lock",
    "bun.lock",
    "bun.lockb",
}

REQUIRED_ENV_KEYS = {
    "APP_ENV",
    "DEBUG",
    "CORS_ORIGINS",
    "VITE_API_BASE_URL",
    "DATABASE_URL",
    "DASHSCOPE_API_KEY",
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
}


def tracked_files() -> list[str]:
    completed = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [line for line in completed.stdout.splitlines() if line]


def parse_env_keys(path: Path) -> set[str]:
    keys: set[str] = set()
    pattern = re.compile(r"^([A-Z][A-Z0-9_]*)=")
    for line in path.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line.strip())
        if match:
            keys.add(match.group(1))
    return keys


def main() -> int:
    errors: list[str] = []

    for relative in REQUIRED_FILES:
        if not (ROOT / relative).is_file():
            errors.append(f"missing required file: {relative}")

    tracked = tracked_files()
    for relative in tracked:
        path = Path(relative)
        if path.name in FORBIDDEN_NAMES:
            errors.append(f"forbidden lockfile: {relative}")
        if path.name == ".env":
            errors.append(f"tracked secret environment file: {relative}")

    env_path = ROOT / ".env.example"
    if env_path.exists():
        missing_keys = sorted(REQUIRED_ENV_KEYS - parse_env_keys(env_path))
        for key in missing_keys:
            errors.append(f".env.example missing key: {key}")

    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1

    print("repository foundation checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
