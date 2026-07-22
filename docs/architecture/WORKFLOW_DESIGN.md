# Research Workflow Design

| 项目状态 | 口径 |
| --- | --- |
| Status | Accepted |
| Authority | Run 状态、事件、取消、重试、缓存与派生语义 |
| Implementation | #76 PostgreSQL baseline、#77 lease/fencing/recovery store、#78 ArtifactVersion atomic publisher 与 M1 v2 Run/Event Runtime Implemented；生产 Pipeline wiring Pending |
| Current runtime | v1 Phase 0 状态机与 `/api/v2` M1 PersistentWorkflowStore Application |
| Target runtime | Project / Run / ArtifactVersion 工作流 |

本文定义 ResearchRun 编排、事件、取消、重试、缓存、修订与派生语义。当前 v1 Executor、Hooks 与测试继续作为兼容基线；M1 v2 Run 创建/读取与 Event 读取已接入 PersistentWorkflowStore，但数据库 Hooks、真实 Pipeline、对外取消资源、CacheSelector 与自动执行仍为 Pending。

## 1. 职责边界

工作流负责：

- Run 与 RunStep 状态转换；
- Step 排序、输入产物校验和输出登记；
- StepAttempt、RunEvent、失败和取消记录；
- 幂等、自动重试、真实缓存选择和派生 Run 入口；
- ArtifactVersion 的发布协调。

工作流不负责：天文清洗规则、论文检索策略、Prompt 内容、Claim/Relation 算法、图谱布局、HTTP DTO 或前端状态。

```text
routers
  -> application services
      -> workflow executor
          -> step adapters
              -> data / paper / reasoning / graph pipelines

workflow executor
  -> RunRepository / ArtifactRepository / EventSink ports
      -> PostgreSQL / observability adapters
```

Router 不串联 Pipeline；Pipeline 不推进 Run 主状态；浏览器不编排后端步骤。

## 2. Run 状态机

```mermaid
stateDiagram-v2
  [*] --> queued
  queued --> planning
  planning --> fetching_data
  fetching_data --> cleaning_data
  cleaning_data --> searching_papers
  searching_papers --> summarizing_papers
  summarizing_papers --> reasoning_literature
  reasoning_literature --> building_graph
  building_graph --> completed

  planning --> waiting_for_input
  waiting_for_input --> planning

  queued --> cancelled
  planning --> cancelled
  fetching_data --> cancelled
  cleaning_data --> cancelled
  searching_papers --> cancelled
  summarizing_papers --> cancelled
  reasoning_literature --> cancelled
  building_graph --> cancelled
  waiting_for_input --> cancelled

  queued --> failed
  planning --> failed
  fetching_data --> failed
  cleaning_data --> failed
  searching_papers --> failed
  summarizing_papers --> failed
  reasoning_literature --> failed
  building_graph --> failed
  waiting_for_input --> failed

  completed --> [*]
  failed --> [*]
  cancelled --> [*]
```

`cached`、`fixture`、修订关系和 `using_cache` 不属于状态。目标 v2 不在原 Run 中使用 `revising -> completed`；人工修订创建新的 `derivation_kind=revision` Run。

## 3. Step 契约

每个 Step 声明：

| 字段 | 含义 |
| --- | --- |
| `key` | 稳定机器标识 |
| `enter_status` | 开始时要求和设置的 Run 状态 |
| `success_status` | 完成后的下一状态 |
| `input_kinds` | 必需 ArtifactKind 与 Schema 版本 |
| `output_kinds` | 可发布 ArtifactKind |
| `idempotency_key` | run + step + input hash + producer version |
| `retry_policy` | 可重试错误、次数与退避 |
| `run(context)` | 只调用对应 Port / Pipeline Adapter |

Step 输出先通过 Schema、Evidence 和质量约束，再登记 ArtifactVersion。模型自由文本不得直接成为完成产物。

## 4. 进度快照与事件

- `GET /runs/{id}` 返回可恢复的权威快照。
- RunEvent 使用 `(run_id, sequence)` 单调有序，支持 cursor polling 或 SSE。
- Event 只包含公开状态、进度、步骤、产物引用和可执行提示，不包含 chain-of-thought。
- 客户端丢失事件后重新拉取 Snapshot，再从 `latest_event_sequence` 继续。
- 进度不得倒退；未知工作量时使用阶段状态，不伪造百分比。

## 5. 持久化与并发

PostgreSQL 是 Run、Step、Attempt、ArtifactVersion 和 Event 的事实来源。更新使用条件写入：

```text
expected_status + expected_revision -> target_status + new_revision
```

同一 Run 只允许一个 Executor lease。有效 lease 保存 token、owner、数据库时间 expires_at 和单调 generation；acquire 与状态事务递增 revision，heartbeat 只续期 expires_at，不使执行中的 Attempt revision 失效；超时接管递增 generation 并返回仍为 running 的 Attempt，接管者必须先登记其失败或恢复结论。旧 token 或 generation、过期 lease、旧 revision 和终态 Run 的后续提交全部拒绝。

`create_run` 使用 PostgreSQL 原子 conflict handling 保证并发 Idempotency-Key 语义，验证完整规范状态链，并在数据库层冻结 Step 集合与转换定义。`begin_step` 在持有 ResearchRun 行锁的短事务中校验冻结顺序，条件更新 Run/Step，追加 StepAttempt，并从 Run 的 `latest_event_sequence` 分配下一 Event。可重试失败保留旧 Attempt 并把 Step 恢复为 pending；耗尽重试、不可重试失败和取消在单个事务内更新 Attempt、Step、Run 与 Event。Snapshot 使用单个 PostgreSQL repeatable-read/read-only 事务，并从 `latest_event_sequence` 提供 Event cursor 恢复。

#78 Publisher 已在固定 `ResearchRun -> RunStep -> ResearchArtifact（id 排序）` 锁顺序下，将产物登记、latest、Attempt、Step、Run 与完成 Event 放入同一 fenced 事务，避免出现 completed 却找不到产物的快照。外部模型、数据源和算法调用仍在事务外执行，ProducerExecution 开始、结束和产物发布分别使用短事务。

MVP 可继续使用 FastAPI BackgroundTasks，但不得以进程内字典作为唯一事实来源。只有真实负载证明需要时才通过 ADR 引入队列。

## 6. 幂等与自动重试

- 创建 Live Run 要求 `Idempotency-Key`；同一 key 与同一请求返回同一 Run。
- 外部读取和模型调用以 input hash、producer version、source scope 组成幂等键。
- 超时、限流和临时网络错误可自动重试；Schema、Evidence、权限和非法状态错误不可自动重试。
- 每次自动重试创建 StepAttempt，保留 attempt、时间、上游 request id 和错误分类。
- 重试不得覆盖失败 Attempt，也不得重复发布相同 ArtifactVersion。

当前 D-02 Paper Adapter 在 Pipeline 边界内执行有界 HTTP request retry，并把 page attempt count、SourceExecution retry count 与错误分类返回给调用方；它不写 Run/Step/Attempt 或推进状态。B-06/Workflow 接入时必须把 Pipeline 返回的执行证据登记到所属 StepAttempt，且不得因 Pipeline 已重试而省略工作流审计。

## 7. 用户重试与派生 Run

终态 Run 不恢复为 running。用户动作创建新 Run：

| `derivation_kind` | 语义 | 复用规则 |
| --- | --- | --- |
| `retry` | 从失败步骤重新执行 | 可复用父 Run 中通过 hash 和 Contract 校验的完成版本 |
| `revision` | 应用 Feedback / RevisionPlan | 只重算受影响步骤，生成新 ArtifactVersion |
| `fork` | 更换 Contract 或研究范围 | 只有新 Contract 允许且输入 hash 一致的版本可复用 |

新 Run 必须保存 `parent_run_id`、原因、复用版本和新生成版本；历史 Run 保持终态。

## 8. 取消语义

- `POST /runs/{id}/cancellations` 创建幂等取消请求。
- queued / waiting Run 可立即 cancelled；运行中 Run 使用 best-effort 协作取消。
- 已发出的外部请求可能完成，但取消确认后的输出不得自动发布为 latest。
- 取消保留已完成且可审查的 ArtifactVersion，UI 明确标记来自 cancelled Run。
- completed / failed / cancelled 重复取消返回当前终态，不伪造状态转换。

## 9. Cache 选择

只有同时满足以下条件才能使用真实缓存：

1. Live 执行发生明确且可恢复的外部失败；
2. CacheRecord 指向真实历史 Run、ArtifactVersion 与 SourceSnapshot；
3. Contract、input hash、producer / prompt version 和适用范围匹配；
4. Evidence 与质量约束仍满足；
5. RunEvent、ArtifactVersion 与页面明确记录缓存选择和本次失败。

Fixture 永远不进入 CacheSelector。缓存不适用时 Run 失败，并向用户提供可执行下一步。

## 10. 修订与版本发布

```text
UserFeedback
-> RevisionPlan
-> 人工确认
-> revision ResearchRun
-> 受影响 Step
-> 新 ArtifactVersion
-> 可选更新 Artifact.latest_version_id
```

GraphEdge 修订若影响 Relation、ReasoningTrace 或 Evidence，RevisionPlan 必须包含完整影响闭包。版本发布前验证 Evidence、SourceSnapshot、content hash 与 supersedes chain。

## 11. 失败和公开错误

- 内部异常转换为稳定 error code、公开摘要和 request/run/step context。
- 公开 API 不返回堆栈、密钥、连接串、受限全文或原始模型长输出。
- 非法状态跳转立即 409，不做“尽量继续”。
- 上游返回不可校验结构时记录 `UPSTREAM_INVALID_RESPONSE`，不得把自由文本降级为科研事实。
- `waiting_for_input` 只用于确实需要用户选择的安全边界，不用于掩盖未知错误。

## 12. 当前 v1 与目标 v2

当前已实现：显式 v1 状态转换表与 WorkflowHooks；#77 PostgreSQL Workflow Store 的 create/acquire/heartbeat/begin/retry/fail/cancel/snapshot 边界；按 Step 调用 Adapter 的 `PersistentWorkflowExecutor`；以及 #78 ProducerExecution Store、结构化 candidate 准入端口和 ArtifactVersion Publisher。Executor 在 `begin_step` 事务提交后调用外部 Adapter，并可把成功提交委托给 Publisher 注入端口；持久化路径默认由 `PERSISTENT_WORKFLOW_ENABLED=false` 保持关闭，v1 Executor 与 `/api/v1` 不切换实现。

当前 v1 `ResearchTask` 快照同时校验顶层状态、进度和 Step 状态：初始 `pending` 快照不得包含已开始 Step，含 `running` Step 的快照不得为 `pending`，`completed` 快照的进度必须为 100。

当前已实现 #76 的 PostgreSQL Schema、Alembic migration 和最小 Repository / Unit of Work 基线，#77 的 lease、条件状态事务、Attempt 自动重试账本、失败/取消、Event cursor 与一致性 Snapshot，#78 的 ProducerExecution 账本、ArtifactVersion 原子发布与 Step/Run 成功推进，以及 M1 v2 Run/Event Application。仍待实现：对外取消资源、真实 CacheSelector、各 Pipeline 的生产接线与自动执行。

迁移期间 v1 `ResearchTask` 可适配为一个 Project + 一个 Run，但 v2 语义不得回写破坏现有接口。

## 13. 验收门禁

- 状态转换、并发 lease、幂等、取消、自动重试和派生 Run 均有单元/集成测试。
- Event 丢失恢复、SSE 断线和 Snapshot 一致性有测试。
- Run 状态、`execution_mode`、`source_mode` 与修订派生关系分别有 Contract 测试，且不会混作同一枚举。
- RevisionPlan 只重算影响闭包，旧版本保持可读。
- Graph 发布验证全部 Evidence，跨文献边验证 Relation / Trace。
- 权限、CSRF、匿名配额和跨会话访问在应用服务层验证。
