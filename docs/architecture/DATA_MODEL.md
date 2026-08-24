# Data Model

| 元数据 | 值 |
| --- | --- |
| Authority | 核心领域实体、实体关系、所有权与数据不变量 |

具体字段由 Pydantic authoring models、PostgreSQL schema 与 TypeScript Domain 契约共同物化；本文件定义稳定关系与职责。

## 1. 聚合关系

```text
System (1) -- (0..1) ModelProviderConfiguration
ResearchSession (1) -- (*) ResearchProject
ResearchProject (1) -- (*) ResearchThreadEntry
ResearchProject (1) -- (*) ModelExecutionRecord
ResearchProject (1) -- (*) ResearchContractDraft
ResearchContractDraft (1) -- (0..1) ResearchContract
ResearchProject (1) -- (*) ResearchContract
ResearchProject (1) -- (*) ResearchRun
ResearchContract (1) -- (*) ResearchRun
ResearchRun (0..1) -- (*) derived ResearchRun
ResearchRun (1) -- (*) RunStep -- (*) StepAttempt
ResearchRun (1) -- (*) RunEvent
ResearchRun (1) -- (*) RunCheckpoint -- (0..1) RunCheckpointDecision
ResearchProject (1) -- (*) ResearchArtifact -- (*) ArtifactVersion
ResearchRun (1) -- (*) ArtifactVersion
ArtifactVersion (1) -- (*) Evidence
SourceSnapshot (1) -- (*) Evidence
ResearchProject (1) -- (*) CacheRecord
completed Live ResearchRun (1) -- (*) CacheRecord
live ArtifactVersion (1) -- (*) CacheRecord
failed RunStep (1) -- (*) CacheSelectionAudit -- (0..1) CacheRecord
ResearchProject (1) -- (*) ResearchInput
ResearchInput (1) -- (*) DocumentParse -- (*) DocumentParseLocator
SourceSnapshot (1) -- (*) DocumentParse
ResearchProject (1) -- (0..1) WorkspaceSnapshot
ResearchProject (1) -- (*) ShareSnapshot
ShareSnapshot (*) -- (*) ArtifactVersion
ArtifactVersion (1) -- (*) UserFeedback
UserFeedback (*) -- (*) RevisionPlan -- (0..1) RevisionPlanConfirmation -- (1) ResearchRun
```

`CacheRecord`、`CacheSelectionAudit`、`UserFeedback`、`RevisionPlan` 与 `RevisionPlanConfirmation` 均为当前 PostgreSQL 运行时对象。

## 2. Project、Draft 与 Contract

- ResearchSession 是匿名访问者的服务端隔离与配额边界。PostgreSQL 只保存 credential/CSRF hash、status、expiry、quota 与单调 security version；resume、rotation 与 revoke 在行锁事务内原子提交。
- ResearchProject 是持续研究上下文，`description` 始终为非空字符串，未填写时保存 `""`。
- ResearchProject 的 `active_draft_id` 只能指向同一 Project、状态为 editable 的当前 Draft；它是当前审查对象的唯一指针，不能以 `latest` 查询替代。
- ResearchThreadEntry 属于 Project，使用 `(project_id, sequence)` 唯一约束保证严格顺序；`kind`、`actor`、`public_content` 与 `structured_payload` 只保存公开内容。Contract、Run、Artifact 卡片必须读取真实实体后投影，不能在 Thread 中复制第二份事实。
- ModelExecutionRecord 属于 Project，是 pre-run Research assistant 的执行审计记录，与 Run 的 ProducerExecution 分离；它固定 Registry Prompt、规范化 input/parameters、通过验证的公开 output snapshot 与对应 hash。同一 Project 同时最多存在一个 `pending | running` ModelExecution；provider 调用期间不持有 Project 行锁，由短事务检查与数据库部分唯一索引共同强制。活跃记录必须持有 token + expiry 执行租约，租期覆盖每次 provider timeout、全部传输尝试、SDK 可接受的最坏 `Retry-After` 等待与持久化余量；重试次数必须有配置上限。过期记录由下一次 Project 写入在行锁内标记失败，迟到 worker 只有仍持有原租约且租约未过期时才能提交成功或失败终态。不得存储 API secret、认证头、raw provider body 或私有 chain-of-thought。
- ModelProviderConfiguration 是至多一条的实例级运行配置，不属于 Session、Project 或 Run。它保存 preset、
  规范化 base URL、model、加密 API Key、掩码尾号、单调 revision 与验证时间；部署 baseline 不复制到表中。
  移除工作台 override 时推进 revision 并保留不含凭据的 tombstone，后续写入不得重用历史 revision。
  工作台 override 更新后只影响新模型调用，既有调用继续持有创建时的不可变 runtime snapshot。
- ResearchContractDraft 是 Project-owned editable entity，使用 `(id, project_id)` 与 `(project_id, session_id)` composite identity 保证属主一致。
- ResearchContract 从一个 Draft 确认产生；`created_from_draft_id + project_id` composite lineage 强制 Draft 与 Contract 属于同一 Project。一个 Draft 最多产生一个 Contract。
- Contract 确认后不可变，包含研究目标、目标对象、请求字段、来源范围、Evidence 与质量约束。

## 3. Run 与执行记录

- ResearchRun 绑定同一 Project 下的 Contract；派生 Run 通过同 Project 的 `parent_run_id` 与 `derivation_kind` 表达 retry、revision 或 fork。同一 Project 同时最多一个 non-terminal ResearchRun，由 partial unique index 作为权威并发围栏。
- RunStep 保存从 confirmed Contract 确定性投影并在 Run 创建时冻结的 canonical step、顺序、状态与进度；StepAttempt 保存真实尝试、错误与上游请求 identity。Executor 不维护第二份 Plan。
- RunCheckpoint 保存同一 Run 在 `waiting_for_input` 边界的人工输入请求（run、step_key、question、options、created_at）；RunCheckpointDecision 保存不可变的 `selected_option`、可空 `free_text` 与 `decided_at`。Decision 创建后不可更新；提交后同一 Run 恢复到合法可执行状态，不创建新 Run 或第二套 review 资源。
- RunEvent 是单调序列的通知记录，Run 快照才是状态事实源。
- HTTP original Run authoring 只创建 original、cache-disabled Run；revision Run 只能由已确认 RevisionPlan 创建，其他未暴露派生字段不得被静默消费。

UserFeedback 固定当前 ArtifactVersion 与对象定位；RevisionPlan 固定同一 completed parent Run、Feedback、parent revision、全部 latest ArtifactVersion、受影响产物闭包、复用版本与 canonical steps。不可变 Confirmation 一对一绑定 Plan 和 revision Run，二者在同一事务创建。

- CacheRecord 是不可变的 Project-owned 复用资格快照，只能从 completed Live Run 的 `source_mode=live` ArtifactVersion 物化；它固定 origin Run/ArtifactVersion、Contract/input、producer/Prompt、SourceSnapshot identity hash、Evidence、质量约束与有效期 identity。
- CacheSelectionAudit 绑定 failed RunStep、明确的 failed ProducerExecution 与本次 recoverable failure。命中时再绑定同 Project 的 CacheRecord/origin Run/origin ArtifactVersion；拒绝时这些 origin 字段必须为空。审计与对应 `cache.selected | cache.rejected` Event 使用同一个持久化 sequence，且均不可原地更新。

## 4. Artifact、Evidence 与来源

- ResearchArtifact 表示逻辑产物；ArtifactVersion 是不可变内容快照，保存 version number、canonical hashes、source mode、ProducerExecution 与 Evidence identity。
- Evidence 必须绑定具体 ArtifactVersion 与 SourceSnapshot，并提供 target、locator、值或短引文、extraction method 与 confidence。
- SourceSnapshot 保存一次真实或录制来源读取的查询、内容哈希、抓取时间、许可与脱敏元数据。
- ResearchInput 是受控摄取后的不可变内容引用；稳定生命周期区分 `accepted`、`unsupported_processing` 与 `failed_ingestion`。摄取写入只在成功时创建 `accepted` 资源，失败通过 Problem Details 返回，不伪造失败资源。
- DocumentParse 是 Project-owned、ResearchInput-backed 的内部不可变预处理 derivative，不是公开 ResearchArtifact 或 ArtifactVersion kind。其逻辑身份固定输入内容、parser/profile/model/config revision 与 Canonical output hash；完整 Canonical payload 使用原子 content-addressed storage，PostgreSQL 只保存身份、ownership、SourceSnapshot、ProducerExecution 与安全内容引用。
- Upload ResearchInput 在首次正式解析持久化时按需生成只含 ResearchInput identity、content hash 与安全 provenance 的 SourceSnapshot，不复制 PDF、图片或全文。
- DocumentParseLocator 固定同 Project 的一个 DocumentParse 与 SourceSnapshot；page、block、bbox、text span、table 与 cell 必须在该 Parse 内闭合，dangling、cross-parse 与 cross-project 引用均拒绝。

## 5. Evidence Graph

- `graph` ArtifactVersion 保存同一 Project 内由明确上游 ArtifactVersion 派生的不可变 node、directed edge 与 Graph-owned Evidence-use closure；Graph 不引用动态 `latest`，分页或渐进读取也不产生新的科学产物。
- Graph input version references 固定 artifact/version identity、kind、schema、content/input/output hash、source mode 与 producer identity。读取时必须重新解析到 persisted ArtifactVersion 并逐项闭合，不能仅信任 Graph content 自身声明。
- node version bindings、Evidence-use upstream version 与 literature edge Relation/Trace version 只能落在已验证的 input/provenance registry 及其由可信上游 content 声明的传递版本内。
- Graph-owned Evidence 由 Publisher 与 Graph ArtifactVersion 在同一事务中物化，target 固定为 `graph_edge`，并在 locator 中保留 upstream ArtifactVersion/Evidence/target/hash；读取层只验证与投影，不重建 Graph 或修补 provenance。
- literature edge 必须保持 accepted Relation 的方向和 type，并闭合双方 Claim、ReasoningTrace、Evidence 与 SourceSnapshot；structural edge 不伪造 Relation/Trace。
- Graph taxonomy、build/admission、hash、容量与 publication 规则由 [Evidence Graph Pipeline](../engineering/GRAPH_PIPELINE.md) 定义；本数据模型只保存稳定实体关系与 ownership 不变量。

## 6. Workspace 与 Share

WorkspaceSnapshot 保存私有布局与选中对象，通过 `(project_id, owner_session_id)` 外键闭合 ownership，并使用乐观锁更新。ShareSnapshot 通过同一复合 ownership 外键冻结具体 ArtifactVersion、Evidence 与 SourceSnapshot identity 的已脱敏公开投影；ArtifactVersion 只冻结由现有 typed Artifact authority 构造的正向科学呈现，不保存原始内容的公开副本或第二套领域模型，呈现中的 Evidence identity 必须来自同一冻结版本。服务端只保存 token hash；重启后的公开读取不重新投影动态资源。

Session retention 只删除达到保留期且没有 ResearchProject 引用的记录；Share retention 可删除达到保留期的撤销/过期分享。两者均不级联删除正常科研历史。

## 7. 核心不变量

1. Project、Draft、Contract、Run、Artifact、Evidence、ResearchInput 与 Snapshot 的外键不得跨 Project 聚合。
2. Contract confirmation、Run creation 与输入摄取的幂等 replay 必须返回已持久化资源的同一事实。
3. ArtifactVersion 发布后内容与 hash 不可原地修改；latest 指针不替代具体 version 引用。
4. UserFeedback、RevisionPlan、Plan 关系与 Confirmation 创建后不可更新；确认前必须重新闭合 parent revision 与全部 frozen latest 指针。
5. `execution_mode` 与 `source_mode` 分离；Fixture、Live 与 Cached provenance 不得互相伪装。
6. 公开 API 不返回凭据、受限全文、原始模型响应或私有 chain-of-thought。
7. Evidence Graph 的 frozen input versions、Graph-owned Evidence 与 literature relation projection 必须在读取边界保持同 Project、同 Version、同 producer/hash closure；任何漂移 fail closed。
8. Thread sequence 在同一 Project 内严格递增且刷新可重放；跨 Project 的 entry、Draft、Execution、Run 读取统一 fail closed。
9. `ModelExecutionRecord` 的状态、错误、safe snapshots 与 timing 必须反映实际 provider 调用；失败前已获得的 output hash、token、latency 与 request identity 不得丢失；无 credentials 时不得生成 succeeded 记录。
10. Provider 成功不等于 Turn 成功；最终 Draft/Thread 持久化必须与 ModelExecution 终态同一事务提交。该事务失败时必须释放 Project 的活跃执行槽，进程中断遗留的活跃记录必须经租约过期回收，不能永久阻塞后续 Turn。
11. DocumentParse 与其 locator 创建后不可更新；相同 Project 与相同逻辑身份只能有一个权威 parse，读取时必须校验 payload 与冻结 metadata。
12. ModelProviderConfiguration 只在真实 Chat Completions 连接探测成功后写入；原始 API Key 不得出现在
    DTO、日志、浏览器存储或模型执行记录中。
