# Research Workflow Design

| 元数据 | 值 |
| --- | --- |
| Status | Accepted |
| Authority | Run 状态机、事件、取消、重试、缓存与派生运行语义 |

本文定义系统的 ResearchRun 工作流编排、状态机、事件推送、取消、重试、缓存与派生运行规范。

## 1. 职责边界

- **工作流负责**：Run 与 RunStep 状态转换、Step 执行顺序校验、StepAttempt 与 RunEvent 记录、幂等键与取消控制、真实缓存选择以及 ArtifactVersion 发布协调。
- **工作流不负责**：数据清洗规则、论文检索策略、Prompt 内容、推理算法、图谱布局或前端状态。

```text
Routers -> Application Services -> Workflow Executor -> Step Adapters -> Pipelines
```

Router 不直接调用 Pipeline；Pipeline 不直接推进 Run 主状态。

真实 ResearchRun 只能由这一条 Workflow Executor 路径驱动：它取得 fenced lease，
按 Run/Step Contract 调用 Step Adapter，提交 Attempt/Event，接收 typed candidate，
再交给 Publisher。创建 `queued` Run 或写入初始 Event 不代表执行已经发生；没有
实际 Executor/Adapter 运行证据时，状态必须保持真实的 queued/failed 语义，不能生成
伪造 running、tool 或 artifact event。

## 2. Run 状态机

```text
[*] -> queued -> planning -> fetching_data -> cleaning_data
    -> searching_papers -> summarizing_papers -> reasoning_literature
    -> building_graph -> completed

queued / planning / fetching_data / ... -> failed
queued / planning / fetching_data / ... -> cancelled
planning <-> waiting_for_input
```

- 终态为 `completed`、`failed`、`cancelled`。终态 Run 不得重新变为 running。
- `cached`、`fixture`、`demo_replay` 与修订派生关系不属于 Run 状态。人工修订创建 `derivation_kind=revision` 的新 Run。

## 3. Step 契约与执行

每个 RunStep 包含：`key` (稳定标识)、`enter_status` (前置状态)、`success_status` (后置状态)、`input_kinds`、`output_kinds`、`idempotency_key` (run + step + input_hash + producer_version) 与 `retry_policy`。

- Step 输出先通过 Schema、Evidence 与质量校验，再由 Publisher 登记为不可变的 ArtifactVersion。
- 校验失败的中间结果记入失败诊断，模型自由文本不得直接成为完成产物。

## 4. 进度与事件 (RunEvent)

- `GET /runs/{id}` 提供权威的状态快照；Feed 首次读取必须先取快照，再按序读取事件。
- `RunEvent` 包含 `run_id`、单调递增 `sequence`、`step_key`、`progress` (0–100) 与 `occurred_at`。
- Event 仅包含公开状态与进度，不包含模型私有思维过程。客户端丢失事件时拉取最新快照并从 `latest_event_sequence` 恢复；Polling 使用有界 backoff，SSE 不是状态事实源。

## 5. 持久化与并发不变量

- PostgreSQL 是 Run、Step、Attempt 与 Event 的唯一权威事实源。
- 状态更新采用条件写入 (`expected_status + expected_revision -> target_status + new_revision`)。
- 同一 Run 仅允许一个 Executor Lease。Lease 包含 token、owner、expires_at 与递增 generation。接管或超期需强行竞争锁。
- Publisher 在单个原子事务内完成 ArtifactVersion 登记、latest 指针更新与 Run/Step 终态确认。

## 6. 幂等与自动重试

- 创建 Live Run 要求 `Idempotency-Key`。
- 外部超时、限流与临时网络波动可由 StepAttempt 自动重试（记录 `attempt_number`、时间与错误码）。
- 业务 Schema 校验失败、权限错误、非法状态冲突等判定性失败不得自动重试。

## 7. 用户重试与派生 Run (Derived Run)

用户操作通过创建新 Run 落地，并记录 `parent_run_id`：

| `derivation_kind` | 语义 | 复用规则 |
| --- | --- | --- |
| `retry` | 从失败步骤重新执行 | 可引用父 Run 中已通过校验且 Input Hash 一致的 ArtifactVersion |
| `revision` | 依据 UserFeedback / RevisionPlan 修订 | 仅重算受影响步骤，生成新 ArtifactVersion |
| `fork` | 更换 Contract 或研究范围 | 仅当新 Contract 允许且输入 Hash 一致时可引用父 Run 的 ArtifactVersion |

## 8. 取消语义

- `POST /runs/{id}/cancellations` 发起取消请求。
- queued / waiting 状态可立即取消；running 状态执行协作式取消。
- 已完成的步骤与产物保留并可追溯，明确标记属于已取消的 Run。
- 终态 Run 重复取消保持幂等，不引发非法状态跳转。

## 9. 缓存选择 (CacheSelector)

仅在同时满足以下条件时启用缓存 (`source_mode=cached`)：
1. Live 运行发生可恢复的外部失败；
2. CacheRecord 关联真实历史 Run、ArtifactVersion 与 SourceSnapshot；
3. Contract、Input Hash 与 Producer Version 完全匹配；
4. 约束与 Evidence 要求仍满足；
5. Event 与产物明确标记为 Cached 及原失败原因。

Fixture 绝对不进入 CacheSelector。
