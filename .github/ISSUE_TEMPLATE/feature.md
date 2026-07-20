---
name: Feature
about: 新功能或 Epic
labels: ["type:feature"]
---

## 状态

`blocked`

使用 `ready`、`blocked`、`in-progress` 或 `review`。依赖未满足时列出阻塞 Issue，例如 `blocked by #80`。

## 角色

`Epic` 或 `Task`。Epic 必须维护真实子 Issue 清单，不直接关联生产实现 PR；原子实现优先使用 Chore/Task 模板。

## 背景

说明问题、用户/系统影响和现有事实。区分 Current、Target 与 Pending。

## 目标

描述完成后可观察、可验证的交付结果。

## 用户或技术范围

-

## 子任务

Epic 使用真实 Issue 链接；非 Epic 删除本节。

- [ ] #

## 验收标准

- [ ] 可执行验收项 1
- [ ] 可执行验收项 2

## 依赖

- 前置 Issue、Contract、Artifact 或外部条件；无依赖时写 `—`。

## 边界

- 明确本 Issue 不负责的内容。

## 影响范围

- 代码目录：
- API / Data / Workflow / Version：
- UI / Deployment / Security：
- 文档 / 材料：

## 验证

- 命令、测试、Benchmark、E2E 或复现证据。
- 需要覆盖的失败、权限、来源或版本场景。

---

**治理要求：** 必须添加一个 `priority:p0/p1/p2`、一个或多个 `area:*`，并归入对应 Milestone。实时范围与状态只维护在 GitHub Issue；相关文档按 `docs/DOCUMENTATION_GOVERNANCE.md` 同步唯一事实来源。
