# Phase 0 Project Brief

| 元数据 | 值 |
| --- | --- |
| Status | Archived |
| Period | 2026-06 to early 2026-07 |
| Authority | Historical record only |
| Superseded by | `PRD.md`, `DESIGN.md`, Roadmap, Module Boundaries and current Issues |

本文保留初始申报与 Phase 0 运行基线。人员、价格、服务器、技术栈、Issue 数量和截止状态均可能已变化，不得作为当前实现依据。

## 申报快照

- 题目编号：XH-202619
- 选题：赛道二 · 方向一 · A — 科学数据查找、解析与整合
- 初始申报名称：星文智研：以 AI 之光，点亮每一次“星”征途
- 记录时报名状态：已通过校团委与发榜单位审核
- 记录时提交截止日期：2026-09-05
- 应用领域：天文学
- 主案例：系外行星候选体与宿主恒星参数整合

## 初始团队分工快照

| 岗位 | 当时负责范围 |
| --- | --- |
| A 前端与产品流程 | `apps/web`、Vue 页面、状态、API Client、UI token |
| B 后端与任务编排 | `apps/api`、Schema、状态机、模型 Client、缓存、导出 |
| C 数据分析与数据源 | `services/data_pipeline`、字段、来源、清洗、单位、质量、导出 |
| D 论文、推理与图谱 | `services/paper_pipeline`、`services/graph_pipeline`、论文、Relation、Graph |

当前职责与目标目录以 [Module Boundaries](../architecture/MODULES.md) 和 GitHub Issues 为准。

## Phase 0 技术基线快照

| 层级 | 当时口径 |
| --- | --- |
| 开发方式 | Web-first、Docker-first、Contract-first |
| 前端 | Node.js 24、pnpm、Vue 3、TypeScript、Vite、shadcn-vue、Tailwind、Pinia、Vue Router、Vue Flow |
| 后端 | FastAPI、Python 3.13、Pydantic v2、uv、SQLAlchemy、Alembic、httpx |
| 数据库 | PostgreSQL 17 |
| 本地环境 | Docker Compose：web + api + postgres |
| 模型 | Qwen 系列，通过阿里云百炼平台调用 |

该前端目标已被 ADR-021 取代。当前运行和目标架构分别见 [README](../../README.md) 与 [Frontend Architecture](../architecture/FRONTEND_ARCHITECTURE.md)。

## 初始资源与预算快照

当时计划使用团队已有服务器和赛题相关模型额度，另记录过开发工具订阅预算。该信息具有强时效性，任何采购、额度或部署决策必须重新核验，不得从本文直接执行。

## 参考资料串联设想

初始方案将 InnoSum、AutoAstro 和 mavis 作为论文解析、数据整合和可视化方面的参考。参考资料现存于 `docs/references/`，但仅为非规范性输入；实际实现必须遵循当前 Contract、Evidence、Security 和 Model Policy。

## 初始阶段划分

- P0：骨架、Docker、Schema、Fixture 与 CI；
- P1：真实数据、论文、总结、推理和图谱；
- P2：版本、缓存、反馈、部署与材料。

当前阶段结果和依赖以 [Roadmap](../product/ROADMAP.md)、[Backlog](../product/BACKLOG.md) 和 GitHub Issues 为准。

## 历史红线

Phase 0 已提出并继续有效的原则包括：前端不直连模型或外部来源；密钥只在后端或 Secrets；模型输出必须结构化校验；关键产物绑定 Evidence；Seed 不冒充自动获取；缓存不冒充实时结果；未实现能力不得写成已实现。

这些原则的当前权威正文分别位于 Security、Model Policy、Data Versioning、PRD 和 AGENTS。