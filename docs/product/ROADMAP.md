# Roadmap

## 里程碑总览

| 里程碑 | 对应优先级 | 目标 | 退出标准 |
| --- | --- | --- | --- |
| M0 文档基建 | — | 文档、协作、保护规则、任务池就绪 | 新成员能按文档开始开发 |
| M1 开发基线 | P0 | Docker Compose + Web 页面 + FastAPI + Mock 数据 + CI/契约/工作流基建 | 三服务可启动，Mock 工作流可展示，CI 拦截构建与契约漂移 |
| M2 核心功能 | P1 | 数据主链路 + 论文获取与文献总结 + 跨文献推理与学术图谱 | 真实数据、论文、推理和图谱均绑定 Evidence |
| M3 反馈与交付 | P2 | 版本/实验治理、缓存兜底、反馈修正、公网 Demo、材料交接 | 演示稳定，历史结果可定位，材料可复现 |

GitHub Milestones 与 Priority 标签严格 1:1 对应：P0 全部归入 M1，P1 全部归入 M2，P2 全部归入 M3。`milestone:*` 标签不再单独使用。

## M0：仓库基础

| 产出 | 负责人 | 状态 |
| --- | --- | --- |
| README、PRD、DESIGN、AGENTS | 开发负责人 | 已建立，持续维护 |
| API、数据模型、模块边界 | B 主导，全员确认 | 已建立，M1 前冻结初版 |
| Workflow、模型/Prompt、版本与测试基线 | B + X | Phase 0 建立，后续按 Issue 落地 |
| Roadmap、Backlog、Acceptance | 开发负责人 | 已建立 |
| GitHub 分支保护、PR 模板、Issue 模板 | 开发负责人 | 已建立 |

## M1：开发基线（P0）

M1 先做 `X-00` 和 `X-04`。C/D 在 M1 不需要完成完整数据链路、论文获取和推理链路，但必须给出最小真实依据，供 Schema、Mock API 和页面结构使用。A 优先跑通 Web 端页面和 Mock 闭环，B 同步交付 FastAPI、Mock API、显式状态机和可导出 Schema；`X-05` 建立机器校验。

| 产出 | 负责人 | 验收 |
| --- | --- | --- |
| MVP 最小真实依据 | A + B + C + D | 字段清单、论文来源、检索词、seed、关系类型已冻结 |
| Docker Compose 本地基线 | A + B | `web`、`api`、`postgres` 可启动，浏览器 API 地址与 CORS 正确 |
| Web 项目骨架 | A | Vue 3 + TypeScript + Vite + pnpm 可启动/构建 |
| FastAPI 项目骨架 | B | Python 3.13 + uv + FastAPI 可启动，基础接口可用 |
| Workflow 骨架 | B | 状态转换集中校验，Executor 与数据库/Pipeline 解耦 |
| CI 与依赖漂移卡口 | A + B | foundation、frozen install、build、pytest、Schema export、Compose config |
| 共享 Schema 初版 | B | Pydantic 单一编写源，可导出 JSON Schema |
| Prompt/模型治理基线 | B + D | Prompt registry、模型输出准入与证据规则明确 |
| Mock 任务流程 | A + B | 页面可展示完整 Mock 工作流 |
| 本地启动文档 | A + B | 新成员 30 分钟内可通过 Docker 跑起来 |

## M2：核心功能（P1）

M2 包含三个子阶段，按依赖关系串行推进，但同一子阶段内 A/B/C/D 可并行。阶段级验收 Issue 为 `X-06` 和 `X-07`。

### M2.1 数据主链路

| 产出 | 负责人 | 验收 |
| --- | --- | --- |
| 主数据源查询 | C | 至少 1 个真实天文数据源可查询 |
| 第二来源或补充来源 | C | 支撑多源与来源对比 |
| 字段映射规则 | C | 关键字段有单位、来源和规则版本 |
| 数据质量评分 | C + B | API 返回质量指标 |
| CSV / 数据字典 / 溯源报告 | C + B | 前端可下载，产物可计算 hash |

### M2.2 论文获取与文献总结（X-06）

| 产出 | 负责人 | 验收 |
| --- | --- | --- |
| 论文获取来源与检索策略 | D | 主案例内可复现，不依赖手写列表冒充自动获取 |
| PaperAcquisition Pipeline | D | 返回 Query、Run、Candidate 与 SourceSnapshot |
| PaperAcquisition API | B + D | 前端可展示检索参数、候选、去重、排序 |
| 总结 Prompt 与 JSON Schema | D + B | 版本化 Prompt，输出稳定通过校验 |
| PaperSummary API | B + D | 前端可展示结构化结果 |
| 文献来源与证据 | D | 每条核心结论绑定 paper/source/evidence |

### M2.3 跨文献推理与学术图谱（X-07）

| 产出 | 负责人 | 验收 |
| --- | --- | --- |
| LiteratureClaim | D | 从多篇论文抽取目标、方法、数据、发现、局限 |
| LiteratureRelation | D | 支持核心关系类型，候选与最终关系分离 |
| ReasoningTrace | D + B | 每条最终关系有 trace 和 evidence |
| Reasoning API | B + D | `/literature-reasoning` 返回结构化结果 |
| Graph JSON | D | 节点、边、证据、推理关系符合契约 |
| 图谱页面 | A | Vue Flow 可点击，详情和推理链可查看 |
| 证据详情接口 | B + D | 点击边或节点可看到来源依据 |
| 图谱展示优化 | A + D | 适合答辩截图和录屏 |

## M3：反馈与交付（P2，X-08）

| 产出 | 负责人 | 验收 |
| --- | --- | --- |
| ArtifactVersion / ExperimentRun | B + D | 关键产物和模型运行可定位版本 |
| 反馈入口 | A | 用户可提交字段、来源、文献、推理问题 |
| 局部修正接口 | B + C + D | 修正产生新版本并保留记录 |
| 缓存兜底 | B | 外部失败时完整演示，缓存绑定来源和版本 |
| 公网 Demo | A + B | 可访问、可演示、生产配置安全 |
| 材料交接包 | 全员 | 截图、导出文件、说明和版本定位齐全 |

## 阶段门控

- `X-06`：数据与论文主链路不能依赖手写结果冒充实时能力。
- `X-07`：无 Evidence/Trace 的 Relation 不进入最终图谱。
- `X-08`：缓存、修正和材料必须绑定真实运行与明确版本。
- 阶段 Issue 只负责集成验收，不替代 A/B/C/D 原子任务。

## 节奏建议

- M1 先完成工作流、契约导出、CI 和安全配置，再扩大真实 Pipeline。
- Web-first 不等于脱离契约；fixtures 必须通过同一 Schema。
- Docker-first 不等于引入复杂中间件；M1 只保留三服务。
- M2 是核心差异化能力，不能降级为后续扩展。
- 自动论文获取优先做主案例内可运行闭环，开放式全文解析后置。
- 跨文献推理共用 Evidence、Relation 和 ReasoningTrace。
- M3 能力从 M2 预留 hash/version 字段，但不提前引入 Redis、Neo4j 或向量库。
