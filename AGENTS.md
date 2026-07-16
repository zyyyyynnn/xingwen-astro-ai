# AGENTS

本文件是本仓库的 Agent 操作协议。协作流程见 [CONTRIBUTING.md](CONTRIBUTING.md)，产品与设计总纲见 [DESIGN.md](DESIGN.md)。

## 1. 默认基准

- 环境：Windows 11、PowerShell 7+、UTF-8。
- 开发方式：Web-first、Docker-first、Contract-first、Evidence-first。
- 主案例：**系外行星候选体与宿主恒星参数整合**。
- 优先级：主链路稳定 > 证据可信 > 可复现 > 自主评审可理解 > 功能扩展。
- 需求明确时直接执行；只改任务要求的部分；无法验证时写明原因。

## 2. 当前实现与目标架构

| 层级 | 当前可运行基线 | 已接受目标（Implementation Pending） |
| --- | --- | --- |
| 品牌 / 前端 | `apps/web`：Vue 3 + Vite | `apps/site`：Astro 静态品牌站 |
| 科研工作台 | Vue 单页骨架 | `apps/workspace`：React + TypeScript |
| UI / 图谱 | shadcn-vue、reka-ui、Vue Flow | 项目 Token + Radix primitives、`@xyflow/react` |
| 共享前端 | 当前未建立 | design-tokens、ui、visual-engine、domain、contracts、data-access、workspace-core、testing |
| API | FastAPI `/api/v1` Task 契约 | `/api/v2` Project / Run / Artifact / Version |
| 后端 | Python 3.13、Pydantic v2 | 保持 FastAPI / Pydantic，增加 v2 Application / Persistence |
| 数据库 | PostgreSQL 17 | 保持 PostgreSQL 17 |
| 本地环境 | Compose：`web`、`api`、`postgres` | 迁移 Issue 明确更新前保持当前命令 |

规则：

- 目标架构不得写成当前已实现能力。
- A-01 开始后，`apps/web` 只做阻塞性修复和迁移读取，不再新增业务功能。
- 新旧前端不得长期双写同一业务；新工作台通过门禁后删除旧 Vue 依赖。
- 本文件不授权在无对应 Issue 时安装 Astro、React、Three.js、Tauri 或改 Docker。

## 3. 技术栈红线

- 前端统一 Node.js 24 LTS、pnpm 10.x、单一 `pnpm-lock.yaml`、TypeScript strict。
- 禁止 npm/yarn/bun 生成依赖状态；禁止提交 `package-lock.json`、`yarn.lock`、`bun.lock`。
- 后端统一 uv、`pyproject.toml`、`uv.lock`；禁止用裸 pip / requirements 替代主流程。
- Pydantic 是当前 Schema authoring source；OpenAPI / JSON Schema 生成 Transport Contract，禁止手写第二套同名生产 Schema。
- 前端不直连 Qwen、天文数据源或论文源，不保存密钥。
- M1 不引入 Redis、Celery、MinIO、Nginx、RabbitMQ、Neo4j 或向量数据库，除非先更新 ADR 与 Backlog。
- 生产 Prompt 位于 `packages/prompts`，不得散落在 Router、组件或临时脚本。

## 4. 执行与修改纪律

- 每处改动对应 Issue、PR 或明确用户指令。
- 不顺手重构、不扩大范围、不引入无明确职责的依赖。
- 跨模块任务先对齐 API、Data Model、Workflow、Version 和 Reasoning Contract。
- 当前代码与目标文档冲突时，明确“Current / Target / Pending”，不得猜测已迁移。
- 不把 Fixture、缓存或模型推断包装成真实科研结论。
- 不保存或展示模型私有 chain-of-thought；ReasoningTrace 只含可审查依据、条件和引用。

## 5. Git 与 PR

- 从 `main` 建分支，不直接推送 `main`；不 reset、force push 或改写远端历史。
- Commit 一个主要目的，使用 `feat` / `fix` / `docs` / `chore` 前缀。
- PR 关联 Issue，说明范围、验证、契约/数据/UI/部署/安全影响和材料口径。
- 通过 Review 与 CI 后 Squash merge；失败卡口不得绕过。
- 工作区存在无关修改时不得擅自暂存、清除或提交。

## 6. 模块边界

| 岗位 | 当前 / 目标目录 | 核心职责 |
| --- | --- | --- |
| A 前端与产品 | Current `apps/web`; Target `apps/site`, `apps/workspace`, frontend packages | 首页、Guided Tour、Workspace、Domain Adapter、视觉与前端门禁 |
| B 后端与编排 | `apps/api`, `packages/schemas`, `scripts` | v1 稳定性、v2 API、Run Workflow、Schema、Session / Share、安全 |
| C 数据 | `services/data_pipeline`, `samples/outputs` | 数据源、清洗、单位、质量、SourceSnapshot、Evidence、导出 |
| D 论文与图谱 | `services/paper_pipeline`, `services/graph_pipeline`, `packages/prompts` | 论文获取、Summary、Claim/Relation/Trace、Graph 与 Evidence |
| X 基建 | 根目录、`.github`, `docs/setup.md` | Compose、CI、环境变量、版本锁定和验证 |

详细依赖方向以 [MODULES.md](docs/architecture/MODULES.md) 为准。

## 7. 文档同步红线

| 改动 | 必须同步 |
| --- | --- |
| 接口、响应、错误、授权 | `docs/architecture/API_CONTRACT.md` |
| 实体、字段、枚举 | `docs/architecture/DATA_MODEL.md` |
| 状态、重试、取消、缓存、派生 | `docs/architecture/WORKFLOW_DESIGN.md` |
| Artifact、版本、来源、分享 | `docs/architecture/DATA_VERSIONING.md` |
| 前端架构与目录 | `DESIGN.md`, `docs/architecture/FRONTEND_ARCHITECTURE.md`, `MODULES.md` |
| 品牌、Token、字体、WebGL | `docs/design/VISUAL_LANGUAGE.md` |
| 首页、Tour、Workspace | `docs/design/WORKSPACE_UX.md` |
| 启动、Docker、环境变量 | `docs/setup.md`, `DEPLOYMENT.md`, `.env.example` |
| 产品范围与验收 | `PRD.md`, `docs/product/ACCEPTANCE.md` |
| 风险与安全 | `docs/quality/RISK_REGISTER.md`, `SECURITY.md` |

## 8. 验证要求

| 类型 | 最低要求 |
| --- | --- |
| Foundation | `python scripts/check_foundation.py` |
| 当前 Compose | `docker compose config`；运行变更时 `docker compose up --build` |
| 当前前端 | frozen pnpm install + build；命令以 `docs/setup.md` 为准 |
| 目标 Monorepo | 建立后运行 lint、typecheck、test、build、E2E smoke、architecture/token checks |
| Astro Site | 静态 HTML 含标题、说明、CTA；SEO、LCP、无 WebGL fallback |
| React Workspace | Contract、Project/Run、最多三面板、键盘、a11y、恢复与分享 |
| Visual Engine | High/Medium/Low、deterministic seed、freeze time、pause/dispose、Poster、Reduced Motion |
| Adapter | Fixture / HTTP 返回同一 Domain Model，一致性测试通过 |
| 后端 | `uv sync --locked` + pytest；错误与权限场景覆盖 |
| 科研可信 | Summary、Relation、Trace、GraphEdge 均按契约绑定 Evidence |

无法执行上一级验证时说明原因和降级验证，不得用“应该可以”代替结果。

## 9. UI 与视觉红线

- 只实现浅色系统：冷淡灰基底、低饱和雾霾蓝、深蓝灰文字、独立状态色。
- Raw Color 只允许在 design-tokens；业务组件使用语义 Token。
- ASCII / Dither 是分层品牌语言，不是满屏滤镜；不得使用大量 DOM glyph。
- 禁止黑底星空、霓虹蓝紫、强发光、大面积渐变、玻璃拟态和通用大圆角 Card 墙。
- 工作台以科研产物为中心，不以聊天气泡、工具日志、IDE 或无限窗口为中心。
- 表格、论文、Evidence 正文优先可读；视觉不能承载唯一信息。
- Canvas 必须有 DOM 内容和 Poster；支持 Reduced Motion、页面隐藏暂停和 GPU dispose。
- 字体二进制提交前必须记录许可证、来源、中文覆盖、Web 加载和 Tauri 离线策略。

## 10. Fixture、运行来源与科研可信

- `execution_mode`: `demo_replay | live`；`source_mode`: `fixture | live | cached | revised`。
- Fixture 版本化并包含 scenario、schema version 和 provenance note。
- Cached 只能引用真实历史 Run、ArtifactVersion 与 SourceSnapshot。
- seed list 仅用于 benchmark、Fixture 或人工校验，不能冒充自动获取。
- 模型输出必须经过 Schema 与 Evidence 校验；无 Evidence / Trace 的关系只能作为候选。
- GraphEdge 全部绑定 Evidence，跨文献边再绑定 Relation / ReasoningTrace。

## 11. 材料口径

提交路径为 `START HERE -> 短片 -> Web Guided Tour -> Workspace -> PDF -> 源码/API/测试`。只交付真实系统素材、明确 Fixture 或可定位真实运行缓存。未实现能力只能写 Proposed、Pending、规划或预留。

禁止宣传：任意天文方向、任意 PDF 全文解析、任意图表全自动解析、无边界 AI Scientist、无证据科学发现。
