# Scientific task-owned RunStep

## Context

ResearchContract 已把科学能力冻结为具有稳定 `task_id`、`skill_id`、参数和输入引用的 `ScientificTaskInput`。原执行设计却按 phase 把多个任务聚合进一个 RunStep，由一次 Attempt 顺序执行整个任务组。这会让重型和轻型任务共享 lease、timeout、retry 与发布边界；任一任务失败会迫使已完成任务重跑，也无法准确表达 task 级取消、预算、审计和恢复。

## Decision

- `planning` 与数据、文献、推理等 canonical pipeline Step 保持既有职责。
- 每个 ScientificTask 编译为一个独立 RunStep；RunStep 持久保存 task identity、skill identity、phase 和前置 Step key。
- Run 状态继续使用稳定 phase，以维持公开状态机；同一 phase 允许连续出现多个 task-owned RunStep。
- ScientificStepAdapter 只接受一个 task identity，并且只执行该任务。
- ScientificStepPublisher 在发布前同时核对 active RunStep、frozen Contract 与输出的 task/skill identity；该任务的 Artifact、Evidence、SourceSnapshot 和 ProducerExecution 作为一个 fenced 输出闭包提交。
- 当前 Executor 仍串行消费冻结依赖链。未来若引入并行调度，必须消费同一 `depends_on_step_keys`，不得再推导第二份 Plan。

## Consequences

- task 级 Attempt、retry、cancel、预算、错误与进度拥有唯一事实来源。
- 同一 phase 的任务可以独立重试，已成功任务无需重复执行。
- RunStep key 不再等同于 phase；读取 DTO 和前端 ViewModel 必须同时暴露 `key`、`phase`、`task_id`、`skill_id` 与依赖。
- 数据库冻结规则必须覆盖新增定义字段，防止 Run 创建后替换任务或依赖。
- 生产 Worker 必须按 RunStep 绑定选择 Adapter，不能按 phase 扫描并执行 Contract 中的全部任务。
