# Paper and Reasoning Benchmark Changelog

## exoplanet_host_star 1.3.0 — 2026-07-21

- `scientific_payload_hash` 递归规范化 Package 与全部对象级 `review_status`；仅批准状态变化不再改变 scientific hash，完整 Package hash 仍会变化。
- 技术 Review 新增 `pull_request` target；`pr_technical_review PASS` 必须精确且仅绑定完整 `zyyyyynnn/xingwen-astro-ai#number`，其他仓库或单对象 scope 不能通过 PR Gate。
- Review evidence 强制 `APPROVED => PASS`、`CHANGES_REQUESTED => BLOCKED`；`COMMENTED` 正文必须含匹配的独立 verdict 行。
- seed intended use 与 Trace provenance 改为 `scientific_review` / `web_gpt_benchmark_draft`，不再把网页端 GPT 科研审查标为人工 Review。
- Clark→revised TIC lineage 因摘要未固定 TIC 版本降为 candidate 并撤出 Graph；宿主星物理参数→TOI 候选体计数的 `limits` 关系改为 rejected negative example；Clark limitation 收紧到公开摘要支持的交叉匹配样本范围。
- PR #96 的真实 `pr_technical_review PASS` 与 `benchmark_scientific_review PASS` 已写入 ReviewRecord；Package 与全部可审核对象提升为 `approved`。
- 批准元数据不改变 scientific payload hash；当前值仍为 `sha256:32db9d4345d904f3f5b9fbe975c41cdfebd4fb45ecc5747e6845959bd220e9cd`，批准后的完整 Package hash 为 `sha256:07fa19820cdbd5b908d4f30705bb863fb9a28050caf7bf54f6c01130467b1e2d`。

## exoplanet_host_star 1.2.0 — 2026-07-21

- reviewer type 统一为 `web_gpt | automation`，新增 `pr_technical_review | benchmark_scientific_review` purpose 和 `pass | blocked` verdict；automation 不能产生正式 PASS。
- ReviewRecord 绑定带时区时间、40 位 reviewed HEAD、Benchmark version、scientific payload hash、本仓库 GitHub Review URL、结构化 findings 与 scope。
- 新增 `review_sequence` / `supersedes_review_id` 单链规则；拒绝缺失父记录、分叉、循环、跨 purpose/scope 覆盖，并以最新叶节点决定有效 verdict。
- 新增独立 `scientific_payload_hash`，排除 Review/Change/批准状态但覆盖科研内容，避免批准记录与 hash 循环引用；PR 技术门继续以外部当前 HEAD 校验。
- 审核状态统一为 `pending_scientific_review | approved | changes_requested`，指标改为 `relation_scientific_accuracy`；当前 Package 保持 Pending，不伪造网页端 GPT PASS。
- Crossref 限流信息拆分为 `documented_policy` 与 `observed_runtime_limits`；保存三份官方声明及冲突、两次 public 响应头快照，并冻结响应头优先、429 backoff、缺失头保守策略。
- 本版本影响 content hash；scientific payload hash 为 `sha256:b979a27c0467061f254dec2343a7c205d8e38d861a5530c4249f3cd6d9455f83`，完整 Package hash 为 `sha256:d3b70722a3c30e4f993e093f3900e5c65e13696e8df7c3c3fd98cfe8d0fb810a`。

## exoplanet_host_star 1.1.0 — 2026-07-21

- 冻结 `source_claim_id relation_type target_claim_id` 方向语义，修正 4 条 Relation、3 条 ReasoningTrace 和 2 条跨文献 GraphEdge 的方向，并为 rejected Relation 增加不可比性 Trace。
- 增加早期 reviewer 类型、稳定 identity、结构化审核对象范围和 Package 批准门；该模型已由 1.2.0 的 web GPT purpose/verdict 契约取代。
- review-approved Relation 现在要求两端 Claim、绑定 ReasoningTrace 和相关 Evidence 均已批准。
- 将 Crossref 单记录与列表/搜索的 public/polite 限流边界机器化，并记录每秒单位、并发、核验日期和官方来源。
- 于 2026-07-21 复核全部 verification source；将失效的 Clark NTRS URL 与不稳定的 DOI 跳转核验路径替换为 Crossref 单记录 API。
- 本版本保持待科研审核状态，关系正确率仍为 `not_available`，不冒充已批准科研 Benchmark。
- 本版本影响 content hash；发布 hash 为 `sha256:0fb405c27f88e4657cf609de5d4e0b5880ebf6ccf20deebd8beda04fa84d7f20`。

## exoplanet_host_star 1.0.0 — 2026-07-19

- 新增 3 个检索来源政策、2 个官方核验记录来源政策和 2 个固定检索场景。
- 新增 6 篇经 DOI、arXiv 或官方机构记录核验的 seed papers。
- 新增基于公开摘要的 PaperSummary、8 条 Claim、4 条 Relation、3 条 ReasoningTrace 和最小 Graph。
- 新增 candidate、accepted、rejected Relation 样例，以及无 Evidence、不可比关系和 Graph 悬空引用的自动拦截测试。
- 新增 5 项评测指标的分子、分母和空集合行为。
- 本版本影响 content hash；发布 hash 为 `sha256:10d04344f08b767dda1dbfd84ba229c2114cdc14d7e2f21e4bbcf085e64dd28e`。
- 评审状态为待科研审核；尚未作为已批准的科研 Benchmark label。
