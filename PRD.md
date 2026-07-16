# Product Requirements

| 元数据         | 值                                                       |
| -------------- | -------------------------------------------------------- |
| Status         | Accepted                                                 |
| Authority      | 用户、问题、产品范围、主流程、成功指标与非目标           |
| Implementation | A-01 runtime implemented；A-02/A-03 与产品主流程 Pending |

本文定义星文智析要解决的问题和必须交付的产品结果。交互细节见 [Workspace UX](docs/design/WORKSPACE_UX.md)，领域与接口见 [Docs Index](docs/README.md)，退出标准见 [Acceptance](docs/product/ACCEPTANCE.md)。

## 1. 产品目标

星文智析面向天文科研数据整理与证据核验场景，将自然语言研究意图转化为可确认的研究契约，并形成可复现、可溯源、可对照的科研产物链。

MVP 固定主案例为 **系外行星候选体与宿主恒星参数整合**。架构可以扩展其他天文数据整合任务，但提交版本只承诺已经通过真实运行、Evidence 和测试证明的范围。

## 2. 核心问题

- 研究目标难以转化为明确的字段、来源、论文和质量约束；
- 多源字段、单位、对象标识和缺失值难以统一；
- 论文候选、总结和跨文献关系缺少可核验来源；
- 数据、结论、推理和图谱无法稳定定位到同一运行和版本；
- AI 输出容易退化为不可审查的自然语言回答；
- 结果难以复现、分享、修订和用于作品提交。

## 3. 目标用户与任务

| 用户           | 主要任务                             | 产品响应                                     |
| -------------- | ------------------------------------ | -------------------------------------------- |
| 天文科研初学者 | 将研究意图转化为明确的数据与文献需求 | ResearchContractDraft 与 ResearchContract    |
| 科研使用者     | 对照数据、论文、结论、条件和来源     | Artifact-first Research Workspace            |
| 竞赛评审       | 判断作品是否真实、完整、可复现       | Brand Site、Guided Tour、Evidence 与版本入口 |
| 开发与复现人员 | 检查接口、数据、运行和测试           | 生成契约、源码、双 Adapter 与复现记录        |
| 材料制作人员   | 生成一致的网页、截图、视频和技术说明 | 确定性 Demo Replay 与 provenance manifest    |

## 4. 产品形态

| 体验域             | 职责                                                 |
| ------------------ | ---------------------------------------------------- |
| Brand Site         | 建立品牌、主案例和可信性认知                         |
| Guided Tour        | 用确定性场景解释 Contract、Run、Artifact 与 Evidence |
| Research Workspace | 管理项目、运行、产物审查、反馈、分享和导出           |

工作台不是通用聊天 Agent。AI 是上下文协作者；中央主区域优先展示科研产物与 Evidence。

## 5. 产品主流程

1. 用户输入研究意图，系统生成可编辑 ResearchContractDraft。
2. 用户确认对象、字段、来源、论文范围、输出和质量要求，形成不可变 ResearchContract。
3. 用户选择 Demo Replay 或 Live Run。
4. 系统生成数据、字段字典、来源快照和质量结果。
5. 系统检索论文候选，记录 Query、去重、排序和选择依据。
6. 系统生成逐项绑定 Evidence 的 PaperSummary。
7. 系统抽取 Claim，构建候选与最终 Relation、ReasoningTrace。
8. 系统生成每条边可核验的证据图谱。
9. 用户在最多三个受控面板中对照产物与 Evidence。
10. 用户导出、分享或提交对象级反馈。
11. 系统生成 RevisionPlan，通过派生 Run 产生新 ArtifactVersion，保留历史版本。

## 6. 真实性语义

执行方式、产物来源和修订关系是三个独立维度：

| 语义          | 产品要求                                                             |
| ------------- | -------------------------------------------------------------------- |
| Demo Replay   | 明确标记的确定性主案例回放                                           |
| Live Run      | 真实调用，允许等待、失败、重试和缓存建议                             |
| Fixture       | 版本化演示或测试数据，带 scenario、schema version 和 provenance note |
| Live source   | 本次真实运行产物，绑定 Run、SourceSnapshot、参数和时间               |
| Cached source | 来自可定位真实历史运行的产物，同时保留本次失败原因                   |
| Revision      | 由派生 Run 或 supersedes 关系表达，继续保留实际来源                  |

精确字段和不变量由 Data Model、Workflow 和 Data Versioning 维护。

## 7. MVP 范围

- Research Contract：自然语言生成 Draft、结构化编辑、确认后不可变。
- 项目与运行：多 Project、多个可并行 Run、明确状态和恢复。
- 数据整合：真实多源查询、实体对齐、字段/单位统一、质量和导出。
- 论文获取：自动检索、去重、排序、来源和选择依据。
- 文献总结：结构化 Summary、Evidence 和明确版本。
- 跨文献推理：Claim、候选/最终 Relation、Trace、条件与 Evidence。
- 学术图谱：受控规模 Graph，所有边绑定 Evidence。
- 科研桌面：Atlas、最多三面板 Canvas、Observatory、Console。
- 反馈修订：对象级 Feedback、RevisionPlan、追加式 ArtifactVersion。
- 分享与导出：只读快照、CSV、JSON 和溯源报告。
- 提交体验：无人讲解也可理解的首页、引导、工作台和材料入口。

## 8. 非目标

- 泛聊天助手或无边界 AI Scientist；
- 任意天文方向自动处理；
- 全网无限制论文爬取或付费全文绕过；
- 任意 PDF、表格或图像的全自动高精度解析；
- 无 Evidence 的科学发现；
- 大规模通用知识图谱平台；
- 完整账号、团队权限和企业审计系统；
- 无限自由窗口或完整 IDE。

## 9. 成功指标

| 指标                                      | MVP 目标               |
| ----------------------------------------- | ---------------------- |
| 目标字段覆盖率                            | >= 80%                 |
| 关键字段来源完整性                        | 100%                   |
| 关键数值单位一致性                        | 100%                   |
| 论文候选检索信息完整性                    | 100%                   |
| 最终 Relation 的 Evidence 与 Trace 覆盖率 | 100%                   |
| GraphEdge Evidence 覆盖率                 | 100%                   |
| 从关键结果定位 Evidence                   | <= 3 次交互            |
| Demo Replay 完整性                        | 无外部服务也可完整走读 |
| 来源与修订标识准确率                      | 100%                   |
| 图形不可用时核心流程可用                  | 100%                   |
| 核心流程键盘可用                          | 无严重阻塞问题         |

## 10. 决策原则

1. 主链路稳定优先于功能数量。
2. 科研可信和 Evidence 优先于视觉包装。
3. 可复现的结构化产物优先于长篇 AI 回复。
4. Demo、Live、Cached 和 Revision 必须按真实来源表达。
5. 宣传和材料必须能由运行、接口、产物或测试证明。
6. 未实现能力只能写为 Proposed、Pending 或后续扩展。

## 11. 关联文档

- [Acceptance](docs/product/ACCEPTANCE.md)
- [Workspace UX](docs/design/WORKSPACE_UX.md)
- [Handoff](docs/handoff/README.md)
- [Docs Index](docs/README.md)
