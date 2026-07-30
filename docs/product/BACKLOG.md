# Backlog Dependency Map

| 元数据    | 值                                                   |
| --------- | ---------------------------------------------------- |
| Status    | Accepted                                             |
| Authority | Open Issue 的角色、父级、职责、执行依赖与交付物索引 |

GitHub Open Issues 是标题、正文、标签、Milestone、负责人和实时状态的唯一来源。本文只维护 `ID / Role / Issue title / Parent / Owner / Dependency / Deliverable`，不复制验收清单、状态历史或完成百分比。

角色口径：

- **Epic**：维护子任务、总体边界和退出条件，不直接关联生产实现 PR。
- **Task**：一个主要模块、一个主要负责人和一个主要交付物，原则上对应一个 PR。
- **Gate**：由 X 方向持有，只验证跨模块交付和阶段退出，不替代 A/B/C/D 实现。
- **Bug**：修复 Current 行为与已批准契约的偏差，不夹带新能力。

`Parent` 只表示父子层级，不是执行前置条件。`Dependency` 只列真正阻塞开工或阶段退出的 Issue；子 Task 不反向依赖其 Parent Epic。

## M1 开发基线

| ID | Role | Issue title | Parent | Owner | Dependency | Deliverable |
| --- | --- | --- | --- | --- | --- | --- |
| #6 | Task | [D] D-01 冻结论文获取与推理 Benchmark Package | — | D | — | Search、Paper、Claim/Relation、Evidence 与 Graph Benchmark |
| #2 | Gate | [X] X-00 Gate：集成并冻结 MVP Case Manifest 与科研基准 | — | X | #5、#6 | 冻结 Case、SourcePolicy、Benchmark、Graph taxonomy |
| #26 | Task | [B] B-02 定义 Pydantic Schema 初版 | — | B | #4 | v1 字段对照、Schema 回归与导出漂移门禁 |
| #28 | Epic | [B] B-04 Epic：建立 /api 最小领域与传输契约 | — | B | #2、#4 | 核心 Contract、Session 安全、Workspace/Share |
| #80 | Task | [B] B-15 冻结 /api 核心领域与传输契约 | #28 | B | #2、#4 | Project、Contract、Run、Event、Artifact、Version Contract |
| #81 | Task | [B] B-16 实现 Session、ownership、CSRF 与统一写入安全边界 | #28 | B | #80 | Session、授权、幂等、Problem Details |
| #82 | Task | [B] B-17 实现 WorkspaceSnapshot、ShareSnapshot 与公开只读投影 | #28 | B | #80、#81 | Workspace 恢复、冻结分享、撤销与过期 |
| #29 | Epic | [A] A-02 Epic：建立品牌视觉系统与静态工作台框架 | — | A | #3 | Design System、Visual Engine、静态 Site/Workspace Shell |
| #84 | Task | [A] A-11 建立 Design Token、UI primitive 与 BrandMark | #29 | A | #3 | 共享 Token、primitive、BrandMark |
| #85 | Task | [A] A-12 实现 Visual Engine 生命周期、质量档与降级 | #29 | A | #3 | deterministic runtime、资源释放、Poster/Reduced Motion |
| #86 | Task | [A] A-13 组装 Brand Site 与静态 Workspace Shell | #29 | A | #84、#85 | 静态首页、Workspace Shell、a11y 与降级 |
| #87 | Task | [A] A-14 建立前端 Domain、Fixture Adapter 与 Guided Tour FSM | #30 | A | #80 | 稳定 Domain、版本化 Fixture、FSM、基础 provenance 状态 |
| #88 | Task | [A] A-15 接入 Session、Contract、Run 与 Event HTTP Adapter | #30 | A | #81、#87 | 生成 Contract Adapter、Mapper、Event 恢复 |
| #89 | Task | [A] A-16 绑定 WorkspaceSnapshot、Share 与静态 Shell 行为 | #30 | A | #82、#86、#88 | Workspace 恢复、只读分享与 Shell 行为 |

## M2 可靠运行时与通用 Artifact 边界

| ID | Role | Issue title | Parent | Owner | Dependency | Deliverable |
| --- | --- | --- | --- | --- | --- | --- |
| #76 | Task | [B] B-12 建立 Workflow PostgreSQL 模型与迁移基线 | — | B | #80 | Run/Step/Attempt/Event/Version/Execution Schema 与 Migration |
| #77 | Task | [B] B-13 实现 ResearchRun lease、StepAttempt 与恢复执行 | — | B | #76、#80 | lease/fencing、Attempt、Event、取消与崩溃恢复 |
| #78 | Task | [B] B-14 实现 ProducerExecution 与 ArtifactVersion 原子发布 | — | B | #76、#77、#80 | 唯一 Publisher、幂等、latest、Run/Step/Event 原子事务 |
| #83 | Task | [B] B-18 实现通用 Artifact、Evidence 与 SourceSnapshot 读取边界 | — | B | #76、#78、#80、#81 | 通用 Envelope、Version/Evidence/SourceSnapshot 读取与授权 |

## M2 数据 Artifact 主链路

| ID | Role | Issue title | Parent | Owner | Dependency | Deliverable |
| --- | --- | --- | --- | --- | --- | --- |
| #32 | Task | [C] C-02 接入主数据源 Adapter 与 SourceSnapshot | — | C | #2、#5 | 主来源查询、原始快照与来源执行元数据 |
| #33 | Epic | [C] C-03 Epic：完成补充来源与跨源实体对齐 | — | C | #2、#32 | 补充来源、crossmatch、匹配 Evidence |
| #90 | Task | [C] C-07 接入补充数据源 Adapter 与 SourceSnapshot | #33 | C | #2、#32 | 补充来源查询和独立 SourceSnapshot |
| #91 | Task | [C] C-08 实现跨源实体对齐、匹配 Evidence 与审查基准 | #33 | C | #32、#90 | crossmatch 规则、冲突保留、人工审查指标 |
| #34 | Task | [C] C-04 实现版本化字段映射、单位统一与数据 Artifact | — | C | #32、#90、#91 | Dataset、FieldDictionary、Evidence、规则版本/hash |
| #35 | Task | [C] C-05 实现分层数据质量与 Evidence 覆盖评估 | — | C | #34 | per-field/row/dataset 质量与 Contract 质量门 |
| #36 | Task | [B] B-05 实现数据 Artifact、分页与导出 API | — | B | #34、#35、#78、#83、#80 | 数据领域读取、行分页、锁定版本导出 |
| #37 | Task | [A] A-04 构建数据产物研究画布 | — | A | #87、#36 | 数据表、字段、质量、来源与 Evidence 对照 |

## M2 论文与 Summary Artifact

| ID | Role | Issue title | Parent | Owner | Dependency | Deliverable |
| --- | --- | --- | --- | --- | --- | --- |
| #38 | Task | [D] D-02 实现论文检索、去重与 PaperCollection Pipeline | — | D | #2、#6 | Query、canonicalization、排序、选择依据与 candidate |
| #39 | Task | [B] B-06 实现论文检索与 PaperCollection Artifact API | — | B | #38、#78、#83、#80 | PaperCollection 领域读取和候选分页 |
| #40 | Task | [A] A-05 构建论文获取与候选审查工作区 | — | A | #87、#39 | 候选、去重、排序、来源与 Evidence 对照 |
| #41 | Task | [D] D-03 实现版本化 PaperSummary Prompt、Schema 与 Evidence 校验 | — | D | #6、#38 | Summary candidate、Prompt 版本和逐项 Evidence 准入 |
| #42 | Task | [B] B-07 实现 PaperSummary Artifact 与 Evidence API | — | B | #41、#78、#83、#80 | Summary 领域读取和逐项 Evidence 对照 |
| #43 | Task | [A] A-06 构建文献总结与 Evidence 阅读工作区 | — | A | #87、#40、#42 | Summary、引用、局限与版本对照 |

## M2 推理与 Graph Artifact

| ID | Role | Issue title | Parent | Owner | Dependency | Deliverable |
| --- | --- | --- | --- | --- | --- | --- |
| #44 | Epic | [D] D-04 Epic：完成 Claim、Relation 与 ReasoningTrace 准入 | — | D | #6、#41 | Claim、Relation/Trace 准入与 Benchmark |
| #92 | Task | [D] D-07 实现 LiteratureClaim 抽取、Evidence 准入与评测 | #44 | D | #6、#41 | Claim candidate、Evidence、Prompt/hash 和评测 |
| #93 | Task | [D] D-08 实现 Relation、ReasoningTrace 准入与评测 | #44 | D | #6、#92 | candidate/accepted/rejected Relation、Trace 与评测 |
| #45 | Task | [B] B-08 实现 Claim、Relation 与 Trace Artifact API | — | B | #92、#93、#78、#83、#80 | 推理 Artifact 领域读取和稳定关联 |
| #46 | Task | [A] A-07 构建跨文献推理与 Trace 对照工作区 | — | A | #43、#45 | Claim/Relation/Trace/Evidence 对照 |
| #47 | Task | [D] D-05 生成版本化证据图谱并执行完整性校验 | — | D | #34、#93 | Graph candidate、taxonomy、Evidence/Trace 完整性 |
| #48 | Task | [B] B-09 实现 Graph Artifact 与 Evidence / SourceSnapshot API | — | B | #47、#78、#83、#80 | Graph 领域读取、过滤、规模控制与 provenance |
| #49 | Task | [A] A-08 构建学术图谱与溯源观测台 | — | A | #46、#48 | Graph、推理、来源和版本联动 |

## M2 阶段门

| ID | Role | Issue title | Parent | Owner | Dependency | Deliverable |
| --- | --- | --- | --- | --- | --- | --- |
| #62 | Gate | [X] X-06 Gate：验证 v2 数据、论文与 Summary 主链路 | — | X | #31、#76、#77、#78、#83、#32、#90、#91、#34、#35、#38、#41、#36、#39、#42、#37、#40、#43 | 固定 Live Run、Artifact/Evidence 与 M2.1 退出结论 |
| #63 | Gate | [X] X-07 Gate：验证推理与证据图谱 Artifact 闭环 | — | X | #62、#77、#78、#83、#92、#93、#47、#45、#48、#46、#49 | 推理/Graph Benchmark、E2E 与 M2.2 退出结论 |

## M3 版本、缓存、修订与交付

| ID | Role | Issue title | Parent | Owner | Dependency | Deliverable |
| --- | --- | --- | --- | --- | --- | --- |
| #50 | Task | [B] B-10 实现 CacheRecord 与 CacheSelector | — | B | #77、#78、#83、#36、#39、#42、#45、#48 | 真实历史缓存匹配、选择原因与失败语义 |
| #51 | Task | [A] A-09 建立运行来源、缓存、版本与质量状态系统 | — | A | #50、#53、#87、#83 | Cache/Revision/Conflict/Version History 统一体验 |
| #52 | Task | [A] A-10 建立上下文反馈与局部修正体验 | — | A | #51、#53、#78、#37、#43、#46、#49 | Feedback、RevisionPlan、revision Run 与版本对照 |
| #53 | Task | [B] B-11 实现 Feedback、RevisionPlan 与 revision Run API | — | B | #77、#78、#83、#36、#39、#42、#45、#48 | Feedback、影响闭包、冲突与派生 Run |
| #54 | Task | [C] C-06 执行数据 RevisionPlan 并生成新 ArtifactVersion | — | C | #34、#35、#53、#78 | 数据局部重算、复用和 supersedes candidate |
| #55 | Task | [D] D-06 执行文献 / 推理 / 图谱 RevisionPlan 并生成新版本 | — | D | #41、#47、#53、#78、#92、#93 | Summary/推理/Graph 影响闭包与新版本 candidate |
| #56 | Task | [X] X-02 部署公网 Brand Site、Workspace 与 API | — | X | #63、#50、#53、#51、#52 | 公网部署、Session/Share、安全头与降级 smoke |
| #57 | Task | [X] X-03 构建可复现的作品提交与材料交接包 | — | X | #51、#52、#56、#62、#63 | START HERE、材料 provenance 与自主复现入口 |
| #64 | Gate | [X] X-08 Gate：验证版本、缓存、修订与稳定交付闭环 | — | X | #63、#77、#78、#83、#50、#53、#54、#55、#51、#52、#56、#57 | 最终验收矩阵、部署版本、固定 Run/Version 和提交结论 |
