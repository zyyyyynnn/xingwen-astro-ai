---
name: Epic
about: 跨多个原子 Task 的父级范围、边界与退出条件
labels: ["type:feature"]
---

## 目标

描述全部必需子 Task 完成后可观察、可验证的总体结果。

## Completed baseline

只填写已在 `main`、已合并 PR、当前 Contract、当前测试或真实运行中可核验的基线。
开放 Issue、Draft/Open PR、目标架构、Fixture、Benchmark、Recorded 和未来 handoff
都不是完成证据。

-

## Planned handoff

以下子任务、集成和退出条件都是计划工作，不表示已实现。

### 子任务

只使用 GitHub 原生 Sub-issue；父子层级不等于执行前置依赖。

- [ ] #

### 外部依赖

只填写子任务之外、真正阻塞该 Epic 退出的 Issue、Contract、Artifact 或外部条件；
父 Epic/普通协作关系不是阻塞。真实阻塞使用 GitHub 原生 blocked-by；无依赖写 `—`。

-

## 输出

- 子任务交付和退出证据汇总。
- 跨任务 Contract、边界与集成结论。

## 技术范围与核心不变量

- 维护子任务层级、总体边界和 Epic 退出条件。
- 核对跨任务输入输出、版本、Evidence 和集成结果。
- Epic 只表示父级范围，不建立生产实现分支，也不能作为生产实现 PR 的唯一或主要 Issue。
- 原子 Task、Bug 或 Gate 分别对应一个主要交付 PR；Epic 不代替它们。

## 验收标准

- [ ] 所有必需子 Task 已完成并提供可复现证据。
- [ ] 跨任务 Contract、边界和集成结果一致。
- [ ] 未完成能力不会被写入产品完成声明或 Accepted Authority。

## PR 交付计划

- Epic 不建立生产实现 PR。
- 子 Task、Bug 或 Gate 分别按一对一规则交付各自唯一主要 PR。
- 需要仓库文件变更时，由明确的治理 Task/Gate 或用户直接授权的 PR 承载。

## 边界

- 不把子 Task 清单复制为执行依赖。
- 不在 Epic 中实现 Adapter、领域算法、HTTP API、UI 或其他原子能力。

## 治理要求

本模板只用于 Epic。必须添加一个 `priority:p0/p1/p2` 与一个或多个 `area:*`；原子实现
统一使用 Task/Bug 模板。
