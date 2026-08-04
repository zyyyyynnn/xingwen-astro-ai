# Backlog Dependency Map

| 元数据    | 值                                                        |
| --------- | --------------------------------------------------------- |
| Status    | Accepted                                                  |
| Authority | Open M2/M3 Issue 的角色、父级、职责、直接依赖与交付物索引 |

GitHub Open Issues 是标题、正文、标签、Milestone、负责人、实时状态和原生关系的唯一来源。本文只维护 `ID / Role / Issue title / Parent / Owner / Direct dependency / Deliverable`，不复制 Issue 正文、验收清单、状态历史或完成百分比。

角色口径：

- **Epic**：维护子任务、总体边界和退出条件，不阻塞实现 Task，也不直接关联生产实现 PR。
- **Task**：一个主要模块、一个主要负责人和一个主要交付物，原则上对应一个纵向 PR。
- **Gate**：由 X 方向持有，只验证跨模块交付和阶段退出，不替代 A/B/C/D 实现。
- **Bug**：修复 Current 行为与已批准契约的偏差，不夹带新能力。

`Parent` 只表示 GitHub 原生 Sub-issue 层级，不是执行前置条件。`Direct dependency` 只列 GitHub 原生 Dependency 中真正阻止当前 Issue 开工或阶段退出的直接输入；不列 Epic、已完成基线或可由图推导的传递依赖。

## 原生 Sub-issue 层级

```text
#33
└─ #90（Completed baseline）

#44
├─ #92
└─ #93
```

#90 已关闭，只在层级图中保留事实位置，不进入 Open Issue 表，也不作为 blocker。

## M2 数据 Artifact 主链路

| ID  | Role | Issue title                                          | Parent | Owner | Direct dependency | Deliverable                                       |
| --- | ---- | ---------------------------------------------------- | ------ | ----- | ----------------- | ------------------------------------------------- |
| #33 | Epic | [C] C-03 Epic：完成补充来源与跨源实体对齐            | —      | C     | —                 | 补充来源、crossmatch、匹配 Evidence               |
| #35 | Task | [C] C-05 实现分层数据质量与 Evidence 覆盖评估        | —      | C     | —                 | per-field/row/dataset 质量与 Contract 质量门      |
| #36 | Task | [B] B-05 实现数据 Artifact、分页与导出 API           | —      | B     | #35               | 数据领域读取、行分页、锁定版本导出                |
| #37 | Task | [A] A-04 构建数据产物研究画布                        | —      | A     | #36               | 数据表、字段、质量、来源与 Evidence 对照          |

## M2 推理与 Graph Artifact

| ID  | Role | Issue title                                                   | Parent | Owner | Direct dependency | Deliverable                                        |
| --- | ---- | ------------------------------------------------------------- | ------ | ----- | ----------------- | -------------------------------------------------- |
| #44 | Epic | [D] D-04 Epic：完成 Claim、Relation 与 ReasoningTrace 准入    | —      | D     | —                 | Claim、Relation/Trace 准入与 Benchmark             |
| #92 | Task | [D] D-07 实现 LiteratureClaim 抽取、Evidence 准入与评测       | #44    | D     | —                 | Claim candidate、Evidence、Prompt/hash 和评测      |
| #93 | Task | [D] D-08 实现 Relation、ReasoningTrace 准入与评测             | #44    | D     | #92               | candidate/accepted/rejected Relation、Trace 与评测 |
| #45 | Task | [B] B-08 实现 Claim、Relation 与 Trace Artifact API           | —      | B     | #93               | 推理 Artifact 领域读取和稳定关联                   |
| #46 | Task | [A] A-07 构建跨文献推理与 Trace 对照工作区                    | —      | A     | #45               | Claim/Relation/Trace/Evidence 对照                 |
| #47 | Task | [D] D-05 生成版本化证据图谱并执行完整性校验                   | —      | D     | #36、#93          | Graph candidate、taxonomy、Evidence/Trace 完整性   |
| #48 | Task | [B] B-09 实现 Graph Artifact 与 Evidence / SourceSnapshot API | —      | B     | #47               | Graph 领域读取、过滤、规模控制与 provenance        |
| #49 | Task | [A] A-08 构建学术图谱与溯源观测台                             | —      | A     | #46、#48          | Graph、推理、来源和版本联动                        |

## M2 阶段门

| ID  | Role | Issue title                                     | Parent | Owner | Direct dependency | Deliverable                                       |
| --- | ---- | ----------------------------------------------- | ------ | ----- | ----------------- | ------------------------------------------------- |
| #62 | Gate | [X] X-06 Gate：验证数据、论文与 Summary 主链路  | —      | X     | #37               | 固定 Live Run、Artifact/Evidence 与 M2.1 退出结论 |
| #63 | Gate | [X] X-07 Gate：验证推理与证据图谱 Artifact 闭环 | —      | X     | #62、#49          | 推理/Graph Benchmark、E2E 与 M2.2 退出结论        |

## M3 版本、缓存、修订与交付

| ID  | Role | Issue title                                               | Parent | Owner | Direct dependency  | Deliverable                                         |
| --- | ---- | --------------------------------------------------------- | ------ | ----- | ------------------ | --------------------------------------------------- |
| #50 | Task | [B] B-10 实现 CacheRecord 与 CacheSelector                | —      | B     | #36、#45、#48      | 真实历史缓存匹配、选择原因与失败语义                |
| #53 | Task | [B] B-11 实现 Feedback、RevisionPlan 与 revision Run API  | —      | B     | #36、#45、#48      | Feedback、影响闭包、冲突与派生 Run                  |
| #54 | Task | [C] C-06 执行数据 RevisionPlan 并生成新 ArtifactVersion   | —      | C     | #35、#53           | 数据局部重算、复用和 supersedes candidate           |
| #55 | Task | [D] D-06 执行文献 / 推理 / 图谱 RevisionPlan 并生成新版本 | —      | D     | #47、#53           | Summary/推理/Graph 影响闭包与新版本 candidate       |
| #51 | Task | [A] A-09 建立运行来源、缓存、版本与质量状态系统           | —      | A     | #50、#53           | Cache/Revision/Conflict/Version History 统一体验    |
| #52 | Task | [A] A-10 建立上下文反馈与局部修正体验                     | —      | A     | #51、#54、#55、#63 | Feedback、RevisionPlan、revision Run 与版本对照     |
| #56 | Task | [X] X-02 部署公网 Brand Site、Workspace 与 API            | —      | X     | #52                | 公网部署、Session/Share、安全头与降级 smoke         |
| #57 | Task | [X] X-03 构建可复现的作品提交与材料交接包                 | —      | X     | #56                | START HERE、材料 provenance 与自主复现入口          |
| #64 | Gate | [X] X-08 Gate：验证版本、缓存、修订与稳定交付闭环         | —      | X     | #57                | 最终验收矩阵、部署版本、固定 Run/Version 和提交结论 |
