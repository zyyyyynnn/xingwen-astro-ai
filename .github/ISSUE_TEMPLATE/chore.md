---
name: Task / Chore
about: 原子实现、维护或治理工作
labels: ["type:task"]
---

## 状态

`ready`

只使用 `ready`、`in-progress` 或 `review`。阻塞状态由 GitHub 原生 Dependency 表达，状态行不得混入角色、负责人或 `blocked by #...`。

## 目标

完成后交付什么可观察结果。

## 输入与输出

**已完成基线**

-

**计划交接**

-

**输入**

-

**输出**

-

## 技术范围

-

## 核心不变量

-

## 验收标准

- [ ] 验收项 1

## PR 交付计划

单一交付 PR，内部按以下阶段实施：

1. 主要实现、Contract 与针对性测试。
2. 完整消费路径、回归、文档和交接证据。
3. 同一 HEAD 完成全部验收、标准 CI 和正式技术 Review 后合并。

不得拆成多个交付 PR；若阶段可独立合并并具有独立交付价值，应在开工前拆分为独立 Task。

## 边界

- 明确不做什么。

---

**治理要求：** 必须添加 `type:task`、适用的 `area:*`、一个 `priority:p0/p1/p2`，并归入对应 Milestone。一个 Task 只包含一个主要模块、一个主要负责人和一个主要交付物，并且对应一个主要交付 PR；一个 PR 也只能有一个主要 Task、Bug 或 Gate。同一 Issue 同时只能存在一个有效 Open PR。创建工作分支并产生实质改动后更新为 `in-progress`；Draft PR 创建后更新为 `review`。当前 HEAD 的 `pr_technical_review` 为 `PASS`、标准 CI 通过、PR 可合并且没有未解决的真实阻塞问题后，才可转 Ready、Squash merge，并在 `main` 合并结果核对成功后关闭 Issue。
