# Data Model

| 元数据 | 值 |
| --- | --- |
| Authority | 核心领域实体、实体关系、所有权与数据不变量 |

具体字段由 Pydantic authoring models、PostgreSQL schema 与 TypeScript Domain 契约共同物化；本文件定义稳定关系与职责。

## 1. 聚合关系

```text
ResearchSession (1) -- (*) ResearchProject
ResearchProject (1) -- (*) ResearchContractDraft
ResearchContractDraft (1) -- (0..1) ResearchContract
ResearchProject (1) -- (*) ResearchContract
ResearchProject (1) -- (*) ResearchRun
ResearchContract (1) -- (*) ResearchRun
ResearchRun (0..1) -- (*) derived ResearchRun
ResearchRun (1) -- (*) RunStep -- (*) StepAttempt
ResearchRun (1) -- (*) RunEvent
ResearchProject (1) -- (*) ResearchArtifact -- (*) ArtifactVersion
ResearchRun (1) -- (*) ArtifactVersion
ArtifactVersion (1) -- (*) Evidence
SourceSnapshot (1) -- (*) Evidence
ResearchProject (1) -- (*) ResearchInput
ResearchInput (1) -- (*) DocumentParse -- (*) DocumentParseLocator
SourceSnapshot (1) -- (*) DocumentParse
ResearchProject (1) -- (0..1) WorkspaceSnapshot
ResearchProject (1) -- (*) ShareSnapshot
ShareSnapshot (*) -- (*) ArtifactVersion
```

`UserFeedback`、`RevisionPlan` 与 `CacheRecord` 的关系属于目标契约；当前运行时不创建这些对象。

## 2. Project、Draft 与 Contract

- ResearchSession 是匿名访问者的服务端隔离与配额边界。
- ResearchProject 是持续研究上下文，`description` 始终为非空字符串，未填写时保存 `""`。
- ResearchContractDraft 是 Project-owned editable entity，使用 `(id, project_id)` 与 `(project_id, session_id)` composite identity 保证属主一致。
- ResearchContract 从一个 Draft 确认产生；`created_from_draft_id + project_id` composite lineage 强制 Draft 与 Contract 属于同一 Project。一个 Draft 最多产生一个 Contract。
- Contract 确认后不可变，包含研究目标、目标对象、请求字段、来源范围、Evidence 与质量约束。

## 3. Run 与执行记录

- ResearchRun 绑定同一 Project 下的 Contract；派生 Run 通过同 Project 的 `parent_run_id` 与 `derivation_kind` 表达 retry、revision 或 fork。
- RunStep 保存 canonical step、顺序、状态与进度；StepAttempt 保存真实尝试、错误与上游请求 identity。
- RunEvent 是单调序列的通知记录，Run 快照才是状态事实源。
- HTTP Run authoring 只创建 original、cache-disabled Run；未暴露的派生字段不得被静默消费。

目标修订与缓存契约：UserFeedback 固定目标 ArtifactVersion 与对象定位；RevisionPlan 固定受影响产物闭包，确认后才能创建 revision Run。CacheRecord 固定可复用的历史 Run、ArtifactVersion、SourceSnapshot 与匹配 identity；CacheSelector 只返回通过 Contract 与 Evidence 校验的记录。它们在对应执行闭环实现前不得被描述为当前数据库或运行时对象。

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

WorkspaceSnapshot 保存私有布局与选中对象，使用乐观锁更新。ShareSnapshot 冻结具体 ArtifactVersion 和 Evidence 范围，服务端只保存 token hash。

## 7. 核心不变量

1. Project、Draft、Contract、Run、Artifact、Evidence、ResearchInput 与 Snapshot 的外键不得跨 Project 聚合。
2. Contract confirmation、Run creation 与输入摄取的幂等 replay 必须返回已持久化资源的同一事实。
3. ArtifactVersion 发布后内容与 hash 不可原地修改；latest 指针不替代具体 version 引用。
4. `execution_mode` 与 `source_mode` 分离；Fixture、Live 与 Cached provenance 不得互相伪装。
5. 公开 API 不返回凭据、受限全文、原始模型响应或私有 chain-of-thought。
6. Evidence Graph 的 frozen input versions、Graph-owned Evidence 与 literature relation projection 必须在读取边界保持同 Project、同 Version、同 producer/hash closure；任何漂移 fail closed。
7. DocumentParse 与其 locator 创建后不可更新；相同 Project 与相同逻辑身份只能有一个权威 parse，读取时必须校验 payload 与冻结 metadata。
