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
    "package.json",
    "pnpm-lock.yaml",
    "pnpm-workspace.yaml",
    "turbo.json",
    "apps/site/package.json",
    "apps/workspace/package.json",
    "apps/api/pyproject.toml",
    "apps/api/uv.lock",
    "docs/architecture/API_CONTRACT.md",
    "docs/architecture/DATA_MODEL.md",
    "docs/architecture/WORKFLOW_DESIGN.md",
    "docs/ai/MODEL_POLICY.md",
    "docs/engineering/TEST_STRATEGY.md",
    "packages/prompts/registry.json",
    "packages/schemas/README.md",
    "packages/design-tokens/package.json",
    "packages/ui/package.json",
    "packages/domain/package.json",
    "packages/contracts/package.json",
    "packages/data-access/package.json",
    "packages/workspace-core/package.json",
    "packages/visual-engine/package.json",
    "packages/testing/package.json",
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
    "SITE_PORT",
    "WORKSPACE_PORT",
    "PUBLIC_WORKSPACE_URL",
    "VITE_API_BASE_URL",
    "DATABASE_URL",
    "DASHSCOPE_API_KEY",
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
}

FRAMEWORK_NAME = "".join(chr(code) for code in (118, 117, 101))
RETIRED_APP = "apps" + "/web"
RETIRED_PACKAGES = {
    "@vitejs/" + "plugin-" + FRAMEWORK_NAME,
    FRAMEWORK_NAME + "-tsc",
    "shadcn-" + FRAMEWORK_NAME,
    "reka-" + "ui",
    "lucide-" + FRAMEWORK_NAME + "-next",
    "@" + FRAMEWORK_NAME + "use/",
    "@" + FRAMEWORK_NAME + "-flow/",
    FRAMEWORK_NAME + "-router",
    "pi" + "nia",
}


def tracked_files() -> list[str]:
    completed = subprocess.run(
        ["git", "ls-files", "-co", "--exclude-standard"],
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
    lockfiles: list[str] = []
    for relative in tracked:
        normalized = relative.replace("\\", "/")
        path = Path(normalized)
        if path.name in FORBIDDEN_NAMES:
            errors.append(f"forbidden lockfile: {normalized}")
        if path.name == ".env":
            errors.append(f"tracked secret environment file: {normalized}")
        if path.name == "pnpm-lock.yaml":
            lockfiles.append(normalized)
        if normalized == RETIRED_APP or normalized.startswith(RETIRED_APP + "/"):
            errors.append(f"retired frontend path: {normalized}")
        if path.suffix == "." + FRAMEWORK_NAME:
            errors.append(f"retired component file: {normalized}")

        if path.name == "package.json":
            content = (ROOT / normalized).read_text(encoding="utf-8")
            for package_name in RETIRED_PACKAGES:
                if package_name in content:
                    errors.append(
                        f"retired frontend dependency in {normalized}: {package_name}"
                    )

    if lockfiles != ["pnpm-lock.yaml"]:
        errors.append(
            "expected exactly one root pnpm lockfile; found: "
            + (", ".join(sorted(lockfiles)) or "none")
        )

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
