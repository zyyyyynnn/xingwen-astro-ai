from __future__ import annotations

import ast
import json
import re
import shutil
import subprocess
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HANDOFF = "45a417fa9ce60795bde007c6cd48a718cee23285"
HISTORY_TOKENS = {
    "review_sequence",
    "supersedes_review_id",
    "BenchmarkChangeRecord",
    "change_records",
    "_effective_review_records",
}
RETIRED_MODULES = {"app.schemas.reasoning", "app.schemas.graph"}
DATA_PIPELINE_MODELS = (
    "CrossmatchBenchmarkManifest",
    "CrossmatchBenchmarkReport",
    "CrossmatchInput",
    "CrossmatchResult",
    "DataArtifactBuildInput",
    "DataQualityEvaluationInput",
    "DataQualityEvaluationRejected",
    "DataQualityEvaluationResult",
    "DataQualityRuleSet",
    "DataSourceCompletion",
    "DatasetArtifactCandidate",
    "DatasetQualityResult",
    "FieldDictionaryArtifactCandidate",
    "FieldQualityResult",
    "MappingRuleSet",
    "QualityConstraintResult",
    "QualityEvaluationPlan",
    "QualityMetricPlan",
    "QualityMetricResult",
    "ResearchContractQualityGate",
    "RowQualityResult",
    "SourceCollectionArtifactCandidate",
    "UnitConversionCatalog",
)
OLD_EXPORT_ONLY_NAMES = {
    "ColumnInfo",
    "DatasetResponse",
    "EvidenceResponse",
    "LiteratureClaim",
    "LiteratureRelation",
    "PaperAcquisitionRun",
    "PaperCandidate",
    "PaperSearchQuery",
    "PaperSummary",
    "QualityScore",
    "ReasoningTrace",
    "SourceRecordItem",
    "SourceSnapshot",
}


def git(*args: str) -> None:
    subprocess.run(["git", *args], cwd=ROOT, check=True)


def restore_handoff_sources() -> None:
    git(
        "checkout",
        HANDOFF,
        "--",
        "apps/api/src/app/schemas/paper_benchmark.py",
        "apps/api/tests/test_paper_benchmark.py",
        "apps/api/tests/test_literature_claim_pipeline.py",
        "apps/api/tests/test_literature_relation_pipeline.py",
        "services/paper_pipeline/benchmarks/exoplanet_host_star/paper-reasoning-benchmark.json",
    )
    git("fetch", "origin", "main")
    git("checkout", "origin/main", "--", "apps/workspace/upstream")


def node_source(source: str, node: ast.AST) -> str:
    return ast.get_source_segment(source, node) or ""


class BenchmarkHistoryPruner(ast.NodeTransformer):
    def __init__(self, source: str) -> None:
        self.source = source

    def visit_ClassDef(self, node: ast.ClassDef):  # noqa: N802
        if node.name == "BenchmarkChangeRecord":
            return None
        if node.name == "BenchmarkReviewRecord":
            node.body = [
                item
                for item in node.body
                if not (
                    isinstance(item, ast.AnnAssign)
                    and isinstance(item.target, ast.Name)
                    and item.target.id in {"review_sequence", "supersedes_review_id"}
                )
            ]
        if node.name == "BenchmarkPackage":
            node.body = [
                item
                for item in node.body
                if not (
                    isinstance(item, ast.AnnAssign)
                    and isinstance(item.target, ast.Name)
                    and item.target.id == "change_records"
                )
            ]
        return self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef):  # noqa: N802
        if node.name == "_effective_review_records":
            return None
        node = self.generic_visit(node)
        node.body = [
            statement
            for statement in node.body
            if not any(
                token in node_source(self.source, statement)
                for token in {"change_records", "BenchmarkChangeRecord"}
            )
        ]
        if not node.body:
            node.body = [ast.Pass()]
        return node

    def visit_Call(self, node: ast.Call):  # noqa: N802
        node = self.generic_visit(node)
        if (
            isinstance(node.func, ast.Name)
            and node.func.id == "_effective_review_records"
            and len(node.args) == 1
        ):
            return node.args[0]
        return node


def transform_benchmark_schema() -> None:
    path = ROOT / "apps/api/src/app/schemas/paper_benchmark.py"
    source = path.read_text(encoding="utf-8")
    tree = BenchmarkHistoryPruner(source).visit(ast.parse(source))
    ast.fix_missing_locations(tree)
    package = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "BenchmarkPackage"
    )
    review_field = next(
        node
        for node in package.body
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == "review_records"
    )
    if not isinstance(review_field.value, ast.Call):
        raise RuntimeError("BenchmarkPackage.review_records must use Field")
    if "max_length" not in {kw.arg for kw in review_field.value.keywords}:
        review_field.value.keywords.append(
            ast.keyword(arg="max_length", value=ast.Constant(value=1))
        )
    validator = ast.parse(
        '''
@model_validator(mode="after")
def validate_current_scientific_review(self) -> Self:
    if len(self.review_records) != 1:
        raise ValueError("benchmark must contain exactly one current scientific review")
    review = self.review_records[0]
    if review.reviewed_benchmark_version != self.benchmark_version:
        raise ValueError("scientific review must bind the current benchmark version")
    if review.reviewed_content_hash != self.scientific_payload_hash:
        raise ValueError("scientific review must bind the current scientific payload hash")
    return self
'''
    ).body[0]
    package.body.append(validator)
    ast.fix_missing_locations(tree)
    transformed = ast.unparse(tree) + "\n"
    if any(token in transformed for token in HISTORY_TOKENS):
        raise RuntimeError("historical benchmark machinery remains in schema")
    ast.parse(transformed)
    path.write_text(transformed, encoding="utf-8")


def canonical_hash(payload: dict[str, object]) -> str:
    projected = dict(payload)
    projected.pop("content_hash", None)
    raw = json.dumps(
        projected, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + sha256(raw).hexdigest()


def transform_benchmark_asset() -> None:
    path = (
        ROOT
        / "services/paper_pipeline/benchmarks/exoplanet_host_star/paper-reasoning-benchmark.json"
    )
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
    payload["content_hash"] = canonical_hash(payload)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def remove_history_tests() -> None:
    path = ROOT / "apps/api/tests/test_paper_benchmark.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    replacements: list[tuple[int, int, str]] = []
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            names = [alias for alias in node.names if alias.name != "BenchmarkChangeRecord"]
            if len(names) != len(node.names):
                replacement = (
                    ast.unparse(
                        ast.ImportFrom(module=node.module, names=names, level=node.level)
                    )
                    + "\n"
                    if names
                    else ""
                )
                replacements.append(
                    (node.lineno, node.end_lineno or node.lineno, replacement)
                )
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and any(
            token in node_source(source, node) for token in HISTORY_TOKENS
        ):
            replacements.append((node.lineno, node.end_lineno or node.lineno, ""))
    for start, end, replacement in sorted(replacements, reverse=True):
        lines[start - 1 : end] = [replacement]
    updated = "".join(lines)
    ast.parse(updated)
    path.write_text(updated, encoding="utf-8")


def remove_retired_projection_tests() -> None:
    for relative in (
        "apps/api/tests/test_literature_claim_pipeline.py",
        "apps/api/tests/test_literature_relation_pipeline.py",
    ):
        path = ROOT / relative
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        retired_aliases: set[str] = set()
        replacements: list[tuple[int, int, str]] = []
        for node in tree.body:
            if isinstance(node, ast.ImportFrom) and node.module in RETIRED_MODULES:
                retired_aliases.update(alias.asname or alias.name for alias in node.names)
                replacements.append((node.lineno, node.end_lineno or node.lineno, ""))
        handled: set[str] = set()
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            segment = node_source(source, node)
            used = {
                alias
                for alias in retired_aliases
                if re.search(rf"\b{re.escape(alias)}\b", segment)
            }
            if not used:
                continue
            if not any(
                token in node.name for token in ("read", "projection", "bypass", "shape")
            ):
                raise RuntimeError(
                    f"{relative}:{node.lineno}: retired projection used by non-baseline test {node.name}"
                )
            handled.update(used)
            replacements.append((node.lineno, node.end_lineno or node.lineno, ""))
        if handled != retired_aliases:
            raise RuntimeError(
                f"{relative}: unhandled retired aliases {sorted(retired_aliases - handled)}"
            )
        lines = source.splitlines(keepends=True)
        for start, end, replacement in sorted(replacements, reverse=True):
            lines[start - 1 : end] = [replacement]
        updated = "".join(lines)
        ast.parse(updated)
        path.write_text(updated, encoding="utf-8")


class ExporterTransformer(ast.NodeTransformer):
    def visit_Name(self, node: ast.Name):  # noqa: N802
        if node.id == "PIPELINE_MODELS":
            return ast.copy_location(ast.Name(id="DATA_PIPELINE_MODELS", ctx=node.ctx), node)
        return node

    def visit_Constant(self, node: ast.Constant):  # noqa: N802
        if node.value == "pipeline":
            return ast.copy_location(ast.Constant(value="data_pipeline"), node)
        return node

    def visit_Assign(self, node: ast.Assign):  # noqa: N802
        node = self.generic_visit(node)
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "DATA_PIPELINE_MODELS":
                node.value = ast.Tuple(
                    elts=[ast.Name(id=name, ctx=ast.Load()) for name in DATA_PIPELINE_MODELS],
                    ctx=ast.Load(),
                )
        return node

    def visit_ImportFrom(self, node: ast.ImportFrom):  # noqa: N802
        if node.module in {
            "app.schemas.dataset",
            "app.schemas.graph",
            "app.schemas.paper",
            "app.schemas.reasoning",
            "app.schemas.source",
            "app.schemas.task",
        }:
            return None
        names = [alias for alias in node.names if alias.name not in OLD_EXPORT_ONLY_NAMES]
        if not names:
            return None
        node.names = names
        return node


def transform_exporter() -> None:
    path = ROOT / "scripts/export_schemas.py"
    source = path.read_text(encoding="utf-8")
    tree = ExporterTransformer().visit(ast.parse(source))
    ast.fix_missing_locations(tree)
    transformed = ast.unparse(tree) + "\n"
    if '"pipeline"' in transformed or "PIPELINE_MODELS" in transformed:
        raise RuntimeError("generic pipeline family remains in exporter")
    ast.parse(transformed)
    path.write_text(transformed, encoding="utf-8")


def classify_paper_runner() -> None:
    for base in (
        ROOT / "services/paper_pipeline",
        ROOT / "apps/api/tests",
        ROOT / "docs",
    ):
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix not in {".py", ".md"}:
                continue
            text = path.read_text(encoding="utf-8")
            if "PaperCollectionPipeline" in text:
                text = text.replace(
                    "PaperCollectionPipeline", "PaperCollectionBenchmarkRunner"
                )
                path.write_text(text, encoding="utf-8")
    path = ROOT / "services/paper_pipeline/pipeline.py"
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        "Orchestrate paper acquisition without owning ResearchRun state or publication.",
        "Run scenario-driven benchmark paper acquisition without owning ResearchRun state or publication.",
    )
    text = text.replace(
        "Generate publisher-ready content while leaving publication to PaperCollection API.",
        "Run a fixed benchmark scenario through reusable paper-acquisition components.",
    )
    path.write_text(text, encoding="utf-8")


def clean_docs_and_history_assets() -> None:
    for path in ROOT.rglob("*.md"):
        posix = path.relative_to(ROOT).as_posix()
        if posix.startswith("apps/workspace/upstream/"):
            continue
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        reference = posix.startswith("docs/references/")
        kept: list[str] = []
        for line in lines:
            if re.match(
                r"^\|\s*(?:Status|Issue|Superseded by|Time range)\s*\|", line, re.I
            ):
                continue
            if reference and re.match(r"^\|\s*Authority\s*\|", line, re.I):
                continue
            kept.append(line)
        updated = "".join(kept)
        updated = updated.replace("VERSIONED_DATA_ARTIFACTS.md", "DATA_ARTIFACTS.md")
        updated = updated.replace("Versioned Data Artifacts", "Data Artifacts")
        updated = updated.replace(
            "Versioned Evidence Graph Pipeline", "Evidence Graph Pipeline"
        )
        updated = updated.replace("Versioned Evidence Graph", "Evidence Graph")
        path.write_text(updated, encoding="utf-8")

    for relative in (
        "packages/prompts/literature_reasoning/v1.md",
        "packages/prompts/paper_summary/v1.md",
        "services/data_pipeline/fixtures/exoplanet_host_star/nasa-toi-first-page.recorded.v1.json",
        "services/data_pipeline/manifests/exoplanet_host_star/quality-rules/quality-rules.v1.json",
        "services/data_pipeline/manifests/CHANGELOG.md",
        "services/paper_pipeline/benchmarks/CHANGELOG.md",
    ):
        target = ROOT / relative
        if target.exists():
            target.unlink()


def fix_persistence_and_delete_old_modules() -> None:
    for relative in (
        "apps/api/src/app/db/models.py",
        "apps/api/migrations/versions/schema_baseline.py",
    ):
        path = ROOT / relative
        text = path.read_text(encoding="utf-8")
        text = text.replace('ondelete="SET NULL"', 'ondelete="RESTRICT"')
        path.write_text(text, encoding="utf-8")

    for module in RETIRED_MODULES:
        hits = []
        for path in (ROOT / "apps/api").rglob("*.py"):
            relative = path.relative_to(ROOT).as_posix()
            if relative in {
                "apps/api/src/app/schemas/graph.py",
                "apps/api/src/app/schemas/reasoning.py",
            }:
                continue
            if module in path.read_text(encoding="utf-8", errors="ignore"):
                hits.append(relative)
        if hits:
            raise RuntimeError(f"{module} still imported by {hits}")
    for relative in (
        "apps/api/src/app/schemas/graph.py",
        "apps/api/src/app/schemas/reasoning.py",
    ):
        target = ROOT / relative
        if target.exists():
            target.unlink()


def remove_old_generated_family() -> None:
    old = ROOT / "packages/schemas/generated/pipeline"
    if old.exists():
        shutil.rmtree(old)


def main() -> None:
    restore_handoff_sources()
    transform_benchmark_schema()
    transform_benchmark_asset()
    remove_history_tests()
    remove_retired_projection_tests()
    transform_exporter()
    classify_paper_runner()
    clean_docs_and_history_assets()
    fix_persistence_and_delete_old_modules()
    remove_old_generated_family()


if __name__ == "__main__":
    main()
