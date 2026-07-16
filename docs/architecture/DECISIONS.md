# Architecture Decisions

## ADR-001：MVP 固定主案例

| 状态 | Accepted |
| --- | --- |

MVP 固定为“系外行星候选体与宿主恒星参数整合”。

原因：主案例越稳定，越容易形成真实数据、论文获取、文献总结、跨文献推理、证据图谱和演示闭环。任意天文方向支持后置。

## ADR-002：核心功能串成一条科研工作流

| 状态 | Accepted |
| --- | --- |

自动化数据分析、自动论文获取、智能文献总结、跨文献逻辑推理和学术图谱可视化围绕同一个 `ResearchTask` 串联，不做孤立功能页。

原因：比赛评审更关注完整科研支撑能力，而不是功能堆叠。

## ADR-003：模型调用统一走后端

| 状态 | Accepted |
| --- | --- |

所有 Qwen / 百炼调用必须经过后端 Qwen Client。

原因：保护 API Key，统一超时、重试、缓存、日志和 JSON Schema 校验。

## ADR-004：模块间统一结构化契约

| 状态 | Accepted |
| --- | --- |

前端、后端、数据、文献、推理、图谱模块共享 `API_CONTRACT.md` 和 `DATA_MODEL.md`。

原因：允许 4 人并行开发，减少联调时字段漂移。

## ADR-005：公网 Demo 必须有真实运行缓存兜底

| 状态 | Accepted |
| --- | --- |

外部数据源、论文源或模型失败时，Demo 可展示最近一次真实运行缓存，并明确标注缓存状态。

原因：保证演示稳定，同时不把手写假数据包装成真实结果。

## ADR-006：图谱边必须绑定证据

| 状态 | Accepted |
| --- | --- |

GraphEdge 必须包含 `evidence_ids`。跨文献关系边还必须包含 `relation_id` 和 `reasoning_trace_id`。

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

原因：比赛评审关注“可溯源”时，不只看有没有来源链接，还会看证据能否定位到字段、文本、查询、论文获取记录或缓存版本。

## ADR-009：P0 先对齐最小真实依据，再并行推进

| 状态 | Accepted |
| --- | --- |

P0 第一步是 `X-00`：冻结 MVP 字段清单、论文获取来源、检索关键词、5-8 篇 seed list、跨文献关系类型和 Graph 最小关系类型。随后先完成 `X-04` Docker Compose 本地开发基线，再让 A/B 并行初始化前后端，C/D 提供最小真实依据。

原因：纯 Mock 会削弱科研可信度；完全串行又会拖慢开发节奏；没有统一 Docker 基线会造成成员本机依赖和版本漂移。

## ADR-010：自动论文获取纳入 MVP 主链路

| 状态 | Accepted |
| --- | --- |

MVP 必须在固定主案例内实现自动论文获取，输出 `PaperSearchQuery`、`PaperAcquisitionRun` 和 `PaperCandidate`。seed list 只能作为兜底、评测基准和人工校验。

原因：自动论文获取是“智能文献总结”的前置核心能力，不能只依赖手写文献清单冒充系统能力。

## ADR-011：跨文献逻辑推理必须结构化

| 状态 | Accepted |
| --- | --- |

跨文献逻辑推理必须落到 `LiteratureClaim`、`LiteratureRelation` 和 `ReasoningTrace`，并绑定 `Evidence`。无证据关系只能作为候选，不进入最终图谱。

原因：“逻辑推理”如果只输出自然语言解释，无法审查、无法复现，也无法支撑答辩中的可信性追问。

## ADR-012：Web-first 与 shadcn-vue 优先

| 状态 | Accepted |
| --- | --- |

前端先完成 `apps/web` 页面、路由、状态、Mock 工作流和 UI token 落地。UI 组件优先采用 shadcn-vue / reka-ui 体系，图谱主库采用 Vue Flow，统计图表按需使用 ECharts。

原因：先形成可演示 Web 闭环，再抽象复用组件，能降低早期不确定性；成熟组件库能减少基础控件成本，同时保持视觉一致性。

## ADR-013：Docker-first 本地开发基线

| 状态 | Accepted |
| --- | --- |

M1 本地环境统一使用 Docker Compose 管理 `web`、`api`、`postgres` 三个服务，固定 `node:24-alpine`、`python:3.13-slim`、`postgres:17-alpine`。

原因：4 人团队设备和本机依赖不一致，Docker Compose 可以把运行时、网络、端口和数据库版本固定为同一基线。

## ADR-014：依赖管理工具固定

| 状态 | Accepted |
| --- | --- |

前端统一使用 pnpm，后端统一使用 uv。提交 `pnpm-lock.yaml` 和 `uv.lock`；禁止混用 npm/yarn/bun lockfile 或用 requirements.txt 替代 uv 主流程。

原因：pnpm 更适合 Web-first 和后续 workspace；uv 统一 Python 版本、依赖和 lockfile。两者配合 Docker 能降低“本机可运行、他人不可运行”的风险。

## ADR-015：Celery / Redis 后置

| 状态 | Accepted |
| --- | --- |

M1 不引入 Redis、Celery、RabbitMQ。任务链路先用 FastAPI、数据库任务状态和 BackgroundTasks 支撑；当论文获取、模型调用或图谱构建耗时明显影响稳定性时，再评估 Redis + Celery/RQ。

原因：MVP 任务规模可控，过早引入任务队列会增加部署、调试和成员协作成本。

## ADR-016：工作流必须由显式状态机驱动

| 状态 | Accepted |
| --- | --- |

`ResearchTask` 的状态转换由 `app.workflow` 集中声明和校验。Router 不直接串联多个 Pipeline，Pipeline 不自行推进任务状态。

原因：把编排散落在 Router/Service 会导致非法跳转、失败记录丢失、缓存语义混乱和巨型业务文件。

## ADR-017：Pydantic 是 Phase 0 Schema authoring source

| 状态 | Accepted |
| --- | --- |

Phase 0 以 `apps/api/src/app/schemas` 作为契约编写源，通过 `scripts/export_schemas.py` 导出 JSON Schema 到 `packages/schemas` 或临时构建目录。前端和 Pipeline 不维护第二套同名字段。

原因：当前 Pydantic 模型已经存在，立即搬迁会制造双写和回归风险；先建立可重复导出，再按实际 codegen 需求评估独立 IDL。

## ADR-018：Prompt 文件不可变版本化

| 状态 | Accepted |
| --- | --- |

生产 Prompt 统一放在 `packages/prompts/<name>/vN.md`，由 registry 指定默认版本。已被真实运行或缓存引用的版本不原地改写。

原因：Prompt 是科研结果的生成条件，散落字符串和“最新版本”无法复现，也会造成缓存结果口径失真。

## ADR-019：科研产物采用追加式版本治理

| 状态 | Accepted |
| --- | --- |

Dataset、Summary、Claim、Trace、Graph 和 Export 的修正通过新 ArtifactVersion 表达；模型/算法运行通过 ExperimentRun 表达。Phase 0 先冻结契约，Phase 1–3 分步落库。

原因：只保存当前结果无法解释历史截图、模型升级差异、缓存来源和用户修正。

## ADR-020：MVP 暂不引入通用图数据库与万能实体层

| 状态 | Accepted |
| --- | --- |

MVP 继续使用 PostgreSQL/JSON 与现有 GraphNode/GraphEdge 契约。只有当真实图规模、查询模式或跨案例复用证明需要时，才评估 Neo4j、通用 Entity/Relation 或向量数据库。

原因：当前风险是可信闭环未跑通，而不是图存储性能。过早抽象会增加迁移和联调成本。
