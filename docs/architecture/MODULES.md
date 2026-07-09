# Module Boundaries

## 1. 目录与职责

| 目录 | 负责人 | 职责 | 核心输出 |
| --- | --- | --- | --- |
| `apps/web` | A | Vue/Vite 前端页面、流程展示、shadcn-vue 组件、论文获取过程、推理关系、Vue Flow 图谱交互、反馈入口 | 页面、组件、前端 API Client、截图素材 |
| `apps/api` | B | FastAPI、任务编排、Qwen Client、论文源代理、缓存、导出 | REST API、状态机、数据库访问、OpenAPI |
| `services/data_pipeline` | C | 天文数据获取、清洗、字段映射、质量评分 | Dataset、FieldDefinition、SourceRecord、QualityScore |
| `services/paper_pipeline` | D | 论文检索、候选获取、去重、相关性排序、结构化总结、来源绑定 | PaperSearchQuery、PaperAcquisitionRun、PaperCandidate、Paper、PaperSummary、Evidence |
| `services/graph_pipeline` | D | Claim 抽取、跨文献关系、推理链、图谱节点、边、证据链 | LiteratureClaim、LiteratureRelation、ReasoningTrace、GraphNode、GraphEdge、Evidence |
| `packages/schemas` | B 主导，全员使用 | 共享类型、枚举、JSON Schema | Pydantic/TypeScript Schema |
| 根目录 Docker 基建 | A + B | Docker Compose、服务端口、环境变量、版本锁定 | `docker-compose.yml`、Dockerfile、`.env.example`、启动说明 |
| `samples` | C + D | 可复现样例输入输出 | 示例 CSV、论文候选 JSON、推理关系 JSON、报告 |
| `docs/handoff` | 全员 | 材料组交接素材 | 截图、导出物、说明 |

## 2. 模块输入输出

### A 前端

输入：

- `API_CONTRACT.md` 定义的接口。
- `DATA_MODEL.md` 定义的数据结构。
- `DESIGN.md` 定义的 shadcn-vue、Tailwind token、Vue Flow 规范。

输出：

- 任务流程页。
- 数据结果页。
- 论文获取页。
- 文献总结页。
- 跨文献推理页。
- 图谱页。
- 反馈修正页。
- 可用于材料组的真实截图。

禁止：

- 前端直接调用 Qwen。
- 前端直接调用论文源或天文数据源。
- 前端保存 API Key 或论文源凭据。
- 前端自行编造后端未返回的数据、论文候选或推理关系。
- 混用 npm/yarn/bun 安装依赖。

### B 后端

输入：

- 前端请求。
- Qwen 配置。
- 论文源配置。
- Data/Paper/Graph Pipeline 输出。

输出：

- 统一 REST API。
- 任务状态机。
- 缓存兜底结果。
- 导出文件。
- 错误码和日志。
- Docker API 服务启动入口。

禁止：

- 让不同接口返回互相冲突的字段。
- 将模型自然语言输出直接返回为最终事实。
- 在日志中输出完整密钥、论文源凭据或过长模型响应。
- 用 requirements.txt 替代 uv 主依赖管理流程。

### C 数据 Pipeline

输入：

- `case_key`。
- 任务目标和字段需求。
- 外部数据源响应或缓存。

输出：

- 标准化 rows。
- 字段字典。
- 来源记录。
- 质量评分。
- CSV 和溯源报告。

禁止：

- 无来源字段进入最终数据集。
- 单位不明的数值字段进入最终展示。
- 手写假数据冒充真实来源。

### D 论文获取与总结 Pipeline

输入：

- `case_key`。
- 任务目标、字段需求和 seed keywords。
- 论文来源响应或真实运行缓存。
- 主案例 seed list，用作兜底、评测基准和人工校验。

输出：

- PaperSearchQuery。
- PaperAcquisitionRun。
- PaperCandidate。
- PaperSummary JSON。
- Evidence。

禁止：

- 将 seed list 冒充自动获取结果。
- 绕过付费全文或抓取无授权内容。
- 生成无法溯源的文献结论。
- 混淆论文结论和模型推断。

### D 图谱与跨文献推理 Pipeline

输入：

- PaperSummary JSON。
- PaperCandidate / Paper。
- 数据 Pipeline 输出。
- Qwen 结构化抽取结果。

输出：

- LiteratureClaim。
- LiteratureRelation。
- ReasoningTrace。
- GraphNode / GraphEdge。
- Evidence。

禁止：

- 无证据 Claim 或 Relation 进入最终图谱。
- 把跨文献推理写成不可审查的自然语言结论。
- 混淆“支持、扩展、限制、矛盾”等关系类型。
- 把图谱做成纯装饰视效。

### X Docker 基建

输入：

- 技术栈版本基线。
- `.env.example`。
- A/B 服务启动方式。

输出：

- `docker-compose.yml`。
- Web/API Dockerfile 或等价构建入口。
- 端口、环境变量、数据卷说明。
- 本地启动验证记录。

禁止：

- 在 M1 强制引入 Redis、Celery、MinIO、Nginx、RabbitMQ。
- 容器依赖成员本机全局 Node、Python、PostgreSQL。
- 把密钥写入镜像、Compose 文件或前端构建变量。

## 3. 联调顺序

1. X：Docker Compose 基线联调。
2. A + B：Mock 任务流联调。
3. B + C：数据结果接口联调。
4. B + D：论文获取、文献总结和跨文献推理接口联调。
5. B + D：图谱与证据详情接口联调。
6. A + B + C + D：主案例端到端联调。
7. 全员：公网 Demo、缓存兜底、材料交接。

## 4. 交接标准

任一模块交接给其他成员前必须提供：

- 输入示例。
- 输出示例。
- 错误场景。
- 验证方式。
- 是否影响文档。
