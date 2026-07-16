# Module Boundaries

## 1. 目录与职责

| 目录 | 负责人 | 职责 | 核心输出 |
| --- | --- | --- | --- |
| `apps/web` | A | Vue/Vite 页面、流程展示、图谱交互、反馈入口 | 页面、组件、API Client、截图 |
| `apps/api` | B | FastAPI、任务编排、模型 Client、缓存、导出 | REST API、状态机、OpenAPI |
| `apps/api/src/app/workflow` | B | 状态转换、Step 执行、失败与持久化边界 | Executor、Hooks、状态测试 |
| `services/data_pipeline` | C | 数据获取、清洗、字段映射、质量评分 | Dataset、FieldDefinition、SourceRecord |
| `services/paper_pipeline` | D | 论文检索、获取、去重、总结、来源绑定 | PaperCandidate、PaperSummary、Evidence |
| `services/graph_pipeline` | D | Claim、Relation、Trace、图谱构建 | LiteratureRelation、ReasoningTrace、Graph |
| `packages/schemas` | B 主导 | 共享契约生成产物和说明 | JSON Schema、manifest |
| `packages/prompts` | B + D | 生产 Prompt registry 与不可变版本 | Prompt 文件、版本映射 |
| `scripts` | B + X | 基建校验、Schema 导出、可复现工具 | CI/本地命令 |
| 根目录 Docker 基建 | A + B | Compose、端口、环境变量、版本锁定 | Compose、Dockerfile、env 模板 |
| `samples` | C + D | 可复现样例与评测输入输出 | CSV、候选、关系、报告 |
| `docs/handoff` | 全员 | 材料交接素材 | 截图、导出、说明 |

## 2. 依赖方向

```text
apps/web -> apps/api
apps/api routers -> application services -> workflow
workflow -> step adapters -> services/*
services/* -> schemas/contracts
model client -> packages/prompts
all persisted results -> Evidence / Source / version metadata
```

禁止反向依赖：

- Pipeline 不调用 Router。
- 前端不调用外部模型、数据源或论文源。
- Prompt 不散落在 Router/组件。
- Workflow 不嵌入清洗、检索或图谱算法。
- generated Schema 不作为手工编写源。

## 3. A 前端

输入：

- API/OpenAPI 和共享契约。
- DESIGN UI token。
- 缓存、错误、证据状态。

输出：

- 任务、数据、论文、总结、推理、图谱和反馈页面。
- 可用于材料组的真实截图。

禁止：

- 自行编造后端未返回的科研结果。
- 保存密钥或直连外部来源。
- 把 cached、mock、candidate 与 final 混淆。
- 手写重复业务类型而不走统一生成/集中层。

## 4. B 后端与 Workflow

输入：

- 前端请求。
- Pipeline 结构化输出。
- 模型、论文源、数据库配置。

输出：

- 统一 API 与错误。
- ResearchTask/TaskStep 状态。
- 缓存、导出、OpenAPI。
- Schema 导出。
- 运行与产物版本关联。

Router 只解析请求和调用 application service。Workflow 只编排，业务规则留在对应 Pipeline。数据库适配通过 Hooks/Repository 接入。

禁止：

- Router 直接串联完整科研链路。
- Pipeline 自行修改任务主状态。
- 将模型自由文本直接作为最终响应。
- 在日志输出密钥、连接串或受限全文。
- 使用进程内状态作为唯一任务事实来源。

## 5. C 数据 Pipeline

输入：case_key、目标、字段需求、外部响应或真实缓存。

输出：标准化 rows、字段字典、来源、质量、导出。

必须：

- 单位、来源、规则版本明确。
- 外部查询记录 SourceSnapshot/hash。
- 关键值绑定 Evidence。

禁止无来源字段、单位不明数值和手写假数据冒充真实来源。

## 6. D 论文与总结 Pipeline

输入：case、目标、字段、seed keywords、论文来源或真实缓存。

输出：Query、Run、Candidate、Paper、Summary、Evidence。

必须：

- Prompt 从 `packages/prompts` 加载具体版本。
- 候选保留来源、检索、去重、相关性。
- Summary 通过 Schema 和 Evidence 校验。

禁止 seed 冒充自动获取、绕过付费访问或生成无法溯源结论。

## 7. D 推理与图谱 Pipeline

输入：已校验 Summary/Claim/Evidence 和数据产物。

输出：Claim、Relation、ReasoningTrace、GraphNode/Edge、Evidence。

必须按 `REASONING_PROTOCOL.md` 区分候选与最终关系。

禁止：

- 无 Evidence/Trace 的 Relation 进入最终图谱。
- 把不可审查的自然语言解释当作 Trace。
- 仅为视觉效果生成边。
- 在 MVP 未证明需要时引入 Neo4j/通用图抽象。

## 8. X 基建

输入：技术基线、env 模板、A/B 启动方式、契约路径。

输出：

- Compose 与 healthcheck。
- CI 与漂移检查。
- 浏览器可访问的 API URL。
- 本地和部署验证记录。

禁止：

- M1 强制引入复杂中间件。
- 容器依赖成员本机全局运行时。
- 默认生产密码、DEBUG 或通配 CORS。
- 只检查文件存在却不实际构建/测试。

## 9. 联调顺序

1. X：Foundation、CI、Compose、Schema export。
2. A + B：Mock 任务流。
3. B + C：数据链路。
4. B + D：论文获取和总结。
5. B + D：推理、图谱、证据。
6. A + B + C + D：主案例端到端。
7. 全员：版本、缓存、部署、材料。

## 10. 交接标准

任一模块交接前提供：

- 输入/输出示例；
- 错误场景；
- Schema 与版本；
- Evidence/来源要求；
- 验证命令与结果；
- 是否影响契约、风险或材料。
