# Roadmap

| 元数据 | 值 |
| --- | --- |
| Status | Accepted |
| Authority | 里程碑结果、阶段顺序和退出门 |

本文不复制每个 Issue 的详细范围或实时状态。Issue 范围与依赖见 [Backlog](BACKLOG.md)，实时状态以 GitHub Issues 和 Milestones 为准。

## 1. 里程碑

| Milestone | Priority | 结果 | 退出门 |
| --- | --- | --- | --- |
| M0 文档与治理 | — | 核心规范、文档体系、协作和任务边界可独立使用 | 文档有唯一事实来源，索引、Issue 和规范一致 |
| M1 开发基线 | P0 | 当前基线稳定；目标前端骨架、Case Manifest、v2 最小 Contract 和双 Adapter 可运行 | X-01 通过，当前 v1 回归保持可用 |
| M2 核心功能 | P1 | 真实数据、论文、Summary、推理和 Graph 形成版本化 Evidence 链 | X-06 与 X-07 通过 |
| M3 反馈与交付 | P2 | 版本、缓存、修订、分享、部署和材料形成稳定闭环 | X-08 通过 |

Priority 与 Milestone 的映射保持：P0 → M1，P1 → M2，P2 → M3。

## 2. M0：文档与治理

M0 的目标不是增加文档数量，而是确保：

- PRD、DESIGN、Contract、Workflow、Version 和 ADR 有清晰 Authority；
- README 是入口，`docs/README.md` 是完整索引；
- Roadmap 只描述阶段结果，Backlog 只描述 Issue 依赖；
- Acceptance、Review Checklist 和 Test Strategy 职责分离；
- 参考资料与历史资料不作为当前实现依据；
- 文档、Issue 和代码可以分别标明 Current、Target、Pending 和 Archived。

## 3. M1：开发基线

### 3.1 已有回退基线

当前已具备 Vue `/api/v1`、FastAPI、PostgreSQL、Docker Compose、Schema 导出和基础 CI。该基线只承担迁移期间的可运行回退，不继续扩展目标业务。

### 3.2 目标基线顺序

1. C-01 与 D-01 分别冻结数据 Manifest 和论文/推理 Benchmark。
2. X-00 集成并冻结主案例 Case Manifest。
3. A-01 建立目标 Monorepo 空骨架与构建边界。
4. B-04 实现 v2 最小领域与传输契约。
5. A-02 建立静态视觉、首页框架和 Workspace Shell。
6. A-03 在既有 Shell 上绑定 Contract、Project/Run、双 Adapter 和 Guided Tour。
7. X-01 证明 Fixture/HTTP、生成 Contract、Session、WorkspaceSnapshot 和 ShareSnapshot 可集成。

### M1 退出标准

- 当前 Compose、v1 API 和回归测试仍可运行；
- Case Manifest 可机器校验并驱动 Contract；
- Site、Workspace 和共享包空基线可构建；
- `/api/v2` 最小资源、错误和授权契约可测试；
- Demo Replay 与 Live 使用同一 Domain Model；
- 目标能力没有通过修改 v1 或双写旧前端伪装完成。

## 4. M2：核心功能

### Phase 1 — X-06

打通：

```text
Project / Contract / Live Run
-> Dataset / FieldDictionary / Quality
-> PaperCollection
-> PaperSummary
-> Evidence / SourceSnapshot / Export
```

退出标准：真实多源数据、论文检索和 Summary 均以 ArtifactVersion 发布，前端可审查来源和 Evidence。

### Phase 2 — X-07

打通：

```text
PaperSummary
-> Claim
-> candidate / accepted Relation
-> ReasoningTrace
-> Graph ArtifactVersion
```

退出标准：Accepted Relation 和 GraphEdge 满足 Evidence/Trace 准入，固定 Benchmark 和端到端测试通过。

## 5. M3：反馈与交付

X-08 聚合以下闭环：

- CacheRecord / CacheSelector；
- Feedback / RevisionPlan / revision Run；
- 数据、Summary、Relation、Trace 和 Graph 的追加式版本；
- 来源、质量、版本和修订的统一前端表达；
- 只读 ShareSnapshot 与锁定版本导出；
- 公网 Site、Tour、Workspace、Share 和 API；
- START HERE、短片、Web、PDF、源码/API/测试与 provenance manifest。

### M3 退出标准

- Fixture、Live、Cached 和 Revision 无语义混淆；
- 历史版本、来源、Prompt/model 和 input/output hash 可定位；
- Session、Share、CSRF、授权、限流和部署安全通过；
- 外部来源或 WebGL 失败时核心体验仍可用；
- 提交材料与实际运行版本一致，可自主复现。

## 6. 阶段门原则

- X 系列阶段 Issue 只做跨模块集成验收，不替代 A/B/C/D 原子任务。
- 阶段退出以运行、测试、Artifact 和 Evidence 为证据，不以文档声明为证据。
- 未通过当前阶段门，不提前宣布下一阶段能力完成。
- 新基础设施只有在真实负载和 ADR 证明必要后引入。