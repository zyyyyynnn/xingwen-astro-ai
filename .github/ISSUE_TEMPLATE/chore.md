---
name: Task / Chore
about: 原子实现、维护或治理工作
labels: ["type:task"]
---

## 状态

`blocked`

只使用 `ready`、`blocked`、`in-progress` 或 `review`。状态行不得混入角色或 `blocked by #...`；阻塞原因写在后续段落。

## 背景

为什么需要这个任务，不处理会造成什么影响。

## 目标

完成后交付什么可观察结果。

## 技术范围

-

## 验收标准

- [ ] 验收项 1

## Parent Epic

- 父 Epic Issue；不属于 Epic 时写 `—`。Parent Epic 仅表示层级归属，不是执行前置依赖。

## 依赖

- 只填写真正阻塞执行的前置 Issue、Contract、文档、环境或生成物；无依赖时写 `—`。

## 边界

- 明确不做什么。

## 影响范围

代码 / CI / Docker / Schema / 文档 / 部署。

## 验证

- 实际命令、结果和未执行原因。

---

**治理要求：** 必须添加 `type:task`、适用的 `area:*`、一个 `priority:p0/p1/p2`，并归入对应 Milestone。一个 Task 只包含一个主要模块、一个主要负责人和一个主要交付物。创建工作分支并产生实质改动后更新为 `in-progress`；本地 Codex Commit、Push 并创建或更新 Draft PR 后更新为 `review`，等待绑定当前 HEAD 且结论明确为 `PASS | BLOCKED` 的网页端 GPT Review。Codex 不得自行转 Ready、合并或关闭 Issue。
