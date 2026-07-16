# Backlog Dependency Map

| 元数据 | 值 |
| --- | --- |
| Status | Accepted |
| Authority | Issue 范围分组与依赖地图 |

GitHub Issues 是标题、正文、标签、Milestone 和实时状态的唯一来源。本文只提供跨岗位依赖地图；Issue 变化时必须同步本文，但不得在这里维护完成百分比或重复完整验收标准。

任务前缀：A 前端与产品，B 后端与编排，C 数据，D 论文/推理/图谱，X 跨模块。

## 1. Phase 0 已完成基线

| Issue | 历史交付 |
| --- | --- |
| #4 B-01 | FastAPI + uv 后端骨架 |
| #21 X-04 | `web` / `api` / `postgres` Docker Compose 基线 |
| #23 X-05 | Foundation、构建、测试、Schema 和 Compose CI |
| #26 B-02 | Phase 0 Pydantic Schema 与导出基线 |
| #27 B-03 | `/api/v1` Task 创建与查询基线 |

这些 Issue 只描述当前回退基线，不承担目标 `/api/v2` 或新前端实现。

## 2. P0 / M1：目标开发基线

| Issue | 任务 | 主要产出 | 依赖 |
| --- | --- | --- | --- |
| #5 C-01 | 冻结主案例 Case / Field Manifest | 版本化字段、单位、来源、crossmatch 与 Evidence locator 规则 | 无 |
| #6 D-01 | 冻结论文获取与推理 Benchmark Package | Search、Paper、Claim/Relation、Evidence 和 Graph 基准 | 无 |
| #2 X-00 | 集成并冻结 MVP Case Manifest 与科研基准 | CaseManifest、SourcePolicy、Paper/Reasoning Benchmark、Graph taxonomy | #5、#6 |
| #3 A-01 | 重构前端 Monorepo 与运行时基线 | Site/Workspace/共享包空骨架与构建边界 | #2、#21 |
| #28 B-04 | 实现 `/api/v2` 最小领域与传输契约 | Session、Project、Draft、Contract、Run、Event、Artifact、Version、Workspace、Share | #2、#4、#26 |
| #29 A-02 | 建立品牌视觉系统、首页与科研工作台框架 | Token、BrandMark、Visual Engine runtime、静态 Site 与 Shell | #3 |
| #30 A-03 | 建立 Research Contract、Guided Tour 与契约驱动双通道 | Project/Run、Contract、Repository、Fixture/HTTP、Tour、WorkspaceSnapshot、Share | #3、#28、#29 |
| #31 X-01 | 完成真实 `/api/v2` Contract 集成 | 生成 Contract、Adapter 一致性、Session/Workspace/Share 主流程 | #23、#28、#30 |

## 3. P1 / M2：数据 Artifact 主链路

| Issue | 任务 | 依赖 |
| --- | --- | --- |
| #32 C-02 | 接入主数据源 Adapter 与 SourceSnapshot | #2、#5 |
| #33 C-03 | 接入补充来源并实现跨源实体对齐 | #32 |
| #34 C-04 | 实现版本化字段映射、单位统一与数据 Artifact | #32、#33 |
| #35 C-05 | 实现分层数据质量与 Evidence 覆盖评估 | #34 |
| #36 B-05 | 实现数据 Artifact、分页与导出 API | #28、#32～#35 |
| #37 A-04 | 构建数据产物研究画布 | #30、#36 |

## 4. P1 / M2：论文与 Summary Artifact

| Issue | 任务 | 依赖 |
| --- | --- | --- |
| #38 D-02 | 实现论文检索、去重与 PaperCollection Pipeline | #2、#6 |
| #39 B-06 | 实现论文检索与 PaperCollection Artifact API | #28、#38 |
| #40 A-05 | 构建论文获取与候选审查工作区 | #30、#39 |
| #41 D-03 | 实现版本化 PaperSummary Prompt、Schema 与 Evidence 校验 | #6、#38 |
| #42 B-07 | 实现 PaperSummary Artifact 与 Evidence API | #28、#41 |
| #43 A-06 | 构建文献总结与 Evidence 阅读工作区 | #30、#40、#42 |

## 5. P1 / M2：推理与 Graph Artifact

| Issue | 任务 | 依赖 |
| --- | --- | --- |
| #44 D-04 | 实现 Claim / Relation / ReasoningTrace 准入与评测 | #6、#41 |
| #45 B-08 | 实现 Claim、Relation 与 Trace Artifact API | #28、#44 |
| #46 A-07 | 构建跨文献推理与 Trace 对照工作区 | #43、#45 |
| #47 D-05 | 生成版本化证据图谱并执行完整性校验 | #34、#44 |
| #48 B-09 | 实现 Graph Artifact 与 Evidence / SourceSnapshot API | #28、#47 |
| #49 A-08 | 构建学术图谱与溯源观测台 | #46、#48 |

## 6. P2 / M3：缓存、版本与修订

| Issue | 任务 | 依赖 |
| --- | --- | --- |
| #50 B-10 | 实现 CacheRecord 与 CacheSelector | #36、#39、#42、#45、#48 |
| #51 A-09 | 建立运行来源、缓存、版本与质量状态系统 | #30、#50 |
| #53 B-11 | 实现 Feedback、RevisionPlan 与 revision Run API | #28、#36、#39、#42、#45、#48 |
| #52 A-10 | 建立上下文反馈与局部修正体验 | #37、#43、#46、#49、#53 |
| #54 C-06 | 执行数据 RevisionPlan 并生成新 ArtifactVersion | #34、#35、#53 |
| #55 D-06 | 执行文献 / 推理 / 图谱 RevisionPlan 并生成新版本 | #41、#44、#47、#53 |

## 7. P2 / M3：部署与材料

| Issue | 任务 | 依赖 |
| --- | --- | --- |
| #56 X-02 | 部署公网 Brand Site、Workspace 与 API | #50、#51、#52、#53、#63 |
| #57 X-03 | 构建可复现的作品提交与材料交接包 | #51、#52、#56、#62、#63 |

## 8. 阶段集成门

阶段 Issue 只负责跨模块集成与退出验收，不替代原子任务。

| Issue | 阶段结果 | 聚合依赖 |
| --- | --- | --- |
| #62 X-06 | v2 数据、论文与 Summary Artifact 主链路 | #31～#43 中相关 P1 任务 |
| #63 X-07 | v2 推理与证据图谱 Artifact 闭环 | #44～#49、#62 |
| #64 X-08 | 版本、缓存、修订、部署与材料闭环 | #50～#57、#63 |

## 9. 暂缓范围

- 任意天文方向支持；
- 全网无限制论文爬取和付费全文绕过；
- 任意 PDF、表格或图像全自动高精度解析；
- 完整账号、团队权限和企业审计；
- Redis/Celery、对象存储、图数据库或向量数据库，除非真实负载和 ADR 证明需要；
- 通用 Entity/Relation 平台和大规模知识图谱。