# Contributing

| 元数据    | 值                                |
| --------- | --------------------------------- |
| Status    | Accepted                          |
| Authority | Git、Issue、PR、网页端 GPT Review 与合并流程 |

Agent 的执行纪律见 [AGENTS](AGENTS.md)；文档层级和同步规则见 [Documentation Governance](docs/DOCUMENTATION_GOVERNANCE.md)。

## 1. 标准流程

1. 从 `main` 获取最新基线。
2. 根据工作类型选择处于 `ready` 的现有 Issue：生产实现使用 Task 或 Bug；阶段验证、证据或退出结论使用 Gate。仅在没有合适 Issue 时创建新 Issue。
3. 从 `main` 创建任务分支；空分支本身不改变 Issue 状态。
4. 分支产生首个实质改动时，将主要 Issue 更新为 `in-progress`，随后实施、测试并同步受影响的权威文档。
5. 本地 Codex Commit、Push 并创建或更新 Draft Pull Request，关联一个主要 Task、Bug 或 Gate；Epic 只能作为父级补充引用。
6. Draft PR 等待网页端 GPT Review 时，将主要 Issue 更新为 `review`。
7. 处理网页端 GPT Review 和 CI 结果；新 Commit 会使旧 Review 失效，必须在新 HEAD 上重新审查。
8. 当前 HEAD 的网页端 GPT `PASS` 与 CI 均通过后，仅由仓库负责人转 Ready 并 Squash merge，随后删除已合并分支。

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

- **状态**：状态行只能是 `ready`、`blocked`、`in-progress` 或 `review`；
- **背景**：为什么需要该改动；
- **目标**：交付的可观察结果；
- **技术或用户范围**：涉及哪些能力；
- **验收标准**：可执行、可验证的完成条件；
- **Parent Epic**：仅 Task 属于某个 Epic 时填写；否则为 `—`；
- **依赖**：真正阻塞执行的前置 Issue、Contract 或 Artifact；
- **边界**：明确不做什么；
- **影响范围**：代码、数据、契约、文档和材料；
- **验证**：预期命令、测试或复现证据。

`open` 只表示 Issue 尚未关闭，不表示可以开工。依赖未满足时必须标记为 `blocked`。

状态行不得写成 `Epic · ready`、`Gate · blocked by #6` 等复合文本。角色由标题和标签表达；阻塞 Issue、分支、PR 和说明写在状态行之后的独立段落。

### 3.1 Issue 角色

本仓库属于个人账户，不依赖组织级自定义 Issue Type。角色通过标题、现有标签和正文表达：

| Role | 标题与标签 | 职责 | PR 规则 |
| ---- | ---------- | ---- | ------- |
| Epic | 标题包含 `Epic`，使用 `type:feature` | 维护子任务、总体边界和退出条件 | 只能作为父级引用，不能作为生产实现 PR 的唯一 Issue |
| Task | 标准 `[A/B/C/D/X] ID 标题`，使用 `type:task` | 一个主要模块、一个主要负责人、一个主要交付物 | 生产实现 PR 的主要 Issue，原则上对应一个 PR |
| Gate | `[X] ID Gate：...`，使用 `type:task` 和 `area:infra` | 验证跨模块输入、阶段证据和退出结论 | 阶段验证或证据 PR 的主要 Issue，不替代 A/B/C/D 实现 |
| Bug  | 使用 `bug` | 修复 Current 行为与已批准契约的偏差 | 修复 PR 的主要 Issue，不夹带新能力或架构迁移 |

Feature 模板仅用于 Epic。原子 Task 使用 Chore/Task 模板；不得创建 `Role=Task + type:feature` 的组合。

Epic 正文使用链接任务清单：

```markdown
- [ ] #80 B-15 冻结核心 Contract
- [ ] #81 B-16 实现 Session 安全边界
```

Task 正文单独记录 Parent Epic：

```markdown
## Parent Epic

- #28
```

**Parent Epic 表示层级归属，不是执行前置依赖。** Task 不得因为父 Epic 尚未关闭而保持 `blocked`；只根据其真正的前置输入决定状态。Epic 的退出依赖子 Task 完成，但子 Task 的 `## 依赖` 不反向包含父 Epic。

Gate 发现实现缺陷时，应回到所属 Task 或 Bug 修复；不得在 Gate PR 中直接接管生产实现。

### 3.2 标题格式

```text
[A] A-11 建立 Design Token、UI primitive 与 BrandMark
[B] B-15 冻结 /api/v2 核心领域与传输契约
[C] C-08 实现跨源实体对齐、匹配 Evidence 与审查基准
[D] D-08 实现 Relation、ReasoningTrace 准入与评测
[X] X-06 Gate：验证 v2 数据、论文与 Summary 主链路
[B] B-04 Epic：建立 /api/v2 最小领域与传输契约
```

### 3.3 Labels 与 Milestones

每个 Issue 必须有一项 priority、一项 type，并按范围添加一个或多个 area：

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

当前可执行性由正文状态和执行依赖决定。

### 3.4 Definition of Ready

Task 或 Bug 进入 `ready` 前必须满足：

- 前置 Issue 已关闭，或提供冻结的版本/hash/Contract；
- 输入、输出 Schema 和数据等级明确；
- 唯一事实源已定位；
- 主要目录、模块 Owner 和边界明确；
- 不与其他 Issue 重复实现同一状态机、事务或领域算法；
- 验收标准可执行；
- Critical / High 风险具有 Owner 和验证计划。

Parent Epic 保持 Open 不影响子 Task 进入 `ready`；父子层级不得被当作 prerequisite。

Gate 进入 `ready` 前，其必需输入必须已完成并提供可复现版本和验证证据。

不满足时保持 `blocked`，不得以临时 DTO、Mock 分支或复制规则绕过依赖。

### 3.5 状态迁移

```text
blocked → ready → in-progress → review → closed
```

- 创建有效工作分支并产生实质改动后，Issue 必须从 `ready` 更新为 `in-progress`。
- 创建 PR 并准备网页端 GPT 审查后，Issue 更新为 `review`。
- 分支废弃或工作暂停时，必须记录原因、清理或归档分支，并按真实依赖恢复为 `ready` 或 `blocked`。
- 状态不得根据计划推测，必须与实际分支、PR 和依赖一致。

### 3.6 WIP 限制

每位负责人同时最多维护：

- 一个 `in-progress` 实现 Task 或 Bug；
- 一个 `review` 或 Gate。

同一方向出现多个 P0/P1 Issue 时，只允许依赖图上最靠前且状态为 `ready` 的 Task 或 Bug开工。需要抢占时必须记录被暂停 Issue、原因和恢复条件。

### 3.7 Definition of Done

Task、Bug 或 Gate 关闭必须提供与其角色相符的证据，至少包括：

- 关联 PR / Commit；
- 实际验证命令和结果；
- Contract、Manifest、Prompt、Fixture 或 Benchmark 版本；
- 测试数据等级；
- migration / rollback 结果（适用时）；
- 未执行项和已知限制；
- 受影响风险 ID；
- 权威文档和 Backlog 同步情况。

Gate 还必须记录输入版本、阶段证据和明确退出结论。

GitHub Issue 是任务状态的实时事实来源；[Backlog](docs/product/BACKLOG.md) 只维护 Open Issue 的角色、父级、范围和执行依赖地图，不复制实时状态。

## 4. PR 规范

PR 描述至少包含：

- 一个主要关联 Issue：生产实现关联 Task 或 Bug；阶段验证、证据或退出结论关联 Gate；
- 所属 Epic 或上级 Gate 的补充引用（适用时）；
- 改动范围与明确非目标；
- 验证命令、结果和未执行原因；
- API、Data Model、Workflow、Version、UI、部署和安全影响；
- Fixture、Live、Cached、Revision 或材料口径影响；
- migration / rollback 要点（适用时）。

PR 不接受：

- 生产实现只关联 Epic，没有明确 Task 或 Bug；
- Gate PR 接管 A/B/C/D 生产实现；
- 没有明确 Issue 或用户授权；
- 大量无关改动；
- 无可复现验证；
- 接口、实体或状态改变但未同步权威契约；
- 生成 Contract 与编写源漂移；
- Fixture、seed 或缓存来源表述失真；
- 密钥、token、连接串或受限内容泄露；
- 将 Pending 能力写成已实现。

## 5. 网页端 GPT Review 责任

作者负责：

- 提供可审查的范围和证据；
- 对已知风险和未验证项保持透明；
- 处理网页端 GPT Review 线程；
- 确保文档与实现同步。

网页端 GPT 审查者负责：

- 先检查 Issue 角色、范围、契约、依赖和不变量，再检查局部实现；
- 区分阻塞问题、建议优化和非本 PR 范围；
- 不以个人风格偏好扩大范围；
- 对安全、数据损坏、来源失真和不可逆迁移优先请求修改。

审查结论必须以 GitHub 可见的 Review、评论或线程保存；本地 Codex 实施过程中的自审、测试或总结不能代替网页端 GPT Review。

正式记录至少使用以下机器可读字段；普通无结论评论不能满足门禁：

```text
review_type: web_gpt
review_purpose: pr_technical_review | benchmark_scientific_review
review_scope:
  target_type: pull_request | <benchmark object type>
  target_ids: [<zyyyyynnn/xingwen-astro-ai#PR | object id>]
reviewed_head_sha: <40-char SHA>
verdict: PASS | BLOCKED
blocking_findings:
non_blocking_findings:
reviewed_at: <timezone-aware timestamp>
evidence_actor_identity: github:<login>
review_evidence_state: COMMENTED | APPROVED | CHANGES_REQUESTED
```

- `pr_technical_review` 审查代码、契约、测试、来源政策、治理文档和可合并性；PASS scope 必须且只能绑定完整 PR，例如 `pull_request: zyyyyynnn/xingwen-astro-ai#96`，单个 Benchmark 对象不能通过 PR Gate。
- `benchmark_scientific_review` 逐项核验来源标识、Evidence、Summary、Claim、Relation、Trace 和 Graph；它不能替代技术 Review，技术 Review 也不能批准科研 Benchmark。
- GitHub state 与 verdict 必须一致：`APPROVED => PASS`、`CHANGES_REQUESTED => BLOCKED`；`COMMENTED` 可承载任一结论，但正文必须包含独立一行 `verdict: PASS` 或 `verdict: BLOCKED`。
- 同一 purpose/scope 的新 Review 必须显式 supersede 上一轮并使用新的 GitHub Review URL；最新叶节点为有效结论，未解决的 `BLOCKED` scope 阻止通过。
- 合并门要求最新技术 Review 的 `reviewed_head_sha` 等于 PR 当前 HEAD 且 verdict 为 `PASS`；Review 后新增 Commit 时必须重新 Review。
- 接受记录前必须通过 GitHub API 读取对应 Review，核对 repository/PR、actor、state、commit id 和包含明确 verdict 的正文；仅匹配 URL 外形不能通过。
- 本地 Codex 不得自行认定 Review 通过、将 Draft 转 Ready、合并 PR 或关闭关联 Issue；不存在额外的人工 PR Review 门。

具体清单见 [Review Checklist](docs/quality/REVIEW_CHECKLIST.md)。

## 6. 合并标准

PR 同时满足以下条件才可合并：

- 生产实现关联明确的 Task 或 Bug；阶段验证或证据 PR 关联明确的 Gate；Epic 只作为父级补充引用；
- 解决一个清晰目标且边界明确；
- 适用测试和 CI 通过；
- 最新网页端 GPT 技术 Review 绑定当前 HEAD、结论为 `PASS`，且所有阻塞项已处理；
- 契约、生成物、Issue 和文档无明显漂移；
- 不暴露敏感信息；
- 不扩大产品承诺；
- 分支可合并，目标 HEAD 未意外变化。

默认由仓库负责人使用 Squash merge。历史或发布分支需要其他策略时，必须由仓库负责人明确批准。
