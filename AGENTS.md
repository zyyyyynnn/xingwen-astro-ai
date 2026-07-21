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

| 层级       | Current / Implemented                                                                           | Pending                                                 |
| ---------- | ----------------------------------------------------------------------------------------------- | ------------------------------------------------------- |
| 前端       | `apps/site` Astro Brand Site、`apps/workspace` React Research Workspace、共享包和根 pnpm 工具链 | A-02 视觉系统与静态框架；A-03 Contract 双通道与业务行为 |
| API        | `/api/v1` Task 契约                                                                             | `/api/v2` Project / Run / Artifact / Version            |
| 后端与数据 | 当前应用、Pipeline 与 PostgreSQL 基线                                                           | 增加 v2 Application / Persistence，不改变既有科研边界   |
| 本地环境   | Compose：`site`、`workspace`、`api`、`postgres`                                                 | 生产部署拓扑按独立 Issue 定义                           |

规则：

- A-01 已实现运行时、路由、共享包边界、工具链、CI 与 Compose；不等于 A-02/A-03 产品能力已实现。
- A-02、A-03 和 `/api/v2` 必须保持 Pending，直到对应代码、测试与运行证据存在。
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

- 从 `main` 建分支，不直接推送 `main`；不 reset、force push 或改写远端历史。
- Commit 一个主要目的，使用 `feat` / `fix` / `docs` / `chore` 前缀。
- PR 关联 Issue，说明范围、验证、契约/数据/UI/部署/安全影响和材料口径。
- 本地 Codex 完成实现、验证、Commit、Push 并创建或更新 Draft PR 后，必须等待网页端 GPT Review；本地自审不能替代正式 Review。
- 网页端 GPT Review 必须绑定当前 HEAD，明确 `PASS | BLOCKED` 并保存 GitHub 可见记录；HEAD 变化后旧 Review 自动失效。
- 只有当前 HEAD 的网页端 GPT `PASS` 与 CI 均通过后，仓库负责人才能将 Draft 转为 Ready 并 Squash merge；Codex 不得自行转 Ready、合并或关闭 Issue，失败卡口不得绕过。
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

| 类型                     | 最低要求                                                                                       |
| ------------------------ | ---------------------------------------------------------------------------------------------- |
| Foundation               | `python scripts/check_foundation.py`                                                           |
| Compose                  | `docker compose config`；运行变更时 `docker compose up --build --wait`                         |
| A-01 前端                | frozen root install、format、lint、typecheck、test、build、E2E、architecture、legacy checks    |
| Brand Site               | 当前静态 HTML 含中文标题、说明、Workspace CTA 与 404；A-02 SEO/视觉细节另行验收                |
| Workspace                | 当前四个最小路由、Not Found、Error Boundary、Loading fallback、键盘导航；A-03 业务行为另行验收 |
| Visual Engine（Pending） | High/Medium/Low、deterministic seed、freeze time、pause/dispose、Poster、Reduced Motion        |
| Adapter（Pending）       | Fixture / HTTP 返回同一 Domain Model，一致性测试通过                                           |
| 后端                     | `uv sync --frozen` + pytest；错误与权限场景覆盖                                                |
| 科研可信                 | Summary、Relation、Trace、GraphEdge 均按契约绑定 Evidence                                      |

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
