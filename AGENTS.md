# AGENTS

本文件是本仓库的 Agent 操作协议。协作流程细节见 [CONTRIBUTING.md](CONTRIBUTING.md)，系统与 UI 设计基线见 [DESIGN.md](DESIGN.md)。

## 1. 默认基准

- 环境：Windows 11、PowerShell 7+、UTF-8。
- 目标：国赛级 MVP，先服务主案例 **系外行星候选体与宿主恒星参数整合**。
- 优先级：主链路稳定 > 证据可信 > 演示完整 > 功能扩展。
- 输出原则：结论先行、改动最小、验证明确；不确定时说明不确定。

## 2. 执行纪律

- 需求清晰时直接执行，不反复确认。
- 只问会实质影响实现、风险或验收的问题。
- 不扩大范围，不顺手重构，不引入无关依赖。
- 每处改动必须对应 Issue、PR 目标或明确用户指令。
- 不把 Mock、缓存或模型推断包装成真实科研结论。

## 3. 模块边界

| 岗位 | 负责目录 | 核心职责 | 必须交付 |
| --- | --- | --- | --- |
| A 前端与产品流程 | `apps/web` | 工作流、数据页、论文获取页、文献页、推理页、图谱页、反馈入口、UI 规范落地 | 可录屏页面、状态处理、联调说明 |
| B 后端与任务编排 | `apps/api`, `packages/schemas` | FastAPI、任务状态、Schema、Qwen Client、论文源访问代理、缓存、导出 | API、OpenAPI、统一错误、验证样例 |
| C 数据分析与数据源 | `services/data_pipeline`, `samples/outputs` | 字段清单、数据源、清洗、单位、质量评分、导出 | CSV、字段字典、来源记录、质量评分 |
| D 论文、推理与图谱 | `services/paper_pipeline`, `services/graph_pipeline` | 论文获取、结构化总结、Claim/Relation/Trace、证据链、Graph JSON | PaperAcquisition、PaperSummary、ReasoningTrace、Graph JSON、证据映射 |

跨模块任务必须先对齐 `API_CONTRACT.md` 和 `DATA_MODEL.md`，再编码。

## 4. 文档同步红线

| 改动 | 必须同步 |
| --- | --- |
| 接口、响应、错误码 | `docs/architecture/API_CONTRACT.md` |
| 数据实体、字段、枚举 | `docs/architecture/DATA_MODEL.md` |
| 模块职责或目录边界 | `DESIGN.md`, `docs/architecture/MODULES.md` |
| MVP 范围或验收口径 | `PRD.md`, `docs/product/ACCEPTANCE.md` |
| 部署、环境变量、密钥 | `DEPLOYMENT.md`, `.env.example`, `SECURITY.md` |
| 新风险、技术债、演示风险 | `docs/quality/RISK_REGISTER.md` |

文档不追求多，只保留能指导开发、验证和材料交接的必要说明。

## 5. 验证要求

| 类型 | 最低要求 |
| --- | --- |
| 前端 | 启动或构建结果；截图覆盖加载、成功、失败、空状态 |
| 后端 | 接口请求与响应 JSON；错误响应含 `code`、`message`、`request_id` |
| 数据 | 样例输入、输出 CSV、字段字典、来源记录可复现 |
| 论文 | PaperAcquisitionRun、PaperCandidate、检索参数、来源和缓存状态可复现 |
| 文献 | PaperSummary JSON 绑定文献来源和 evidence |
| 推理 | LiteratureClaim、LiteratureRelation、ReasoningTrace 绑定 evidence |
| 图谱 | Graph JSON 的边全部绑定 `evidence_ids`，跨文献边绑定 `reasoning_trace_id` |
| 部署 | 公网 URL、环境变量清单、缓存兜底验证 |

无法运行上一级验证时，说明原因并给出已完成的降级验证。不得用“应该可以”替代结果。

## 6. UI 修改纪律

`DESIGN.md` 是 UI 设计系统唯一入口。前端实现必须遵守：

- 视觉方向：米白纸感、低饱和灰、低饱和靛灰强调。
- 颜色、间距、圆角、阴影、字体、动效必须 token 化。
- 业务组件不得散落非 token 色值、随意阴影、强边框或过度动效。
- 数据表、论文获取、推理链、证据面板、图谱、任务时间线必须优先清晰可读，不为装饰牺牲可信度。
- UI 改动需同步检查 `docs/quality/REVIEW_CHECKLIST.md` 中的 UI 项。

## 7. 科研可信红线

- 前端不直连 Qwen，不直连外部天文数据源或论文源。
- API Key 和论文源凭据只允许在后端环境变量或部署平台 Secrets 中存在。
- 模型输出必须结构化校验，不能直接当作事实。
- 展示字段、文献结论、跨文献关系、图谱边必须能追溯到 `Evidence`。
- 跨文献关系必须绑定 `ReasoningTrace`。
- seed list 只能作为兜底、评测基准或人工校验，不得冒充自动论文获取结果。
- 缓存是元信息，不是主任务状态；缓存结果必须明确标注。

## 8. 材料口径红线

开发组只交付真实系统素材或明确标注的真实运行缓存。未实现能力只能写为“规划”“预留”“后续扩展”，不得写成“已实现”。

禁止宣传：任意天文方向、任意 PDF 全文解析、任意图表全自动解析、无边界 AI Scientist、无证据科学发现。
