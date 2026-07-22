# Data Model

| 项目状态 | 口径 |
| --- | --- |
| Status | Accepted |
| Authority | 领域实体、字段、枚举与不变量 |
| Implementation | Core Pydantic contract、Workspace/Share application projection、D-02 content、#76/#77 Workflow persistence、#78 atomic publisher 与 #83 Artifact provenance read persistence Implemented；Workspace/Share runtime integration Pending |
| Current model | `/api/v1` 的 ResearchTask 与结果 DTO（冻结字段见 [DATA_MODEL_V1.md](DATA_MODEL_V1.md) 与 [V1_SCHEMA_FIELD_MATRIX.md](V1_SCHEMA_FIELD_MATRIX.md)） |
| Target model | Project / Run / Artifact / ArtifactVersion |

本文冻结 `/api/v2` 与前端 Domain Model 的目标实体和不变量。七个核心资源的 Pydantic Schema、Session 安全边界、Workspace/Share application projection、#76 Workflow PostgreSQL Schema、#77 Run lease/recovery、#78 ArtifactVersion Publisher 及 #83 Artifact/Evidence/SourceSnapshot 私有读取已实现；Workspace/Share 生产事实源接入与其余 v2 Application API 仍未实现。字段使用 snake_case；时间统一为带时区 UTC ISO 8601。

## 1. 建模原则

- Project 是持续研究上下文，Run 是一次契约驱动执行。
- Artifact 是稳定身份，ArtifactVersion 是不可变内容快照。
- Evidence 绑定明确 ArtifactVersion，不绑定漂移的 latest。
- `execution_mode` 与 `source_mode` 正交；Fixture 不能冒充 Cached。
- 重试、修订、派生创建新 Run；自动瞬态重试只增加 StepAttempt。
- WorkspaceSnapshot 是私有 UI 恢复状态，ShareSnapshot 是冻结的只读公开投影。
- ReasoningTrace 只记录可审查依据、条件和引用，不保存模型私有 chain-of-thought。

## 2. 实体关系

```mermaid
erDiagram
  RESEARCH_SESSION ||--o{ RESEARCH_PROJECT : owns
  RESEARCH_PROJECT ||--o{ RESEARCH_CONTRACT : defines
  RESEARCH_PROJECT ||--o{ RESEARCH_RUN : contains
  RESEARCH_CONTRACT ||--o{ RESEARCH_RUN : drives
  RESEARCH_RUN ||--o{ RUN_STEP : executes
  RUN_STEP ||--o{ STEP_ATTEMPT : records
  RESEARCH_RUN ||--o{ RUN_EVENT : emits
  RESEARCH_PROJECT ||--o{ RESEARCH_ARTIFACT : owns
  RESEARCH_ARTIFACT ||--o{ ARTIFACT_VERSION : versions
  RESEARCH_RUN ||--o{ ARTIFACT_VERSION : produces
  ARTIFACT_VERSION ||--o{ EVIDENCE : supports
  SOURCE_SNAPSHOT ||--o{ EVIDENCE : locates
  RESEARCH_PROJECT ||--o| WORKSPACE_SNAPSHOT : restores
  RESEARCH_PROJECT ||--o{ SHARE_SNAPSHOT : publishes
  SHARE_SNAPSHOT }o--o{ ARTIFACT_VERSION : freezes
  USER_FEEDBACK }o--|| ARTIFACT_VERSION : targets
```

## 3. 通用类型与枚举

- 对外 ID 使用不可枚举的 UUIDv7、ULID 或等价高熵标识；数据库内部实现不暴露。
- `schema_version` 使用语义版本字符串。
- `content_hash` 使用 `sha256:<hex>`，只识别内容，不替代业务 ID。
- 所有资源至少包含 `created_at`；可变元数据包含 `updated_at` 和乐观锁 `revision`。

```text
execution_mode = demo_replay | live
source_mode = fixture | live | cached
derivation_kind = original | retry | revision | fork
```

不变量：`execution_mode` 只属于 ResearchRun 及创建 Run 的请求，不属于 ResearchContract 或 ResearchContractDraft。Fixture Adapter 产生 `demo_replay + fixture`；HTTP Live Run 产生 `execution_mode=live`，其产物可为 `live` 或 `cached`。Cached 必须引用真实历史 Run。修订不是来源模式：当 `derivation_kind=revision` 或 `supersedes_version_id` 非空时，产物处于修订派生关系，仍保留实际 `source_mode`。

## 4. ResearchSession

免登录访问者的服务端隔离边界。

```text
id
status: active | expired | revoked
created_at
expires_at
last_seen_at
quota_profile
project_count
run_count
```

Session id 不进入公开 URL、日志或导出。Cookie、CSRF token 和原始 share token 不属于领域 DTO。

## 5. ResearchProject

```text
id
session_id
name
description
case_key
active_contract_id
latest_run_id
created_at
updated_at
revision
```

Project 表示持续研究问题，不保存聊天消息流。一个 Project 可有多个 Contract、并行 Run、Artifact 和 ShareSnapshot。

## 6. ResearchContract

确认后的科研输入契约；Run 创建后引用不可变版本。

```text
id
project_id
version
research_goal
target_objects[]
data_requirements
requested_fields[]
source_scope
paper_search_scope
output_requirements[]
evidence_requirements
quality_constraints
created_from_draft_id
created_at
content_hash
```

| 字段 | 最低约束 |
| --- | --- |
| `research_goal` | 4–500 字符，不能只含空白 |
| `target_objects` | 至少一个受当前 case 支持的对象类型 |
| `requested_fields` | 至少一个字段，由 case manifest 校验 |
| `source_scope` | provider-level 允许来源、合规和缓存策略；table 映射由 Field Manifest 解析 |
| `paper_search_scope` | 关键词、年份、来源、候选上限和选择规则 |
| `evidence_requirements` | locator、snapshot、引用和最低覆盖要求 |
| `quality_constraints` | 来源完整性、单位一致性等可验证阈值 |

ResearchContractDraft 是短期可编辑资源，包含 `id`、`session_id`、`version`、`intent`、`contract`、`warnings`、`expires_at`；确认时复制为不可变 Contract。

C-01 Manifest 来源边界：

- Case Manifest 的 `allowed_source_ids` 与 API `source_scope.allowed_sources` 使用 provider source id，例如 `nasa_exoplanet_archive`。
- Field Manifest 的 `SourceDefinition.provider_source_id` 绑定 provider；table source id 必须等于 `{provider_source_id}.{source_table}`，例如 `nasa_exoplanet_archive.ps`。
- provider scope 到 table source id 的解析只能从现有 `SourceDefinition` 派生，不维护第二套来源定义。
- `SourceAlias` 仍引用 table source id；其 raw、误差、limit、row key、reference 和 provenance 列必须属于该表的 evidence-backed allowlist，并满足对应角色约束。
- Case 与 Field Manifest 的审计字段统一为 `created_at`、`maintained_by`；`maintained_at`、`maintainer` 非法。

## 7. ResearchRun、Step 与 Event

ResearchRun：

```text
id
project_id
contract_id
execution_mode
status: RunStatus（定义见 `WORKFLOW_DESIGN.md`）
progress
parent_run_id
derivation_kind
retry_from_step
cache_policy
started_at
finished_at
created_at
updated_at
latest_event_sequence
failure_code
failure_summary
```

Run 状态集合、转换、重试和取消规则只在 [WORKFLOW_DESIGN.md](WORKFLOW_DESIGN.md) 定义。`cached`、`fixture`、修订关系和 `using_cache` 都不是 Run 状态。

持久化层额外保存 `revision`、不可公开的 `lease_token`、内部 `lease_owner`、`lease_generation`、`lease_expires_at` 和 `steps_frozen_at`。有效 lease 的 token、owner、expires_at 必须同时存在；接管时 generation 单调递增。任何 Executor 写入都同时校验 status、revision、token、generation 与数据库时间；这些并发控制字段不进入 `/api/v2` Transport Contract。

RunStep：

```text
id
run_id
position
key
label
enter_status
success_status
max_attempts
status: pending | running | waiting | completed | failed | cancelled | skipped
progress
started_at
finished_at
input_hash
output_artifact_version_ids[]
failure_code
public_message
```

`output_artifact_version_ids` 是读取投影，不作为 `RunStep` 数据库数组事实保存；持久化层通过 `ArtifactVersion.run_step_id` 与 `step_attempt_id` 反向定位输出。

Run 创建事务验证完整规范状态链，并在插入全部 Step 后设置 `steps_frozen_at`；PostgreSQL 触发器阻止后续插入、删除、重排或修改执行定义。StepAttempt 记录 `attempt_number`、幂等键、状态、时间、error class/code、retryable 和 upstream request id；重试不得覆盖前一次失败。

RunEvent 包含 `run_id`、单调递增 `sequence`、event_type、step_key、progress、public_message、artifact_version_ids 和 occurred_at。Event 用于增量通知，不作为当前状态事实来源，也不包含 chain-of-thought。

## 8. ResearchArtifact 与 ArtifactVersion

ResearchArtifact：

```text
id
project_id
kind
title
logical_key
created_at
latest_version_id
```

`kind`：`dataset`、`field_dictionary`、`source_collection`、`paper_collection`、`paper_summary`、`literature_claims`、`literature_relations`、`reasoning_traces`、`graph`、`export`。

ArtifactVersion：

```text
id
artifact_id
project_id
created_by_run_id
version_number
schema_version
content
content_hash
input_hash
source_mode
producer
source_snapshot_ids[]
evidence_ids[]
supersedes_version_id
created_at
```

#76 持久化基线额外保存 `run_step_id`、`step_attempt_id` 与 `producer_execution_id` 外键，用于从不可变版本反向定位实际 Step、Attempt 和 ProducerExecution；#78 Publisher 使用 `publication_key` 保证同一 Artifact 内的发布幂等。这些字段不改变公开 ArtifactVersion 的领域身份。

组合外键强制 Contract、Run、Artifact、Step、Attempt、ProducerExecution 与 ArtifactVersion 留在同一 Project / Run / Artifact 聚合内；`latest_version_id` 与 `supersedes_version_id` 不能跨 Artifact 引用。

不变量：

- `(artifact_id, version_number)` 唯一，content 创建后不可原地修改。
- `(artifact_id, publication_key)` 唯一；同 key 同内容和 producer 条件返回既有 Version，不同条件稳定冲突。
- Evidence、ShareSnapshot 与 Export 固定引用 version id，不引用 latest。
- Cached 还需 CacheRecord 与 origin Run；修订版本还需 supersedes version 和 Feedback，并保留自身实际来源模式。
- `producer` 包含 type、name、version，以及适用的 model、prompt、parameters hash；不包含密钥或私有推理。

## 9. 科研 Artifact 内容

### 9.1 Dataset 与 FieldDefinition

Dataset 包含 name、columns、rows 或 page_reference、row_count、quality_score、source_snapshot_ids。大型数据集保存 manifest 与分页引用，不强制嵌入全部 rows。

FieldDefinition 包含 name、label、description、data_type、canonical_unit、source_field、source_snapshot_ids、transformation_rule、missing_rate、evidence_ids。

### 9.2 PaperCollection 与 PaperSummary

PaperCollection 包含 query、acquisition_run、candidates、selected_paper_ids、dedupe_rule、ranking_rule、source_snapshot_ids。Candidate 至少包含 title、authors、year、DOI/arXiv/URL、source snapshot、relevance、selected 和 selection_reason。Seed 只能标记 benchmark、scientific_review 或 fixture。

当前 D-02 已在唯一 Pydantic 编写源实现独立的 PaperCollection Pipeline content、完整 SourceSnapshot 和 ProducerExecution 元信息；Query、candidate、duplicate group、conflict、ranking、selection/exclusion、指标与 hash 的运行规则见 [PaperCollection Pipeline](../engineering/PAPER_COLLECTION_PIPELINE.md)。#78 已实现通用 Publisher 端口，但这不表示 `/api/v2` HTTP API 或 Paper Pipeline 到持久化 Workflow 的生产集成已实现。

PaperSummary 包含 paper_id、research_goal、method、dataset、findings、limitations、future_work、evidence_ids；每个核心 finding / limitation 可定位 Evidence。

### 9.3 Claim、Relation 与 ReasoningTrace

LiteratureClaim：paper_id、claim_type、text、conditions、evidence_ids、confidence、`candidate | accepted | rejected`。

LiteratureRelation：source/target claim、relation_type、conditions、reasoning_trace_id、evidence_ids、confidence、状态。方向统一为 `source_claim_id relation_type target_claim_id`；source 是关系主语，target 是关系宾语。Accepted Relation 必须同时有 Evidence 和 ReasoningTrace。

ReasoningTrace：relation_id、premise_claim_ids、显式 steps、conditions、evidence_ids、review_status。`premise_claim_ids` 按 Relation 的 source、target 顺序保存。Step 只描述引用、比较条件和结构化结论，不记录隐藏 prompt、内部 token 或逐 token 推理。

### 9.4 Graph

Graph 包含 nodes、edges、layout_hint 和 filters。每条 GraphEdge 必须有 evidence_ids；跨文献边还必须有 relation_id 和 reasoning_trace_id。不得为装饰生成无科研意义的边。

### 9.5 Benchmark 审核与来源政策

Benchmark ReviewRecord 的 reviewer type 仅为 `web_gpt | automation`，purpose 为 `pr_technical_review | benchmark_scientific_review`，并包含稳定 identity、role、结构化对象范围、带时区日期、`pass | blocked`、40 位 reviewed HEAD、reviewed benchmark version、reviewed scientific payload hash、GitHub Review URL、GitHub evidence actor/state/body、阻塞/非阻塞项和备注。automation 不能产生正式 PASS；web GPT 证据必须定位本仓库 GitHub Pull Request Review，并由 GitHub API 核对 repository/PR、actor、state、commit id 和正文。`APPROVED` 只对应 `pass`，`CHANGES_REQUESTED` 只对应 `blocked`；`COMMENTED` 正文必须含匹配的独立 verdict 行。

多轮 Review 使用 `review_sequence` 和 `supersedes_review_id` 形成单链：同 purpose/scope 才能 supersede，不允许缺失父记录、分叉、循环或复用旧 GitHub Review URL；每条链最新叶节点是有效结论，未解决的 `blocked` scope 阻止批准。`pr_technical_review PASS` 的 scope 必须精确且仅为当前 `pull_request: zyyyyynnn/xingwen-astro-ai#number`，并通过独立的最终 HEAD Gate 校验；其他仓库或单对象 scope 不能批准整个 PR。技术 Review 不能批准科研 Benchmark，`benchmark_scientific_review` 也不能替代 PR 技术 Review。

Benchmark 的 PaperSummary、Evidence、Claim、Relation 和 ReasoningTrace 分别保存 `pending_scientific_review | approved | changes_requested`。Package 批准时，当前 version 与 `scientific_payload_hash` 的 web GPT scientific PASS 范围覆盖全部 SourcePolicy、SeedPaper、PaperSummary、Evidence、Claim、Relation、ReasoningTrace 和 GraphEdge；review-approved Relation 的两端 Claim、ReasoningTrace 与相关 Evidence 同时为 approved。

Crossref SourcePolicy 分离 `documented_policy` 与 `observed_runtime_limits`：前者版本化保存官方页面声明、适用说明和已知冲突，后者保存显式请求的 endpoint、request class、时间、响应状态与实际 `x-api-pool`、rate-limit、interval、concurrency 响应头。缺失头显式记为 `unavailable`；运行时 Adapter 必须优先服从当前响应头、处理 429/backoff，并在缺失头时使用保守策略。D-01 只保存快照，不实现 Adapter。

## 10. Evidence 与 SourceSnapshot

Evidence：

```text
id
artifact_version_id
target_type
target_id
evidence_type
source_snapshot_id
paper_id
locator
quote_or_value
extraction_method
confidence
created_at
```

Locator 使用判别联合：database cell 定位 query hash、row key 和 field；paper text 定位 section/page/paragraph/range；model extraction 引用输入 evidence 与 prompt/model version；reasoning trace 引用 relation 和显式 step。

SourceSnapshot：

```text
id
source_id
source_type
retrieved_at
query
query_hash
source_version_or_etag
content_hash
license_note
cache_version
request_metadata
```

持久化层为 Evidence 和 SourceSnapshot 额外保存内部 `project_id` 组合外键，用于强制 Version、Evidence 与 Snapshot 留在同一 Project；Evidence 的内部 `is_restricted` 标记只控制私有读取脱敏，不进入 Transport DTO。`request_metadata` 只保存可复现且非敏感字段；认证头、Cookie、API Key 和完整受限响应不得保存。B-18 读取层还执行防御性 allowlist/redaction，历史或损坏记录中的敏感字段不会序列化。

## 11. Feedback 与 RevisionPlan

UserFeedback 包含 project/run、target_type、target_id、artifact_version_id、category、message、proposed_change、status 和 created_at。目标覆盖 Field、Source、Paper、PaperSummary、Claim、Relation、ReasoningTrace、GraphEdge。

RevisionPlan 包含 feedback_ids、affected_artifact_version_ids、affected_steps、reuse_artifact_version_ids、conflicts 和 status。确认后创建 `derivation_kind=revision` 的新 Run，原版本保持可读。

## 12. WorkspaceSnapshot 与 ShareSnapshot

WorkspaceSnapshot 内部绑定 session/project，传输 DTO 不序列化 session id；它保存 active_run_id、最多三个具有唯一 slot_id 的 panel_slots、selected_object_ref、pinned_evidence_ids、结构化 Atlas/Observatory 状态、layout_preset、revision 和 updated_at。不保存 token、任意自由文本、未提交敏感输入、GPU 状态或模型内部状态。相同 payload 重放保持 revision，不同 payload 以 revision 乐观锁覆盖。

ShareSnapshot：

```text
id
project_id
created_by_session_id
title
artifact_version_ids[]
evidence_ids[]
redaction_policy
token_hash
status: active | expired | revoked
created_at
expires_at
revoked_at
```

原始 token 只在创建响应中出现一次。ShareSnapshot 不引用动态 latest，不授予反馈、再生成或私有 Project 读取权限。

当前 `public_metadata_only` 投影冻结 ArtifactVersion 的 id、kind、title、version/schema/content hash、source mode 和 created_at，以及 Evidence 到明确 Version/SourceSnapshot 的最小身份引用；不公开 Artifact content、Evidence locator、Session/Project、producer 私有元数据或原始 token。运行适配器只保存 token 的 SHA-256 hash。

## 13. CacheRecord 与 ProducerExecution

CacheRecord 至少包含 origin_run_id、artifact_version_id、source_snapshot_ids、input_hash、contract_hash、producer_version、created_at 和 validity_scope。缓存不得只是无来源 JSON。

ProducerExecution 记录 run、step、attempt、lease generation、producer/model、prompt version/hash、安全标量 parameters 及其 hash、input/output hash、状态、时间、token usage、latency 和 error code；成功、失败、rejected 与 cancelled 终态均保留。参数键和值经过长度、类型和敏感名称校验，不保存密钥、认证头、受限全文、原始模型长输出或私有 chain-of-thought。

## 14. 一致性边界

- Project 聚合只内嵌 Run / Artifact 摘要，不内嵌完整大产物。
- Run Snapshot 是状态事实来源；Event 只做增量通知。
- ArtifactVersion、latest 指针、StepAttempt、RunStep、ResearchRun 与 RunEvent 在同一 fenced 发布事务登记；任一写入失败整体回滚。
- Evidence 创建前验证 target 属于对应 ArtifactVersion。
- Graph 发布前验证所有边 Evidence，跨文献边再验证 Relation / Trace。
- ShareSnapshot 创建时验证版本属于同一 Project，并执行脱敏。
- Revision Run 只复用 content hash 与 Contract 允许的完成版本。

## 15. v1 迁移映射

| 当前 v1 | 目标 v2 |
| --- | --- |
| `ResearchTask` | `ResearchProject` + 一个 `ResearchRun` |
| Task options | `ResearchContract` |
| Task status / steps | `ResearchRun` + RunStep + RunEvent |
| dataset/papers/reasoning/graph 响应 | ResearchArtifact + ArtifactVersion.content |
| `meta.cached` / `used_cache` | ArtifactVersion.source_mode + CacheRecord |
| 同一 Task 的 `revising` | 新 `derivation_kind=revision` Run |

迁移适配只用于过渡；v1 Task DTO 不得成为新 React 组件的 Domain Model。
