# Data and Artifact Versioning

| 项目状态  | 口径                                              |
| --------- | ------------------------------------------------- |
| Status    | Accepted                                          |
| Authority | ArtifactVersion、来源、缓存、修订、分享与保留规则 |

本文定义科研产物、来源、缓存、修订、工作台与分享的版本规则。ArtifactVersion、Evidence 和 SourceSnapshot 由 PostgreSQL 提供私有读取与 Project ownership 边界；`paper_collection` 在该边界上提供只读校验与候选 keyset cursor，不改变发布事务。Workspace/Share Runtime 使用 PostgreSQL resource authority 校验资源事实；WorkspaceSnapshot 与 ShareSnapshot 记录由进程内 Adapter 保存，不跨重启或实例共享。

## 1. 版本边界

C-04 的 `MappingRuleSet` 与 `UnitConversionCatalog` 是 Artifact 内容生成条件：两者的完整仓库冻结内容（包括 entity projection、集合 tolerance、容量和 Decimal 安全边界）的 id/version/content hash、Case/Field Manifest pins、C-08 result、acquisition SourceSnapshot/record set 和 requested fields 全部进入 `DataArtifactBuildInput.input_hash`。公共入口拒绝 caller 自行修改并重算 hash 的替代策略。Dataset、FieldDictionary、SourceCollection 和 bundle 分别计算 output hash；bundle 对三类 candidate 执行共同 pins、producer、input、Snapshot/Evidence、FieldDefinition 与 raw-record 引用闭包校验后才封印实例。Pipeline typed candidate 尚未成为 `ArtifactVersion`；只有通过 #78 structured admission port 并进入 Publisher 事务后，才能分配数据库版本号。

C-05 的 `DataQualityEvaluationInput.input_hash` 进一步绑定 C-04 input/candidate IDs/output hashes、Dataset canonical/lineage hash、C-08 identity、ResearchContract projection、冻结 `DataQualityRuleSet`、SourceSnapshot/Evidence IDs 和 producer version。`DataQualityEvaluationResult` 的 output/content hash 不包含自身 hash、wall-clock、日志、分支、数据库 ID、ArtifactVersion number 或 private seal；它仍不是 `ArtifactVersion`。只有通过 process-local C-05 pass-only gate 与 #78 Publisher port 后，B 才能创建数据库版本。

| 对象              | 是否不可变           | 用途                                                        |
| ----------------- | -------------------- | ----------------------------------------------------------- |
| ResearchContract  | 确认后不可变         | 固定一次 Run 的研究输入和质量要求                           |
| ResearchRun       | 创建后关键输入不可变 | 记录一次执行、失败、取消或派生关系                          |
| ResearchArtifact  | 身份可更新           | 表示同一逻辑产物，维护 latest 指针                          |
| ArtifactVersion   | 内容不可变           | Evidence、Cache、Share、Export 的绑定单位                   |
| SourceSnapshot    | 不可变               | 固定外部来源、查询、时间和许可信息                          |
| BenchmarkPackage  | 已发布版本不可变     | 使用 benchmark id、version 与 content hash 固定静态评测输入 |
| WorkspaceSnapshot | 可覆盖、乐观锁       | 私有 UI 恢复状态，不是科研产物                              |
| ShareSnapshot     | 创建后不可变         | 冻结公开版本与脱敏范围                                      |

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

Publisher 只接受通过 Pydantic 结构校验以及调用方 Evidence、Domain、Quality 三道准入门的 opaque candidate。发布事务按 `ResearchRun -> RunStep -> ResearchArtifact（id 排序）` 固定顺序加锁，并原子写入 Version、latest、Attempt、Step、Run 和 Event；任一写入失败全部回滚。`publication_key` 在 Artifact 内唯一，同 key 同内容和 producer 条件重放既有 Version，不同条件返回稳定冲突。

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

对 PaperCollection，ArtifactVersion `content_hash` 固定 Publisher 实际写入的完整 JSON；content 内部 D-02 `output_hash` 固定排除抓取和执行 wall-clock 后的科研稳定内容。读取时必须分别复算，不能要求这两个 hash 相等。

D-02 在 PaperCollection content 内生成 detached ProducerExecution：记录固定 step key、producer/rule version、parameters/input/output hash、状态、时间、latency 和错误码，不登记 ResearchRun 或数据库记录。持久化 ProducerExecution Store 与 ArtifactVersion 分配由 Publisher 端口负责，detached 记录经该端口进入持久化与版本边界。具体稳定 hash 与失败记录见 [PaperCollection Pipeline](../engineering/PAPER_COLLECTION_PIPELINE.md)。

D-03 同样生成 detached PaperSummary ProducerExecution，记录 `model_name`、Prompt name/version/hash、parameters version/hash、PaperCollection ArtifactVersion id/schema/output hash、SourceSnapshot 版本、input hash、模型响应 hash、最终 output hash 与安全终态。读取投影同时暴露 ArtifactVersion `version_number` / `supersedes_version_id`；Cached Summary 必须逐来源给出 cache version、适用性、Live 失败原因和 origin Run/ArtifactVersion，并把 audit `source_id` 绑定到对应 SourceSnapshot，不允许来源调换、空审计或与 `source_mode` 不一致的审计进入正常读取。JSON/Schema 拒绝只保留稳定 error code 和响应 hash，不保留原始模型输出；Evidence 降级仍产生可审查 Summary content，但 unsupported/unverifiable 项不作为已验证事实。生产模型 client、数据库 ProducerExecution 持久化与 ArtifactVersion 事务属于 Workflow 与读取投影边界。

D-07 生成 detached LiteratureClaim ProducerExecution，固定 PaperSummary ArtifactVersion/schema/output hash、paper/summary、SourceSnapshot versions、Prompt/schema/model/parameters/producer/normalization version 与 input/model-response/output hash。JSON/Schema rejected result 不保存原始响应；Schema-valid Claim 的 accepted/candidate/rejected record 均保留输入与 execution 引用。`LiteratureClaimsCandidate` 已通过 Pipeline seal，可进入 structured ArtifactVersion admission；其内部稳定 `output_hash` 排除 execution/run id、wall-clock 与 latency，ArtifactVersion admission 返回的 `content_hash` 则覆盖准备持久化的完整 JSON，两者不要求相等。后续持久化与读取边界使用 admitted `content_hash` 对照数据库 ProducerExecution，并负责 ArtifactVersion 接线和 version-pinned HTTP projection。

D-08 生成 detached LiteratureRelation ProducerExecution，固定一个或多个 sealed
LiteratureClaims ArtifactVersion/schema/content/output hash、双方 Claim/PaperSummary
versions、Evidence/SourceSnapshot、`literature_reasoning@v2`、model/parameters、pairing、
comparison、Trace protocol、confidence definition/calibration 与 input/model-response/output
hash。confidence score 来自外部版本化 assessment，不由模型生成；它表示完整
`relation type + admission decision` 的置信，不表示 accepted probability。assessment
subject 绑定 source/target Claim ArtifactVersion/id、relation type 与 fingerprint，并绑定
当前 admission decision；跨方向、版本、类型或 decision 复用必须拒绝。JSON/Schema
rejected result 只保存稳定 error code 和响应 hash，不保存原始模型响应。

`LiteratureRelationsCandidate@1.0.0` 是 D-08 唯一 structured ArtifactVersion admission
输入。单个 `kind=literature_relations` candidate 同时内嵌 Relation 与 ReasoningTrace
闭包，不单独发布 `reasoning_traces` Artifact。私有 seal 绑定对象身份、schema、
input/output hash、admission context/commitment 与完整 public payload hash；authority
registry 与唯一 minter 仅存在于进程内闭包，一次性 binder 只绑定 exact Pipeline owner
class 后删除自身，不序列化为可窃取 token，也不保留可导入 mint/registry。
mint 同时绑定原始 `admit` code frame 与其局部 gate-complete candidate；脱离该调用点的
反射调用不能注册 authority。JSON/Pydantic round-trip、
copy/deepcopy、手工重建、Phase 0/core 投影或字段/hash 修改都不能恢复 seal。D-08 不分配
数据库版本号；后续 Publisher 对 admitted 完整 JSON 计算 `content_hash` 并执行事务。

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

成功的 NASA Exoplanet Archive TOI acquisition 必须生成完整不可变 SourceSnapshot，记录冻结 Manifest、规范化 query/hash、TAP_SCHEMA 预检、keyset 分页、请求/响应 hash、耗时、重试、许可、版本/ETag 与 request-id 可用性。上游未提供 ETag 或 request-id 时显式记录 `unavailable`，不得生成替代值；Recorded response 固定为 `source_mode=fixture` 与 `data_level=recorded_response`，并绑定版本化 fixture hash/provenance。运行规则见 [Data Source Acquisition](../engineering/DATA_SOURCE_ACQUISITION.md)。

C-07 对 PS 补充来源生成独立 SourceSnapshot；C-08 不合并或重写两侧
Snapshot，而是把双方 Snapshot/query/content hash、completion、origin、排序后的
raw-record hashes、Manifest/RuleSet/SourcePolicy/alias pins 和可选人工裁决 hash 绑定到稳定
`source_input_hash` / `input_hash`。`output_hash` 绑定 candidate、edge、Evidence、
未解决结果和指标，不包含 wall-clock、日志或输出路径。规则语义变化必须发布新
RuleSet version/hash。运行规则见
[Cross-source Entity Alignment](../engineering/CROSS_SOURCE_ENTITY_ALIGNMENT.md)。

成功的 Crossref metadata execution 生成完整不可变 SourceSnapshot；失败请求保存 SourceExecution 的 query/pagination/hash/error，不伪造 Snapshot。Cached PaperCollection 要求 Snapshot 额外绑定真实 `origin_run_id` 与 `origin_artifact_version_id`；CacheSelector 与 origin persistence 由 B/Workflow 边界负责。

## 6. Hash 规则

C-04 数值使用版本化 Decimal/serialization 策略；Transformation Evidence、source value、row、selection、conflict 与三类 candidate 均重算稳定 hash。hash 不包含 wall-clock、Git 分支、日志、数据库 ID、ArtifactVersion number 或 Publisher content hash，不能用重新解析/复制实例绕过 publication seal。具体字段见 [Versioned Data Artifacts](../engineering/VERSIONED_DATA_ARTIFACTS.md)。

- JSON hash 前使用稳定键顺序、明确数字/日期编码和 UTF-8。
- 文本统一 UTF-8 与 LF 后计算；二进制使用 SHA-256。
- Dataset manifest 包含字段、row count、分页/文件 hash，不依赖显示顺序。
- 模型输入 hash 覆盖 Prompt 版本、模型参数、Contract hash 和输入 Evidence / ArtifactVersion。
- D-03 `input_hash` 覆盖 PaperCollection Version/schema/output hash、SourceSnapshot id/version/content hash、目标 paper、Evidence 输入 hash、Prompt name/version/hash、model、parameters version/hash；相同版本化输入可定位同一 input hash。
- D-03 `model_response_hash` 标识原始响应而不保存原文；`output_hash` 固定经过 Evidence 准入后的稳定 Summary 内容，排除 execution id、run id、wall-clock、latency 与 producer output hash 自引用。
- D-07 `input_hash` 继续覆盖 PaperSummary Version/schema/output hash、paper/summary、SourceSnapshot 版本、Prompt/model/parameters 与 producer/normalization version；valid `model_response_hash` 对 Claim 集合做稳定排序，`output_hash` 覆盖准入后的结构、Evidence、状态和拒绝原因并排除 execution/run id、wall-clock、latency 与自引用。
- D-08 `input_hash` 覆盖 sealed LiteratureClaims 输入版本、双方 Claim/PaperSummary、Evidence/SourceSnapshot、Prompt/model/parameters、pairing/comparison/Trace policy 与 confidence definition/calibration；valid `model_response_hash` 对固定方向 Relation 结构做稳定排序。Relation fingerprint 覆盖双方 Claim ArtifactVersion/id 与 relation type；`output_hash` 覆盖 Relation/Trace、Evidence 闭包、confidence、三态和拒绝原因，并排除 execution/run id、wall-clock、latency、嵌套 producer execution id 与自引用。
- Prompt 文件按 UTF-8/LF 归一后计算 SHA-256；registry 明确列出每个不可变版本的 path/content hash/status，历史版本不原地改写。
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

同一 payload 的 PUT 重放返回既有 Snapshot；不同 payload 必须匹配当前 revision，冲突不静默覆盖。Snapshot Adapter 为进程内实现，重启后状态失效；任何持久化 Adapter 必须保持相同 revision 语义。

ShareSnapshot 固定：

- ArtifactVersion ids；
- 可公开 Evidence ids；
- redaction policy；
- created_at / expires_at；
- token hash 与撤销状态。

分享不指向 latest，因此后续修订不会改变已提交 URL 的内容。原 token 不进入数据库明文、日志或 Project 聚合响应。

创建时复制允许公开的不可变 Version/Evidence 元数据形成冻结投影；之后即使目录中的 latest 或显示元数据变化，既有分享响应也不漂移。Redaction policy 为 `public_metadata_only`。

## 10. 删除与保留

- 会话过期按保留策略清理私有 Project 与未分享数据。
- 活跃 ShareSnapshot 可按政策保留所需最小版本，或在项目清理时同步撤销。
- 涉及密钥、侵权或依法删除时执行强制删除；审计记录不得继续保留必须清除的敏感内容。
- 导出和临时下载 URL 有独立过期时间，不作为 ArtifactVersion 的唯一存储。

## 11. 架构依赖

ArtifactVersion 发布依赖已校验的领域内容、ProducerExecution、Evidence 与 SourceSnapshot。任务顺序和直接依赖由 Roadmap、Backlog 与 GitHub 原生 Dependency 维护。

任何阶段都不因版本治理提前引入 Redis、对象存储、图数据库或通用事件总线。

## 12. 验收

- 同一输入和 producer version 产生稳定 hash。
- old / latest / supersedes 关系无环且可回溯。
- Cache、Share、Export 不引用动态 latest。
- Revision 保留旧版本并能显示影响范围。
- Share token 只存 hash、可撤销、可过期、无法跨 Project 扩权。
- Prompt、模型、来源、Contract 与 Evidence 均能定位明确版本。
