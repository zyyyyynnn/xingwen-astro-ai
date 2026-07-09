# Review Checklist

本清单用于 PR、自测和演示前检查，只保留可执行项。

## 1. PR 合并前

| 检查项 | 必须满足 |
| --- | --- |
| 范围 | PR 只解决一个明确任务，关联 Issue |
| 验证 | PR 描述包含验证命令、结果或未验证原因 |
| 文档 | 接口、数据、UI、部署或范围变化已同步对应文档 |
| 安全 | 未提交 `.env`、API Key、Token、连接串、论文源凭据或完整密钥日志 |
| 接口 | 响应结构符合 `API_CONTRACT.md` |
| 数据 | 字段命名、枚举和证据链符合 `DATA_MODEL.md` |
| UI | 颜色、间距、圆角、阴影、动效符合 `DESIGN.md` |
| 缓存 | 使用缓存时 API 和页面均明确标注 |
| 论文 | 自动获取结果不能由 seed list 冒充 |
| 推理 | 跨文献关系必须绑定 `Evidence` 和 `ReasoningTrace` |
| 口径 | 不宣传未实现能力 |

## 2. 前端自测

- 页面可启动或构建通过。
- 首页说明主案例，不写任意科研问题。
- 任务页覆盖 `pending`、`planning`、`completed`、`failed`，并展示 `TaskStep` 过程信息。
- 数据、论文获取、文献、推理、图谱页面覆盖加载、成功、失败、空状态。
- 论文获取页能展示检索参数、候选论文、去重规则、相关性分数和入选原因。
- 推理页能展示 Claim、Relation、ReasoningTrace，并能打开证据。
- 表格、证据面板和图谱详情不溢出、不遮挡核心信息。
- UI 使用 token，不散落高饱和颜色、强阴影或硬编码动效。
- 图标按钮有可读标签，键盘可访问不阻塞主流程。

## 3. 后端自测

- `/api/v1/health` 可用。
- 创建任务、查询任务、获取 dataset/paper-acquisition/papers/literature-reasoning/graph/evidence 接口可用。
- 错误响应包含 `code`、`message`、`request_id`。
- `meta.cached`、`used_cache`、`SourceRecord.cached` 语义一致。
- 论文源失败时有错误码或缓存兜底路径。
- Qwen 调用有超时、错误处理和缓存兜底策略。
- 日志不输出完整密钥、连接串、论文源凭据或过长模型响应。

## 4. 数据自测

- MVP 字段清单包含字段名、含义、单位、来源优先级。
- 原始来源、清洗结果、字段字典可复现。
- 缺失率、字段覆盖率、单位一致性能计算。
- CSV、字段字典、溯源报告可导出并被常见工具打开。
- 数据结果能追溯到 SourceRecord 和 Evidence。

## 5. 论文、文献、推理与图谱自测

- 主案例论文获取来源、检索关键词、检索参数可复现。
- PaperAcquisitionRun 记录候选数量、入选数量、去重规则和缓存状态。
- PaperCandidate 有来源、URL/DOI/arXiv ID、相关性分数和入选原因。
- seed list 只作为兜底、评测基准或人工校验，不冒充自动获取结果。
- PaperSummary 结构固定，核心结论绑定 evidence。
- LiteratureClaim 覆盖目标、方法、数据、发现、局限等类型。
- LiteratureRelation 至少覆盖 3 类关系，并绑定 `evidence_ids`。
- ReasoningTrace 可解释关系判断过程，不只返回自然语言结论。
- GraphNode / GraphEdge 符合 `DATA_MODEL.md`。
- 每条 GraphEdge 绑定 `evidence_ids`，跨文献边绑定 `reasoning_trace_id`。
- 无证据内容只作为候选，不作为最终结论。

## 6. 演示前检查

| 检查项 | 必须满足 |
| --- | --- |
| 公网访问 | 首页、任务页、数据页、论文获取页、文献页、推理页、图谱页可打开 |
| 主案例 | 固定输入可完整跑通或使用真实运行缓存兜底 |
| 论文 | 能展示自动获取过程，不用手写列表冒充 |
| 推理 | 能展示至少 3 类跨文献关系及证据链 |
| 导出 | CSV、字段字典、溯源报告、论文与推理关系 JSON 可下载 |
| 截图 | 页面无明显错位、报错、空白占位或密钥暴露 |
| 证据 | 字段、结论、关系、图谱边可打开证据详情 |
| 材料 | 交接口径不超过已实现能力 |

## 7. 文档审查

- `README.md` 是否仍是清晰入口。
- `PRD.md` 是否仍只承诺固定主案例范围。
- `DESIGN.md` 是否与实际架构和 UI 代码一致。
- `API_CONTRACT.md` 是否与后端接口一致。
- `DATA_MODEL.md` 是否与数据库、Schema 和前端类型一致。
- `ACCEPTANCE.md` 是否覆盖当前演示目标。
