---
name: Task / Chore
about: 原子实现、维护或治理工作
labels: ["type:task"]
---

## 目标

完成后交付什么可观察、可验证的结果。

## 输入

-

## 输出

-

## 技术范围

- 一个主要模块、一个可观察交付物。
- 明确不修改的边界、公共接口、数据版本与失败语义。

## 核心不变量

-

## 失败语义

-

## 验收标准

- [ ] 每项验收都能通过测试、运行、Contract 或可复核材料观察。
- [ ] 覆盖正常路径、关键边界和失败/拒绝路径。
- [ ] 版本、Evidence、ownership、权限和错误语义没有回退。
- [ ] 提供真实验证命令、结果与未验证项。

## PR 交付计划

默认 Atomic Delivery 使用一个主要交付 PR；主要实现、Contract、针对性测试、完整消费路径、回归、文档与交接证据必须在同一最终 HEAD 完成。标准 CI 和正式技术 Review 通过后再合并；可独立交付的后续能力应在开工前拆分为新 Task。

用户或维护者明确授权 Grouped Delivery 时，本 Task / Chore 可以与同一垂直闭环中的其他原子 Issue 共同交付，但必须保持本 Issue 独立的 acceptance/evidence，不能借打包扩大范围或降低退出标准。

## 边界

- 明确不做什么。
- 不夹带无关功能、依赖升级或重构。

## 治理要求

本模板只用于原子 Task / Chore。默认 Atomic Delivery 与明确授权的 Grouped Delivery 均遵循 `CONTRIBUTING.md`；同一 Issue 同时最多一个有效主要交付 PR。真实阻塞使用原生依赖。任务状态、负责人、标签、层级与阻塞关系只使用 GitHub native metadata，不得复制到正文，不在正文维护第二套动态状态、依赖清单或子任务 checklist。Issue 标题遵循 `CONTRIBUTING.md` 的唯一规范。
