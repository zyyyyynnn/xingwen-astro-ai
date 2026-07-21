from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "api" / "src"))

from app.schemas.paper_benchmark import (  # noqa: E402
    BenchmarkPackage,
    compute_benchmark_content_hash,
    compute_benchmark_scientific_payload_hash,
)

BENCHMARK_PATH = (
    ROOT
    / "services"
    / "paper_pipeline"
    / "benchmarks"
    / "exoplanet_host_star"
    / "paper-reasoning-benchmark.v1.json"
)
CHANGELOG_PATH = ROOT / "services" / "paper_pipeline" / "benchmarks" / "CHANGELOG.md"
README_PATH = ROOT / "services" / "paper_pipeline" / "benchmarks" / "README.md"
TEST_PATH = ROOT / "apps" / "api" / "tests" / "test_paper_benchmark.py"

VERSION = "1.3.0"
REVIEWED_HEAD = "1a541bb84d9d022bca3da137f4ec41bf60b6aab8"
SCIENTIFIC_HASH = "sha256:32db9d4345d904f3f5b9fbe975c41cdfebd4fb45ecc5747e6845959bd220e9cd"

TECHNICAL_BODY = """review_type: web_gpt
review_purpose: pr_technical_review
review_scope:
  target_type: pull_request
  target_ids: [zyyyyynnn/xingwen-astro-ai#96]
reviewed_head_sha: 1a541bb84d9d022bca3da137f4ec41bf60b6aab8
reviewed_benchmark_version: 1.3.0
reviewed_scientific_payload_hash: sha256:32db9d4345d904f3f5b9fbe975c41cdfebd4fb45ecc5747e6845959bd220e9cd
verdict: PASS
blocking_findings: []
non_blocking_findings:
  - GitHub 连接身份与 PR 作者相同，因此本结论以 COMMENTED Review 保存；正文中的明确 PASS、HEAD 与完整 PR scope 构成仓库治理要求的有效技术审查记录。
  - 未单独运行 ruff format --check 可接受：该命令不属于当前仓库 CI，且会要求修改既有无关文件；当前 Ruff check、仓库 format:check、CI 与 diff 检查均通过。
reviewed_at: 2026-07-21T14:49:27+08:00
evidence_actor_identity: github:zyyyyynnn
review_evidence_state: COMMENTED

结论：当前 HEAD 的技术契约、Review 演进、scientific/content hash、完整 PR scope、GitHub state/verdict、Crossref documented/observed 分层、测试与治理文档均满足合并要求。后续若 HEAD 变化，本 Review 自动失效。"""

SCIENTIFIC_BODY = """review_type: web_gpt
review_purpose: benchmark_scientific_review
review_scope:
  target_type: benchmark_package
  target_ids: [exoplanet_host_star.paper_reasoning]
  coverage: all declared source policies, seed papers, summaries, evidence, claims, relations, reasoning traces, and graph edges
reviewed_head_sha: 1a541bb84d9d022bca3da137f4ec41bf60b6aab8
reviewed_benchmark_version: 1.3.0
reviewed_scientific_payload_hash: sha256:32db9d4345d904f3f5b9fbe975c41cdfebd4fb45ecc5747e6845959bd220e9cd
verdict: PASS
blocking_findings: []
non_blocking_findings:
  - 当前结论限定于已声明的公开摘要与书目证据，不扩大为全文级、对象级或实时数据源科学保证。
  - Clark 样本边界应继续保持为 GALAH DR2、TIC、Gaia DR2 的特定交叉匹配样本，不推广到所有 TESS target 或 host star。
reviewed_at: 2026-07-21T14:49:27+08:00
evidence_actor_identity: github:zyyyyynnn
review_evidence_state: COMMENTED

科研核验结论：六篇 seed paper 的核心书目信息与摘要证据可复现；revised TIC extends initial TIC 的 accepted 关系有摘要依据；Clark→revised TIC 已正确降为 candidate 并撤出 Graph；host-property dependency→TOI candidate count 已正确改为 rejected negative example；Graph 仅保留有证据且 accepted 的跨文献关系。当前 version/hash 的 Benchmark 科研内容通过。后续若 scientific payload hash 或 HEAD 变化，本 Review 自动失效。"""


def full_scientific_scope(payload: dict[str, object]) -> list[dict[str, object]]:
    return [
        {"target_type": "benchmark_package", "target_ids": [payload["benchmark_id"]]},
        {
            "target_type": "source_policy",
            "target_ids": [item["source_id"] for item in payload["source_policies"]],
        },
        {
            "target_type": "seed_paper",
            "target_ids": [item["paper_id"] for item in payload["seed_papers"]],
        },
        {
            "target_type": "paper_summary",
            "target_ids": [item["summary_id"] for item in payload["paper_summaries"]],
        },
        {
            "target_type": "evidence",
            "target_ids": [item["evidence_id"] for item in payload["evidence"]],
        },
        {
            "target_type": "claim",
            "target_ids": [item["claim_id"] for item in payload["claims"]],
        },
        {
            "target_type": "relation",
            "target_ids": [item["relation_id"] for item in payload["relations"]],
        },
        {
            "target_type": "reasoning_trace",
            "target_ids": [item["trace_id"] for item in payload["reasoning_traces"]],
        },
        {
            "target_type": "graph_edge",
            "target_ids": [item["edge_id"] for item in payload["graph"]["edges"]],
        },
    ]


def replace_function_body(text: str, name: str, replacement: str) -> str:
    pattern = rf"def {re.escape(name)}\(.*?(?=\n\ndef |\Z)"
    updated, count = re.subn(pattern, replacement.rstrip(), text, count=1, flags=re.S)
    if count != 1:
        raise RuntimeError(f"could not replace function {name}")
    return updated


def main() -> None:
    payload = json.loads(BENCHMARK_PATH.read_text(encoding="utf-8"))
    if payload["benchmark_version"] != VERSION:
        raise RuntimeError(f"unexpected benchmark version: {payload['benchmark_version']}")
    if payload["scientific_payload_hash"] != SCIENTIFIC_HASH:
        raise RuntimeError("scientific payload changed after the recorded review")

    payload["review_status"] = "approved"
    for collection_name in (
        "paper_summaries",
        "evidence",
        "claims",
        "relations",
        "reasoning_traces",
    ):
        for item in payload[collection_name]:
            item["review_status"] = "approved"

    payload["review_records"] = [
        {
            "review_id": "review.pr_96_technical_pass",
            "review_sequence": 1,
            "supersedes_review_id": None,
            "reviewed_at": "2026-07-21T14:50:21+08:00",
            "reviewer_type": "web_gpt",
            "reviewer_identity": "openai:web-gpt",
            "reviewer_role": "pull_request_reviewer",
            "review_purpose": "pr_technical_review",
            "verdict": "pass",
            "reviewed_head_sha": REVIEWED_HEAD,
            "reviewed_benchmark_version": VERSION,
            "reviewed_content_hash": SCIENTIFIC_HASH,
            "scope": [
                {
                    "target_type": "pull_request",
                    "target_ids": ["zyyyyynnn/xingwen-astro-ai#96"],
                }
            ],
            "blocking_findings": [],
            "non_blocking_findings": [
                "GitHub author identity and reviewer evidence actor are the repository owner; the COMMENTED body records an explicit PASS bound to the final reviewed HEAD."
            ],
            "notes": "Web GPT technical review PASS recorded from merged PR #96.",
            "evidence_actor_identity": "github:zyyyyynnn",
            "review_evidence_state": "COMMENTED",
            "review_evidence_body": TECHNICAL_BODY,
            "review_evidence_url": "https://github.com/zyyyyynnn/xingwen-astro-ai/pull/96#pullrequestreview-4742006762",
        },
        {
            "review_id": "review.pr_96_scientific_pass",
            "review_sequence": 1,
            "supersedes_review_id": None,
            "reviewed_at": "2026-07-21T14:50:40+08:00",
            "reviewer_type": "web_gpt",
            "reviewer_identity": "openai:web-gpt",
            "reviewer_role": "scientific_benchmark_reviewer",
            "review_purpose": "benchmark_scientific_review",
            "verdict": "pass",
            "reviewed_head_sha": REVIEWED_HEAD,
            "reviewed_benchmark_version": VERSION,
            "reviewed_content_hash": SCIENTIFIC_HASH,
            "scope": full_scientific_scope(payload),
            "blocking_findings": [],
            "non_blocking_findings": [
                "Approval is limited to the declared public abstract and bibliographic evidence boundaries.",
                "Clark remains limited to the stated GALAH DR2, TIC, and Gaia DR2 cross-matched sample.",
            ],
            "notes": "Web GPT scientific benchmark review PASS recorded from merged PR #96.",
            "evidence_actor_identity": "github:zyyyyynnn",
            "review_evidence_state": "COMMENTED",
            "review_evidence_body": SCIENTIFIC_BODY,
            "review_evidence_url": "https://github.com/zyyyyynnn/xingwen-astro-ai/pull/96#pullrequestreview-4742008435",
        },
    ]

    final_change = next(
        item for item in reversed(payload["change_records"]) if item["version"] == VERSION
    )
    approval_note = (
        " Record the final PR #96 web GPT technical and scientific PASS evidence and "
        "promote the package review metadata to approved without changing scientific content."
    )
    if approval_note.strip() not in final_change["summary"]:
        final_change["summary"] += approval_note

    actual_scientific_hash = compute_benchmark_scientific_payload_hash(payload)
    if actual_scientific_hash != SCIENTIFIC_HASH:
        raise RuntimeError(
            f"approval metadata changed scientific hash: {actual_scientific_hash}"
        )
    payload["scientific_payload_hash"] = SCIENTIFIC_HASH
    payload["content_hash"] = compute_benchmark_content_hash(payload)
    BenchmarkPackage.model_validate(payload)
    BENCHMARK_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    content_hash = payload["content_hash"]

    changelog = CHANGELOG_PATH.read_text(encoding="utf-8")
    changelog = changelog.replace(
        "- Package 保持 `pending_scientific_review`，`relation_scientific_accuracy` 保持 `not_available`，未伪造 PASS。",
        "- PR #96 的真实 `pr_technical_review PASS` 与 `benchmark_scientific_review PASS` 已写入 ReviewRecord；Package 与全部可审核对象提升为 `approved`。",
        1,
    )
    changelog = re.sub(
        r"- 本版本影响 content hash；scientific payload hash 为 `sha256:32db9d4345d904f3f5b9fbe975c41cdfebd4fb45ecc5747e6845959bd220e9cd`，完整 Package hash 为 `sha256:[0-9a-f]{64}`。",
        f"- 批准元数据不改变 scientific payload hash；当前值仍为 `sha256:32db9d4345d904f3f5b9fbe975c41cdfebd4fb45ecc5747e6845959bd220e9cd`，批准后的完整 Package hash 为 `{content_hash}`。",
        changelog,
        count=1,
    )
    CHANGELOG_PATH.write_text(changelog, encoding="utf-8")

    readme = README_PATH.read_text(encoding="utf-8")
    readme, count = re.subn(
        r"当前 `1\.3\.0` Package 的 `review_status` 为 `pending_scientific_review`。[^\n]+",
        "当前 `1.3.0` Package 的 `review_status` 为 `approved`。PR #96 的网页端 GPT 技术与科研 PASS 已绑定最终 reviewed HEAD、`benchmark_version=1.3.0` 与当前 `scientific_payload_hash`，并以完整对象 scope 写入 `review_records`；所有带审核状态的 Summary、Evidence、Claim、Relation 和 Trace 均已批准。",
        readme,
        count=1,
    )
    if count != 1:
        raise RuntimeError("could not update README review status")
    readme = re.sub(
        r"当前值为 `sha256:32db9d4345d904f3f5b9fbe975c41cdfebd4fb45ecc5747e6845959bd220e9cd`；完整 Package hash 为 `sha256:[0-9a-f]{64}`。",
        f"当前值为 `sha256:32db9d4345d904f3f5b9fbe975c41cdfebd4fb45ecc5747e6845959bd220e9cd`；批准后的完整 Package hash 为 `{content_hash}`。",
        readme,
        count=1,
    )
    README_PATH.write_text(readme, encoding="utf-8")

    tests = TEST_PATH.read_text(encoding="utf-8")
    tests = tests.replace(
        "assert package.review_status is BenchmarkReviewStatus.pending_scientific_review",
        "assert package.review_status is BenchmarkReviewStatus.approved",
        1,
    )
    tests = tests.replace(
        """def test_review_records_have_stable_identity_and_machine_readable_scope() -> None:
    package = load_benchmark_package(BENCHMARK_PATH)

    assert package.review_records == ()""",
        """def test_review_records_have_stable_identity_and_machine_readable_scope() -> None:
    package = load_benchmark_package(BENCHMARK_PATH)

    assert {record.review_purpose.value for record in package.review_records} == {
        \"pr_technical_review\",
        \"benchmark_scientific_review\",
    }
    assert all(record.verdict.value == \"pass\" for record in package.review_records)
    assert all(record.reviewed_head_sha == \"1a541bb84d9d022bca3da137f4ec41bf60b6aab8\" for record in package.review_records)""",
        1,
    )
    tests = tests.replace(
        """    approved_objects = deepcopy(payload)
    for collection_name in (
        \"paper_summaries\",
        \"evidence\",
        \"claims\",
        \"relations\",
        \"reasoning_traces\",
    ):
        for item in approved_objects[collection_name]:
            item[\"review_status\"] = \"approved\"

    assert (
        compute_benchmark_scientific_payload_hash(approved_objects)
        == expected_scientific_hash
    )
    assert compute_benchmark_content_hash(approved_objects) != expected_content_hash""",
        """    pending_objects = deepcopy(payload)
    for collection_name in (
        \"paper_summaries\",
        \"evidence\",
        \"claims\",
        \"relations\",
        \"reasoning_traces\",
    ):
        for item in pending_objects[collection_name]:
            item[\"review_status\"] = \"pending_scientific_review\"

    assert (
        compute_benchmark_scientific_payload_hash(pending_objects)
        == expected_scientific_hash
    )
    assert compute_benchmark_content_hash(pending_objects) != expected_content_hash""",
        1,
    )
    tests = re.sub(
        r"(def test_pending_benchmark_does_not_report_relation_accuracy\(\) -> None:\n)    package = load_benchmark_package\(BENCHMARK_PATH\)",
        r"\1    package = _review_fixture(\n        package_status=BenchmarkReviewStatus.pending_scientific_review,\n        approved_relation_count=0,\n    )",
        tests,
        count=1,
    )
    tests = re.sub(
        r"(def test_metrics_report_not_available_for_empty_denominators\(\) -> None:\n)    package = load_benchmark_package\(BENCHMARK_PATH\)",
        r"\1    package = _review_fixture(\n        package_status=BenchmarkReviewStatus.pending_scientific_review,\n        approved_relation_count=0,\n    )",
        tests,
        count=1,
    )
    anchor = "\n\ndef test_benchmark_review_labels_name_web_gpt_scientific_review() -> None:"
    published_test = """


def test_published_package_records_real_web_gpt_approval() -> None:
    package = load_benchmark_package(BENCHMARK_PATH)
    approved_relations = sum(
        relation.review_status is BenchmarkReviewStatus.approved
        for relation in package.relations
    )

    assert package.review_status is BenchmarkReviewStatus.approved
    assert approved_relations == len(package.relations)
    results = evaluate_benchmark(
        package,
        _evaluation_input(
            scientifically_reviewed_relations_correct=approved_relations,
            scientifically_reviewed_relations_total=approved_relations,
        ),
    )
    relation_accuracy = next(
        result
        for result in results
        if result.metric_id is BenchmarkMetricId.relation_scientific_accuracy
    )
    assert relation_accuracy.denominator == approved_relations
    assert relation_accuracy.value == 1.0
"""
    if "def test_published_package_records_real_web_gpt_approval" not in tests:
        tests = tests.replace(anchor, published_test + anchor, 1)
    TEST_PATH.write_text(tests, encoding="utf-8")

    print(f"D-01 package approved; content_hash={content_hash}")


if __name__ == "__main__":
    main()
