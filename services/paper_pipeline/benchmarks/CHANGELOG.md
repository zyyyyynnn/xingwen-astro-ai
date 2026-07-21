# Paper and Reasoning Benchmark Changelog

## exoplanet_host_star 1.1.0 — 2026-07-21

- 冻结 `source_claim_id relation_type target_claim_id` 方向语义，修正 4 条 Relation、3 条 ReasoningTrace 和 2 条跨文献 GraphEdge 的方向，并为 rejected Relation 增加不可比性 Trace。
- 增加人类/自动化 reviewer 类型、稳定 identity、结构化审核对象范围和完整 Package 人工批准门。
- review-approved Relation 现在要求两端 Claim、绑定 ReasoningTrace 和相关 Evidence 均已批准。
- 将 Crossref 单记录与列表/搜索的 public/polite 限流边界机器化，并记录每秒单位、并发、核验日期和官方来源。
- 于 2026-07-21 复核全部 verification source；将失效的 Clark NTRS URL 与不稳定的 DOI 跳转核验路径替换为 Crossref 单记录 API。
- 本版本保持 `pending_human_review`，`relation_human_accuracy` 仍为 `not_available`，不冒充人工 gold package。
- 本版本影响 content hash；发布 hash 为 `sha256:0fb405c27f88e4657cf609de5d4e0b5880ebf6ccf20deebd8beda04fa84d7f20`。

## exoplanet_host_star 1.0.0 — 2026-07-19

- 新增 3 个检索来源政策、2 个官方核验记录来源政策和 2 个固定检索场景。
- 新增 6 篇经 DOI、arXiv 或官方机构记录核验的 seed papers。
- 新增基于公开摘要的 PaperSummary、8 条 Claim、4 条 Relation、3 条 ReasoningTrace 和最小 Graph。
- 新增 candidate、accepted、rejected Relation 样例，以及无 Evidence、不可比关系和 Graph 悬空引用的自动拦截测试。
- 新增 5 项评测指标的分子、分母和空集合行为。
- 本版本影响 content hash；发布 hash 为 `sha256:10d04344f08b767dda1dbfd84ba229c2114cdc14d7e2f21e4bbcf085e64dd28e`。
- 评审状态为 `pending_human_review`；尚未作为人工批准的科研 gold label。
