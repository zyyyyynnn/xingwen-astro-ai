# Architecture Decisions

## ADR-001：MVP 固定主案例

| 状态 | Accepted |
| --- | --- |

MVP 固定为“系外行星候选体与宿主恒星参数整合”。

原因：主案例越稳定，越容易形成真实数据、论文获取、文献总结、跨文献推理、证据图谱和演示闭环。任意天文方向支持后置。

## ADR-002：核心功能串成一条科研工作流

| 状态 | Accepted |
| --- | --- |

自动化数据分析、自动论文获取、智能文献总结、跨文献逻辑推理和学术图谱可视化围绕同一个 `ResearchTask` 串联，不做孤立功能页。

原因：比赛评审更关注完整科研支撑能力，而不是功能堆叠。

## ADR-003：模型调用统一走后端

| 状态 | Accepted |
| --- | --- |

所有 Qwen / 百炼调用必须经过后端 Qwen Client。

原因：保护 API Key，统一超时、重试、缓存、日志和 JSON Schema 校验。

## ADR-004：模块间统一结构化契约

| 状态 | Accepted |
| --- | --- |

前端、后端、数据、文献、推理、图谱模块共享 `API_CONTRACT.md` 和 `DATA_MODEL.md`。

原因：允许 4 人并行开发，减少联调时字段漂移。

## ADR-005：公网 Demo 必须有真实运行缓存兜底

| 状态 | Accepted |
| --- | --- |

外部数据源、论文源或模型失败时，Demo 可展示最近一次真实运行缓存，并明确标注缓存状态。

原因：保证演示稳定，同时不把手写假数据包装成真实结果。

## ADR-006：图谱边必须绑定证据

| 状态 | Accepted |
| --- | --- |

GraphEdge 必须包含 `evidence_ids`。跨文献关系边还必须包含 `relation_id` 和 `reasoning_trace_id`。

原因：图谱是科研证据组织能力，不是装饰性可视化。

## ADR-007：缓存是元信息，不是主任务状态

| 状态 | Accepted |
| --- | --- |

缓存命中通过 `meta.cached`、`ResearchTask.used_cache`、`SourceRecord.cached` 和页面提示表达，不再使用 `using_cache` 作为 `task_status`。

原因：任务状态描述流程阶段，缓存描述结果来源。两者混用会让前端状态流、验收截图和后端状态机都变复杂。

## ADR-008：Evidence 必须可定位、可核验、可复现

| 状态 | Accepted |
| --- | --- |

`Evidence` 除 `source_id` / `paper_id` 外，还需要记录 `locator`、`quote_or_value`、`extraction_method` 和 `source_snapshot`。

原因：比赛评审关注“可溯源”时，不只看有没有来源链接，还会看证据能否定位到字段、文本、查询、论文获取记录或缓存版本。

## ADR-009：P0 先对齐最小真实依据，再并行推进

| 状态 | Accepted |
| --- | --- |

P0 第一步是 `X-00`：冻结 MVP 字段清单、论文获取来源、检索关键词、5-8 篇 seed list、跨文献关系类型和 Graph 最小关系类型。随后先完成 `X-04` Docker Compose 本地开发基线，再让 A/B 并行初始化前后端，C/D 提供最小真实依据。

原因：纯手写 Fixture 会削弱科研可信度；完全串行又会拖慢开发节奏；没有统一 Docker 基线会造成成员本机依赖和版本漂移。

## ADR-010：自动论文获取纳入 MVP 主链路

| 状态 | Accepted |
| --- | --- |

MVP 必须在固定主案例内实现自动论文获取，输出 `PaperSearchQuery`、`PaperAcquisitionRun` 和 `PaperCandidate`。seed list 只能作为兜底、评测基准和人工校验。

原因：自动论文获取是“智能文献总结”的前置核心能力，不能只依赖手写文献清单冒充系统能力。

## ADR-011：跨文献逻辑推理必须结构化

| 状态 | Accepted |
| --- | --- |

跨文献逻辑推理必须落到 `LiteratureClaim`、`LiteratureRelation` 和 `ReasoningTrace`，并绑定 `Evidence`。无证据关系只能作为候选，不进入最终图谱。

原因：“逻辑推理”如果只输出自然语言解释，无法审查、无法复现，也无法支撑自主评审或终审展示中的可信性追问。

## ADR-012：Web-first 与 shadcn-vue 优先

| 状态 | Superseded by ADR-021 |
| --- | --- |

前端先完成 `apps/web` 页面、路由、状态、Mock 工作流和 UI token 落地。UI 组件优先采用 shadcn-vue / reka-ui 体系，图谱主库采用 Vue Flow，统计图表按需使用 ECharts。

原因：先形成可演示 Web 闭环，再抽象复用组件，能降低早期不确定性；成熟组件库能减少基础控件成本，同时保持视觉一致性。

历史说明：该决策已完成当前 `apps/web` Vue 骨架使命。目标前端不再以 Vue、shadcn-vue、Vue Router、Pinia 或 Vue Flow 作为未来方案；迁移完成前它们仍是当前可运行实现事实。

## ADR-013：Docker-first 本地开发基线

| 状态 | Accepted |
| --- | --- |

M1 本地环境统一使用 Docker Compose 管理 `web`、`api`、`postgres` 三个服务，固定 `node:24-alpine`、`python:3.13-slim`、`postgres:17-alpine`。

原因：4 人团队设备和本机依赖不一致，Docker Compose 可以把运行时、网络、端口和数据库版本固定为同一基线。

## ADR-014：依赖管理工具固定

| 状态 | Accepted |
| --- | --- |

前端统一使用 pnpm，后端统一使用 uv。提交 `pnpm-lock.yaml` 和 `uv.lock`；禁止混用 npm/yarn/bun lockfile 或用 requirements.txt 替代 uv 主流程。

原因：pnpm 更适合 Web-first 和后续 workspace；uv 统一 Python 版本、依赖和 lockfile。两者配合 Docker 能降低“本机可运行、他人不可运行”的风险。

## ADR-015：Celery / Redis 后置

| 状态 | Accepted |
| --- | --- |

M1 不引入 Redis、Celery、RabbitMQ。任务链路先用 FastAPI、数据库任务状态和 BackgroundTasks 支撑；当论文获取、模型调用或图谱构建耗时明显影响稳定性时，再评估 Redis + Celery/RQ。

原因：MVP 任务规模可控，过早引入任务队列会增加部署、调试和成员协作成本。

## ADR-016：工作流必须由显式状态机驱动

| 状态 | Accepted |
| --- | --- |

`ResearchTask` 的状态转换由 `app.workflow` 集中声明和校验。Router 不直接串联多个 Pipeline，Pipeline 不自行推进任务状态。

原因：把编排散落在 Router/Service 会导致非法跳转、失败记录丢失、缓存语义混乱和巨型业务文件。

## ADR-017：Pydantic 是 Phase 0 Schema authoring source

| 状态 | Accepted |
| --- | --- |

Phase 0 以 `apps/api/src/app/schemas` 作为契约编写源，通过 `scripts/export_schemas.py` 导出 JSON Schema 到 `packages/schemas` 或临时构建目录。前端和 Pipeline 不维护第二套同名字段。

原因：当前 Pydantic 模型已经存在，立即搬迁会制造双写和回归风险；先建立可重复导出，再按实际 codegen 需求评估独立 IDL。

## ADR-018：Prompt 文件不可变版本化

| 状态 | Accepted |
| --- | --- |

生产 Prompt 统一放在 `packages/prompts/<name>/vN.md`，由 registry 指定默认版本。已被真实运行或缓存引用的版本不原地改写。

原因：Prompt 是科研结果的生成条件，散落字符串和“最新版本”无法复现，也会造成缓存结果口径失真。

## ADR-019：科研产物采用追加式版本治理

| 状态 | Superseded in part by ADR-027 |
| --- | --- |

Dataset、Summary、Claim、Trace、Graph 和 Export 的修正通过新 ArtifactVersion 表达。追加式治理原则继续有效；原 `ExperimentRun` 名称仅代表当前迁移源，目标模型由 ADR-027 的 ResearchRun 负责工作流编排、ProducerExecution 记录具体模型或算法执行。Phase 0 先冻结契约，Phase 1–3 分步落库。

原因：只保存当前结果无法解释历史截图、模型升级差异、缓存来源和用户修正。

## ADR-020：MVP 暂不引入通用图数据库与万能实体层

| 状态 | Accepted |
| --- | --- |

MVP 继续使用 PostgreSQL/JSON 与现有 GraphNode/GraphEdge 契约。只有当真实图规模、查询模式或跨案例复用证明需要时，才评估 Neo4j、通用 Entity/Relation 或向量数据库。

原因：当前风险是可信闭环未跑通，而不是图存储性能。过早抽象会增加迁移和联调成本。

## ADR-021：前端迁移为 Astro 品牌站 + React 工作台

### Status

Accepted for implementation；Implementation Pending。Supersedes ADR-012 的目标前端部分。

### Context

当前 Vue 骨架能验证基础构建和 API 边界，但品牌静态首屏、SEO、React Three Fiber 实时视觉、桌面级多面板工作台与未来 Tauri 复用对运行时提出了不同要求。长期维护两套业务前端会造成契约和视觉漂移。

### Decision

目标前端采用 pnpm Monorepo：`apps/site` 使用 Astro 静态输出，`apps/workspace` 使用 React + TypeScript；共享能力进入 `packages/design-tokens`、`ui`、`visual-engine`、`domain`、`contracts`、`data-access`、`workspace-core` 和 `testing`。旧 `apps/web` 仅作为迁移期回退基线，完成验收后删除。

### Consequences

- 正向：静态首屏与复杂工作台职责分离；WebGL、React Flow 和未来 Tauri 共享 React 核心。
- 负向：团队需要承担一次性迁移和新工具链学习成本；迁移期 CI 需要短暂构建两套入口。
- 运维：仍输出静态站点与现有 FastAPI，不引入前端服务端渲染或新基础设施。

### Rejected alternatives

- 继续扩展单体 Vue：短期成本低，但会把品牌、工作台、视觉引擎和迁移适配耦合在一个应用。
- 全站 Next.js：当前没有服务端渲染和 React Server Components 的明确需求，运行与部署复杂度更高。
- Astro 承载完整工作台：Island 模型不适合统一管理高密度桌面状态。

### Implementation boundary

由 A-01 建立新运行时和共享包，不实现业务页面；迁移完成前不在新旧前端重复开发同一业务功能。本 RFC 不创建应用、不安装依赖、不修改 Docker。

## ADR-022：工作台采用科研产物优先，而非聊天优先

### Status

Accepted for implementation；Implementation Pending。

### Context

聊天线程和工具日志适合通用 Agent，但无法稳定承载 Dataset、Paper、Claim、Relation、ReasoningTrace、Graph、Evidence 与版本对照，也会弱化自主评审时的可信性。

### Decision

工作台以 Research Atlas、最多三面板 Research Canvas、Provenance Observatory 和底部 Research Console 组成。中央默认显示科研产物；自然语言交互只负责生成 Research Contract、结构化解释、运行或修订请求。

### Consequences

- 正向：核心结果可对照、可定位、可分享；产品不依赖对话历史才能理解。
- 负向：需要专门设计每类 Artifact 的视图与选择模型，初期组件数量高于聊天界面。

### Rejected alternatives

- 聊天气泡作为中央界面：无法支持高密度表格和证据并排审查。
- IDE / terminal 模仿：与科研产物领域不一致，增加无关认知负担。

### Implementation boundary

Research Console 不保存模型私有思维过程；原始执行日志仅用于诊断，不作为主要产物。

## ADR-023：Fixture / HTTP 双通道通过 Repository Port 共享领域契约

### Status

Accepted for implementation；Implementation Pending。

### Context

作品提交需要确定性 Demo Replay，真实运行又必须容纳网络失败、等待和缓存。页面直接读取 Fixture 或后端 DTO 会形成两套行为和真实性口径。

### Decision

UI 经 Application Service 调用 Repository Port；Fixture Adapter 与 HTTP Adapter 均校验 Transport Contract、映射为同一 Domain Model。`execution_mode` 与 `source_mode` 分离，Fixture 固定标记 `source_mode=fixture`。

### Consequences

- 正向：Demo、测试和 Live 复用组件；Adapter 一致性可自动测试。
- 负向：需要维护 Mapper 与版本化 Fixture，不能直接把响应交给页面。

### Rejected alternatives

- 组件内 `fetch` 与条件分支：难以隔离错误和来源语义。
- 将手写 Fixture 标为缓存：破坏真实运行缓存的可信性。

### Implementation boundary

Fixture 必须包含 scenario、schema version、生成说明和证据边界；Cached 只能引用真实历史 Run。

## ADR-024：ASCII / Dither 视觉引擎使用 GPU 实时渲染与确定性降级

### Status

Accepted for implementation；Implementation Pending。

### Context

品牌需要近看可辨 ASCII、远看形成连续半色调的天体纹理。大量 DOM glyph 会造成布局、性能和无障碍问题，WebGL 又可能因设备、驱动或 Reduced Motion 不可用。

### Decision

使用 Three.js、React Three Fiber、自定义 GLSL、glyph atlas 与 instancing 构建 `packages/visual-engine`。输入是可测试的 Visual Model，使用 deterministic seed；High / Medium / Low 档位和静态 Poster 保证降级。

### Consequences

- 正向：性能和品牌一致性可控；视觉回归可冻结 seed 与时间。
- 负向：Shader、GPU 生命周期与跨设备测试增加实施成本。

### Rejected alternatives

- 成千上万个 DOM 字符：性能、读屏和缩放不可控。
- 预渲染视频作为唯一表现：不能响应状态，也无法保证移动端与 Reduced Motion 的语义完整。
- Canvas 承载业务文字：静态 HTML、SEO 和可访问性不可接受。

### Implementation boundary

WebGL 不承载唯一信息，不是 LCP 前置条件；页面隐藏时暂停，卸载时 dispose，失败时保留完整 DOM 与 Poster。

## ADR-025：Web 当前交付，Tauri 通过 Platform Adapter 后置

### Status

Accepted for implementation；Implementation Pending。

### Context

当前主要交付是公网 Web；未来桌面端可能需要文件系统、通知、窗口、本地缓存和深链接。现在引入 Tauri 会扩大构建、签名和安全面。

### Decision

当前只交付 Web。平台能力通过 FileExport、Notification、LocalCache、DeepLink 等 Port 注入；浏览器提供 Web Adapter，未来 `apps/desktop` 提供 Tauri Adapter。

### Consequences

- 正向：核心工作台不依赖平台 API，可在证明需求后封装桌面端。
- 负向：初期需要保持 Port 边界，即使只有一个 Web 实现。

### Rejected alternatives

- 本轮同时实现 Tauri：超出竞赛 Web 主路径，增加发布与权限风险。
- 组件直接调用浏览器 API：未来桌面复用时会散落条件分支。

### Implementation boundary

本轮不创建 `apps/desktop`，不安装 Tauri，不定义签名或自动更新流程。

## ADR-026：免登录隔离会话与只读分享链接

### Status

Accepted for implementation；Implementation Pending。

### Context

评审需要无注册进入 Demo 和临时 Live Run，同时 Project、Run、用户输入和未公开 Evidence 必须隔离；分享结果只能读取冻结版本，不能复用编辑会话凭据。

### Decision

后端创建有过期时间和资源配额的匿名 ResearchSession，通过 Secure、HttpOnly、SameSite Cookie 标识。所有私有资源按服务端会话授权。分享创建 ShareSnapshot，锁定公开 ArtifactVersion 与 Evidence 范围，并生成高熵、可撤销、可过期的只读 token；服务端只保存 token hash。

### Consequences

- 正向：降低首次体验门槛；分享内容稳定且不泄露编辑权限。
- 负向：匿名会话仍需速率限制、CSRF、防枚举和清理策略，不能等同于“无安全要求”。

### Rejected alternatives

- 强制账号：增加初审体验摩擦，当前没有团队权限需求。
- 把 session id 放入分享 URL：会形成水平越权风险。
- 分享 latest 指针：后续修订会悄然改变已提交材料。

### Implementation boundary

MVP 不实现账号、团队角色或公开编辑；分享默认 no-store、最小字段、可撤销，并过滤受限全文、密钥、内部错误和未授权输入。

## ADR-027：Project / Run / Artifact / Version 分层领域模型

### Status

Accepted for implementation；Implementation Pending。

### Context

当前 `ResearchTask` 同时承担用户目标、执行状态和结果容器，无法表达同一问题的多次运行、失败重试、局部修订、只读分享与历史对照。

### Decision

`ResearchProject` 表示持续研究上下文，`ResearchRun` 表示一次不可变契约驱动执行，`ResearchArtifact` 表示稳定产物身份，`ArtifactVersion` 表示追加式内容快照。重试、修订和派生创建带 `parent_run_id` 与 `derivation_kind` 的新 Run；版本不原地覆盖。

### Consequences

- 正向：并行运行、缓存、修订、分享和复现拥有统一语义。
- 负向：API 和存储对象增加，迁移期需要把 v1 Task DTO 映射到目标模型。

### Rejected alternatives

- 为每次修订覆盖 Task 结果：无法审计历史截图与证据。
- 把聊天线程作为项目：领域语义错误，无法定义产物生命周期。
- 只给产物增加 `version` 字符串：缺少 Run、来源和父子关系。

### Implementation boundary

目标 API 使用 `/api/v2`；当前 `/api/v1/tasks` 保留到新工作台通过契约与 E2E 门禁后再宣布弃用。

## ADR-028：纯浅色雾霾蓝视觉体系

### Status

Accepted for implementation；Implementation Pending。

### Context

黑色宇宙背景、霓虹蓝紫和通用 SaaS 卡片会削弱材料阅读与品牌差异；MVP 资源不足以同时完成高质量双主题。

### Decision

只实现浅色系统：冷淡灰基底、低饱和雾霾蓝品牌色、深蓝灰文字和独立状态色。使用 OKLCH Raw Scale 与语义 Token；ASCII / Dither 强度按首页、工作台、正文分层。

### Consequences

- 正向：视觉和科研阅读统一，Token 与视觉回归范围可控。
- 负向：暂不支持完整深色主题；需要验证雾霾蓝与状态色对比度。

### Rejected alternatives

- 同期深浅双主题：增加 Token、WebGL、图表和视觉回归矩阵。
- 黑底星空：与高密度文献、数据和 Evidence 阅读冲突。
- 大面积渐变和发光：降低可信度并增加视觉疲劳。

### Implementation boundary

业务组件不得硬编码 Raw Color；状态不能只靠颜色表达。字体二进制必须完成许可证、来源、中文覆盖和离线策略记录后才能提交。
