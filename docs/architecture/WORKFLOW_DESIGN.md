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

Application Service 创建冻结了 canonical steps 的 `queued` Run。Executor 持有 fenced lease，按顺序启动 StepAttempt；Pipeline 只返回 typed candidate，Publisher 在准入通过后原子发布 ArtifactVersion 并推进 Step。创建 Run 或初始 Event 不代表执行已经发生。

## 2. 状态机

```text
[*] -> queued -> planning -> fetching_data -> cleaning_data
                   <-> waiting_for_input
    -> searching_papers -> summarizing_papers -> reasoning_literature
    -> building_graph -> completed

queued / planning / fetching_data / cleaning_data / searching_papers /
summarizing_papers / reasoning_literature / building_graph -> failed

queued / planning / waiting_for_input / fetching_data / cleaning_data /
searching_papers / summarizing_papers / reasoning_literature /
building_graph -> cancelled
```

`waiting_for_input` 表示执行已停在明确的人工输入边界；`cancelled` 表示取消已持久化。`completed`、`failed` 与 `cancelled` 是终态。RunStep 的稳定状态为 `pending | running | waiting | completed | failed | cancelled | skipped`，StepAttempt 为 `running | completed | failed | cancelled`。没有真实状态写入时不得投影这些状态。

Planner 只有在持久化明确的输入请求后才能从 `planning` 进入 `waiting_for_input`，并在收到匹配输入后回到 `planning`。没有该 writer/command 时不得进入等待状态。

## 3. 顺序、重试与失败

- RunStep 的 `enter_status` 与 `success_status` 必须符合 canonical transition；前序 Step 未完成时不得启动后序 Step。
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

以下派生、修订与缓存条目定义稳定目标契约；当前 HTTP authoring 只创建 original、cache-disabled Run，未接入的 writer 不得伪造对应记录。

- `parent_run_id` 固定派生来源；`derivation_kind` 只允许 `original | retry | revision | fork`。
- `retry_from_step` 只对 retry Run 有效；Executor 不能从该 Step 恢复时必须拒绝创建，不得从首 Step 静默重跑。
- Revision Run 由 UserFeedback 与已确认 RevisionPlan 约束，只重算受影响闭包并发布新的 ArtifactVersion。
- Fork Run 使用新的 Contract；复用父 Run 产物时必须重新验证 input hash、Contract 与 Evidence。

## 6. CacheSelector 与取消

目标 CacheSelector 负责从真实历史 Run 中选择满足 Contract、input hash、producer identity 与 Evidence 约束的 CacheRecord。只有选择成功并绑定 origin Run/ArtifactVersion 时才能写入 `source_mode=cached`；Fixture 不得进入选择结果。

`cache_policy=disabled` 禁止选择缓存；`fallback_on_recoverable_failure` 只允许在 Live 调用发生可恢复失败后运行 CacheSelector，选择失败时保留原失败事实。

取消必须以条件写入将 Run、未完成 Step 与运行中的 Attempt 一致推进为 `cancelled`，追加单调 Event，并拒绝取消后的晚到产物。重复取消终态 Run 保持幂等。

## 7. HTTP authoring 边界

`POST /api/projects/{project_id}/runs` 只接受 `contract_id` 与 `execution_mode`，创建 `derivation_kind=original`、`cache_policy=disabled` 的 Run。派生、选择性 retry、反馈修订、缓存选择与取消没有对应公开命令；额外字段由请求 Schema 拒绝，防止调用者误以为能力已经执行。
