from __future__ import annotations

import ast
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOOD_RESEARCH_SERVICE = "e72b7439d94e6947414c37b45adf52a80124eedd"
BENCHMARK_HANDOFF = "45a417fa9ce60795bde007c6cd48a718cee23285"
RETIRED_MODULES = {"app.schemas.reasoning", "app.schemas.graph"}
HISTORY_TOKENS = {
    "BenchmarkChangeRecord",
    "change_records",
    "review_sequence",
    "supersedes_review_id",
    "_effective_review_records",
}


def run(*args: str, cwd: Path | None = None) -> None:
    subprocess.run(args, cwd=cwd or ROOT, check=True)


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def write(relative: str, content: str) -> None:
    path = ROOT / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def restore_authoritative_sources() -> None:
    run(
        "git",
        "checkout",
        GOOD_RESEARCH_SERVICE,
        "--",
        "apps/api/src/app/services/research.py",
    )
    run(
        "git",
        "checkout",
        BENCHMARK_HANDOFF,
        "--",
        "apps/api/src/app/schemas/paper_benchmark.py",
        "apps/api/tests/test_paper_benchmark.py",
        "apps/api/tests/test_literature_claim_pipeline.py",
        "apps/api/tests/test_literature_relation_pipeline.py",
        "services/paper_pipeline/benchmarks/exoplanet_host_star/paper-reasoning-benchmark.json",
    )
    run("git", "checkout", "origin/main", "--", "apps/workspace/upstream")


def repair_research_service() -> None:
    relative = "apps/api/src/app/services/research.py"
    text = read(relative)
    text = text.replace(
        "from sqlalchemy import func, select\nfrom sqlalchemy.orm import Session",
        "from sqlalchemy import func, select\nfrom sqlalchemy.exc import IntegrityError\nfrom sqlalchemy.orm import Session",
    )
    text = text.replace(
        "            if contract.content is None or contract.created_from_draft_id is None:\n"
        "                raise _not_found(\"CONTRACT_NOT_FOUND\")\n",
        "",
    )
    text = text.replace(
        "            select(ResearchContractModel.id)\n"
        "            .where(\n"
        "                ResearchContractModel.project_id == project.id,\n"
        "                ResearchContractModel.content.is_not(None),\n"
        "            )\n",
        "            select(ResearchContractModel.id)\n"
        "            .where(ResearchContractModel.project_id == project.id)\n",
    )
    text = text.replace("    payload = dict(row.content or {})", "    payload = dict(row.content)")

    project_insert = """            session.add(model)\n            session.flush()\n            return self._project_read(session, model)\n"""
    project_safe = """            try:\n                with session.begin_nested():\n                    session.add(model)\n                    session.flush()\n            except IntegrityError as exc:\n                replay = session.scalar(\n                    select(ResearchProjectModel).where(\n                        ResearchProjectModel.session_id == session_id,\n                        ResearchProjectModel.idempotency_key == idempotency_key,\n                    )\n                )\n                if replay is None:\n                    raise\n                if replay.request_hash != request_hash:\n                    raise _idempotency_conflict() from exc\n                return self._project_read(session, replay)\n            return self._project_read(session, model)\n"""
    if project_insert not in text:
        raise RuntimeError("project insert block drifted")
    text = text.replace(project_insert, project_safe, 1)

    draft_insert = """            session.add(model)\n            session.flush()\n            return _draft(model)\n"""
    draft_safe = """            try:\n                with session.begin_nested():\n                    session.add(model)\n                    session.flush()\n            except IntegrityError as exc:\n                replay = session.scalar(\n                    select(ResearchContractDraftModel).where(\n                        ResearchContractDraftModel.session_id == session_id,\n                        ResearchContractDraftModel.idempotency_key == idempotency_key,\n                    )\n                )\n                if replay is None:\n                    raise\n                if replay.request_hash != request_hash:\n                    raise _idempotency_conflict() from exc\n                return _draft(replay)\n            return _draft(model)\n"""
    if draft_insert not in text:
        raise RuntimeError("draft insert block drifted")
    text = text.replace(draft_insert, draft_safe, 1)
    if any(
        token in text
        for token in ("CreateProjectRequest", "CreateContractDraftRequest", "ContractDraftUpdate")
    ):
        raise RuntimeError("accidental authoring DTO vocabulary remains")
    ast.parse(text)
    write(relative, text)


def repair_latest_version_fk() -> None:
    model_path = "apps/api/src/app/db/models.py"
    model = read(model_path)
    old_model_fk = """            name=\"fk_research_artifacts_latest_version_same_artifact\",\n            use_alter=True,\n            ondelete=\"SET NULL\",\n"""
    new_model_fk = """            name=\"fk_research_artifacts_latest_version_same_artifact\",\n            use_alter=True,\n            ondelete=\"RESTRICT\",\n"""
    if old_model_fk not in model:
        raise RuntimeError("ResearchArtifact current-pointer ORM FK drifted")
    write(model_path, model.replace(old_model_fk, new_model_fk, 1))

    migration_path = "apps/api/migrations/versions/schema_baseline.py"
    migration = read(migration_path)
    old_migration_fk = """        [\"latest_version_id\", \"id\"],\n        [\"id\", \"artifact_id\"],\n        ondelete=\"SET NULL\",\n"""
    new_migration_fk = """        [\"latest_version_id\", \"id\"],\n        [\"id\", \"artifact_id\"],\n        ondelete=\"RESTRICT\",\n"""
    if old_migration_fk not in migration:
        raise RuntimeError("ResearchArtifact current-pointer baseline FK drifted")
    write(migration_path, migration.replace(old_migration_fk, new_migration_fk, 1))


def _node_text(source: str, node: ast.AST) -> str:
    return ast.get_source_segment(source, node) or ""


def repair_benchmark_schema() -> None:
    relative = "apps/api/src/app/schemas/paper_benchmark.py"
    source = read(relative)
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    edits: list[tuple[int, int, str]] = []

    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "BenchmarkChangeRecord":
            edits.append((node.lineno, node.end_lineno or node.lineno, ""))
        elif isinstance(node, ast.FunctionDef) and node.name == "_effective_review_records":
            edits.append((node.lineno, node.end_lineno or node.lineno, ""))
        elif isinstance(node, ast.ClassDef) and node.name == "BenchmarkReviewRecord":
            for item in node.body:
                if (
                    isinstance(item, ast.AnnAssign)
                    and isinstance(item.target, ast.Name)
                    and item.target.id in {"review_sequence", "supersedes_review_id"}
                ):
                    edits.append((item.lineno, item.end_lineno or item.lineno, ""))
        elif isinstance(node, ast.ClassDef) and node.name == "BenchmarkPackagePayload":
            for item in node.body:
                if (
                    isinstance(item, ast.AnnAssign)
                    and isinstance(item.target, ast.Name)
                    and item.target.id == "change_records"
                ):
                    edits.append((item.lineno, item.end_lineno or item.lineno, ""))

    for start, end, replacement in sorted(edits, reverse=True):
        lines[start - 1 : end] = [replacement]
    text = "".join(lines)
    text = text.replace(
        "    review_records: tuple[BenchmarkReviewRecord, ...] = ()",
        "    review_records: tuple[BenchmarkReviewRecord, ...] = Field(min_length=1, max_length=1)",
    )
    text = text.replace(
        "        effective_review_records = _effective_review_records(self.review_records)",
        "        effective_review_records = self.review_records",
    )
    text = text.replace('        "change_records",\n', "")
    anchor = '        _require_unique_model_ids(self.review_records, "review_id", "review record")\n'
    binding = anchor + """        current_review = self.review_records[0]\n        if current_review.reviewed_benchmark_version != self.benchmark_version:\n            raise ValueError(\"scientific review must bind the current benchmark version\")\n        if current_review.reviewed_content_hash != self.scientific_payload_hash:\n            raise ValueError(\"scientific review must bind the current scientific payload hash\")\n"""
    if anchor not in text:
        raise RuntimeError("benchmark review validation anchor drifted")
    text = text.replace(anchor, binding, 1)
    if any(token in text for token in HISTORY_TOKENS):
        raise RuntimeError("historical benchmark machinery remains in schema")
    ast.parse(text)
    write(relative, text)


def repair_benchmark_asset() -> None:
    relative = "services/paper_pipeline/benchmarks/exoplanet_host_star/paper-reasoning-benchmark.json"
    path = ROOT / relative
    payload = json.loads(path.read_text(encoding="utf-8"))
    reviews = payload.get("review_records")
    if not isinstance(reviews, list) or len(reviews) != 1:
        raise RuntimeError("benchmark must contain exactly one current scientific review")
    review = reviews[0]
    review.pop("review_sequence", None)
    review.pop("supersedes_review_id", None)
    payload.pop("change_records", None)
    if review["reviewed_benchmark_version"] != payload["benchmark_version"]:
        raise RuntimeError("review benchmark identity mismatch")
    if review["reviewed_content_hash"] != payload["scientific_payload_hash"]:
        raise RuntimeError("review scientific payload identity mismatch")
    # Let the production Benchmark hashing boundary compute content_hash.
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    code = r'''
import json
from pathlib import Path
from app.schemas.paper_benchmark import BenchmarkPackage, compute_benchmark_content_hash, compute_benchmark_scientific_payload_hash
path = Path("services/paper_pipeline/benchmarks/exoplanet_host_star/paper-reasoning-benchmark.json")
payload = json.loads(path.read_text(encoding="utf-8"))
assert compute_benchmark_scientific_payload_hash(payload) == payload["scientific_payload_hash"]
payload["content_hash"] = compute_benchmark_content_hash(payload)
BenchmarkPackage.model_validate(payload)
path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
'''
    subprocess.run(
        ["uv", "run", "--project", "apps/api", "python", "-c", code],
        cwd=ROOT,
        check=True,
        env={**dict(__import__("os").environ), "PYTHONPATH": "apps/api/src"},
    )


def repair_benchmark_tests() -> None:
    relative = "apps/api/tests/test_paper_benchmark.py"
    source = read(relative)
    tree = ast.parse(source)

    class Transformer(ast.NodeTransformer):
        def visit_ImportFrom(self, node: ast.ImportFrom):  # noqa: N802
            node.names = [alias for alias in node.names if alias.name != "BenchmarkChangeRecord"]
            return node if node.names else None

        def visit_FunctionDef(self, node: ast.FunctionDef):  # noqa: N802
            if node.name == "_review_record":
                node.args.args = [
                    arg for arg in node.args.args if arg.arg not in {"sequence", "supersedes"}
                ]
                node.args.kwonlyargs = [
                    arg for arg in node.args.kwonlyargs if arg.arg not in {"sequence", "supersedes"}
                ]
                # Keep defaults aligned with keyword-only arguments.
                original_pairs = list(zip(node.args.kwonlyargs, node.args.kw_defaults))
                node.args.kwonlyargs = [pair[0] for pair in original_pairs]
                node.args.kw_defaults = [pair[1] for pair in original_pairs]
                for statement in node.body:
                    if isinstance(statement, ast.Return) and isinstance(statement.value, ast.Dict):
                        kept_keys: list[ast.expr | None] = []
                        kept_values: list[ast.expr] = []
                        for key, value in zip(statement.value.keys, statement.value.values):
                            if isinstance(key, ast.Constant) and key.value in {
                                "review_sequence",
                                "supersedes_review_id",
                            }:
                                continue
                            kept_keys.append(key)
                            kept_values.append(value)
                        statement.value.keys = kept_keys
                        statement.value.values = kept_values
                return self.generic_visit(node)
            if node.name.startswith("test_"):
                segment = _node_text(source, node)
                if any(token in segment for token in HISTORY_TOKENS) or "supersedes=" in segment or "sequence=" in segment:
                    return None
            return self.generic_visit(node)

    transformed = Transformer().visit(tree)
    ast.fix_missing_locations(transformed)
    text = ast.unparse(transformed) + "\n"
    if any(token in text for token in HISTORY_TOKENS):
        raise RuntimeError("historical benchmark test machinery remains")
    ast.parse(text)
    write(relative, text)


def remove_retired_projection_tests() -> None:
    for relative in (
        "apps/api/tests/test_literature_claim_pipeline.py",
        "apps/api/tests/test_literature_relation_pipeline.py",
    ):
        source = read(relative)
        tree = ast.parse(source)
        retired_aliases: set[str] = set()
        for node in tree.body:
            if isinstance(node, ast.ImportFrom) and node.module in RETIRED_MODULES:
                retired_aliases.update(alias.asname or alias.name for alias in node.names)

        class Transformer(ast.NodeTransformer):
            def visit_ImportFrom(self, node: ast.ImportFrom):  # noqa: N802
                if node.module in RETIRED_MODULES:
                    return None
                return node

            def visit_FunctionDef(self, node: ast.FunctionDef):  # noqa: N802
                if node.name.startswith("test_"):
                    segment = _node_text(source, node)
                    if any(re.search(rf"\b{re.escape(alias)}\b", segment) for alias in retired_aliases):
                        return None
                return self.generic_visit(node)

        transformed = Transformer().visit(tree)
        ast.fix_missing_locations(transformed)
        text = ast.unparse(transformed) + "\n"
        if any(re.search(rf"\b{re.escape(alias)}\b", text) for alias in retired_aliases):
            raise RuntimeError(f"retired projection alias remains in {relative}")
        ast.parse(text)
        write(relative, text)


def remove_publisher_retired_projection_knowledge() -> None:
    relative = "apps/api/src/app/workflow/publisher.py"
    text = read(relative)
    text = text.replace("    from app.schemas.graph import GraphResponse\n\n", "")
    text = re.sub(
        r"\n    if candidate_class is GraphResponse:\n        raise PublicationAdmissionError\(\n            \"Graph read projection cannot bypass .*?\"\n        \)\n",
        "\n",
        text,
        flags=re.S,
    )
    text = text.replace("Versioned Evidence Graph Pipeline", "Evidence Graph Pipeline")
    text = text.replace("Versioned Evidence Graph", "Evidence Graph")
    ast.parse(text)
    write(relative, text)


def delete_retired_schemas() -> None:
    remove_publisher_retired_projection_knowledge()
    hits: dict[str, list[str]] = {module: [] for module in RETIRED_MODULES}
    for path in (ROOT / "apps/api").rglob("*.py"):
        relative = path.relative_to(ROOT).as_posix()
        if relative in {
            "apps/api/src/app/schemas/graph.py",
            "apps/api/src/app/schemas/reasoning.py",
        }:
            continue
        source = path.read_text(encoding="utf-8", errors="ignore")
        for module in RETIRED_MODULES:
            if module in source:
                hits[module].append(relative)
    blocking = {module: paths for module, paths in hits.items() if paths}
    if blocking:
        raise RuntimeError(f"retired schemas still imported: {blocking}")
    for relative in (
        "apps/api/src/app/schemas/graph.py",
        "apps/api/src/app/schemas/reasoning.py",
    ):
        (ROOT / relative).unlink(missing_ok=True)


def repair_exporter_and_schema_families() -> None:
    relative = "scripts/export_schemas.py"
    text = read(relative)
    text = text.replace("PIPELINE_MODELS", "DATA_PIPELINE_MODELS")
    text = text.replace('"pipeline"', '"data_pipeline"')
    for module in (
        "app.schemas.dataset",
        "app.schemas.graph",
        "app.schemas.paper",
        "app.schemas.reasoning",
        "app.schemas.source",
        "app.schemas.task",
    ):
        text = re.sub(rf"^from {re.escape(module)} import \([^)]*\)\n", "", text, flags=re.M | re.S)
        text = re.sub(rf"^from {re.escape(module)} import .*\n", "", text, flags=re.M)
    ast.parse(text)
    write(relative, text)
    for family in ("phase0", "pipeline", "legacy", "v1", "v2"):
        path = ROOT / "packages/schemas/generated" / family
        if path.exists():
            shutil.rmtree(path)


def rename_paper_collection_runner() -> None:
    for base in (
        ROOT / "services/paper_pipeline",
        ROOT / "apps/api/tests",
        ROOT / "docs",
        ROOT / "packages/data-access",
    ):
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".py", ".md", ".json", ".ts"}:
                continue
            text = path.read_text(encoding="utf-8")
            if "PaperCollectionPipeline" in text:
                path.write_text(
                    text.replace("PaperCollectionPipeline", "PaperCollectionBenchmarkRunner"),
                    encoding="utf-8",
                    newline="\n",
                )
    relative = "services/paper_pipeline/pipeline.py"
    text = read(relative)
    text = text.replace(
        "Orchestrate paper acquisition without owning ResearchRun state or publication.",
        "Run scenario-driven benchmark paper acquisition without owning ResearchRun state or publication.",
    )
    text = text.replace(
        "Generate publisher-ready content while leaving publication to PaperCollection API.",
        "Run one benchmark scenario through reusable paper-search components; publication remains external.",
    )
    write(relative, text)


def clean_markdown_and_history() -> None:
    for path in ROOT.rglob("*.md"):
        relative = path.relative_to(ROOT).as_posix()
        if relative.startswith("apps/workspace/upstream/"):
            continue
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        reference = relative.startswith("docs/references/")
        filtered: list[str] = []
        for line in lines:
            if re.match(r"^\|\s*(?:Status|Issue|Superseded by|Time range)\s*\|", line, re.I):
                continue
            if reference and re.match(r"^\|\s*(?:元数据|[-: ]+)\s*\|", line):
                continue
            if reference and re.match(r"^\|\s*Authority\s*\|", line, re.I):
                continue
            filtered.append(line)
        text = "".join(filtered)
        text = text.replace("VERSIONED_DATA_ARTIFACTS.md", "DATA_ARTIFACTS.md")
        text = text.replace("Versioned Data Artifacts", "Data Artifacts")
        text = text.replace("Versioned Evidence Graph Pipeline", "Evidence Graph Pipeline")
        text = text.replace("Versioned Evidence Graph", "Evidence Graph")
        path.write_text(text, encoding="utf-8", newline="\n")

    api_path = ROOT / "docs/architecture/API_CONTRACT.md"
    api = api_path.read_text(encoding="utf-8")
    api = api.replace(
        "本文定义无版本前缀的单一 `/api/*` 接口面。包含 Core APIs 与 Pipeline APIs（`/api/health`、`/api/tasks*`）。系统仅做加法演进，不升级 URL 版本号。具体 Endpoints、DTOs 与字段由 Pydantic 编写源、OpenAPI 与生成的 Contract 权威定义。",
        "本文定义无版本前缀的单一 `/api/*` 接口面：当前 Research resource surface 与明确的 system endpoints（例如 `/api/health`）。系统不维护旧 API、目标 API、兼容 API 或 Task API；具体 Endpoints、DTOs 与字段由 Pydantic 编写源、OpenAPI 与生成的 Contract 权威定义。",
    )
    api = api.replace(
        "- 成功响应使用统一 Envelope；错误响应遵循 RFC 9457 Problem Details。",
        "- 单资源成功响应使用 `Envelope`，集合成功响应使用 `CollectionEnvelope`；错误响应统一遵循 RFC 9457 `ProblemDetails`。",
    )
    api_path.write_text(api, encoding="utf-8", newline="\n")

    for relative in (
        "packages/prompts/literature_reasoning/v1.md",
        "packages/prompts/paper_summary/v1.md",
        "services/data_pipeline/fixtures/exoplanet_host_star/nasa-toi-first-page.recorded.v1.json",
        "services/data_pipeline/manifests/exoplanet_host_star/quality-rules/quality-rules.v1.json",
        "services/data_pipeline/manifests/CHANGELOG.md",
        "services/paper_pipeline/benchmarks/CHANGELOG.md",
    ):
        (ROOT / relative).unlink(missing_ok=True)


def remove_fake_app_version() -> None:
    config_path = "apps/api/src/app/config.py"
    config = read(config_path).replace('    APP_VERSION: str = "0.1.0"\n', "")
    write(config_path, config)

    health_path = "apps/api/src/app/routers/health.py"
    health = read(health_path).replace(
        '    return {"status": "ok", "version": settings.APP_VERSION, "env": settings.APP_ENV}',
        '    return {"status": "ok", "env": settings.APP_ENV}',
    )
    write(health_path, health)

    main_path = "apps/api/src/app/main.py"
    main = read(main_path)
    if "from importlib.metadata import version as package_version\n" not in main:
        main = main.replace(
            "from datetime import timedelta\n",
            "from datetime import timedelta\nfrom importlib.metadata import version as package_version\n",
        )
    main = main.replace("        version=settings.APP_VERSION,", '        version=package_version("api"),')
    write(main_path, main)


def install_foundation_self_authoring_guard() -> None:
    relative = "scripts/check_foundation.py"
    text = read(relative)
    anchor = 'FORBIDDEN_FRONTEND_PACKAGE_PREFIXES = ("@vue/",)\n'
    addition = anchor + '''\nWORKFLOW_AUTHORING_ALLOWLIST: frozenset[str] = frozenset()\n_WORKFLOW_AUTHORING_PATTERNS = (\n    ("contents: write", re.compile(r"(?mi)^\\s*contents\\s*:\\s*write\\s*(?:#.*)?$")),\n    ("git commit", re.compile(r"(?i)\\bgit\\s+commit\\b")),\n    ("git push", re.compile(r"(?i)\\bgit\\s+push\\b")),\n)\n'''
    if "WORKFLOW_AUTHORING_ALLOWLIST" not in text:
        if anchor not in text:
            raise RuntimeError("foundation dependency anchor drifted")
        text = text.replace(anchor, addition, 1)
    helper_anchor = "\ndef main() -> int:\n"
    helper = '''\ndef workflow_authoring_violations(relative: str, content: str) -> tuple[str, ...]:\n    normalized = relative.replace("\\\\", "/")\n    if not normalized.startswith(".github/workflows/"):\n        return ()\n    if Path(normalized).suffix.lower() not in {".yml", ".yaml"}:\n        return ()\n    if normalized in WORKFLOW_AUTHORING_ALLOWLIST:\n        return ()\n    return tuple(\n        label for label, pattern in _WORKFLOW_AUTHORING_PATTERNS if pattern.search(content)\n    )\n\n\ndef main() -> int:\n'''
    if "def workflow_authoring_violations" not in text:
        if helper_anchor not in text:
            raise RuntimeError("foundation main anchor drifted")
        text = text.replace(helper_anchor, helper, 1)
    loop_anchor = '''        if normalized == "pnpm-lock.yaml":\n            for package_name in lockfile_package_names(\n                (ROOT / normalized).read_text(encoding="utf-8")\n            ):\n                if is_forbidden_frontend_package(package_name):\n                    errors.append(\n                        f"forbidden frontend dependency in {normalized}: {package_name}"\n                    )\n\n'''
    loop_addition = loop_anchor + '''        if normalized.startswith(".github/workflows/") and path.suffix.lower() in {\n            ".yml",\n            ".yaml",\n        }:\n            workflow = (ROOT / normalized).read_text(encoding="utf-8")\n            for violation in workflow_authoring_violations(normalized, workflow):\n                errors.append(\n                    f"self-authoring CI is forbidden in {normalized}: {violation}"\n                )\n\n'''
    if "self-authoring CI is forbidden" not in text:
        if loop_anchor not in text:
            raise RuntimeError("foundation tracked loop anchor drifted")
        text = text.replace(loop_anchor, loop_addition, 1)
    ast.parse(text)
    write(relative, text)

    test_relative = "scripts/test_check_foundation.py"
    write(
        test_relative,
        '''"""Tests for repository foundation boundaries."""\n\nfrom __future__ import annotations\n\nimport unittest\n\nfrom scripts.check_foundation import (\n    DEPENDENCY_FIELDS,\n    FORBIDDEN_FRONTEND_PACKAGES,\n    FORBIDDEN_FRONTEND_PACKAGE_PREFIXES,\n    WORKFLOW_AUTHORING_ALLOWLIST,\n    is_forbidden_frontend_package,\n    workflow_authoring_violations,\n)\n\n\nclass FrontendFoundationRulesTest(unittest.TestCase):\n    def test_dependency_boundary_covers_every_manifest_field(self) -> None:\n        self.assertEqual(\n            DEPENDENCY_FIELDS,\n            (\n                "dependencies",\n                "devDependencies",\n                "peerDependencies",\n                "optionalDependencies",\n            ),\n        )\n\n    def test_forbidden_frontend_packages_cover_exact_and_prefix_forms(self) -> None:\n        self.assertTrue(\n            all(is_forbidden_frontend_package(name) for name in FORBIDDEN_FRONTEND_PACKAGES)\n        )\n        self.assertTrue(\n            all(\n                is_forbidden_frontend_package(prefix + "fixture")\n                for prefix in FORBIDDEN_FRONTEND_PACKAGE_PREFIXES\n            )\n        )\n\n\nclass WorkflowFoundationRulesTest(unittest.TestCase):\n    def test_current_workflow_authoring_allowlist_is_empty(self) -> None:\n        self.assertEqual(WORKFLOW_AUTHORING_ALLOWLIST, frozenset())\n\n    def test_rejects_contents_write(self) -> None:\n        self.assertIn(\n            "contents: write",\n            workflow_authoring_violations(\n                ".github/workflows/ci.yml", "permissions:\\n  contents: write\\n"\n            ),\n        )\n\n    def test_rejects_git_commit_and_push(self) -> None:\n        self.assertEqual(\n            set(\n                workflow_authoring_violations(\n                    ".github/workflows/ci.yml",\n                    "run: |\\n  git commit -m rewrite\\n  git push origin HEAD\\n",\n                )\n            ),\n            {"git commit", "git push"},\n        )\n\n    def test_allows_read_only_validation(self) -> None:\n        self.assertEqual(\n            workflow_authoring_violations(\n                ".github/workflows/ci.yml", "permissions:\\n  contents: read\\n"\n            ),\n            (),\n        )\n\n\nif __name__ == "__main__":\n    unittest.main()\n''',
    )


def add_research_import_smoke_to_ci() -> None:
    relative = ".github/workflows/ci.yml"
    text = read(relative)
    if "Smoke current research import boundary" in text:
        return
    anchor = "      - name: Upgrade isolated PostgreSQL schema\n"
    smoke = '''      - name: Smoke current research import boundary\n        run: |\n          uv run python - <<'PY'\n          import app.main\n          from app.services.research import ResearchApplicationService\n          from app.routers import research\n          from app.schemas import core\n          print("research import boundary: OK")\n          PY\n\n'''
    if anchor not in text:
        raise RuntimeError("CI backend migration anchor drifted")
    write(relative, text.replace(anchor, smoke + anchor, 1))


def delete_development_migrations() -> None:
    versions = ROOT / "apps/api/migrations/versions"
    for path in versions.glob("*.py"):
        if path.name != "schema_baseline.py":
            path.unlink()


def final_static_assertions() -> None:
    for relative in (
        ".github/workflows/run-final-delegacy.yml",
        ".github/workflows/final-delegacy-maintenance.yml",
        ".github/workflows/benchmark-current-maintenance.yml",
        ".github/workflows/repository-maintenance.yml",
        ".github/workflows/one-time-delegacy-edit.yml",
        "scripts/finalize_delegacy_once.py",
        "README.nonexistent",
    ):
        if (ROOT / relative).exists():
            raise RuntimeError(f"one-shot authoring asset remains: {relative}")

    service = read("apps/api/src/app/services/research.py")
    for required in (
        "CreateResearchProjectRequest",
        "CreateResearchContractDraftRequest",
        "UpdateResearchContractDraftRequest",
        "ConfirmResearchContractRequest",
        "def create_draft",
        "def update_draft",
        "expected=request.expected_draft_version",
        "ResearchProjectModel.created_at.desc()",
        "session.begin_nested()",
    ):
        if required not in service:
            raise RuntimeError(f"Research service invariant missing: {required}")

    benchmark_schema = read("apps/api/src/app/schemas/paper_benchmark.py")
    benchmark_asset = read(
        "services/paper_pipeline/benchmarks/exoplanet_host_star/paper-reasoning-benchmark.json"
    )
    for token in HISTORY_TOKENS:
        if token in benchmark_schema or token in benchmark_asset:
            raise RuntimeError(f"Benchmark history token remains: {token}")

    for relative in (
        "apps/api/src/app/schemas/graph.py",
        "apps/api/src/app/schemas/reasoning.py",
    ):
        if (ROOT / relative).exists():
            raise RuntimeError(f"retired schema remains: {relative}")

    for family in ("phase0", "pipeline", "legacy", "v1", "v2"):
        if (ROOT / "packages/schemas/generated" / family).exists():
            raise RuntimeError(f"forbidden generated family remains: {family}")

    for path in ROOT.rglob("*.md"):
        relative = path.relative_to(ROOT).as_posix()
        if relative.startswith("apps/workspace/upstream/"):
            continue
        text = path.read_text(encoding="utf-8")
        if re.search(r"^\|\s*Status\s*\|", text, flags=re.M | re.I):
            raise RuntimeError(f"lifecycle Status metadata remains: {relative}")
        if "/api/tasks" in text:
            raise RuntimeError(f"retired Task API remains in governed Markdown: {relative}")

    if "PaperCollectionPipeline" in subprocess.run(
        ["git", "grep", "-n", "PaperCollectionPipeline", "--", ":!apps/workspace/upstream"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    ).stdout:
        raise RuntimeError("old PaperCollection runner identity remains")


def remove_scratch_assets() -> None:
    (ROOT / "scripts/pr209_scratch_repair.py").unlink(missing_ok=True)
    (ROOT / ".github/workflows/pr209-scratch-repair.yml").unlink(missing_ok=True)


def main() -> None:
    restore_authoritative_sources()
    repair_research_service()
    repair_latest_version_fk()
    repair_benchmark_schema()
    repair_benchmark_asset()
    repair_benchmark_tests()
    remove_retired_projection_tests()
    delete_retired_schemas()
    repair_exporter_and_schema_families()
    rename_paper_collection_runner()
    clean_markdown_and_history()
    remove_fake_app_version()
    install_foundation_self_authoring_guard()
    add_research_import_smoke_to_ci()
    delete_development_migrations()
    final_static_assertions()
    remove_scratch_assets()


if __name__ == "__main__":
    main()
