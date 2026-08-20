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

Application Service 从已确认 Contract 的 `output_requirements` 确定性编译最小前置依赖闭包，并创建冻结该有序 RunStep 集合的 `queued` Run。Executor 只消费已冻结的 RunStep，不重新推导、扩展或由模型生成第二份 Plan。每个 Step 内部由 Qwen Agent 对该 Step 唯一注册的服务端工具给出一次公开分析并触发执行；服务端校验工具身份与公开分析文本后执行工具并把 Observation 写入公开 Activity。模型不能选择未注册工具、改变冻结 Step 顺序、授予新来源、扩大预算或绕过 Artifact 准入。Pipeline 只返回 typed candidate，Publisher 在准入通过后原子发布 ArtifactVersion 并推进 Step。创建 Run 或初始 Event 不代表执行已经发生。

执行协调分两层：ResearchRunWorker 只负责 poll、lease、step loop、Attempt、bounded retry orchestration、Publisher 提交与终态转换；StepRuntime 是薄分发层，只把每个冻结 RunStep 派发给对应的专职 Step Service（数据、论文检索/总结、文献推理、图谱），科学语义唯一保存在 `services/` 各 Pipeline（含契约门控的实时数据获取与文献检索），共享的 ProducerExecution 发布生命周期由 step publication 层唯一关闭。Run 依赖闭包唯一 Owner 是冻结的 RunStep chain（RunPlan）；Worker 不持有第二份 Artifact dependency closure，Artifact 名称映射只服务用户可读标题，不决定依赖。

## 2. 状态机

```text
[*] -> queued -> planning
                   <-> waiting_for_input
    -> [fetching_data -> cleaning_data]
    -> [acquiring_observations -> analyzing_data -> training_models -> building_visualizations]
    -> [searching_papers -> summarizing_papers -> reasoning_literature]
    -> [building_graph] -> completed

queued / planning / fetching_data / cleaning_data / acquiring_observations /
analyzing_data / training_models / building_visualizations / searching_papers /
summarizing_papers / reasoning_literature / building_graph -> failed

queued / planning / waiting_for_input / fetching_data / cleaning_data /
acquiring_observations / analyzing_data / training_models /
building_visualizations / searching_papers / summarizing_papers /
reasoning_literature / building_graph -> cancelled
```

`waiting_for_input` 表示执行已停在明确的人工输入边界；`cancelled` 表示取消已持久化。`completed`、`failed` 与 `cancelled` 是终态。RunStep 的稳定状态为 `pending | running | waiting | completed | failed | cancelled | skipped`，StepAttempt 为 `running | completed | failed | cancelled`。没有真实状态写入时不得投影这些状态。

Planner 只有在持久化明确的输入请求后才能从 `planning` 进入 `waiting_for_input`，并在收到匹配输入后回到 `planning`。没有该 writer/command 时不得进入等待状态。

## 3. 顺序、重试与失败

- `planning` 始终是首 Step；其后只冻结 Contract 产物闭包需要的 canonical steps，并保持 canonical 相对顺序。canonical Step 的 key 等于状态名；每个 scientific task 使用独立稳定 key，同时保留 `task_id`、`skill_id` 与所属状态，同一科学阶段可顺序执行多个 task。每个 Step 的 `success_status` 必须精确指向冻结 Plan 的下一 Step 状态，末 Step 指向 `completed`。
- `dataset | field_dictionary | source_collection` 引入 `fetching_data -> cleaning_data`；每个 scientific task 由能力表唯一映射到 `acquiring_observations | analyzing_data | training_models | building_visualizations` 之一，需要 Dataset 前置条件且没有显式 `input_refs` 的任务同时引入数据闭包，已冻结显式输入的任务直接消费该输入，不重复抓取无关数据；`paper_collection` 引入 `searching_papers`；`paper_summary` 追加 `summarizing_papers`；Literature Claim/Relation/ReasoningTrace 追加完整文献检索、总结与 `reasoning_literature` 闭包；`graph` 追加完整文献闭包与 `building_graph`，仅当 Contract 同时请求数据产物时才包含数据闭包。
- 可执行 requested output 由 `SUPPORTED_RUN_OUTPUTS` 显式 allowlist 声明；新增 ArtifactKind 在获得明确 RunPlan mapping 前必须 fail closed，且不得创建 Run。不得使用枚举全集减例外的方式自动授予执行能力。
- RunStep 数据库约束只守住 status domain、唯一性与 position 等局部不变量；Contract-driven 子集链的冻结顺序与 next-step transition 由 Workflow Store 按唯一 `RUN_STEP_STATUS_ORDER` 验证，状态顺序只允许前进或在多个 scientific task 间保持同一阶段，不在数据库枚举所有 transition pair。前序 Step 未完成时不得启动后序 Step。
- StepAttempt 使用递增 `attempt_number`、稳定 idempotency key、错误分类与 retryable 标记记录实际尝试。
- 外部超时、限流或临时网络故障可在该 Step 的 `max_attempts` 内重试；Schema、权限与状态冲突等确定性失败不得重试。
- Artifact 级 Candidate 未通过 Schema、Evidence、质量或领域准入时不得发布 ArtifactVersion。Claim/Relation 的记录级 `candidate | rejected` 是已完成准入计算的事实，可保存在通过聚合完整性校验的 ArtifactVersion 中；这不等于将记录提升为 `accepted`，下游仍必须按记录状态执行自己的准入门禁。

## 4. 快照、事件与并发

- PostgreSQL 是 Run、Step、Attempt 与 Event 的唯一事实源。
- `GET /api/runs/{id}` 返回权威快照；RunEvent 仅用于按 `sequence` 恢复增量通知，且不得超过 `latest_event_sequence`。
- 状态写入使用 `expected_status + expected_revision` 条件更新。
- 同一 Run 只允许一个有效 lease；lease 绑定 token、owner、expiry 与递增 generation。
- RunEvent 是项目私有消息流的唯一增量事实：`activity_id` 标识一个逻辑操作，`activity_kind / activity_phase / activity_name / step_key / progress / content / details / artifact_version_ids / occurred_at` 表达分析、工具调用、Observation、重试、产物与终态。同一工具的运行、Observation 与产物提交必须使用同一个 `activity_id` 原位演化，不得写成开始/完成两条重复流水账。
- 每个服务端冻结 Step 只进行一次模型决策：模型通过唯一注册主工具的结构化参数生成简体中文公开分析（`public_analysis`），并选择该工具；主工具成功返回 Observation 后由服务端完成 Step，不再通过额外模型调用请求 `finish_step`。研究协议与前序产物作为任务上下文直接提供，不重复播报无独立决策价值的读取动作。
- `public_analysis` 以 `reasoning` Activity 持久化；模型响应前先写同一 `activity_id` 的运行态，结构化参数验证通过后原位更新为完成态。Provider 私有 `reasoning_content` 不进入 RunEvent、Research Thread、ShareSnapshot、Export 或正式 Artifact Renderer。ReasoningTrace 仍是证据绑定的正式产物，与步骤级公开分析是两个边界。
- 工具 Activity 只记录注册工具的稳定名称、经过领域过滤的参数、来源与结果摘要；凭据、原始传输响应和内部错误堆栈不得写入 RunEvent。

## 4.1 消息边界

四类公开消息边界严格分离：

| 边界                | 语义                                   |
| ------------------- | -------------------------------------- |
| Assistant Message   | 面向用户的正常研究叙事，写入 Thread    |
| Reasoning Activity  | 公开的简短步骤分析（`public_analysis`）|
| Tool Activity       | 执行事实                               |
| ReasoningTrace      | Evidence-bound 正式科学推导 Artifact   |

Provider private chain-of-thought 永不进入上述任一路径。

Run 的关键语义节点可以写 Assistant Message：run started、major step
started、meaningful validated result、recoverable issue、result published、
completed / cancelled / failed。不按每一个内部函数调用写 Assistant Message。

模型决策只产生执行前的 `public_analysis`：为什么现在执行、将检查什么、如何
判断该步骤完成。主工具 schema 不包含任何执行后结果文案；Step 执行成功后的
Assistant Message 由服务端基于真实已验证完成结果（`result.public_message`
或 validated result）构造并写入 Thread，不为结果文案额外调用模型，也不得在
执行前预测科研结果。

## 4.2 waiting_for_input、取消、重试与修订闭环

- `waiting_for_input` 使用同一 Run 等待人工输入。Checkpoint 由 `RunCheckpoint`（run、step_key、question、options、created_at）与 `RunCheckpointDecision`（selected_option、可空 free_text、decided_at）持久化；Decision 不可变，提交后原子恢复同一 Run 到合法可执行状态，不创建新 Run、新 Contract 或第二套 review runtime。Checkpoint 的通用生命周期属于 Workspace 基础：等待表现、持久化读取、不可变决策、同 Run 恢复与共享 Choice 交互原语由通用运行时唯一提供；具体科学触发时机、科学问题与选项内容以及决策对科学执行的影响由科学能力集成通过同一机制接入，不得另建第二套 checkpoint 运行时。
- 同一 Project 同时最多一个 non-terminal ResearchRun（服务端规则，不由前端按钮保证）：唯一 Workflow Store writer 先锁定对应 Project 聚合根行，在同一事务中重放幂等请求并完成 active Run 准入；Application Service 返回用户友好 `409`，PostgreSQL partial unique index 保留为最终并发围栏。Retry / Revision 派生创建时，父 Run 必须已处于允许派生的稳定状态。
- 取消必须以条件写入将 Run、未完成 Step 与运行中的 Attempt 一致推进为 `cancelled`，追加单调 Event，并拒绝取消后的晚到产物。重复取消终态 Run 保持幂等。已发布 ArtifactVersion、Thread、Event 与 Evidence 保留。
- 自动 retry 只处理受治理的瞬时失败（bounded retry），耗尽后才对用户可见；人工 retry 沿用 retry derivation（`parent_run_id`、`derivation_kind=retry`、`retry_from_step`），只从真实 retryable failed step 建立，保留历史 Attempt，不原地覆盖失败尝试，不修改原 Run history。
- Revision 由 UserFeedback 与已确认 RevisionPlan 驱动，确认后才产生 revision Run；运行中修改请求不静默修改当前 Run。

## 5. 派生 Run 与修订

派生关系是稳定运行时契约；当前 HTTP authoring 支持 original Run、由已确认 RevisionPlan 创建的 revision Run 与由失败边界派生的 retry Run，CacheSelector 是内部失败回退能力。尚未接入的 fork、自动 cache fallback 与 cached publication writer 不得伪造对应记录。

- `parent_run_id` 固定派生来源；`derivation_kind` 只允许 `original | retry | revision | fork`。
- `retry_from_step` 只对 retry Run 有效；Executor 不能从该 Step 恢复时必须拒绝创建，不得从首 Step 静默重跑。
- Revision Run 由 UserFeedback 与已确认 RevisionPlan 约束。确认事务锁定 Plan，重新校验 completed parent Run revision 和全部 frozen latest 指针，再通过唯一 Workflow Store writer 创建 Run、RunStep 与初始 Event；并发或重复确认只产生一个 Run。
- revision Run 的冻结 Step 从 `planning` 开始；其余 Step 只能由 frozen recompute ArtifactVersion decisions 的 `step_key` 确定性投影，并保持全局相对顺序。不存在受影响发布目标、超出父 Contract canonical closure 或来自其他 Run 的 current ArtifactVersion 不得制造 Step。未受影响 ArtifactVersion 以 reuse identity 记录。后续执行仍复用既有 Executor、Pipeline 与原子 Publisher，新 ArtifactVersion 通过 `supersedes_version_id` 与 ProducerExecution 形成 lineage。
- Fork Run 使用新的 Contract；复用父 Run 产物时必须重新验证 input hash、Contract 与 Evidence。

## 6. CacheSelector 与取消

CacheRecordStore 只从 completed Live Run 的已发布 `source_mode=live` ArtifactVersion 注册不可变候选，并重新闭合 Contract、input、producer/Prompt、SourceSnapshot identity hash、Evidence、数据质量投影与 UTC validity window。Fixture、cached/recorded、未完成 origin、无 SourceSnapshot/Evidence 或越出 Contract source scope 的候选不得注册。

`cache_policy=disabled` 禁止选择缓存；`fallback_on_recoverable_failure` 只允许在 Run、RunStep 与 Attempt 已持久化 failed，Attempt 明确 `retryable=true`，且调用方提供属于该 Attempt 的 failed ProducerExecution identity 后运行 CacheSelector。Schema、权限、非法状态、非 recoverable failure 或伪造 ProducerExecution 在查询候选前 fail closed。

Selector 在 failed Run 行锁事务中逐项匹配 artifact kind、Contract/input hash、producer/Prompt、来源范围、质量约束、Evidence 要求、有效期及当前 provenance closure。命中只引用 CacheRecord 的 origin Run/ArtifactVersion；拒绝保存稳定原因。两者都保留原 `run.failed`，追加 `cache.selected | cache.rejected` Event 与不可变 CacheSelectionAudit，不改变 failed/origin Run 状态，不发布 ArtifactVersion。`(run_step_id, request_hash)` 唯一约束与 Run 行锁保证并发 replay 不重复审计或发布。

CacheSelector 是当前 PostgreSQL Application/Workflow 内部能力，但当前 HTTP authoring 与 Executor 自动 fallback 尚未暴露；将选择结果发布为 `source_mode=cached` 仍必须经过未来显式接入的 Publisher 路径，不能由 Selector 建立第二发布边界。

## 7. Research assistant 与 Run 读取边界

Research assistant 在 Run 创建前通过 `ModelExecutionPort` 生成公开 Planner outcome。它可以创建或更新 Draft、追加 Thread entry，不能创建 Run 或 Artifact；只有人类确认 Contract 后才能进入既有 Run 状态机。`clarification_required`、`partial`、`unsupported` 与 `refused` 不能静默提升为可执行 Draft。

Planner 的 capability catalog 必须同时声明全部可选成果与当前可执行成果。模型只能把用户明确请求且可执行的成果写入 Draft；明确请求但当前没有受治理执行闭包的成果必须返回 `partial | unsupported`。人工修改后仍可能形成不可执行 Contract，Run 创建边界继续 fail closed，且不得创建 fake RunStep。

`GET /api/runs/{run_id}/steps` 是 RunStep 的只读投影，显示真实 `pending | running | waiting | completed | failed | cancelled | skipped` 状态与顺序。它不产生 Executor、Attempt、lease、Pipeline 或 Publisher 行为。

## 8. HTTP authoring 边界

`POST /api/projects/{project_id}/runs` 只接受 `contract_id` 与 `execution_mode`，从该 confirmed Contract 冻结确定性 RunStep Plan，并创建 `derivation_kind=original`、`cache_policy=disabled` 的 Run。Feedback、RevisionPlan 与确认分别使用独立资源端点，不能把修订字段塞入 original Run 请求。

Run 生命周期命令只暴露有真实执行闭环的窄端点，Route 不实现 workflow algorithm：

- `POST /api/runs/{run_id}/cancel`：条件状态写入，未完成 Step 与运行中 Attempt 一致 cancelled，追加单调 Event，拒绝 late publish，重复取消幂等。
- `POST /api/runs/{run_id}/retry`：Application Service 验证 Run failed、存在 retryable failed step 与合法 `retry_from_step` 后创建明确 derived Run，不复活/覆盖 failed Attempt，不静默从头全跑。
- `GET /api/runs/{run_id}/checkpoint` 与 `POST /api/runs/{run_id}/checkpoint-decision`：读取当前等待中的 Checkpoint；提交 Decision 原子写入不可变记录并将同一 Run 从 `waiting_for_input` 恢复到合法可执行状态。重复相同 Decision 按既有 idempotency convention 幂等或明确 conflict。

缓存选择没有公开 authoring 命令；额外字段由请求 Schema 拒绝。
