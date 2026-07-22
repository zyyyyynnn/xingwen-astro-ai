# Data and Artifact Versioning

| 项目状态 | 口径 |
| --- | --- |
| Status | Accepted |
| Authority | ArtifactVersion、来源、缓存、修订、分享与保留规则 |
| Implementation | Workspace/Share process-local adapter、D-02 content、#76 persistence、#78 atomic publication 与 #83 provenance read persistence Implemented；Workspace/Share integration and cache/revision workflows Pending |
| Current runtime | v1 DTO、Prompt registry 与 Phase 0 版本字段 |
| Target runtime | Project / Run / Artifact / ArtifactVersion 追加式治理 |

本文冻结科研产物、来源、缓存、修订、工作台与分享的目标版本规则。B-18 已为 ArtifactVersion、Evidence 和 SourceSnapshot 提供 PostgreSQL 私有读取与 Project ownership 边界；Workspace/Share 仍仅通过进程内端口适配器实现并发与安全语义，不表示其 PostgreSQL 表或跨实例恢复已经落地。

## 1. 版本边界

| 对象 | 是否不可变 | 用途 |
| --- | --- | --- |
| ResearchContract | 确认后不可变 | 固定一次 Run 的研究输入和质量要求 |
| ResearchRun | 创建后关键输入不可变 | 记录一次执行、失败、取消或派生关系 |
| ResearchArtifact | 身份可更新 | 表示同一逻辑产物，维护 latest 指针 |
| ArtifactVersion | 内容不可变 | Evidence、Cache、Share、Export 的绑定单位 |
| SourceSnapshot | 不可变 | 固定外部来源、查询、时间和许可信息 |
| BenchmarkPackage | 已发布版本不可变 | 使用 benchmark id、version 与 content hash 固定静态评测输入 |
| WorkspaceSnapshot | 可覆盖、乐观锁 | 私有 UI 恢复状态，不是科研产物 |
| ShareSnapshot | 创建后不可变 | 冻结公开版本与脱敏范围 |

BenchmarkPackage 的 `schema_version` 表示机器结构版本，`benchmark_version` 表示论文、Evidence、科研审核标签、Graph、来源政策或指标内容版本。任何内容或语义变化都发布新 version 与 content hash，并追加 change record；实际 Review 完成后才追加 review record，不得由 Codex 伪造。不得在相同 version 下原地改变已发布语义。来源核验日期、稳定 URL、文档政策冲突和运行时响应头快照属于 hash 绑定内容，运行时 SourceSnapshot 仍另行记录实际响应与请求元数据。

Benchmark 同时保存两个 hash：

- `scientific_payload_hash` 排除 `content_hash`、`scientific_payload_hash`、`review_records`、`change_records`，并递归规范化 Package、PaperSummary、Evidence、Claim、Relation 和 ReasoningTrace 的全部 `review_status`；其余版本、来源政策、论文、Summary、Evidence、Claim、Relation、Trace、Graph 和指标仍被覆盖。它允许科研 Review 先绑定稳定科研内容，再追加批准记录和状态，避免 hash 自引用。
- `content_hash` 排除自身但包含 `scientific_payload_hash`、Review 与 Change 元数据，固定完整发布 Package。

Scientific Review 的 `reviewed_benchmark_version` 与 `reviewed_content_hash` 必须分别等于当前 `benchmark_version` 与 `scientific_payload_hash`。PR 技术 Review 属于 GitHub 外部门禁证据，以 PR 当前 HEAD 为比较值，且 PASS scope 必须精确绑定当前 `pull_request: zyyyyynnn/xingwen-astro-ai#number`；不能把必须等于自身 Commit SHA 的记录嵌入同一 Commit。

## 2. ArtifactVersion

最低字段：

```text
id
artifact_id
project_id
created_by_run_id
version_number
schema_version
content_hash
input_hash
source_mode
producer
source_snapshot_ids[]
evidence_ids[]
supersedes_version_id
created_at
```

规则：

- `(artifact_id, version_number)` 唯一。
- 内容不可原地改写，latest 只是可变指针。
- Evidence、ShareSnapshot 和 Export 固定引用 version id。
- 修订创建新版本并形成无环 supersedes chain。
- `source_mode` 仅允许 `fixture | live | cached`；Cached 引用 origin Run / Version。
- 修订由创建它的 revision Run 或非空 `supersedes_version_id` 推导；新版本保留自身实际 `source_mode`，不设置 `revised` 来源值。

## 3. Run 派生与版本发布

```text
original Run -> ArtifactVersion 1
retry Run    -> Version 1（复用）+ 新失败步骤产物
revision Run -> ArtifactVersion 2 supersedes Version 1
fork Run     -> 新 Contract 下的新版本或新 Artifact
```

自动瞬态重试不创建新 Run，只新增 StepAttempt；用户在终态后重试、修订或改变 Contract 必须创建派生 Run。

版本只有在 Schema、Evidence、SourceSnapshot、质量约束和 content hash 验证通过后才发布。取消后完成的外部输出可以保留为诊断记录，但不得自动提升为 latest。

#78 Publisher 只接受通过 Pydantic 结构校验以及调用方 Evidence、Domain、Quality 三道准入门的 opaque candidate。发布事务按 `ResearchRun -> RunStep -> ResearchArtifact（id 排序）` 固定顺序加锁，并原子写入 Version、latest、Attempt、Step、Run 和 Event；任一写入失败全部回滚。`publication_key` 在 Artifact 内唯一，同 key 同内容和 producer 条件重放既有 Version，不同条件返回稳定冲突。

## 4. ProducerExecution

模型或算法执行的可公开复现元信息：

```text
id
run_id
step_key
step_attempt_id
lease_generation
producer_type
producer_name
producer_version
model_provider
model_name
prompt_name
prompt_version
prompt_hash
parameters
parameters_hash
input_hash
output_hash
status
started_at
finished_at
token_usage
latency_ms
error_code
```

`parameters` 只保存经过名称、类型和长度约束的安全标量；敏感键在数据库访问前拒绝。不得保存 API Key、认证头、完整受限全文、原始模型长输出或 chain-of-thought。成功、失败、rejected 与 cancelled 执行均保留。

D-02 当前在 PaperCollection content 内生成 detached ProducerExecution：记录固定 step key、producer/rule version、parameters/input/output hash、状态、时间、latency 和错误码，但不登记 ResearchRun 或数据库记录。#78 已提供持久化 ProducerExecution Store 与 ArtifactVersion Publisher；D-02 到该端口的生产接线仍由后续集成负责。具体稳定 hash 与失败记录见 [PaperCollection Pipeline](../engineering/PAPER_COLLECTION_PIPELINE.md)。

## 5. SourceSnapshot

最低字段：

```text
id
source_id
retrieved_at
query
query_hash
source_version_or_etag
content_hash
cache_version
license_note
request_metadata
```

数据库查询、论文检索、论文元数据和可公开文本使用各自 locator。Snapshot 中的 request metadata 只保留可复现且非敏感字段。

D-02 已为成功 Crossref metadata execution 生成完整不可变 SourceSnapshot；失败请求保存 SourceExecution 的 query/pagination/hash/error，不伪造 Snapshot。Cached PaperCollection 要求 Snapshot 额外绑定真实 `origin_run_id` 与 `origin_artifact_version_id`，但 CacheSelector 与 origin persistence 仍为 Pending。

## 6. Hash 规则

- JSON hash 前使用稳定键顺序、明确数字/日期编码和 UTF-8。
- 文本统一 UTF-8 与 LF 后计算；二进制使用 SHA-256。
- Dataset manifest 包含字段、row count、分页/文件 hash，不依赖显示顺序。
- 模型输入 hash 覆盖 Prompt 版本、模型参数、Contract hash 和输入 Evidence / ArtifactVersion。
- hash 识别内容，不替代 Project、Run、Artifact 或 Version 主键。

## 7. CacheRecord

CacheRecord 至少绑定：

- origin ResearchRun；
- ArtifactVersion；
- SourceSnapshot；
- Contract / input hash；
- producer / prompt version；
- created_at 与 validity_scope。

CacheSelector 只能在 Live 发生可恢复失败后使用匹配的真实历史产物。Fixture、seed、视觉样例和手写 JSON 不能标记为 Cached。

## 8. Feedback 与修订

- Feedback 定位 object id 与 ArtifactVersion。
- RevisionPlan 计算受影响步骤、需复用和需重算版本。
- 人工确认后创建 revision Run 和新 ArtifactVersion。
- 旧版本默认保留并可对照；GraphEdge 修订同步 Relation、ReasoningTrace 与 Evidence 影响闭包。
- 冲突时状态为 conflict，不以后提交静默覆盖先提交。

## 9. Workspace 与 Share

WorkspaceSnapshot 使用 `revision` 做乐观锁，可覆盖同一会话的布局，但不进入科研版本链。

同一 payload 的 PUT 重放返回既有 Snapshot；不同 payload 必须匹配当前 revision，冲突不静默覆盖。当前 adapter 重启后失效，后续持久化 adapter 必须保持相同 revision 语义。

ShareSnapshot 固定：

- ArtifactVersion ids；
- 可公开 Evidence ids；
- redaction policy；
- created_at / expires_at；
- token hash 与撤销状态。

分享不指向 latest，因此后续修订不会改变已提交 URL 的内容。原 token 不进入数据库明文、日志或 Project 聚合响应。

创建时复制允许公开的不可变 Version/Evidence 元数据形成冻结投影；之后即使目录中的 latest 或显示元数据变化，既有分享响应也不漂移。当前 M1 redaction policy 仅为 `public_metadata_only`。

## 10. 删除与保留

- 会话过期按保留策略清理私有 Project 与未分享数据。
- 活跃 ShareSnapshot 可按政策保留所需最小版本，或在项目清理时同步撤销。
- 涉及密钥、侵权或依法删除时执行强制删除；审计记录不得继续保留必须清除的敏感内容。
- 导出和临时下载 URL 有独立过期时间，不作为 ArtifactVersion 的唯一存储。

## 11. 实施顺序

1. v2 Pydantic Schema 与迁移映射。
2. ResearchProject、ResearchContract、ResearchRun、RunStep / Event 持久化。
3. ResearchArtifact、ArtifactVersion、SourceSnapshot 和 Evidence 事务边界。
4. CacheRecord、派生 Run、Feedback / RevisionPlan。
5. WorkspaceSnapshot 与安全 ShareSnapshot。

任何阶段都不因版本治理提前引入 Redis、对象存储、图数据库或通用事件总线。

## 12. 验收

- 同一输入和 producer version 产生稳定 hash。
- old / latest / supersedes 关系无环且可回溯。
- Cache、Share、Export 不引用动态 latest。
- Revision 保留旧版本并能显示影响范围。
- Share token 只存 hash、可撤销、可过期、无法跨 Project 扩权。
- Prompt、模型、来源、Contract 与 Evidence 均能定位明确版本。
