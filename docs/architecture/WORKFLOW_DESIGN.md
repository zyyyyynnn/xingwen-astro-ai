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

每个受控 `ScientificTaskInput` 必须展开为独立 RunStep。该 Step 持久绑定稳定 `task_id`、`skill_id`、所属 phase 与 `depends_on_step_keys`；phase 只投影 Run 的公开工作阶段，不能作为合并多个任务、共享 Attempt 或共享重试预算的执行桶。

## 2. 状态机

```text
[*] -> queued -> planning
                   -> waiting_for_input -> cancelled
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

只有服务端受审计错误分类才能打开 Human Checkpoint；当前明确分类为文档总结 Step 缺少受支持的 PDF、Markdown 或纯文本输入。writer 在同一事务内把 Attempt 记为失败、Step 记为 `waiting`、Run 记为 `waiting_for_input`，冻结输入类型要求、释放 lease 并追加 `step.waiting_for_input` Event。任意异常文本、客户端字段或模型输出不得直接创建 Checkpoint。

## 3. 顺序、重试与失败

- `planning` 始终是首 Step；其后只冻结 Contract 产物闭包需要的 canonical steps，并保持 phase 的 canonical 相对顺序。同一 phase 可包含多个 task-owned RunStep。每个 Step 的 `depends_on_step_keys` 固定实际前置依赖，`success_status` 精确指向冻结 Plan 下一 Step 的 phase，末 Step 指向 `completed`。
- `dataset | field_dictionary | source_collection` 引入 `fetching_data -> cleaning_data`；`paper_collection` 引入 `searching_papers`；`paper_summary` 追加 `summarizing_papers`；Literature Claim/Relation/ReasoningTrace 追加完整文献检索、总结与 `reasoning_literature` 闭包；`graph` 追加完整文献闭包与 `building_graph`，仅当 Contract 同时请求数据产物时才包含数据闭包。
- 可执行 requested output 由 `SUPPORTED_RUN_OUTPUTS` 显式 allowlist 声明；新增 ArtifactKind 在获得明确 RunPlan mapping 前必须 fail closed，且不得创建 Run。不得使用枚举全集减例外的方式自动授予执行能力。
- RunStep 数据库约束守住 status domain、唯一性、position、task/skill 成对绑定与冻结定义；Contract-driven 子集链的 phase 顺序、显式依赖和 next-step transition 由 Workflow Store 按唯一 `RUN_STEP_STATUS_ORDER` 验证，不在数据库枚举所有 transition pair。依赖 Step 未完成时不得启动当前 Step。
- StepAttempt 使用递增 `attempt_number`、稳定 idempotency key、错误分类与 retryable 标记记录实际尝试。
- 外部超时、限流或临时网络故障可在该 Step 的 `max_attempts` 内重试；Schema、权限与状态冲突等确定性失败不得重试。
- Candidate 未通过 Schema、Evidence、质量或领域准入时不得发布 ArtifactVersion。

## 4. 快照、事件与并发

- PostgreSQL 是 Run、Step、Attempt 与 Event 的唯一事实源。
- `GET /api/runs/{id}` 返回权威快照；RunEvent 仅用于按 `sequence` 恢复增量通知，且不得超过 `latest_event_sequence`。
- 状态写入使用 `expected_status + expected_revision` 条件更新。
- 同一 Run 只允许一个有效 lease；lease 绑定 token、owner、expiry 与递增 generation。
- Run 内 bounded Function Calling 必须在 provider 调用前创建绑定当前
  StepAttempt 与 lease generation 的 ProducerExecution。同一 idempotency key 只能恢复
  同一完整终态 decision；不完整或不同 generation 的记录 fail closed，不重复
  调用 provider。校验拒绝只封存唯一、非空且有界的 tool call ID 及其 arguments
  hash；零个、多个或无效 call identity 不得伪造身份，且任何路径都不得保存原始
  arguments。
- Event 只包含公开进度、错误摘要与产物引用，不包含模型私有思维过程。

### 4.1 队列准入与执行容量

- `live` Run 创建使用 PostgreSQL transaction advisory lock 串行化容量判定与写入；
  同一事务先解析 Idempotency-Key replay，再检查 global 与 Project 级 Live
  nonterminal 总量及其中的 `queued` 上限。达到任一上限返回
  `429 RUN_QUEUE_CAPACITY_EXCEEDED` 与稳定
  `Retry-After`，且不创建 Run、RunStep 或 Event。`demo_replay` 不进入 Live 队列。
- 每个 Live queued Run 在创建时持久化 `queue_expires_at`。过期且没有有效 lease
  的 Run 原子进入 `failed / RUN_QUEUE_TIMEOUT`，首个未开始 Step 记为 failed、其余
  未开始 Step 记为 cancelled，并追加唯一 `run.failed` Event；不得在内存计时器中
  伪造超时。过期回收由 Worker poll 与后续 admission 共同触发，所以所有 Worker
  停止时允许延迟执行，但下一次触发必须收敛到相同终态。
- lease acquisition 在同一 PostgreSQL 容量锁内检查 global 与 Project 级有效 Live
  lease 数，作为跨进程 active capacity 的最终门禁。进程本地并发数只能进一步收紧，
  不能绕过数据库门禁；不引入 Redis、Kafka 或第二套队列事实源。
- runnable 选择每轮只提供每个 Project 最早的候选 Run，并按持久化
  `workflow_project_dispatches.last_dispatched_at` 排序。成功取得 lease 时原子推进
  Project dispatch cursor，因此持续提交的单个 Project 不能让其他 Project 饥饿。

### 4.2 Worker lifecycle 与 draining

- `workflow_workers` 持久化 `accepting | draining | stopped`、配置容量、启动、心跳、
  drain request 与停止时间；进程布尔值不是 lifecycle 事实源。
- `draining` Worker 不再领取新 Run。drain 前已经开始的 StepAttempt 允许完成其
  commit/failure transaction；完成后若 Run 仍非终态，Worker 释放 lease 并停止，
  后续 Worker 从冻结的下一个 pending Step 继续。不得为缩短关停而取消一个仍在
  正常执行的 Attempt。
- Worker shutdown 先持久化 draining，等待受控外部调用和子进程的既有超时预算
  收敛，再持久化 stopped。`/api/health` 的 workflow worker 投影读取该持久状态与
  当前有效 lease 数；API liveness 不因 draining 变为失败。

## 5. 派生 Run 与修订

以下派生、修订与缓存条目定义稳定目标契约；当前 HTTP authoring 只创建 original、cache-disabled Run，未接入的 writer 不得伪造对应记录。

- `parent_run_id` 固定派生来源；`derivation_kind` 只允许 `original | retry | revision | fork`。RunDecision 是不可变审计记录，固定 parent/child、decision、精确 Step、补充 ResearchInput id、请求 hash 与 Idempotency-Key。
- `retry_from_step` 只对 retry Run 有效。resume 只能解析 open Checkpoint 且必须提供同 Project、同 Session、未过期、已接受并满足冻结类型要求的 ResearchInput；retry 只能选择 failed Step，且其最后 Attempt 必须标记为可修复。派生 Run 复制冻结 Step 定义，把目标 Step 之前的 Step 标记为 `skipped`，从 `retry_from_step` 精确执行受影响后缀；不得从首 Step 静默重跑。
- resume 创建派生 Run 后，原 `waiting_for_input` Run 以 `cancelled` 终结并追加 `run.superseded`，Checkpoint 绑定 resolution Run；这表示原执行被派生执行取代，不改写其已完成 Step、Attempt、ArtifactVersion 或 Event。retry 不改变已为 `failed` 的 parent Run。
- Revision Run 由 UserFeedback 与已确认 RevisionPlan 约束，只重算受影响闭包并发布新的 ArtifactVersion。
- Fork Run 使用新的 Contract；复用父 Run 产物时必须重新验证 input hash、Contract 与 Evidence。

## 6. CacheSelector 与取消

目标 CacheSelector 负责从真实历史 Run 中选择满足 Contract、input hash、producer identity 与 Evidence 约束的 CacheRecord。只有选择成功并绑定 origin Run/ArtifactVersion 时才能写入 `source_mode=cached`；Fixture 不得进入选择结果。

`cache_policy=disabled` 禁止选择缓存；`fallback_on_recoverable_failure` 只允许在 Live 调用发生可恢复失败后运行 CacheSelector，选择失败时保留原失败事实。

取消必须以条件写入将 Run、未完成 Step 与运行中的 Attempt 一致推进为 `cancelled`，追加单调 Event，并拒绝取消后的晚到产物。重复取消终态 Run 保持幂等。

## 7. Research assistant 与 Run 读取边界

Research assistant 在 Run 创建前通过 `ModelExecutionPort` 生成公开 Planner outcome。它可以创建或更新 Draft、追加 Thread entry，不能创建 Run 或 Artifact；只有人类确认 Contract 后才能进入既有 Run 状态机。`clarification_required`、`partial`、`unsupported` 与 `refused` 不能静默提升为可执行 Draft。

Planner 的 capability catalog 必须同时声明全部可选成果与当前可执行成果。模型只能把用户明确请求且可执行的成果写入 Draft；明确请求但当前没有受治理执行闭包的成果必须返回 `partial | unsupported`。人工修改后仍可能形成不可执行 Contract，Run 创建边界继续 fail closed，且不得创建 fake RunStep。

`GET /api/runs/{run_id}/steps` 是 RunStep 的只读投影，显示真实 `pending | running | waiting | completed | failed | cancelled | skipped` 状态与顺序。它不产生 Executor、Attempt、lease、Pipeline 或 Publisher 行为。

## 8. HTTP authoring 边界

`POST /api/projects/{project_id}/runs` 只接受 `contract_id` 与 `execution_mode`，从该 confirmed Contract 冻结确定性 RunStep Plan，并创建 `derivation_kind=original`、`cache_policy=disabled` 的 Run。

`GET /api/runs/{run_id}/checkpoint` 读取该 Run 的权威 Checkpoint。`POST /api/runs/{run_id}/decisions` 接受严格判别的 `resume | retry | cancel`，同时要求 `If-Match` 与 `Idempotency-Key`；resume/retry 原子创建并返回派生 Run，cancel 原子终结 open Checkpoint Run。幂等 replay 返回同一 Decision 与同一结果 Run；同 key 不同 payload、stale revision、跨 ownership、输入类型不匹配或不可修复 Step 均 fail closed。反馈修订与缓存选择仍没有公开命令。

task-owned Step 的架构决定见 [Scientific task-owned RunStep decision](decisions/scientific-task-owned-run-steps.md)。
