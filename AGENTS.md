# AGENTS

本文件是本仓库的 Agent 操作协议。协作流程见 [CONTRIBUTING.md](CONTRIBUTING.md)，产品与设计总纲见 [DESIGN.md](DESIGN.md)，文档权威层级见 [Documentation Governance](docs/DOCUMENTATION_GOVERNANCE.md)。

事实冲突时按以下顺序处理：当前 Issue / PR 已批准范围、L1 核心规范、L2 专项规范、L3 执行治理、L0 摘要、L4 参考资料。代码与验证证据决定 Implementation 状态；发现冲突时修正低权威来源，不自行猜测。

## 1. 默认基准

- 环境：Windows 11、PowerShell 7+、UTF-8。
- 开发方式：Web-first、Docker-first、Contract-first、Evidence-first。
- 主案例：**系外行星候选体与宿主恒星参数整合**。
- 优先级：主链路稳定 > 证据可信 > 可复现 > 自主评审可理解 > 功能扩展。
- 需求明确时直接执行；只改任务要求的部分；无法验证时写明原因。

## 2. 当前实现与后续边界

| 层级       | Current / Implemented                                                                                                                                                 | Pending                                   |
| ---------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------- |
| 前端       | `apps/site` Astro Brand Site、`apps/workspace` React Research Workspace、A-03 Tour/Workspace/Share Fixture + HTTP Port、真实 Browser/刷新恢复、共享包和根 pnpm 工具链 | A-02 视觉系统收口                         |
| API        | `/api/v1` Task 契约；`/api/v2` M1 核心 Runtime（27-operation 公开 Authoring Chain）、PostgreSQL 权威读取与 X-01 真实集成                                                                                   | M2 科研能力                               |
| 后端与数据 | 当前应用、v2 Application / Persistence、Pipeline 与 PostgreSQL 基线                                                                                                   | M2 科研 Pipeline 扩展，不改变既有科研边界 |
| 本地环境   | Compose：`site`、`workspace`、`api`、`migrate`、`postgres`；独立 X-01 Browser 集成入口                                                                                | 生产部署拓扑按独立 Issue 定义             |

规则：

- A-01 已实现运行时、路由、共享包边界、工具链、CI 与 Compose；A-03/X-01 由后续独立实现和真实集成证据完成，不等于 A-02 或 M2 产品能力已实现。
- A-03 已在同一套 Tour、Workspace 和匿名 Share 组件上验证 Fixture / HTTP Repository Port，并有组件、Fixture E2E 与独立真实 HTTP Browser/Compose 证据。
- `/api/v2` M1 Runtime 与 X-01 真实集成已实现；Snapshot/Share 记录仍为进程生命周期存储，M2 科研 Pipeline 与跨实例持久化不在该结论内。
- 本文件不授权在无对应 Issue 时安装 Three.js、React Three Fiber、GSAP、状态库、Tauri 或新增业务依赖。
- `apps/site` 与 `apps/workspace` 不得重复实现同一业务状态；共享能力进入职责明确的 Package。

## 3. 技术栈红线

- 前端统一 Node.js 24.18.0、pnpm 11.13.1、单一根 `pnpm-lock.yaml`、TypeScript strict。
- TypeScript 当前固定 6.0.3；只有 `typescript-eslint` 与 Astro 检查工具共同支持 TypeScript 7 后才能升级。
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
- 当前代码与规划文档冲突时，以运行证据为准并明确“Current / Implemented / Pending”，不得猜测完成状态。
- 不把 Fixture、缓存或模型推断包装成真实科研结论。
- 不保存或展示模型私有 chain-of-thought；ReasoningTrace 只含可审查依据、条件和引用。

## 5. Git 与 PR

- 到 GitHub Issues 中查看已明确指派给自己的未关闭任务，即 Assignee 包含自己的 Issue。开始前完整阅读任务的目标、范围、依赖、边界和验收标准；未明确指派的任务不要自行开工。本条约束从 GitHub 任务池自行领取工作，不改变用户在当前会话直接下达明确任务的授权效力。Assignee、任务执行人、模块 Owner 或风险 Owner 不因此获得额外 PR 审查权或合并审批权。
- 从 `main` 建分支，不直接推送 `main`；不 reset、force push 或改写远端历史。
- Commit 一个主要目的，使用 `feat` / `fix` / `docs` / `chore` 前缀。
- PR 关联明确 Issue，或在 PR 描述中记录用户在当前会话直接下达的明确授权；不得为了满足形式要求创建无关 Issue。PR 说明范围、验证、契约/数据/UI/部署/安全影响和材料口径。
- 本地 Codex 完成实现、验证、Commit、Push 并创建或更新 Draft PR 后，必须按 [Contributing §5](CONTRIBUTING.md#5-正式技术-review-责任) 获取绑定当前 HEAD 的正式技术 Review；实施过程中的自审不能替代正式 Review，HEAD 变化会使旧 Review 失效。
- 合并必须满足 [Contributing §6](CONTRIBUTING.md#6-合并标准) 与 [Review Checklist §10](docs/quality/REVIEW_CHECKLIST.md#10-合并条件)。最低条件是当前 HEAD 的 `pr_technical_review` 为 `PASS`、标准 CI 全绿、PR 可合并且没有未解决的真实阻塞问题；否则不得转 Ready、合并或关闭关联 Issue。
- 工作区存在无关修改时不得擅自暂存、清除或提交。

## 6. 模块边界

| 岗位         | 当前目录                                                                                                                                          | 核心职责                                                           |
| ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| A 前端与产品 | `apps/site`, `apps/workspace`, `packages/design-tokens`, `ui`, `domain`, `contracts`, `data-access`, `workspace-core`, `visual-engine`, `testing` | Brand Site、Guided Tour、Workspace、Domain Adapter、视觉与前端门禁 |
| B 后端与编排 | `apps/api`, `packages/schemas`, `scripts`                                                                                                         | v1 稳定性、v2 API、Run Workflow、Schema、Session / Share、安全     |
| C 数据       | `services/data_pipeline`, `samples/outputs`                                                                                                       | 数据源、清洗、单位、质量、SourceSnapshot、Evidence、导出           |
| D 论文与图谱 | `services/paper_pipeline`, `services/graph_pipeline`, `packages/prompts`                                                                          | 论文获取、Summary、Claim/Relation/Trace、Graph 与 Evidence         |
| X 基建       | 根目录、`.github`, `docs/setup.md`                                                                                                                | Compose、CI、环境变量、版本锁定和验证                              |

详细依赖方向以 [MODULES.md](docs/architecture/MODULES.md) 为准。

## 7. 文档同步红线

| 改动                         | 必须同步                                                                |
| ---------------------------- | ----------------------------------------------------------------------- |
| 接口、响应、错误、授权       | `docs/architecture/API_CONTRACT.md`                                     |
| 实体、字段、枚举             | `docs/architecture/DATA_MODEL.md`                                       |
| 状态、重试、取消、缓存、派生 | `docs/architecture/WORKFLOW_DESIGN.md`                                  |
| Artifact、版本、来源、分享   | `docs/architecture/DATA_VERSIONING.md`                                  |
| 前端架构与目录               | `DESIGN.md`, `docs/architecture/FRONTEND_ARCHITECTURE.md`, `MODULES.md` |
| 品牌、Token、字体、WebGL     | `docs/design/VISUAL_LANGUAGE.md`                                        |
| 首页、Tour、Workspace        | `docs/design/WORKSPACE_UX.md`                                           |
| 启动、Docker、环境变量       | `docs/setup.md`, `DEPLOYMENT.md`, `.env.example`                        |
| 产品范围与验收               | `PRD.md`, `docs/product/ACCEPTANCE.md`                                  |
| 风险与安全                   | `docs/quality/RISK_REGISTER.md`, `SECURITY.md`                          |

## 8. 验证要求

| 类型                     | 最低要求                                                                                                                                         |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| Foundation               | `python scripts/check_foundation.py`                                                                                                             |
| Compose                  | `docker compose config`；运行变更时 `docker compose up --build --wait`                                                                           |
| A-01 前端                | frozen root install、format、lint、typecheck、test、build、E2E、architecture、legacy checks                                                      |
| Brand Site               | 当前静态 HTML 含中文标题、说明、Workspace CTA 与 404；A-02 目标为极简单英雄首页 + bluegray Token，另验收                                         |
| Workspace                | 四个路由、Not Found、Error Boundary、Loading fallback、键盘导航；Fixture 与真实 HTTP Browser 的 Tour/Workspace/Share、冲突、刷新恢复和匿名 Share |
| Visual Engine（Pending） | High/Medium/Low、deterministic seed、freeze time、pause/dispose、Poster、Reduced Motion                                                          |
| Adapter                  | Fixture / HTTP 返回同一 Domain Model，一致性测试通过                                                                                             |
| 后端                     | `uv sync --frozen` + pytest；错误与权限场景覆盖                                                                                                  |
| 科研可信                 | Summary、Relation、Trace、GraphEdge 均按契约绑定 Evidence                                                                                        |

无法执行上一级验证时说明原因和降级验证，不得用“应该可以”代替结果。

## 9. UI 与视觉红线

- 只实现浅色系统；Raw Color 只在 design-tokens，业务组件只用语义 Token。
- 禁止黑底星空、霓虹蓝紫、强发光、大面积渐变、玻璃拟态和通用大圆角 Card 墙。
- 工作台以科研产物为中心，不以聊天气泡、工具日志、IDE 或无限窗口为中心。
- Canvas 必须有 DOM 内容和 Poster，支持 Reduced Motion、页面隐藏暂停与 GPU dispose；不得用大量 DOM glyph 实现 ASCII / Dither。
- 字体二进制提交前必须记录来源、可再分发许可证、中文覆盖与加载策略。

## 10. Fixture、运行来源与科研可信

- `execution_mode`: `demo_replay | live`，只属于 Run 与启动状态；`source_mode`: `fixture | live | cached`；修订由 revision Run 或 supersedes 关系推导。
- Fixture 版本化并包含 scenario、schema version 和 provenance note。
- Cached 只能引用真实历史 Run、ArtifactVersion 与 SourceSnapshot。
- seed list 仅用于 benchmark、Fixture 或人工校验，不能冒充自动获取。
- 模型输出必须经过 Schema 与 Evidence 校验；无 Evidence / Trace 的关系只能作为候选。
- GraphEdge 全部绑定 Evidence，跨文献边再绑定 Relation / ReasoningTrace。

## 11. 材料口径

唯一提交顺序见 [docs/handoff/README.md](docs/handoff/README.md)。只交付真实系统素材、明确 Fixture 或可定位真实运行缓存；未实现能力只能写 Proposed、Pending、规划或预留。

禁止宣传：任意天文方向、任意 PDF 全文解析、任意图表全自动解析、无边界 AI Scientist、无证据科学发现。
