# Research Workflow Design

| 元数据    | 值                                                              |
| --------- | --------------------------------------------------------------- |
| Authority | Run 状态机、派生关系、Step、Attempt、事件、取消、缓存与并发控制 |

本文定义 ResearchRun 的稳定生命周期与执行不变量。数据规则、Prompt、科学准入与前端状态由各自 Authority 管理。

## 1. 执行边界

```text
Router -> Application Service -> Persistent Workflow Executor
       -> Step Adapter -> Pipeline -> Publisher
```

Application Service 从已确认 Contract 的 `output_requirements` 确定性编译最小前置依赖闭包，并创建冻结该有序 RunStep 集合的 `queued` Run。Executor 只消费已冻结的 RunStep，不重新推导、扩展或由模型生成第二份 Plan。Pipeline 只返回 typed candidate，Publisher 在准入通过后原子发布 ArtifactVersion 并推进 Step。创建 Run 或初始 Event 不代表执行已经发生。

## 2. 状态机

```text
[*] -> queued -> planning
                   <-> waiting_for_input
    -> [fetching_data -> cleaning_data]
    -> [searching_papers -> summarizing_papers -> reasoning_literature]
    -> [building_graph] -> completed

queued / planning / fetching_data / cleaning_data / searching_papers /
summarizing_papers / reasoning_literature / building_graph -> failed

queued / planning / waiting_for_input / fetching_data / cleaning_data /
searching_papers / summarizing_papers / reasoning_literature /
building_graph -> cancelled
```

`waiting_for_input` 表示执行已停在明确的人工输入边界；`cancelled` 表示取消已持久化。`completed`、`failed` 与 `cancelled` 是终态。RunStep 的稳定状态为 `pending | running | waiting | completed | failed | cancelled | skipped`，StepAttempt 为 `running | completed | failed | cancelled`。没有真实状态写入时不得投影这些状态。

Planner 只有在持久化明确的输入请求后才能从 `planning` 进入 `waiting_for_input`，并在收到匹配输入后回到 `planning`。没有该 writer/command 时不得进入等待状态。

## 3. 顺序、重试与失败

- `planning` 始终是首 Step；其后只冻结 Contract 产物闭包需要的 canonical steps，并保持 canonical 相对顺序。每个 Step 的 `success_status` 必须精确指向冻结 Plan 的下一 Step，末 Step 指向 `completed`。
- `dataset | field_dictionary | source_collection` 引入 `fetching_data -> cleaning_data`；`paper_collection` 引入 `searching_papers`；`paper_summary` 追加 `summarizing_papers`；Literature Claim/Relation/ReasoningTrace 追加完整文献检索、总结与 `reasoning_literature` 闭包；`graph` 追加完整文献闭包与 `building_graph`，仅当 Contract 同时请求数据产物时才包含数据闭包。
- 可执行 requested output 由 `SUPPORTED_RUN_OUTPUTS` 显式 allowlist 声明；新增 ArtifactKind 在获得明确 RunPlan mapping 前必须 fail closed，且不得创建 Run。不得使用枚举全集减例外的方式自动授予执行能力。
- RunStep 数据库约束只守住 status domain、唯一性与 position 等局部不变量；Contract-driven 子集链的冻结顺序与 next-step transition 由 Workflow Store 按唯一 `RUN_STEP_STATUS_ORDER` 验证，不在数据库枚举所有 transition pair。前序 Step 未完成时不得启动后序 Step。
- StepAttempt 使用递增 `attempt_number`、稳定 idempotency key、错误分类与 retryable 标记记录实际尝试。
- 外部超时、限流或临时网络故障可在该 Step 的 `max_attempts` 内重试；Schema、权限与状态冲突等确定性失败不得重试。
- Candidate 未通过 Schema、Evidence、质量或领域准入时不得发布 ArtifactVersion。

## 4. 快照、事件与并发

- PostgreSQL 是 Run、Step、Attempt 与 Event 的唯一事实源。
- `GET /api/runs/{id}` 返回权威快照；RunEvent 仅用于按 `sequence` 恢复增量通知，且不得超过 `latest_event_sequence`。
- 状态写入使用 `expected_status + expected_revision` 条件更新。
- 同一 Run 只允许一个有效 lease；lease 绑定 token、owner、expiry 与递增 generation。
- Event 只包含公开进度、错误摘要与产物引用，不包含模型私有思维过程。

## 5. 派生 Run 与修订

以下派生与修订条目定义稳定目标契约；当前 HTTP authoring 只创建 original、cache-disabled Run，未接入的 writer 不得伪造对应记录。

- `parent_run_id` 固定派生来源；`derivation_kind` 只允许 `original | retry | revision | fork`。
- `retry_from_step` 只对 retry Run 有效；Executor 不能从该 Step 恢复时必须拒绝创建，不得从首 Step 静默重跑。
- Revision Run 由 UserFeedback 与已确认 RevisionPlan 约束，只重算受影响闭包并发布新的 ArtifactVersion。
- Fork Run 使用新的 Contract；复用父 Run 产物时必须重新验证 input hash、Contract 与 Evidence。

## 6. CacheSelector 与取消

CacheRecordStore 只从 completed Live Run 的已发布 `source_mode=live` ArtifactVersion 注册不可变候选，并重新闭合 Contract、input、producer/Prompt、SourceSnapshot identity hash、Evidence、数据质量投影与 UTC validity window。Fixture、cached/recorded、未完成 origin、无 SourceSnapshot/Evidence 或越出 Contract source scope 的候选不得注册。

`cache_policy=disabled` 禁止选择缓存；`fallback_on_recoverable_failure` 只允许在 Run、RunStep 与 Attempt 已持久化 failed，Attempt 明确 `retryable=true`，且调用方提供属于该 Attempt 的 failed ProducerExecution identity 后运行 CacheSelector。Schema、权限、非法状态、非 recoverable failure 或伪造 ProducerExecution 在查询候选前 fail closed。

Selector 在 failed Run 行锁事务中逐项匹配 artifact kind、Contract/input hash、producer/Prompt、来源范围、质量约束、Evidence 要求、有效期及当前 provenance closure。命中只引用 CacheRecord 的 origin Run/ArtifactVersion；拒绝保存稳定原因。两者都保留原 `run.failed`，追加 `cache.selected | cache.rejected` Event 与不可变 CacheSelectionAudit，不改变 failed/origin Run 状态，不发布 ArtifactVersion。`(run_step_id, request_hash)` 唯一约束与 Run 行锁保证并发 replay 不重复审计或发布。

CacheSelector 是当前 PostgreSQL Application/Workflow 内部能力，但当前 HTTP authoring 与 Executor 自动 fallback 尚未暴露；将选择结果发布为 `source_mode=cached` 仍必须经过未来显式接入的 Publisher 路径，不能由 Selector 建立第二发布边界。

取消必须以条件写入将 Run、未完成 Step 与运行中的 Attempt 一致推进为 `cancelled`，追加单调 Event，并拒绝取消后的晚到产物。重复取消终态 Run 保持幂等。

## 7. Research assistant 与 Run 读取边界

Research assistant 在 Run 创建前通过 `ModelExecutionPort` 生成公开 Planner outcome。它可以创建或更新 Draft、追加 Thread entry，不能创建 Run 或 Artifact；只有人类确认 Contract 后才能进入既有 Run 状态机。`clarification_required`、`partial`、`unsupported` 与 `refused` 不能静默提升为可执行 Draft。

Planner 的 capability catalog 必须同时声明全部可选成果与当前可执行成果。模型只能把用户明确请求且可执行的成果写入 Draft；明确请求但当前没有受治理执行闭包的成果必须返回 `partial | unsupported`。人工修改后仍可能形成不可执行 Contract，Run 创建边界继续 fail closed，且不得创建 fake RunStep。

`GET /api/runs/{run_id}/steps` 是 RunStep 的只读投影，显示真实 `pending | running | waiting | completed | failed | cancelled | skipped` 状态与顺序。它不产生 Executor、Attempt、lease、Pipeline 或 Publisher 行为。

## 8. HTTP authoring 边界

`POST /api/projects/{project_id}/runs` 只接受 `contract_id` 与 `execution_mode`，从该 confirmed Contract 冻结确定性 RunStep Plan，并创建 `derivation_kind=original`、`cache_policy=disabled` 的 Run。派生、选择性 retry、反馈修订、缓存选择与取消没有对应公开命令；额外字段由请求 Schema 拒绝，防止调用者误以为能力已经执行。
