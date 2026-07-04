# AGENTS

## 1. 协作原则

本项目按国赛级 MVP 标准推进。所有开发必须服务主案例：**系外行星候选体与宿主恒星参数整合**。

优先级：主链路稳定 > 证据可信 > 演示完整 > 功能扩展。

## 2. 岗位边界

| 岗位 | 负责目录 | 核心职责 | 必须交付 |
| --- | --- | --- | --- |
| A 前端与产品流程 | `apps/web` | 工作流页面、数据页、文献页、图谱页、反馈入口 | 可录屏页面、错误/加载/空状态、前端联调说明 |
| B 后端与任务编排 | `apps/api`, `packages/schemas` | FastAPI、任务状态、Qwen Client、缓存、导出、数据库 | API、状态机、统一错误、OpenAPI 文档 |
| C 数据分析与数据源 | `services/data_pipeline`, `samples/outputs` | 数据源接入、字段映射、单位统一、质量评分、导出 | CSV、字段字典、来源记录、质量评分 |
| D 文献总结与学术图谱 | `services/paper_pipeline`, `services/graph_pipeline` | 文献结构化总结、证据链、图谱节点和边 | PaperSummary JSON、Graph JSON、证据映射 |

## 3. Git 工作流

- `main` 始终保持可运行。
- 所有改动通过 Pull Request 合并。
- 每个任务从 `main` 新建分支。
- 分支命名：`feat/a-task-timeline`、`feat/b-qwen-client`、`feat/c-data-cleaning`、`feat/d-graph-json`。
- PR 至少 1 人 Review 后合并。
- 直接推送 `main` 禁止。

## 4. 文档同步规则

| 改动类型 | 必须同步更新 |
| --- | --- |
| 新增/修改接口 | `docs/architecture/API_CONTRACT.md` |
| 新增/修改数据结构 | `docs/architecture/DATA_MODEL.md` |
| 修改模块职责 | `DESIGN.md`, `docs/architecture/MODULES.md` |
| 修改 MVP 范围 | `PRD.md`, `docs/product/ACCEPTANCE.md` |
| 修改部署方式 | `DEPLOYMENT.md`, `.env.example` |
| 新增风险或技术债 | `docs/quality/RISK_REGISTER.md` |

## 5. Issue 要求

Issue 必须包含：

- 背景：为什么做。
- 目标：完成后用户或系统得到什么。
- 验收标准：怎么判断完成。
- 影响范围：前端、后端、数据、文献、图谱、文档。

标题格式：

```text
[A] 实现任务进度时间线
[B] 封装 Qwen 调用层
[C] 输出字段映射与质量评分
[D] 构建论文-数据-证据图谱 JSON
```

## 6. PR 要求

PR 必须说明：

- 改了什么。
- 为什么改。
- 如何验证。
- 是否改接口或数据结构。
- 是否需要前后端联调。
- 是否影响材料组截图或演示口径。

PR 不接受：

- 无验收说明。
- 接口变化但不改 API 文档。
- 数据结构变化但不改数据模型。
- 前端直连模型或暴露 API Key。
- 无来源的模型结论直接展示。

## 7. 模型调用约定

- 所有模型调用统一走后端 Qwen Client。
- Prompt 集中管理，记录版本。
- 模型输出必须经过 JSON Schema 校验。
- 文献总结必须绑定文献来源。
- 图谱边必须绑定 `evidence_ids`。

## 8. 验证要求

| 模块 | 最低验证 |
| --- | --- |
| 前端 | 页面截图或录屏，覆盖加载、成功、失败状态 |
| 后端 | 接口请求示例和响应 JSON |
| 数据 | 样例输入、输出 CSV、字段字典、来源记录 |
| 文献 | PaperSummary JSON 和对应来源 |
| 图谱 | Graph JSON 和证据详情 |
| 部署 | 公网 URL、环境变量清单、缓存兜底验证 |

## 9. 材料交接规则

开发组只交付真实系统素材。未实现能力只能写为“规划/预留/后续扩展”，不得写成“已实现”。
