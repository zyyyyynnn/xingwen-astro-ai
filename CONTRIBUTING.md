# Contributing

| 元数据    | 值                                         |
| --------- | ------------------------------------------ |
| Status    | Accepted                                   |
| Authority | Git、Issue、PR、正式技术 Review 与合并流程 |

Agent 的执行协议与项目约束见 [AGENTS](AGENTS.md)；文档分类和唯一事实来源规则见 [Documentation Governance](docs/DOCUMENTATION_GOVERNANCE.md)。

## 1. 标准流程

1. 从 `main` 获取最新基线。
2. 到 GitHub Issues 中查看已明确指派给自己的未关闭任务，即 Assignee 包含自己的 Issue。开始前完整阅读任务的目标、范围、依赖、边界和验收标准；未明确指派的任务不要自行开工，用户在当前会话直接明确授权的任务除外。根据工作类型选择处于 `ready` 的 Task、Bug 或 Gate。
3. 从 `main` 创建任务分支；空分支本身不改变 Issue 状态。
4. 分支产生首个实质改动时，如有关联的主要 Issue，将其更新为 `in-progress`；随后实施、测试并同步受影响的权威文档。
5. 本地 Codex Commit、Push 并创建或更新 Draft Pull Request，原则上关联一个主要 Task、Bug 或 Gate；直接用户授权的单次治理或维护任务可在 PR 描述中记录授权来源。Epic 只能作为父级补充引用。
6. Draft PR 等待正式技术 Review 时，如有关联的主要 Issue，将其更新为 `review`。
7. 处理正式技术 Review 和 CI 结果；新 Commit 会使旧 Review 失效，必须在新 HEAD 上重新审查，新 Review 显式 supersede 同 scope 旧 Review。
8. 当前 HEAD 的 `pr_technical_review` 为 `PASS`、标准 CI 均通过、PR 可合并且没有未解决的真实阻塞问题后，可由审查者或 Codex 转 Ready 并 Squash merge；核对 `main` 合并结果后关闭关联 Issue，随后删除已合并分支。

`main` 必须保持可运行；禁止直接推送。

Epic 不直接建立生产实现分支；Gate 不替代 A/B/C/D 原子实现。

## 2. 分支与 Commit

分支命名：

```text
feat/a-research-canvas
feat/b-artifact-reader
feat/c-source-crossmatch
feat/d-reasoning-admission
fix/api-contract-conflict
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

Issue 正文只保留：

- **状态**：状态行只能是 `ready`、`in-progress` 或 `review`；
- **目标**：交付的可观察结果；
- **输入与输出**：已完成基线与计划交接；
- **技术范围**：涉及的能力和主要模块；
- **核心不变量**：不能破坏的契约、数据和权限边界；
- **验收标准**：可执行、可验证的完成条件；
- **PR 交付计划**：可独立验证的纵向切片；
- **边界**：明确不做什么。

`open` 只表示 Issue 尚未关闭，不表示可以开工。GitHub 原生 Sub-issue 表示层级，Dependency 表示直接阻塞；正文不复制父子关系或直接依赖清单。

Assignee 只表示任务执行归属，不表示额外审查权或合并审批权；任务执行人、模块 Owner 和风险 Owner 也不构成正式技术 Review 之后的第二道授权门。

状态行不得附加角色、依赖或 Issue 编号。角色由标题和标签表达；阻塞关系只由 GitHub 原生 Dependency 表达。

### 3.1 Issue 角色

本仓库属于个人账户，不依赖组织级自定义 Issue Type。角色通过标题、现有标签和正文表达：

| Role | 标题与标签                                           | 职责                                         | PR 规则                                             |
| ---- | ---------------------------------------------------- | -------------------------------------------- | --------------------------------------------------- |
| Epic | 标题包含 `Epic`，使用 `type:feature`                 | 维护子任务、总体边界和退出条件               | 只能作为父级引用，不能作为生产实现 PR 的唯一 Issue  |
| Task | 标准 `[A/B/C/D/X] ID 标题`，使用 `type:task`         | 一个主要模块、一个主要负责人、一个主要交付物 | 生产实现 PR 的主要 Issue，原则上对应一个 PR         |
| Gate | `[X] ID Gate：...`，使用 `type:task` 和 `area:infra` | 验证跨模块输入、阶段证据和退出结论           | 阶段验证或证据 PR 的主要 Issue，不替代 A/B/C/D 实现 |
| Bug  | 使用 `bug`                                           | 修复 Current 行为与已批准契约的偏差          | 修复 PR 的主要 Issue，不夹带新能力或架构迁移        |

Feature 模板仅用于 Epic。原子 Task 使用 Chore/Task 模板；不得创建 `Role=Task + type:feature` 的组合。

Epic 与 Task 的层级只使用 GitHub 原生 Sub-issue；正文不维护重复任务清单或 `Parent Epic` 章节。

**Parent Epic 表示层级归属，不是执行前置依赖。** Task 不得因为父 Epic 尚未关闭而被原生 Dependency 阻塞；只根据其真正的前置输入决定可执行性。Epic 的退出依赖子 Task 完成，但子 Task 不反向依赖父 Epic。

Gate 发现实现缺陷时，应回到所属 Task 或 Bug 修复；不得在 Gate PR 中直接接管生产实现。

### 3.2 标题格式

```text
[A] A-11 建立 Design Token、UI primitive 与 BrandMark
[B] B-15 冻结 /api 核心领域与传输契约
[C] C-08 实现跨源实体对齐、匹配 Evidence 与审查基准
[D] D-08 实现 Relation、ReasoningTrace 准入与评测
[X] X-06 Gate：验证数据、论文与 Summary 主链路
[B] B-04 Epic：建立 /api 最小领域与传输契约
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

`ready` 表示 Issue 的范围、交接和验收已准备进入计划队列，不表示当前即可开工。Task、Bug 或 Gate 使用 `ready` 前必须满足：

- 输入、输出 Schema、数据等级和计划交接明确；
- 唯一事实源已定位；
- 主要目录、模块 Owner 和边界明确；
- 不与其他 Issue 重复实现同一状态机、事务或领域算法；
- 验收标准可执行；
- Critical / High 风险具有 Owner 和验证计划。

Parent Epic 保持 Open 不影响子 Task 进入 `ready`；父子层级不得被当作 prerequisite。

从 `ready` 开始实质工作还必须满足：没有未完成的原生 Dependency，或对应输入已经提供冻结版本/hash/Contract。Gate 只能在必需输入完成并提供可复现版本和验证证据后开始验证。

等待直接输入期间，正文保持 `ready`，编号左侧的阻塞状态由 GitHub 原生 Dependency 计算。不得移除真实 Dependency，也不得以临时 DTO、Mock 分支或复制规则绕过依赖；正文不增加另一套阻塞枚举。

### 3.5 状态迁移

```text
ready → in-progress → review → closed
```

- 创建有效工作分支并产生实质改动后，Issue 必须从 `ready` 更新为 `in-progress`。
- 创建 PR 并准备正式技术 Review 后，Issue 更新为 `review`。
- 分支废弃或工作暂停时，必须记录原因、清理或归档分支，并恢复为 `ready`；尚未完成的直接输入继续保留为原生 Dependency。
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

- 一个主要关联 Issue，或用户在当前会话直接授权任务的可追溯授权背景；
- 所属 Epic 或上级 Gate 的补充引用（适用时）；
- 改动范围与明确非目标；
- 验证命令、结果和未执行原因；
- API、Data Model、Workflow、Version、UI、部署和安全影响；
- Fixture、Live、Cached、Revision 或材料口径影响；
- migration / rollback 要点（适用时）。

PR 不接受：

- 生产实现只关联 Epic，没有明确 Task 或 Bug；
- Gate PR 接管 A/B/C/D 生产实现；
- 没有明确 Issue 或可追溯的用户直接授权；
- 大量无关改动；
- 无可复现验证；
- 接口、实体或状态改变但未同步权威契约；
- 生成 Contract 与编写源漂移；
- Fixture、seed 或缓存来源表述失真；
- 密钥、token、连接串或受限内容泄露；
- 将 Pending 能力写成已实现。

## 5. 正式技术 Review 责任

合格审查者可以是人工审查者、Codex、网页端 GPT、独立审查 Agent 或用户明确授权的其他技术审查主体；不以工具、模型、客户端或入口决定 Review 是否有效。默认由独立于实现过程的审查者执行正式 Review；用户明确授权当前 Agent 兼任审查者时允许执行，但必须先结束实现阶段、重新 fetch、固定 base 和当前 HEAD、重新读取完整 diff、分别执行 Standards 与 Spec 审查，并保存独立的 GitHub Pull Request Review。普通 PR Comment、Issue Comment 或线程回复不能满足正式 Review 门禁。

作者负责：

- 提供可审查的范围和证据；
- 对已知风险和未验证项保持透明；
- 处理正式技术 Review 线程；
- 确保文档与实现同步。

审查者负责：

- 先检查 Issue 角色、范围、契约、依赖和不变量，再检查局部实现；
- 区分阻塞问题、建议优化和非本 PR 范围；
- 不以个人风格偏好扩大范围；
- 对安全、数据损坏、来源失真和不可逆迁移优先请求修改。

阻塞项与非阻塞建议的唯一完整定义见 [Review Checklist](docs/quality/REVIEW_CHECKLIST.md)。审查者只应阻塞真实影响当前 PR 正确性或可合并性的问题，不得以风格偏好、范围外增强或额外治理层扩大范围。

审查结论必须保存为 GitHub Pull Request Review；其 state 为 `COMMENTED`、`APPROVED` 或 `CHANGES_REQUESTED`。普通评论、线程、实施过程中的自审、测试或总结不能代替正式技术 Review。

正式记录至少使用以下机器可读字段；普通无结论评论不能满足门禁：

```text
review_type: technical
review_purpose: pr_technical_review | benchmark_scientific_review
review_scope:
  target_type: pull_request | <benchmark object type>
  target_ids: [<zyyyyynnn/xingwen-astro-ai#PR | object id>]
reviewed_head_sha: <40-char SHA>
verdict: PASS | BLOCKED
blocking_findings:
non_blocking_findings:
reviewed_at: <timezone-aware timestamp>
reviewer_kind: human | codex | web_gpt | agent
reviewer_identity: <真实可追溯身份>
review_authorization: repository_policy | user_explicit
evidence_actor_identity: github:<实际发布 Review 的登录名>
review_evidence_state: COMMENTED | APPROVED | CHANGES_REQUESTED
```

- `reviewer_kind` 只记录来源（human/codex/web_gpt/agent），不用于决定 Review 是否有效。
- `reviewer_identity` 标识实际技术审查主体；`evidence_actor_identity` 标识发布 GitHub Review 的账号。二者可以不同，但都必须真实且与授权记录一致。
- `pr_technical_review` 审查代码、契约、测试、来源政策、治理文档和可合并性；PASS scope 必须且只能绑定完整 PR，例如 `pull_request: zyyyyynnn/xingwen-astro-ai#96`，单个 Benchmark 对象不能通过 PR Gate。
- `benchmark_scientific_review` 逐项核验来源标识、Evidence、Summary、Claim、Relation、Trace 和 Graph；它不能替代技术 Review，技术 Review 也不能批准科研 Benchmark。
- GitHub state 与 verdict 必须一致：`APPROVED => PASS`、`CHANGES_REQUESTED => BLOCKED`；`COMMENTED` 可承载任一结论，但正文必须包含独立一行 `verdict: PASS` 或 `verdict: BLOCKED`。
- 同一 purpose/scope 的新 Review 必须显式 supersede 上一轮并使用新的 GitHub Review URL；最新叶节点为有效结论，未解决的 `BLOCKED` scope 阻止通过。
- 合并门要求最新技术 Review 的 `reviewed_head_sha` 等于 PR 当前 HEAD 且 verdict 为 `PASS`；Review 后新增 Commit 时必须重新 Review。
- 接受记录前必须通过 GitHub API 读取对应 Pull Request Review，核对 repository/PR、actor、state、commit id 和包含明确 verdict 的正文；`actor` 必须等于 `evidence_actor_identity`，仅匹配 URL 外形不能通过。
- 不得伪造审查者身份、冒充其他审查主体，或把普通进度评论当作 `PASS`。当前 HEAD 的 `pr_technical_review` 尚未 `PASS`、标准 CI 未全部成功、HEAD 已变化、PR 不可合并或仍有真实阻塞问题时，Codex 不得转 Ready、合并 PR 或关闭关联 Issue；条件满足后可由审查者或 Codex 执行标准合并流程，不存在额外人工 PR Review、负责人二次批准或单独授权评论门。

具体清单见 [Review Checklist](docs/quality/REVIEW_CHECKLIST.md)。

## 6. 合并标准

PR 同时满足以下条件才可合并：

- 生产实现关联明确的 Task 或 Bug；阶段验证或证据 PR 关联明确的 Gate；Epic 只作为父级补充引用；
- 解决一个清晰目标且边界明确；
- 适用测试和 CI 通过；
- 最新正式技术 Review 绑定当前 HEAD、结论为 `PASS`，且所有阻塞项已处理；
- 契约、生成物、Issue 和文档无明显漂移；
- 不暴露敏感信息；
- 不扩大产品承诺；
- 分支可合并，目标 HEAD 未意外变化。

默认使用 Squash merge。上述条件满足后，审查者或 Codex 均可执行；历史或发布分支如需其他策略，必须在对应 Issue 或 PR 范围中事先明确，不得临时绕过 CI 或改写历史。
