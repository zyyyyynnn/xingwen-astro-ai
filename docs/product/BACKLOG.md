# Backlog Dependency Map

| 元数据    | 值                                  |
| --------- | ----------------------------------- |
| Status    | Accepted                            |
| Authority | Open Issue 的职责、依赖与交付物索引 |

GitHub Open Issues 是标题、正文、标签、Milestone 和实时状态的唯一来源。本文只维护 `ID / 标题 / Owner / Dependency / Deliverable`，不复制验收清单或完成百分比。

## M1 开发基线

| ID  | 标题                                                      | Owner | Dependency    | Deliverable                                                                            |
| --- | --------------------------------------------------------- | ----- | ------------- | -------------------------------------------------------------------------------------- |
| #2  | X-00 集成并冻结 MVP Case Manifest 与科研基准              | X     | #5、#6        | 冻结 Case Manifest、Source Policy、论文/推理 Benchmark 与 Graph taxonomy               |
| #3  | A-01 完成 Astro + React Monorepo 运行时硬切换             | A     | —             | Astro Site、React Workspace、八个共享包、根工具链、CI 与 Compose                       |
| #5  | C-01 冻结主案例 Case / Field Manifest                     | C     | —             | 版本化字段、单位、来源、crossmatch 与 Evidence locator 规则                            |
| #6  | D-01 冻结论文获取与推理 Benchmark Package                 | D     | —             | Search、Paper、Claim/Relation、Evidence 与 Graph 基准                                  |
| #28 | B-04 实现 `/api/v2` 最小领域与传输契约                    | B     | #2、#4、#26   | Session、Project、Contract、Run、Event、Artifact、Version、Workspace 与 Share Contract |
| #29 | A-02 建立品牌视觉系统、首页与科研工作台框架               | A     | #3            | Token、BrandMark、Visual Engine runtime、静态 Site 与 Workspace Shell                  |
| #30 | A-03 建立 Research Contract、Guided Tour 与契约驱动双通道 | A     | #3、#28、#29  | Project/Run、Contract、Repository、Fixture/HTTP、Tour、WorkspaceSnapshot 与 Share      |
| #31 | X-01 完成真实 `/api/v2` Contract 集成                     | X     | #23、#28、#30 | 生成 Contract、Adapter 一致性、Session、Workspace 与 Share 主流程                      |

## M2 数据 Artifact 主链路

| ID  | 标题                                             | Owner | Dependency    | Deliverable                                   |
| --- | ------------------------------------------------ | ----- | ------------- | --------------------------------------------- |
| #32 | C-02 接入主数据源 Adapter 与 SourceSnapshot      | C     | #2、#5        | 主数据源查询、原始响应快照与来源记录          |
| #33 | C-03 接入补充来源并实现跨源实体对齐              | C     | #5、#32       | 补充来源、crossmatch 结果与匹配 Evidence      |
| #34 | C-04 实现版本化字段映射、单位统一与数据 Artifact | C     | #32、#33      | Dataset、FieldDictionary、规则版本与 hash     |
| #35 | C-05 实现分层数据质量与 Evidence 覆盖评估        | C     | #34           | Quality Artifact、覆盖率与冲突结果            |
| #36 | B-05 实现数据 Artifact、分页与导出 API           | B     | #28、#32～#35 | 数据 Artifact、分页、Evidence 与导出 Contract |
| #37 | A-04 构建数据产物研究画布                        | A     | #30、#36      | 数据表、字段、质量、来源与 Evidence 对照体验  |

## M2 论文与 Summary Artifact

| ID  | 标题                                                         | Owner | Dependency    | Deliverable                                               |
| --- | ------------------------------------------------------------ | ----- | ------------- | --------------------------------------------------------- |
| #38 | D-02 实现论文检索、去重与 PaperCollection Pipeline           | D     | #2、#6        | Query、canonicalization、排序、选择依据与 PaperCollection |
| #39 | B-06 实现论文检索与 PaperCollection Artifact API             | B     | #28、#38      | PaperCollection、Run/Version 与来源 API                   |
| #40 | A-05 构建论文获取与候选审查工作区                            | A     | #30、#39      | 论文候选、检索依据、来源和选择状态体验                    |
| #41 | D-03 实现版本化 PaperSummary Prompt、Schema 与 Evidence 校验 | D     | #6、#38       | PaperSummary、Prompt 版本与 Evidence 校验                 |
| #42 | B-07 实现 PaperSummary Artifact 与 Evidence API              | B     | #28、#41      | PaperSummary、Evidence 与版本 API                         |
| #43 | A-06 构建文献总结与 Evidence 阅读工作区                      | A     | #30、#40、#42 | Summary、引用、局限与 Evidence 对照体验                   |

## M2 推理与 Graph Artifact

| ID  | 标题                                                      | Owner | Dependency | Deliverable                                       |
| --- | --------------------------------------------------------- | ----- | ---------- | ------------------------------------------------- |
| #44 | D-04 实现 Claim / Relation / ReasoningTrace 准入与评测    | D     | #6、#41    | Claim、Relation、Trace、准入结果与 Benchmark      |
| #45 | B-08 实现 Claim、Relation 与 Trace Artifact API           | B     | #28、#44   | 推理 Artifact、Evidence 与 Trace API              |
| #46 | A-07 构建跨文献推理与 Trace 对照工作区                    | A     | #43、#45   | Claim、Relation、条件、Trace 与 Evidence 对照体验 |
| #47 | D-05 生成版本化证据图谱并执行完整性校验                   | D     | #34、#44   | Graph Artifact、taxonomy 与完整性报告             |
| #48 | B-09 实现 Graph Artifact 与 Evidence / SourceSnapshot API | B     | #28、#47   | Graph、Evidence、SourceSnapshot 与版本 API        |
| #49 | A-08 构建学术图谱与溯源观测台                             | A     | #46、#48   | Graph、推理、来源和版本联动体验                   |

## M3 版本、缓存与修订

| ID  | 标题                                                  | Owner | Dependency                   | Deliverable                                      |
| --- | ----------------------------------------------------- | ----- | ---------------------------- | ------------------------------------------------ |
| #50 | B-10 实现 CacheRecord 与 CacheSelector                | B     | #36、#39、#42、#45、#48      | 缓存登记、匹配、选择原因与失败语义               |
| #51 | A-09 建立运行来源、缓存、版本与质量状态系统           | A     | #30、#50                     | 来源、质量、版本和缓存状态体验                   |
| #52 | A-10 建立上下文反馈与局部修正体验                     | A     | #37、#43、#46、#49、#53      | Feedback、RevisionPlan 与版本对照体验            |
| #53 | B-11 实现 Feedback、RevisionPlan 与 revision Run API  | B     | #28、#36、#39、#42、#45、#48 | Feedback、影响闭包、冲突与 revision Run Contract |
| #54 | C-06 执行数据 RevisionPlan 并生成新 ArtifactVersion   | C     | #34、#35、#53                | 数据派生 Run、新版本与 supersedes 链             |
| #55 | D-06 执行文献 / 推理 / 图谱 RevisionPlan 并生成新版本 | D     | #41、#44、#47、#53           | 文献、推理与 Graph 派生版本                      |

## M3 部署、材料与阶段门

| ID  | 标题                                                   | Owner | Dependency               | Deliverable                                               |
| --- | ------------------------------------------------------ | ----- | ------------------------ | --------------------------------------------------------- |
| #56 | X-02 部署公网 Brand Site、Workspace 与 API             | X     | #50、#51、#52、#53、#63  | 公网 Site、Workspace、API、数据库与发布验证               |
| #57 | X-03 构建可复现的作品提交与材料交接包                  | X     | #51、#52、#56、#62、#63  | START HERE、材料 provenance 与复现入口                    |
| #62 | X-06 Phase 1：打通 v2 数据、论文与总结 Artifact 主链路 | X     | #28、#31～#43 中相关任务 | Dataset、PaperCollection、PaperSummary 与 Evidence 集成门 |
| #63 | X-07 Phase 2：打通 v2 推理与证据图谱 Artifact 闭环     | X     | #44～#49、#62            | Claim、Relation、Trace、Graph 与 Evidence 集成门          |
| #64 | X-08 Phase 3：完成版本、缓存、修订与稳定交付闭环       | X     | #50～#57、#63            | 版本、缓存、修订、部署与材料退出门                        |
