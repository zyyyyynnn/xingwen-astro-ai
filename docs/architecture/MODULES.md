# Module Boundaries

## 1. 目录与职责

| 目录 | 负责人 | 职责 | 核心输出 |
| --- | --- | --- | --- |
| `apps/web` | A | 前端页面、流程展示、图谱交互、反馈入口 | 页面、组件、前端 API Client |
| `apps/api` | B | FastAPI、任务编排、Qwen Client、缓存、导出 | REST API、状态机、数据库访问 |
| `services/data_pipeline` | C | 天文数据获取、清洗、字段映射、质量评分 | Dataset、FieldDefinition、SourceRecord、QualityScore |
| `services/paper_pipeline` | D | 文献清单、结构化总结、来源绑定 | Paper、PaperSummary、Evidence |
| `services/graph_pipeline` | D | 图谱节点、边、证据链 | GraphNode、GraphEdge、Evidence |
| `packages/schemas` | B 主导，全员使用 | 共享类型、枚举、JSON Schema | Pydantic/TypeScript Schema |
| `samples` | C + D | 可复现样例输入输出 | 示例 CSV、JSON、报告 |
| `docs/handoff` | 全员 | 材料组交接素材 | 截图、导出物、说明 |

## 2. 模块输入输出

### A 前端

输入：

- `API_CONTRACT.md` 定义的接口。
- `DATA_MODEL.md` 定义的数据结构。

输出：

- 任务流程页。
- 数据结果页。
- 文献总结页。
- 图谱页。
- 反馈修正页。
- 可用于材料组的真实截图。

禁止：

- 前端直接调用 Qwen。
- 前端保存 API Key。
- 前端自行编造后端未返回的数据。

### B 后端

输入：

- 前端请求。
- Qwen 配置。
- Data/Paper/Graph Pipeline 输出。

输出：

- 统一 REST API。
- 任务状态机。
- 缓存兜底结果。
- 导出文件。
- 错误码和日志。

禁止：

- 让不同接口返回互相冲突的字段。
- 将模型自然语言输出直接返回为最终事实。
- 在日志中输出完整密钥。

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

### D 文献与图谱 Pipeline

输入：

- 主案例文献清单。
- 数据 Pipeline 输出。
- Qwen 结构化总结结果。

输出：

- PaperSummary JSON。
- Evidence。
- GraphNode / GraphEdge。

禁止：

- 无证据边进入图谱。
- 混淆论文结论和模型推断。
- 把图谱做成纯装饰视效。

## 3. 联调顺序

1. A + B：Mock 任务流联调。
2. B + C：数据结果接口联调。
3. B + D：文献总结与图谱接口联调。
4. A + B + C + D：主案例端到端联调。
5. 全员：公网 Demo、缓存兜底、材料交接。

## 4. 交接标准

任一模块交接给其他成员前必须提供：

- 输入示例。
- 输出示例。
- 错误场景。
- 验证方式。
- 是否影响文档。
