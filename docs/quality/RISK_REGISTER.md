# Risk Register

## 高风险

| 风险 | 影响 | 应对 |
| --- | --- | --- |
| 外部数据源不稳定 | Demo 中断、数据无法刷新 | 真实运行缓存兜底，展示 cached 标识 |
| 论文来源不稳定或限流 | 自动论文获取失败，核心能力无法展示 | 限定主案例、保留真实运行缓存、记录检索参数和来源状态 |
| 模型输出编造或格式不稳定 | 文献总结和图谱可信度下降 | JSON Schema 校验、Evidence 校验、无效输出不得直出 |
| 跨文献关系幻觉 | 推理能力被评审质疑 | LiteratureRelation 必须绑定 Evidence 和 ReasoningTrace，无证据关系只作候选 |
| API Key、数据库或论文源凭据泄露 | 账号、费用与数据风险 | Secret 仅在后端/部署平台，生产启动校验，日志脱敏 |
| 三大功能割裂 | 作品像功能拼盘，竞争力下降 | 所有页面围绕同一 ResearchTask、Evidence 和 ReasoningTrace 链 |
| 主案例范围扩散 | 进度失控 | MVP 固定 `exoplanet_host_star` |
| 工作流编排散落在 Router/Pipeline | 非法跳转、失败状态和重试不可控 | 显式状态机、Workflow Executor、数据库 Hooks 边界 |
| 产物无版本或原地覆盖 | 无法复现答辩结果、缓存和人工修正 | ArtifactVersion/ExperimentRun 契约，追加式修正 |

## 中风险

| 风险 | 影响 | 应对 |
| --- | --- | --- |
| 前后端字段不一致 | 联调成本上升 | Pydantic authoring source + JSON Schema/OpenAPI 导出 |
| Schema 导出未进入 CI | 共享契约名义存在但持续漂移 | CI 每次导出全部 Pydantic Model，后续启用 stale check |
| Prompt 散落或原地修改 | 模型结果和缓存不可复现 | `packages/prompts` registry + 不可变版本 |
| seed list 冒充自动获取 | 材料口径失真，演示可信度下降 | seed list 只作为兜底、评测基准和人工校验，自动获取必须有 run 记录 |
| 图谱只好看但无证据 | 评审质疑科研价值 | 每条边必须有 `evidence_ids`，跨文献边必须有 `reasoning_trace_id` |
| 文献总结缺少引用脉络 | 难以体现科研工具价值 | PaperSummary 绑定 paper/source/evidence |
| 论文候选相关性差 | 总结和推理质量下降 | 固定检索基准，候选保留 relevance_score 和 selection_reason |
| Docker 内前端使用 `api` 服务名 | 浏览器无法访问 API | `VITE_API_BASE_URL` 使用宿主机/公网可访问 URL |
| localhost 与 127.0.0.1 CORS 口径不一致 | 本地页面请求被阻止 | `.env.example` 同时列入两个本地 origin |
| CI 仅检查文件存在 | 错误依赖、构建失败仍显示通过 | frozen install、pytest、schema export、frontend build、compose config |
| 部署平台限制 | 公网 Demo 不稳定 | 前端、后端、数据库分离部署，保留缓存模式 |
| 成员任务边界不清 | 重复开发或遗漏 | 按 `MODULES.md`、Phase Issue 和 `BACKLOG.md` 认领 |

## 低风险

| 风险 | 影响 | 应对 |
| --- | --- | --- |
| UI 细节不统一 | 展示专业度下降 | DESIGN 和前端 token 规范 |
| 导出格式不够美观 | 材料复用成本增加 | 先保证 CSV/JSON 正确，再补报告模板 |
| 文档过期 | 新成员误解项目 | PR 改接口/模型/范围时必须同步文档 |
| 过早引入通用图数据库/向量库 | 基建复杂度上升 | 真实规模和查询需求出现后再 ADR 评估 |

## 风险处理原则

1. 影响 Demo 稳定性的风险优先处理。
2. 影响科研可信性的风险优先处理。
3. 影响自动论文获取和跨文献推理主链路的风险不得后置为“展示优化”。
4. 影响密钥、版本与证据链的风险必须有机器校验或运行时防线。
5. 影响美观但不影响主链路的风险后置。
6. 无法本周解决的风险必须写明兜底方案、责任 Issue 和验收条件。
