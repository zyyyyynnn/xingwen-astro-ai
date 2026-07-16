# Research Workflow Design

本文定义 `ResearchTask` 的编排边界。业务实体与字段见 `DATA_MODEL.md`，HTTP 接口见 `API_CONTRACT.md`，状态转换的可执行基线见 `apps/api/src/app/workflow/`。

## 1. 目标

工作流层只负责：

- 任务状态转换；
- Pipeline 步骤排序；
- 步骤开始、完成、失败记录；
- 产物登记；
- 重试、缓存和幂等策略的统一入口；
- 失败信息向统一错误结构转换。

工作流层不负责：

- 天文数据清洗规则；
- 论文检索策略；
- Prompt 业务内容；
- Claim/Relation 算法；
- 图谱布局；
- HTTP 展示模型拼装。

## 2. 依赖方向

```text
routers
  -> application services
      -> workflow executor
          -> step adapters
              -> services/data_pipeline
              -> services/paper_pipeline
              -> services/graph_pipeline

workflow executor
  -> WorkflowHooks protocol
      -> persistence / observability adapter
```

禁止 Router 直接串联多个 Pipeline，也禁止 Pipeline 反向调用 Router 或前端。

## 3. 主状态机

```text
pending
  -> planning
  -> fetching_data
  -> cleaning_data
  -> searching_papers
  -> summarizing_papers
  -> reasoning_literature
  -> building_graph
  -> completed
  -> revising
  -> completed
```

所有非终态步骤都可进入 `failed`。`failed` 默认是终态；恢复必须创建显式重试/修复动作，不允许静默改回运行态。

`using_cache` 不是任务状态。缓存命中只通过 `used_cache`、`meta.cached`、`SourceRecord.cached` 和缓存记录表达。

## 4. Step 契约

每个 Step 必须声明：

| 字段 | 含义 |
| --- | --- |
| `key` | 稳定机器标识，对齐 TaskStep |
| `label` | 用户可读名称 |
| `enter_status` | 进入步骤时的任务状态 |
| `success_status` | 步骤成功后的任务状态 |
| `run(context)` | 仅调用对应 Pipeline/Adapter |
| 输入 | 上一步已校验产物与任务上下文 |
| 输出 | 可持久化、可验证的 artifacts 映射 |

Step 不得直接修改下一步骤内部数据，也不得返回未校验模型文本作为最终产物。

## 5. 持久化边界

Phase 0 使用 `WorkflowHooks` Protocol 隔离执行器与数据库。真实实现至少需要：

- 乐观条件更新：`expected_status -> target_status`；
- TaskStep 状态与时间戳；
- 产物 ID/版本登记；
- `request_id`、`task_id`、`step_key` 关联；
- 错误码与可公开错误信息；
- 缓存来源元信息。

不得只在进程内保存主任务状态。`BackgroundTasks` 可用于 MVP 执行，但 PostgreSQL 是状态事实来源。

## 6. 幂等与重试

每个真实 Step 在进入 Phase 1 前必须定义：

- 幂等键：通常由 `task_id + step_key + input_hash + version` 组成；
- 可重试错误：超时、限流、临时网络错误；
- 不可重试错误：Schema 错误、证据缺失、非法状态转换；
- 最大尝试次数与退避；
- 重试是否复用已完成产物；
- 外部写操作的重复保护。

重试不能覆盖原始失败记录。每次尝试应保留 attempt、时间、错误类型和来源。

## 7. 缓存策略

缓存只在以下条件下作为兜底：

1. 实时执行发生明确可恢复失败；
2. 缓存来自真实历史运行；
3. 输入、来源、Prompt/模型版本与适用范围可识别；
4. 响应和页面明确标注 cached；
5. 证据链仍可定位。

缓存命中后任务可完成，但必须设置 `used_cache=true`，并保留实时失败与缓存选择原因。

## 8. 失败处理

- Step 抛出的内部异常由执行器包装为带 task/step 上下文的错误。
- 公开 API 不返回堆栈、密钥、数据库连接串或过长模型输出。
- Step 失败先记录 TaskStep，再将 ResearchTask 转为 `failed`。
- 非法状态跳转必须立即拒绝，不做“尽量继续”。
- 局部修正使用 `revising`，不重跑无关步骤。

## 9. Phase 0 交付

已建立：

- 显式状态转换表；
- 无数据库依赖的 Workflow Executor；
- WorkflowHooks 持久化协议；
- 状态机单元测试；
- 后续 Pipeline Adapter 的固定落点。

尚未实现：

- 数据库 WorkflowHooks；
- BackgroundTasks/队列执行适配；
- 真实 Pipeline Step；
- 自动重试与缓存选择器；
- ExperimentRun/ArtifactVersion 落库。

这些内容由后续 Phase Issues 验收，不能在材料中写成已实现。
