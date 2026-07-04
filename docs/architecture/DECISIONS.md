# Architecture Decisions

## ADR-001：MVP 固定主案例

| 状态 | Accepted |
| --- | --- |

MVP 固定为“系外行星候选体与宿主恒星参数整合”。

原因：主案例越稳定，越容易形成真实数据、文献总结、证据图谱和演示闭环。任意天文方向支持后置。

## ADR-002：三大功能串成一条科研工作流

| 状态 | Accepted |
| --- | --- |

自动化数据分析、智能文献总结、学术图谱可视化围绕同一个 `ResearchTask` 串联，不做三个孤立功能页。

原因：比赛评审更关注完整科研支撑能力，而不是功能堆叠。

## ADR-003：模型调用统一走后端

| 状态 | Accepted |
| --- | --- |

所有 Qwen / 百炼调用必须经过后端 Qwen Client。

原因：保护 API Key，统一超时、重试、缓存、日志和 JSON Schema 校验。

## ADR-004：模块间统一结构化契约

| 状态 | Accepted |
| --- | --- |

前端、后端、数据、文献、图谱模块共享 `API_CONTRACT.md` 和 `DATA_MODEL.md`。

原因：允许 4 人并行开发，减少联调时字段漂移。

## ADR-005：公网 Demo 必须有真实运行缓存兜底

| 状态 | Accepted |
| --- | --- |

外部数据源或模型失败时，Demo 可展示最近一次真实运行缓存，并明确标注缓存状态。

原因：保证演示稳定，同时不把手写假数据包装成真实结果。

## ADR-006：图谱边必须绑定证据

| 状态 | Accepted |
| --- | --- |

GraphEdge 必须包含 `evidence_ids`。

原因：图谱是科研证据组织能力，不是装饰性可视化。

## ADR-007：缓存是元信息，不是主任务状态

| 状态 | Accepted |
| --- | --- |

缓存命中通过 `meta.cached`、`ResearchTask.used_cache`、`SourceRecord.cached` 和页面提示表达，不再使用 `using_cache` 作为 `task_status`。

原因：任务状态描述流程阶段，缓存描述结果来源。两者混用会让前端状态流、验收截图和后端状态机都变复杂。

## ADR-008：Evidence 必须可定位、可核验、可复现

| 状态 | Accepted |
| --- | --- |

`Evidence` 除 `source_id` / `paper_id` 外，还需要记录 `locator`、`quote_or_value`、`extraction_method` 和 `source_snapshot`。

原因：比赛评审关注“可溯源”时，不只看有没有来源链接，还会看证据能否定位到字段、文本、查询或缓存版本。

## ADR-009：P0 先对齐最小真实依据，再并行推进

| 状态 | Accepted |
| --- | --- |

P0 第一步是 `X-00`：冻结 MVP 字段清单、5-8 篇文献清单和 Graph 最小关系类型。随后 A/B 并行初始化前后端，C/D 提供最小真实依据。

原因：纯 Mock 会削弱科研可信度；完全串行又会拖慢开发节奏。
