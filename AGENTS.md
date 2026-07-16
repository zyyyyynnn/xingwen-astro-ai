# AGENTS

本文件是本仓库的 Agent 操作协议。协作流程细节见 [CONTRIBUTING.md](CONTRIBUTING.md)，系统、技术栈与 UI 基线见 [DESIGN.md](DESIGN.md)。

## 1. 默认基准

- 环境：Windows 11、PowerShell 7+、UTF-8。
- 开发方式：Web-first、Docker-first、Contract-first、Evidence-first。
- 目标：国赛级 MVP，先服务主案例 **系外行星候选体与宿主恒星参数整合**。
- 优先级：主链路稳定 > 证据可信 > 可复现 > 演示完整 > 功能扩展。
- 输出原则：结论先行、改动最小、验证明确；不确定时说明不确定。

## 2. 技术栈红线

| 层级 | 固定口径 |
| --- | --- |
| 前端 | Vue 3 + TypeScript + Vite |
| UI | shadcn-vue + reka-ui + Tailwind CSS 4 + CSS Variables |
| 图谱 | Vue Flow；统计图表按需使用 ECharts |
| 前端包管理 | pnpm 10.x；提交 `pnpm-lock.yaml` |
| 后端 | FastAPI + Python 3.13 + Pydantic v2 |
| Python 依赖 | uv + `pyproject.toml` + `uv.lock` |
| 数据库 | PostgreSQL 17-alpine |
| 本地环境 | Docker Compose：`web`、`api`、`postgres` |
| 工作流 | `apps/api/src/app/workflow` 显式状态机 |
| Prompt | `packages/prompts` 不可变版本 |

禁止：

- 使用 npm/yarn/bun 生成依赖状态。
- 提交 `package-lock.json`、`yarn.lock`、`bun.lock`。
- 用裸 pip/requirements 替代 uv 主流程。
- M1 引入 Redis、Celery、MinIO、Nginx、RabbitMQ、Neo4j 或向量数据库，除非先更新 ADR 和 Backlog。
- 在 Router、Vue 组件或临时脚本中维护生产 Prompt。

## 3. 执行纪律

- 需求清晰时直接执行，不反复确认。
- 只问会实质影响实现、风险或验收的问题。
- 不扩大范围，不顺手重构，不引入无关依赖。
- 每处改动对应 Issue、PR 目标或明确用户指令。
- 不把 Mock、缓存或模型推断包装成真实科研结论。
- 不创建第二套同名 Schema；Pydantic authoring source 通过脚本导出共享契约。

## 4. 提交与合并纪律

- 分支从 `main` 新建，命名体现岗位或模块，不直接推送 `main`。
- Commit 一个主要目的，前缀 `feat` / `fix` / `docs` / `chore`。
- PR 必须关联 Issue，并说明改动、验证、契约/部署/安全影响和材料口径。
- 涉及接口、数据、状态、Prompt、模块、启动、风险或安全时同步对应文档。
- 通过 Review、CI 后 Squash merge；合并后删除分支。
- 禁止无验证说明、契约未同步、密钥泄露或宣传未实现能力。

## 5. 模块边界

| 岗位 | 负责目录 | 核心职责 | 必须交付 |
| --- | --- | --- | --- |
| A 前端与产品流程 | `apps/web` | 工作流、数据、论文、推理、图谱、反馈 UI | 页面、状态处理、联调说明 |
| B 后端与任务编排 | `apps/api`, `packages/schemas`, `scripts` | FastAPI、状态机、Schema、Qwen Client、缓存、导出 | API、OpenAPI、统一错误、测试 |
| C 数据分析与数据源 | `services/data_pipeline`, `samples/outputs` | 数据源、清洗、单位、质量、导出 | CSV、字段字典、来源、质量 |
| D 论文、推理与图谱 | `services/paper_pipeline`, `services/graph_pipeline`, `packages/prompts` | 获取、总结、Claim/Relation/Trace、Graph | 结构化产物、Prompt、证据 |
| X 跨模块基建 | 根目录、`.github`, `docs/setup.md` | Compose、CI、环境变量、版本锁定 | 一键启动、机器校验、文档 |

跨模块任务先对齐 API、Data Model、Workflow 和 Prompt/Reasoning 契约，再编码。

## 6. 文档同步红线

| 改动 | 必须同步 |
| --- | --- |
| 接口、响应、错误码 | `docs/architecture/API_CONTRACT.md` |
| 数据实体、字段、枚举 | `docs/architecture/DATA_MODEL.md` |
| 状态、步骤、重试、缓存流程 | `docs/architecture/WORKFLOW_DESIGN.md` |
| 产物、运行、版本治理 | `docs/architecture/DATA_VERSIONING.md` |
| 模型、Prompt、Relation 准入 | `docs/ai/*`, `packages/prompts` |
| 技术栈、模块职责、目录边界 | `DESIGN.md`, `docs/architecture/MODULES.md` |
| 本地启动、Docker、环境变量 | `docs/setup.md`, `DEPLOYMENT.md`, `.env.example` |
| MVP 范围或验收口径 | `PRD.md`, `docs/product/ACCEPTANCE.md` |
| 新风险、技术债、演示风险 | `docs/quality/RISK_REGISTER.md` |
| 安全、密钥、日志 | `SECURITY.md` |

文档只保留能指导开发、验证和交接的必要说明。

## 7. 验证要求

| 类型 | 最低要求 |
| --- | --- |
| Foundation | `python scripts/check_foundation.py` |
| Docker | `docker compose config`，必要时 `docker compose up --build` |
| 前端 | frozen install + build；状态覆盖加载/成功/失败/空/缓存 |
| 后端 | frozen sync + pytest；错误含 code/message/request_id |
| Schema | 全部 Pydantic Model 可导出 JSON Schema |
| 数据 | 样例、CSV、字段、来源可复现 |
| 论文 | Run、Candidate、参数、来源、缓存可复现 |
| 文献 | PaperSummary 绑定来源和 Evidence |
| 推理 | Claim、Relation、Trace 绑定 Evidence |
| 图谱 | 边绑定 evidence；跨文献边绑定 trace |
| 部署 | URL、配置、安全校验、缓存验证 |

无法运行上一级验证时，说明原因和降级验证，不得用“应该可以”代替结果。

## 8. UI 修改纪律

`DESIGN.md` 是 UI 系统唯一入口。

- 优先 shadcn-vue 和项目 token。
- 视觉方向：米白纸感、低饱和灰、低饱和靛灰。
- 业务组件不散落非 token 色值、强阴影或过度动效。
- 数据表、证据面板、推理链、图谱优先清晰可读。
- UI 改动同步 `REVIEW_CHECKLIST.md`。

## 9. 科研可信红线

- 前端不直连 Qwen、论文源或天文数据源。
- 密钥只允许在后端环境变量或部署 Secrets。
- 模型输出必须经过 JSON、Schema、Evidence 校验。
- 展示字段、文献结论、关系、图谱边必须可追溯。
- 跨文献最终关系绑定 ReasoningTrace。
- seed list 仅用于兜底、评测或人工校验。
- 缓存是元信息，不是任务状态。
- Prompt、模型和关键产物必须可定位版本。
- 无 Evidence/Trace 的关系只能作为候选。

## 10. 材料口径红线

只交付真实系统素材或明确标注的真实运行缓存。未实现能力只能写为规划、预留或后续扩展。

禁止宣传：任意天文方向、任意 PDF 全文解析、任意图表全自动解析、无边界 AI Scientist、无证据科学发现。
