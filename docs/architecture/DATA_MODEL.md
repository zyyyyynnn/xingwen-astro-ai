# Data Model

| 元数据 | 值 |
| --- | --- |
| Status | Accepted |
| Authority | 核心领域实体、实体关系、所有权与数据不变量 |

本文定义系统的核心领域实体、领域语义与关系不变量。具体字段全集由后端 Pydantic 模型、数据库 Schema 与前端 TypeScript Domain 编写源权威定义。

## 1. 建模原则

- **Project**：表示持续的研究任务上下文。
- **Contract**：表示不可变的研究输入协议与质量约束。
- **Run**：表示一次由 Contract 驱动的独立执行。
- **Artifact**：表示科研产物的逻辑身份。
- **ArtifactVersion**：表示科研产物的不可变内容快照。
- **Evidence**：表示产物中的数据点或结论所绑定的唯一证据。
- **SourceSnapshot**：表示原始数据或文献的来源快照。

## 2. 实体关系 (ER Diagram)

```text
ResearchSession (1) -- (*) ResearchProject
ResearchProject (1) -- (*) ResearchContract
ResearchProject (1) -- (*) ResearchRun
ResearchProject (1) -- (*) ResearchArtifact
ResearchContract (1) -- (*) ResearchRun
ResearchRun (1) -- (*) RunStep
ResearchRun (1) -- (*) RunEvent
ResearchArtifact (1) -- (*) ArtifactVersion
ResearchRun (1) -- (*) ArtifactVersion
ArtifactVersion (1) -- (*) Evidence
SourceSnapshot (1) -- (*) Evidence
ResearchProject (1) -- (0..1) WorkspaceSnapshot
ResearchProject (1) -- (*) ShareSnapshot
ShareSnapshot (*) -- (*) ArtifactVersion
UserFeedback (1) -- (1) ArtifactVersion
```

## 3. 核心实体说明

### 3.1 ResearchSession
匿名访问者的服务端隔离边界。控制配额与所有权防越权，Session ID 严禁进入公开 URL、日志或导出。

### 3.2 ResearchProject
持续研究问题的主载体，包含名称、描述与关联主案例。一个 Project 可包含多个 Contract、并行 Run、Artifacts 与 ShareSnapshots。

### 3.3 ResearchContract
确认后的不可变科研输入协议，定义研究目标 (`research_goal`)、目标对象 (`target_objects`)、请求字段 (`requested_fields`)、允许来源范围 (`source_scope`) 与质量约束 (`quality_constraints`)。
Draft 是编辑态资源，一旦确认即产生不可变 Contract。

### 3.4 ResearchRun、RunStep 与 RunEvent
- **ResearchRun**：驱动一次完整的执行，包含 `execution_mode` (demo_replay / live)、`status` (RunStatus)、`parent_run_id` 与 `derivation_kind` (original / retry / revision / fork)。
- **RunStep**：记录具体的步骤状态 (pending / running / completed / failed) 与重试尝试 (StepAttempt)。
- **RunEvent**：增量推送的有序进度事件，仅作通知使用，不作为状态事实源，严禁包含模型私有思维过程。

### 3.5 ResearchArtifact 与 ArtifactVersion
- **ResearchArtifact**：拥有逻辑身份与 `kind` 标识（`dataset` / `field_dictionary` / `source_collection` / `paper_collection` / `paper_summary` / `literature_claims` / `literature_relations` / `reasoning_traces` / `graph` / `export`）。
- **ArtifactVersion**：不可变快照。包含 `version_number`、`content`、`content_hash`、`input_hash`、`source_mode` (fixture / live / cached)、`producer` 描述、`evidence_ids` 与 `supersedes_version_id`。

### 3.6 Evidence 与 SourceSnapshot
- **Evidence**：绑定特定 `artifact_version_id` 与 `source_snapshot_id`。包含 `target_type`、`locator`、`quote_or_value`、`extraction_method` 与 `confidence`。
- **SourceSnapshot**：抓取或检索到的不可变原始数据/文献快照，包含 `source_id`、`retrieved_at`、`query_hash`、`content_hash` 与 `request_metadata`（仅限非敏感可复现字段）。

### 3.7 WorkspaceSnapshot 与 ShareSnapshot
- **WorkspaceSnapshot**：私有工作台布局与 UI 恢复状态，包含面板槽位（Slot）与选中的对象引用。
- **ShareSnapshot**：只读公开快照，锁定具体不可变的 `artifact_version_ids` 与脱敏规则，服务端仅保存 `token_hash`。

### 3.8 UserFeedback 与 RevisionPlan
- **UserFeedback**：针对特定产物版本（如字段、关系、文献总结）提交的修正建议。
- **RevisionPlan**：受影响的产物闭包。确认修定计划后启动 `derivation_kind=revision` 的新 Run 并生成新的 ArtifactVersion。

## 4. 关键不变量

1. **不可变性**：`ArtifactVersion` 一经创建，其内容与哈希计算后严禁原地修改。
2. **唯一属主**：所有 Project、Run、Artifact、Evidence 与 Snapshot 组合外键必须严格留在同一 Project 聚合内部。
3. **真实性分层**：`execution_mode` (demo_replay/live) 与 `source_mode` (fixture/live/cached) 分离，Fixture 不得伪造为 Cached。
4. **证据优先**：所有的核心数据、总结条目、关系与图谱边必须逐项追溯至合规的 `Evidence` 与 `SourceSnapshot`。
5. **版本锁定**：Evidence、ShareSnapshot 与 Export 严格锁定具体的 `version_id`，不依赖浮动的 `latest` 指针。

## 5. LiteratureClaim、LiteratureRelation 与 ReasoningTrace

- `literature_claims` ArtifactVersion 保存唯一的 typed Claim candidate。每个非 rejected Claim 固定一个已验证 PaperSummary ArtifactVersion，并通过持久化 Evidence 与 SourceSnapshot 形成完整 provenance。
- `literature_relations` ArtifactVersion 保存 Relation、双方 Claim 投影和可审查 ReasoningTrace。每个非 rejected Relation 必须精确固定 source/target Claim ArtifactVersion 与对应 PaperSummary ArtifactVersion。
- ReasoningTrace 不是独立 ArtifactVersion；它只公开 premise、结构化比较步骤、条件、限制、冲突、结论与 Evidence 引用。
- `graph_eligible` 是读取闭包结果，不是新的科学判定。只有 accepted Relation、accepted endpoints 与完整 Trace/Evidence/SourceSnapshot 同时成立时为真。
- ArtifactVersion 与 Evidence 在同一 Publisher 事务内原子创建。Pipeline Evidence/SourceSnapshot ID 保留在 locator 与 typed content 中，数据库 registry 保存对应 PostgreSQL UUID；两侧必须一一闭合且同属一个 Project。
