# Phase 0 API Contract（归档）

| Metadata | Value |
| --- | --- |
| Status | Archived |
| Authority | Phase 0 DTO 冻结决策与偏差记录（历史） |
| Superseded by | [Data Model](../../architecture/DATA_MODEL.md)、[API Contract](../../architecture/API_CONTRACT.md) |
| Authoring source | `apps/api/src/app/schemas` |
| Time range | Phase 0 基线（Issue #26）至无版本化单面 API 收口（ADR-030） |

本文归档 Phase 0 传输契约的冻结决策与偏差记录。精确字段事实不在本文维护，以下来源为准：

- Pydantic authoring source：`apps/api/src/app/schemas/`；
- 生成 Schema：`packages/schemas/generated/phase0/`；
- 契约执法测试：`apps/api/tests/test_pipeline_contract.py`。

## 冻结决策

- Phase 0 契约由 Issue #26 冻结，供 Pipeline 基线接口继续使用；目标模型由 [Data Model](../../architecture/DATA_MODEL.md) 定义，不得隐式修改冻结 DTO。
- 有意偏差必须记录在本文并由契约测试覆盖。
- 全部时间戳为带时区 ISO 8601；除显式 optional 或默认值外字段必填。

## 传输命名决策

- 领域 `id` 在 Phase 0 线上负载中保留 legacy wire alias：`dataset_id`、`query_id`、`run_id`、`candidate_id`、`paper_id`、`claim_id`、`relation_id`、`trace_id`。
- 历史实体到传输类的重命名：FieldDefinition → `ColumnInfo`、SourceRecord → `SourceRecordItem`、Paper → `PaperItem`、Evidence → `EvidenceResponse`（保留 import 兼容）。

## 有意偏差记录

1. `PaperItem` 不携带 `doi` 与 `arxiv_id`；二者由 `PaperCandidate` 表达。这是与历史实体示例的有意传输差异。
2. Phase 0 Evidence 响应内嵌的 `SourceSnapshot` 只含 `retrieved_at` 与 `query_hash`，为兼容而冻结；目标模型的完整 SourceSnapshot 属于核心 API，不得静默回灌到 Phase 0 线上响应。
3. Evidence 的 `source_id`、`paper_id`、`content`、`locator`、`quote_or_value` 可空，因为数据库、论文、模型、反馈与缓存证据不共享同一 locator；`target_*`、抽取元数据、快照、置信度与时间保持必填以保证可审计。

## 证据不变量（Phase 0）

- PaperSummary、LiteratureClaim、LiteratureRelation、ReasoningTrace 至少绑定一个 Evidence id。
- LiteratureRelation 必须携带 ReasoningTrace id。
- Fixture 数据必须标识为 Fixture，不得表述为真实或缓存的科研结果。
