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
ResearchProject (1) -- (0..1) WorkspaceSnapshot
ResearchProject (1) -- (*) ShareSnapshot
ShareSnapshot (*) -- (*) ArtifactVersion
UserFeedback (*) -- (1) ArtifactVersion
RevisionPlan (1) -- (*) UserFeedback
CacheRecord (*) -- (1) ArtifactVersion
```

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
- UserFeedback 固定目标 ArtifactVersion 与对象定位；RevisionPlan 固定受影响产物闭包，确认后才能创建 revision Run。
- CacheRecord 固定可复用的历史 Run、ArtifactVersion、SourceSnapshot 与匹配 identity；CacheSelector 只返回通过 Contract 与 Evidence 校验的记录。
- HTTP Run authoring 只创建 original、cache-disabled Run；未暴露的派生字段不得被静默消费。

## 4. Artifact、Evidence 与来源

- ResearchArtifact 表示逻辑产物；ArtifactVersion 是不可变内容快照，保存 version number、canonical hashes、source mode、ProducerExecution 与 Evidence identity。
- Evidence 必须绑定具体 ArtifactVersion 与 SourceSnapshot，并提供 target、locator、值或短引文、extraction method 与 confidence。
- SourceSnapshot 保存一次真实或录制来源读取的查询、内容哈希、抓取时间、许可与脱敏元数据。
- ResearchInput 是受控摄取后的不可变内容引用；稳定生命周期区分 `accepted`、`unsupported_processing` 与 `failed_ingestion`。摄取写入只在成功时创建 `accepted` 资源，失败通过 Problem Details 返回，不伪造失败资源。

## 5. Workspace 与 Share

WorkspaceSnapshot 保存私有布局与选中对象，使用乐观锁更新。ShareSnapshot 冻结具体 ArtifactVersion 和 Evidence 范围，服务端只保存 token hash。

## 6. 核心不变量

1. Project、Draft、Contract、Run、Artifact、Evidence、ResearchInput 与 Snapshot 的外键不得跨 Project 聚合。
2. Contract confirmation、Run creation 与输入摄取的幂等 replay 必须返回已持久化资源的同一事实。
3. ArtifactVersion 发布后内容与 hash 不可原地修改；latest 指针不替代具体 version 引用。
4. `execution_mode` 与 `source_mode` 分离；Fixture、Live 与 Cached provenance 不得互相伪装。
5. 公开 API 不返回凭据、受限全文、原始模型响应或私有 chain-of-thought。
