# Module Boundaries

| 元数据 | 值 |
| --- | --- |
| Status | Accepted |
| Authority | 跨模块职责、输入输出、依赖方向与交接边界 |

本文定义系统各架构分层的职责分工、依赖方向与交接边界。前端包依赖见 [Frontend Architecture](FRONTEND_ARCHITECTURE.md)。

## 1. 依赖方向

```text
Experience (Site / Workspace)
  -> Frontend Application Services
  -> Repository Ports / Adapters
  -> API Application Services
  -> ResearchRun Workflow
  -> Data / Paper / Reasoning / Graph Pipelines
  -> ArtifactVersion / Evidence / SourceSnapshot
```

**单向依赖与禁忌规则：**
- `@xingwen/domain` 严禁反向依赖 React、Astro、HTTP 或 DOM API。
- 前端组件与 UI 运行时严禁直接发起网络 fetch 或直连外部数据/文献源。
- Pipeline 纯粹实现科研算法，严禁直接调用 Router 或推进 ResearchRun 主状态机。
- Router 严禁直接串联 Pipeline，不直接承载算法实现。
- 生产者严禁在 Router 或组件中硬编码散落 Prompt，统一由 `packages/prompts` 管理。

## 2. 模块职责划定

### 2.1 前端与产品体验
- **职责**：提供 Brand Site 静态站与 Research Workspace 宿主界面，负责路由、Agent Activity 展示、Artifact 渲染、Evidence Inspector 对照、交互响应与分享体验。
- **不负责**：直连外部模型/数据源、决定 Run 状态、伪造后端未返回的科研事实。

### 2.2 API、Application 与 Workflow
- **职责**：提供统一无版本 `/api/*` 接口，管理 Session、Project、Contract、Run 状态机与 Event 推送，处理并发锁、幂等、重试、取消、CacheSelector、Feedback 与持久化事务。
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

## 3. 跨模块交接标准

模块间交接必须提供：
1. 明确的输入与输出 Pydantic / TypeScript Schema 版本；
2. 明确的数据真实性等级标识 (Live / Fixture / Cached)；
3. 完整的 Evidence、SourceSnapshot、Hash 与 Producer 属性；
4. 明确的错误分类、空结果与失败语义。
