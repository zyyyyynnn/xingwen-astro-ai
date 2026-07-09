# Backlog

任务编号前缀：`A` 前端，`B` 后端，`C` 数据，`D` 文献/图谱，`X` 跨模块。

## P0：先跑通 Web 与本地环境

P0 不按“后端全部完成后前端再开始”的串行方式推进。`X-00` 对齐真实依据，`X-04` 固定 Docker 本地开发基线，随后 A/B 并行初始化，C/D 提供最小真实依据，避免 Mock 工作流变成空壳。

| ID | 任务 | 负责人 | 产出 | 依赖 |
| --- | --- | --- | --- | --- |
| X-00 | 冻结 MVP 最小真实依据 | A + B + C + D | 字段清单、论文获取来源、检索关键词、seed list、跨文献关系类型、Graph 最小关系类型 | 无 |
| X-04 | 建立 Docker Compose 本地开发基线 | A + B | `web`、`api`、`postgres` 三容器，固定 Node 24、Python 3.13、PostgreSQL 17、pnpm、uv | X-00 |
| C-01 | 确定 MVP 字段清单 | C | 字段名、含义、单位、来源优先级 | X-00 |
| D-01 | 确定论文获取与推理基准 | D | 论文源候选、检索关键词、5-8 篇 seed list、Claim/Relation 样例 | X-00 |
| A-01 | 初始化 Web 端骨架 | A | Vue 3 + TypeScript + Vite + pnpm + shadcn-vue + Tailwind CSS 4 可启动 | X-04 |
| B-01 | 初始化 FastAPI 与 uv 后端骨架 | B | FastAPI + Python 3.13 + uv 可启动，Docker API 服务可运行 | X-04 |
| B-02 | 定义 Pydantic Schema 初版 | B | 与 DATA_MODEL 对齐，包含 PaperAcquisition、Claim、Relation、Trace | B-01, C-01, D-01 |
| B-03 | 创建任务/查询任务接口 | B | `/api/v1/health`、`/api/v1/tasks` 可用 | B-02 |
| B-04 | Mock 任务结果聚合 | B | dataset/paper-acquisition/papers/literature-reasoning/graph/evidence 返回样例 | B-03, C-01, D-01 |
| A-02 | 搭建页面路由和基础布局 | A | 首页、任务页、数据页、论文获取页、文献页、推理页、图谱页 | A-01 |
| A-03 | 基于 Mock 展示完整任务流 | A | 任务流、数据、论文获取、文献、推理、图谱页面可展示；API 不可用时仅开发模式使用 fixtures | A-02, B-04 |
| X-01 | 前后端 Mock 联调 | A + B | Docker Compose 下页面可展示完整 Mock 工作流 | A-03, B-04 |

## P1：数据主链路

| ID | 任务 | 负责人 | 产出 | 依赖 |
| --- | --- | --- | --- | --- |
| C-02 | 接入主数据源查询 | C | 原始查询结果和 SourceRecord | C-01 |
| C-03 | 接入补充来源或缓存来源 | C | 第二来源说明 | C-02 |
| C-04 | 字段映射和单位统一 | C | FieldDefinition + 清洗后 rows | C-02 |
| C-05 | 数据质量评分 | C | QualityScore | C-04 |
| B-05 | 数据结果 API 对接 | B + C | dataset/sources/export 接口 | C-04 |
| A-04 | 数据结果页 | A | 数据表、字段字典、来源、质量评分 | B-05 |

## P1：论文获取、文献总结与跨文献推理

| ID | 任务 | 负责人 | 产出 | 依赖 |
| --- | --- | --- | --- | --- |
| D-02 | 论文自动获取 Pipeline | D | PaperSearchQuery、PaperAcquisitionRun、PaperCandidate | D-01 |
| B-06 | 论文获取 API 对接 | B + D | `/paper-acquisition` 接口 | D-02 |
| A-05 | 论文获取页 | A | 检索参数、候选论文、去重、相关性排序展示 | B-06 |
| D-03 | 文献总结 Prompt 与 Schema | D | PaperSummary JSON + Evidence | D-02 |
| B-07 | 文献总结 API 对接 | B + D | `/papers` 接口 | D-03 |
| A-06 | 文献总结页 | A | 结构化总结展示 | B-07 |
| D-04 | Claim/Relation/ReasoningTrace 构建 | D | LiteratureClaim、LiteratureRelation、ReasoningTrace | D-03 |
| B-08 | 跨文献推理 API 对接 | B + D | `/literature-reasoning` 接口 | D-04 |
| A-07 | 跨文献推理页 | A | Claim、Relation、Trace 可展示并打开证据 | B-08 |
| D-05 | 图谱节点/边生成 | D | Graph JSON，包含跨文献关系 | C-04, D-04 |
| B-09 | 证据详情和图谱 API | B + D | `/graph`, `/evidence/{id}` | D-05 |
| A-08 | 学术图谱页 | A | Vue Flow 图谱，可点击节点、关系边和证据面板 | B-09 |

## P2：反馈、缓存、部署

| ID | 任务 | 负责人 | 产出 | 依赖 |
| --- | --- | --- | --- | --- |
| B-10 | 缓存兜底机制 | B | data/paper/model/reasoning cache record + cached meta | B-05, B-07, B-08, B-09 |
| A-09 | 缓存模式提示 | A | 页面明确标注缓存结果 | B-10 |
| A-10 | 反馈入口 | A | 字段/来源/文献/推理/图谱反馈表单 | A-04, A-08 |
| B-11 | 反馈修正接口 | B | `/feedback` + revising 状态 | A-10 |
| C-06 | 字段/单位局部修正 | C | 修正记录和重导出 | B-11 |
| D-06 | 文献/推理/图谱局部修正 | D | evidence、relation、trace 更新 | B-11 |
| X-02 | 公网 Demo 部署 | A + B | URL、环境变量、缓存验证 | 核心链路完成 |
| X-03 | 材料交接包 | 全员 | 截图、CSV、论文候选、推理图谱、说明 | X-02 |

## 暂缓任务

| 任务 | 暂缓原因 |
| --- | --- |
| 任意天文方向支持 | 会削弱主案例稳定性 |
| 全网无限制论文爬取 | 来源合规和稳定性不可控，MVP 限定主案例和可运行来源 |
| 任意 PDF 全文高精度解析 | 成本高，MVP 优先元数据、摘要和开放可访问文本片段 |
| Redis / Celery | MVP 先用 FastAPI + DB 状态机 / BackgroundTasks，任务变重后再评估 |
| MinIO / Nginx / RabbitMQ | M1 不需要，过早引入会增加团队环境复杂度 |
| 多用户权限系统 | 比赛演示不是核心风险 |
| 大规模图谱存储 | MVP 图谱规模可由 JSON 支撑 |
