---
name: Epic
about: 跨多个原子 Task 的父级范围、边界与退出条件
labels: ["type:feature"]
---

## 状态

`ready`

只使用 `ready`、`in-progress` 或 `review`。阻塞状态由 GitHub 原生 Dependency 表达，状态行不得混入角色、负责人或 `blocked by #...`。

## 目标

描述全部必需子 Task 完成后可观察、可验证的总体结果。

## 输入与输出

**已完成基线**

-

**子任务**

只使用 GitHub 原生 Sub-issue；父子层级不等于执行前置依赖。

- [ ] #

**外部依赖**

- 仅填写子任务之外、真正阻塞该 Epic 退出的 Issue、Contract、Artifact 或外部条件；无依赖时写 `—`。

**输出**

- 子任务交付和退出证据汇总。
- 跨任务 Contract、边界与集成结论。

## 技术范围

- 维护子任务层级、总体边界和 Epic 退出条件。
- 核对跨任务输入输出、版本、证据和集成结果。
- 不在 Epic 内实现原子生产能力。

## 核心不变量

- Epic 只表示父级范围，不是子 Task 的执行前置依赖。
- Epic 不建立生产实现分支，也不能作为生产实现 PR 的唯一或主要 Issue。
- 每个原子 Task、Bug 或 Gate 分别对应一个主要交付 PR。
- Epic 可以作为多个子任务 PR 的补充父级引用，但不能代替这些 PR 各自的主要 Issue。

## 验收标准

- [ ] 所有必需子 Task 已完成并提供可复现证据。
- [ ] 跨任务 Contract、边界和集成结果一致。
- [ ] Epic 没有接管子 Task 的生产实现或 PR。

## PR 交付计划

- Epic 不建立生产实现 PR。
- 子 Task、Bug 或 Gate 分别按一对一规则交付各自唯一主要 PR。
- Epic 只在子任务完成后汇总退出证据；需要仓库文件变更时，由明确 Gate 或用户直接授权的治理 PR 承载。

## 边界

- 不把子 Task 清单复制为执行依赖。
- 不在 Epic 中实现 Adapter、领域算法、HTTP API、UI 或其他原子能力。

---

**治理要求：** 本模板只用于 Epic。必须添加一个 `priority:p0/p1/p2`、一个或多个 `area:*`，并归入对应 Milestone。原子实现统一使用 Chore/Task 模板；不得把本模板改写为 Task，也不得把 Epic 作为生产实现 PR 的主要 Issue。
