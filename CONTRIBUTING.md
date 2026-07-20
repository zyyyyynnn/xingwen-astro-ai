# Contributing

| 元数据    | 值                                |
| --------- | --------------------------------- |
| Status    | Accepted                          |
| Authority | Git、Issue、PR、Review 与合并流程 |

Agent 的执行纪律见 [AGENTS](AGENTS.md)；文档层级和同步规则见 [Documentation Governance](docs/DOCUMENTATION_GOVERNANCE.md)。

## 1. 标准流程

1. 从 `main` 获取最新基线。
2. 选择处于 `ready` 的现有 Task；仅在没有合适任务时创建新 Issue。
3. 从 `main` 创建任务分支。
4. 实施、测试并同步受影响的权威文档。
5. 提交 Pull Request，关联 Task Issue。
6. 处理 Review 和 CI 结果。
7. 使用 Squash merge，删除已合并分支。

`main` 必须保持可运行；禁止直接推送。

Epic 不直接建立生产实现分支；Gate 不替代 A/B/C/D 原子实现。

## 2. 分支与 Commit

分支命名：

```text
feat/a-research-canvas
feat/b-v2-artifacts
feat/c-source-crossmatch
feat/d-reasoning-admission
fix/api-version-conflict
docs/issue-governance
```

Commit 使用明确前缀：

```text
feat: add artifact version endpoint
fix: preserve evidence on revision conflict
docs: align workflow and issue boundaries
chore: update generated contracts
```

一个 Commit 只表达一个主要目的。不得将无关格式化、依赖升级或重构混入功能提交。

## 3. Issue 规范

Issue 至少包含：

- **状态**：`ready`、`blocked`、`in-progress` 或 `review`；
- **背景**：为什么需要该改动；
- **目标**：交付的可观察结果；
- **技术或用户范围**：涉及哪些能力；
- **验收标准**：可执行、可验证的完成条件；
- **依赖**：前置 Issue、Contract 或 Artifact；
- **边界**：明确不做什么；
- **影响范围**：代码、数据、契约、文档和材料；
- **验证**：预期命令、测试或复现证据。

`open` 只表示 Issue 尚未关闭，不表示可以开工。依赖未满足时必须标记为 `blocked`。

### 3.1 Issue 角色

本仓库属于个人账户，不依赖组织级自定义 Issue Type。角色通过标题、现有标签和正文表达：

| Role | 标题与标签 | 职责 | PR 规则 |
| ---- | ---------- | ---- | ------- |
| Epic | 标题包含 `Epic`，使用 `type:feature` | 维护子任务、总体边界和退出条件 | 不直接关联生产实现 PR |
| Task | 标准 `[A/B/C/D/X] ID 标题`，使用 `type:task` | 一个主要模块、一个主要负责人、一个主要交付物 | 原则上对应一个 PR |
| Gate | `[X] ID Gate：...`，使用 `type:task` 和 `area:infra` | 验证跨模块输入、阶段证据和退出结论 | 不替代 A/B/C/D 实现 |
| Bug  | 使用 `bug` | 修复 Current 行为与已批准契约的偏差 | 不夹带新能力或架构迁移 |

Epic 正文使用链接任务清单：

```markdown
- [ ] #80 B-15 冻结核心 Contract
- [ ] #81 B-16 实现 Session 安全边界
```

Gate 发现实现缺陷时，应回到所属 Task 修复；不得在 Gate PR 中直接接管生产实现。

### 3.2 标题格式

```text
[A] A-11 建立 Design Token、UI primitive 与 BrandMark
[B] B-15 冻结 /api/v2 核心领域与传输契约
[C] C-08 实现跨源实体对齐、匹配 Evidence 与审查基准
[D] D-08 实现 Relation、ReasoningTrace 准入与评测
[X] X-06 Gate：验证 v2 数据、论文与 Summary 主链路
[B] B-04 Epic：建立 /api/v2 最小领域与传输契约
```

### 3.3 Labels

每个 Issue 应有一项 priority、一项 type，并按范围添加一个或多个 area：

| 类别     | 值                                                                                        |
| -------- | ----------------------------------------------------------------------------------------- |
| area     | `area:frontend`、`area:backend`、`area:data`、`area:pipeline`、`area:graph`、`area:infra` |
| priority | `priority:p0`、`priority:p1`、`priority:p2`                                               |
| type     | `type:task`、`type:docs`、`type:feature`、`bug`、`enhancement`                            |

Priority 表达所属交付阶段，不表达 Issue 当前是否可开工：

| Priority | Milestone     |
| -------- | ------------- |
| P0       | M1 开发基线   |
| P1       | M2 核心功能   |
| P2       | M3 反馈与交付 |

当前可执行性由正文状态和依赖决定。

### 3.4 Definition of Ready

Task 进入 `ready` 前必须满足：

- 前置 Issue 已关闭，或提供冻结的版本/hash/Contract；
- 输入、输出 Schema 和数据等级明确；
- 唯一事实源已定位；
- 主要目录、模块 Owner 和边界明确；
- 不与其他 Issue 重复实现同一状态机、事务或领域算法；
- 验收标准可执行；
- Critical / High 风险具有 Owner 和验证计划。

不满足时保持 `blocked`，不得以临时 DTO、Mock 分支或复制规则绕过依赖。

### 3.5 WIP 限制

每位负责人同时最多维护：

- 一个 `in-progress` 实现 Task；
- 一个 `review` 或 Gate。

同一方向出现多个 P0/P1 Issue 时，只允许依赖图上最靠前且状态为 `ready` 的 Task 开工。需要抢占时必须记录被暂停 Issue、原因和恢复条件。

### 3.6 Definition of Done

Task 关闭必须提供：

- 关联 PR / Commit；
- 实际验证命令和结果；
- Contract、Manifest、Prompt、Fixture 或 Benchmark 版本；
- 测试数据等级；
- migration / rollback 结果（适用时）；
- 未执行项和已知限制；
- 受影响风险 ID；
- 权威文档和 Backlog 同步情况。

GitHub Issue 是任务状态的实时事实来源；[Backlog](docs/product/BACKLOG.md) 只维护 Open Issue 的角色、范围和依赖地图，不复制实时状态。

## 4. PR 规范

PR 描述至少包含：

- 关联 Task Issue；
- 改动范围与明确非目标；
- 验证命令、结果和未执行原因；
- API、Data Model、Workflow、Version、UI、部署和安全影响；
- Fixture、Live、Cached、Revision 或材料口径影响；
- migration / rollback 要点（适用时）。

PR 不接受：

- 直接关联 Epic 但没有明确 Task；
- Gate PR 接管 A/B/C/D 生产实现；
- 没有明确 Issue 或用户授权；
- 大量无关改动；
- 无可复现验证；
- 接口、实体或状态改变但未同步权威契约；
- 生成 Contract 与编写源漂移；
- Fixture、seed 或缓存来源表述失真；
- 密钥、token、连接串或受限内容泄露；
- 将 Pending 能力写成已实现。

## 5. Review 责任

作者负责：

- 提供可审查的范围和证据；
- 对已知风险和未验证项保持透明；
- 处理 Review 线程；
- 确保文档与实现同步。

审查者负责：

- 先检查 Issue 角色、范围、契约、依赖和不变量，再检查局部实现；
- 区分阻塞问题、建议优化和非本 PR 范围；
- 不以个人风格偏好扩大范围；
- 对安全、数据损坏、来源失真和不可逆迁移优先请求修改。

具体清单见 [Review Checklist](docs/quality/REVIEW_CHECKLIST.md)。

## 6. 合并标准

PR 同时满足以下条件才可合并：

- 关联明确的 Task，且所属 Epic/Gate 引用关系正确；
- 解决一个清晰目标且边界明确；
- 适用测试和 CI 通过；
- Review 阻塞项已处理；
- 契约、生成物、Issue 和文档无明显漂移；
- 不暴露敏感信息；
- 不扩大产品承诺；
- 分支可合并，目标 HEAD 未意外变化。

默认使用 Squash merge。历史或发布分支需要其他策略时，必须由仓库负责人明确批准。
