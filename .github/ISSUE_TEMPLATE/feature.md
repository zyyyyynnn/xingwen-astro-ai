---
name: Epic
about: 跨多个原子 Task 的父级范围、边界与退出条件
labels: ["type:feature"]
---

## 状态

`ready`

只使用 `ready`、`in-progress` 或 `review`。阻塞状态由 GitHub 原生 Dependency 表达，状态行不得混入角色、负责人或 `blocked by #...`。

## 背景

说明为什么需要该 Epic、它解决什么跨任务问题，以及稳定范围与非目标。

## 目标

描述全部必需子 Task 完成后可观察、可验证的总体结果。

## 子任务

只使用真实 Issue 链接；父子层级不等于执行前置依赖。

- [ ] #

## 外部依赖

- 仅填写子任务之外、真正阻塞该 Epic 退出的 Issue、Contract、Artifact 或外部条件；无依赖时写 `—`。

## Epic 退出条件

- [ ] 所有必需子 Task 已完成并提供证据。
- [ ] 跨任务 Contract、边界和集成结果一致。

## PR 交付规则

- Epic 不建立生产实现 PR，也不能作为生产实现 PR 的唯一或主要 Issue。
- 每个原子 Task、Bug 或 Gate 分别对应一个主要交付 PR。
- Epic 可以作为多个子任务 PR 的补充父级引用，但不能代替这些 PR 各自的主要 Task、Bug 或 Gate。
- Epic 只在子任务完成后汇总退出证据；需要证据性变更时，应由明确 Gate 或直接授权的治理 PR 承载。

## 边界

- Epic 不直接承载生产实现。
- 不把子 Task 清单重复写入执行依赖。

## 验证

- 汇总子 Task、阶段 Gate、Benchmark、E2E 或复现证据。

---

**治理要求：** 本模板只用于 Epic。必须添加一个 `priority:p0/p1/p2`、一个或多个 `area:*`，并归入对应 Milestone。原子实现统一使用 Chore/Task 模板；不得把本模板改写为 Task，也不得把 Epic 作为生产实现 PR 的主要 Issue。
