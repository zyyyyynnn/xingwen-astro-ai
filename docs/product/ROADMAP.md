# Roadmap

> 当前 Phase 0 的 Vue / FastAPI / Compose 基线仍可运行；A 线目标已接受 Astro + React 重构，但 Implementation Pending。Milestone 与 P0/P1/P2 映射保持不变。

## 里程碑总览

| 里程碑 | 对应优先级 | 目标 | 退出标准 |
| --- | --- | --- | --- |
| M0 文档基建 | — | 文档、协作、保护规则、任务池就绪 | 新成员能按文档开始开发 |
| M1 开发基线 | P0 | 当前 Compose / FastAPI 基线 + 目标前端 Monorepo、品牌/工作台框架和 Contract 双通道 | 当前三服务保持可启动；新前端基线、Fixture Demo、CI 与契约门禁通过 |
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

M1 已建立 `X-00`、`X-04`、FastAPI、Vue 骨架和 Phase 0 Workflow。2026-07 前端产品级重构重新打开 A-01，并按 A-01 → A-02 → A-03 建立目标运行时、品牌/工作台框架和 Contract 驱动双通道；C/D 继续提供最小真实依据，B 保持 v1 稳定并准备 v2 Contract。迁移期不在 Vue 与 React 双写业务。

| 产出 | 负责人 | 验收 |
| --- | --- | --- |
| MVP 最小真实依据 | A + B + C + D | 字段清单、论文来源、检索词、seed、关系类型已冻结 |
| Docker Compose 本地基线 | A + B | `web`、`api`、`postgres` 可启动，浏览器 API 地址与 CORS 正确 |
| 当前 Web 回退基线 | A | `apps/web` Vue 3 骨架保持可启动，不新增业务功能 |
| 目标前端 Monorepo | A | Node 24、pnpm workspace、Astro Site、React Workspace、strict TS 和共享 packages 可构建 |
| 品牌与 Workspace 框架 | A | 四幕首页、视觉 Token、Visual Engine fallback、Artifact-first Shell 骨架 |
| Contract 双通道 | A + B | Research Contract、Fixture / HTTP Adapter、Guided Tour、Project / Run Shell |
| FastAPI 项目骨架 | B | Python 3.13 + uv + FastAPI 可启动，基础接口可用 |
| Workflow 骨架 | B | 状态转换集中校验，Executor 与数据库/Pipeline 解耦 |
| CI 与依赖漂移卡口 | A + B | foundation、frozen install、build、pytest、Schema export、Compose config |
| 共享 Schema 初版 | B | Pydantic 单一编写源，可导出 JSON Schema |
| Prompt/模型治理基线 | B + D | Prompt registry、模型输出准入与证据规则明确 |
| Demo Replay | A + B | 版本化 Fixture 可稳定展示且不冒充 Live / Cached |
| 本地启动文档 | A + B | 新成员 30 分钟内可通过 Docker 跑起来 |

A 线 M1 退出顺序：

1. A-01：Monorepo 与运行时基线，不实现业务页面、不实现 Tauri。
2. A-02：品牌视觉、首页四幕框架、Workspace Shell 与 WebGL 降级，不接真实业务数据。
3. A-03：Research Contract、Guided Tour、Repository Port、Fixture / HTTP、Project / Run 与只读分享入口。

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
| 数据产物研究画布（A-04） | A | 高密度表格、虚拟化、字段/来源/质量/Evidence 对照和导出状态完整 |

### M2.2 论文获取与文献总结（X-06）

| 产出 | 负责人 | 验收 |
| --- | --- | --- |
| 论文获取来源与检索策略 | D | 主案例内可复现，不依赖手写列表冒充自动获取 |
| PaperAcquisition Pipeline | D | 返回 Query、Run、Candidate 与 SourceSnapshot |
| PaperAcquisition API | B + D | 前端可展示检索参数、候选、去重、排序 |
| 总结 Prompt 与 JSON Schema | D + B | 版本化 Prompt，输出稳定通过校验 |
| PaperSummary API | B + D | 前端可展示结构化结果 |
| 文献来源与证据 | D | 每条核心结论绑定 paper/source/evidence |
| 论文候选工作区（A-05） | A | Query、来源、去重、排序、选择依据和 Demo/Live/Cached 清楚 |
| 文献 Evidence 工作区（A-06） | A | Summary、原文 locator、条件和跨论文对照可审查 |

### M2.3 跨文献推理与学术图谱（X-07）

| 产出 | 负责人 | 验收 |
| --- | --- | --- |
| LiteratureClaim | D | 从多篇论文抽取目标、方法、数据、发现、局限 |
| LiteratureRelation | D | 支持核心关系类型，候选与最终关系分离 |
| ReasoningTrace | D + B | 每条最终关系有 trace 和 evidence |
| Reasoning API | B + D | `/literature-reasoning` 返回结构化结果 |
| Graph JSON | D | 节点、边、证据、推理关系符合契约 |
| 推理 Trace 工作区（A-07） | A | Claim、候选/最终 Relation、Trace 与 Evidence 最多三面板对照 |
| 图谱工作区（A-08） | A | React Flow 可点击，详情、Provenance 和推理链可查看 |
| 证据详情接口 | B + D | 点击边或节点可看到来源依据 |
| 图谱展示优化 | A + D | 适合作品自主阅读、截图、录屏和可能的终审展示 |

## M3：反馈与交付（P2，X-08）

| 产出 | 负责人 | 验收 |
| --- | --- | --- |
| ArtifactVersion / ExperimentRun | B + D | 关键产物和模型运行可定位版本 |
| 来源与版本状态系统（A-09） | A | Live / Cached / Fixture / Revised、版本、时间和 SourceSnapshot 跨页面一致 |
| 上下文反馈（A-10） | A | 字段、来源、论文、Claim、Relation、Trace、GraphEdge 可定位反馈 |
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
- Web-first 不等于脱离契约；Fixture / HTTP Adapter 必须通过同一 Schema 和 Domain Contract。
- WebGL 不得成为 LCP 或核心操作前置条件；Poster、Reduced Motion、pause/dispose 是实现门禁。
- Docker-first 不等于引入复杂中间件；M1 只保留三服务。
- M2 是核心差异化能力，不能降级为后续扩展。
- 自动论文获取优先做主案例内可运行闭环，开放式全文解析后置。
- 跨文献推理共用 Evidence、Relation 和 ReasoningTrace。
- M3 能力从 M2 预留 hash/version 字段，但不提前引入 Redis、Neo4j 或向量库。
