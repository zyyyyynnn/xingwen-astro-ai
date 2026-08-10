---
name: Epic
about: 跨多个原子 Task 的父级范围、边界与退出条件
labels: ["type:feature"]
---

## 目标

描述全部必需子 Task 完成后可观察、可验证的总体结果。

## 范围

- 总体目标、跨模块边界与退出条件。
- 子任务层级只通过 GitHub 原生 Sub-issue 表达。

## 跨模块边界与不变量

- 维护子任务层级、总体边界和 Epic 退出条件。
- 核对跨任务输入输出、版本、Evidence 和集成结果。
- Epic 只表示父级范围，不建立生产实现分支，也不能作为生产实现 PR 的唯一或主要 Issue。
- 原子 Task、Bug 或 Gate 分别对应一个主要交付 PR；Epic 不代替它们。

## 输出与退出证据

- 子任务交付和退出证据汇总。
- 跨任务 Contract、边界与集成结论。

## 验收标准

- [ ] 所有必需子 Task 已完成并提供可复现证据。
- [ ] 跨任务 Contract、边界和集成结果一致。
- [ ] 未完成能力不会被写入产品完成声明或 Accepted Authority。

## 边界

- 不在 Epic 中实现 Adapter、领域算法、HTTP API、UI 或其他原子能力。
- 不把子 Task 清单复制为执行依赖或正文状态。

## 治理要求

本模板只用于 Epic。原子实现统一使用 Task/Bug 模板。子任务关系使用原生 Sub-issue，不在正文
维护依赖清单或 `#` 子任务 checklist。任务状态、负责人、标签、层级与阻塞关系只使用 GitHub
native metadata，不得复制到正文。Epic 标题遵循 `CONTRIBUTING.md` 的唯一规范。
