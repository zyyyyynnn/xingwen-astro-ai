# Product Requirements

| 元数据 | 值 |
| --- | --- |
| Authority | 用户、问题、产品范围、主流程、差异化与成功指标 |

## 1. 产品目标

星文智析面向天文科研数据整理、文献理解与证据核验，把自然语言研究意图转化为可确认的研究契约，并通过可复现的 Agent 执行形成版本化科研产物、Evidence 与人类可审查的修订闭环。

MVP 固定主案例为**系外行星候选体与宿主恒星参数整合**。用户最终面对的是一个统一的 Research Workspace，而不是聊天外壳、工具集合或多个能力入口的拼装。

## 2. 核心问题

- 研究目标难以稳定转化为对象、字段、来源、文献和质量约束；
- 多源数据的字段、单位、对象标识、缺失值与冲突难以统一；
- 科学 PDF、论文候选、Summary、Claim 与跨文献 Relation 缺少可定位证据；
- 数据、结论、推理、图谱、模型执行和版本无法形成同一审查链；
- 通用 Agent 容易产生聊天式输出、工具日志或不可复核答案，而不是科研 Artifact；
- 结果难以比较、修订、导出、分享和复现。

## 3. 目标用户

| 用户 | 核心任务 | 产品响应 |
| --- | --- | --- |
| 天文科研初学者 | 把问题转成明确、可执行的研究协议 | ResearchContractDraft / ResearchContract |
| 科研使用者 | 运行数据与文献研究并审查结果 | Research Workspace / Artifact / Evidence |
| 评审与复现人员 | 判断结果是否真实、完整、可复现 | Version / SourceSnapshot / Evidence / Share |

## 4. 产品形态

- **Brand Site**：建立品牌与主案例认知，进入 Workspace。
- **Research Workspace**：唯一私有科研工作台，承载 Agent Thread、Contract、Run、Artifact、Evidence、Revision、Export/Share。
- **Public Share**：冻结版本的只读公开投影，不加载私有 Agent Shell。

Workspace 不是泛聊天助手、IDE 或工具集合。Agent 交互降低操作成本；科研 Artifact 与 Evidence 是主要工作对象。

## 5. 产品主流程

```text
Research Intent
→ editable ResearchContractDraft
→ confirmed immutable ResearchContract
→ Live ResearchRun
→ multi-source scientific data + document/literature acquisition
→ parsing / cleaning / alignment / scientific analysis
→ typed ArtifactVersion + Evidence + SourceSnapshot
→ PaperSummary / Claim / Relation / ReasoningTrace / Evidence Graph
→ human review
→ RevisionPlan / derived Run / superseding ArtifactVersion
→ Export / frozen Public Share
```

运行允许真实等待、失败、partial、unsupported、retry 与 cached recommendation；不得用 Fixture 模拟主流程成功。

## 6. 差异化

星文智析不以“拥有更多 Agent/工具”作为差异化，而以以下能力的**统一闭环**作为核心：

- 多源天文数据获取、字段/单位统一、实体对齐与质量评估；
- 科学文档解析与可定位 Evidence；
- 文献检索、Summary、Claim、Relation 与公开可审查 ReasoningTrace；
- Evidence-bound 学术 Graph；
- 天文 Scientific Skills、时序/建模/可视化能力进入同一 ResearchRun 与 Artifact 体系；
- immutable ArtifactVersion、SourceSnapshot、ProducerExecution 与真实 provenance；
- 对象级反馈、RevisionPlan 与最小影响重算；
- 统一 Workspace 中的能力发现、执行、审查、比较、分享与恢复。

新增或迁入能力必须转化为当前领域语义和统一交互，不保留功能岛、第二套运行时或来源导向的产品入口。

## 7. MVP 能力范围

- Research Contract：自然语言生成 Draft、结构化审查、确认后不可变；
- Project / Run：真实状态、并发、lease、恢复、取消、人工 checkpoint；
- Scientific data integration：多源 acquisition、cross-match、mapping、unit、quality、Dataset；
- Scientific document：PDF/图像解析、结构化 locator、DocumentParse → Summary / data candidate；
- Literature：候选检索、去重、排序、Summary、Claim、Relation、ReasoningTrace；
- Graph：Accepted Relation 构建 Evidence Graph，边可追溯；
- Scientific Skills：经统一 runtime 执行经过治理的天文计算、分析、建模与可视化能力；
- Research Workspace：Agent Shell、Thread、Activity、Composer、Result Index、Fullscreen Result Workspace、Evidence Inspector；
- Revision / Diff：科学语义差异、Feedback、RevisionPlan、derived Run；
- Export / Share：冻结版本、最小公开投影、可撤销/过期。

## 8. 完成定义

一个承诺给用户的能力只有在以下条件同时成立时才算 MVP 已实现：

1. 从正式产品入口可发现或由 Agent 在明确研究任务中自动触发；
2. 走正式 Domain / Repository / Workflow / Publisher；
3. 输出是 typed Artifact / Evidence / Activity，而不是 raw JSON 或本地文件孤岛；
4. loading / error / partial / unsupported 语义真实；
5. 用户能继续审查、比较、修订、导出或分享适用结果；
6. 有 Browser 或真实纵向运行证据。

API、库函数、单测、Fixture、benchmark 或静态截图单独存在不满足该定义。

## 9. 非目标

- 无边界 AI Scientist 或泛聊天平台；
- 任意科研领域通用自动化；
- 全网无限制爬取或付费内容绕过；
- 大规模通用知识图谱平台；
- 完整 IDE、代码托管、Sandbox/Cloud/Enterprise Runtime；
- 完整账号、组织与企业审计系统；
- 为兼容历史实现保留双 runtime、双 schema、双 renderer 或第二 Workspace；
- 为实现来源建立额外产品入口、模块标签或技术拼装展示。

## 10. 成功指标

| 指标 | MVP 目标 |
| --- | --- |
| 目标字段覆盖率 | >= 80% |
| 关键字段来源完整性 | 100% |
| 关键数值单位一致性 | 100% |
| 论文候选检索信息完整性 | 100% |
| 最终 Relation 的 Evidence / Trace 覆盖率 | 100% |
| GraphEdge Evidence 覆盖率 | 100% |
| 从关键结果定位 Evidence | <= 3 次交互 |
| 用户承诺能力正式入口可达率 | 100% |
| 当前/历史/修订来源表达准确率 | 100% |
| 主案例合格模型调用可复核率 | 100% |
