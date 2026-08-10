"""Repository foundation checks used by CI and local validation."""

from __future__ import annotations

import json
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
    ".gitattributes",
    "package.json",
    "pnpm-lock.yaml",
    "pnpm-workspace.yaml",
    "turbo.json",
    "scripts/check-docs.mjs",
    "scripts/check-docs-rules.mjs",
    "scripts/check-docs.test.mjs",
    "scripts/check-frontend-architecture.mjs",
    "scripts/test_check_foundation.py",
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
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "RESEARCH_INPUT_MAX_SIZE_BYTES",
    "RESEARCH_INPUT_ALLOWED_MIME_TYPES",
    "RESEARCH_INPUT_UPLOAD_DIR",
    "RESEARCH_INPUT_RATE_LIMIT",
    "RESEARCH_INPUT_IDEMPOTENCY_LEASE_SECONDS",
    "URL_FETCH_ALLOWED_PROTOCOLS",
    "URL_FETCH_ALLOWED_HOSTS",
    "URL_FETCH_TIMEOUT_SECONDS",
    "URL_FETCH_MAX_REDIRECTS",
    "URL_FETCH_MAX_RESPONSE_BYTES",
}

# These settings previously represented runtime switches or capabilities with no
# current consumer. A future implementation must introduce its exact consumed
# settings together with the implementation rather than reserving placeholders.
FORBIDDEN_ENV_KEYS = {
    "PERSISTENT_WORKFLOW_ENABLED",
    "DASHSCOPE_API_KEY",
    "QWEN_BASE_URL",
    "QWEN_MODEL",
    "QWEN_TIMEOUT_SECONDS",
    "PAPER_SOURCE_BASE_URL",
    "PAPER_SOURCE_API_KEY",
    "PAPER_SEARCH_TIMEOUT_SECONDS",
    "PAPER_SEARCH_MAX_RESULTS",
    "ENABLE_DEMO_CACHE",
    "CACHE_TTL_SECONDS",
    "DEMO_CASE_KEY",
}

DEPENDENCY_FIELDS = (
    "dependencies",
    "devDependencies",
    "peerDependencies",
    "optionalDependencies",
)
FORBIDDEN_FRONTEND_PACKAGES = {"vue", "vue-demi"}
FORBIDDEN_FRONTEND_PACKAGE_PREFIXES = ("@vue/",)


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


def is_forbidden_frontend_package(name: str) -> bool:
    normalized = name.lower()
    return normalized in FORBIDDEN_FRONTEND_PACKAGES or normalized.startswith(
        FORBIDDEN_FRONTEND_PACKAGE_PREFIXES
    )


def lockfile_package_names(content: str) -> set[str]:
    names: set[str] = set()
    in_resolution_section = False
    for line in content.splitlines():
        top_level = re.fullmatch(r"([a-z][a-zA-Z]*):\s*", line)
        if top_level:
            in_resolution_section = top_level.group(1) in {"packages", "snapshots"}
            continue
        if not in_resolution_section:
            continue
        entry = re.fullmatch(r"  (.+):\s*", line)
        if not entry:
            continue
        key = entry.group(1).strip("'\"").lstrip("/")
        separator = (
            key.find("@", key.find("/") + 1) if key.startswith("@") else key.find("@")
        )
        names.add(key[:separator] if separator > 0 else key)
    return names


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
        if path.name == "package.json":
            manifest = json.loads((ROOT / normalized).read_text(encoding="utf-8"))
            for field in DEPENDENCY_FIELDS:
                dependencies = manifest.get(field, {})
                for package_name in dependencies:
                    if is_forbidden_frontend_package(package_name):
                        errors.append(
                            f"forbidden frontend dependency in {normalized} "
                            f"({field}): {package_name}"
                        )

        if normalized == "pnpm-lock.yaml":
            for package_name in lockfile_package_names(
                (ROOT / normalized).read_text(encoding="utf-8")
            ):
                if is_forbidden_frontend_package(package_name):
                    errors.append(
                        f"forbidden frontend dependency in {normalized}: {package_name}"
                    )

    if lockfiles != ["pnpm-lock.yaml"]:
        errors.append(
            "expected exactly one root pnpm lockfile; found: "
            + (", ".join(sorted(lockfiles)) or "none")
        )

    env_path = ROOT / ".env.example"
    if env_path.exists():
        env_keys = parse_env_keys(env_path)
        for key in sorted(REQUIRED_ENV_KEYS - env_keys):
            errors.append(f".env.example missing key: {key}")
        for key in sorted(FORBIDDEN_ENV_KEYS & env_keys):
            errors.append(f".env.example contains unused placeholder key: {key}")

    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1

    print("repository foundation checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
