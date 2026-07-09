# Roadmap

## 里程碑总览

| 阶段 | 目标 | 退出标准 |
| --- | --- | --- |
| M0 仓库基础 | 文档、协作、保护规则、任务池就绪 | 新成员能按文档开始开发 |
| M1 Web 与骨架跑通 | Docker Compose + Web 页面 + FastAPI + Mock 数据 + CI 卡口 | `web/api/postgres` 可一键启动，Web 端可展示完整 Mock 工作流，PR 可拦截依赖漂移 |
| M2 数据主链路 | 主案例数据获取、清洗、导出 | 真实数据进入 CSV、字段字典、溯源报告 |
| M3 论文获取与文献总结 | 自动获取主案例论文并生成结构化总结 | PaperAcquisition 和 PaperSummary 可展示并绑定来源 |
| M4 跨文献推理与学术图谱 | Claim/Relation/Trace 和证据图谱 | 推理关系可展示，图谱边绑定 evidence 和 trace |
| M5 反馈与公网 Demo | 反馈修正、缓存兜底、公网访问 | 演示链路稳定，可交付截图和录屏素材 |

## M0：仓库基础

| 产出 | 负责人 | 状态 |
| --- | --- | --- |
| README、PRD、DESIGN、AGENTS | 开发负责人 | 已建立，持续维护 |
| API、数据模型、模块边界 | B 主导，全员确认 | 已建立，M1 前冻结初版 |
| Roadmap、Backlog、Acceptance | 开发负责人 | 已建立 |
| GitHub 分支保护、PR 模板、Issue 模板 | 开发负责人 | 已建立 |

## M1：Web-first + Docker-first 骨架

M1 先做 `X-00` 和 `X-04`。C/D 在 M1 不需要完成完整数据链路、论文获取和推理链路，但必须给出最小真实依据，供 Schema、Mock API 和页面结构使用。A 优先跑通 Web 端页面和 Mock 闭环，B 同步交付 FastAPI 与 Mock API；A/B/X-04 初步完成后，由 `X-05` 建立最小 CI 与依赖漂移卡口。

| 产出 | 负责人 | 验收 |
| --- | --- | --- |
| MVP 最小真实依据 | A + B + C + D | 字段清单、论文获取来源、检索关键词、5-8 篇 seed list、Claim/Relation 样例、Graph 最小关系类型已冻结 |
| Docker Compose 本地基线 | A + B | `web`、`api`、`postgres` 三容器可 `docker compose up --build` 启动 |
| Web 项目骨架 | A | Vue 3 + TypeScript + Vite + pnpm + shadcn-vue + Tailwind CSS 4 可启动 |
| FastAPI 项目骨架 | B | Python 3.13 + uv + FastAPI 可启动，`/api/v1/health`、`/api/v1/tasks` 可用 |
| CI 与依赖漂移卡口 | A + B | PR 可检查错误 lockfile、`.env` 泄露、关键环境变量、pnpm/uv/Docker 基线 |
| 共享 Schema 初版 | B | 前后端字段命名一致，PaperAcquisition、Claim、Relation、Trace、Evidence 字段符合 DATA_MODEL |
| Mock 任务流程 | A + B | 创建任务后可看到任务流、数据、论文获取、文献、推理、图谱 Mock 结果 |
| 本地启动文档 | A + B | 新成员 30 分钟内可通过 Docker 跑起来 |

## M2：自动化数据分析主链路

| 产出 | 负责人 | 验收 |
| --- | --- | --- |
| 主数据源查询 | C | 至少 1 个真实天文数据源可查询 |
| 第二来源或补充来源 | C | 支撑“多源”与来源对比 |
| 字段映射规则 | C | 关键字段有单位和来源 |
| 数据质量评分 | C + B | API 返回质量指标 |
| CSV / 数据字典 / 溯源报告 | C + B | 前端可下载 |

## M3：自动论文获取与智能文献总结

| 产出 | 负责人 | 验收 |
| --- | --- | --- |
| 论文获取来源与检索策略 | D | 主案例内可复现，不依赖手写列表冒充自动获取 |
| PaperAcquisition Pipeline | D | 返回 PaperSearchQuery、PaperAcquisitionRun、PaperCandidate |
| PaperAcquisition API | B + D | 前端可展示检索参数、候选论文、去重、相关性排序 |
| 总结 Prompt 与 JSON Schema | D + B | 输出稳定通过校验 |
| PaperSummary API | B + D | 前端可展示结构化结果 |
| 文献来源与证据 | D | 每条核心结论绑定 paper/source/evidence |

## M4：跨文献逻辑推理与学术图谱可视化

| 产出 | 负责人 | 验收 |
| --- | --- | --- |
| LiteratureClaim | D | 从多篇论文中抽取目标、方法、数据、发现、局限 |
| LiteratureRelation | D | 至少支持 `supports`、`extends`/`derived_from`、`limits`/`contradicts` 中 3 类关系 |
| ReasoningTrace | D + B | 每条最终关系有 trace 和 evidence |
| Reasoning API | B + D | `/literature-reasoning` 可返回 claims、relations、traces |
| Graph JSON | D | 节点、边、证据、推理关系符合 DATA_MODEL |
| 图谱页面 | A | Vue Flow 图谱可点击，详情可读，推理链可查看 |
| 证据详情接口 | B + D | 点击边或节点可看到来源依据 |
| 图谱展示优化 | A + D | 适合答辩截图和录屏 |

## M5：反馈修正与公网 Demo

| 产出 | 负责人 | 验收 |
| --- | --- | --- |
| 反馈入口 | A | 用户可提交字段、单位、来源、文献总结、推理关系问题 |
| 局部修正接口 | B + C + D | 修正后结果有记录 |
| 缓存兜底 | B | 外部 API、论文源或模型失败时仍可完整演示，缓存作为 meta 标记 |
| 公网 Demo | A + B | 可访问、可演示、密钥不暴露 |
| 材料交接包 | 全员 | 截图、导出文件、说明文档齐全 |

## 节奏建议

- M1 必须先完成 `X-00` 和 `X-04`，再让 A/B 并行推进，C/D 给最小真实依据。
- `X-05` 在 A/B/X-04 初步完成后建立最小 CI，先卡住依赖漂移，再逐步加入构建和 Docker 检查。
- Web-first 不等于脱离契约；前端 fixtures 必须对齐 `API_CONTRACT.md`。
- Docker-first 不等于一开始引入复杂中间件；M1 只保留 `web`、`api`、`postgres`。
- M2 是数据主链路，M3/M4 是核心差异化能力，不能降级为后续扩展。
- 自动论文获取优先做主案例内可运行闭环，开放式全文解析后置。
- 跨文献推理必须共用 `Evidence`、`LiteratureRelation` 和 `ReasoningTrace` 数据模型。
- M5 不等于最后才开始；缓存兜底和导出设计从 M2 就要预留。
