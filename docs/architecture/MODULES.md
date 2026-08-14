# Module Boundaries

| 元数据    | 值                                       |
| --------- | ---------------------------------------- |
| Authority | 跨模块职责、输入输出、依赖方向与交接边界 |

本文定义系统各架构分层的职责分工、依赖方向与交接边界。前端包依赖见 [Frontend Architecture](FRONTEND_ARCHITECTURE.md)。

## 1. 依赖方向

```text
Experience (Site / Workspace)
  -> Frontend Application Boundary
  -> Research Adapter / Query
  -> Repository Port
  -> Fixture / HTTP Adapter
  -> API Application Service
  -> ResearchRun Workflow
  -> Step Adapter
  -> Scientific Pipeline
  -> Publisher
  -> ArtifactVersion / Evidence / SourceSnapshot
```

**单向依赖与禁忌规则：**

- `@xingwen/domain` 严禁反向依赖 React、Astro、HTTP 或 DOM API。
- 前端组件与 UI 运行时严禁直接发起网络 fetch 或直连外部数据/文献源。
- Runtime DTO 必须先通过 Contract/Pydantic 校验，再映射成 Domain/ViewModel；UI 不读取 raw DTO、API path 或未校验错误。
- Fixture Adapter 与 HTTP Adapter 必须输出同一 Domain/Repository Port 形状；Adapter 只做协议、解析和 provenance 映射，不写科研事实。
- Pipeline 纯粹实现科研算法，严禁直接调用 Router、推进 ResearchRun 主状态机、发布 HTTP DTO 或分配版本。
- Router 严禁直接串联 Pipeline，不直接承载算法实现。
- Workflow 是 Run/Step/Attempt/Event/lease/retry/cancel/publish 以及目标 cache/revision 契约的唯一编排边界；不得创建第二套执行器或状态机。没有公开命令或 Adapter 的能力必须 fail closed。
- Publisher 是 ArtifactVersion、Evidence 与 SourceSnapshot 关联的唯一发布事务边界。
- 生产者严禁在 Router 或组件中硬编码散落 Prompt，统一由 Prompt Registry 管理；禁止 `any`、不安全断言和深层私有 import。

## 2. 模块职责划定

### 2.1 前端与产品体验

- **职责**：提供 Brand Site 静态站与 Research Workspace 宿主界面，负责 Session Gate、路由、Query/Mutation 组合、Research Thread 展示、Artifact Renderer Registry、浮动 Research Inspector、交互响应与分享体验。
- **不负责**：直连外部模型/数据源、决定 Run 状态、伪造后端未返回的科研事实。

`/workspace` 的项目首次创建、项目恢复与研究交互共享同一 Workspace Shell。
显式退出由 Workspace Application Boundary 撤销 Session、清除私有 Query 状态后返回
Brand Site 首页；会话失效页只承接真实 Session 过期或私有边界拒绝，不是退出后的中转页。

`@xingwen/research-adapter` 是前端唯一的 Research Application Boundary，负责
Domain 到 UI ViewModel、Thread/RunEvent 到公开 PresentationEvent、UI Intent
到 ApplicationCommand，以及已归一化 Repository 错误到稳定公开错误的纯映射。
它只依赖 `@xingwen/domain` 与 `@xingwen/data-access` 的窄 public ports/errors 边界，不拥有
transport、session、query/cache、polling、server state 或 renderer 生命周期。

### 2.2 API、Application 与 Workflow

- **职责**：提供统一无版本 `/api/*` 接口，管理 Session、Project、Contract、Run 状态机与 Event 读取；Workflow 拥有并发锁、幂等、StepAttempt 重试、取消与发布事务，提供内部 CacheRecord/CacheSelector 失败回退审计，并为 RevisionPlan 保留唯一目标编排边界；通过 Persistent Workflow Executor 连接 Step Adapter。HTTP 只暴露有真实执行闭环的命令。
- **不负责**：具体清洗算法、文献检索策略、图谱布局算法。

### 2.3 数据 Pipeline

- **职责**：基于 Case/Field Manifest 抓取主/补充数据，生成 SourceSnapshot、跨源实体对齐、字段清洗、单位统一、数据质量评估及 Dataset / FieldDictionary typed candidates。
- **不负责**：推进 Run 主状态、选择 Cache 或发布 HTTP DTO。

### 2.4 文献、推理与图谱 Pipeline

- **职责**：执行论文检索与去重、结构化文献总结 (PaperSummary)、Claim 抽取、有向 Relation 识别、ReasoningTrace 构建与 Graph 生成，并绑定 Evidence。
- **不负责**：绕过来源许可、记录模型私有 chain-of-thought、为视觉效果制造假节点/边。

### 2.5 基线与工具链 (Infra & Tooling)

- **职责**：管理 Docker Compose、CI 自动化、单根 pnpm-lock、Schema 导出工具与部署脚手架。
- **不负责**：替代业务模块实现逻辑。

### 2.6 Publisher 与版本边界

- **Publisher**：接收已经通过 Schema、Evidence、质量和 ownership admission 的 typed
  candidate，在一个事务内创建不可变 ArtifactVersion 及其 Evidence/SourceSnapshot
  关联，并记录 ProducerExecution。
- **Pipeline / API**：只产生 candidate 或读取固定版本；不得直接写版本表、维护
  `latest`、把失败结果发布成成功或以 UI 投影代替科学 Artifact。

## 3. 跨模块交接标准

模块间交接必须提供：

1. 明确的输入与输出 Pydantic / TypeScript Schema 版本；
2. 明确的数据真实性等级标识 (Live / Fixture / Cached)；
3. 完整的 Evidence、SourceSnapshot、Hash 与 Producer 属性；
4. 明确的错误分类、空结果与失败语义。
