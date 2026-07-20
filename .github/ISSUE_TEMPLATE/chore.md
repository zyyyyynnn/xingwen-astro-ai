---
name: Chore
about: 原子任务、维护或治理工作
labels: ["type:task"]
---

## 状态

`blocked`

使用 `ready`、`blocked`、`in-progress` 或 `review`。依赖未满足时列出阻塞 Issue，例如 `blocked by #80`。

## 背景

为什么需要这个任务，不处理会造成什么影响。

## 目标

完成后交付什么可观察结果。

## 技术范围

-

## 验收标准

- [ ] 验收项 1

## 依赖

- 前置 Issue、文档、环境或生成物；无依赖时写 `—`。

## 边界

- 明确不做什么。

## 影响范围

代码 / CI / Docker / Schema / 文档 / 部署。

## 验证

- 实际命令、结果和未执行原因。

---

**治理要求：** 必须添加 `type:task`、适用的 `area:*`、一个 `priority:p0/p1/p2`，并归入对应 Milestone。一个 Task 只包含一个主要模块、一个主要负责人和一个主要交付物。文档任务遵守 `docs/DOCUMENTATION_GOVERNANCE.md`。
