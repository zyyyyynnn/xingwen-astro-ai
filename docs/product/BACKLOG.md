# Backlog

任务编号前缀：`A` 前端，`B` 后端，`C` 数据，`D` 文献/图谱，`X` 跨模块。

## P0：冻结目标前端并保持当前基线可运行

当前 `X-00`、`X-04`、Vue / FastAPI 骨架与 `X-05` 已形成 Phase 0 基线。A 线按新的 Astro + React、科研产物优先和 ASCII / Dither 方案继续，迁移期保持当前命令可运行，不向旧 Vue 增加业务功能。

| ID | 任务 | 负责人 | 产出 | 依赖 |
| --- | --- | --- | --- | --- |
| X-00 | 冻结 MVP 最小真实依据 | A + B + C + D | 字段清单、论文获取来源、检索关键词、seed list、跨文献关系类型、Graph 最小关系类型 | 无 |
| X-04 | 建立 Docker Compose 本地开发基线 | A + B | `web`、`api`、`postgres` 三容器，固定 Node 24、Python 3.13、PostgreSQL 17、pnpm、uv | X-00 |
| C-01 | 确定 MVP 字段清单 | C | 字段名、含义、单位、来源优先级 | X-00 |
| D-01 | 确定论文获取与推理基准 | D | 论文源候选、检索关键词、5-8 篇 seed list、Claim/Relation 样例 | X-00 |
| A-01 | 重构前端 Monorepo 与运行时基线 | A | pnpm workspace、`apps/site`、`apps/workspace`、共享 packages、strict TS、构建/测试目标与旧 Vue 迁移策略 | X-04 |
| B-01 | 初始化 FastAPI 与 uv 后端骨架 | B | FastAPI + Python 3.13 + uv 可启动，Docker API 服务可运行 | X-04 |
| X-05 | 建立基础 CI 与依赖漂移卡口 | A + B | foundation check、frozen install、前端构建、后端测试、Schema 导出、Compose 校验 | X-04, A-01, B-01 |
| B-02 | 定义 Pydantic Schema 初版 | B | 与 DATA_MODEL 对齐，包含 PaperAcquisition、Claim、Relation、Trace；可导出 JSON Schema | B-01, C-01, D-01 |
| B-03 | 创建任务/查询任务接口 | B | `/api/v1/health`、`/api/v1/tasks` 可用 | B-02 |
| B-04 | v1 Phase 0 结果聚合 | B | dataset/paper-acquisition/papers/literature-reasoning/graph/evidence 返回带明确示例口径的响应 | B-03, C-01, D-01 |
| A-02 | 建立品牌视觉系统、首页与科研工作台框架 | A | Token、字标/字体层级、ASCII/Dither 基础、四幕首页、Workspace Shell、fallback | A-01 |
| A-03 | 建立 Research Contract、Guided Tour 与契约驱动双通道 | A | Project/Run Shell、Research Contract、Fixture/HTTP Adapter、Tour、Atlas/Canvas/Observatory/Console、分享入口 | A-01, A-02, target Contract |
| X-01 | 前后端 Contract 联调 | A + B | HTTP Adapter 与 v2 Contract 可联调，Fixture / HTTP 一致性测试通过 | A-03, target Contract, X-05 |

## P1：数据主链路

| ID | 任务 | 负责人 | 产出 | 依赖 |
| --- | --- | --- | --- | --- |
| C-02 | 接入主数据源查询 | C | 原始查询结果和 SourceRecord | C-01 |
| C-03 | 接入补充来源或缓存来源 | C | 第二来源说明 | C-02 |
| C-04 | 字段映射和单位统一 | C | FieldDefinition + 清洗后 rows | C-02 |
| C-05 | 数据质量评分 | C | QualityScore | C-04 |
| B-05 | 数据结果 API 对接 | B + C | dataset/sources/export 接口 | C-04 |
| A-04 | 构建数据产物研究画布 | A | 虚拟化数据表、字段字典、来源、质量、对照、导出、Evidence 与完整状态 | A-03, B-05 |

## P1：论文获取、文献总结与跨文献推理

| ID | 任务 | 负责人 | 产出 | 依赖 |
| --- | --- | --- | --- | --- |
| D-02 | 论文自动获取 Pipeline | D | PaperSearchQuery、PaperAcquisitionRun、PaperCandidate | D-01 |
| B-06 | 论文获取 API 对接 | B + D | `/paper-acquisition` 接口 | D-02 |
| A-05 | 构建论文获取与候选审查工作区 | A | 检索参数、来源、候选、去重、排序、选择依据、运行来源和 Evidence 对照 | A-03, B-06 |
| D-03 | 文献总结 Prompt 与 Schema | D | PaperSummary JSON + Evidence | D-02 |
| B-07 | 文献总结 API 对接 | B + D | `/papers` 接口 | D-03 |
| A-06 | 构建文献总结与 Evidence 阅读工作区 | A | 目标、方法、数据、结论、局限、locator、短引用/值与文献对照 | A-03, A-05, B-07 |
| D-04 | Claim/Relation/ReasoningTrace 构建 | D | LiteratureClaim、LiteratureRelation、ReasoningTrace | D-03 |
| B-08 | 跨文献推理 API 对接 | B + D | `/literature-reasoning` 接口 | D-04 |
| A-07 | 构建跨文献推理与 Trace 对照工作区 | A | Claim、候选/最终 Relation、Trace、条件、Evidence 与三面板对照 | A-06, B-08 |
| D-05 | 图谱节点/边生成 | D | Graph JSON，包含跨文献关系 | C-04, D-04 |
| B-09 | 证据详情和图谱 API | B + D | `/graph`, `/evidence/{id}` | D-05 |
| A-08 | 构建学术图谱与溯源观测台 | A | React Flow 证据图谱、Provenance Observatory、产物联动和规模控制 | A-07, B-09 |

## P2：反馈、缓存、部署

| ID | 任务 | 负责人 | 产出 | 依赖 |
| --- | --- | --- | --- | --- |
| B-10 | 缓存兜底机制 | B | data/paper/model/reasoning cache record + cached meta | B-05, B-07, B-08, B-09 |
| A-09 | 建立运行来源、缓存、版本与质量状态系统 | A | Live/Cached/Fixture/Revised、version、retrieved_at、SourceSnapshot 跨页面一致 | A-03, B-10, version/cache Contract |
| A-10 | 建立上下文反馈与局部修正体验 | A | Field/Source/Paper/Claim/Relation/Trace/GraphEdge 反馈、RevisionPlan 和新 ArtifactVersion 状态 | A-04, A-06, A-07, A-08, feedback Contract |
| B-11 | 反馈修正接口 | B | `/feedback` + revising 状态 | A-10 |
| C-06 | 字段/单位局部修正 | C | 修正记录和重导出 | B-11 |
| D-06 | 文献/推理/图谱局部修正 | D | evidence、relation、trace 更新 | B-11 |
| X-02 | 公网 Demo 部署 | A + B | URL、环境变量、缓存验证 | 核心链路完成 |
| X-03 | 材料交接包 | 全员 | 截图、CSV、论文候选、推理图谱、说明 | X-02 |

## 跨阶段集成 Issue

这些 Issue 是阶段级验收与集成门，不替代上面的 A/B/C/D 原子任务。

| ID | 阶段 | 目标 | 聚合依赖 |
| --- | --- | --- | --- |
| X-06 | Phase 1 | 真实数据、自动论文获取、结构化总结与 Evidence 主链路 | C-02~C-05、D-02~D-03、B-05~B-07、A-04~A-06 |
| X-07 | Phase 2 | Claim/Relation/Trace、Graph 与证据查看闭环 | D-04~D-05、B-08~B-09、A-07~A-08 |
| X-08 | Phase 3 | 版本/实验治理、缓存、反馈、部署与材料交付 | B-10~B-11、A-09~A-10、C-06、D-06、X-02~X-03 |

## 暂缓任务

| 任务 | 暂缓原因 |
| --- | --- |
| 任意天文方向支持 | 会削弱主案例稳定性 |
| 全网无限制论文爬取 | 来源合规和稳定性不可控，MVP 限定主案例和可运行来源 |
| 任意 PDF 全文高精度解析 | 成本高，MVP 优先元数据、摘要和开放可访问文本片段 |
| Redis / Celery | MVP 先用 FastAPI + DB 状态机 / BackgroundTasks，任务变重后再评估 |
| MinIO / Nginx / RabbitMQ | M1 不需要，过早引入会增加团队环境复杂度 |
| 多用户权限系统 | 比赛演示不是核心风险 |
| Neo4j / 通用 Entity 层 / 向量数据库 | 真实规模和查询需求尚未证明需要 |
