# Acceptance Criteria

## 1. MVP 总验收

| 编号 | 标准 | 必须证明 |
| --- | --- | --- |
| G-01 | 公网 Demo 可访问 | URL、首页截图、主流程截图 |
| G-02 | 主案例完整跑通 | 从输入到导出的连续录屏或截图链 |
| G-03 | 数据来自真实来源 | 来源 URL、查询参数、获取时间 |
| G-04 | 论文自动获取可复现 | 检索参数、论文来源、候选列表、去重和相关性排序记录 |
| G-05 | 文献总结结构化 | PaperSummary JSON 和页面展示 |
| G-06 | 跨文献推理可审查 | Claim、Relation、ReasoningTrace、Evidence 可展示 |
| G-07 | 图谱可溯源 | 节点/边详情能看到 evidence 和 reasoning trace |
| G-08 | 输出可导出 | CSV、数据字典、溯源报告、论文与推理关系 JSON |
| G-09 | 反馈可修正 | 反馈前后结果差异和修正记录 |
| G-10 | 缓存兜底可用 | 模拟外部失败时仍能演示主案例，页面标注 cached |
| G-11 | 本地环境可复现 | Docker Compose 可启动 `web`、`api`、`postgres` |
| G-12 | 技术基线可约束 | CI 能拦截错误 lockfile、`.env` 泄露、关键变量缺失和依赖漂移 |

## 2. A 前端验收

| 项目 | 标准 |
| --- | --- |
| 技术栈 | Vue 3 + TypeScript + Vite + pnpm + shadcn-vue + Tailwind CSS 4 |
| 页面完整性 | 首页、任务流程、数据结果、论文获取、文献总结、跨文献推理、图谱、反馈页面可访问 |
| 状态完整性 | 加载、成功、失败、缓存模式均有明确提示 |
| 数据展示 | 数据表、字段字典、来源、质量评分可读 |
| 论文获取展示 | 检索参数、候选论文、去重结果、相关性排序和选择原因可读 |
| 文献展示 | PaperSummary 结构清晰，结论能打开 Evidence |
| 推理展示 | Claim、Relation、ReasoningTrace 可读，关系类型不混淆 |
| 图谱交互 | Vue Flow 节点可点击，边或详情面板能展示证据和推理链 |
| 展示质量 | 页面适合答辩录屏，不像临时后台页面 |

## 3. B 后端验收

| 项目 | 标准 |
| --- | --- |
| 技术栈 | FastAPI + Python 3.13 + uv + Pydantic v2 |
| API | `API_CONTRACT.md` 中核心接口可用 |
| 状态机 | 任务状态按 DESIGN 定义流转，包含 `searching_papers` 和 `reasoning_literature` |
| Qwen Client | 模型调用集中封装，支持超时和错误处理 |
| 数据库 | PostgreSQL 17 中可持久化任务、来源、数据、论文候选、总结、Claim、Relation、Trace、反馈 |
| 缓存 | 外部数据源、论文源或模型失败时可返回最近一次真实运行结果 |
| 安全 | API Key、论文源凭据不进前端、不进日志、不进仓库 |

## 4. X Docker 与 CI 基线验收

| 项目 | 标准 |
| --- | --- |
| Compose | `docker compose up --build` 可启动 `web`、`api`、`postgres` |
| Web 容器 | Node 24 基线，使用 pnpm |
| API 容器 | Python 3.13 基线，使用 uv |
| 数据库容器 | 使用 `postgres:17-alpine` 并持久化数据卷 |
| 环境变量 | 与 `.env.example` 一致，敏感项不进入前端构建变量 |
| CI 静态卡口 | 拦截 `package-lock.json`、`yarn.lock`、`bun.lock`、`.env` 和关键变量缺失 |
| CI 构建卡口 | A/B/X-04 完成后运行 pnpm、uv 和 Docker Compose 检查 |
| 禁止项 | 不引入 Redis、Celery、MinIO、Nginx、RabbitMQ 作为 M1 必需项 |

## 5. C 数据验收

| 项目 | 标准 |
| --- | --- |
| 数据源 | 至少 2 类真实来源或 1 个主源 + 1 个可解释补充源 |
| 字段映射 | 关键字段有名称、含义、单位、来源 |
| 清洗 | 缺失值、单位、类型转换规则明确 |
| 质量评分 | 字段覆盖率、缺失率、来源完整性、单位一致性可计算 |
| 导出 | CSV 和字段字典可复现生成 |

## 6. D 论文、推理与图谱验收

| 项目 | 标准 |
| --- | --- |
| 论文获取 | 主案例内至少 1 个论文来源可运行，候选论文带检索参数、来源、获取时间 |
| 候选处理 | 候选论文有去重规则、相关性排序和入选原因 |
| 文献总结 | 覆盖研究目标、方法、数据、结论、局限 |
| 来源绑定 | 核心总结绑定 paper/source/evidence |
| Claim 抽取 | 从多篇论文中抽取目标、方法、数据、发现、局限等 Claim |
| Relation 构建 | 至少 3 类跨文献关系可生成并绑定 evidence |
| ReasoningTrace | 最终跨文献关系有可审查推理链 |
| 图谱结构 | 节点类型和边类型符合 DATA_MODEL |
| 证据链 | 图谱边必须有 `evidence_ids`，跨文献边必须有关联 `reasoning_trace_id` |
| 可信性 | 不把无来源模型输出或无证据推理作为事实 |

## 7. 文档验收

| 文档 | 标准 |
| --- | --- |
| README | 能让新成员 5 分钟理解项目、技术栈、入口、文档地图 |
| PRD | 范围清楚，知道什么做、什么不做 |
| DESIGN | 架构、技术栈、状态机、模块边界、缓存、安全清楚 |
| API_CONTRACT | 前后端可据此并行开发 |
| DATA_MODEL | 数据、论文、文献、推理、图谱、证据字段一致 |
| ROADMAP/BACKLOG | 能直接拆 Issue 和排优先级 |
| setup/DEPLOYMENT | Docker、本地启动、密钥、部署和公网 Demo 风险明确 |
| REVIEW_CHECKLIST | 覆盖 CI、包管理、Docker、UI、接口、证据链和材料口径 |

## 8. 一票否决项

出现以下情况，MVP 不算完成：

- 公网 Demo 无法访问。
- 前端直接暴露 API Key 或论文源凭据。
- 数据、论文、文献、推理或图谱结果无法追溯来源。
- 论文候选是手写 seed list 冒充自动获取结果。
- 跨文献关系没有 `Evidence` 或 `ReasoningTrace`。
- 缓存数据是手写假数据且未标注。
- 宣传材料把未实现能力写成已实现。
- API 或数据模型与文档明显不一致。
- 本地环境依赖成员个人电脑版本，无法通过 Docker Compose 复现。
- X-05 完成后，PR 绕过失败的 CI 或依赖漂移卡口合并。
