# Architecture Decisions

| 元数据    | 值                                   |
| --------- | ------------------------------------ |
| Status    | Accepted                             |
| Authority | 已批准架构决策、替代关系与不可逆取舍 |

本文保留决策历史。`Accepted` 表示决策有效，不表示代码已经全部实现；目标能力的实施状态以对应规范、Issue 和运行证据为准。

## 1. 状态索引

| ADR     | 状态                           | 当前含义                                               |
| ------- | ------------------------------ | ------------------------------------------------------ |
| 001     | Accepted                       | MVP 固定主案例                                         |
| 002     | Superseded in model by ADR-027 | 单一科研链原则保留，ResearchTask 模型被取代            |
| 003     | Accepted                       | 模型调用统一走后端                                     |
| 004     | Accepted                       | 模块使用生成的结构化 Contract                          |
| 005     | Refined by ADR-023/027         | 真实历史缓存可兜底，但按 Run/Version 规则选择          |
| 006     | Accepted                       | GraphEdge 必须有 Evidence                              |
| 007     | Superseded by ADR-023/027      | 缓存非状态原则保留，旧字段表达被取代                   |
| 008     | Accepted                       | Evidence 可定位、核验和复现                            |
| 009     | Refined                        | C-01/D-01 先产出，X-00 再集成冻结                      |
| 010     | Accepted                       | 自动论文获取属于 MVP 主链路                            |
| 011     | Accepted                       | 跨文献推理必须结构化                                   |
| 013     | Accepted                       | Docker Compose 使用 Site、Workspace、API 与 PostgreSQL |
| 014     | Accepted                       | pnpm 与 uv 固定                                        |
| 015     | Accepted                       | 队列和复杂中间件后置                                   |
| 016     | Superseded in model by ADR-027 | 显式状态机原则保留，目标对象改为 ResearchRun           |
| 017     | Accepted                       | Pydantic / OpenAPI 为 Transport Contract 编写源        |
| 018     | Accepted                       | Prompt 不可变版本化                                    |
| 019     | Superseded in part by ADR-027  | 追加式版本原则保留，运行对象重新分层                   |
| 020     | Accepted                       | 暂不引入通用图数据库和万能实体层                       |
| 021     | Implemented                    | Astro Brand Site + React Workspace Monorepo 运行时     |
| 022–027 | Accepted；Pending              | 产品体验、领域与安全方案                               |
| 028     | Superseded by ADR-029          | 浅色雾霾蓝视觉体系（已由 bluegray 取代）              |
| 029     | Accepted；Pending              | 浅色 bluegray 视觉 + Brand Site 极简单英雄首页         |
| 030     | Accepted for implementation    | 无版本化单面 API（/api/*）与追加式演进                 |

## ADR-001：MVP 固定主案例

**Status:** Accepted

**Decision:** MVP 固定为“系外行星候选体与宿主恒星参数整合”。

**Rationale:** 稳定案例才能形成真实数据、论文、推理、图谱和复现闭环。

**Consequence:** 其他天文方向只作为后续扩展，不影响当前 Contract 和验收。

## ADR-002：核心功能形成单一科研链

**Status:** Superseded in model by ADR-027

**Decision:** 数据、论文、总结、推理和图谱围绕同一研究上下文串联，不做孤立功能页。

**Rationale:** 完整可核验链路比功能堆叠更有产品和科研价值。

**Replacement:** 原 `ResearchTask` 聚合模型由 Project / Contract / Run / Artifact / Version 分层取代。

## ADR-003：模型调用统一走后端

**Status:** Accepted

**Decision:** 所有生产模型调用经过后端 Model Client、Application Service 和准入流程。

**Rationale:** 统一认证、超时、重试、日志、Schema、Evidence 和版本记录。

**Rejected:** 前端直连模型；Router 或临时脚本维护生产调用。

## ADR-004：模块间使用结构化 Contract

**Status:** Accepted

**Decision:** Transport Contract 由 Pydantic / OpenAPI / JSON Schema 生成；前端映射为稳定 Domain Model。

**Rationale:** 减少 A/B/C/D 并行开发中的字段和错误语义漂移。

**Consequence:** 不允许组件、Pipeline 或测试各自维护第二套同名生产类型。

## ADR-005：公网体验允许真实历史缓存兜底

**Status:** Refined by ADR-023 and ADR-027

**Decision:** Live 发生可恢复失败时，可以展示与当前 Contract、输入、质量和 Evidence 匹配的真实历史 ArtifactVersion。

**Rationale:** 保证演示稳定，同时不伪造实时科研结果。

**Consequence:** CacheRecord 必须绑定 origin Run、Version、SourceSnapshot 和选择原因；Fixture/seed 不属于缓存。

## ADR-006：GraphEdge 必须绑定 Evidence

**Status:** Accepted

**Decision:** 所有 GraphEdge 绑定 Evidence；跨文献边额外绑定 Accepted Relation 和 ReasoningTrace。

**Rationale:** Graph 是科研证据组织，不是装饰性可视化。

**Consequence:** 无完整引用的边不得发布到最终 Graph ArtifactVersion。

## ADR-007：缓存不是 Run 状态

**Status:** Superseded in representation by ADR-023 and ADR-027

**Decision:** 流程状态、执行方式、产物来源和修订关系分别表达。

**Rationale:** 把缓存写入状态机会混淆运行事实和结果来源。

**Replacement:** 目标模型使用 ResearchRun.status、execution_mode、ArtifactVersion.source_mode 和派生关系。

## ADR-008：Evidence 必须可定位、核验、复现

**Status:** Accepted

**Decision:** Evidence 记录 target、SourceSnapshot、locator、quote/value、extraction method、confidence 和版本关系。

**Rationale:** 单一来源链接不足以复现字段值、论文结论或推理关系。

**Consequence:** Evidence 创建和引用完整性属于 Artifact 发布门。

## ADR-009：先产出基准，再集成冻结

**Status:** Refined

**Decision:** C-01 产出 Case / Field Manifest，D-01 产出论文与推理 Benchmark，X-00 负责跨模块集成冻结。

**Rationale:** 避免循环依赖，同时让数据和论文团队可并行形成机器可校验输入。

**Consequence:** B-04、A-03 和后续 Pipeline 消费 X-00 冻结版本，不自行复制基准。

## ADR-010：自动论文获取属于 MVP 主链路

**Status:** Accepted

**Decision:** 固定主案例内实现可复现论文检索、候选 canonicalization、去重、排序和选择依据。

**Rationale:** 智能文献总结不能依赖手写清单冒充自动能力。

**Boundary:** Seed 只用于 Benchmark、Fixture 或人工校验。

## ADR-011：跨文献推理必须结构化

**Status:** Accepted

**Decision:** 推理落到 Claim、candidate/accepted/rejected Relation、ReasoningTrace 和 Evidence。

**Rationale:** 自然语言解释无法稳定审查、评测、版本化或生成可信 Graph。

**Boundary:** 不记录模型私有 chain-of-thought。

## ADR-013：Docker-first 本地基线

**Status:** Accepted

**Decision:** 当前本地统一使用 `site`、`workspace`、`api`、`postgres` Compose 服务；前端固定 Node.js 24.18.0 与 pnpm 11.13.1，后端固定 Python 3.13 与 uv。

**Rationale:** 降低成员本机版本和网络差异。

**Consequence:** Site 与 Workspace 分别健康检查；公网拓扑仍由独立部署 Issue 验证。

## ADR-014：依赖管理工具固定

**Status:** Accepted

**Decision:** 前端使用 pnpm 和单一 lockfile；后端使用 uv、`pyproject.toml` 和 `uv.lock`。

**Rationale:** 统一依赖解析、缓存、CI 和复现方式。

**Rejected:** npm/yarn/bun lockfile 混用；以 requirements.txt 替代 uv 主流程。

## ADR-015：队列与复杂中间件后置

**Status:** Accepted

**Decision:** 在真实负载证明必要前，不将 Redis、Celery、RabbitMQ、对象存储、图数据库或向量数据库设为 MVP 前置。

**Rationale:** 当前主要风险是可信链路和集成，而非基础设施容量。

**Consequence:** 新基础设施需要独立 ADR、负载证据和迁移/回滚计划。

## ADR-016：工作流由显式状态机驱动

**Status:** Superseded in model by ADR-027; principle remains accepted

**Decision:** 状态转换集中定义和校验；Router 不串联 Pipeline，Pipeline 不推进主状态。

**Rationale:** 防止非法跳转、失败丢失和缓存/修订语义混乱。

**Replacement:** 目标状态机围绕 ResearchRun、RunStep、StepAttempt 和 RunEvent。

## ADR-017：Pydantic 是 Contract 编写源

**Status:** Accepted

**Decision:** 后端 Pydantic 模型生成 OpenAPI 3.1 / JSON Schema 和前端 Transport Type。

**Rationale:** 避免并行手写 DTO，保留可重复导出和 stale check。

**Consequence:** `packages/schemas` 记录导出边界；A-01 已建立 `packages/contracts` 公开入口，生成 Type、validation 与 mapper 由 A-03 实现。

## ADR-018：Prompt 文件不可变版本化

**Status:** Accepted

**Decision:** 生产 Prompt 位于 `packages/prompts/<name>/vN.md`，由 registry 选择默认版本。

**Rationale:** Prompt 是科研产物的生成条件，必须可复现和回滚。

**Consequence:** 已被运行、Version、Benchmark 或 CacheRecord 引用的 Prompt 不原地改写。

## ADR-019：科研产物采用追加式版本治理

**Status:** Superseded in part by ADR-027

**Decision:** Dataset、Summary、Claim、Trace、Graph 和 Export 的修订创建新 ArtifactVersion。

**Rationale:** 原地覆盖无法解释历史截图、缓存、模型升级和人工修订。

**Replacement:** ResearchRun 管理工作流；ProducerExecution 记录具体模型/算法；ArtifactVersion 管理内容。

## ADR-020：暂不引入通用图数据库与万能实体层

**Status:** Accepted

**Decision:** MVP 使用 PostgreSQL/JSON 和明确 Graph Contract；只有真实规模和查询模式证明需要时再评估专用图存储。

**Rationale:** 过早抽象增加迁移和联调成本，不能解决当前 Evidence 完整性问题。

## ADR-021：Astro Brand Site + React Workspace

**Status:** Implemented for A-01 runtime

**Context:** 品牌静态首屏、SEO、WebGL 场景和桌面级工作台具有不同运行特征。

**Decision:** pnpm Monorepo；`apps/site` 使用 Astro 静态输出，`apps/workspace` 使用 React 与 Vite；共享 `design-tokens`、`ui`、`domain`、`contracts`、`data-access`、`workspace-core`、`visual-engine` 和 `testing`。

**Consequences:** Brand Site 与 Research Workspace 分离构建，共享包依赖方向由自动门禁约束；A-02/A-03 继续在该边界内实现。

**Rejected:** 无明确需求的全站 Next.js；用 Astro Islands 承载完整工作台。

**Boundary:** A-01 只实现运行时、最小路由、共享包、CI 和 Compose，不代表 A-02 视觉系统或 A-03 业务行为完成。

## ADR-022：工作台采用科研产物优先

**Status:** Accepted for implementation; Pending

**Decision:** Research Atlas、最多三面板 Research Canvas、Provenance Observatory 和 Research Console 构成核心工作台；中央默认显示科研产物。

**Rationale:** 聊天线程和工具日志无法稳定承载高密度数据、Evidence 和版本对照。

**Rejected:** 聊天气泡主界面；IDE / terminal 模仿；无限自由窗口。

## ADR-023：Fixture / HTTP 通过 Repository Port 共享 Domain

**Status:** Accepted for implementation; Pending

**Decision:** UI 通过 Application Service 和 Repository Port 获取 Domain；Fixture 与 HTTP Adapter 校验同一 Contract。execution、source 和 revision 分离。

**Rationale:** Demo、测试和 Live 复用组件，真实性语义可自动测试。

**Boundary:** Fixture 带 scenario、Schema 和 provenance；Cached 只引用真实历史 Run。

## ADR-024：ASCII / Dither 使用 GPU 实时渲染和确定性降级

**Status:** Accepted for implementation; Pending

**Decision:** Three.js、React Three Fiber、自定义 GLSL、glyph atlas 和 instancing；使用 deterministic seed、质量档和 Poster fallback。

**Rationale:** 大量 DOM glyph 不可控，纯预渲染视频无法响应状态。

**Boundary:** WebGL 不承载唯一信息，不阻塞 LCP；页面隐藏暂停，卸载释放资源。

## ADR-025：Web 当前交付，Tauri 后置

**Status:** Accepted for implementation; Pending

**Decision:** 当前只交付 Web；文件、通知、本地缓存和深链接通过 Platform Port 注入，未来 Tauri 替换 Adapter。

**Rationale:** 避免当前扩大构建、签名、权限和发布风险。

**Boundary:** 未经独立 Issue 不创建 `apps/desktop` 或引入 Tauri。

## ADR-026：免登录隔离 Session 与只读分享

**Status:** Accepted for implementation; Pending

**Decision:** 匿名 ResearchSession 使用安全 Cookie 和服务端 ownership；ShareSnapshot 锁定 Version/Evidence，token 高熵、可撤销、可过期且服务端只存 hash。

**Rationale:** 降低评审进入门槛，同时隔离私有研究和编辑权限。

**Rejected:** 强制账号；把 Session id 放入分享 URL；分享动态 latest。

## ADR-027：Project / Run / Artifact / Version 分层

**Status:** Accepted for implementation; Pending

**Decision:** Project 表示持续上下文，Contract 表示不可变输入，Run 表示一次执行，Artifact 表示逻辑身份，ArtifactVersion 表示不可变内容；retry/revision/fork 创建派生 Run。

**Rationale:** 支持并行运行、失败重试、缓存、修订、分享和历史对照。

**Rejected:** 覆盖 Task 结果；以聊天线程作为项目；只增加字符串 version。

## ADR-028：纯浅色雾霾蓝视觉体系

**Status:** Superseded by ADR-029

**Decision:** 冷淡灰基底、低饱和雾霾蓝品牌色、深蓝灰文字和独立状态色；只实现浅色系统，使用 OKLCH Raw Scale 与语义 Token。

**Rationale:** 提高文献、数据和 Evidence 阅读质量，控制视觉与回归范围。

**Rejected:** 同期深浅双主题；黑底星空；大面积霓虹、渐变和发光。

**Boundary:** 业务组件不硬编码 Raw Color；状态不只靠颜色；字体资产提交前验证许可、来源、字符覆盖和加载策略。

**Superseded because:** brand / ink / border / celestial 分属 haze 与 gray 两套色板后易漂移；首页叙事过载。由 ADR-029 统一为 bluegray 单刻度，并收束 Brand Site 信息密度。

## ADR-029：浅色 bluegray 视觉体系与极简单英雄首页

**Status:** Accepted for implementation; Pending

**Decision:**

- 只实现浅色系统。Cold Paper（hue 230）仅服务 canvas / surface；brand、ink、border、celestial 共用 **bluegray** 刻度（hue 235，chroma 约 0.006–0.026）。
- 主题色锚点 `#6E7981` = `oklch(0.57 0.018 235)` = bluegray-500。
- 状态色保留独立色相；业务组件只消费语义 Token，Raw 仅在 `packages/design-tokens`。
- Brand Site 首页为**单英雄区极简入口**：偏轴系外行星 ASCII/Dither Hero、双短 CTA（开始演示 / 进入工作台）、一句主标题、三至四段无标题短注。
- 多幕叙事职责归属 Guided Tour；Live 仅在 Tour 或启动门选择。

**Rationale:** 单一色相刻度避免配色漂移；首页克制留白提升竞赛场景下的识别与转化；复杂可信说明放到 Tour 与工作台，避免首屏信息堆砌。

**Rejected:** haze 与 gray 双色板并存；黑底星空；高饱和蓝紫网点；首页滚动四幕或 PRD 参数墙；首页 Live 模式开关。

**Boundary:** 文档冻结不等于 Implemented；A-01 运行时 Token 可能仍为旧子集，以代码与测试证据为准。WebGL Hero、完整 Token 落地与视觉回归由 A-02 交付。字体资产提交前验证许可、来源、字符覆盖和加载策略。

**See also:** [Visual Language](../design/VISUAL_LANGUAGE.md), [Workspace UX](../design/WORKSPACE_UX.md) §2.1 / §2.4。

## ADR-030：无版本化单面 API（/api/*）

**Status:** Accepted for implementation

**Context:** 早期 `/api/v1`（Pipeline 任务基线）与 `/api/v2`（M1 核心 Runtime）以 URL 版本段区分同一套演进中的 API。消费方仅为仓库内 `apps/workspace` 与 `apps/site`，无外部客户端，URL 版本段带来的分叉成本高于收益。

**Decision:** 硬切换收口为单一无版本面 `/api/*`，无兼容别名：

- 全部路径打平到语义化顶级资源（Session / Project / Contract / Run / Artifact / Evidence / Source / Workspace / Share / Health / Task）；契约草稿与契约收敛到 `/api/contracts/drafts/{id}` 与 `/api/contracts/{id}`；公共分享读收敛到 `/api/public/shares/{token}`。
- 安全面**默认拒绝**：`/api/*` 一律需匿名会话，仅 health、tasks、docs、openapi、匿名 session-create 与 `public/shares/{token}` 读在白名单内免鉴权；分类集中于 `app.api_surface`。
- 演进采用**追加式（Additive Only）**：只允许新增端点、新增可选字段或新 Query 参数；禁止删除或重命名现有字段。字段废弃用 Pydantic / OpenAPI `deprecated=True`（经既有生成管线自动流入 JSON Schema 与 `dto.ts`）并可选输出 `Deprecation` / `Sunset` 响应头，绝不通过变更 URL 版本号断代。
- 演进钩子 `app.api_surface.DEPRECATED_OPERATIONS` 为空时不挂载任何废弃头中间件，请求热路径零成本；首次废弃再启用。

**Rationale:** 单面消除版本分叉与“冻结 v2”表述的歧义；追加式 + 既有三重门禁（committed generated schema、`--check` 导出、运行时↔契约 App parity）在评审中以红 diff 机械拦截破坏性变更；`/api/public/*` 命名约定使新增匿名读无需再改中间件。

**Consequence:** 取代此前“冻结的 /api/v2 契约面”表述；`docs/architecture/API_CONTRACT.md` 按 Core APIs 与 Pipeline APIs 组织；生成目录、同步脚本与导出符号去版本化（`core`、`sync_contracts`、`CoreModelName` 等）。会话 Cookie 作用域由 `/api/v2` 扩为 `/api`（set 与 delete 同步）。切换时存量匿名会话一次性失效：持有 `/api/v2` 作用域 Cookie 的浏览器不会向 `/api/sessions` 发送该凭据，恢复无法触发，旧 Cookie 在会话 TTL 内自行过期。作用域扩大后 HttpOnly 凭据也会随请求发送到 `/api/health` 与 `/api/tasks*`，但这些端点不消费会话，无授权或 CSRF 后果。

**Rejected:** 保留 v1/v2 别名或双挂载；用 URL 版本号表达破坏性变更；跨模块搬迁端点归属（保持按域扁平）。

**Boundary:** 不触碰 Alembic 迁移文件（revision id 不可变）；文档冻结不等于 Implemented，以代码与运行证据为准。

## 2. 新增与修改规则

- 新的不可逆、高迁移成本或跨模块决策使用下一个 ADR 编号。
- 修改现行决策时优先新增 ADR 并标记 `Superseded by`，不重写历史。
- 状态变化同步相关规范、Backlog、Issue 和迁移说明。
- ADR 不替代实现证据；只有代码、测试和运行通过后，能力才可标记为 Implemented。
