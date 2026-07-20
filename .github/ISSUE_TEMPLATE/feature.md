---
name: Epic
about: 跨多个原子 Task 的父级范围、边界与退出条件
labels: ["type:feature"]
---

## 状态

`blocked`

只使用 `ready`、`blocked`、`in-progress` 或 `review`。状态行不得混入 `Epic`、负责人或 `blocked by #...`；阻塞原因写在后续段落。

## 背景

说明为什么需要该 Epic、它解决什么跨任务问题，以及 Current、Target 与 Pending 的边界。

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

## 边界

- Epic 不直接承载生产实现，也不能作为生产实现 PR 的唯一 Issue。
- 不把子 Task 清单重复写入“执行依赖”。

## 影响范围

- 代码目录：
- API / Data / Workflow / Version：
- UI / Deployment / Security：
- 文档 / 材料：

## 验证

- 汇总子 Task、阶段 Gate、Benchmark、E2E 或复现证据。

---

**治理要求：** 本模板只用于 Epic。必须添加一个 `priority:p0/p1/p2`、一个或多个 `area:*`，并归入对应 Milestone。原子实现统一使用 Chore/Task 模板；不得把本模板改写为 Task。