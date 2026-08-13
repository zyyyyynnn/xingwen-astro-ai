# Product Requirements

| 元数据 | 值 |
| --- | --- |
| Authority | 用户、问题、产品范围、主流程、成功指标与非目标 |

本文定义星文智析要解决的问题和必须交付的产品结果。交互细节见 [Workspace UX](docs/design/WORKSPACE_UX.md)，规范索引见 [docs/README.md](docs/README.md)，退出标准见 [Acceptance](docs/product/ACCEPTANCE.md)。

## 1. 产品目标

星文智析面向天文科研数据整理与证据核验场景，将自然语言研究意图转化为可确认的研究契约，并形成可复现、可溯源、可对照的科研产物链。

MVP 固定主案例为 **系外行星候选体与宿主恒星参数整合**。架构支持扩展其他天文数据整合任务，但产品只承诺已经通过真实运行、Evidence 和测试证明的范围。

## 2. 核心问题

- 研究目标难以转化为明确的字段、来源、论文和质量约束；
- 多源字段、单位、对象标识和缺失值难以统一；
- 论文候选、总结和跨文献关系缺少可核验来源；
- 数据、结论、推理和图谱无法稳定定位到同一运行和版本；
- AI 输出容易退化为不可审查的自然语言回答；
- 结果难以复现、分享、修订和导出。

## 3. 目标用户与任务

| 用户 | 主要任务 | 产品响应 |
| --- | --- | --- |
| 天文科研初学者 | 将研究意图转化为明确的数据与文献需求 | ResearchContractDraft 与 ResearchContract |
| 科研使用者 | 对照数据、论文、结论、条件和来源 | Research Workspace |
| 评审与复现人员 | 判断数据与推导是否真实、完整、可复现 | Brand Site、Evidence 与 Version 入口 |

## 4. 产品形态

| 体验域 | 职责 |
| --- | --- |
| Brand Site | 建立品牌与主案例认知，引导进入工作台 |
| Research Workspace | 管理项目、运行、产物审查、反馈、分享和导出 |

工作台不是通用聊天 Agent。AI 是上下文协作者；中央主区域优先展示科研产物与 Evidence。

## 5. 产品主流程

```text
1. 用户输入研究意图 -> 生成可编辑 ResearchContractDraft
2. 用户确认对象、字段、来源、论文范围与质量要求 -> 形成不可变 ResearchContract
3. 用户启动 Live Run -> 生成数据、字段字典、来源快照和质量结果
4. 检索论文候选 -> 记录 Query、去重、排序和选择依据
5. 生成逐项绑定 Evidence 的 PaperSummary
6. 抽取 Claim -> 构建候选与最终 Relation、ReasoningTrace
7. 生成每条边可核验的证据图谱
8. 用户审查产物与 Evidence -> 导出或分享
9. 用户提交对象级反馈 -> 确认 RevisionPlan -> 派生 Run 生成新的 ArtifactVersion
```

## 6. 真实性语义

| 语义 | 产品要求 |
| --- | --- |
| Live Run | 真实调用，允许等待、失败、重试和缓存建议 |
| Fixture | 版本化演示或测试数据，带 scenario 与 schema version |
| Live source | 本次真实运行产物，绑定 Run、SourceSnapshot、参数和时间 |
| Cached source | 来自可定位真实历史运行的产物，同时保留本次失败原因 |
| Revision | 由派生 Run 或 supersedes 关系表达，保留实际来源 |

## 7. MVP 范围

- **Research Contract**：自然语言生成 Draft、结构化编辑、确认后不可变。
- **项目与运行**：多 Project、多个可并行 Run、明确状态和恢复。
- **数据整合**：多源查询、实体对齐、字段/单位统一、质量和导出。
- **受控科学分析**：数据画像、统计分析、天体目录与星历工具、FITS/科学图像分析、可复现可视化和受资源约束的科学建模。
- **论文获取**：自动检索、去重、排序、来源和选择依据。
- **文献总结**：结构化 Summary、Evidence 和明确版本。
- **跨文献推理**：Claim、候选/最终 Relation、Trace、条件与 Evidence。
- **学术图谱**：所有边绑定 Evidence 的证据图谱。
- **科学分析产物**：AnalysisReport、Visualization 与 ModelEvaluation 均绑定输入版本、Producer、Evidence、局限和可复现参数。
- **科研工作台**：成熟 Agent 骨架、导航、Agent Activity、Artifact Workspace、Inspector 与 Composer。
- **分享与导出**：只读快照、CSV、JSON 和溯源报告。
- **反馈修订**：对象级 UserFeedback、可确认 RevisionPlan 与追加式 ArtifactVersion。

## 8. 非目标

- 泛聊天助手或无边界 AI Scientist；
- 未注册、未授权或没有资源边界的任意天文自动处理；
- 执行模型生成的任意代码、脚本或 notebook；
- 全网无限制论文爬取或付费全文绕过；
- 任意 PDF、表格或图像的全自动高精度解析；
- 无 Evidence 的科学发现；
- 大规模通用知识图谱平台；
- 完整账号、团队权限和企业审计系统；
- 无限自由窗口或完整 IDE。

## 9. 成功指标

| 指标 | MVP 目标 |
| --- | --- |
| 目标字段覆盖率 | >= 80% |
| 关键字段来源完整性 | 100% |
| 关键数值单位一致性 | 100% |
| 论文候选检索信息完整性 | 100% |
| 最终 Relation 的 Evidence 与 Trace 覆盖率 | 100% |
| GraphEdge Evidence 覆盖率 | 100% |
| 从关键结果定位 Evidence | <= 3 次交互 |
| 来源与修订标识准确率 | 100% |
